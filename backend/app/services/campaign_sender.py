"""Servicio de envío de campañas WhatsApp (Sprint 13 #162).

Procesa campañas con `status='scheduled' AND scheduled_at <= now()` y campañas
ya en `running` (caso de reinicio mid-flight). Por cada destinatario `queued`:

1. Re-lookup de `contacts.opt_in` (S13-003 fail-closed): si el contacto cambió
   a `opt_in=False` entre encolar y enviar, marca `status='skipped'` con
   `error_code='opt_out_at_send'` y registra `campaign_events(event_type='sync_warning')`.
2. Transición atómica `queued → sending` con `WHERE status='queued'` para
   idempotencia ante reinicio del worker (otro tick que esté corriendo no
   re-envía).
3. POST a Meta (`services/meta_whatsapp.send_template_message`) con rate-limit
   token-bucket por `meta_account_id` (S13-002, default 10 msg/s configurable
   por env `META_RATE_LIMIT_RPS`) y retry exponencial con `tenacity` sobre
   errores 429 o códigos Meta 80007 / 131056.
4. En éxito: `status='sent'`, `meta_message_id=wamid`, `sent_at=now()` +
   evento `sent`.
5. En fallo permanente: `status='failed'`, `error_code=meta_code`, `failed_at=now()`
   + evento `failed`.

Modo sandbox: si `META_SANDBOX=1` o `MetaAccount.encrypted_access_token` es
NULL, se simula la respuesta con `wamid.local-<uuid>` (no llama a Meta). Útil
para desarrollo local y QA.

Reglas de seguridad aplicadas:
- NUNCA loggear `phone_e164` en bruto. Sólo `recipient_id`, `campaign_id` y
  últimos 4 dígitos enmascarados via `_mask_phone()`.
- NUNCA loggear el access_token descifrado (queda únicamente en el scope
  efímero de `services.meta_whatsapp._headers`).
- Errores al cliente: el endpoint `/internal/campaigns/tick` retorna sólo
  agregados (`recipients_sent`, `recipients_failed`); el detalle de cada
  error va a `logger.exception` y al `CampaignEvent.payload_json`.
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .. import models
from . import messaging, meta_whatsapp


logger = logging.getLogger(__name__)


# ─── Configuración (env-driven) ───────────────────────────────────────────────

MAX_BATCH_PER_TICK = int(os.getenv("CAMPAIGN_SENDER_BATCH", "200"))
"""Máximo de recipients procesados por tick por campaña. Default 200 (config
env CAMPAIGN_SENDER_BATCH). Limita el blast-radius por tick y permite que el
scheduler externo (cron de 60s) avance varias campañas en paralelo."""

DEFAULT_RATE_LIMIT_RPS = float(os.getenv("META_RATE_LIMIT_RPS", "10"))
"""Tope de mensajes por segundo por `meta_account_id` (S13-002). Default 10
(conservador). Token-bucket en memoria, lock-protected, no cross-process: si
hay varias replicas del backend, se debe migrar a Redis."""

SANDBOX_MODE = os.getenv("META_SANDBOX", "1") == "1"
"""Si está activo o si la MetaAccount no tiene token cifrado, se simula la
respuesta Meta con `wamid.local-<uuid>`. En producción debe ser 0."""

# Códigos de error Meta tratados como retryables (rate limit / temporal failure).
_META_RETRYABLE_CODES = {80007, 131056}
"""80007 = rate limit hit; 131056 = (pair) rate limit. Ambos son retryables
con backoff (ver S13-002)."""


# ─── Utilidades ───────────────────────────────────────────────────────────────


def _mask_phone(phone_e164: Optional[str]) -> str:
    """Enmascara un número E.164 para logging. `+573001234567` → `+57***4567`."""
    if not phone_e164 or len(phone_e164) < 6:
        return "<redacted>"
    return f"{phone_e164[:3]}***{phone_e164[-4:]}"


# ─── Token-bucket rate-limiter (en memoria, por meta_account_id) ──────────────


class _TokenBucket:
    """Token-bucket simple, thread-safe, en memoria.

    No cross-process. Suficiente para 1 task ECS Fargate (el deploy actual).
    Si se escala horizontalmente se debe migrar a Redis (`redis-py` + Lua
    script atómico).
    """

    def __init__(self, rate_per_sec: float, capacity: Optional[float] = None):
        self.rate = float(rate_per_sec)
        self.capacity = float(capacity if capacity is not None else rate_per_sec)
        self._tokens = self.capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        """Bloquea hasta que haya 1 token disponible o expire `timeout`.

        Devuelve True si se adquirió, False si expiró. En este servicio
        siempre esperamos (no bypaseamos el rate-limit), por lo que solo
        devuelve False ante un timeout muy largo (caso anómalo).
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                if elapsed > 0:
                    self._tokens = min(
                        self.capacity, self._tokens + elapsed * self.rate
                    )
                    self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
                # Calcula espera mínima hasta tener 1 token.
                needed = 1.0 - self._tokens
                wait = needed / self.rate if self.rate > 0 else timeout
            if time.monotonic() + wait > deadline:
                return False
            time.sleep(min(wait, 0.5))


