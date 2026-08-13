"""Importa los reportes de mascotasporcolombia.com a nuestra tabla `mascotas`.

"Mascotas por Colombia" es una plataforma solidaria con el mismo propósito que
la nuestra: reunir a las mascotas perdidas con sus familias tras el terremoto.
Traer sus reportes a nuestra base le sirve al bot para ofrecer coincidencias que
nosotros no tenemos y **mandar a la persona a la ficha original**, donde está el
contacto de quien reportó. No competimos con ellos: los amplificamos.

Qué hace
--------
1. Lee `https://www.mascotasporcolombia.com/sitemap.xml` y se queda con las
   fichas: `/mascotas/<slug>` (mascotas PERDIDAS) y `/found-pets/<slug>`
   (mascotas ENCONTRADAS).
2. Descarta por `<lastmod>` todo lo anterior a `MPC_DESDE` sin bajar la página
   (una ficha se actualiza siempre después de publicarse, así que `lastmod`
   nunca es anterior a la fecha de publicación: filtrar por ahí es seguro).
3. Baja cada ficha y saca los datos del payload de React que Next.js embebe en
   el HTML (`self.__next_f.push([1,"…"])`), donde viaja el objeto `initialData`
   con el registro completo tal cual lo tiene la plataforma de origen.
4. Confirma la fecha con `created_at` de ese objeto (la fecha real de
   publicación, más fiable que `lastmod`) y mapea a nuestro esquema.
5. Separa en varios registros las fichas que reportan un grupo (ver abajo).
6. Da de alta con `svc.crear_reporte()` o actualiza lo que ya existe,
   deduplicando por (`source`, `origen_id`).

Decisiones que conviene conocer antes de tocar este script
----------------------------------------------------------
* **El tipo lo manda la ruta**: `/mascotas/` = perdidas, `/found-pets/` =
  encontradas. El payload también trae un `kind`; se usa solo para chequear y
  avisar por log si algún día difieren. `/…/departamento/<x>` son índices, no
  fichas, y quedan fuera.
* **No importamos el teléfono.** La ficha de origen lo publica, pero el contacto
  de esas familias no es nuestro para redistribuirlo: `contacto_telefono` queda
  NULL y quien reconozca a la mascota se va a `origen_url` (`crear_reporte` ya
  acepta reportes sin teléfono cuando traen origen).
* **No importamos las fotos.** `mascota_fotos.storage_key` es una clave de
  NUESTRO storage (S3 o disco) que el backend lee y sirve por
  `GET /mascotas/foto/...`; meter ahí una URL remota rompería ese contrato
  (imágenes rotas en el panel y en el bot, borrados fallidos). Guardamos la URL
  de la primera foto dentro de `notas` y listo. Si algún día queremos
  mostrarlas, lo limpio es una columna `foto_url_externa` en `mascotas` (o un
  `remote_url` opcional en `mascota_fotos`), no forzar `storage_key`.
* **Una ficha puede traer varias mascotas** (un grupo encontrado junto). Se
  crea un registro por animal cuando el texto dice cuántos son ("dos perros",
  "3 cachorros"), con `origen_id` sufijado (`…#1`, `…#2`), la misma foto y una
  nota que aclara que venían juntos. Si el texto está en plural pero no dice
  cuántos ("Perritos encontrados…"), queda **un solo** registro con una nota
  para revisar a mano: un registro correcto vale más que tres inventados.
* **`origen_id` lleva la sección**: `mascotas/<slug>` o `found-pets/<slug>`. El
  slug solo NO sirve como clave: hoy mismo hay 23 slugs (`perro-cali-5`, …) que
  existen en las dos secciones y se pisarían entre ellos.
* **Idempotente**: re-correrlo actualiza los campos que cambiaron en el origen y
  no duplica. Un reporte que el equipo puso en `cerrado` no se revive.
* **Educado con el sitio**: lee y respeta `robots.txt` en cada corrida (si no se
  puede leer, no se importa nada), se identifica con un User-Agent propio, baja
  una página a la vez y espera ~1s entre requests. Nunca en paralelo.

Uso local:
    docker compose -p wati cp backend/scripts/import_mascotasporcolombia.py \
        backend:/app/scripts/
    docker compose -p wati exec -T backend python \
        scripts/import_mascotasporcolombia.py --dry-run
    docker compose -p wati exec -T backend python \
        scripts/import_mascotasporcolombia.py

En RDS (misma imagen del backend, red de la VPC):
    aws ecs run-task --region sa-east-1 \
      --cluster multiagente-cluster \
      --task-definition multiagente-backend \
      --launch-type FARGATE \
      --network-configuration 'awsvpcConfiguration={subnets=[subnet-07829afbd13c5bb8f,subnet-00f56d6ce74d72a2e],securityGroups=[sg-0499ec72831ef7da9],assignPublicIp=ENABLED}' \
      --overrides '{"containerOverrides":[{"name":"backend","command":["python","scripts/import_mascotasporcolombia.py"]}]}'

ENV / flags:
    MPC_DESDE     (--desde)    solo fichas publicadas desde esta fecha  [2026-08-10]
    MPC_DRY_RUN=1 (--dry-run)  muestra el mapeo sin escribir en la BD
    MPC_LIMITE    (--limite)   procesa como máximo N fichas (pruebas)
    MPC_PAUSA     (--pausa)    segundos entre requests                  [1.0]
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.robotparser import RobotFileParser

import requests

from .. import models
from ..database import SessionLocal
from . import mascotas as svc

logger = logging.getLogger(__name__)

BASE = "https://www.mascotasporcolombia.com"
SITEMAP = f"{BASE}/sitemap.xml"
ROBOTS = f"{BASE}/robots.txt"
SOURCE = "mascotasporcolombia"

# Nos identificamos con un UA propio y un link de contacto: si les molestamos,
# que sepan a quién bloquear sin tener que bloquear a medio internet.
USER_AGENT = "GlomaMascotasBot/1.0 (+https://mascotasperdidascolombia.com)"
TIMEOUT = 25
INTENTOS = 3          # 1 intento + 2 reintentos suaves
ESPERA_REINTENTO = 4  # segundos, fijo: no vale la pena un backoff sofisticado

DESDE_DEFAULT = "2026-08-10"
PAUSA_DEFAULT = 1.0

# Cada sección del sitio es uno de nuestros dos tipos de reporte.
SECCIONES = {
    "mascotas": models.MASCOTA_TIPO_PERDIDA,
    "found-pets": models.MASCOTA_TIPO_ENCONTRADA,
}
# Rutas de esas secciones que NO son fichas de mascota.
SLUGS_NO_FICHA = {"reportar", "registrar", "departamento", "buscar"}

# El origen guarda el tamaño sin tilde; lo dejamos como lo escribe la gente aquí
# (el scoring compara sin tildes, así que esto es solo cosmética del panel).
TAMANOS = {"pequeno": "pequeño", "mediano": "mediano", "grande": "grande"}

# Estados del origen que significan "ya no está buscando/disponible".
ESTADOS_RESUELTOS = {"resuelta", "resuelto", "reunida", "reunido", "entregada", "entregado"}

# Nombres de contacto que no identifican a nadie: no vale la pena guardarlos.
# Se comparan ya normalizados (sin tildes ni puntuación) con `svc.normalizar`.
NOMBRES_VACIOS = {"desconocido", "desconocida", "anonimo", "n a", "na", "sin nombre"}

# --- Fichas con varias mascotas -------------------------------------------
# Hay fichas que reportan un grupo encontrado junto ("dos perros", "3 cachorros")
# en una sola publicación. Cada animal tiene que ser un registro nuestro o el
# cruce perdida↔encontrada nunca los va a encontrar por separado.
NUMEROS = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6,
}
MAX_MASCOTAS_POR_FICHA = 6   # más que esto es una jauría o un error de lectura
_RAIZ_ANIMAL = r"(?:perr|perrit|cachorr|gat|gatit|gatic|michi|mascot|animal|canin|felin)"
_RE_CONTEO = re.compile(
    rf"\b({'|'.join(sorted(NUMEROS, key=len, reverse=True))})\s+{_RAIZ_ANIMAL}\w*"
)
_RE_PLURAL = re.compile(
    r"\b(?:perros|perritos|perritas|perras|cachorros|cachorras|gatos|gatitos|"
    r"gaticos|gatas|michis|mascotas|animales|caninos|felinos)\b"
)
# Vocabulario mínimo para repartir colores cuando la ficha los distingue
# ("uno negro y otro café"). Si no cuadra el número de colores con el de
# animales, no se inventa nada: todos quedan con el color de la ficha.
COLORES = (
    "negro", "negra", "blanco", "blanca", "cafe", "marron", "gris", "dorado",
    "dorada", "amarillo", "canela", "naranja", "atigrado", "tricolor", "crema",
    "beige", "chocolate", "carey", "mostaza", "plateado",
)
_RE_COLOR_INDIVIDUAL = re.compile(
    rf"\b(?:uno|una|otro|otra)\s+(?:es\s+)?(?:de\s+)?(?:color\s+)?({'|'.join(COLORES)})\b"
)


# ---------------------------------------------------------------------------
# HTTP: despacio y sin disfraz
# ---------------------------------------------------------------------------

def _sesion() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-CO,es;q=0.9",
    })
    return s


def _bajar(sesion: requests.Session, url: str, pausa: float) -> str:
    """GET secuencial con reintento suave. Siempre pausa antes de pedir."""
    ultimo: Optional[Exception] = None
    for intento in range(1, INTENTOS + 1):
        time.sleep(pausa if intento == 1 else ESPERA_REINTENTO)
        try:
            resp = sesion.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:      # noqa: BLE001 — cualquier fallo se reintenta
            ultimo = exc
            logger.warning("intento %s/%s falló para %s (%s)",
                           intento, INTENTOS, url, type(exc).__name__)
    raise RuntimeError(f"no se pudo bajar {url}") from ultimo


def _robots(sesion: requests.Session) -> RobotFileParser:
    """robots.txt del sitio. Si no se puede leer, abortamos: pedir permiso y no
    esperar la respuesta no es pedir permiso."""
    parser = RobotFileParser()
    resp = None
    for intento in range(1, INTENTOS + 1):
        try:
            resp = sesion.get(ROBOTS, timeout=TIMEOUT)
            break
        except Exception:             # noqa: BLE001 — un hipo de red no aborta la corrida
            logger.warning("intento %s/%s falló al leer robots.txt", intento, INTENTOS)
            time.sleep(ESPERA_REINTENTO)
    if resp is None:
        raise RuntimeError("no se pudo leer robots.txt")
    if resp.status_code == 404:
        parser.parse([])              # sin robots.txt, todo permitido
        return parser
    resp.raise_for_status()
    parser.parse(resp.text.splitlines())
    return parser


# ---------------------------------------------------------------------------
# Sitemap
# ---------------------------------------------------------------------------

def _fichas_del_sitemap(xml: str) -> List[Dict[str, Any]]:
    """(url, sección, slug, lastmod) de cada ficha de mascota del sitemap."""
    fichas = []
    for bloque in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", bloque, re.S)
        if not loc:
            continue
        ruta = re.match(rf"{re.escape(BASE)}/([^/]+)/([^/?#]+)/?$", loc.group(1))
        if not ruta:
            continue
        seccion, slug = ruta.group(1), ruta.group(2)
        if seccion not in SECCIONES or slug in SLUGS_NO_FICHA:
            continue
        lastmod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", bloque, re.S)
        fichas.append({
            "url": loc.group(1),
            "seccion": seccion,
            "slug": slug,
            "lastmod": lastmod.group(1) if lastmod else None,
        })
    return fichas


# ---------------------------------------------------------------------------
# Ficha: sacar el registro del payload de Next.js
# ---------------------------------------------------------------------------

_RE_FLIGHT = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', re.S)
_RE_KIND = re.compile(r'"kind":"(perdida|encontrada)"')
_RE_FOTOS = re.compile(r'"photos":(\[[^\]]*\])')
_RE_OG_IMAGE = re.compile(r'<meta property="og:image" content="([^"]+)"')


def _payload_flight(html: str) -> str:
    """Concatena los trozos del payload RSC que Next.js deja en el HTML.

    Los datos de la ficha no están en el DOM servido (el detalle se hidrata en
    el cliente) ni en el JSON-LD (que solo trae Organization/WebSite): están en
    estos `push`, ya en JSON.
    """
    partes = []
    for trozo in _RE_FLIGHT.findall(html):
        try:
            partes.append(json.loads(trozo))
        except ValueError:
            continue
    return "".join(partes)


def _objeto_json(texto: str, desde: int) -> Optional[str]:
    """Recorta el objeto JSON que empieza en `desde` contando llaves."""
    profundidad = 0
    en_cadena = False
    escape = False
    for i in range(desde, len(texto)):
        c = texto[i]
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[desde:i + 1]
    return None


def _extraer_ficha(html: str) -> Optional[Dict[str, Any]]:
    """Registro del origen + tipo + fotos, o None si la página no es una ficha."""
    payload = _payload_flight(html)
    marca = payload.find('"initialData":')
    if marca < 0:
        return None
    inicio = payload.find("{", marca)
    crudo = _objeto_json(payload, inicio) if inicio > 0 else None
    if not crudo:
        return None
    try:
        datos = json.loads(crudo)
    except ValueError:
        return None

    kind = _RE_KIND.search(payload)
    fotos = _RE_FOTOS.search(payload)
    try:
        rutas = json.loads(fotos.group(1)) if fotos else []
    except ValueError:
        rutas = []
    return {
        "datos": datos,
        "kind": kind.group(1) if kind else None,
        "fotos": _urls_de_fotos(rutas, html),
    }


def _urls_de_fotos(rutas: List[Any], html: str) -> List[str]:
    """URLs absolutas de las fotos (solo para el log: no las importamos).

    Las rutas vienen relativas al bucket del origen (`lost/xxx.webp`) salvo en
    los reportes que ellos mismos importaron, que ya traen la URL completa. El
    prefijo del bucket se deduce de `og:image`, que es la primera foto.
    """
    rutas = [r for r in rutas if isinstance(r, str) and r]
    if not rutas:
        return []
    og = _RE_OG_IMAGE.search(html)
    prefijo = ""
    if og and not rutas[0].startswith("http") and og.group(1).endswith(rutas[0]):
        prefijo = og.group(1)[:-len(rutas[0])]
    return [r if r.startswith("http") else f"{prefijo}{r}" for r in rutas if prefijo or r.startswith("http")]


# ---------------------------------------------------------------------------
# Mapeo al esquema nuestro
# ---------------------------------------------------------------------------

def _fecha_iso(valor: Any) -> Optional[date]:
    """'2026-08-11T00:00:00+00:00' → date(2026, 8, 11)."""
    if not isinstance(valor, str):
        return None
    return svc._parse_fecha(valor[:10])


def _texto(valor: Any, limite: int) -> Optional[str]:
    if valor is None or isinstance(valor, (dict, list, bool)):
        return None
    return svc._limpiar(valor, limite)


def _ubicacion(d: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(ubicacion, barrio) a partir de sector / ciudad / departamento.

    `sector` es texto libre: a veces es el barrio ("Robledo Miramar") y a veces
    una frase entera ("Se perdió en el barrio Cuarto de Legua, y dicen haberla
    visto por siloé"). Se concatena igual porque el scoring de zona compara por
    tokens, no por igualdad.
    """
    partes: List[str] = []
    vistos = set()
    for clave in ("sector", "city", "state"):
        texto = _texto(d.get(clave), 255)
        if not texto or svc.normalizar(texto) in vistos:
            continue
        vistos.add(svc.normalizar(texto))
        partes.append(texto)
    ubicacion = svc._limpiar(", ".join(partes), 255) if partes else None
    barrio = _texto(d.get("sector") or d.get("city"), 120)
    return ubicacion, barrio


