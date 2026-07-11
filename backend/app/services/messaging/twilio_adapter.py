"""Adaptador Twilio del puerto de mensajería (Sprint 18).

Envía WhatsApp por la API de Twilio (proveedor/BSP autorizado) y normaliza los
webhooks de entrada y de estado. Diseñado para **funcionar sin credenciales
reales**: si no hay claves configuradas (o `TWILIO_SANDBOX=1`), simula el envío
con un `SM.local-<uuid>`; cuando la cuenta esté lista basta pegar las claves
(env o BD) y poner `TWILIO_SANDBOX=0` — sin tocar código.

Origen de credenciales (en orden de preferencia):
  1. Campos por-tenant en la cuenta (BD, cifrados con Fernet):
     `twilio_account_sid`, `encrypted_twilio_auth_token`,
     `twilio_from` / `twilio_messaging_service_sid`.
  2. Variables de entorno globales (cuenta matriz / bootstrap single-tenant):
     `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
     `TWILIO_WHATSAPP_FROM`, `TWILIO_MESSAGING_SERVICE_SID`.

Reglas de seguridad:
  - El `Auth Token` NUNCA se loggea (va sólo en el BasicAuth efímero de httpx).
  - Los errores de Twilio se persisten/loggean sin credenciales.
"""
from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import httpx

from .base import MessagingError, NormalizedInbound, NormalizedStatus

logger = logging.getLogger(__name__)

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01"

# Códigos Twilio tratados como retryables (rate-limit / temporal).
_TWILIO_RETRYABLE_CODES = {20429, 63018, 63016}

# Twilio MessageStatus → estado interno del funnel de campañas.
_TWILIO_TO_INTERNAL = {
    "queued": "queued",
    "accepted": "queued",
    "scheduled": "queued",
    "sending": "sending",
    "sent": "sent",
    "delivered": "delivered",
    "read": "read",
    "failed": "failed",
    "undelivered": "failed",
    "canceled": "failed",
}


@dataclass
class _Creds:
    account_sid: Optional[str]
    auth_token: Optional[str]
    from_: Optional[str]
    messaging_service_sid: Optional[str]

    @property
    def complete(self) -> bool:
        return bool(self.account_sid and self.auth_token and (self.from_ or self.messaging_service_sid))


def _resolve_creds(account) -> _Creds:
    """Resuelve credenciales: primero por-tenant (BD, descifradas), luego env."""
    sid = getattr(account, "twilio_account_sid", None) or os.getenv("TWILIO_ACCOUNT_SID")

    token: Optional[str] = None
    enc = getattr(account, "encrypted_twilio_auth_token", None)
    if enc:
        from ..crypto import decrypt_secret  # import perezoso; plaintext efímero

        token = decrypt_secret(enc)
    else:
        token = os.getenv("TWILIO_AUTH_TOKEN")

    from_ = getattr(account, "twilio_from", None) or os.getenv("TWILIO_WHATSAPP_FROM")
    msg_sid = getattr(account, "twilio_messaging_service_sid", None) or os.getenv(
        "TWILIO_MESSAGING_SERVICE_SID"
    )
    return _Creds(account_sid=sid, auth_token=token, from_=from_, messaging_service_sid=msg_sid)


def is_sandbox(account) -> bool:
    """Sandbox Twilio: `TWILIO_SANDBOX=1` (default) o credenciales incompletas."""
    if os.getenv("TWILIO_SANDBOX", "1") == "1":
        return True
    return not _resolve_creds(account).complete


def _as_whatsapp(number: str) -> str:
    """Normaliza a `whatsapp:+<E164>` (acepta con/sin '+' y con/sin prefijo)."""
    n = (number or "").strip()
    if n.startswith("whatsapp:"):
        return n
    if not n.startswith("+"):
        n = "+" + n
    return f"whatsapp:{n}"


