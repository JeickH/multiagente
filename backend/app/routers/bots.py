from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas, crud
from ..dependencies import get_db, get_current_membership

router = APIRouter(prefix="/bots", tags=["bots"])


@router.get("", response_model=List[schemas.BotListItem])
def list_bots(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Lista los bots del team del usuario autenticado.

    Solo lectura en Sprint 8 — cualquier miembro del team puede listar.
    """
    bots = crud.list_bots_by_team(db, member.team_id)
    return [crud.bot_to_list_item(b) for b in bots]


@router.get("/{bot_id}", response_model=schemas.BotDetail)
def get_bot_detail(
    bot_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Detalle + pasos ordenados para renderizar el diagrama de flujo.

    IDOR-safe: filtramos por team_id además de bot_id.
    """
    bot = crud.get_bot_for_team(db, member.team_id, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    return crud.bot_to_detail(bot)
