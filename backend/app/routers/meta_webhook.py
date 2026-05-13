"""
Webhook de Meta WhatsApp Cloud API.

Configuración en panel Meta:
  - Callback URL: https://<host>/meta/webhook
  - Verify token: METAS_WEBHOOK_VERIFY_TOKEN del .env
  - Suscripción al campo: messages

Para probar en local se necesita una URL pública (ej: ngrok http 8000).

Sprint 13 #163: extiende el handler con `process_status_event` para
correlacionar callbacks de Meta de mensajes salientes de campañas con
`CampaignRecipient` (`meta_message_id` UNIQUE) y registrar `CampaignEvent`
idempotentes vía `ON CONFLICT DO NOTHING` (índice parcial `uq_events_dedupe`
sobre `(meta_message_id, event_type) WHERE meta_message_id IS NOT NULL`).

Mitigaciones (`backend/docs/sprint13_security_review.md`):
  - **S13-004**: `_sanitize_payload_for_log` enmascara teléfonos E.164 antes
    de loggear; el payload bruto se persiste solo en BD (`campaign_events.
    payload_json`), nunca en logs.
  - **S13-005**: `_verify_signature` es **fail-closed obligatorio** en
    producción. Si `APP_ENV=production` y falta `META_APP_SECRET` o falta la
    firma → 403 sin procesar nada. En desarrollo se permite fail-open con
    `logger.warning` explícito.
"""
import copy
import os
import re
import hmac
import hashlib
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from dotenv import load_dotenv

from .. import models, crud
from ..dependencies import get_db
from ..services import bot_router as bot_router_svc
from ..services import bot_runner

load_dotenv()
logger = logging.getLogger("meta_webhook")

VERIFY_TOKEN = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "")
APP_SECRET = os.getenv("META_APP_SECRET", "")

router = APIRouter(prefix="/meta", tags=["meta"])


# ─── Constantes de mapeo de status (Sprint 13 #163) ──────────────────────
# Funnel: queued < sending < sent < delivered < read; failed/skipped/cancelled
# son terminales. Sólo avanzamos si el nuevo status tiene un rank estrictamente
# mayor (idempotencia + tolerancia a reordering de webhooks).
_STATUS_RANK: Dict[str, int] = {
    "queued": 0,
    "sending": 1,
    "sent": 2,
    "delivered": 3,
    "read": 4,
    # terminales: rank alto para que nunca se "regresen" a sent/delivered
    "failed": 99,
    "skipped": 99,
}

# Mapping de status Meta → status interno. Meta envía: sent, delivered, read,
# failed. Mantenemos el mismo nombre.
_META_TO_INTERNAL: Dict[str, str] = {
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
}

# Estados de un recipient que indican que la campaña aún está en vuelo.
_IN_FLIGHT_RECIPIENT_STATUSES = ("queued", "sending")


def _status_rank(status: str) -> int:
    """Rank del status en el funnel; estados desconocidos → -1 (no avanza)."""
    return _STATUS_RANK.get(status, -1)


# ─── S13-004: helpers para logging sin PII ──────────────────────────────
_PHONE_RE = re.compile(r"\+?\b[1-9]\d{6,18}\b")


def _mask_phone_str(value: str) -> str:
    """Enmascara teléfonos E.164 dentro de un string libre.

    Conserva los 3 primeros y los últimos 2 dígitos visibles para depurar
    sin filtrar PII completa.
    """

    def repl(m: re.Match) -> str:
        digits = m.group(0).lstrip("+")
        if len(digits) <= 5:
            return "***"
        return f"{digits[:3]}***{digits[-2:]}"

    return _PHONE_RE.sub(repl, value)


_PHONE_FIELD_KEYS = {
    "phone_e164",
    "phone",
    "from",
    "wa_id",
    "recipient_id",
    "display_phone",
    "display_phone_number",
}


