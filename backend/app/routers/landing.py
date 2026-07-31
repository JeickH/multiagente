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
import time
from collections import deque
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..dependencies import get_db
from ..services import llm_engine
from ..services.crypto import CryptoError, decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/landing", tags=["landing"])


PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{5,30}$")


class LeadIn(BaseModel):
    email: EmailStr
    telefono: str = Field(..., min_length=6, max_length=32)
    source: str = Field(default="gloma_landing", max_length=64)

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
        email=str(payload.email).lower(),
        telefono=payload.telefono,
        source=payload.source,
        user_agent=ua,
        ip_address=ip,
    )
    db.add(lead)
    db.commit()
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

# Texto que ve el visitante cuando el bot decide pasar a una persona: en la
# landing todavía no hay número de WhatsApp conectado, así que el "handoff" se
# resuelve invitando al canal humano real de Gloma (regla #3 del sprint).
_HANDOFF_TEXT = (
    "Te dejo con nuestro equipo 🤍 Escríbenos por WhatsApp al "
    "*+57 300 318 7871* o déjanos tus datos en el formulario de esta página y "
    "un especialista te contacta hoy mismo ✨"
)
_LIMIT_TEXT = (
    "¡Qué buena conversación! 🤍 Para seguir con calma, sigamos por WhatsApp al "
    "*+57 300 318 7871* o déjanos tus datos en el formulario de esta página."
)
_BUSY_TEXT = (
    "Estamos atendiendo muchas conversaciones en este momento 🙏 Escríbenos "
    "por WhatsApp al *+57 300 318 7871* y te atendemos de una vez."
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
    if not token:
        return {"history": [], "turns": 0}
    try:
        data = json.loads(decrypt_secret(token, ttl_seconds=_SESSION_TTL_SECONDS))
    except (CryptoError, ValueError, TypeError):
        return {"history": [], "turns": 0}
    if not isinstance(data, dict):
        return {"history": [], "turns": 0}
    history = data.get("h")
    return {
        "history": history if isinstance(history, list) else [],
        "turns": int(data.get("n") or 0),
    }


def _dump_session(history: List[Dict[str, str]], turns: int) -> str:
    return encrypt_secret(
        json.dumps({"h": history, "n": turns}, ensure_ascii=False)
    )


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
    El visitante es anónimo — no se crea usuario, contacto ni conversación; el
    estado va cifrado en `session` y solo queda telemetría del turno.
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
    if sess["turns"] >= _MAX_TURNS_PER_SESSION:
        return _only_text(_LIMIT_TEXT)

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
        else _dump_session(history, sess["turns"] + 1)
    )
    return ChatOut(
        actions=actions or [ChatAction(type="say", text=_HANDOFF_TEXT)],
        session=session_token,
        finished=finished,
        handoff=handoff,
    )
