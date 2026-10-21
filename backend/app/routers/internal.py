"""Endpoints internos, protegidos con shared secret (no auth de usuario).

Se pensaron para ser invocados por cron / scheduler externo.

Uso:
    curl -X POST -H "X-Internal-Key: $INTERNAL_API_KEY" \
        https://<host>/internal/bot-scheduler/tick

Todos van por `_require_internal_key`: fail-closed en producción (#642).
"""
from __future__ import annotations

import hmac
import logging
import os
from datetime import datetime

import threading
import time

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal
from ..dependencies import get_db
from ..services import bot_runner, campaign_sender, limpieza_demos
from ..services import suscripciones as svc_suscripciones

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])


def _require_internal_key(
    x_internal_key: str | None = Header(default=None),
    x_internal_secret: str | None = Header(default=None),
) -> None:
    """Auth para endpoints internos Sprint 13+.

    Acepta `X-Internal-Key` (nombre nuevo, doc Sprint 13) o `X-Internal-Secret`
    (legacy, scheduler de bots). El valor debe coincidir con `INTERNAL_API_KEY`
    o `INTERNAL_SECRET`. Si NINGUNO está seteado: en producción (`APP_ENV`
    production/prod) → 403; en desarrollo pasa libre.

    #642: el tick usaba otro guardia que solo leía `INTERNAL_SECRET` (que no
    existe en la task-def) y pasaba libre si faltaba: quedaba abierto en
    producción. La Lambda `multiagente-bot-tick` manda la llave de
    `/multiagente/prod/INTERNAL_API_KEY` en las dos cabeceras.
    """
    expected = os.getenv("INTERNAL_API_KEY") or os.getenv("INTERNAL_SECRET") or ""
    env = (os.getenv("APP_ENV", "development") or "").strip().lower()
    in_prod = env in ("production", "prod")
    if not expected:
        if in_prod:
            raise HTTPException(status_code=403, detail="forbidden")
        return
    provided = x_internal_key or x_internal_secret or ""
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="forbidden")


# ---------------------------------------------------------------------------
# Limpieza de bots de demo inactivos (#638): enganchada al tick, a lo sumo una
# vez por hora y DESPUÉS de responder (BackgroundTasks), para no alargarlo.
# ---------------------------------------------------------------------------

_LIMPIEZA_CADA_S = 3600.0
_ultima_limpieza: float | None = None
_limpieza_lock = threading.Lock()


def _toca_limpieza(ahora: float) -> bool:
    """Reserva el turno de la limpieza si pasó una hora desde la última. La
    guardia es en memoria: el backend corre como una sola task, y la limpieza
    es idempotente si un reinicio la adelanta."""
    global _ultima_limpieza
    with _limpieza_lock:
        if _ultima_limpieza is not None and ahora - _ultima_limpieza < _LIMPIEZA_CADA_S:
            return False
        _ultima_limpieza = ahora
        return True


def _correr_limpieza_demos() -> None:
    db = SessionLocal()
    try:
        limpieza_demos.limpiar_bots_demo_inactivos(db)
    except Exception:  # noqa: BLE001 — nunca tumba el tick
        logger.exception("limpieza_demos: la corrida del tick falló")
        db.rollback()
    finally:
        db.close()


@router.post("/bot-scheduler/tick")
def bot_scheduler_tick(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_key),
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

    limpieza = _toca_limpieza(time.monotonic())
    if limpieza:
        background.add_task(_correr_limpieza_demos)

    return {
        "processed": len(processed),
        "items": processed,
        "tick_at": now.isoformat() + "Z",
        "limpieza_demos": limpieza,
    }


@router.post("/suscripciones/tick")
def suscripciones_tick(
    db: Session = Depends(get_db),
    _: None = Depends(_require_internal_key),
    limit: int = 50,
):
    """Cobra las suscripciones vencidas y reconcilia los cobros colgados.

    Va **aparte del tick de bots** a propósito: mezclar los dos haría que un
    error cobrando le tumbara el turno al bot de un cliente, y son cosas que
    fallan por motivos completamente distintos.

    No hace falta que corra cada minuto — una suscripción se cobra una vez al
    mes. Cada 5 minutos deja el cobro dentro de los 5 minutos de la hora que el
    cliente eligió, que es más precisión de la que nadie va a notar.

    Respuesta agregada y sin PII: solo conteos.
    """
    try:
        return svc_suscripciones.tick(db, limite=limit)
    except HTTPException:
        raise
    except Exception:
        logger.exception("suscripciones_tick falló")
        raise HTTPException(status_code=500, detail="tick failed")


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