def _estado_origen(d: Dict[str, Any]) -> str:
    """`status` tal cual lo escribe el origen ('en_la_calle', 'reunida'…).

    Ojo: aquí NO sirve `svc.normalizar()`, que convierte los guiones bajos en
    espacios y haría que ningún estado del origen coincida.
    """
    valor = d.get("status")
    return valor.strip().lower() if isinstance(valor, str) else ""


def _notas(d: Dict[str, Any], fotos: List[str]) -> Optional[str]:
    """Descripción del origen + el contexto que solo traen las 'encontradas'.

    Incluye el link de la primera foto: no bajamos la imagen a nuestro storage
    (ver el docstring del módulo), pero tener la URL a mano le sirve al equipo
    para comparar sin salir del panel.
    """
    lineas = [_texto(d.get("description"), 1500)]
    estado_origen = _estado_origen(d)
    if estado_origen == "en_resguardo":
        lineas.append("Quien la encontró la tiene resguardada.")
    elif estado_origen == "en_la_calle":
        lineas.append("Sigue en la calle, no está resguardada.")
    salud = _texto(d.get("health_status"), 200)
    if salud:
        lineas.append(f"Estado de salud reportado: {salud}.")
    if d.get("has_reward"):
        lineas.append("La familia ofrece recompensa.")
    if d.get("is_imported"):
        lineas.append("La plataforma de origen lo tomó a su vez de otro sitio.")
    if fotos:
        lineas.append(f"Foto en la ficha original: {fotos[0]}")
    # `_limpiar` deja todo en un párrafo (colapsa los saltos de línea): son
    # frases cortas y en el panel se leen igual de bien.
    return svc._limpiar("\n".join([l for l in lineas if l]), 2000)


