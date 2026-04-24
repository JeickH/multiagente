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
from typing import Optional

from sqlalchemy.orm import Session

from .. import models


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
    # 1) ¿Hay sesión activa? Sigue con ese bot.
    active = get_active_session(db, conversation_id)
    if active and active.bot:
        return active.bot, active

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
