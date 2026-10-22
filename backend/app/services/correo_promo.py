"""Correo automático de la promoción de la demo (#644).

Cuando un prospecto inicia la demo en `glomacx.com/demo` (lead y demo ya
creados, nunca en el 202 falso del honeypot ni cuando un tope rechaza), el
backend le manda por SES el correo de la promoción que ve en la pantalla de
premio. Corre como tarea de fondo con su propia sesión: no bloquea ni cambia la
respuesta de `/demo/iniciar`, y nunca levanta.

Versión: CO si el teléfono del lead es `+57`, si no INTL (igual que la
pantalla de premio). Plantillas en `app/templates/correo_promo_demo/`
(copiadas de `ventas/correo_promo_demo/`, que es donde se editan y se
regeneran con `build_correo.py`).

Anti-abuso (los topes por correo de la demo están altos por decisión del CEO,
así que esto es lo que evita usar la demo para mandarle correos a terceros):
- a lo sumo 1 correo por dirección cada `DEMO_CORREO_PROMO_DIAS` (30), contado
  sobre `demos` unidas a su lead;
- techo global de `DEMO_CORREO_PROMO_MAX_DIA` (2000) en 24 h;
- `DEMO_CORREO_PROMO_SOLO_A`: si está definida, solo se envía a esas
  direcciones (pruebas).
La reserva (contar y marcar) va en una transacción serializada con un lock
consultivo de Postgres, para que dos `/iniciar` simultáneos con el mismo
correo no manden dos.

Registro en la fila de `demos`: `correo_promo_estado` (`enviado|omitido|error`),
`correo_promo_enviado_at`, `correo_promo_message_id`. NULL = no se intentó
(envío apagado). Logs con id de demo, estado, motivo y message id; nunca el
correo, el nombre ni la respuesta de SES (puede traer la dirección).

Envs:
    DEMO_CORREO_PROMO_ACTIVO    1/true para enviar (default apagado)
    DEMO_CORREO_PROMO_DIAS      30
    DEMO_CORREO_PROMO_MAX_DIA   2000
    DEMO_CORREO_PROMO_SOLO_A    lista separada por comas (vacía = todos)
    DEMO_CORREO_REMITENTE       "Gloma <contacto@glomacx.com>"
    DEMO_CORREO_RESPONDER_A     contacto@glomacx.com
    SES_REGION                  us-east-1 (el dominio está verificado ahí:
                                excepción documentada a sa-east-1)
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Optional, Set, Tuple

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

ESTADO_ENVIADO = "enviado"
ESTADO_OMITIDO = "omitido"
ESTADO_ERROR = "error"

_DIR = Path(__file__).resolve().parent.parent / "templates" / "correo_promo_demo"
_REMITENTE_DEFAULT = "Gloma <contacto@glomacx.com>"
_RESPONDER_A_DEFAULT = "contacto@glomacx.com"
LIST_UNSUBSCRIBE = (
    "<mailto:contacto@glomacx.com?subject=No%20quiero%20recibir%20m%C3%A1s%20correos>"
)
#: Clave del lock consultivo que serializa la reserva (contar + marcar).
_LOCK_RESERVA = 644_001
_CONTROL = re.compile(r"[\x00-\x1f\x7f\u0085  ]")


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


def maximo_diario() -> int:
    return _entero("DEMO_CORREO_PROMO_MAX_DIA", 2000, 0)


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
    """Una línea: sin saltos ni caracteres de control (inyección de
    cabeceras en el asunto), espacios colapsados y largo acotado."""
    v = _CONTROL.sub(" ", valor or "")
    return re.sub(r"\s+", " ", v).strip()[:largo]


def primer_nombre(nombre: Optional[str]) -> str:
    partes = _limpio(nombre).split(" ")
    return partes[0] if partes and partes[0] else "Hola"


def renderizar(version: str, nombre: Optional[str], empresa: Optional[str]) -> Tuple[str, str, str]:
    """(asunto, html, texto) con los placeholders reemplazados.

    En el HTML los valores van escapados con `html.escape`; en el texto y el
    asunto, limpios (una línea, sin controles)."""
    n, e = primer_nombre(nombre), _limpio(empresa) or "tu empresa"
    asunto = _asuntos()[version]["asunto"].replace("{{nombre}}", n).replace("{{empresa}}", e)
    cuerpo_html = (_plantilla(version, "html")
                   .replace("{{nombre}}", html.escape(n, quote=True))
                   .replace("{{empresa}}", html.escape(e, quote=True)))
    cuerpo_txt = _plantilla(version, "txt").replace("{{nombre}}", n).replace("{{empresa}}", e)
    return _limpio(asunto, 200), cuerpo_html, cuerpo_txt


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
    respuesta = cliente.send_email(
        FromEmailAddress=os.getenv("DEMO_CORREO_REMITENTE") or _REMITENTE_DEFAULT,
        Destination={"ToAddresses": [destino]},
        ReplyToAddresses=[os.getenv("DEMO_CORREO_RESPONDER_A") or _RESPONDER_A_DEFAULT],
        Content={"Simple": simple},
    )
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

def _reservar(db: Session, demo: models.Demo, correo: str, ahora: datetime) -> Optional[str]:
    """Marca la demo como `enviado` (reserva) o `omitido` y hace commit.
    Devuelve None si toca enviar; si no, el motivo de la omisión."""
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_RESERVA})
    motivo: Optional[str] = None
    lista = solo_a()
    D, L = models.Demo, models.Lead
    if lista is not None and correo not in lista:
        motivo = "fuera_de_lista"
    elif (
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
    elif (
        db.query(func.count(D.id))
        .filter(
            D.correo_promo_estado == ESTADO_ENVIADO,
            D.correo_promo_enviado_at >= ahora - timedelta(hours=24),
            # El correo sale segundos después de crear la demo: con esto la
            # cuenta usa el índice de `created_at`.
            D.created_at >= ahora - timedelta(hours=48),
        )
        .scalar()
        >= maximo_diario()
    ):
        motivo = "techo_diario"
    if motivo:
        demo.correo_promo_estado = ESTADO_OMITIDO
    else:
        demo.correo_promo_estado = ESTADO_ENVIADO
        demo.correo_promo_enviado_at = ahora
    db.commit()
    return motivo


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
            demo.correo_promo_estado = ESTADO_OMITIDO
            db.commit()
            logger.info("correo_promo: demo=%s estado=omitido motivo=sin_lead", demo_id)
            return ESTADO_OMITIDO
        correo = lead.email.strip().lower()
        ahora = ahora or datetime.utcnow()
        motivo = _reservar(db, demo, correo, ahora)
        if motivo:
            logger.info("correo_promo: demo=%s estado=omitido motivo=%s", demo_id, motivo)
            return ESTADO_OMITIDO

        version = version_para(lead.telefono)
        asunto, cuerpo_html, cuerpo_txt = renderizar(version, lead.nombre, demo.empresa)
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