def _cuantas_mascotas(descripcion: Optional[str]) -> Tuple[int, bool]:
    """(cuántos animales describe la ficha, si el plural quedó sin contar).

    Solo separa cuando el texto dice el número ("dos perros", "3 cachorros").
    Si habla en plural pero no dice cuántos ("Perritos encontrados…"), devuelve
    1 y avisa: preferimos un registro correcto a tres inventados.
    """
    texto = svc.normalizar(descripcion)
    if not texto:
        return 1, False
    cantidades = [NUMEROS[m] for m in _RE_CONTEO.findall(texto)]
    cantidades = [n for n in cantidades if 2 <= n <= MAX_MASCOTAS_POR_FICHA]
    if cantidades:
        return max(cantidades), False
    return 1, bool(_RE_PLURAL.search(texto))


def _colores_individuales(descripcion: Optional[str], cuantos: int) -> List[Optional[str]]:
    """Un color por animal si la ficha los distingue; si no, todos sin color."""
    encontrados = _RE_COLOR_INDIVIDUAL.findall(svc.normalizar(descripcion))
    if len(encontrados) != cuantos:
        return [None] * cuantos
    return encontrados


def _separar(campos: Dict[str, Any], descripcion: Optional[str], origen_id: str) -> List[Dict[str, Any]]:
    """Una ficha → uno o varios registros (uno por mascota reportada).

    Los hermanos comparten ficha, foto y ubicación; se diferencian por el
    sufijo de `origen_id` (`…#1`, `…#2`), que es lo que mantiene la
    idempotencia contra el índice único (`source`, `origen_id`).
    """
    cuantos, plural_sin_contar = _cuantas_mascotas(descripcion)

    if cuantos == 1:
        campos["origen_id"] = origen_id
        if plural_sin_contar:
            campos["notas"] = _sumar_nota(campos["notas"], (
                "La ficha original habla de varias mascotas pero no dice "
                "cuántas: quedó en un solo registro, revisar a mano."
            ))
        return [campos]

    colores = _colores_individuales(descripcion, cuantos)
    registros = []
    for i in range(cuantos):
        hermano = dict(campos)
        hermano["origen_id"] = f"{origen_id}#{i + 1}"
        if colores[i]:
            hermano["color"] = colores[i]
        if i > 0:
            # Un nombre no puede ser de varios animales: se queda con el primero.
            hermano["nombre"] = None
        hermano["notas"] = _sumar_nota(campos["notas"], (
            f"Reportados juntos en la misma ficha ({cuantos} animales); "
            f"este es el {i + 1} de {cuantos} y comparten la misma foto."
        ))
        registros.append(hermano)
    return registros


