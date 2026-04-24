from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..dependencies import get_current_membership, get_db
from ..services import bot_engine

router = APIRouter(prefix="/bots", tags=["bots"])


@router.get("", response_model=List[schemas.BotListItem])
def list_bots(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Lista los bots del owner del team del usuario autenticado.

    Cualquier miembro del team ve los mismos bots (los del owner). Sprint 9.
    """
    bots = crud.list_bots_visible_to_member(db, member)
    return [crud.bot_to_list_item(b) for b in bots]


@router.get("/export")
def export_bots(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Descarga un JSON con todos los bots visibles para el miembro.

    Formato portable, sin métricas ni IDs internos. Pensado para respaldo
    y para que el CEO pueda compartir configuraciones con el equipo.
    """
    bots = crud.list_bots_visible_to_member(db, member)
    payload = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "count": len(bots),
        "bots": [crud.bot_to_export_dict(b) for b in bots],
    }
    filename = f"bots-export-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.json"
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.get("/{bot_id}", response_model=schemas.BotDetail)
def get_bot_detail(
    bot_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Detalle + pasos ordenados para renderizar el diagrama de flujo."""
    bot = crud.get_bot_visible_to_member(db, member, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    return crud.bot_to_detail(bot)


@router.post("/{bot_id}/simulate", response_model=schemas.BotSimulateOut)
def simulate_bot(
    bot_id: int,
    payload: schemas.BotSimulateIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Motor de simulación para el pop-up "Probar Chatbot".

    El estado lo mantiene el cliente. En el primer turno se envía `state=null`
    y `user_input=null`; los turnos siguientes envían el `next_state` recibido
    antes y, si corresponde, el mensaje escrito por el usuario.

    La misma función `bot_engine.advance` se usará al recibir mensajes reales
    desde el webhook de Meta en un sprint futuro.
    """
    bot = crud.get_bot_visible_to_member(db, member, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    result = bot_engine.advance(bot, payload.state, payload.user_input)
    return schemas.BotSimulateOut(
        actions=[schemas.BotAction(**a) for a in result["actions"]],
        next_state=result["next_state"],
        finished=result["finished"],
    )
