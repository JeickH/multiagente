"""Bot runner: orquesta motor + sesión persistida + envío a Meta.

Es la capa entre `bot_engine.advance()` (puro) y el mundo real:
carga la sesión de DB, corre el motor, envía cada acción por WhatsApp
Cloud API, persiste sesiones y programa delays.

Invocado desde:
  - meta_webhook.py     cuando entra un mensaje y hay bot que responder.
  - scheduler tick      cuando vence un BotPendingAction de delay.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import crud, models
from . import bot_engine, meta_whatsapp

logger = logging.getLogger(__name__)


def _load_state(session: Optional[models.BotSession]) -> Optional[dict]:
    if session is None or not session.state:
        return None
    try:
        return json.loads(session.state)
    except (ValueError, TypeError):
        return None


def _persist_state(
    db: Session,
    session: models.BotSession,
    next_state: Optional[dict],
    finished: bool,
    waiting: bool,
) -> None:
    session.state = json.dumps(next_state) if next_state else None
    if finished:
        session.status = models.BOT_SESSION_FINISHED
        session.finished_at = datetime.utcnow()
    elif waiting:
        session.status = models.BOT_SESSION_WAITING
    else:
        session.status = models.BOT_SESSION_RUNNING
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)


def _create_session(
    db: Session, bot: models.Bot, conversation_id: int
) -> models.BotSession:
    s = models.BotSession(
        bot_id=bot.id,
        conversation_id=conversation_id,
        state=None,
        status=models.BOT_SESSION_RUNNING,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _schedule_delay(
    db: Session, session: models.BotSession, seconds: int
) -> None:
    pa = models.BotPendingAction(
        session_id=session.id,
        scheduled_at=datetime.utcnow() + timedelta(seconds=max(seconds, 1)),
        action_type="resume_session",
        status=models.BOT_PENDING_STATUS_PENDING,
    )
    db.add(pa)
    db.commit()


def run_turn(
    db: Session,
    *,
    bot: models.Bot,
    conversation: models.Conversation,
    session: Optional[models.BotSession],
    user_input: Optional[str],
    meta_account: Optional[models.MetaAccount],
) -> models.BotSession:
    """Ejecuta un turno del bot para la conversación dada.

    - Si `session` es None, crea una nueva (inicio del flujo).
    - Si hay `user_input`, se pasa al motor.
    - Por cada acción retornada:
        * `say` / `say_media` / `end` → se envían como mensaje a Meta.
        * `pause` → se programa como BotPendingAction y se corta el turno.
        * `ask` → no se envía nada extra; la acción anterior (say) ya fue enviada.
                  Lo realmente importante es que la sesión queda en status=waiting.

    Idempotencia: el caller debe haber deduplicado por meta_message_id.
    """
    if session is None:
        session = _create_session(db, bot, conversation.id)

    state = _load_state(session)
    result = bot_engine.advance(bot, state, user_input)

    actions = result["actions"]
    next_state = result["next_state"]
    finished = bool(result["finished"])
    waiting = any(a.get("type") == "ask" for a in actions)

    # Procesamos las acciones en orden. Si encontramos un `pause`, cortamos
    # el turno y programamos un delay; el resto queda para cuando vuelva.
    for i, action in enumerate(actions):
        atype = action.get("type")
        payload = action.get("payload") or {}

        if atype == "say":
            _send_text(db, conversation, bot, meta_account, payload.get("text", ""))
        elif atype == "say_media":
            # MVP: enviamos un texto con el caption (sin subir media real).
            # Cuando integremos upload de media real a Meta se reemplaza esto.
            caption = payload.get("caption", "")
            _send_text(db, conversation, bot, meta_account, caption or "[archivo multimedia]")
        elif atype == "ask":
            # El `ask` en sí no viaja al contacto: el prompt ya se envió como
            # `say` inmediatamente antes. Solo marca que el motor espera input.
            pass
        elif atype == "end":
            _send_text(db, conversation, bot, meta_account, payload.get("text", ""))
        elif atype == "pause":
            seconds = int(payload.get("seconds") or 0)
            if seconds > 0:
                _schedule_delay(db, session, seconds)
                # Guardamos un estado "intermedio" para que el scheduler tick
                # retome desde el próximo step cuando venza.
                _persist_state(db, session, next_state, finished=False, waiting=False)
                return session
        else:
            logger.warning("bot_runner: acción desconocida %s", atype)

    _persist_state(db, session, next_state, finished, waiting)
    return session


def _send_text(
    db: Session,
    conversation: models.Conversation,
    bot: models.Bot,
    account: Optional[models.MetaAccount],
    text: str,
) -> None:
    """Envía texto por Meta + persiste el mensaje saliente en la conversación."""
    if not text.strip():
        return

    if account is None or not crud.is_meta_account_usable(account):
        crud.add_message(
            db,
            conversation,
            direction="outbound",
            content=text,
            message_type="text",
            sent_by_user_id=None,
            status="failed",
            error_detail="MetaAccount no usable",
        )
        return

    try:
        meta_id, _ = meta_whatsapp.send_text_message(
            account, conversation.contact_wa_id, text
        )
        crud.add_message(
            db,
            conversation,
            direction="outbound",
            content=text,
            message_type="text",
            meta_message_id=meta_id,
            sent_by_user_id=None,
            status="sent",
        )
    except Exception as exc:  # MetaWhatsAppError, CryptoError, red, etc.
        logger.exception("Error enviando mensaje del bot %s", bot.id)
        crud.add_message(
            db,
            conversation,
            direction="outbound",
            content=text,
            message_type="text",
            sent_by_user_id=None,
            status="failed",
            error_detail=str(exc)[:500],
        )


def process_pending_action(
    db: Session, pa: models.BotPendingAction
) -> None:
    """Procesa una BotPendingAction vencida: resume la sesión sin user_input.

    Marca la acción como done/failed según resultado.
    """
    pa.attempts += 1
    session = pa.session
    if session is None or session.status in (
        models.BOT_SESSION_FINISHED,
        models.BOT_SESSION_CANCELLED,
    ):
        pa.status = models.BOT_PENDING_STATUS_DONE
        pa.processed_at = datetime.utcnow()
        db.commit()
        return

    conversation = session.conversation
    bot = session.bot
    if conversation is None or bot is None:
        pa.status = models.BOT_PENDING_STATUS_FAILED
        pa.last_error = "session sin conversation/bot"
        pa.processed_at = datetime.utcnow()
        db.commit()
        return

    # Buscar la MetaAccount del team de la conversación.
    account = crud.get_meta_account_for_team(db, conversation.team_id)

    try:
        run_turn(
            db,
            bot=bot,
            conversation=conversation,
            session=session,
            user_input=None,
            meta_account=account,
        )
        pa.status = models.BOT_PENDING_STATUS_DONE
    except Exception as exc:  # pragma: no cover - defensivo
        logger.exception("process_pending_action falló")
        pa.status = models.BOT_PENDING_STATUS_FAILED
        pa.last_error = str(exc)[:500]
    pa.processed_at = datetime.utcnow()
    db.commit()
