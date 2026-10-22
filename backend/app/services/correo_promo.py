"""Correo automático de la promoción de la demo (#644, endurecido en #647).

Cuando un prospecto inicia la demo en `glomacx.com/demo` (lead y demo ya
creados, nunca en el 202 falso del honeypot ni cuando un tope rechaza), el
backend le manda por SES el correo de la promoción que ve en la pantalla de
premio. Corre como tarea de fondo con su propia sesión: no bloquea ni cambia la
respuesta de `/demo/iniciar`, y nunca levanta.

Versión: CO si el teléfono del lead es `+57`, si no INTL (igual que la
pantalla de premio). Plantillas en `app/templates/correo_promo_demo/`
(copiadas de `ventas/correo_promo_demo/`, que es donde se editan y se
regeneran con `build_correo.py`; sin Google Fonts).

Contenido (#647 A1): lo que escribe el visitante solo entra al correo si pasa
una lista blanca. El nombre, si es una sola palabra de letras (≤ 30); si no,
el correo sale sin nombre («Tu promoción de Gloma: …», «Hola, ganaste…»). La
empresa, si no trae `. / : @ \\ { }` ni un número de 5+ dígitos; si no, «tu
empresa». Así nadie usa la demo para mandarle a un tercero, desde nuestro
dominio, un correo con un link o un dominio suyo.

Consentimiento (#647 M3): solo sale a demos aceptadas con una versión del
texto legal que avisa el envío (`VERSIONES_CON_CORREO`); comparación explícita
contra ese conjunto, no por orden de las cadenas.

Anti-abuso (los topes por correo de la demo están altos por decisión del CEO):
- `DEMO_CORREO_PROMO_SOLO_A`: si está definida, solo esas direcciones (pruebas);
- dominios desechables conocidos → omitido (`desechable`);
- el dominio tiene que tener MX (timeout 2 s). Sin MX → `sin_mx`; si el DNS
  falla o no responde → `dns` (no se envía a ciegas);
- a lo sumo 1 correo por dirección cada `DEMO_CORREO_PROMO_DIAS` (30);
- techos globales `DEMO_CORREO_PROMO_MAX_HORA` (200) y
  `DEMO_CORREO_PROMO_MAX_DIA` (2000);
- cortacircuitos: si hubo ≥ `DEMO_CORREO_PROMO_MAX_ERRORES` (20) `error` en
  24 h, no se envía más (`cortacircuitos`) hasta revisión manual. Se queda
  trabado aunque pasen las 24 h: se rearma poniendo
  `DEMO_CORREO_PROMO_REARMADO_EN` (fecha UTC ISO, p. ej. 2026-10-22T15:00)
  y solo cuentan los errores posteriores.
La reserva (contar y marcar) va en una transacción serializada con un lock
consultivo de Postgres, para que dos `/iniciar` simultáneos con el mismo
correo no manden dos. El DNS se consulta antes, fuera del lock.

Bajas: el pie pide responder a contacto@glomacx.com. Quien lo pida se agrega a
la lista de supresión de SES de la cuenta (la cuenta suprime BOUNCE y
COMPLAINT), y SES no le vuelve a entregar nada, sin columna nuestra:
    python scripts/baja_correo_promo.py persona@dominio.com
    (= aws sesv2 put-suppressed-destination --email-address … --reason COMPLAINT
       --region $SES_REGION)

Registro en la fila de `demos`: `correo_promo_estado` (`enviado|omitido|error`),
`correo_promo_enviado_at`, `correo_promo_message_id`. NULL = no se intentó
(envío apagado). Logs con id de demo, estado, motivo y message id; nunca el
correo, el nombre ni la respuesta de SES (puede traer la dirección).

Envs:
    DEMO_CORREO_PROMO_ACTIVO      1/true para enviar (default apagado)
    DEMO_CORREO_PROMO_DIAS        30
    DEMO_CORREO_PROMO_MAX_HORA    200
    DEMO_CORREO_PROMO_MAX_DIA     2000
    DEMO_CORREO_PROMO_MAX_ERRORES 20
    DEMO_CORREO_PROMO_REARMADO_EN (vacía)
    DEMO_CORREO_PROMO_SOLO_A      lista separada por comas (vacía = todos)
    DEMO_CORREO_REMITENTE         "Gloma <contacto@glomacx.com>"
    DEMO_CORREO_RESPONDER_A       contacto@glomacx.com
    DEMO_CORREO_CONFIG_SET        (vacía = sin configuration set)
    SES_REGION                    us-east-1 (el dominio está verificado ahí:
                                  excepción documentada a sa-east-1)
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

ESTADO_ENVIADO = "enviado"
ESTADO_OMITIDO = "omitido"
ESTADO_ERROR = "error"

#: Versiones del consentimiento cuyo texto avisa que se envía el correo de la
#: promoción. Al publicar una versión nueva del texto legal que lo mantenga,
#: se agrega aquí (y `routers/demo.CONSENT_VERSION` pasa a esa).
VERSIONES_CON_CORREO: FrozenSet[str] = frozenset({"demo-2026-10c"})

_DIR = Path(__file__).resolve().parent.parent / "templates" / "correo_promo_demo"
_REMITENTE_DEFAULT = "Gloma <contacto@glomacx.com>"
_RESPONDER_A_DEFAULT = "contacto@glomacx.com"
LIST_UNSUBSCRIBE = (
    "<mailto:contacto@glomacx.com?subject=No%20quiero%20recibir%20m%C3%A1s%20correos>"
)
#: Clave del lock consultivo que serializa la reserva (contar + marcar).
_LOCK_RESERVA = 644_001
_CONTROL = re.compile(r"[\x00-\x1f\x7f\u0085  ]")
#: #647 A1: una palabra de letras (sin dígitos, `_`, apóstrofos ni guiones).
_NOMBRE_OK = re.compile(r"^[^\W\d_][^\W\d_'’-]{0,29}$")
_EMPRESA_MALA = re.compile(r"[./:@\\{}]|\d{5,}")
_EMPRESA_GENERICA = "tu empresa"
_DNS_TIMEOUT_S = 2.0

#: Desechables conocidos (lista corta; se compara el dominio y sus subdominios).
DOMINIOS_DESECHABLES: FrozenSet[str] = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "guerrillamail.org",
    "guerrillamail.info", "guerrillamailblock.com", "sharklasers.com", "grr.la",
    "10minutemail.com", "10minutemail.net", "temp-mail.org", "tempmail.com",
    "tempmail.net", "tempmailo.com", "tempail.com", "yopmail.com", "yopmail.net",
    "yopmail.fr", "trashmail.com", "trashmail.de", "getnada.com", "nada.email",
    "dispostable.com", "maildrop.cc", "throwawaymail.com", "fakeinbox.com",
    "mintemail.com", "emailondeck.com", "moakt.com", "mohmal.com", "mailnesia.com",
    "mytemp.email", "1secmail.com", "1secmail.net", "burnermail.io",
    "inboxkitten.com", "spam4.me", "mailcatch.com", "getairmail.com", "tmpmail.org",
    "tmpmail.net", "dropmail.me", "emailfake.com", "crazymailing.com",
})


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def activo() -> bool:
    return (os.getenv("DEMO_CORREO_PROMO_ACTIVO") or "").strip().lower() in (
        "1", "true", "si", "sí", "yes", "on")


def _entero(nombre: str, default: int, minimo: int) -> int:
    try:
        return max(minimo, int(os.getenv(nombre) or default))
    except ValueError:
        return default


def dias_entre_correos() -> int:
    return _entero("DEMO_CORREO_PROMO_DIAS", 30, 1)


def maximo_por_hora() -> int:
    return _entero("DEMO_CORREO_PROMO_MAX_HORA", 200, 0)


def maximo_diario() -> int:
    return _entero("DEMO_CORREO_PROMO_MAX_DIA", 2000, 0)


def maximo_errores() -> int:
    return _entero("DEMO_CORREO_PROMO_MAX_ERRORES", 20, 1)


def rearmado_en() -> Optional[datetime]:
    crudo = (os.getenv("DEMO_CORREO_PROMO_REARMADO_EN") or "").strip()
    if not crudo:
        return None
    try:
        fecha = datetime.fromisoformat(crudo.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("correo_promo: DEMO_CORREO_PROMO_REARMADO_EN inválida; se ignora")
        return None
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    return fecha


def solo_a() -> Optional[Set[str]]:
    crudo = (os.getenv("DEMO_CORREO_PROMO_SOLO_A") or "").strip()
    if not crudo:
        return None
    return {c.strip().lower() for c in re.split(r"[,;\s]+", crudo) if c.strip()}


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------

def version_para(telefono: Optional[str]) -> str:
    return "co" if (telefono or "").strip().startswith("+57") else "intl"


@lru_cache(maxsize=None)
def _plantilla(version: str, ext: str) -> str:
    return (_DIR / f"promo_demo_{version}.{ext}").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def _asuntos() -> Dict[str, Dict[str, str]]:
    return json.loads((_DIR / "asuntos.json").read_text(encoding="utf-8"))


def _limpio(valor: Optional[str], largo: int = 120) -> str:
    """Una línea: sin saltos ni caracteres de control, espacios colapsados y
    largo acotado."""
    v = _CONTROL.sub(" ", valor or "")
    return re.sub(r"\s+", " ", v).strip()[:largo]


def nombre_para_correo(nombre: Optional[str]) -> Optional[str]:
    """El primer nombre si pasa la lista blanca; si no, None (sin nombre)."""
    partes = _limpio(nombre).split(" ")
    primero = partes[0] if partes else ""
    return primero if _NOMBRE_OK.match(primero) else None


def empresa_para_correo(empresa: Optional[str]) -> str:
    e = _limpio(empresa, 80)
    if not e or _EMPRESA_MALA.search(e):
        return _EMPRESA_GENERICA
    return e


def _con_nombre(plantilla: str, nombre: Optional[str], escapar: bool) -> str:
    if nombre is None:
        # «{{nombre}}, tu promoción…» → «Tu promoción…»; «{{nombre}}, ganaste…»
        # → «Hola, ganaste…».
        return plantilla.replace("{{nombre}}, tu ", "Tu ").replace("{{nombre}}", "Hola")
    return plantilla.replace("{{nombre}}", html.escape(nombre, quote=True) if escapar else nombre)


def renderizar(version: str, nombre: Optional[str], empresa: Optional[str]) -> Tuple[str, str, str]:
    """(asunto, html, texto) con los placeholders reemplazados.

    Nombre y empresa pasan primero por su lista blanca; además, en el HTML
    van escapados con `html.escape` y en el texto y el asunto, en una línea.
    La empresa se reemplaza al final y no puede traer `{}`: no hay forma de
    que un valor meta otro placeholder."""
    n, e = nombre_para_correo(nombre), empresa_para_correo(empresa)
    asunto = _con_nombre(_asuntos()[version]["asunto"], n, False).replace("{{empresa}}", e)
    cuerpo_html = (_con_nombre(_plantilla(version, "html"), n, True)
                   .replace("{{empresa}}", html.escape(e, quote=True)))
    cuerpo_txt = _con_nombre(_plantilla(version, "txt"), n, False).replace("{{empresa}}", e)
    return _limpio(asunto, 200), cuerpo_html, cuerpo_txt


# ---------------------------------------------------------------------------
# Destinatario: desechables y MX
# ---------------------------------------------------------------------------

def _dominio(correo: str) -> str:
    return correo.rsplit("@", 1)[-1].strip().lower().rstrip(".")


def es_desechable(correo: str) -> bool:
    dominio = _dominio(correo)
    partes = dominio.split(".")
    return any(".".join(partes[i:]) in DOMINIOS_DESECHABLES for i in range(len(partes) - 1))


def _consultar_mx(dominio: str) -> List[str]:
    """Los hosts MX del dominio. Levanta las excepciones de dnspython."""
    import dns.resolver

    resolver = dns.resolver.Resolver()
    resolver.timeout = _DNS_TIMEOUT_S
    resolver.lifetime = _DNS_TIMEOUT_S
    respuesta = resolver.resolve(dominio, "MX")
    return [str(r.exchange).rstrip(".") for r in respuesta]


def motivo_mx(correo: str) -> Optional[str]:
    """None si el dominio tiene MX; `sin_mx` si no existe o no recibe correo
    (incluye el «null MX» de RFC 7505); `dns` si no se pudo saber."""
    import dns.exception
    import dns.resolver

    try:
        hosts = _consultar_mx(_dominio(correo))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return "sin_mx"
    except (dns.exception.Timeout, dns.resolver.NoNameservers, dns.exception.DNSException):
        return "dns"
    except Exception:  # noqa: BLE001 — cualquier otra cosa: no enviar a ciegas
        return "dns"
    if not [h for h in hosts if h]:
        return "sin_mx"
    return None


# ---------------------------------------------------------------------------
# SES
# ---------------------------------------------------------------------------

def _cliente_ses():
    import boto3
    from botocore.config import Config

    return boto3.client(
        "sesv2",
        region_name=os.getenv("SES_REGION") or "us-east-1",
        config=Config(connect_timeout=3, read_timeout=6,
                      retries={"max_attempts": 2, "mode": "standard"}),
    )


def _enviar_ses(destino: str, asunto: str, cuerpo_html: str, cuerpo_txt: str) -> str:
    cliente = _cliente_ses()
    simple: Dict[str, object] = {
        "Subject": {"Data": asunto, "Charset": "UTF-8"},
        "Body": {
            "Text": {"Data": cuerpo_txt, "Charset": "UTF-8"},
            "Html": {"Data": cuerpo_html, "Charset": "UTF-8"},
        },
    }
    try:
        admite_cabeceras = "Headers" in cliente.meta.service_model.shape_for("Message").members
    except Exception:  # noqa: BLE001
        admite_cabeceras = False
    if admite_cabeceras:
        simple["Headers"] = [{"Name": "List-Unsubscribe", "Value": LIST_UNSUBSCRIBE}]
    parametros: Dict[str, object] = {
        "FromEmailAddress": os.getenv("DEMO_CORREO_REMITENTE") or _REMITENTE_DEFAULT,
        "Destination": {"ToAddresses": [destino]},
        "ReplyToAddresses": [os.getenv("DEMO_CORREO_RESPONDER_A") or _RESPONDER_A_DEFAULT],
        "Content": {"Simple": simple},
    }
    config_set = (os.getenv("DEMO_CORREO_CONFIG_SET") or "").strip()
    if config_set:
        parametros["ConfigurationSetName"] = config_set
    respuesta = cliente.send_email(**parametros)
    return str(respuesta.get("MessageId") or "")[:100]


def _codigo_error(exc: Exception) -> str:
    """Código del error para el log, sin el mensaje (SES puede incluir la
    dirección de destino)."""
    respuesta = getattr(exc, "response", None)
    if isinstance(respuesta, dict):
        codigo = (respuesta.get("Error") or {}).get("Code")
        if codigo:
            return str(codigo)[:60]
    return type(exc).__name__


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------

def cortacircuitos_abierto(db: Session, ahora: datetime) -> bool:
    """¿Hubo `maximo_errores()` errores dentro de alguna ventana de 24 h desde
    el último rearme? Queda abierto (sin envíos) hasta que se rearme."""
    D = models.Demo
    q = db.query(D.created_at).filter(D.correo_promo_estado == ESTADO_ERROR)
    desde = rearmado_en()
    if desde is not None:
        q = q.filter(D.created_at >= desde)
    fechas = sorted(f for (f,) in q.all() if f is not None)
    n = maximo_errores()
    return any(fechas[i + n - 1] - fechas[i] <= timedelta(hours=24)
               for i in range(len(fechas) - n + 1))


def _contar_enviados(db: Session, desde: datetime, ahora: datetime) -> int:
    D = models.Demo
    return int(
        db.query(func.count(D.id))
        .filter(
            D.correo_promo_estado == ESTADO_ENVIADO,
            D.correo_promo_enviado_at >= desde,
            # El correo sale segundos después de crear la demo: con esto la
            # cuenta usa el índice de `created_at`.
            D.created_at >= desde - timedelta(hours=24),
        )
        .scalar() or 0
    )


def _reservar(db: Session, demo: models.Demo, correo: str, ahora: datetime) -> Optional[str]:
    """Marca la demo como `enviado` (reserva) u `omitido` y hace commit.
    Devuelve None si toca enviar; si no, el motivo de la omisión."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_RESERVA})
    D, L = models.Demo, models.Lead
    motivo: Optional[str] = None
    if (
        db.query(func.count(D.id))
        .join(L, L.id == D.lead_id)
        .filter(
            L.email == correo,
            D.id != demo.id,
            D.correo_promo_estado == ESTADO_ENVIADO,
            D.correo_promo_enviado_at >= ahora - timedelta(days=dias_entre_correos()),
        )
        .scalar()
    ):
        motivo = "ya_recibio"
    elif _contar_enviados(db, ahora - timedelta(hours=1), ahora) >= maximo_por_hora():
        motivo = "techo_hora"
    elif _contar_enviados(db, ahora - timedelta(hours=24), ahora) >= maximo_diario():
        motivo = "techo_diario"
    elif cortacircuitos_abierto(db, ahora):
        motivo = "cortacircuitos"
    if motivo:
        demo.correo_promo_estado = ESTADO_OMITIDO
    else:
        demo.correo_promo_estado = ESTADO_ENVIADO
        demo.correo_promo_enviado_at = ahora
    db.commit()
    return motivo


