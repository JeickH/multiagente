"""Endpoints públicos de la landing Gloma.

Dos capacidades, ambas SIN autenticación (son el frente público de
glomabeauty.com, único prefijo que `frontend/middleware.ts` deja pasar bajo el
apex):

- `POST /landing/leads`  → formulario de contacto (Sprint 12).
- `POST /landing/chat`   → widget de WhatsApp de la landing (Sprint 20 #269):
  instancia el bot institucional de Gloma sin que el visitante tenga que
  escribir por WhatsApp. Es el MISMO bot que atiende el simulador de la app y
  que atenderá el WhatsApp de Gloma cuando el número quede conectado.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import time
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from .. import crud, models
from ..dependencies import get_db
from ..services import llm_engine
from ..services.messaging import PREFIJO_CHAT_WEB
from ..services.crypto import CryptoError, decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/landing", tags=["landing"])


PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{5,30}$")

# Rangos de "¿cuántos chats reciben al mes?" alineados con los paquetes de
# conversaciones publicados en la landing (600 / 2.000 / 6.000).
CHATS_MES_OPCIONES = ("menos_600", "600_2000", "2000_6000", "mas_6000", "no_se")


def _limpiar_texto(v: str) -> str:
    """Sin caracteres de control ni espacios de sobra."""
    v = re.sub(r"[\x00-\x1f\x7f]", " ", v or "")
    return re.sub(r"\s+", " ", v).strip()


class LeadIn(BaseModel):
    """Solicitud de contacto del form de la landing ("Quiero que me contacten").

    #298: `nombre` es obligatorio — el equipo necesita a quién llamar cuando
    hace el seguimiento desde `/citas`.
    """

    nombre: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    telefono: str = Field(..., min_length=6, max_length=32)
    source: str = Field(default="gloma_landing", max_length=64)
    # 2026-09-27: calificación del prospecto y autorización de datos. Todos
    # opcionales en el esquema porque la landing de Gorvek usa el mismo
    # endpoint sin ellos; la autorización sí se exige a la de Gloma (abajo).
    agencia: Optional[str] = Field(default=None, max_length=120)
    chats_mes: Optional[str] = Field(default=None, max_length=16)
    acepta_privacidad: bool = False

    @field_validator("nombre")
    @classmethod
    def _clean_nombre(cls, v: str) -> str:
        # El largo lo acota Field.
        v = _limpiar_texto(v)
        if len(v) < 2:
            raise ValueError("Nombre inválido")
        return v

    @field_validator("agencia")
    @classmethod
    def _clean_agencia(cls, v: Optional[str]) -> Optional[str]:
        v = _limpiar_texto(v or "")
        return v or None

    @field_validator("chats_mes")
    @classmethod
    def _check_chats_mes(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return None
        if v not in CHATS_MES_OPCIONES:
            raise ValueError("Opción de chats al mes inválida")
        return v

    @field_validator("telefono")
    @classmethod
    def _strip_phone(cls, v: str) -> str:
        v = (v or "").strip()
        if not PHONE_RE.match(v):
            raise ValueError("Teléfono inválido")
        return v

    @field_validator("source")
    @classmethod
    def _strip_source(cls, v: str) -> str:
        return (v or "").strip() or "gloma_landing"

    @model_validator(mode="after")
    def _exige_autorizacion_en_gloma(self) -> "LeadIn":
        # Ley 1581: sin autorización expresa no se guardan los datos. El
        # checkbox del form es obligatorio, pero la regla vive aquí para que
        # no dependa del navegador.
        if self.source == "gloma_landing" and not self.acepta_privacidad:
            raise ValueError("Debes aceptar la política de tratamiento de datos")
        return self


class LeadOut(BaseModel):
    ok: bool = True


@router.post("/leads", response_model=LeadOut)
def create_lead(
    payload: LeadIn, request: Request, db: Session = Depends(get_db)
):
    """Guarda un lead del form de contacto. Público (sin auth).

    Rate-limit MVP en memoria: max 5 leads/IP/hora.
    """
    ip = (request.client.host if request.client else "unknown")[:60]
    ua = (request.headers.get("user-agent") or "")[:500]

    # Rate-limit básico
    since = datetime.utcnow() - timedelta(hours=1)
    count = (
        db.query(models.Lead)
        .filter(models.Lead.ip_address == ip, models.Lead.created_at >= since)
        .count()
    )
    if count >= 5:
        raise HTTPException(
            status_code=429,
            detail="Hemos recibido demasiadas solicitudes desde tu conexión. Intenta más tarde.",
        )

    lead = models.Lead(
        nombre=payload.nombre,
        email=str(payload.email).lower(),
        telefono=payload.telefono,
        source=payload.source,
        user_agent=ua,
        ip_address=ip,
        estado="pendiente",
        agencia=payload.agencia,
        chats_mes=payload.chats_mes,
        acepto_privacidad_at=datetime.utcnow() if payload.acepta_privacidad else None,
    )
    db.add(lead)
    db.commit()
    # Sin PII en el log (regla de seguridad #1): solo id y origen.
    logger.info("lead creado id=%s source=%s", lead.id, lead.source)
    return LeadOut(ok=True)


# ---------------------------------------------------------------------------
# Chat público del widget de la landing (#269)
# ---------------------------------------------------------------------------

# Cuenta dueña del bot institucional (creada por scripts/seed_bot_gloma.py).
_GLOMA_EMAIL = os.getenv("GLOMA_LANDING_EMAIL", "gloma@glomabeauty.com")

_MAX_MESSAGE_CHARS = 500     # lo que puede escribir el visitante por turno
_MAX_TURNS_PER_SESSION = 25  # tope de turnos de una misma sesión
_SESSION_TTL_SECONDS = 3 * 3600
_RATE_PER_IP_HOUR = 40       # turnos por IP en la última hora
_RATE_GLOBAL_HOUR = 400      # techo global (protege el gasto de Bedrock)

# Texto que ve el visitante cuando el bot decide pasar a una persona: se le
# invita al WhatsApp de Gloma, que atiende el mismo agente y cuyas
# conversaciones quedan en la bandeja de la app, donde el equipo las toma
# (2026-10-29; antes era el WhatsApp personal 315, que no quedaba en la app).
_HANDOFF_TEXT = (
    "Te dejo con nuestro equipo 🤍 Escríbenos por WhatsApp al "
    "*+57 323 908 7528* o déjanos tus datos en el formulario de esta página y "
    "un especialista te contacta hoy mismo ✨"
)
_LIMIT_TEXT = (
    "¡Qué buena conversación! 🤍 Para seguir con calma, sigamos por WhatsApp al "
    "*+57 323 908 7528* o déjanos tus datos en el formulario de esta página."
)
_BUSY_TEXT = (
    "Estamos atendiendo muchas conversaciones en este momento 🙏 Escríbenos "
    "por WhatsApp al *+57 323 908 7528* y te atendemos de una vez."
)

# Rate-limit en memoria del proceso. El backend corre como una sola task ECS;
# si algún día escala horizontalmente, esto pasa a ser un límite por task (más
# permisivo, nunca menos seguro que no tener nada). Se complementa con el tope
# de turnos por sesión, que sí viaja firmado dentro del token.
_hits_by_ip: Dict[str, Deque[float]] = {}
_hits_global: Deque[float] = deque()
_rate_lock = Lock()


class ChatIn(BaseModel):
    """Turno del visitante. `session` es el token devuelto por el turno previo."""

    session: Optional[str] = Field(default=None, max_length=20000)
    message: Optional[str] = Field(default=None, max_length=_MAX_MESSAGE_CHARS)

    @field_validator("message")
    @classmethod
    def _clean_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        # Sin caracteres de control (evita basura en el prompt y en la BD).
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v).strip()
        return v[:_MAX_MESSAGE_CHARS] or None


class ChatAction(BaseModel):
    type: str                      # say | say_media
    text: str = ""
    url: Optional[str] = None
    media_type: Optional[str] = None


class ChatOut(BaseModel):
    actions: List[ChatAction]
    session: Optional[str] = None  # None cuando la conversación terminó
    finished: bool = False
    handoff: bool = False          # el widget muestra el CTA a WhatsApp humano


def _client_ip(request: Request) -> str:
    """IP del visitante. Detrás de API Gateway la real viene en X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()[:60]
    return (request.client.host if request.client else "unknown")[:60]


