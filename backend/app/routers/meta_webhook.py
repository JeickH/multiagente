"""
Webhook de Meta WhatsApp Cloud API.

Configuración en panel Meta:
  - Callback URL: https://<host>/meta/webhook
  - Verify token: METAS_WEBHOOK_VERIFY_TOKEN del .env
  - Suscripción al campo: messages

Para probar en local se necesita una URL pública (ej: ngrok http 8000).
"""
import os
import hmac
import hashlib
import logging
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from sqlalchemy.orm import Session
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


def _verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """Valida la firma X-Hub-Signature-256 enviada por Meta."""
    if not APP_SECRET:
        return True  # En dev sin app secret confiamos en el verify token
    if not signature_header or not signature_header.startswith("sha256="):
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


@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_signature(raw_body, signature):
        raise HTTPException(status_code=401, detail="Firma inválida")

    payload = await request.json()
    logger.info("Webhook Meta recibido: %s", payload)

    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")

                # Buscar la cuenta Meta por phone_number_id
                account = (
                    db.query(models.MetaAccount)
                    .filter(models.MetaAccount.phone_number_id == phone_number_id)
                    .first()
                )
                if not account:
                    logger.warning(
                        "Webhook recibido para phone_number_id %s no asociado a ningún team",
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
                        logger.info("Webhook dedupe: msg %s ya procesado", msg_id)
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
                        logger.exception("bot_runner falló para bot=%s conv=%s", bot.id, conv.id)

                # Status updates (delivered/read/failed) — opcional para tracking
                for status_evt in value.get("statuses", []) or []:
                    logger.info("Status update: %s", status_evt)

    except Exception as exc:
        logger.exception("Error procesando webhook Meta: %s", exc)
        # Devolvemos 200 para evitar reintentos en bucle de Meta; logueamos para debug.

    return {"status": "ok"}