def _omitir(db: Session, demo: models.Demo, motivo: str) -> str:
    demo.correo_promo_estado = ESTADO_OMITIDO
    db.commit()
    nivel = logging.WARNING if motivo == "cortacircuitos" else logging.INFO
    logger.log(nivel, "correo_promo: demo=%s estado=omitido motivo=%s", demo.id, motivo)
    return ESTADO_OMITIDO


def enviar_promo_de_demo(
    demo_id: int,
    nueva_sesion: Optional[Callable[[], Session]] = None,
    ahora: Optional[datetime] = None,
) -> Optional[str]:
    """Tarea de fondo. Devuelve el estado final (o None si no se intentó).
    Nunca levanta."""
    if not activo():
        return None
    if nueva_sesion is None:
        from ..database import SessionLocal
        nueva_sesion = SessionLocal
    db = nueva_sesion()
    estado: Optional[str] = None
    try:
        demo = db.query(models.Demo).filter(models.Demo.id == demo_id).first()
        if demo is None or demo.correo_promo_estado is not None:
            return demo.correo_promo_estado if demo else None   # idempotente
        lead = (db.query(models.Lead).filter(models.Lead.id == demo.lead_id).first()
                if demo.lead_id else None)
        if lead is None or not lead.email:
            return _omitir(db, demo, "sin_lead")
        if demo.consent_version not in VERSIONES_CON_CORREO:
            return _omitir(db, demo, "consentimiento")
        correo = lead.email.strip().lower()
        lista = solo_a()
        if lista is not None and correo not in lista:
            return _omitir(db, demo, "fuera_de_lista")
        if es_desechable(correo):
            return _omitir(db, demo, "desechable")
        telefono, nombre, empresa = lead.telefono, lead.nombre, demo.empresa
        db.rollback()                     # sin conexión tomada durante el DNS
        mx = motivo_mx(correo)
        demo = db.query(models.Demo).filter(models.Demo.id == demo_id).first()
        if demo is None or demo.correo_promo_estado is not None:
            return demo.correo_promo_estado if demo else None
        if mx:
            return _omitir(db, demo, mx)

        ahora = ahora or datetime.utcnow()
        motivo = _reservar(db, demo, correo, ahora)
        if motivo:
            nivel = logging.WARNING if motivo == "cortacircuitos" else logging.INFO
            logger.log(nivel, "correo_promo: demo=%s estado=omitido motivo=%s", demo_id, motivo)
            return ESTADO_OMITIDO

        version = version_para(telefono)
        asunto, cuerpo_html, cuerpo_txt = renderizar(version, nombre, empresa)
        try:
            message_id = _enviar_ses(correo, asunto, cuerpo_html, cuerpo_txt)
        except Exception as exc:  # noqa: BLE001 — SES caído no rompe nada
            demo.correo_promo_estado = ESTADO_ERROR
            demo.correo_promo_enviado_at = None
            db.commit()
            logger.warning("correo_promo: demo=%s estado=error codigo=%s",
                           demo_id, _codigo_error(exc))
            return ESTADO_ERROR
        demo.correo_promo_message_id = message_id or None
        db.commit()
        estado = ESTADO_ENVIADO
        logger.info("correo_promo: demo=%s estado=enviado version=%s message_id=%s",
                    demo_id, version, message_id)
        return estado
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # Sin traza: el error de SQL lleva los parámetros (el correo).
        logger.error("correo_promo: falló demo=%s tipo=%s", demo_id, type(exc).__name__)
        return estado
    finally:
        db.close()
