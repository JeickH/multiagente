"""Webhook de Twilio WhatsApp (Sprint 18).

Endpoints:
  - POST /twilio/webhook  → mensajes entrantes (dispara el pipeline de bots).
  - POST /twilio/status   → callbacks de estado (correlaciona campañas).

Twilio envía `application/x-www-form-urlencoded` y firma cada request con el
header **`X-Twilio-Signature`** (HMAC-SHA1 base64 sobre `url + params ordenados`
usando el Auth Token). Verificación **fail-closed en producción** (regla de
seguridad #5): si falta el Auth Token o la firma en prod → 403. En desarrollo se
permite fail-open con `logger.warning`.

Notas de despliegue:
  - Detrás de API Gateway, `request.url` puede no coincidir con la URL pública
    que firmó Twilio. Configurar `TWILIO_WEBHOOK_BASE_URL`
    (p.ej. `https://api.glomabeauty.com`) para reconstruir la URL exacta.
  - Mientras no haya cuenta Twilio conectada, `TWILIO_SANDBOX=1` mantiene el
    envío simulado; estos webhooks quedan listos para el día del cutover.

Reglas aplicadas: #1 (no loggear PII/tokens), #5 (webhook fail-closed), #6
(errores sanitizados; 200 a Twilio para no entrar en bucle de reintentos).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from datetime import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .. import crud, models
from ..dependencies import get_db
from ..services import bot_router as bot_router_svc
from ..services import bot_runner
from ..services.messaging import twilio_adapter

logger = logging.getLogger("twilio_webhook")

router = APIRouter(prefix="/twilio", tags=["twilio"])

# Funnel de estados (idéntico a meta_webhook): sólo avanzamos si el nuevo rank
# es estrictamente mayor. failed/skipped son terminales al nivel de 'sent'.
_STATUS_RANK: Dict[str, int] = {
    "queued": 0,
    "sending": 1,
    "sent": 2,
    "delivered": 3,
    "read": 4,
    "failed": 2,
    "skipped": 2,
}
_IN_FLIGHT = ("queued", "sending")


def _is_production() -> bool:
    env = (os.getenv("APP_ENV", "development") or "").strip().lower()
    return env in ("production", "prod")


def _public_url(request: Request) -> str:
    """URL exacta que Twilio usó para firmar (respeta base override)."""
    base_url = os.getenv("TWILIO_WEBHOOK_BASE_URL")
    if base_url:
        return f"{base_url.rstrip('/')}{request.url.path}"
    return str(request.url)


def _verify_signature(url: str, params: Dict[str, str], signature: str) -> bool:
    """Valida `X-Twilio-Signature`. Fail-closed en producción (regla #5)."""
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    in_prod = _is_production()

    if not token:
        if in_prod:
            logger.error("webhook.twilio fail-closed: TWILIO_AUTH_TOKEN ausente en producción")
            return False
        logger.warning("FAIL-OPEN: firma Twilio omitida — sólo seguro en dev (sin TWILIO_AUTH_TOKEN)")
        return True

    if not signature:
        if in_prod:
            logger.error("webhook.twilio fail-closed: firma ausente en producción")
        return False

    # Twilio: HMAC-SHA1 sobre url + concatenación de (clave+valor) ordenada por clave.
    payload = url
    for key in sorted(params):
        payload += key + params[key]
    digest = hmac.new(token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature)


def process_twilio_status(db: Session, form: Dict[str, str]) -> bool:
    """Correlaciona un callback de estado de Twilio con un CampaignRecipient.

    Devuelve True si el `MessageSid` pertenece a una campaña y se procesó.
    Correlación por `provider_message_id` (columna agnóstica, Sprint 18).
    """
    norm = twilio_adapter.parse_status(form)
    if norm is None:
        return False

    recipient = (
        db.query(models.CampaignRecipient)
        .filter(models.CampaignRecipient.provider_message_id == norm.message_id)
        .first()
    )
    if recipient is None:
        return False

    now = datetime.utcnow()
    advanced = False
    current = _STATUS_RANK.get(recipient.status, 0)
    incoming = _STATUS_RANK.get(norm.status, 0)

    if incoming > current:
        recipient.status = norm.status
        if norm.status == "sent" and recipient.sent_at is None:
            recipient.sent_at = now
        elif norm.status == "delivered":
            recipient.delivered_at = now
            if recipient.sent_at is None:
                recipient.sent_at = now
        elif norm.status == "read":
            recipient.read_at = now
            if recipient.sent_at is None:
                recipient.sent_at = now
        elif norm.status == "failed":
            recipient.failed_at = now
            if norm.error_code:
                recipient.error_code = str(norm.error_code)[:40]
        advanced = True

    # Evento idempotente (dedupe por índice parcial uq_events_dedupe).
    stmt = (
        pg_insert(models.CampaignEvent)
        .values(
            campaign_id=recipient.campaign_id,
            recipient_id=recipient.id,
            event_type=norm.status,
            payload_json=norm.raw,
            meta_message_id=norm.message_id,
            created_at=now,
        )
        .on_conflict_do_nothing()
    )
    db.execute(stmt)

    if advanced:
        still_pending = (
            db.query(models.CampaignRecipient)
            .filter(
                models.CampaignRecipient.campaign_id == recipient.campaign_id,
                models.CampaignRecipient.status.in_(_IN_FLIGHT),
            )
            .first()
        )
        if still_pending is None:
            camp = (
                db.query(models.Campaign)
                .filter(models.Campaign.id == recipient.campaign_id)
                .first()
            )
            if camp is not None and camp.status != models.CAMPAIGN_STATUS_COMPLETED:
                camp.status = models.CAMPAIGN_STATUS_COMPLETED
                camp.completed_at = now

    db.commit()
    logger.info(
        "webhook.twilio status recipient_id=%s campaign_id=%s event=%s advanced=%s",
        recipient.id,
        recipient.campaign_id,
        norm.status,
        advanced,
    )
    return True


def _resolve_account_by_to(db: Session, to_wa_id: str) -> Optional[models.MetaAccount]:
    """Resuelve la cuenta Twilio por el número destino (el de la marca).

    Compara sólo dígitos para tolerar variaciones ('whatsapp:+57...', '+57...').
    """
    digits = "".join(ch for ch in (to_wa_id or "") if ch.isdigit())
    if not digits:
        return None
    for acc in (
        db.query(models.MetaAccount)
        .filter(models.MetaAccount.provider == "twilio")
        .all()
    ):
        acc_digits = "".join(ch for ch in (acc.twilio_from or "") if ch.isdigit())
        if acc_digits and acc_digits == digits:
            return acc
    return None


@router.post("/status")
async def receive_status(request: Request, db: Session = Depends(get_db)):
    form = dict((await request.form()))
    signature = request.headers.get("X-Twilio-Signature", "")
    if not _verify_signature(_public_url(request), form, signature):
        return PlainTextResponse("Firma inválida", status_code=403 if _is_production() else 401)

    try:
        handled = process_twilio_status(db, form)
        if not handled:
            logger.info("webhook.twilio status_legacy sid=%s", form.get("MessageSid"))
    except Exception:
        logger.exception("webhook.twilio error procesando status")
    # 200 vacío: Twilio no reintenta.
    return PlainTextResponse("", status_code=200)


@router.post("/webhook")
async def receive_inbound(request: Request, db: Session = Depends(get_db)):
    form = dict((await request.form()))
    signature = request.headers.get("X-Twilio-Signature", "")
    if not _verify_signature(_public_url(request), form, signature):
        return PlainTextResponse("Firma inválida", status_code=403 if _is_production() else 401)

    try:
        norm = twilio_adapter.parse_inbound(form)
        if norm is None:
            return PlainTextResponse("", status_code=200)

        account = _resolve_account_by_to(db, norm.to_wa_id)
        if account is None or account.team is None:
            # Aún sin cuenta Twilio conectada a este número: no-op (queda listo
            # para el cutover). No se loggea el número en limpio.
            logger.info("webhook.twilio inbound sin cuenta asociada — ignorado")
            return PlainTextResponse("", status_code=200)

        content = norm.text or f"[{norm.message_type}]"
        conv = crud.get_or_create_conversation(
            db,
            team_id=account.team_id,
            contact_wa_id=norm.from_wa_id,
            contact_name=None,
        )

        # Dedupe por message_id (Twilio puede reintentar).
        if norm.message_id and (
            db.query(models.Message)
            .filter(models.Message.meta_message_id == norm.message_id)
            .first()
        ):
            logger.info("webhook.twilio dedupe inbound conversation_id=%s", conv.id)
            return PlainTextResponse("", status_code=200)

        crud.add_message(
            db,
            conv,
            direction="inbound",
            content=content,
            message_type=norm.message_type,
            meta_message_id=norm.message_id,
            status="received",
        )

        bot, session = bot_router_svc.resolve_bot_for_incoming_message(
            db,
            team=account.team,
            conversation_id=conv.id,
            message_text=content,
        )
        if bot is not None:
            try:
                bot_runner.run_turn(
                    db,
                    bot=bot,
                    conversation=conv,
                    session=session,
                    user_input=content if session is not None else None,
                    meta_account=account,
                )
            except Exception:
                logger.exception("bot_runner falló (twilio) bot=%s conv=%s", bot.id, conv.id)
    except Exception:
        logger.exception("Error procesando webhook Twilio")

    return PlainTextResponse("", status_code=200)