def _rate_ok(ip: str) -> bool:
    """Ventana deslizante de 1 hora, por IP y global. True si se puede atender."""
    now = time.monotonic()
    cutoff = now - 3600
    with _rate_lock:
        while _hits_global and _hits_global[0] < cutoff:
            _hits_global.popleft()
        bucket = _hits_by_ip.setdefault(ip, deque())
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if not bucket and len(_hits_by_ip) > 5000:
            # Higiene del diccionario: purga IPs sin actividad reciente.
            for key in [k for k, v in _hits_by_ip.items() if not v]:
                _hits_by_ip.pop(key, None)
            bucket = _hits_by_ip.setdefault(ip, deque())
        if len(bucket) >= _RATE_PER_IP_HOUR or len(_hits_global) >= _RATE_GLOBAL_HOUR:
            return False
        bucket.append(now)
        _hits_global.append(now)
        return True


def _load_session(token: Optional[str]) -> Dict[str, Any]:
    """Descifra el estado del cliente. Token inválido/vencido → sesión nueva.

    El historial NUNCA lo controla el visitante: viaja cifrado con Fernet
    (AEAD), así que no puede inyectar turnos falsos ni inflarlo.
    """
    nueva = {"history": [], "turns": 0, "contacto": None}
    if not token:
        return nueva
    try:
        data = json.loads(decrypt_secret(token, ttl_seconds=_SESSION_TTL_SECONDS))
    except (CryptoError, ValueError, TypeError):
        return nueva
    if not isinstance(data, dict):
        return nueva
    history = data.get("h")
    contacto = data.get("c")
    return {
        "history": history if isinstance(history, list) else [],
        "turns": int(data.get("n") or 0),
        # Sesiones de antes de guardar el chat (sin "c"): reciben uno nuevo.
        "contacto": contacto if _CONTACTO_WEB_RE.fullmatch(str(contacto or "")) else None,
    }


