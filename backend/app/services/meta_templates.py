"""
Cliente y servicio para Meta WhatsApp Business — Message Templates.

Endpoints Meta (Graph API):
  - GET    /{waba_id}/message_templates              (listar)
  - POST   /{waba_id}/message_templates              (crear)
  - DELETE /{waba_id}/message_templates?name={name}  (borrar)

SEGURIDAD (Sprint 13 — security review):
- S13-001: el caller (router) ya validó que `meta_account_id` pertenece al
  team del usuario. Aquí confiamos en eso.
- S13-006: errores de Meta se sanitizan antes de devolverlos al cliente;
  detalle completo solo a `logger.exception`.
- S13-007: el rate-limit por usuario lo aplica el router. Aquí solo no
  reintentamos en bucle.
- S13-014: NO loggear el cuerpo de `POST /templates` (puede contener PII
  de ejemplo del operador).
- Reglas 1, 2 y 6 de CLAUDE.md.

Modo sandbox:
  Si `MetaAccount.encrypted_access_token` es vacío/NULL o si la env var
  `META_SANDBOX=1`, el servicio no llama a Meta y devuelve mocks creíbles.
  Esto permite probar la UI sin credenciales reales.
"""
from __future__ import annotations

import logging
import os
import re as _re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from .meta_whatsapp import MetaWhatsAppError, _sanitize_error_payload


logger = logging.getLogger(__name__)


_META_GRAPH_BASE = "https://graph.facebook.com"
_DEFAULT_PAGE_LIMIT = 200
_HTTP_TIMEOUT = 30.0


def _is_sandbox(account: models.MetaAccount) -> bool:
    """Decide si entramos en modo sandbox.

    Sandbox si:
      - env META_SANDBOX=1, o
      - el meta_account no tiene token cifrado (ej. seed local sin creds).
    """
    if os.getenv("META_SANDBOX", "").strip() in ("1", "true", "yes"):
        return True
    if not account.encrypted_access_token:
        return True
    return False


def _waba_id(account: models.MetaAccount) -> str:
    return account.waba_id


def _api_version(account: models.MetaAccount) -> str:
    return account.api_version or "v22.0"


def _headers(account: models.MetaAccount) -> Dict[str, str]:
    """Headers con token descifrado al vuelo (no se guarda en variable de larga vida)."""
    token = crud.get_decrypted_access_token(account)
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _sandbox_templates() -> List[Dict[str, Any]]:
    """Devuelve 4 plantillas mock con shape compatible con Meta."""
    return [
        {
            "id": "sandbox_tpl_welcome_001",
            "name": "welcome_message",
            "category": "MARKETING",
            "language": "es_CO",
            "status": "APPROVED",
            "components": [
                {"type": "HEADER", "format": "TEXT", "text": "¡Hola {{1}}!"},
                {"type": "BODY", "text": "Bienvenido a Gloma. Cuéntanos cómo te podemos ayudar."},
                {"type": "FOOTER", "text": "Gloma Beauty"},
            ],
        },
        {
            "id": "sandbox_tpl_promo_002",
            "name": "promo_descuento",
            "category": "MARKETING",
            "language": "es_CO",
            "status": "APPROVED",
            "components": [
                {"type": "HEADER", "format": "TEXT", "text": "Promoción"},
                {"type": "BODY", "text": "{{1}}, tienes {{2}}% de descuento esta semana."},
            ],
        },
        {
            "id": "sandbox_tpl_otp_003",
            "name": "codigo_verificacion",
            "category": "AUTHENTICATION",
            "language": "es",
            "status": "APPROVED",
            "components": [
                {"type": "BODY", "text": "Tu código es {{1}}. No lo compartas."},
            ],
        },
        {
            "id": "sandbox_tpl_followup_004",
            "name": "seguimiento_pedido",
            "category": "UTILITY",
            "language": "es_CO",
            "status": "APPROVED",
            "components": [
                {"type": "BODY", "text": "Hola {{1}}, tu pedido {{2}} está en camino."},
                {"type": "FOOTER", "text": "Equipo Gloma"},
            ],
        },
    ]


# ─── Sync ──────────────────────────────────────────────────────────────────