def _sumar_nota(notas: Optional[str], linea: str) -> Optional[str]:
    return svc._limpiar(" ".join(filter(None, [notas, linea])), 2000)


def _contacto_nombre(d: Dict[str, Any]) -> Optional[str]:
    nombre = _texto(d.get("reporter_name") or d.get("finder_name"), 120)
    if not nombre:
        return None
    normalizado = svc.normalizar(nombre)
    # "Contacto en Encuentra tu Peludo" y similares no son personas.
    if normalizado in NOMBRES_VACIOS or normalizado.startswith("contacto en"):
        return None
    return nombre


def _estado(d: Dict[str, Any]) -> str:
    """El origen manda: una mascota que allá ya apareció no debe ofrecerse acá."""
    if d.get("resolved_at") or _estado_origen(d) in ESTADOS_RESUELTOS:
        return models.MASCOTA_ESTADO_REUNIDA
    return models.MASCOTA_ESTADO_ACTIVO


def _mapear(
    ficha: Dict[str, Any], extraido: Dict[str, Any], origen_id: str
) -> Tuple[List[Dict[str, Any]], str]:
    """Ficha del origen → uno o varios registros nuestros.

    Devuelve (registros, motivo_descarte). Son varios cuando la ficha reporta
    un grupo encontrado junto y dice cuántos animales son.
    """
    d = extraido["datos"]

    if d.get("deleted_at"):
        return [], "borrada en el origen"
    if d.get("is_approved") is False:
        return [], "sin aprobar en el origen"

    # La sección del sitio manda (es estructural: /mascotas = perdidas,
    # /found-pets = encontradas). El `kind` del payload es el cinturón: si
    # alguna vez difieren, quiero enterarme por el log, no por un cruce mal hecho.
    tipo = SECCIONES[ficha["seccion"]]
    if extraido["kind"] and extraido["kind"] != tipo:
        logger.warning("%s: la sección dice %s y el registro dice %s",
                       ficha["url"], tipo, extraido["kind"])

    ubicacion, barrio = _ubicacion(d)
    if not ubicacion:
        # `ubicacion` es NOT NULL y sin zona el reporte no sirve para cruzar.
        return [], "sin ubicación"

    # `especie` es NOT NULL: sin dato, 'otra' (el bot igual filtra por especie
    # y 'otra' no descarta nada que no deba descartar).
    especie = svc.normalizar_especie(d.get("species")) or "otra"

    lat, lon = d.get("latitude"), d.get("longitude")
    maps_url = f"https://www.google.com/maps?q={lat},{lon}" if lat and lon else None

    tamano = _texto(d.get("size"), 24)
    campos = {
        "tipo_registro": tipo,
        "especie": especie,
        "especie_otra": _texto(d.get("species"), 60) if especie == "otra" else None,
        "raza": _texto(d.get("breed"), 80),
        "color": _texto(d.get("color"), 80),
        "nombre": _texto(d.get("name"), 80),
        "sexo": svc.normalizar_sexo(d.get("sex")),
        "edad": _texto(d.get("age_group"), 40),
        "tamano": TAMANOS.get(svc.normalizar(tamano), tamano),
        "senas": _texto(d.get("distinctive_marks"), 2000),
        "ubicacion": ubicacion,
        "maps_url": maps_url,
        "barrio": barrio,
        "contacto_nombre": _contacto_nombre(d),
        # `contacto_telefono` queda NULL a propósito: ver el docstring.
        "fecha_evento": _fecha_iso(d.get("last_seen_at") or d.get("found_at")),
        "notas": _notas(d, extraido["fotos"]),
        "estado": _estado(d),
        "origen_url": ficha["url"],
    }
    return _separar(campos, d.get("description"), origen_id), ""


