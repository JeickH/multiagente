"""Puerto de mensajería agnóstico de proveedor (Sprint 18).

Campañas, bots y webhooks hablan con ESTE módulo, no con Meta ni Twilio
directamente. `get_provider(account)` / las funciones de despacho eligen el
adaptador según `account.provider` (`'meta'` por defecto | `'twilio'`).

Cutover a Twilio = poner `account.provider='twilio'` (+ claves Twilio en env o
BD). Meta sigue disponible como legacy por el mismo puerto.

Los adaptadores se importan de forma perezosa dentro de cada función para
evitar ciclos de import (`meta_adapter` → `meta_whatsapp` → `services`).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .base import (
    MAX_TEXTO_WHATSAPP,
    MessagingError,
    NormalizedInbound,
    NormalizedStatus,
    TextoMuyLargoError,
    mensaje_texto_muy_largo,
)

__all__ = [
    "MAX_TEXTO_WHATSAPP",
    "MessagingError",
    "TextoMuyLargoError",
    "mensaje_texto_muy_largo",
    "NormalizedInbound",
    "NormalizedStatus",
    "provider_of",
    "is_sandbox",
    "send_text",
    "send_media",
    "send_template",
]


def provider_of(account) -> str:
    return (getattr(account, "provider", None) or "meta").lower()


def _adapter(account):
    if provider_of(account) == "twilio":
        from . import twilio_adapter

        return twilio_adapter
    from . import meta_adapter

    return meta_adapter


def is_sandbox(account) -> bool:
    return _adapter(account).is_sandbox(account)


#: Contactos del chat de la página (`routers/landing.py`): se guardan en la
#: bandeja de Gloma para que todo lo que dice el agente quede en la app, pero
#: no son un WhatsApp. Ningún envío sale hacia ellos.
PREFIJO_CHAT_WEB = "web-"


def es_chat_web(wa_id: Optional[str]) -> bool:
    return (wa_id or "").startswith(PREFIJO_CHAT_WEB)


def _no_es_chat_web(account, to_wa_id: str) -> None:
    if es_chat_web(to_wa_id):
        raise MessagingError(
            "conversación del chat de la página: no tiene WhatsApp",
            provider=provider_of(account),
        )


def send_text(account, to_wa_id: str, body: str) -> Tuple[str, Dict[str, Any]]:
    _no_es_chat_web(account, to_wa_id)
    return _adapter(account).send_text(account, to_wa_id, body)


def send_media(
    account,
    to_wa_id: str,
    media_url: str,
    caption: Optional[str] = None,
    media_type: str = "image",
) -> Tuple[str, Dict[str, Any]]:
    """Envía un archivo por URL pública. Ambos proveedores lo hacen por link,
    sin upload previo (Twilio descarga la URL; Meta acepta `link`)."""
    _no_es_chat_web(account, to_wa_id)
    return _adapter(account).send_media(
        account, to_wa_id, media_url, caption=caption, media_type=media_type
    )


def download_media(account, media_url: str) -> Optional[Tuple[bytes, str]]:
    """Baja un archivo que entró por webhook. `(bytes, content_type)` o `None`.

    Lo que llega en el webhook es un enlace del proveedor: privado (pide sus
    credenciales) y temporal. Para que el asesor pueda ver la foto que le mandó
    el cliente hay que bajarla en el momento y guardarla como propia.

    Nunca levanta: `None` significa "no se pudo, sigue con el marcador".
    """
    adaptador = _adapter(account)
    descargar = getattr(adaptador, "download_media", None)
    if descargar is None:
        return None
    return descargar(account, media_url)


def send_template(
    account,
    to_wa_id: str,
    template_name: str,
    language_code: str = "es_CO",
    variables: Optional[dict] = None,
) -> Tuple[str, Dict[str, Any]]:
    _no_es_chat_web(account, to_wa_id)
    return _adapter(account).send_template(
        account, to_wa_id, template_name, language_code=language_code, variables=variables
    )