def sync_templates(
    db: Session,
    meta_account: models.MetaAccount,
) -> schemas.WhatsappTemplateSyncResult:
    """Sincroniza plantillas desde Meta hacia la cache local.

    Modo sandbox: si aplica, usa `_sandbox_templates()` sin tocar la red.

    Devuelve un `WhatsappTemplateSyncResult` con conteos. Errores se
    capturan y se devuelven sanitizados en `errors`.
    """
    result = schemas.WhatsappTemplateSyncResult()
    sandbox = _is_sandbox(meta_account)
    result.sandbox = sandbox

    if sandbox:
        logger.info(
            "meta_templates.sync: SANDBOX mode meta_account_id=%s waba_id=%s",
            meta_account.id,
            meta_account.waba_id,
        )
        upstream = _sandbox_templates()
    else:
        try:
            upstream = _fetch_templates_from_meta(meta_account)
        except MetaWhatsAppError as exc:
            logger.exception(
                "meta_templates.sync: error de Meta meta_account_id=%s status=%s",
                meta_account.id,
                getattr(exc, "status_code", 0),
            )
            result.errors.append("meta_api_unavailable")
            return result

    upstream_keys: set[Tuple[str, str]] = set()
    for item in upstream:
        try:
            name = item.get("name")
            language = item.get("language")
            if not name or not language:
                continue
            upstream_keys.add((name, language))
            _, created = crud.upsert_template_from_meta(
                db,
                meta_account.id,
                meta_template_id=item.get("id"),
                name=name,
                category=item.get("category"),
                language=language,
                status=(item.get("status") or "PENDING").upper(),
                components_json={"components": item.get("components") or []},
                rejection_reason=item.get("rejected_reason"),
            )
            result.synced += 1
            if created:
                result.created += 1
            else:
                result.updated += 1
        except Exception:
            logger.exception(
                "meta_templates.sync: fallo al upsertear plantilla meta_account_id=%s",
                meta_account.id,
            )
            result.errors.append("template_upsert_failed")

    # Marcar localmente como DELETED las que ya no están upstream.
    local = crud.list_templates(db, meta_account.id)
    for tpl in local:
        if tpl.status == "DELETED":
            continue
        if (tpl.name, tpl.language) not in upstream_keys:
            try:
                crud.mark_template_deleted_upstream(db, tpl)
                result.deleted_upstream += 1
            except Exception:
                logger.exception(
                    "meta_templates.sync: fallo al marcar DELETED template_id=%s",
                    tpl.id,
                )
                result.errors.append("template_mark_deleted_failed")

    return result


