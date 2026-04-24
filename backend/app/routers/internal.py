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
from ..services import bot_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal_secret(x_internal_secret: str | None = Header(default=None)) -> None:
    secret = os.getenv("INTERNAL_SECRET", "")
    if not secret:
        # En dev sin secreto, dejamos pasar para facilitar pruebas locales.
        return
    if x_internal_secret != secret:
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