_buckets: Dict[int, _TokenBucket] = {}
_buckets_lock = threading.Lock()


def _get_bucket(meta_account_id: int, rate: float = DEFAULT_RATE_LIMIT_RPS) -> _TokenBucket:
    with _buckets_lock:
        bucket = _buckets.get(meta_account_id)
        if bucket is None:
            bucket = _TokenBucket(rate_per_sec=rate, capacity=rate)
            _buckets[meta_account_id] = bucket
        return bucket


# ─── Cliente Meta con backoff exponencial ─────────────────────────────────────


@dataclass
class _SendResult:
    success: bool
    meta_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    payload: Optional[dict] = None
    permanent_failure: bool = False


def _is_retryable_meta_error(exc: BaseException) -> bool:
    """Retry si el error del proveedor es transitorio (429 / rate-limit / 5xx).

    Sprint 18: acepta `messaging.MessagingError` (cubre Meta y Twilio); cada
    adaptador ya marca `retryable`. Se conservan los códigos Meta por robustez.
    """
    if not isinstance(exc, messaging.MessagingError):
        return False
    if getattr(exc, "retryable", False):
        return True
    if exc.status_code == 429:
        return True
    return getattr(exc, "provider_code", None) in _META_RETRYABLE_CODES


def _send_template_with_retry(
    account: models.MetaAccount,
    to_wa_id: str,
    template_name: str,
    language_code: str,
) -> tuple[str, dict]:
    """Envía por el proveedor de la cuenta con 3 retries y backoff exponencial.

    Las excepciones permanentes (4xx no retryables) burbujean sin reintentar.
    """

    @retry(
        retry=retry_if_exception(_is_retryable_meta_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=8.0, jitter=0.5),
        reraise=True,
    )
    def _attempt() -> tuple[str, dict]:
        return messaging.send_template(
            account, to_wa_id, template_name, language_code=language_code
        )

    return _attempt()


def _send_one(
    account: models.MetaAccount,
    template: models.WhatsappTemplate,
    to_wa_id: str,
) -> _SendResult:
    """Envía un mensaje por el proveedor de la cuenta (Meta o Twilio) o simula.

    Sandbox cuando el adaptador del proveedor lo indique:
    - Meta: `META_SANDBOX=1` o `encrypted_access_token` NULL.
    - Twilio: `TWILIO_SANDBOX=1` o credenciales incompletas.
    """
    if messaging.is_sandbox(account):
        # No tocar al proveedor; simular id local. Cumple S13-002 (rate-limit
        # local también aplica para coherencia de pruebas de carga).
        return _SendResult(
            success=True,
            meta_message_id=f"wamid.local-{uuid.uuid4().hex[:24]}",
            payload={"sandbox": True},
        )

    try:
        message_id, payload = _send_template_with_retry(
            account=account,
            to_wa_id=to_wa_id,
            template_name=template.name,
            language_code=template.language,
        )
        if not message_id:
            return _SendResult(
                success=False,
                error_code="provider_no_message_id",
                error_message="El proveedor no devolvió message id",
                payload=payload,
                permanent_failure=True,
            )
        return _SendResult(success=True, meta_message_id=message_id, payload=payload)
    except messaging.MessagingError as exc:
        # Tras retries, fallido permanente. Mensaje genérico para el evento; el
        # detalle sanitizado queda en el payload y en logger.exception.
        code = getattr(exc, "provider_code", None)
        provider = getattr(exc, "provider", "provider") or "provider"
        return _SendResult(
            success=False,
            error_code=f"{provider}_{code}" if code else f"{provider}_http_{exc.status_code}",
            error_message="El proveedor rechazó el envío",
            payload=exc.payload,
            permanent_failure=True,
        )
    except RetryError as exc:
        # Tenacity agotó retries sobre error retryable; tratamos como fallo
        # temporal pero marcamos failed (re-intentaríamos en el próximo tick
        # si dejáramos el recipient en 'sending' indefinidamente, pero eso
        # bloquearía el progreso → preferimos failed con error_code dedicado).
        logger.exception(
            "Sender: retries agotados (rate-limit/429) campaign template=%s",
            template.id,
        )
        return _SendResult(
            success=False,
            error_code="meta_retry_exhausted",
            error_message="Reintentos agotados",
            permanent_failure=True,
        )
    except Exception:
        logger.exception(
            "Sender: error inesperado al postear a Meta template=%s", template.id
        )
        return _SendResult(
            success=False,
            error_code="meta_unexpected_error",
            error_message="Error inesperado",
            permanent_failure=True,
        )


