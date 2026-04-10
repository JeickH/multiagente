"""
Cliente para Meta WhatsApp Cloud API (graph.facebook.com).
Documentación: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
import logging
import re as _re
import httpx
from typing import Optional, Tuple, Dict, Any

from .. import models


logger = logging.getLogger(__name__)


class MetaWhatsAppError(Exception):
    """Error al llamar a la API de Meta."""

    def __init__(self, message: str, status_code: int = 0, payload: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


# Patrón para detectar tokens Meta (prefix EAA + caracteres base64)
_TOKEN_PATTERN = _re.compile(r"EAA[A-Za-z0-9_\-]{10,}")

_SENSITIVE_KEYS = {"authorization", "access_token", "token", "app_secret"}


def _sanitize_error_payload(payload):
    """Elimina/redacta cualquier rastro del access_token o headers Authorization.

    Se usa antes de incluir un payload de error en MetaWhatsAppError o en logs.
    Hallazgo S-04 del Sprint 7: errores de Meta pueden contener el token o el
    header Authorization completo en traces de httpx.
    """
    if payload is None:
        return None
    if isinstance(payload, str):
        return _TOKEN_PATTERN.sub("EAA<REDACTED>", payload)
    if isinstance(payload, dict):
        safe = {}
        for k, v in payload.items():
            if isinstance(k, str) and k.lower() in _SENSITIVE_KEYS:
                safe[k] = "<REDACTED>"
            else:
                safe[k] = _sanitize_error_payload(v)
        return safe
    if isinstance(payload, (list, tuple)):
        return [_sanitize_error_payload(item) for item in payload]
    return payload


def _base_url(account: models.MetaAccount) -> str:
    return f"https://graph.facebook.com/{account.api_version}/{account.phone_number_id}/messages"


def _headers(account: models.MetaAccount) -> Dict[str, str]:
    """Construye headers con el access_token descifrado al vuelo.

    SEGURIDAD: el plaintext solo vive en este scope, no se retorna en
    estructuras de larga vida ni se loggea.
    """
    from ..crud import get_decrypted_access_token
    token = get_decrypted_access_token(account)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _post(account: models.MetaAccount, payload: dict) -> dict:
    url = _base_url(account)
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=_headers(account), json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as exc:
        try:
            safe_payload = _sanitize_error_payload(exc.response.json())
        except Exception:
            safe_payload = _sanitize_error_payload(
                (exc.response.text or "")[:500] if exc.response is not None else None
            )
        logger.exception(
            "Error HTTP de Meta: status=%s endpoint=%s",
            exc.response.status_code,
            url,
        )
        raise MetaWhatsAppError(
            f"Meta respondió con status {exc.response.status_code}",
            status_code=exc.response.status_code,
            payload=safe_payload,
        ) from exc
    except httpx.RequestError as exc:
        logger.exception(
            "Error de red al llamar a Meta: type=%s endpoint=%s",
            type(exc).__name__,
            url,
        )
        raise MetaWhatsAppError("Error de red al contactar a Meta") from exc


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


async def get_phone_number_info(
    phone_number_id: str,
    access_token: str,
    api_version: str = "v22.0",
) -> dict:
    """Valida credenciales de Meta antes de persistirlas.

    Llama a:
        GET https://graph.facebook.com/{api_version}/{phone_number_id}
            ?fields=display_phone_number,verified_name

    SEGURIDAD:
    - El token va EXCLUSIVAMENTE en el header Authorization, nunca en query string.
    - Los errores de Meta se sanitizan con _sanitize_error_payload antes de
      devolverse (para que no filtren el token en mensajes como "invalid token: EAA...").
    - El detalle completo se loggea server-side sin el header Authorization.

    Retorna un dict con las claves del Graph API:
        { "display_phone_number": "+57 300 318 7871",
          "verified_name": "Tienda Zeniv",
          "id": "1057839004082880" }

    Lanza MetaWhatsAppError con mensaje genérico si la validación falla.
    """
    url = f"https://graph.facebook.com/{api_version}/{phone_number_id}"
    params = {"fields": "display_phone_number,verified_name"}
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        try:
            safe_payload = _sanitize_error_payload(exc.response.json())
        except Exception:
            safe_payload = _sanitize_error_payload(
                (exc.response.text or "")[:500]
            )
        logger.warning(
            "Validación de credenciales Meta falló: status=%s phone_number_id=%s",
            exc.response.status_code,
            phone_number_id,
        )
        # Mensaje genérico para el cliente; detalle sanitizado en payload
        raise MetaWhatsAppError(
            "No se pudieron validar las credenciales con Meta",
            status_code=exc.response.status_code,
            payload=safe_payload,
        ) from exc
    except httpx.RequestError as exc:
        logger.warning(
            "Error de red al validar credenciales Meta: type=%s",
            type(exc).__name__,
        )
        raise MetaWhatsAppError(
            "Error de red al contactar a Meta"
        ) from exc

    # Validar que la respuesta tiene los campos esperados
    if "display_phone_number" not in data:
        logger.warning(
            "Respuesta de Meta sin display_phone_number: keys=%s",
            list(data.keys()),
        )
        raise MetaWhatsAppError(
            "Respuesta inesperada de Meta al validar credenciales"
        )

    return data
