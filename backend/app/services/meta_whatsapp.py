"""
Cliente para Meta WhatsApp Cloud API (graph.facebook.com).
Documentación: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
import httpx
from typing import Optional, Tuple, Dict, Any

from .. import models


class MetaWhatsAppError(Exception):
    """Error al llamar a la API de Meta."""

    def __init__(self, message: str, status_code: int = 0, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


def _base_url(account: models.MetaAccount) -> str:
    return f"https://graph.facebook.com/{account.api_version}/{account.phone_number_id}/messages"


def _headers(account: models.MetaAccount) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {account.access_token}",
        "Content-Type": "application/json",
    }


def _post(account: models.MetaAccount, payload: dict) -> dict:
    url = _base_url(account)
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=_headers(account), json=payload)
    except httpx.RequestError as exc:
        raise MetaWhatsAppError(f"Error de red llamando a Meta: {exc}") from exc

    if response.status_code >= 400:
        try:
            data = response.json()
        except Exception:
            data = {"raw": response.text}
        message = data.get("error", {}).get("message") or response.text or "Error desconocido"
        raise MetaWhatsAppError(
            f"Meta API error {response.status_code}: {message}",
            status_code=response.status_code,
            payload=data,
        )

    return response.json()


def send_text_message(
    account: models.MetaAccount, to_wa_id: str, body: str
) -> Tuple[str, Dict[str, Any]]:
    """
    Envía un mensaje libre de texto a un contacto. Sólo funciona dentro de la
    ventana de servicio de 24h tras la última interacción del usuario.
    Devuelve (meta_message_id, payload_completo).
    """
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_wa_id,
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    data = _post(account, payload)
    message_id = (
        data.get("messages", [{}])[0].get("id") if data.get("messages") else None
    )
    return message_id, data


def send_template_message(
    account: models.MetaAccount,
    to_wa_id: str,
    template_name: str,
    language_code: str = "es_CO",
) -> Tuple[str, Dict[str, Any]]:
    """
    Envía un mensaje de plantilla aprobada. Permite iniciar conversación
    fuera de la ventana de 24h.
    """
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
        },
    }
    data = _post(account, payload)
    message_id = (
        data.get("messages", [{}])[0].get("id") if data.get("messages") else None
    )
    return message_id, data
