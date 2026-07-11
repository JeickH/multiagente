"""Tipos base del puerto de mensajería agnóstico de proveedor (Sprint 18).

Este módulo NO importa ningún adaptador (evita ciclos de import). Contiene:
  - `MessagingError`: error común que ambos adaptadores (Meta / Twilio) lanzan.
    `MetaWhatsAppError` hereda de aquí, por lo que `except MessagingError`
    captura errores de los dos proveedores.
  - `NormalizedInbound` / `NormalizedStatus`: representación uniforme de los
    eventos que llegan por webhook, independiente del proveedor.

Regla de seguridad #1/#6: ni el token ni credenciales se guardan aquí; los
payloads que se adjuntan a `MessagingError` deben venir ya sanitizados por el
adaptador.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class MessagingError(Exception):
    """Error al enviar/consultar un proveedor de mensajería.

    Atributos:
      provider: 'meta' | 'twilio' | 'unknown'.
      status_code: HTTP status devuelto por el proveedor (0 si fue error de red).
      payload: cuerpo de error YA sanitizado (sin tokens) para persistir/loggear.
      provider_code: código de error propio del proveedor (Meta `error.code`,
        Twilio `code`). Se usa para decidir retry y para `error_code`.
      retryable: True si el error es transitorio (rate-limit / 429 / 5xx).
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "unknown",
        status_code: int = 0,
        payload: Optional[dict] = None,
        provider_code: Optional[Any] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.payload = payload or {}
        self.provider_code = provider_code
        self.retryable = retryable


@dataclass
class NormalizedInbound:
    """Mensaje entrante normalizado (indep. de proveedor)."""

    provider: str
    from_wa_id: str            # E.164 sin prefijo 'whatsapp:' ni '+'
    to_wa_id: str              # número destino (el de la marca), E.164 sin '+'
    message_id: str            # id del proveedor (wamid / MessageSid)
    text: Optional[str] = None
    message_type: str = "text"
    media_urls: list = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NormalizedStatus:
    """Callback de estado normalizado (indep. de proveedor)."""

    provider: str
    message_id: str            # id del proveedor del mensaje saliente
    status: str                # interno: queued|sent|delivered|read|failed
    error_code: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
