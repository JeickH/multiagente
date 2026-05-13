"""
Router de WhatsApp Templates.

Endpoints (todos requieren autenticación):
  - GET    /templates                  → lista plantillas del team
  - POST   /templates/sync             → sincroniza con Meta (rate-limited)
  - POST   /templates                  → crea plantilla en Meta (rate-limited)
  - DELETE /templates/{id}             → soft-delete (Meta + local)

SEGURIDAD:
  - S13-001: el `meta_account` se resuelve por `team_id` del usuario
    autenticado. Si no existe → 404 (no 403, no revelamos existencia).
  - S13-007: rate-limit en memoria (sync 1/min/user, create 5/h/team).
  - S13-006: errores de Meta llegan al cliente como códigos genéricos.
  - Regla 6: detalle solo a `logger.exception`.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..dependencies import get_db, get_current_user
from ..services import meta_templates
from ..services.meta_whatsapp import MetaWhatsAppError


logger = logging.getLogger(__name__)

router = APIRouter(tags=["templates"])


# ─── Rate-limit en memoria (per-process) ──────────────────────────────────
# NOTA: este rate-limit es por-proceso. En producción con múltiples tasks
# ECS conviene moverlo a Redis. Para Sprint 13 / ~10 usuarios concurrentes
# en una sola task es suficiente. Documentado en BITACORA.

_lock = threading.Lock()
_sync_last_call: dict[int, float] = {}        # user_id → epoch
_create_history: dict[int, list[float]] = {}  # team_id → [epoch, ...]

SYNC_MIN_INTERVAL_SECONDS = 60       # 1 sync/min/user
CREATE_MAX_PER_HOUR = 5              # 5 templates/hora/team
CREATE_WINDOW_SECONDS = 3600


def _check_sync_rate_limit(user_id: int) -> None:
    now = time.time()
    with _lock:
        last = _sync_last_call.get(user_id, 0.0)
        if now - last < SYNC_MIN_INTERVAL_SECONDS:
            wait = int(SYNC_MIN_INTERVAL_SECONDS - (now - last))
            raise HTTPException(
                status_code=429,
                detail=f"Sincronización en curso. Reintenta en {wait}s.",
            )
        _sync_last_call[user_id] = now


def _check_create_rate_limit(team_id: int) -> None:
    now = time.time()
    with _lock:
        history = [t for t in _create_history.get(team_id, []) if now - t < CREATE_WINDOW_SECONDS]
        if len(history) >= CREATE_MAX_PER_HOUR:
            raise HTTPException(
                status_code=429,
                detail="Límite de plantillas por hora alcanzado. Inténtalo más tarde.",
            )
        history.append(now)
        _create_history[team_id] = history


# ─── Dependency: meta_account del usuario ────────────────────────────────


def _resolve_meta_account(
    db: Session, user: models.User
) -> models.MetaAccount:
    """Resuelve el MetaAccount del team del usuario, o 404 si no hay.

    S13-001: nunca aceptamos `meta_account_id` desde el cliente. Lo derivamos
    del usuario autenticado. Si no tiene team o no tiene MetaAccount → 404
    (no 403, para no revelar existencia).
    """
    member = crud.get_membership_for_user(db, user)
    if member is None:
        logger.info(
            "templates: usuario sin team user_id=%s",
            user.id,
        )
        raise HTTPException(status_code=404, detail="Cuenta de WhatsApp no encontrada")
    account = crud.get_meta_account_for_team(db, member.team_id)
    if account is None:
        logger.info(
            "templates: team sin MetaAccount team_id=%s user_id=%s",
            member.team_id,
            user.id,
        )
        raise HTTPException(status_code=404, detail="Cuenta de WhatsApp no encontrada")
    return account


# ─── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/templates", response_model=List[schemas.WhatsappTemplateOut])
def list_templates_endpoint(
    status: Optional[str] = Query(default=None, max_length=20),
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Lista las plantillas del meta_account del team del usuario."""
    account = _resolve_meta_account(db, user)
    rows = crud.list_templates(db, account.id, status_filter=status)
    return [schemas.WhatsappTemplateOut.model_validate(t) for t in rows]


@router.post("/templates/sync", response_model=schemas.WhatsappTemplateSyncResult)
def sync_templates_endpoint(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Sincroniza plantillas desde Meta. Rate-limited a 1 call/min/usuario."""
    _check_sync_rate_limit(user.id)
    account = _resolve_meta_account(db, user)
    try:
        return meta_templates.sync_templates(db, account)
    except MetaWhatsAppError as exc:
        # Ya fue logueado dentro del servicio; aquí solo sanitizamos.
        logger.warning(
            "templates.sync: MetaWhatsAppError user_id=%s code=%s",
            user.id,
            str(exc)[:80],
        )
        raise HTTPException(
            status_code=502,
            detail="No fue posible sincronizar con Meta en este momento.",
        )


@router.post(
    "/templates",
    response_model=schemas.WhatsappTemplateOut,
    status_code=201,
)
def create_template_endpoint(
    payload: schemas.WhatsappTemplateCreatePayload,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Crea una plantilla en Meta. Rate-limited a 5/h/team."""
    account = _resolve_meta_account(db, user)
    member = crud.get_membership_for_user(db, user)
    if member is None:
        # Defensa: _resolve_meta_account ya validaría, pero por claridad.
        raise HTTPException(status_code=404, detail="Cuenta de WhatsApp no encontrada")
    _check_create_rate_limit(member.team_id)

    try:
        tpl = meta_templates.create_template(db, account, payload)
    except MetaWhatsAppError as exc:
        code = str(exc)
        logger.warning(
            "templates.create: MetaWhatsAppError user_id=%s code=%s status=%s",
            user.id,
            code[:80],
            getattr(exc, "status_code", 0),
        )
        if code == meta_templates.ERR_TEMPLATE_NAME_TAKEN:
            raise HTTPException(status_code=409, detail="El nombre de la plantilla ya existe.")
        if code == meta_templates.ERR_TEMPLATE_REJECTED:
            raise HTTPException(
                status_code=400,
                detail="Meta rechazó la plantilla. Revisa el contenido e inténtalo de nuevo.",
            )
        raise HTTPException(
            status_code=502,
            detail="No fue posible crear la plantilla en este momento.",
        )

    return schemas.WhatsappTemplateOut.model_validate(tpl)


@router.delete("/templates/{template_id}", status_code=204)
def delete_template_endpoint(
    template_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Soft-delete: borra en Meta y marca local como DELETED."""
    account = _resolve_meta_account(db, user)
    template = crud.get_template(db, account.id, template_id)
    if template is None:
        # S13-001: 404 sin revelar existencia para IDs de otros teams.
        raise HTTPException(status_code=404, detail="Plantilla no encontrada")

    try:
        meta_templates.delete_template(db, account, template)
    except MetaWhatsAppError as exc:
        logger.warning(
            "templates.delete: MetaWhatsAppError user_id=%s template_id=%s code=%s",
            user.id,
            template_id,
            str(exc)[:80],
        )
        raise HTTPException(
            status_code=502,
            detail="No fue posible eliminar la plantilla en este momento.",
        )
    return None
