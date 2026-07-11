"""Adaptador Meta del puerto de mensajería (Sprint 18).

Envuelve el cliente existente `services.meta_whatsapp` sin cambiar su
comportamiento. Todos los envíos por Meta siguen pasando por el mismo código
auditado en Sprints anteriores.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from .. import meta_whatsapp


def is_sandbox(account) -> bool:
    """Sandbox Meta: env `META_SANDBOX=1` o cuenta sin token cifrado.

    Idéntico criterio al histórico de `campaign_sender` (S13), ahora centralizado.
    """
    if os.getenv("META_SANDBOX", "1") == "1":
        return True
    return not getattr(account, "encrypted_access_token", None)


def send_text(account, to_wa_id: str, body: str) -> Tuple[str, Dict[str, Any]]:
    return meta_whatsapp.send_text_message(account, to_wa_id, body)


def send_template(
    account,
    to_wa_id: str,
    template_name: str,
    language_code: str = "es_CO",
    variables: Optional[dict] = None,
) -> Tuple[str, Dict[str, Any]]:
    # El cliente Meta actual no parametriza variables de plantilla; se conserva
    # la firma histórica. (La parametrización real es follow-up #229.)
    return meta_whatsapp.send_template_message(
        account, to_wa_id, template_name, language_code=language_code
    )