def _dump_session(history: List[Dict[str, str]], turns: int, contacto: Optional[str] = None) -> str:
    data: Dict[str, Any] = {"h": history, "n": turns}
    if contacto:
        data["c"] = contacto
    return encrypt_secret(json.dumps(data, ensure_ascii=False))


# ---------------------------------------------------------------------------
# El chat de la página queda en la bandeja de Gloma (CEO, 2026-10-29): todo lo
# que dice el agente tiene que verse en la app, por la web y por WhatsApp.
# Cada visitante es una conversación con un contacto `web-<hex>` que no es un
# teléfono: viaja dentro del token cifrado, así que el visitante no puede
# elegirlo ni escribir en la conversación de otro. `messaging` se niega a
# mandarle un WhatsApp a un `web-…`.
# ---------------------------------------------------------------------------

_CONTACTO_WEB_RE = re.compile(re.escape(PREFIJO_CHAT_WEB) + r"[0-9a-f]{12}")


def _nuevo_contacto_web() -> str:
    return f"{PREFIJO_CHAT_WEB}{secrets.token_hex(6)}"


def _guardar_turno_web(
    db: Session,
    bot: models.Bot,
    contacto: str,
    entrada: Optional[str],
    salidas: List["ChatAction"],
) -> None:
    """Guarda el turno en la conversación del visitante. Nunca levanta: si la
    base falla, el visitante igual recibe su respuesta."""
    if db is None:
        return
    try:
        # El team del dueño del bot (`Bot.team_id` es de compatibilidad y no se usa).
        team_id = (
            db.query(models.Team.id)
            .filter(models.Team.owner_user_id == bot.user_id)
            .order_by(models.Team.id)
            .limit(1)
            .scalar()
        )
        if team_id is None:
            logger.error("landing_chat: el bot %s no tiene team; el chat no se guarda", bot.id)
            return
        conv = crud.get_or_create_conversation(
            db, team_id=team_id, contact_wa_id=contacto,
            contact_name=f"Chat web · {contacto[-4:]}",
        )
        if entrada:
            crud.add_message(db, conv, direction="inbound", content=entrada, status="received")
        for salida in salidas:
            contenido = "\n".join(p for p in (salida.text, salida.url) if p)
            if contenido:
                tipo = "text" if salida.type == "say" else (salida.media_type or "image")
                crud.add_message(db, conv, direction="outbound", content=contenido, message_type=tipo)
    except Exception:
        logger.exception("landing_chat: no se pudo guardar el turno del chat web")
        try:
            db.rollback()
        except Exception:
            pass


