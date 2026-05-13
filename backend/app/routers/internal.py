"""Endpoints internos, protegidos con shared secret (no auth de usuario).

Se pensaron para ser invocados por cron / scheduler externo.

Uso:
    curl -X POST -H "X-Internal-Secret: $INTERNAL_SECRET" \
        https://<host>/internal/bot-scheduler/tick
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..dependencies import get_db
from ..services import bot_runner, campaign_sender

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal_secret(x_internal_secret: str | None = Header(default=None)) -> None:
    secret = os.getenv("INTERNAL_SECRET", "")
    if not secret:
        # En dev sin secreto, dejamos pasar para facilitar pruebas locales.
        return
    if x_internal_secret != secret:
        raise HTTPException(status_code=403, detail="forbidden")


def _require_internal_key(
    x_internal_key: str | None = Header(default=None),
    x_internal_secret: str | None = Header(default=None),
) -> None:
    """Auth para endpoints internos Sprint 13+.

    Acepta `X-Internal-Key` (nombre nuevo, doc Sprint 13) o `X-Internal-Secret`
    (legacy, scheduler de bots). El valor debe coincidir con `INTERNAL_API_KEY`
    o `INTERNAL_SECRET`. Si NINGUNO está seteado, dev-mode → pasa libre.
    """
    expected = os.getenv("INTERNAL_API_KEY") or os.getenv("INTERNAL_SECRET") or ""
    env = (os.getenv("APP_ENV", "development") or "").strip().lower()
    in_prod = env in ("production", "prod")
    if not expected:
        if in_prod:
            raise HTTPException(status_code=403, detail="forbidden")
        return
    provided = x_internal_key or x_internal_secret
    if provided != expected:
        raise HTTPException(status_code=403, detail="forbidden")


@router.post("/bot-scheduler/tick")
def bot_scheduler_tick(
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_secret),
    limit: int = 50,
):
    """Procesa hasta `limit` BotPendingAction vencidas.

    Pensado para dispararse cada 60s por un cron externo.
    Respuesta: conteo y lista breve de lo procesado.
    """
    now = datetime.utcnow()
    pending = (
        db.query(models.BotPendingAction)
        .filter(
            models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING,
            models.BotPendingAction.scheduled_at <= now,
        )
        .order_by(models.BotPendingAction.scheduled_at.asc())
        .limit(limit)
        .all()
    )

    processed = []
    for pa in pending:
        bot_runner.process_pending_action(db, pa)
        processed.append({"id": pa.id, "status": pa.status})

    return {
        "processed": len(processed),
        "items": processed,
        "tick_at": now.isoformat() + "Z",
    }


@router.post("/campaigns/tick")
def campaigns_tick(
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_key),
):
    """Procesa un tick de envío de campañas Sprint 13 (#162).

    Pensado para dispararse cada 60s por un cron externo. Llama a
    `campaign_sender.send_campaign_tick(db)` y devuelve un dict agregado
    sanitizado (sin PII).

    Errores inesperados se sanitizan: detalle completo a `logger.exception`,
    cliente recibe `{"error": "tick failed"}` con 500 (regla 6 de seguridad).
    """
    try:
        return campaign_sender.send_campaign_tick(db)
    except HTTPException:
        raise
    except Exception:
        logger.exception("campaigns_tick falló")
        raise HTTPException(status_code=500, detail="tick failed")