# ─── Tick principal ───────────────────────────────────────────────────────────


def _transition_to_sending(db: Session, recipient_id: int) -> bool:
    """Transición atómica `queued → sending` con `WHERE status='queued'`.

    Si rowcount=0 significa que otro proceso ya tomó el recipient — debemos
    saltarlo (idempotencia ante reinicios o concurrencia, S13 spec).
    """
    res = db.execute(
        text(
            "UPDATE campaign_recipients SET status='sending' "
            "WHERE id=:rid AND status='queued'"
        ),
        {"rid": recipient_id},
    )
    db.commit()
    return res.rowcount == 1


def _mark_sent(
    db: Session, recipient_id: int, meta_message_id: str, when: datetime
) -> None:
    # Sprint 18: se persiste el id en ambas columnas — `meta_message_id`
    # (correlación legacy del webhook Meta) y `provider_message_id` (correlación
    # agnóstica que usa el webhook de Twilio).
    db.execute(
        text(
            "UPDATE campaign_recipients "
            "SET status='sent', meta_message_id=:wamid, "
            "provider_message_id=:wamid, sent_at=:ts "
            "WHERE id=:rid"
        ),
        {"rid": recipient_id, "wamid": meta_message_id, "ts": when},
    )


def _mark_failed(
    db: Session, recipient_id: int, error_code: str, when: datetime
) -> None:
    db.execute(
        text(
            "UPDATE campaign_recipients "
            "SET status='failed', error_code=:ec, failed_at=:ts "
            "WHERE id=:rid"
        ),
        {"rid": recipient_id, "ec": (error_code or "unknown")[:40], "ts": when},
    )


def _mark_skipped(db: Session, recipient_id: int, error_code: str) -> None:
    db.execute(
        text(
            "UPDATE campaign_recipients "
            "SET status='skipped', error_code=:ec "
            "WHERE id=:rid"
        ),
        {"rid": recipient_id, "ec": (error_code or "unknown")[:40]},
    )


def _insert_event(
    db: Session,
    campaign_id: int,
    recipient_id: Optional[int],
    event_type: str,
    payload: Optional[dict] = None,
    meta_message_id: Optional[str] = None,
) -> None:
    """Inserta CampaignEvent. NO loggea `payload` (puede contener PII)."""
    event = models.CampaignEvent(
        campaign_id=campaign_id,
        recipient_id=recipient_id,
        event_type=event_type,
        payload_json=payload,
        meta_message_id=meta_message_id,
    )
    db.add(event)


def _campaign_is_complete(db: Session, campaign_id: int) -> bool:
    """True si NO quedan recipients en estado no-terminal."""
    row = db.execute(
        text(
            "SELECT COUNT(*) AS pending FROM campaign_recipients "
            "WHERE campaign_id=:cid AND status IN ('queued','sending')"
        ),
        {"cid": campaign_id},
    ).first()
    return (row.pending if row else 0) == 0


