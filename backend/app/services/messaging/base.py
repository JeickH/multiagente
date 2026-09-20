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

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def team_is_demo(account) -> bool:
    """¿El tenant dueño de esta cuenta está en modo demostración? (#318)

    Un team en `modo='demo'` nunca envía de verdad: los adaptadores lo tratan
    como sandbox aunque las credenciales sean válidas y `TWILIO_SANDBOX=0`.
    Evita que una cuenta de demostración le escriba a un número real o consuma
    la cuota de conversaciones del WABA.

    Si no se puede determinar el modo (relación no cargable), asumimos **demo**:
    ante la duda es preferible no enviar que enviarle a alguien por error.
    """
    try:
        team = getattr(account, "team", None)
        if team is None:
            return False  # cuentas sin team (tests, objetos sueltos) no se bloquean
        return (getattr(team, "modo", None) or "demo").lower() != "produccion"
    except Exception:
        logger.error(
            "messaging: no se pudo leer team.modo — se asume demo y NO se envía"
        )
        return True


# Tope de caracteres de un mensaje de texto saliente.
#
# El número es de Twilio, no nuestro: su plataforma corta en 1.600 caracteres el
# `Body` de CUALQUIER canal (SMS, WhatsApp, Messenger) y responde HTTP 400 con
# el código 21617 — "The concatenated message body exceeds the 1600 character
# limit" (https://www.twilio.com/docs/api/errors/21617). WhatsApp por su cuenta
# aceptaría 4.096, pero nuestros mensajes pasan por Twilio, así que manda el más
# chico. Se aplica igual a las cuentas Meta: un solo número, uno para todos, es
# lo que hace que el contador del navegador no pueda mentir.
#
# ⚠ Este valor está declarado DOS veces a propósito: acá y en
# `frontend/lib/mensajeTexto.ts` (`MAX_TEXTO_WHATSAPP`), para que el compositor
# pueda avisar sin ir al servidor. Que no se desincronicen lo cuida
# `backend/tests/test_mensaje_largo.py::test_el_frontend_declara_el_mismo_limite`,
# que lee el .ts y compara. Si cambias uno, el test te obliga a cambiar el otro.
MAX_TEXTO_WHATSAPP = 1600

# Código de Twilio para "el cuerpo excede el límite de caracteres".
TWILIO_CODE_BODY_MUY_LARGO = 21617


def _miles(n: int) -> str:
    """1742 → "1.742". Separador de miles con punto, como se lee en Colombia."""
    return f"{n:,}".replace(",", ".")


def mensaje_texto_muy_largo(largo: int, maximo: int = MAX_TEXTO_WHATSAPP) -> str:
    """Lo que se le dice a la asesora cuando el mensaje no cabe.

    Es el texto que llega al navegador, así que dice qué pasó y qué hacer, sin
    una palabra del proveedor (regla #6: el detalle de Twilio va sólo al log).
    El número sale siempre de `MAX_TEXTO_WHATSAPP` y nunca escrito a mano.
    """
    return (
        f"El mensaje es muy largo para WhatsApp: tiene {_miles(largo)} caracteres "
        f"y el máximo son {_miles(maximo)}. Pártelo en dos y vuelve a enviarlo."
    )


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


class TextoMuyLargoError(MessagingError):
    """El cuerpo del mensaje pasa de `MAX_TEXTO_WHATSAPP`.

    Es culpa de quien escribió, no del proveedor ni de la red: por eso es la
    única `MessagingError` que el router traduce a **400** y no a 502, y por eso
    `retryable=False` — reintentar el mismo texto va a fallar igual.

    `mensaje_para_la_persona` es lo ÚNICO de esta excepción que puede viajar al
    navegador; ya viene redactado y sin datos del proveedor.
    """

    def __init__(self, largo: int, *, maximo: int = MAX_TEXTO_WHATSAPP, provider: str = "unknown"):
        self.largo = largo
        self.maximo = maximo
        self.mensaje_para_la_persona = mensaje_texto_muy_largo(largo, maximo)
        super().__init__(
            f"Texto de {largo} caracteres; el máximo es {maximo}",
            provider=provider,
            status_code=400,
            provider_code=TWILIO_CODE_BODY_MUY_LARGO,
            retryable=False,
        )


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


# Marcador con el que entra a la conversación un mensaje sin texto legible.
# Se guarda tal cual en `messages.content`, así que lo lee el asesor humano en
# la bandeja **y** el bot como turno del cliente: por eso está en español y dice
# qué pasó, en vez del `[audio]` críptico de antes. El bot tiene instrucciones
# de pedir que le escriban cuando ve este marcador (`llm_engine._system_prompt`).
MARCADOR_NOTA_DE_VOZ = "[nota de voz]"

# Igual para las fotos y capturas: tampoco sabemos leerlas todavía.
MARCADOR_IMAGEN = "[imagen]"

# Tipos que WhatsApp usa para una nota de voz o un audio adjunto.
_TIPOS_AUDIO = frozenset({"audio", "voice", "ptt"})
_TIPOS_IMAGEN = frozenset({"image", "imagen", "photo"})


def es_audio(message_type: Optional[str]) -> bool:
    """¿Este mensaje entrante es una nota de voz / un audio?"""
    return (message_type or "").strip().lower() in _TIPOS_AUDIO


def es_imagen(message_type: Optional[str]) -> bool:
    """¿Este mensaje entrante es una foto o una captura de pantalla?"""
    return (message_type or "").strip().lower() in _TIPOS_IMAGEN


def marcador_inbound(message_type: Optional[str]) -> str:
    """Texto que representa un mensaje entrante que no trae texto.

    Audios e imágenes llevan un marcador explícito porque el bot tiene que
    reaccionar a ellos; el resto conserva el `[tipo]` histórico.
    """
    if es_audio(message_type):
        return MARCADOR_NOTA_DE_VOZ
    if es_imagen(message_type):
        return MARCADOR_IMAGEN
    return f"[{message_type or 'desconocido'}]"


@dataclass
class NormalizedStatus:
    """Callback de estado normalizado (indep. de proveedor)."""

    provider: str
    message_id: str            # id del proveedor del mensaje saliente
    status: str                # interno: queued|sent|delivered|read|failed
    error_code: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)
