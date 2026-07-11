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

from .base import MessagingError, NormalizedInbound, NormalizedStatus

__all__ = [
    "MessagingError",
    "NormalizedInbound",
    "NormalizedStatus",
    "provider_of",
    "is_sandbox",
    "send_text",
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


def send_text(account, to_wa_id: str, body: str) -> Tuple[str, Dict[str, Any]]:
    return _adapter(account).send_text(account, to_wa_id, body)


def send_template(
    account,
    to_wa_id: str,
    template_name: str,
    language_code: str = "es_CO",
    variables: Optional[dict] = None,
) -> Tuple[str, Dict[str, Any]]:
    return _adapter(account).send_template(
        account, to_wa_id, template_name, language_code=language_code, variables=variables
    )
