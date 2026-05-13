"""Router de Campañas (Sprint 13 — tarea #161).

Endpoints (todos requieren autenticación, filtrados por `team_id`):
  - GET    /campaigns                       → listado con KPIs por campaña
  - GET    /campaigns/kpis                  → KPIs globales del team (dashboard)
  - POST   /campaigns                       → crear campaña + recipients
  - GET    /campaigns/{id}                  → detalle con KPIs + preview
  - GET    /campaigns/{id}/recipients       → paginado de destinatarios
  - POST   /campaigns/{id}/cancel           → cancelar (draft|scheduled → cancelled)

SEGURIDAD (regla 6 / S13-001 / S13-002 / S13-003):
  - `team_id` se infiere SIEMPRE del `current_membership`; nunca del cliente.
  - 404 (no 403) ante recursos de otros teams.
  - Errores genéricos al cliente; detalle a `logger.exception`.

NOTA: el router viejo `routers/campanas.py` es un stub legacy (`GET /campanas`).
Se conserva intacto para no romper compat de frontend antiguo. Este router
nuevo usa el path en inglés `/campaigns` (la fuente de verdad para Sprint 13).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..dependencies import get_current_membership, get_db


logger = logging.getLogger(__name__)

router = APIRouter(tags=["campaigns"])


@router.get("/campaigns", response_model=list[schemas.CampaignOut])
def list_campaigns_endpoint(
    status_filter: Optional[str] = Query(default=None, alias="status", max_length=20),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Listado de campañas del team con KPIs agregados."""
    return crud.list_campaigns(
        db,
        member.team_id,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/campaigns/kpis", response_model=schemas.CampaignsGlobalKPIs)
def campaigns_global_kpis_endpoint(
    date_from: Optional[datetime] = Query(default=None),
    date_to: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """KPIs agregados del team (para dashboard `/campanas`)."""
    return crud.campaign_kpis_global(
        db,
        member.team_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.post(
    "/campaigns",
    response_model=schemas.CampaignDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_campaign_endpoint(
    payload: schemas.CampaignCreate,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Crea una campaña y encola sus destinatarios.

    Mitigaciones aplicadas (delegadas a `crud.create_campaign`):
      - S13-001: valida `template ↔ meta_account ↔ team` cruzado, 404 si rompe.
      - S13-002: enforce `MAX_RECIPIENTS_PER_CAMPAIGN`, 422 si excede.
      - S13-003: contactos `opt_in=False` se insertan como `skipped` con
        `error_code='opt_out_at_enqueue'`.
    """
    try:
        return crud.create_campaign(
            db,
            member.team_id,
            member.user_id,
            payload,
        )
    except HTTPException:
        raise
    except IntegrityError:
        db.rollback()
        logger.exception(
            "create_campaign: IntegrityError (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=409,
            detail="No se pudo guardar la campaña (conflicto).",
        )
    except Exception:
        db.rollback()
        logger.exception(
            "create_campaign: error inesperado (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=500,
            detail="Error temporal al crear la campaña.",
        )


@router.get("/campaigns/{campaign_id}", response_model=schemas.CampaignDetailOut)
def get_campaign_endpoint(
    campaign_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Detalle de campaña + KPIs + preview de destinatarios."""
    campaign = crud.get_campaign(db, member.team_id, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    return crud.build_campaign_detail_out(db, campaign)


@router.get(
    "/campaigns/{campaign_id}/recipients",
    response_model=schemas.CampaignRecipientsPage,
)
def list_campaign_recipients_endpoint(
    campaign_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Paginado de destinatarios. 404 si la campaña no pertenece al team."""
    result = crud.list_campaign_recipients(
        db, member.team_id, campaign_id, limit=limit, offset=offset
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    total, items = result
    return schemas.CampaignRecipientsPage(
        items=[schemas.CampaignRecipientOut.model_validate(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/campaigns/{campaign_id}/cancel",
    response_model=schemas.CampaignDetailOut,
)
def cancel_campaign_endpoint(
    campaign_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Cancela una campaña `draft` o `scheduled`.

    409 si ya está `running`, `completed` o `cancelled`.
    """
    outcome, campaign = crud.cancel_campaign(db, member.team_id, campaign_id)
    if outcome == "not_found":
        raise HTTPException(status_code=404, detail="Campaña no encontrada")
    if outcome == "conflict":
        raise HTTPException(
            status_code=409,
            detail="La campaña no se puede cancelar en su estado actual.",
        )
    return crud.build_campaign_detail_out(db, campaign)