def _fetch_templates_from_meta(
    account: models.MetaAccount,
) -> List[Dict[str, Any]]:
    """GET /{waba_id}/message_templates con paginación.

    Lanza MetaWhatsAppError con mensaje genérico si Meta falla.
    """
    waba = _waba_id(account)
    api = _api_version(account)
    url: Optional[str] = (
        f"{_META_GRAPH_BASE}/{api}/{waba}/message_templates"
    )
    params: Optional[Dict[str, Any]] = {
        "limit": _DEFAULT_PAGE_LIMIT,
        "fields": "name,language,status,category,components,id,rejected_reason",
    }

    all_items: List[Dict[str, Any]] = []
    headers = _headers(account)
    pages = 0
    MAX_PAGES = 50  # cota dura defensiva

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            while url and pages < MAX_PAGES:
                response = client.get(url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()
                all_items.extend(data.get("data") or [])
                pages += 1
                url = (
                    (data.get("paging") or {}).get("next")
                    if isinstance(data.get("paging"), dict)
                    else None
                )
                params = None  # ya viene en la URL `next`
    except httpx.HTTPStatusError as exc:
        try:
            safe = _sanitize_error_payload(exc.response.json())
        except Exception:
            safe = _sanitize_error_payload(
                (exc.response.text or "")[:500] if exc.response is not None else None
            )
        logger.exception(
            "meta_templates._fetch: HTTP error status=%s waba_id=%s",
            exc.response.status_code,
            waba,
        )
        raise MetaWhatsAppError(
            "Meta respondió con error al listar plantillas",
            status_code=exc.response.status_code,
            payload=safe,
        ) from exc
    except httpx.RequestError as exc:
        logger.exception(
            "meta_templates._fetch: error de red waba_id=%s type=%s",
            waba,
            type(exc).__name__,
        )
        raise MetaWhatsAppError("Error de red al contactar a Meta") from exc

    return all_items


# ─── Create ───────────────────────────────────────────────────────────────


# Set fijo de errores que pueden llegar al cliente (S13-006).
ERR_TEMPLATE_NAME_TAKEN = "template_name_taken"
ERR_TEMPLATE_REJECTED = "template_rejected_by_meta"
ERR_META_UNAVAILABLE = "meta_api_unavailable"
ERR_TEMPLATE_INVALID = "template_invalid_payload"


def create_template(
    db: Session,
    meta_account: models.MetaAccount,
    payload: schemas.WhatsappTemplateCreatePayload,
) -> models.WhatsappTemplate:
    """Crea una plantilla en Meta y la persiste localmente como PENDING.

    Sandbox: no llama a Meta; crea la fila local con status=PENDING y un
    `meta_template_id` mock.

    Lanza `MetaWhatsAppError` con código sanitizado si:
      - Meta rechaza (400) → ERR_TEMPLATE_REJECTED
      - Nombre ya existe localmente o en Meta → ERR_TEMPLATE_NAME_TAKEN
      - Red/timeout → ERR_META_UNAVAILABLE
    """
    # Pre-check local de duplicados (UX: 400 antes de tocar a Meta).
    if crud.get_template_by_name_lang(
        db, meta_account.id, payload.name, payload.language
    ):
        raise MetaWhatsAppError(ERR_TEMPLATE_NAME_TAKEN, status_code=409)

    sandbox = _is_sandbox(meta_account)

    if sandbox:
        logger.info(
            "meta_templates.create: SANDBOX mode meta_account_id=%s name=%s lang=%s",
            meta_account.id,
            payload.name,
            payload.language,
        )
        tpl = crud.create_template_pending(
            db,
            meta_account.id,
            name=payload.name,
            category=payload.category,
            language=payload.language,
            components_json={"components": payload.components},
            meta_template_id=f"sandbox_tpl_{payload.name}",
        )
        return tpl

    # Llamada real a Meta.
    waba = _waba_id(meta_account)
    api = _api_version(meta_account)
    url = f"{_META_GRAPH_BASE}/{api}/{waba}/message_templates"
    body = {
        "name": payload.name,
        "category": payload.category,
        "language": payload.language,
        "components": payload.components,
    }

    # NUNCA loguear `body` (puede tener PII de ejemplo — S13-014).
    logger.info(
        "meta_templates.create: POST a Meta meta_account_id=%s name=%s lang=%s",
        meta_account.id,
        payload.name,
        payload.language,
    )

    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.post(url, headers=_headers(meta_account), json=body)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        try:
            safe = _sanitize_error_payload(exc.response.json())
        except Exception:
            safe = _sanitize_error_payload(
                (exc.response.text or "")[:500] if exc.response is not None else None
            )
        logger.exception(
            "meta_templates.create: HTTP error status=%s waba_id=%s name=%s",
            status_code,
            waba,
            payload.name,
        )
        if status_code in (400, 422):
            raise MetaWhatsAppError(
                ERR_TEMPLATE_REJECTED, status_code=status_code, payload=safe
            ) from exc
        raise MetaWhatsAppError(
            ERR_META_UNAVAILABLE, status_code=status_code, payload=safe
        ) from exc
    except httpx.RequestError as exc:
        logger.exception(
            "meta_templates.create: error de red waba_id=%s type=%s",
            waba,
            type(exc).__name__,
        )
        raise MetaWhatsAppError(ERR_META_UNAVAILABLE) from exc

    tpl = crud.create_template_pending(
        db,
        meta_account.id,
        name=payload.name,
        category=payload.category,
        language=payload.language,
        components_json={"components": payload.components},
        meta_template_id=str(data.get("id")) if data.get("id") else None,
    )
    return tpl


# ─── Delete ───────────────────────────────────────────────────────────────


def delete_template(
    db: Session,
    meta_account: models.MetaAccount,
    template: models.WhatsappTemplate,
) -> models.WhatsappTemplate:
    """Borra la plantilla en Meta y la marca como DELETED localmente.

    Soft delete local (preserva FK desde `campaigns.template_id`).
    """
    sandbox = _is_sandbox(meta_account)

    if sandbox:
        logger.info(
            "meta_templates.delete: SANDBOX mode meta_account_id=%s name=%s",
            meta_account.id,
            template.name,
        )
        crud.mark_template_deleted_upstream(db, template)
        return template

    waba = _waba_id(meta_account)
    api = _api_version(meta_account)
    url = f"{_META_GRAPH_BASE}/{api}/{waba}/message_templates"
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT) as client:
            response = client.delete(
                url,
                headers=_headers(meta_account),
                params={"name": template.name},
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code if exc.response is not None else 0
        try:
            safe = _sanitize_error_payload(exc.response.json())
        except Exception:
            safe = _sanitize_error_payload(
                (exc.response.text or "")[:500] if exc.response is not None else None
            )
        logger.exception(
            "meta_templates.delete: HTTP error status=%s waba_id=%s name=%s",
            status_code,
            waba,
            template.name,
        )
        # 404 desde Meta → se considera ya borrada upstream, OK.
        if status_code == 404:
            crud.mark_template_deleted_upstream(db, template)
            return template
        raise MetaWhatsAppError(
            ERR_META_UNAVAILABLE, status_code=status_code, payload=safe
        ) from exc
    except httpx.RequestError as exc:
        logger.exception(
            "meta_templates.delete: error de red waba_id=%s type=%s",
            waba,
            type(exc).__name__,
        )
        raise MetaWhatsAppError(ERR_META_UNAVAILABLE) from exc

    crud.mark_template_deleted_upstream(db, template)
    return template