def send_campaign_tick(db: Session) -> dict:
    """Procesa un tick de envío de campañas.

    Selecciona campañas con `status='scheduled' AND scheduled_at <= now()`
    o `status='running'` (resuming). Por cada una, envía hasta
    `MAX_BATCH_PER_TICK` recipients en `queued`.

    Devuelve un dict agregado (sin PII):
        {
          "campaigns_processed": int,
          "recipients_sent": int,
          "recipients_failed": int,
          "recipients_skipped": int,
          "errors": [{"campaign_id": int, "error_code": str}, ...],
        }
    """
    now = datetime.utcnow()
    result = {
        "campaigns_processed": 0,
        "recipients_sent": 0,
        "recipients_failed": 0,
        "recipients_skipped": 0,
        "errors": [],
    }

    # 1) Selecciona campañas elegibles. `running` se incluye para reanudar
    #    campañas que quedaron a mitad por reinicio del worker.
    campaigns = (
        db.query(models.Campaign)
        .filter(
            (
                (models.Campaign.status == "scheduled")
                & (
                    (models.Campaign.scheduled_at.is_(None))
                    | (models.Campaign.scheduled_at <= now)
                )
            )
            | (models.Campaign.status == "running")
        )
        .order_by(models.Campaign.scheduled_at.asc().nullslast(), models.Campaign.id.asc())
        .all()
    )

    for campaign in campaigns:
        result["campaigns_processed"] += 1

        # Transicionar a 'running' la primera vez.
        if campaign.status == "scheduled":
            db.execute(
                text(
                    "UPDATE campaigns SET status='running', started_at=COALESCE(started_at, :ts) "
                    "WHERE id=:cid AND status='scheduled'"
                ),
                {"cid": campaign.id, "ts": now},
            )
            db.commit()
            db.refresh(campaign)

        # Carga la MetaAccount + Template (necesarias para el POST a Meta).
        account: models.MetaAccount = campaign.meta_account
        template: models.WhatsappTemplate = campaign.template
        if account is None or template is None:
            logger.error(
                "Sender: campaign id=%s sin meta_account o template; marcando failed",
                campaign.id,
            )
            db.execute(
                text(
                    "UPDATE campaigns SET status='failed', completed_at=:ts WHERE id=:cid"
                ),
                {"cid": campaign.id, "ts": now},
            )
            db.commit()
            result["errors"].append(
                {"campaign_id": campaign.id, "error_code": "missing_account_or_template"}
            )
            continue

        bucket = _get_bucket(account.id, DEFAULT_RATE_LIMIT_RPS)

        # 2) Selecciona el batch de recipients aún `queued`.
        recipients = (
            db.query(models.CampaignRecipient)
            .filter(
                models.CampaignRecipient.campaign_id == campaign.id,
                models.CampaignRecipient.status == "queued",
            )
            .order_by(models.CampaignRecipient.id.asc())
            .limit(MAX_BATCH_PER_TICK)
            .all()
        )

        for rcp in recipients:
            # 2a) Opt-in fail-closed (S13-003): re-lookup en contacts.
            contact = (
                db.query(models.Contact)
                .filter(models.Contact.id == rcp.contact_id)
                .first()
            )
            if contact is None or not bool(contact.opt_in):
                _mark_skipped(db, rcp.id, "opt_out_at_send")
                _insert_event(
                    db,
                    campaign_id=campaign.id,
                    recipient_id=rcp.id,
                    event_type="sync_warning",
                    payload={"reason": "opt_out_at_send", "contact_id": rcp.contact_id},
                )
                db.commit()
                result["recipients_skipped"] += 1
                logger.info(
                    "sender.skipped campaign_id=%s recipient_id=%s reason=opt_out_at_send",
                    campaign.id,
                    rcp.id,
                )
                continue

            # 2b) Idempotencia: queued → sending con WHERE status='queued'.
            took = _transition_to_sending(db, rcp.id)
            if not took:
                logger.info(
                    "sender.skip_taken_by_other campaign_id=%s recipient_id=%s",
                    campaign.id,
                    rcp.id,
                )
                continue

            # 2c) Rate-limit token-bucket por meta_account_id.
            bucket.acquire(timeout=60.0)

            # 2d) Envío (real o sandbox). Meta usa wa_id SIN '+' por convención
            #     del Graph API; quitamos el '+' si viene.
            to_wa_id = rcp.phone_e164.lstrip("+") if rcp.phone_e164 else ""
            send_res = _send_one(account, template, to_wa_id)

            send_ts = datetime.utcnow()
            if send_res.success:
                try:
                    _mark_sent(db, rcp.id, send_res.meta_message_id, send_ts)
                    _insert_event(
                        db,
                        campaign_id=campaign.id,
                        recipient_id=rcp.id,
                        event_type="sent",
                        payload=send_res.payload,
                        meta_message_id=send_res.meta_message_id,
                    )
                    db.commit()
                    result["recipients_sent"] += 1
                except Exception:
                    db.rollback()
                    logger.exception(
                        "sender.commit_failed campaign_id=%s recipient_id=%s",
                        campaign.id,
                        rcp.id,
                    )
                    result["recipients_failed"] += 1
            else:
                _mark_failed(db, rcp.id, send_res.error_code or "unknown", send_ts)
                _insert_event(
                    db,
                    campaign_id=campaign.id,
                    recipient_id=rcp.id,
                    event_type="failed",
                    payload={
                        "error_code": send_res.error_code,
                        "error_message": send_res.error_message,
                    },
                )
                db.commit()
                result["recipients_failed"] += 1
                result["errors"].append(
                    {
                        "campaign_id": campaign.id,
                        "error_code": send_res.error_code or "unknown",
                    }
                )

        # 3) ¿Campaign completa? Sólo si NO quedan queued/sending.
        if _campaign_is_complete(db, campaign.id):
            db.execute(
                text(
                    "UPDATE campaigns SET status='completed', completed_at=:ts "
                    "WHERE id=:cid AND status='running'"
                ),
                {"cid": campaign.id, "ts": datetime.utcnow()},
            )
            db.commit()

    return result
