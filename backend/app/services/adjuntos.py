"""Archivos que el ASESOR le manda al cliente desde la ventana de Mensajes.

Hasta ahora `/mensajes` solo sabía enviar texto y plantillas: si el cliente
pedía una foto del hotel o el asesor quería contestarle con una nota de voz,
había que salirse de la plataforma. El puerto de mensajería ya sabía enviar
archivos (`messaging.send_media`); lo que faltaba era **dónde alojarlos**, que
es todo lo que hace este módulo.

Cómo funciona el envío, que explica el resto del diseño: los dos proveedores
(Meta y Twilio) mandan media **por link público** — nosotros no subimos el
archivo a ninguna parte, les pasamos una URL y ellos la descargan. Así que:

  - **Storage**, calcado de `services/mascotas`: S3 en producción
    (`ADJUNTOS_BUCKET`, y si está vacío el mismo bucket de mascotas con otro
    prefijo) y filesystem en desarrollo (`ADJUNTOS_MEDIA_DIR`).
  - **El bucket sigue privado**: el archivo se sirve por
    `GET /mensajes/adjunto/{team_id}/{nombre}`, que es público porque quien lo
    descarga es el servidor de Meta/Twilio y ese no manda ningún token.
  - **El `team_id` va en la ruta del objeto**. Es lo que hace que el adjunto de
    un tenant no se pueda pedir con la ruta de otro, y por eso el nombre del
    archivo se valida contra un regex estricto antes de tocar el storage: sin
    eso, `..%2f..%2f` sería un path traversal contra el bucket.

Dos detalles que no son obvios y que cuestan un mensaje no entregado:

  1. **WhatsApp no acepta `audio/webm`**, que es justo lo que graba Chrome con
     `MediaRecorder`. Se transcodifica a OGG/Opus con ffmpeg (va instalado en
     `Dockerfile.backend`); así además llega como nota de voz y no como archivo
     adjunto. Si ffmpeg no está (un dev sin rebuild), no se revienta: lo que ya
     viene en un formato aceptable pasa tal cual, y lo que no, se rechaza con
     un mensaje que dice qué hacer.

     Lo mismo pasa con **`video/quicktime` (.mov)**, que es lo que graba un
     iPhone y lo que exporta un Mac: entra a la lista blanca para poder
     recibirlo y mostrarlo, pero sale convertido a MP4 (`transcodificar_a_mp4`).
     En el bucket nunca queda un .mov.
  2. **El tipo se decide por la firma del archivo, no por el nombre ni por el
     `Content-Type`** que declara el navegador. Para imágenes y PDF la firma es
     obligatoria: si no coincide, no se guarda.
  3. **El archivo no sube por nuestra API**, sube directo a S3 con un POST
     prefirmado (`presignar_subida`). No es una optimización: entre el navegador
     y ECS hay dos saltos con techo propio —el compute de Amplify, que corre en
     Lambda y revienta pasados ~4,4 MB porque el cuerpo viaja en base64, y el
     API Gateway HTTP, con un límite duro de 10 MB que AWS no deja subir—. Por
     ahí un video de 10 MB **nunca** iba a pasar, dijera lo que dijera `LIMITES`.
     Subiendo contra S3 se esquivan los dos.

     Lo que sube el navegador aterriza en `adjuntos-tmp/` y **no está validado
     todavía**: son bytes de un desconocido hasta que `preparar` diga lo
     contrario. Por eso ese prefijo es intocable para el endpoint público — que
     solo sirve `adjuntos/{team}/{uuid}/{nombre}` — y por eso el paso de
     confirmación vuelve a hacer *toda* la validación sobre los bytes reales
     antes de moverlos al prefijo definitivo.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from . import imagenes

logger = logging.getLogger(__name__)

# Categorías: son los `message_type` con los que se persiste el mensaje y lo que
# espera `messaging.send_media(media_type=...)`.
IMAGEN = "image"
AUDIO = "audio"
VIDEO = "video"
DOCUMENTO = "document"

# Lista blanca (no lista negra): mime → (categoría, extensión con la que se
# guarda). Lo que no está aquí no entra, y punto.
TIPOS_PERMITIDOS: Dict[str, Tuple[str, str]] = {
    "image/jpeg": (IMAGEN, ".jpg"),
    "image/png": (IMAGEN, ".png"),
    "image/webp": (IMAGEN, ".webp"),
    "audio/ogg": (AUDIO, ".ogg"),
    "audio/mpeg": (AUDIO, ".mp3"),
    "audio/mp4": (AUDIO, ".m4a"),
    "audio/aac": (AUDIO, ".aac"),
    "audio/amr": (AUDIO, ".amr"),
    "audio/webm": (AUDIO, ".webm"),
    "video/mp4": (VIDEO, ".mp4"),
    "video/3gpp": (VIDEO, ".3gp"),
    # QuickTime (.mov) es lo que sale de un iPhone y de cualquier exportación de
    # un Mac, así que es el video que una asesora tiene a mano. WhatsApp NO lo
    # acepta: entra acá para poder recibirlo y se convierte a MP4 antes de
    # mandarlo (ver `transcodificar_a_mp4`). En el bucket nunca queda un .mov.
    "video/quicktime": (VIDEO, ".mov"),
    "application/pdf": (DOCUMENTO, ".pdf"),
    # Office y texto plano: son los que WhatsApp acepta como documento, ni uno
    # más. Un asesor manda un itinerario en Word o una cotización en Excel tan
    # seguido como un PDF.
    "application/msword": (DOCUMENTO, ".doc"),
    "application/vnd.ms-excel": (DOCUMENTO, ".xls"),
    "application/vnd.ms-powerpoint": (DOCUMENTO, ".ppt"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        DOCUMENTO, ".docx"
    ),
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
        DOCUMENTO, ".xlsx"
    ),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        DOCUMENTO, ".pptx"
    ),
    "text/plain": (DOCUMENTO, ".txt"),
    "text/csv": (DOCUMENTO, ".csv"),
}

# Marcadores de familia que devuelve `_firma` cuando los bytes solo alcanzan
# para saber el envoltorio, no el formato. Un .docx y un .xlsx son los dos un
# ZIP; un .doc y un .xls son los dos un contenedor OLE2. Distinguirlos de
# verdad exige abrir el archivo, y para lo que necesitamos —que el archivo sea
# lo que dice ser— basta con verificar la familia.
_ZIP = "application/zip"
_OLE2 = "application/x-ole-storage"

# Documento → qué firma exige. Los de texto plano no tienen firma: se validan
# aparte, comprobando que no traigan bytes binarios.
_FAMILIA_EXIGIDA: Dict[str, str] = {
    "application/pdf": "application/pdf",
    "application/msword": _OLE2,
    "application/vnd.ms-excel": _OLE2,
    "application/vnd.ms-powerpoint": _OLE2,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _ZIP,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _ZIP,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": _ZIP,
}

# Documentos sin firma estable: se aceptan solo si el contenido es texto de
# verdad (ver `_parece_texto`).
_DOCUMENTOS_DE_TEXTO = frozenset({"text/plain", "text/csv"})

# Extensión → mime, para servir el archivo con su tipo real (el storage guarda
# el archivo, no una fila con metadatos).
EXTENSIONES: Dict[str, str] = {ext: mime for mime, (_, ext) in TIPOS_PERMITIDOS.items()}

# Límites por categoría. El de imagen es el de Meta (5 MB); el resto, 16 MB.
#
# El video va en 12 MB y no en los 16 de Meta por decisión de producto: es el
# tope que se le prometió al asesor en la interfaz. Subirlo hasta 16 es cambiar
# este número y el de `frontend/lib/adjuntos.ts`, nada más — el camino de subida
# ya no tiene techo propio (ver `presignar_subida`).
LIMITES: Dict[str, int] = {
    IMAGEN: 5 * 1024 * 1024,
    AUDIO: 16 * 1024 * 1024,
    VIDEO: 12 * 1024 * 1024,
    DOCUMENTO: 16 * 1024 * 1024,
}
MAX_BYTES = max(LIMITES.values())

# Pie de foto. WhatsApp corta alrededor de los 1024 caracteres; 900 deja aire.
MAX_CAPTION = 900
# El audio va sin pie: WhatsApp no lo muestra en una nota de voz.
CATEGORIAS_CON_CAPTION = (IMAGEN, VIDEO, DOCUMENTO)

# Audio que WhatsApp acepta tal cual. Todo lo demás (hoy, `audio/webm`) hay que
# convertirlo antes de mandarlo.
AUDIO_ACEPTADO_POR_WHATSAPP = frozenset(
    {"audio/ogg", "audio/mpeg", "audio/mp4", "audio/aac", "audio/amr"}
)

# Video que WhatsApp acepta tal cual. Los dos proveedores dicen lo mismo y es
# una lista corta: MP4 y 3GP. Lo que no esté acá (hoy, `video/quicktime`) se
# convierte antes de mandarlo.
VIDEO_ACEPTADO_POR_WHATSAPP = frozenset({"video/mp4", "video/3gpp"})

PREFIJO = "adjuntos"
# Zona de tránsito de las subidas directas a S3. Es un prefijo aparte y no una
# subcarpeta de `adjuntos/` a propósito: lo que hay acá todavía no pasó por
# `preparar`, y quiero que sea imposible —no improbable— que el endpoint
# público lo alcance. Se limpia solo con una regla de ciclo de vida de 1 día,
# por si un asesor abandona la pestaña entre el `presignar` y el `confirmar`.
PREFIJO_TMP = "adjuntos-tmp"
RUTA_PUBLICA = "/mensajes/adjunto"

# Cuánto vale el POST prefirmado. Diez minutos alcanzan de sobra para subir
# 12 MB por una conexión mala y no dejan una credencial viva dando vueltas.
EXPIRA_SUBIDA = 600

# La carpeta es un uuid4 en hex y nada más: es lo que hace que un adjunto no se
# pueda adivinar, y lo que sostiene el endpoint público.
CARPETA_RE = re.compile(r"^[0-9a-f]{32}$")

# Dentro de esa carpeta, el nombre visible: caracteres inofensivos y una
# extensión de la lista blanca. Ni rutas, ni puntos de más.
NOMBRE_RE = re.compile(
    r"^[A-Za-z0-9_-]{1,%d}\.(?:%s)$"
    % (60, "|".join(sorted(e.lstrip(".") for e in EXTENSIONES)))
)

# Cuando el archivo no trae un nombre usable (una nota de voz recién grabada,
# por ejemplo) se usa este, que además es el que ve quien recibe.
NOMBRE_POR_DEFECTO = {
    IMAGEN: "imagen",
    AUDIO: "nota-de-voz",
    VIDEO: "video",
    DOCUMENTO: "documento",
}

# Vocales con tilde y ñ → ASCII. El nombre viaja dentro de una URL que descarga
# un servidor ajeno (Meta o Twilio); no es lugar para acentos.
_TRANSLITERA = str.maketrans(
    "áàäâãéèëêíìïîóòöôõúùüûñçÁÀÄÂÃÉÈËÊÍÌÏÎÓÒÖÔÕÚÙÜÛÑÇ",
    "aaaaaeeeeiiiiooooouuuuncAAAAAEEEEIIIIOOOOOUUUUNC",
)


def nombre_visible(filename: Optional[str], categoria: str, extension: str) -> str:
    """El nombre con el que el cliente va a ver el archivo en WhatsApp.

    Importa de verdad en los documentos: el chat muestra el nombre en grande, y
    un `8f3c9a…pdf` parece un archivo basura y no la cotización que el asesor
    acaba de mandar. La extensión NO sale del nombre que subieron — sale de lo
    que dictaminó la validación.
    """
    base = os.path.splitext(os.path.basename(filename or ""))[0]
    base = base.translate(_TRANSLITERA)
    base = re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-")[:60]
    return f"{base or NOMBRE_POR_DEFECTO.get(categoria, 'archivo')}{extension}"

_FFMPEG_TIMEOUT = 60   # segundos; un audio de 16 MB se convierte en muchísimo menos


@dataclass
class Preparado:
    """Un archivo ya validado y listo para guardarse."""

    data: bytes
    content_type: str
    categoria: str
    extension: str


@dataclass
class Adjunto:
    """Un archivo ya guardado, con la URL por la que lo descargará el proveedor."""

    key: str
    nombre: str
    url: str
    content_type: str
    categoria: str
    bytes_size: int


# ---------------------------------------------------------------------------
# Storage (mismo patrón que services/mascotas: S3 en prod, disco en local)
# ---------------------------------------------------------------------------

def _bucket() -> str:
    """Bucket propio si lo hay; si no, el de mascotas (privado, otro prefijo).

    Un solo bucket privado con dos prefijos evita tener que aprovisionar,
    versionar y respaldar uno nuevo para el mismo tipo de contenido.
    """
    return (
        os.getenv("ADJUNTOS_BUCKET") or os.getenv("MASCOTAS_BUCKET") or ""
    ).strip()


def _s3():
    import boto3  # import perezoso: en local el backend corre sin S3
    from botocore.config import Config

    # `s3v4` explícito por el POST prefirmado: botocore firma los POST con SigV2
    # si no se le dice otra cosa, y S3 dejó de aceptar SigV2 en los buckets
    # creados después de junio de 2020 —el nuestro es de 2026—. Sin esto la
    # subida directa falla con un 400 de S3 que no dice por qué.
    return boto3.client(
        "s3",
        region_name=os.getenv("AWS_REGION", "sa-east-1"),
        config=Config(signature_version="s3v4"),
    )


def _dir_local() -> Path:
    """Carpeta del modo disco. Se lee en cada llamada (y no al importar) para
    que un test pueda apuntarla a su carpeta temporal."""
    return Path(os.getenv("ADJUNTOS_MEDIA_DIR", "/app/media/adjuntos"))


def _ruta_local(key: str) -> Path:
    # En el bucket la key lleva el prefijo `adjuntos/` porque comparte espacio
    # con las fotos de mascotas. En disco la carpeta ya ES la de adjuntos, así
    # que el prefijo no se repite.
    relativo = key[len(PREFIJO) + 1:] if key.startswith(PREFIJO + "/") else key
    return _dir_local() / relativo


def _put_object(key: str, data: bytes, content_type: str) -> None:
    bucket = _bucket()
    if bucket:
        _s3().put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)
        return
    path = _ruta_local(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _get_object(key: str) -> Optional[bytes]:
    bucket = _bucket()
    if bucket:
        try:
            return _s3().get_object(Bucket=bucket, Key=key)["Body"].read()
        except Exception:
            # Detalle solo server-side (regla de seguridad #6).
            logger.exception("adjuntos: no se pudo leer %s de S3", key)
            return None
    try:
        return _ruta_local(key).read_bytes()
    except OSError:
        return None


def _base_publica() -> str:
    """Prefijo absoluto de las URLs que ve el proveedor.

    Tiene que ser absoluto y https: Meta y Twilio descargan el archivo desde
    sus servidores, no desde el navegador del asesor. En producción sale de
    `MASCOTAS_PUBLIC_BASE`, que ya apunta al backend público; `ADJUNTOS_PUBLIC_BASE`
    existe por si algún día se separan.
    """
    return (
        os.getenv("ADJUNTOS_PUBLIC_BASE") or os.getenv("MASCOTAS_PUBLIC_BASE") or ""
    ).rstrip("/")


def url_publica(team_id: int, carpeta: str, nombre: str) -> str:
    return f"{_base_publica()}{RUTA_PUBLICA}/{int(team_id)}/{carpeta}/{nombre}"


def key_de(team_id: int, carpeta: str, nombre: str) -> str:
    return f"{PREFIJO}/{int(team_id)}/{carpeta}/{nombre}"


# ---------------------------------------------------------------------------
# Subida directa a S3 (esquiva Amplify y el API Gateway; ver el módulo arriba)
# ---------------------------------------------------------------------------

# La referencia que devolvemos y que el cliente nos repite en el confirmar. Es
# un uuid4 nuestro, nunca algo que el cliente proponga, y se valida con este
# regex antes de tocar una key: sin eso, un `../../mascotas/` en la referencia
# leería objetos de otro prefijo del bucket.
REFERENCIA_RE = re.compile(r"^[0-9a-f]{32}$")


def hay_storage_remoto() -> bool:
    """¿Estamos contra S3? En local (disco) no hay a dónde prefirmar, y el
    asesor sube por la API de siempre — que ahí no tiene ningún salto en medio."""
    return bool(_bucket())


def _key_tmp(team_id: int, referencia: str) -> Optional[str]:
    if not REFERENCIA_RE.match(referencia or ""):
        return None
    try:
        team = int(team_id)
    except (TypeError, ValueError):
        return None
    return f"{PREFIJO_TMP}/{team}/{referencia}" if team > 0 else None


def presignar_subida(team_id: int, limite: int) -> Optional[Dict[str, object]]:
    """POST prefirmado para que el navegador suba **una sola vez, un solo
    archivo, de un tamaño acotado**.

    Tres candados, porque esto es una credencial que sale de nuestro servidor:

      - la key la elegimos nosotros (uuid4), el cliente no la propone;
      - `content-length-range` la firma S3: un cliente que ignore nuestro
        límite y empuje 2 GB recibe un 403 de S3, no un bucket lleno;
      - expira en `EXPIRA_SUBIDA`.

    Devuelve `None` si no hay bucket (desarrollo local).
    """
    bucket = _bucket()
    if not bucket:
        return None

    referencia = uuid.uuid4().hex
    key = _key_tmp(team_id, referencia)
    if key is None:
        return None

    firmado = _s3().generate_presigned_post(
        Bucket=bucket,
        Key=key,
        # Sin campos libres: lo único que el navegador aporta es el archivo. El
        # `Content-Type` no se firma porque acá no decide nada — el tipo real lo
        # dictamina `preparar` mirando los bytes.
        Fields={},
        Conditions=[["content-length-range", 1, int(limite)]],
        ExpiresIn=EXPIRA_SUBIDA,
    )
    # El log lleva la referencia, jamás la URL: la URL ES la firma (regla #1).
    logger.info("adjuntos: subida prefirmada team=%s ref=%s", team_id, referencia)
    return {
        "url": firmado["url"],
        "campos": firmado["fields"],
        "referencia": referencia,
    }


def _es_objeto_inexistente(exc: Exception) -> bool:
    """¿La excepción es "ese objeto no está" y no un problema de verdad?

    Se mira el código de S3 y no el tipo, para no importar botocore acá arriba
    —el módulo tiene que poder importarse en una máquina sin boto3 instalado—.
    """
    codigo = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
    return codigo in ("NoSuchKey", "404", "NoSuchBucket")


def leer_subida(team_id: int, referencia: str) -> Optional[bytes]:
    """Los bytes que el navegador dejó en la zona de tránsito.

    Se lee un byte más que el tope y el llamador decide: es el mismo truco del
    endpoint de subida directa, y acá importa igual —que S3 haya aceptado el
    objeto no obliga a este proceso a cargárselo entero en memoria—.
    """
    bucket = _bucket()
    key = _key_tmp(team_id, referencia)
    if not bucket or key is None:
        return None
    try:
        cuerpo = _s3().get_object(Bucket=bucket, Key=key)["Body"]
        return cuerpo.read(MAX_BYTES + 1)
    except Exception as exc:
        if _es_objeto_inexistente(exc):
            # Caso corriente, no incidente: el asesor confirmó sin que la subida
            # terminara, o la referencia ya se usó. Sin traceback, que si no el
            # log de producción se llena de ruido que parece un error.
            logger.info(
                "adjuntos: no hay subida pendiente team=%s ref=%s", team_id, referencia
            )
        else:
            # Esto sí es problema nuestro (permisos, red). Detalle server-side.
            logger.exception(
                "adjuntos: no se pudo leer la subida team=%s ref=%s", team_id, referencia
            )
        return None


def borrar_subida(team_id: int, referencia: str) -> None:
    """Saca el archivo de la zona de tránsito. Best-effort: si falla, el objeto
    se muere solo con la regla de ciclo de vida y no vale tumbar un envío que
    ya salió por no haber podido borrar un temporal."""
    bucket = _bucket()
    key = _key_tmp(team_id, referencia)
    if not bucket or key is None:
        return
    try:
        _s3().delete_object(Bucket=bucket, Key=key)
    except Exception:
        logger.warning(
            "adjuntos: quedó un temporal sin borrar team=%s ref=%s", team_id, referencia
        )


# ---------------------------------------------------------------------------
# Qué es de verdad este archivo
# ---------------------------------------------------------------------------

# Sentinela para los contenedores ISO-BMFF (`ftyp`): la firma no distingue un
# mp4 de solo audio de uno con video, así que ahí sí manda lo que declaró el
# navegador.
_FTYP = "ftyp"

# Marcas (`major_brand`) que SÍ dicen sin ambigüedad qué es el archivo. Van los
# 4 bytes que siguen a `ftyp`.
#
# `qt  ` es la importante: es QuickTime, o sea un .mov. Sin esta tabla la firma
# devolvía el sentinela y `_tipo_real` caía en su respaldo "un ftyp raro debe
# ser un mp4" — así que un .mov de iPhone se guardaba **con extensión .mp4 y
# etiquetado video/mp4** teniendo bytes de QuickTime adentro. Se subía sin
# error y era WhatsApp quien lo rechazaba después.
#
# `isom`, `mp42`, `avc1` y compañía NO están acá a propósito: esas marcas las
# comparten un mp4 de video y un m4a de solo audio, y ahí sigue mandando el
# `Content-Type` como hasta ahora.
_MARCAS_FTYP: Dict[bytes, str] = {
    b"qt  ": "video/quicktime",
    b"M4A ": "audio/mp4",
    b"M4B ": "audio/mp4",
    b"3gp4": "video/3gpp",
    b"3gp5": "video/3gpp",
    b"3gp6": "video/3gpp",
    b"3g2a": "video/3gpp",
}


def _firma(data: bytes) -> Optional[str]:
    """El tipo real según los primeros bytes. `None` si no se reconoce.

    No pretende cubrir todos los formatos del mundo: cubre los de la lista
    blanca. Para los que no tienen firma estable (AMR crudo, AAC en ADTS,
    3GP) devolver `None` es correcto — el que decide entonces es el
    `Content-Type`, y el daño posible está acotado por la lista blanca.
    """
    if len(data) < 12:
        return None
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"ID3"):
        return "audio/mpeg"
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        # 0xFF + sync: puede ser MP3 o AAC crudo (ADTS). Los separa el campo
        # "layer": en ADTS siempre va en 00, en MP3 nunca.
        es_adts = (data[1] & 0xF0) == 0xF0 and (data[1] & 0x06) == 0
        return "audio/aac" if es_adts else "audio/mpeg"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        # Matroska/WebM. Es lo que graba el navegador; si trae video, ffmpeg se
        # queda con la pista de audio igual.
        return "audio/webm"
    if data.startswith(b"#!AMR"):
        return "audio/amr"
    if data[4:8] == b"ftyp":
        return _MARCAS_FTYP.get(data[8:12], _FTYP)
    if data.startswith(b"PK\x03\x04"):
        # docx / xlsx / pptx. Cuál de los tres es, lo dice el `Content-Type`.
        return _ZIP
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        # Office viejo (.doc / .xls / .ppt): contenedor OLE2.
        return _OLE2
    return None


def _parece_texto(data: bytes) -> bool:
    """¿Esto es texto plano y no un binario con nombre de .txt?

    Un byte nulo no aparece en texto real y sí en casi cualquier ejecutable, así
    que alcanza para el filtro; después se exige que decodifique.
    """
    muestra = data[:8192]
    if b"\x00" in muestra:
        return False
    for codec in ("utf-8", "latin-1"):
        try:
            muestra.decode(codec)
            return True
        except UnicodeDecodeError:
            continue
    return False


def _normalizar_mime(valor: Optional[str]) -> str:
    """"audio/webm; codecs=opus" → "audio/webm"."""
    return (valor or "").lower().split(";")[0].strip()


def _mime_por_nombre(filename: Optional[str]) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    return EXTENSIONES.get(ext, "")


def categoria_declarada(
    content_type: Optional[str], filename: Optional[str]
) -> Optional[str]:
    """Qué dice **el navegador** que es esto, sin haber visto un solo byte.

    Existe solo para el paso previo a la subida directa: ahí hay que decidir
    con qué tope se firma el POST y todavía no tenemos el archivo. No es una
    validación y no reemplaza a `preparar` — quien manda sigue siendo la firma
    de los bytes, que se revisa al confirmar. Lo peor que puede lograr un
    cliente mintiendo acá es firmarse un tope de 16 MB para un video de 13 y
    que `preparar` se lo rechace después de subirlo.
    """
    declarado = _normalizar_mime(content_type)
    if declarado in TIPOS_PERMITIDOS:
        return TIPOS_PERMITIDOS[declarado][0]
    por_nombre = _mime_por_nombre(filename)
    if por_nombre in TIPOS_PERMITIDOS:
        return TIPOS_PERMITIDOS[por_nombre][0]
    return None


def _tipo_real(
    data: bytes, declarado: str, filename: Optional[str]
) -> Tuple[str, Optional[str]]:
    """(mime con el que se va a tratar el archivo, firma detectada).

    Orden de confianza: la firma, después el `Content-Type` y de último la
    extensión del nombre — que es la pista más débil de todas y solo se usa
    cuando el navegador manda `application/octet-stream`.
    """
    firma = _firma(data)
    if firma in TIPOS_PERMITIDOS:
        return firma, firma
    if declarado in TIPOS_PERMITIDOS:
        return declarado, firma
    por_nombre = _mime_por_nombre(filename)
    if por_nombre:
        return por_nombre, firma
    # Un `ftyp` sin `Content-Type` útil: lo más probable es un video de celular.
    if firma == _FTYP:
        return "video/mp4", firma
    return "", firma


# ---------------------------------------------------------------------------
# Conversión de audio
# ---------------------------------------------------------------------------

def transcodificar_a_ogg(data: bytes) -> Optional[bytes]:
    """Convierte cualquier audio a OGG/Opus. `None` si no se pudo.

    Nunca levanta excepción: que falte ffmpeg en una máquina de desarrollo no
    puede tumbar el request — el llamador decide qué contarle al asesor.
    """
    with tempfile.TemporaryDirectory(prefix="adjunto-") as tmp:
        entrada = Path(tmp) / "entrada"
        salida = Path(tmp) / "salida.ogg"
        entrada.write_bytes(data)
        comando = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(entrada),
            "-vn",                      # si venía con video, se descarta
            "-c:a", "libopus", "-b:a", "32k", "-ac", "1",
            str(salida),
        ]
        try:
            proceso = subprocess.run(
                comando, capture_output=True, timeout=_FFMPEG_TIMEOUT, check=False
            )
        except FileNotFoundError:
            logger.warning(
                "adjuntos: ffmpeg no está instalado, no se puede convertir el audio"
            )
            return None
        except subprocess.TimeoutExpired:
            logger.warning("adjuntos: ffmpeg no terminó en %ss", _FFMPEG_TIMEOUT)
            return None

        if proceso.returncode != 0 or not salida.exists():
            # Sin volcar la salida de ffmpeg (regla #6): solo el código.
            logger.error("adjuntos: ffmpeg falló al convertir (rc=%s)", proceso.returncode)
            return None
        convertido = salida.read_bytes()
    return convertido or None


# ---------------------------------------------------------------------------
# Conversión de video (.mov → .mp4)
# ---------------------------------------------------------------------------

# Lo que WhatsApp exige **dentro** del MP4, que es distinto del contenedor:
# H.264 de video y AAC de audio. Un .mov de iPhone grabado en "Alta eficiencia"
# trae HEVC y no sirve aunque se reetiquete.
_VIDEO_CODEC_OK = "h264"
_AUDIO_CODECS_OK = frozenset({"aac", ""})  # "" = el archivo no trae audio

# Dos presupuestos muy distintos, y la diferencia es la razón de todo el diseño
# de abajo:
#
#   - Copiar las pistas a otro contenedor (remux) no decodifica nada: son
#     milisegundos, sin importar cuánto dure el video.
#   - Recodificar sí. Y esto corre en una task de Fargate de 0,25 vCPU, detrás
#     de un API Gateway cuyo timeout de integración es de 30 s duros que AWS no
#     deja subir sin pedir cuota. Por eso el tope es 20 s: pasado eso el asesor
#     recibiría un 504 del gateway —un error que no explica nada— en vez del
#     mensaje que le dice qué hacer con su archivo.
_FFMPEG_REMUX_TIMEOUT = 20
_FFMPEG_RECODIFICAR_TIMEOUT = 20


def _codecs_de(ruta: Path) -> Optional[Tuple[str, str]]:
    """`(codec de video, codec de audio)` según ffprobe. `None` si no se pudo.

    El audio vacío significa "no tiene pista de audio", que para WhatsApp es
    válido. Devolver `None` (ffprobe ausente o archivo ilegible) hace que el
    llamador recodifique, que es la opción segura: convertir de más cuesta
    tiempo, mandar HEVC cuesta un mensaje no entregado.
    """
    comando = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,codec_name",
        "-of", "json", str(ruta),
    ]
    try:
        proceso = subprocess.run(
            comando, capture_output=True, timeout=_FFMPEG_REMUX_TIMEOUT, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("adjuntos: ffprobe no disponible o no terminó a tiempo")
        return None
    if proceso.returncode != 0:
        logger.error("adjuntos: ffprobe falló (rc=%s)", proceso.returncode)
        return None
    try:
        streams = json.loads(proceso.stdout or b"{}").get("streams") or []
    except (ValueError, TypeError):
        return None

    video = audio = ""
    for stream in streams:
        tipo = (stream.get("codec_type") or "").lower()
        nombre = (stream.get("codec_name") or "").lower()
        if tipo == "video" and not video:
            video = nombre
        elif tipo == "audio" and not audio:
            audio = nombre
    return video, audio


def transcodificar_a_mp4(data: bytes) -> Optional[bytes]:
    """Convierte un video a MP4 que WhatsApp acepte. `None` si no se pudo.

    Dos caminos, y elegir bien el barato es lo que hace que esto quepa en el
    request:

      1. **Remux** cuando las pistas ya son H.264/AAC —el caso corriente: un
         .mov de un Mac, o de un iPhone configurado en "Más compatible"—. Se
         copian tal cual a un contenedor MP4. No se decodifica ni un frame, no
         se pierde calidad y tarda lo que tarde leer el archivo.
      2. **Recodificar** cuando no (HEVC, ProRes). Es caro, y en 0,25 vCPU un
         video largo no termina dentro del timeout: por eso va a 720p con
         `ultrafast`, y si aun así no alcanza se devuelve `None` para que el
         asesor lea qué hacer en vez de esperar un 504.

    `+faststart` en los dos: mueve el índice al principio del archivo. Quien
    descarga esto es el servidor de Meta o el de Twilio, y con el índice al
    final tiene que bajar el archivo entero antes de poder empezar.

    Nunca levanta excepción, igual que `transcodificar_a_ogg`.
    """
    with tempfile.TemporaryDirectory(prefix="video-") as tmp:
        entrada = Path(tmp) / "entrada"
        salida = Path(tmp) / "salida.mp4"
        entrada.write_bytes(data)

        codecs = _codecs_de(entrada)
        puede_copiarse = (
            codecs is not None
            and codecs[0] == _VIDEO_CODEC_OK
            and codecs[1] in _AUDIO_CODECS_OK
        )
        if puede_copiarse:
            comando = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(entrada),
                "-c", "copy", "-movflags", "+faststart",
                str(salida),
            ]
            tope = _FFMPEG_REMUX_TIMEOUT
        else:
            comando = [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(entrada),
                # `-2` mantiene la proporción y deja la altura par, que libx264
                # exige. `min(1280,iw)` no agranda un video que ya sea chico.
                #
                # Se probó bajarlo a 854 para ganar tiempo y **no sirvió**:
                # medido en la task real, un HEVC de 10 s a 720p tarda 15,4 s
                # contra 15,7 s a 1280. El costo está en *decodificar* el HEVC,
                # que pasa antes del escalado, así que achicar la salida no
                # compra nada y sí se lleva calidad por delante. Lo que mueve
                # esta aguja es más CPU en la task, no este número.
                "-vf", "scale='min(1280,iw)':-2",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "96k", "-ac", "2",
                "-movflags", "+faststart",
                str(salida),
            ]
            tope = _FFMPEG_RECODIFICAR_TIMEOUT

        try:
            proceso = subprocess.run(
                comando, capture_output=True, timeout=tope, check=False
            )
        except FileNotFoundError:
            logger.warning(
                "adjuntos: ffmpeg no está instalado, no se puede convertir el video"
            )
            return None
        except subprocess.TimeoutExpired:
            logger.warning(
                "adjuntos: la conversión de video no terminó en %ss (copia=%s)",
                tope, puede_copiarse,
            )
            return None

        if proceso.returncode != 0 or not salida.exists():
            logger.error(
                "adjuntos: ffmpeg falló al convertir video (rc=%s, copia=%s)",
                proceso.returncode, puede_copiarse,
            )
            return None
        convertido = salida.read_bytes()
    logger.info(
        "adjuntos: video convertido a mp4 %d -> %d bytes (copia=%s)",
        len(data), len(convertido), puede_copiarse,
    )
    return convertido or None


# ---------------------------------------------------------------------------
# Validación
# ---------------------------------------------------------------------------

_NOMBRES_CATEGORIA = {
    IMAGEN: "imágenes",
    AUDIO: "audios",
    VIDEO: "videos",
    DOCUMENTO: "documentos",
}

TEXTO_NO_PERMITIDO = (
    "Ese tipo de archivo no se puede enviar por WhatsApp. Puedes mandar "
    "imágenes (JPG, PNG, WEBP), audio (MP3, OGG, M4A), video (MP4 o MOV) o "
    "documentos (PDF, Word, Excel, PowerPoint, TXT o CSV)."
)


def texto_excede(categoria: str) -> str:
    """El "pesa demasiado" con el tope de esa categoría.

    Lo usan los dos caminos —el chequeo previo a la subida directa y `preparar`
    sobre los bytes— para que el asesor lea exactamente lo mismo suba por donde
    suba, y para que el número salga siempre de `LIMITES` y no de un texto que
    alguien se olvide de actualizar.
    """
    return (
        f"El archivo pesa demasiado: el máximo para "
        f"{_NOMBRES_CATEGORIA[categoria]} es {LIMITES[categoria] // (1024 * 1024)} MB."
    )


def preparar(
    data: bytes,
    content_type: Optional[str] = None,
    filename: Optional[str] = None,
    *,
    convertir_video: bool = True,
) -> Tuple[Optional[Preparado], str]:
    """Valida el archivo y lo deja listo para guardar.

    Devuelve `(preparado, problema)`. `problema` es un texto **para el asesor**:
    dice qué pasó y qué hacer, sin filtrar nada del servidor.

    `convertir_video=False` guarda el video tal como llegó, sin pasarlo por
    ffmpeg. Lo usa **el camino entrante** (`guardar_entrante`), y no es una
    optimización: ese código corre dentro del webhook, y Twilio da unos 15
    segundos para contestarlo. Recodificar un HEVC puede tomar veinte, así que
    convertir ahí cambiaría "el asesor ve un video que su navegador quizá no
    reproduce" por "el webhook se pasa de tiempo y el mensaje se pierde" —
    que es muchísimo peor. Lo entrante además no vuelve a salir hacia WhatsApp:
    se guarda para *verlo* en la bandeja, y ahí el contenedor da igual.
    """
    if not data:
        return None, "El archivo llegó vacío."

    declarado = _normalizar_mime(content_type)
    mime, firma = _tipo_real(data, declarado, filename)
    if mime not in TIPOS_PERMITIDOS:
        return None, TEXTO_NO_PERMITIDO

    categoria, extension = TIPOS_PERMITIDOS[mime]

    # Imágenes: la firma manda y es obligatoria. Es lo que impide que algo
    # renombrado a .jpg termine guardado y servido como imagen.
    if categoria == IMAGEN and firma != mime:
        return None, "El archivo no parece una imagen válida."

    # Documentos: se exige que el archivo sea de la familia que dice ser (PDF,
    # ZIP para los formatos nuevos de Office, OLE2 para los viejos). Los de
    # texto plano no tienen firma, así que se comprueba que sean texto.
    if categoria == DOCUMENTO:
        if mime not in _DOCUMENTOS_DE_TEXTO and firma != _FAMILIA_EXIGIDA.get(mime):
            # Windows declara los .csv como `application/vnd.ms-excel`, que pide
            # firma OLE2 y no la tiene. Antes de rechazar un archivo legítimo,
            # miramos si en realidad es texto.
            extension_real = os.path.splitext(filename or "")[1].lower()
            if extension_real in (".csv", ".txt") and _parece_texto(data):
                mime = "text/csv" if extension_real == ".csv" else "text/plain"
                extension = extension_real
            else:
                return None, "El archivo no parece un documento válido o está dañado."
        elif mime in _DOCUMENTOS_DE_TEXTO and not _parece_texto(data):
            return None, "El archivo no parece un documento de texto válido."

    if len(data) > LIMITES[categoria]:
        return None, texto_excede(categoria)

    if categoria == IMAGEN:
        # Rechazo explícito de la bomba de descompresión ANTES de decodificar
        # (auditoría de seguridad #1). Tiene que ir aquí, no en `comprimir`:
        # `comprimir` se traga cualquier error y devuelve None, con lo que se
        # guardaría el original —la bomba— en vez de rechazarlo. Se lee solo el
        # header, así que esto no dispara la descompresión.
        if imagenes.excede_resolucion(data):
            return None, (
                "La imagen tiene una resolución demasiado alta. "
                "Envíala más pequeña (máximo 50 megapíxeles)."
            )
        # Mismo camino rápido que la subida de fotos de mascotas: una pasada a
        # calidad fija. Si no gana nada, `comprimir` devuelve None y se guarda
        # el original.
        comprimida = imagenes.comprimir(data)
        if comprimida is not None:
            logger.info(
                "adjuntos: imagen comprimida %d -> %d bytes", len(data), len(comprimida)
            )
            data, mime, extension = comprimida, "image/jpeg", ".jpg"

    if categoria == VIDEO and convertir_video and mime not in VIDEO_ACEPTADO_POR_WHATSAPP:
        # Hoy esto es siempre `video/quicktime`: el .mov del iPhone o del Mac.
        convertido = transcodificar_a_mp4(data)
        if convertido is None:
            return None, (
                "No pudimos convertir ese video a un formato que WhatsApp acepte. "
                "Si es muy largo o viene de un iPhone en «Alta eficiencia», "
                "expórtalo como MP4 y vuelve a intentarlo."
            )
        data, mime, extension = convertido, "video/mp4", ".mp4"
        if len(data) > LIMITES[VIDEO]:
            # Convertir puede agrandar: un .mov de 11 MB copiado a MP4 pesa casi
            # lo mismo, y ahí el tope se pasa por poco. Se avisa con el número
            # real en vez de dejar que lo rechace WhatsApp.
            return None, (
                "El video pesa demasiado incluso convertido: el máximo es "
                f"{LIMITES[VIDEO] // (1024 * 1024)} MB."
            )

    if categoria == AUDIO and mime not in AUDIO_ACEPTADO_POR_WHATSAPP:
        # Hoy esto es siempre `audio/webm`: lo que graba el navegador.
        convertido = transcodificar_a_ogg(data)
        if convertido is None:
            return None, (
                "No pudimos convertir el audio a un formato que WhatsApp acepte. "
                "Envíalo en MP3 u OGG."
            )
        data, mime, extension = convertido, "audio/ogg", ".ogg"
        if len(data) > LIMITES[AUDIO]:
            return None, (
                "El audio pesa demasiado incluso convertido: el máximo es "
                f"{LIMITES[AUDIO] // (1024 * 1024)} MB."
            )

    return Preparado(data=data, content_type=mime, categoria=categoria,
                     extension=extension), ""


def limpiar_caption(caption: Optional[str], categoria: str) -> str:
    """Pie del archivo, recortado. Vacío para el audio: WhatsApp no lo muestra
    en una nota de voz, así que prometerlo sería mentira."""
    if categoria not in CATEGORIAS_CON_CAPTION:
        return ""
    return (caption or "").strip()[:MAX_CAPTION]


# ---------------------------------------------------------------------------
# Guardar y servir
# ---------------------------------------------------------------------------

def guardar(
    team_id: int, preparado: Preparado, filename: Optional[str] = None
) -> Adjunto:
    """Sube el archivo y devuelve por dónde lo va a descargar el proveedor.

    El `team_id` va en la ruta a propósito: es el aislamiento entre tenants del
    storage, y lo que hace que servir un adjunto sea una verificación de ruta y
    no una consulta.

    La carpeta es el uuid (lo impredecible) y el archivo conserva un nombre
    legible: quien recibe un documento por WhatsApp ve el último tramo de la
    URL, y ahí tiene que decir "Itinerario-Covenas.pdf".
    """
    carpeta = uuid.uuid4().hex
    nombre = nombre_visible(filename, preparado.categoria, preparado.extension)
    key = key_de(team_id, carpeta, nombre)
    _put_object(key, preparado.data, preparado.content_type)
    logger.info(
        "adjuntos: guardado team=%s tipo=%s bytes=%s",
        team_id, preparado.categoria, len(preparado.data),
    )
    return Adjunto(
        key=key,
        nombre=nombre,
        url=url_publica(team_id, carpeta, nombre),
        content_type=preparado.content_type,
        categoria=preparado.categoria,
        bytes_size=len(preparado.data),
    )


def guardar_entrante(
    team_id: int, data: bytes, content_type: str, filename: Optional[str] = None
) -> Optional[Adjunto]:
    """Guarda un archivo que **mandó el cliente**, para que el asesor lo vea.

    Pasa por la misma validación que lo que sale (`preparar`): lista blanca,
    firma real y tope de tamaño. Que el archivo venga del proveedor no lo hace
    confiable — lo subió un desconocido desde su celular, y termina servido por
    un endpoint público nuestro.

    Devuelve `None` si no se pudo: el webhook sigue igual y el mensaje se queda
    con su marcador. Perder una foto es feo; perder el turno del bot, peor.

    El video se guarda **sin convertir** (`convertir_video=False`): esto corre
    dentro del webhook y ffmpeg no cabe en ese presupuesto de tiempo. Ver
    `preparar`.
    """
    preparado, problema = preparar(
        data, content_type, filename, convertir_video=False
    )
    if preparado is None:
        logger.info("adjuntos: entrante descartado (%s)", problema)
        return None
    try:
        return guardar(team_id, preparado, filename)
    except Exception:
        logger.exception("adjuntos: no se pudo guardar un entrante team=%s", team_id)
        return None


def leer(team_id: int, carpeta: str, nombre: str) -> Optional[Tuple[bytes, str]]:
    """Bytes + content-type de un adjunto. `None` si no existe o si la ruta no
    tiene la forma exacta que emitimos.

    Esta validación es la que sostiene todo el endpoint público: sin ella, un
    `nombre` con `../` saldría de la carpeta del team y leería cualquier objeto
    del bucket.
    """
    try:
        team = int(team_id)
    except (TypeError, ValueError):
        return None
    if (
        team <= 0
        or not CARPETA_RE.match(carpeta or "")
        or not NOMBRE_RE.match(nombre or "")
    ):
        # Sin la ruta pedida en el log: es entrada de un desconocido (regla #1).
        logger.warning("adjuntos: pedido con ruta inválida team=%s", team_id)
        return None

    data = _get_object(key_de(team, carpeta, nombre))
    if data is None:
        return None
    extension = os.path.splitext(nombre)[1].lower()
    return data, EXTENSIONES.get(extension, "application/octet-stream")