def _sanitize_payload_for_log(payload: Any) -> Any:
    """Devuelve una copia profunda del payload con teléfonos enmascarados.

    Recorre dicts/lists; si la clave parece de teléfono o el valor matchea
    regex E.164, lo enmascara. Para no perder estructura, devolvemos un
    objeto del mismo shape. NO modifica el payload original.

    Se usa SOLO para logging; el payload completo sí va a BD
    (`campaign_events.payload_json`) por requerimiento de auditoría.
    """
    if isinstance(payload, dict):
        out: Dict[str, Any] = {}
        for k, v in payload.items():
            if isinstance(v, str) and (k in _PHONE_FIELD_KEYS or _PHONE_RE.search(v)):
                out[k] = _mask_phone_str(v)
            else:
                out[k] = _sanitize_payload_for_log(v)
        return out
    if isinstance(payload, list):
        return [_sanitize_payload_for_log(x) for x in payload]
    if isinstance(payload, str):
        return _mask_phone_str(payload)
    return payload


def _summarize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Resumen compacto sin PII para logging por defecto.

    Cuenta entries, messages, statuses; lista phone_number_ids (no PII).
    """
    entries = payload.get("entry", []) or []
    msg_count = 0
    status_count = 0
    phone_ids = set()
    for entry in entries:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            md = value.get("metadata", {}) or {}
            if md.get("phone_number_id"):
                phone_ids.add(md["phone_number_id"])
            msg_count += len(value.get("messages", []) or [])
            status_count += len(value.get("statuses", []) or [])
    return {
        "entries": len(entries),
        "messages": msg_count,
        "statuses": status_count,
        "phone_number_ids": sorted(phone_ids),
    }


# ─── S13-005: verificación de firma fail-closed en prod ──────────────────
def _is_production() -> bool:
    """True si APP_ENV indica entorno productivo.

    Acepta tanto `production` (convención del proyecto, ver `config.py`)
    como `prod` (alias defensivo).
    """
    env = (os.getenv("APP_ENV", "development") or "").strip().lower()
    return env in ("production", "prod")


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """Valida la firma X-Hub-Signature-256 enviada por Meta.

    S13-005: fail-closed obligatorio en producción.
      - prod + falta APP_SECRET → False (rechaza; misconfig que abriría
        la puerta a inyección de eventos falsos).
      - prod + falta firma → False.
      - dev + falta APP_SECRET → True (fail-open SOLO en dev) con WARN.
    """
    in_prod = _is_production()

    if not APP_SECRET:
        if in_prod:
            logger.error(
                "webhook.meta sig_check fail-closed: META_APP_SECRET ausente en producción"
            )
            return False
        logger.warning(
            "FAIL-OPEN: webhook signature skipped — only safe in dev "
            "(META_APP_SECRET no configurado)"
        )
        return True

    if not signature_header or not signature_header.startswith("sha256="):
        if in_prod:
            logger.error(
                "webhook.meta sig_check fail-closed: firma ausente o malformada en producción"
            )
        return False

    expected = (
        "sha256="
        + hmac.new(
            APP_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


@router.get("/webhook")
def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Endpoint de verificación que llama Meta al guardar la URL del webhook."""
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return int(hub_challenge) if hub_challenge and hub_challenge.isdigit() else hub_challenge
    raise HTTPException(status_code=403, detail="Verificación fallida")


# ─── Sprint 13 #163: correlación de status de campañas ───────────────────
def _sanitize_error_message(raw: Any) -> Optional[str]:
    """Trunca a 200 chars y limpia caracteres de control. No-PII (códigos)."""
    if raw is None:
        return None
    text = str(raw)
    # quitar saltos de línea y caracteres de control que ensucian el log
    text = re.sub(r"[\r\n\t]+", " ", text).strip()
    return text[:200] if text else None