# ---------------------------------------------------------------------------
# Escritura
# ---------------------------------------------------------------------------

def _existente(db, origen_id: str) -> Optional[models.Mascota]:
    if db is None:
        return None
    return (
        db.query(models.Mascota)
        .filter(models.Mascota.source == SOURCE, models.Mascota.origen_id == origen_id)
        .first()
    )


def _guardar(db, campos: Dict[str, Any], dry_run: bool) -> Tuple[str, str]:
    """Crea o actualiza el reporte.

    Devuelve (resultado, problema) con resultado en 'creada' | 'actualizada' |
    'igual' | 'rechazada'. El alta pasa por `svc.crear_reporte()` para que los
    importados atraviesen exactamente las mismas validaciones que los del bot.
    En `dry_run` calcula lo mismo sin escribir.
    """
    origen_id = campos["origen_id"]
    existente = _existente(db, origen_id)

    if existente is None:
        if dry_run:
            return "creada", ""
        mascota, problema = svc.crear_reporte(db, campos, source=SOURCE)
        if mascota is None:
            return "rechazada", problema
        # `crear_reporte` siempre nace 'activo' (es lo correcto para el bot);
        # si en el origen ya apareció, lo corregimos acá.
        if campos["estado"] != mascota.estado:
            mascota.estado = campos["estado"]
            db.commit()
        return "creada", ""

    cambios = []
    for campo, valor in campos.items():
        if campo == "origen_id":
            continue                    # es la clave, no un dato que cambie
        # Un reporte que el equipo cerró a mano (duplicado de uno nuestro, por
        # ejemplo) no se revive aunque el origen lo siga mostrando activo.
        if campo == "estado" and existente.estado == models.MASCOTA_ESTADO_CERRADO:
            continue
        if getattr(existente, campo) != valor:
            cambios.append((campo, valor))
    if not cambios:
        return "igual", ""
    if dry_run:
        logger.info("%s cambiaría: %s", origen_id, ",".join(c for c, _ in cambios))
        return "actualizada", ""
    for campo, valor in cambios:
        setattr(existente, campo, valor)
    existente.updated_at = datetime.utcnow()
    db.commit()
    logger.info("%s actualizada (%s): %s",
                existente.codigo, origen_id, ",".join(c for c, _ in cambios))
    return "actualizada", ""