def _gloma_bot(db: Session) -> Optional[models.Bot]:
    """Bot institucional de Gloma: el bot LLM activo de la cuenta oficial."""
    owner = (
        db.query(models.User)
        .filter(models.User.correo == _GLOMA_EMAIL.lower())
        .first()
    )
    if owner is None:
        return None
    return (
        db.query(models.Bot)
        .filter(
            models.Bot.user_id == owner.id,
            models.Bot.engine == "llm",
            models.Bot.status == "active",
        )
        .order_by(models.Bot.id.desc())
        .first()
    )


def _only_text(text: str) -> ChatOut:
    return ChatOut(actions=[ChatAction(type="say", text=text)], session=None,
                   finished=True, handoff=True)


@router.post("/chat", response_model=ChatOut)
def landing_chat(payload: ChatIn, request: Request, db: Session = Depends(get_db)):
    """Un turno de conversación con el bot institucional de Gloma. Público.

    Mismo motor (`services/llm_engine`) que usan el simulador de la app y los
    webhooks de WhatsApp: cambiar el contexto a priori actualiza los 3 canales.
    El visitante es anónimo: no se crea usuario. Desde 2026-10-29 cada chat
    queda como conversación en la bandeja de Gloma (contacto `web-<hex>`, ver
    `_guardar_turno_web`); el historial que lee el bot sigue cifrado en `session`.
    """
    bot = _gloma_bot(db)
    if bot is None:
        # No debería pasar (el seed corre en cada despliegue); si pasa, el
        # visitante recibe el canal humano en vez de un error técnico.
        logger.error("landing_chat: no hay bot institucional para %s", _GLOMA_EMAIL)
        return _only_text(_BUSY_TEXT)

    if not _rate_ok(_client_ip(request)):
        logger.warning("landing_chat: rate-limit alcanzado")
        return _only_text(_BUSY_TEXT)

    sess = _load_session(payload.session)
    contacto = sess["contacto"] or _nuevo_contacto_web()
    if sess["turns"] >= _MAX_TURNS_PER_SESSION:
        salida = _only_text(_LIMIT_TEXT)
        _guardar_turno_web(db, bot, contacto, payload.message, salida.actions)
        return salida

    result = llm_engine.advance(
        bot, {"history": sess["history"]} if sess["history"] else None,
        payload.message,
    )
    llm_engine.record_decision(db, bot, result.get("telemetry"), source="landing")
    # #276: si el bot agendó una demo en este turno, queda en `demo_bookings`.
    llm_engine.record_booking(db, bot, result.get("telemetry"), source="landing")

    actions: List[ChatAction] = []
    handoff = False
    for act in result.get("actions") or []:
        kind = act.get("type")
        data = act.get("payload") or {}
        if kind == "say":
            text = (data.get("text") or "").strip()
            if text:
                actions.append(ChatAction(type="say", text=text))
        elif kind == "say_media":
            actions.append(ChatAction(
                type="say_media", text=data.get("caption") or "",
                url=data.get("url") or "",
                media_type=data.get("media_type") or "image",
            ))
        elif kind == "handoff":
            # En la landing no hay bandeja donde entregar al visitante: se le
            # ofrece el canal humano real de Gloma.
            handoff = True
            actions.append(ChatAction(type="say", text=_HANDOFF_TEXT))
        # 'end' no agrega texto: el bot ya se despidió en un `say`.

    finished = bool(result.get("finished")) or handoff
    next_state = result.get("next_state") or {}
    history = next_state.get("history") if isinstance(next_state, dict) else None
    session_token = (
        None if finished or not history
        else _dump_session(history, sess["turns"] + 1, contacto)
    )
    actions = actions or [ChatAction(type="say", text=_HANDOFF_TEXT)]
    _guardar_turno_web(db, bot, contacto, payload.message, actions)
    return ChatOut(
        actions=actions,
        session=session_token,
        finished=finished,
        handoff=handoff,
    )