def process_status_event(db: Session, status_dict: Dict[str, Any]) -> bool:
    """Procesa un item de `value.statuses[]` de Meta.

    Returns:
        True si el status corresponde a un `CampaignRecipient` y se actualizó
        (o se ignoró por idempotencia controlada). False si no es de una
        campaña — el caller puede seguir con el flujo legacy de mensajes 1:1.

    Reglas Sprint 13:
      1. `wamid = status_dict["id"]` → busca `CampaignRecipient` por
         `meta_message_id`. Si no existe → False.
      2. Mapea `status` Meta → interno con `_META_TO_INTERNAL`. Status
         desconocido → log warning y False (no se considera de campaña).
      3. **Idempotencia**: avanza recipient.status SOLO si el rank del
         nuevo es estrictamente mayor que el actual.
      4. Setea `<status>_at` con `timestamp` del payload si viene, si no
         `now()`.
      5. `failed`: extrae `errors[0].code` y guarda en `error_code` (sanitiza
         a string corto, máx 40 chars del CHECK del schema).
      6. Inserta `CampaignEvent` con `ON CONFLICT DO NOTHING` sobre el
         índice parcial `uq_events_dedupe(meta_message_id, event_type)`.
      7. Si la campaña ya no tiene recipients `queued|sending` → cierra
         `status='completed', completed_at=now()`.
    """
    wamid = status_dict.get("id")
    meta_status = status_dict.get("status")
    if not wamid or not meta_status:
        return False

    internal_status = _META_TO_INTERNAL.get(meta_status)
    if internal_status is None:
        # status que no mapeamos (p.ej. 'deleted' futurible); no es nuestro
        logger.info(
            "webhook.campaign status_unknown=%s — ignorado", meta_status
        )
        return False

    recipient = (
        db.query(models.CampaignRecipient)
        .filter(models.CampaignRecipient.meta_message_id == wamid)
        .first()
    )
    if recipient is None:
        # No es un mensaje de campaña; el caller seguirá con flujo 1:1.
        return False

    # Timestamp del evento (Meta lo envía como unix epoch en string)
    raw_ts = status_dict.get("timestamp")
    try:
        event_dt = (
            datetime.utcfromtimestamp(int(raw_ts)) if raw_ts is not None else datetime.utcnow()
        )
    except (TypeError, ValueError):
        event_dt = datetime.utcnow()

    advanced = False
    current_rank = _status_rank(recipient.status)
    new_rank = _status_rank(internal_status)

    if new_rank > current_rank:
        recipient.status = internal_status
        if internal_status == "sent" and recipient.sent_at is None:
            recipient.sent_at = event_dt
        elif internal_status == "delivered":
            recipient.delivered_at = event_dt
            # garantiza que sent_at esté poblado (algunos webhooks omiten sent)
            if recipient.sent_at is None:
                recipient.sent_at = event_dt
        elif internal_status == "read":
            recipient.read_at = event_dt
            if recipient.sent_at is None:
                recipient.sent_at = event_dt
        elif internal_status == "failed":
            recipient.failed_at = event_dt
            errors = status_dict.get("errors") or []
            if errors:
                err0 = errors[0] or {}
                code = err0.get("code")
                if code is not None:
                    # `error_code VARCHAR(40)` en el schema
                    recipient.error_code = str(code)[:40]
        advanced = True
    else:
        logger.info(
            "webhook.campaign idempotent skip recipient_id=%s current=%s incoming=%s",
            recipient.id,
            recipient.status,
            internal_status,
        )

    # Dedupe + insert del evento (siempre intentamos; ON CONFLICT garantiza
    # idempotencia incluso si Meta reenvía el mismo callback).
    stmt = (
        pg_insert(models.CampaignEvent)
        .values(
            campaign_id=recipient.campaign_id,
            recipient_id=recipient.id,
            event_type=internal_status,
            payload_json=status_dict,  # payload completo SÓLO en BD
            meta_message_id=wamid,
            created_at=event_dt,
        )
        # `uq_events_dedupe` es un índice parcial UNIQUE sobre
        # `(meta_message_id, event_type) WHERE meta_message_id IS NOT NULL`.
        # `on_conflict_do_nothing()` sin args captura el conflicto contra
        # cualquier UNIQUE; aquí sólo existe `uq_events_dedupe` y el PK, así
        # que es seguro.
        .on_conflict_do_nothing()
    )
    db.execute(stmt)

    # Cierre de campaña si ya no quedan in-flight
    if advanced:
        still_pending = (
            db.query(models.CampaignRecipient)
            .filter(
                models.CampaignRecipient.campaign_id == recipient.campaign_id,
                models.CampaignRecipient.status.in_(_IN_FLIGHT_RECIPIENT_STATUSES),
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
                camp.completed_at = datetime.utcnow()

    db.commit()

    logger.info(
        "webhook.campaign processed recipient_id=%s campaign_id=%s event=%s advanced=%s",
        recipient.id,
        recipient.campaign_id,
        internal_status,
        advanced,
    )
    return True


@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(raw_body, signature):
        # S13-005: en prod sin firma/secreto cae aquí → 403 fail-closed.
        # 401 se mantenía por compat Sprint 6; usamos 403 alineado a la review.
        status_code = 403 if _is_production() else 401
        raise HTTPException(status_code=status_code, detail="Firma inválida")

    payload = await request.json()
    # S13-004: NO loggear payload crudo (contiene `phone_e164`, `from`,
    # `recipient_id`, contenido de mensajes). Solo metadata agregada.
    logger.info("webhook.meta received %s", _summarize_payload(payload))

    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")

                # Status updates (sent / delivered / read / failed)
                # Sprint 13 #163: estos eventos se correlacionan **por
                # `wamid`** (UNIQUE en `campaign_recipients.meta_message_id`),
                # NO por `phone_number_id`, así que los procesamos antes del
                # lookup de `MetaAccount`. Si el wamid pertenece a una
                # campaña → actualiza recipient + inserta evento idempotente;
                # si no, cae al log legacy (Sprint 6 sólo loggeaba).
                for status_evt in value.get("statuses", []) or []:
                    try:
                        handled = process_status_event(db, status_evt)
                    except Exception:
                        logger.exception(
                            "webhook.campaign error procesando status (status=%s)",
                            (status_evt or {}).get("status"),
                        )
                        handled = False

                    if not handled:
                        # No es de campaña. Log mínimo (sin PII).
                        safe = _sanitize_payload_for_log(status_evt or {})
                        logger.info("webhook.meta status_legacy=%s", safe)

                # Buscar la cuenta Meta por phone_number_id (sólo necesario
                # para mensajes inbound, contactos y bots).
                account = (
                    db.query(models.MetaAccount)
                    .filter(models.MetaAccount.phone_number_id == phone_number_id)
                    .first()
                )
                if not account:
                    logger.warning(
                        "webhook.meta phone_number_id=%s no asociado a ningún team",
                        phone_number_id,
                    )
                    continue

                contacts = {c.get("wa_id"): c for c in value.get("contacts", [])}

                for msg in value.get("messages", []) or []:
                    wa_id = msg.get("from")
                    msg_id = msg.get("id")
                    msg_type = msg.get("type", "text")

                    if msg_type == "text":
                        content = msg.get("text", {}).get("body", "")
                    else:
                        content = f"[{msg_type}]"

                    contact_info = contacts.get(wa_id, {})
                    contact_name = contact_info.get("profile", {}).get("name")

                    conv = crud.get_or_create_conversation(
                        db,
                        team_id=account.team_id,
                        contact_wa_id=wa_id,
                        contact_name=contact_name,
                    )

                    # Dedupe por meta_message_id: si ya procesamos este mensaje
                    # (Meta reintenta), saltar.
                    if msg_id and (
                        db.query(models.Message)
                        .filter(models.Message.meta_message_id == msg_id)
                        .first()
                    ):
                        # S13-004: no loggear msg_id ni wa_id en limpio en INFO;
                        # solo conv interno.
                        logger.info(
                            "webhook.meta dedupe inbound conversation_id=%s",
                            conv.id,
                        )
                        continue

                    crud.add_message(
                        db,
                        conv,
                        direction="inbound",
                        content=content,
                        message_type=msg_type,
                        meta_message_id=msg_id,
                        status="received",
                    )

                    # Sprint 10: resolver bot y ejecutar un turno.
                    team = account.team
                    if team is None:
                        continue

                    bot, session = bot_router_svc.resolve_bot_for_incoming_message(
                        db,
                        team=team,
                        conversation_id=conv.id,
                        message_text=content,
                    )
                    if bot is None:
                        # Sin bot que responder: queda para el agente humano
                        continue

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
                        logger.exception(
                            "bot_runner falló para bot=%s conv=%s", bot.id, conv.id
                        )

    except Exception as exc:
        # Se logea la traza completa server-side (regla 6) pero NO el payload
        # bruto en INFO/WARN.
        logger.exception("Error procesando webhook Meta: %s", exc)
        # Devolvemos 200 para evitar reintentos en bucle de Meta; logueamos para debug.

    return {"status": "ok"}