# ---------------------------------------------------------------------------
# Corrida
# ---------------------------------------------------------------------------

def _resumen_ficha(campos: Dict[str, Any], fotos: int, estado: str) -> str:
    """Bloque por registro para el dry-run. Sin PII (regla de seguridad #1):
    del contacto solo se dice si venía o no."""
    return (
        f"[{estado.upper()}] {campos['origen_id']}\n"
        f"    tipo={campos['tipo_registro']} especie={campos['especie']}"
        f" raza={campos['raza']!r} color={campos['color']!r}"
        f" nombre={campos['nombre']!r} sexo={campos['sexo']} tamano={campos['tamano']!r}\n"
        f"    ubicacion={campos['ubicacion']!r} barrio={campos['barrio']!r}\n"
        f"    fecha_evento={campos['fecha_evento']} estado={campos['estado']}"
        f" contacto_nombre={'<presente>' if campos['contacto_nombre'] else '—'}"
        f" fotos_en_origen={fotos}\n"
        f"    origen_url={campos['origen_url']}"
    )


def importar(
    desde: date,
    dry_run: bool,
    limite: Optional[int],
    pausa: float,
    progreso: Optional[Callable[[Dict[str, int]], None]] = None,
) -> Dict[str, int]:
    """Recorre el origen y da de alta/actualiza los reportes.

    `progreso` (opcional) recibe los contadores parciales cada pocas fichas:
    lo usa el botón del panel para mostrar avance en una corrida que dura
    minutos.
    """
    conteo = {
        "sitemap": 0, "viejas_por_lastmod": 0, "bajadas": 0,
        "viejas_por_publicacion": 0, "creadas": 0, "actualizadas": 0,
        "sin_cambios": 0, "omitidas": 0, "rechazadas": 0, "fallidas": 0,
        "fotos_en_origen": 0,
        # Por sección, contando FICHAS (no registros) que pasan el filtro.
        "perdidas": 0, "encontradas": 0,
        # Fichas que describían un grupo y se separaron en varios registros.
        "fichas_con_varias": 0, "registros_extra": 0,
    }

    sesion = _sesion()
    robots = _robots(sesion)
    if not robots.can_fetch(USER_AGENT, SITEMAP):
        raise RuntimeError("robots.txt no permite leer el sitemap: no se importa nada")

    fichas = _fichas_del_sitemap(_bajar(sesion, SITEMAP, pausa))
    conteo["sitemap"] = len(fichas)
    logger.info("sitemap: %s fichas de mascota", len(fichas))

    # Primero las más recientes: si hay `--limite`, que sirva para algo.
    fichas.sort(key=lambda f: f["lastmod"] or "", reverse=True)

    db = SessionLocal()
    if dry_run:
        # El ensayo tiene que poder correrse aunque la migración todavía no esté
        # aplicada: si la tabla no responde, seguimos sin saber qué ya existe.
        try:
            db.query(models.Mascota).limit(1).all()
        except Exception:
            logger.warning("dry-run sin base de datos: no se puede distinguir "
                           "lo nuevo de lo que ya está importado")
            db.close()
            db = None

    try:
        for ficha in fichas:
            if limite is not None and conteo["bajadas"] >= limite:
                break
            if ficha["lastmod"] and (svc._parse_fecha(ficha["lastmod"][:10]) or desde) < desde:
                conteo["viejas_por_lastmod"] += 1
                continue
            if not robots.can_fetch(USER_AGENT, ficha["url"]):
                logger.warning("robots.txt no permite %s", ficha["url"])
                conteo["omitidas"] += 1
                continue

            origen_id = f"{ficha['seccion']}/{ficha['slug']}"
            # Avance para el botón del panel: cada 5 fichas basta para que la
            # barra se mueva sin llenar el log ni castigar el lock.
            if progreso is not None and conteo["bajadas"] % 5 == 0:
                try:
                    progreso({
                        "vistas": conteo["bajadas"],
                        "creadas": conteo["creadas"],
                        "actualizadas": conteo["actualizadas"],
                        "fallidas": conteo["fallidas"] + conteo["rechazadas"],
                    })
                except Exception:   # el avance nunca puede tumbar la corrida
                    logger.debug("no se pudo reportar el avance", exc_info=True)

            try:
                html = _bajar(sesion, ficha["url"], pausa)
                conteo["bajadas"] += 1
                extraido = _extraer_ficha(html)
                if extraido is None:
                    logger.warning("%s: no se pudo leer el registro del HTML", origen_id)
                    conteo["fallidas"] += 1
                    continue

                publicada = _fecha_iso(extraido["datos"].get("created_at"))
                if publicada and publicada < desde:
                    conteo["viejas_por_publicacion"] += 1
                    continue

                registros, motivo = _mapear(ficha, extraido, origen_id)
                if not registros:
                    logger.info("%s omitida: %s", origen_id, motivo)
                    conteo["omitidas"] += 1
                    continue

                conteo["fotos_en_origen"] += len(extraido["fotos"])
                conteo["perdidas" if ficha["seccion"] == "mascotas" else "encontradas"] += 1
                if len(registros) > 1:
                    conteo["fichas_con_varias"] += 1
                    conteo["registros_extra"] += len(registros) - 1
                    logger.info("%s reporta %s mascotas juntas: se separan en "
                                "%s registros", origen_id, len(registros), len(registros))

                for campos in registros:
                    resultado, problema = _guardar(db, campos, dry_run)
                    if resultado == "rechazada":
                        logger.warning("%s rechazada: %s", campos["origen_id"], problema)
                        conteo["rechazadas"] += 1
                        continue
                    conteo[{
                        "creada": "creadas", "actualizada": "actualizadas",
                    }.get(resultado, "sin_cambios")] += 1
                    if dry_run:
                        print(_resumen_ficha(campos, len(extraido["fotos"]), resultado),
                              flush=True)   # para que se intercale con el log
                if dry_run and db is not None:
                    # El ensayo solo lee; sin esto la transacción quedaría
                    # abierta ("idle in transaction") toda la corrida.
                    db.rollback()
            except Exception:
                # Una ficha rota no puede tumbar la corrida. Detalle completo
                # solo en el log del servidor (regla de seguridad #6).
                logger.exception("%s falló", origen_id)
                conteo["fallidas"] += 1
                if db is not None:
                    db.rollback()
    finally:
        if db is not None:
            db.close()
    return conteo


