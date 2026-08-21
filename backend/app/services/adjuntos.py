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
  2. **El tipo se decide por la firma del archivo, no por el nombre ni por el
     `Content-Type`** que declara el navegador. Para imágenes y PDF la firma es
     obligatoria: si no coincide, no se guarda.
"""
from __future__ import annotations

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
LIMITES: Dict[str, int] = {
    IMAGEN: 5 * 1024 * 1024,
    AUDIO: 16 * 1024 * 1024,
    VIDEO: 16 * 1024 * 1024,
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

PREFIJO = "adjuntos"
RUTA_PUBLICA = "/mensajes/adjunto"

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

    return boto3.client("s3", region_name=os.getenv("AWS_REGION", "sa-east-1"))


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
# Qué es de verdad este archivo
# ---------------------------------------------------------------------------

# Sentinela para los contenedores ISO-BMFF (`ftyp`): la firma no distingue un
# mp4 de solo audio de uno con video, así que ahí sí manda lo que declaró el
# navegador.
_FTYP = "ftyp"


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
        return _FTYP
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
# Validación
# ---------------------------------------------------------------------------

_NOMBRES_CATEGORIA = {
    IMAGEN: "imágenes",
    AUDIO: "audios",
    VIDEO: "videos",
    DOCUMENTO: "documentos",
}

_TEXTO_NO_PERMITIDO = (
    "Ese tipo de archivo no se puede enviar por WhatsApp. Puedes mandar "
    "imágenes (JPG, PNG, WEBP), audio (MP3, OGG, M4A), video MP4 o documentos "
    "(PDF, Word, Excel, PowerPoint, TXT o CSV)."
)


def preparar(
    data: bytes, content_type: Optional[str] = None, filename: Optional[str] = None
) -> Tuple[Optional[Preparado], str]:
    """Valida el archivo y lo deja listo para guardar.

    Devuelve `(preparado, problema)`. `problema` es un texto **para el asesor**:
    dice qué pasó y qué hacer, sin filtrar nada del servidor.
    """
    if not data:
        return None, "El archivo llegó vacío."

    declarado = _normalizar_mime(content_type)
    mime, firma = _tipo_real(data, declarado, filename)
    if mime not in TIPOS_PERMITIDOS:
        return None, _TEXTO_NO_PERMITIDO

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

    limite = LIMITES[categoria]
    if len(data) > limite:
        return None, (
            f"El archivo pesa demasiado: el máximo para "
            f"{_NOMBRES_CATEGORIA[categoria]} es {limite // (1024 * 1024)} MB."
        )

    if categoria == IMAGEN:
        # Mismo camino rápido que la subida de fotos de mascotas: una pasada a
        # calidad fija. Si no gana nada, `comprimir` devuelve None y se guarda
        # el original.
        comprimida = imagenes.comprimir(data)
        if comprimida is not None:
            logger.info(
                "adjuntos: imagen comprimida %d -> %d bytes", len(data), len(comprimida)
            )
            data, mime, extension = comprimida, "image/jpeg", ".jpg"

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