def _post_message(account, data: Dict[str, str]) -> Tuple[str, Dict[str, Any]]:
    creds = _resolve_creds(account)
    if not creds.complete:
        raise MessagingError(
            "Credenciales de Twilio incompletas",
            provider="twilio",
            status_code=0,
            retryable=False,
        )

    # Selección del emisor: MessagingServiceSid tiene prioridad sobre From.
    if creds.messaging_service_sid:
        data["MessagingServiceSid"] = creds.messaging_service_sid
    else:
        data["From"] = _as_whatsapp(creds.from_)

    url = f"{TWILIO_API_BASE}/Accounts/{creds.account_sid}/Messages.json"
    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, data=data, auth=(creds.account_sid, creds.auth_token))
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        try:
            err = exc.response.json()
        except Exception:
            err = {"message": (exc.response.text or "")[:300] if exc.response is not None else ""}
        code = err.get("code")
        status = exc.response.status_code
        logger.warning("twilio.send http_error status=%s code=%s", status, code)
        raise MessagingError(
            "Twilio rechazó el envío",
            provider="twilio",
            status_code=status,
            payload=err,
            provider_code=code,
            retryable=(status == 429 or status >= 500 or code in _TWILIO_RETRYABLE_CODES),
        ) from exc
    except httpx.RequestError as exc:
        logger.warning("twilio.send network_error type=%s", type(exc).__name__)
        raise MessagingError(
            "Error de red al contactar a Twilio",
            provider="twilio",
            status_code=0,
            retryable=True,
        ) from exc

    message_sid = body.get("sid")
    return message_sid, body


def send_text(account, to_wa_id: str, body: str) -> Tuple[str, Dict[str, Any]]:
    """Texto libre (dentro de la ventana de servicio de 24h)."""
    if is_sandbox(account):
        return f"SM.local-{uuid.uuid4().hex[:24]}", {"sandbox": True, "provider": "twilio"}
    return _post_message(account, {"To": _as_whatsapp(to_wa_id), "Body": body})


def send_template(
    account,
    to_wa_id: str,
    template_name: str,
    language_code: str = "es_CO",
    variables: Optional[dict] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Plantilla vía Content API.

    `template_name` debe ser el **Content SID** de Twilio (`HX...`). El mapeo
    nombre-de-plantilla → Content SID es follow-up #229; en sandbox no aplica.
    """
    if is_sandbox(account):
        return f"SM.local-{uuid.uuid4().hex[:24]}", {"sandbox": True, "provider": "twilio"}
    data: Dict[str, str] = {"To": _as_whatsapp(to_wa_id), "ContentSid": template_name}
    if variables:
        import json

        data["ContentVariables"] = json.dumps(variables)
    return _post_message(account, data)


# ─── Normalización de webhooks ────────────────────────────────────────────────


def parse_inbound(form: Dict[str, str]) -> Optional[NormalizedInbound]:
    """Convierte el form-encoded de un webhook de entrada de Twilio."""
    message_sid = form.get("MessageSid") or form.get("SmsSid")
    from_raw = form.get("From", "")
    if not message_sid or not from_raw:
        return None
    num_media = int(form.get("NumMedia", "0") or "0")
    media = [form[f"MediaUrl{i}"] for i in range(num_media) if form.get(f"MediaUrl{i}")]
    return NormalizedInbound(
        provider="twilio",
        from_wa_id=from_raw.replace("whatsapp:", "").lstrip("+"),
        to_wa_id=form.get("To", "").replace("whatsapp:", "").lstrip("+"),
        message_id=message_sid,
        text=form.get("Body"),
        message_type="media" if media else "text",
        media_urls=media,
        raw=dict(form),
    )


def parse_status(form: Dict[str, str]) -> Optional[NormalizedStatus]:
    """Convierte el form-encoded de un callback de estado de Twilio."""
    message_sid = form.get("MessageSid") or form.get("SmsSid")
    raw_status = form.get("MessageStatus") or form.get("SmsStatus")
    if not message_sid or not raw_status:
        return None
    internal = _TWILIO_TO_INTERNAL.get(raw_status)
    if internal is None:
        return None
    return NormalizedStatus(
        provider="twilio",
        message_id=message_sid,
        status=internal,
        error_code=form.get("ErrorCode"),
        raw=dict(form),
    )