# ---------------------------------------------------------------------------
# Punto de entrada del módulo
# ---------------------------------------------------------------------------

def sincronizar(
    db=None,
    desde: Optional[date] = None,
    dry_run: bool = False,
    progreso: Optional[Callable[[Dict[str, int]], None]] = None,
    limite: Optional[int] = None,
    pausa: float = PAUSA_DEFAULT,
) -> Dict[str, int]:
    """Importa los reportes nuevos del origen. Contadores normalizados.

    Es lo que llaman el botón "Sincronizar" del panel y el script de consola.
    `db` se acepta por compatibilidad con el contrato del router, pero la
    corrida abre su propia sesión por ficha (una importación larga no debe
    sostener abierta la sesión del request).

    Claves del resultado: vistas, filtradas, creadas, actualizadas, sin_cambios,
    fallidas, perdidas, encontradas.
    """
    if desde is None:
        desde = svc._parse_fecha(os.getenv("MPC_DESDE") or DESDE_DEFAULT) or date(2026, 8, 10)

    conteo = importar(desde, dry_run, limite, max(0.5, pausa), progreso=progreso)

    # Los contadores internos son más detallados que los que espera el panel;
    # se traducen aquí para no atar la UI a la mecánica del scraper.
    return {
        "vistas": conteo.get("sitemap", 0),
        "filtradas": conteo.get("viejas_por_lastmod", 0)
        + conteo.get("viejas_por_publicacion", 0),
        "creadas": conteo.get("creadas", 0),
        "actualizadas": conteo.get("actualizadas", 0),
        "sin_cambios": conteo.get("sin_cambios", 0),
        "fallidas": conteo.get("fallidas", 0) + conteo.get("rechazadas", 0),
        "perdidas": conteo.get("perdidas", 0),
        "encontradas": conteo.get("encontradas", 0),
    }
