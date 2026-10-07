"""Router de bots: decide qué bot debe atender un mensaje entrante.

Prioridad (Sprint 10):
  1. Si la conversación tiene una BotSession activa (running/waiting),
     sigue con ese bot. Así un flujo en curso no se interrumpe aunque el
     mensaje contenga keywords de otro bot.
  2. Si no hay sesión activa, se buscan bots con trigger_type='keyword'
     que matcheen alguna de sus keywords (case-insensitive, substring).
  3. Si no matchea nada, se usa el bot default del owner del team
     (trigger_type='default'). Si la cuenta tiene varios default activos con
     `reparto_pct`, se reparte entre ellos (A/B de guiones): ver
     `elegir_por_reparto` y `_bot_default`.
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
from typing import Dict, Optional, Sequence

from sqlalchemy import func, or_
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

    # 2) Keyword match entre bots del owner del team. Ordenados por id: sin
    #    ORDER BY, Postgres devuelve las filas en el orden que le convenga y,
    #    con dos bots que matchean o dos default, el que respondía dependía del
    #    plan de la consulta.
    owner_id = team.owner_user_id
    bots = (
        db.query(models.Bot)
        .filter(
            models.Bot.user_id == owner_id,
            models.Bot.status == "active",
        )
        .order_by(models.Bot.id)
        .all()
    )

    text_low = (message_text or "").lower()
    for bot in bots:
        if bot.trigger_type != models.BOT_TRIGGER_KEYWORD:
            continue
        for kw in _keywords_for(bot):
            if kw and kw in text_low:
                return bot, None

    # 3) Bot default (o el que toque por el reparto entre varios).
    defaults = [b for b in bots if b.trigger_type == models.BOT_TRIGGER_DEFAULT]
    default_bot = _bot_default(db, team=team, conv=conv, defaults=defaults)
    if default_bot:
        return default_bot, None

    # 4) Nada matchea.
    return None, None


# ---------------------------------------------------------------------------
# Reparto de conversaciones nuevas entre varios bots default (A/B de guiones)
# ---------------------------------------------------------------------------

def elegir_por_reparto(
    bots: Sequence[models.Bot], conteos: Dict[int, int]
) -> models.Bot:
    """Elige a quién le toca la próxima conversación. Función pura.

    Determinista, no aleatoria: con pocas conversaciones el azar se aleja
    mucho del porcentaje (un 50/50 puede dar 7/3 en diez), y entonces la
    comparación entre guiones se ensucia justo cuando hay menos datos. Aquí
    se elige al bot con mayor **déficit**: lo que le correspondería si la
    conversación que llega ya estuviera repartida, menos lo que ya recibió.

        total     = sum(conteos) + 1
        déficit_i = pct_i / sum_pct * total - conteo_i

    Empate → el de menor id (el original, en una variante recién creada).

    `bots` son los que están en el reparto (pct > 0); `conteos` es
    {bot_id: conversaciones asignadas desde el reparto vigente}.
    """
    if not bots:
        raise ValueError("elegir_por_reparto: no hay bots en el reparto")
    suma_pct = sum(int(b.reparto_pct or 0) for b in bots)
    if suma_pct <= 0:
        return min(bots, key=lambda b: b.id)
    total = sum(int(conteos.get(b.id, 0)) for b in bots) + 1

    def _deficit(b: models.Bot) -> float:
        return int(b.reparto_pct or 0) / suma_pct * total - int(conteos.get(b.id, 0))

    # max por déficit; a igualdad, menor id (por eso el -id en la clave).
    # Redondeo a 9 decimales para que 0.7*10-7 vs 0.3*10-3 no se desempaten
    # por ruido de coma flotante.
    return max(bots, key=lambda b: (round(_deficit(b), 9), -b.id))


def _conteos_del_reparto(
    db: Session, *, team_id: int, en_reparto: Sequence[models.Bot]
) -> Dict[int, int]:
    """Conversaciones asignadas a cada bot del reparto vigente. UNA consulta.

    El conteo arranca en el `reparto_desde` más reciente: cambiar 100/0 a
    50/50 no debe mandarle al bot nuevo todo lo que "le debe" del reparto
    anterior. Filtrado también por `team_id` (los bots son del owner, pero un
    conteo nunca debe poder mezclar conversaciones de otra cuenta).
    """
    ids = [b.id for b in en_reparto]
    fechas = [b.reparto_desde for b in en_reparto if b.reparto_desde is not None]
    q = db.query(
        models.Conversation.bot_asignado_id, func.count(models.Conversation.id)
    ).filter(
        models.Conversation.team_id == team_id,
        models.Conversation.bot_asignado_id.in_(ids),
    )
    if fechas:
        q = q.filter(models.Conversation.bot_asignado_at >= max(fechas))
    return {
        int(bot_id): int(n)
        for bot_id, n in q.group_by(models.Conversation.bot_asignado_id).all()
    }


def _bot_default(
    db: Session,
    *,
    team: models.Team,
    conv: Optional[models.Conversation],
    defaults: Sequence[models.Bot],
) -> Optional[models.Bot]:
    """Paso 3 del router: qué bot default atiende.

    `defaults` llega ya filtrado (owner, activos, trigger default) y ordenado
    por id. Sin ningún bot con porcentaje, todo queda como siempre: el de
    menor id, sin escribir nada en la conversación.
    """
    if not defaults:
        return None
    en_reparto = [b for b in defaults if int(b.reparto_pct or 0) > 0]
    if not en_reparto or conv is None:
        return defaults[0]

    por_id = {b.id: b for b in en_reparto}

    # Pegajoso: si vuelve, lo atiende el mismo guion. Solo vale si ese bot
    # sigue en el reparto (del owner, activo, default y pct > 0 — es decir,
    # está en `en_reparto`); si se pausó o quedó en 0 %, se reasigna.
    anterior = conv.bot_asignado_id
    if anterior is not None and anterior in por_id:
        return por_id[anterior]

    conteos = _conteos_del_reparto(db, team_id=team.id, en_reparto=en_reparto)
    elegido = elegir_por_reparto(en_reparto, conteos)

    # Compare-and-set: dos mensajes del mismo contacto que llegan a la vez no
    # deben quedar con bots distintos. Solo escribe si nadie asignó entre la
    # lectura y ahora; si otro proceso ganó, se usa el que quedó.
    ahora = datetime.utcnow()
    filas = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conv.id,
            or_(
                models.Conversation.bot_asignado_id.is_(None),
                models.Conversation.bot_asignado_id == anterior,
            )
            if anterior is not None
            else models.Conversation.bot_asignado_id.is_(None),
        )
        .update(
            {
                models.Conversation.bot_asignado_id: elegido.id,
                models.Conversation.bot_asignado_at: ahora,
            },
            synchronize_session=False,
        )
    )
    db.flush()
    db.refresh(conv)
    if not filas:
        ganador = por_id.get(conv.bot_asignado_id)
        logger.info(
            "bot_router: reparto ya resuelto por otro proceso conv=%s bot=%s",
            conv.id, conv.bot_asignado_id,
        )
        return ganador or elegido

    # Sin el contenido del mensaje (regla de seguridad #1).
    logger.info(
        "bot_router: reparto conv=%s bot=%s (antes=%s) conteos=%s",
        conv.id, elegido.id, anterior, conteos,
    )
    return elegido
