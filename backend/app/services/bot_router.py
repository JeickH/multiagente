"""Router de bots: decide qué bot debe atender un mensaje entrante.

Prioridad (Sprint 10):
  1. Si la conversación tiene una BotSession activa (running/waiting),
     sigue con ese bot. Así un flujo en curso no se interrumpe aunque el
     mensaje contenga keywords de otro bot.
  2. Si no hay sesión activa, se buscan bots con trigger_type='keyword'
     que matcheen alguna de sus keywords (case-insensitive, substring).
  3. Si no matchea nada, se usa el bot default del owner del team
     (trigger_type='default').
  4. Si no hay default, devuelve None → el mensaje queda sin responder
     automáticamente (el agente humano lo atiende).

Futuro:
  - trigger_type='manual' solo entra si otro bot lo invoca (step tipo
    `invoke_bot`, no implementado en este sprint).
  - Ventanas horarias / días de la semana por bot.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import models
from . import llm_engine

logger = logging.getLogger(__name__)


def _keywords_for(bot: models.Bot) -> list[str]:
    if not bot.trigger_config:
        return []
    try:
        cfg = json.loads(bot.trigger_config)
    except (ValueError, TypeError):
        return []
    kws = cfg.get("keywords") if isinstance(cfg, dict) else None
    if not isinstance(kws, list):
        return []
    return [str(k).strip().lower() for k in kws if isinstance(k, (str, int))]


def get_active_session(
    db: Session, conversation_id: int
) -> Optional[models.BotSession]:
    """Devuelve la sesión activa (running/waiting) de la conversación, si existe."""
    return (
        db.query(models.BotSession)
        .filter(
            models.BotSession.conversation_id == conversation_id,
            models.BotSession.status.in_(
                [models.BOT_SESSION_RUNNING, models.BOT_SESSION_WAITING]
            ),
        )
        .order_by(models.BotSession.started_at.desc())
        .first()
    )


def ultima_sesion_cerrada(
    db: Session, conversation_id: int
) -> Optional[models.BotSession]:
    """La última sesión ya terminada de la conversación, si la hay."""
    return (
        db.query(models.BotSession)
        .filter(
            models.BotSession.conversation_id == conversation_id,
            models.BotSession.status.in_(
                [models.BOT_SESSION_FINISHED, models.BOT_SESSION_CANCELLED]
            ),
        )
        .order_by(models.BotSession.updated_at.desc())
        .first()
    )


def _dentro_de_la_ventana(
    session: models.BotSession, horas: float, ahora: Optional[datetime] = None
) -> bool:
    referencia = session.updated_at or session.finished_at or session.started_at
    if referencia is None:
        return False
    return (ahora or datetime.utcnow()) - referencia <= timedelta(hours=horas)


def resolve_bot_for_incoming_message(
    db: Session,
    *,
    team: models.Team,
    conversation_id: int,
    message_text: str,
) -> tuple[Optional[models.Bot], Optional[models.BotSession]]:
    """Decide qué bot (y sesión) atienden el mensaje entrante.

    Returns:
        (bot, session)
        - (bot, session) con session existente → continuar flujo
        - (bot, None) → arrancar sesión nueva
        - (None, None) → ningún bot aplica, que lo tome un humano
    """
    # 0) Sprint 19: si la conversación ya fue entregada a un asesor humano
    #    (handoff), el bot NO vuelve a intervenir — el humano conserva el chat.
    conv = db.query(models.Conversation).get(conversation_id)
    if conv is not None and (conv.assigned_to or "bot") != "bot":
        return None, None

    # 1) ¿Hay sesión activa? Sigue con ese bot.
    active = get_active_session(db, conversation_id)
    if active and active.bot:
        return active.bot, active

    # 1-bis) #377: no hay sesión activa, pero puede haber una **cerrada hace
    # poco**. Antes esto arrancaba una sesión nueva con el historial en blanco,
    # y el bot soltaba "Hola, ¿con quién tengo el gusto?" a alguien que llevaba
    # diez minutos hablando con él. Pasó cuatro veces en el chat del 20-ago-2026.
    ultima = ultima_sesion_cerrada(db, conversation_id)
    if ultima is not None and ultima.bot is not None:
        bot = ultima.bot
        cfg = llm_engine.config_de(bot)

        # a) Atajo determinista (B1): la conversación ya se cerró y lo que llega
        #    es pura cortesía. No se corre el bot — ni un turno de Bedrock, ni
        #    un mensaje de vuelta. Sin el contenido del mensaje en el log
        #    (regla de seguridad #1).
        if llm_engine.seguimiento_de(cfg) is not None and llm_engine.es_cortesia(
            message_text
        ):
            logger.info(
                "bot_router: cortesía tras el cierre, el bot no responde conv=%s bot=%s",
                conversation_id, bot.id,
            )
            return None, None

        # b) Retomar (B3): dentro de la ventana se revive ESA sesión, con su
        #    historial. `bot_runner` la vuelve a poner en marcha.
        horas = llm_engine.horas_para_retomar(cfg)
        if (
            horas is not None
            and getattr(bot, "status", "active") == "active"
            and _dentro_de_la_ventana(ultima, horas)
        ):
            logger.info(
                "bot_router: se retoma la sesión %s (conv=%s)", ultima.id, conversation_id
            )
            return bot, ultima

    # 2) Keyword match entre bots del owner del team.
    owner_id = team.owner_user_id
    bots = (
        db.query(models.Bot)
        .filter(
            models.Bot.user_id == owner_id,
            models.Bot.status == "active",
        )
        .all()
    )

    text_low = (message_text or "").lower()
    for bot in bots:
        if bot.trigger_type != models.BOT_TRIGGER_KEYWORD:
            continue
        for kw in _keywords_for(bot):
            if kw and kw in text_low:
                return bot, None

    # 3) Bot default.
    default_bot = next(
        (b for b in bots if b.trigger_type == models.BOT_TRIGGER_DEFAULT),
        None,
    )
    if default_bot:
        return default_bot, None

    # 4) Nada matchea.
    return None, None
