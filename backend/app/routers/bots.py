import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..dependencies import get_current_membership, get_current_owner_membership, get_db
from ..services import bot_engine, llm_engine, pausa, pedidos_sheet

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bots", tags=["bots"])


def _detalle(bot: models.Bot, member: models.TeamMember) -> dict:
    """`BotDetail` con el guion efectivo solo para el owner (None para los
    demás miembros: el guion es configuración del negocio, no de la bandeja)."""
    instrucciones = (
        llm_engine.instrucciones_efectivas(bot) if member.role == "owner" else None
    )
    return crud.bot_to_detail(bot, instrucciones=instrucciones)


@router.get("", response_model=List[schemas.BotListItem])
def list_bots(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Lista los bots del owner del team del usuario autenticado.

    Cualquier miembro del team ve los mismos bots (los del owner). Sprint 9.
    """
    return crud.list_bot_items_for_member(db, member)


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


# OJO: declarada ANTES de `/{bot_id}`. Hoy no chocan (métodos distintos), pero
# si algún día se agrega `PUT /{bot_id}`, FastAPI intentaría parsear "reparto"
# como id y respondería 422.
@router.put("/reparto", response_model=List[schemas.BotListItem])
def put_reparto(
    payload: schemas.BotRepartoIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_owner_membership),
):
    """Reparte las conversaciones NUEVAS entre los bots default activos (A/B).

    Los porcentajes deben sumar 100. `{"reparto": []}` quita el reparto y la
    cuenta vuelve a atender con el default de menor id.
    """
    try:
        crud.guardar_reparto(
            db, member, [(i.bot_id, i.pct) for i in payload.reparto]
        )
    except crud.BotNoEncontrado:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    except crud.RepartoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return crud.list_bot_items_for_member(db, member)


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
    return _detalle(bot, member)


@router.post(
    "/{bot_id}/duplicar", response_model=schemas.BotDetail, status_code=201
)
def duplicar_bot(
    bot_id: int,
    payload: Optional[schemas.BotDuplicarIn] = Body(default=None),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_owner_membership),
):
    """Crea una variante del bot (otro guion sobre los mismos productos).

    La variante no recibe conversaciones hasta que se la incluya en el
    reparto (`PUT /bots/reparto`).
    """
    origen = crud.get_bot_visible_to_member(db, member, bot_id)
    if not origen:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    try:
        nuevo = crud.duplicar_bot(
            db,
            member,
            origen,
            name=payload.name if payload else None,
            instrucciones=llm_engine.instrucciones_efectivas(origen),
        )
    except crud.RepartoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except crud.BotDeOtroTeam:
        logger.warning(
            "bots: duplicar bot de otro team bot_id=%s team_id=%s user_id=%s",
            bot_id, member.team_id, member.user_id,
        )
        raise HTTPException(status_code=409, detail="No se puede duplicar este bot")
    return _detalle(nuevo, member)


@router.put("/{bot_id}/instrucciones", response_model=schemas.BotDetail)
def put_instrucciones(
    bot_id: int,
    payload: schemas.BotInstruccionesIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_owner_membership),
):
    """Guarda el guion del bot. Manda desde el turno siguiente, sin desplegar."""
    bot = crud.get_bot_visible_to_member(db, member, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")
    try:
        bot = crud.guardar_instrucciones(db, member, bot, payload.instrucciones)
    except crud.RepartoInvalido as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _detalle(bot, member)


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

    Con el servicio pausado por falta de pago no se simula: cada turno de un
    bot LLM es una llamada a Bedrock que paga Gloma.
    """
    bot = crud.get_bot_visible_to_member(db, member, bot_id)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot no encontrado")

    pausa.exigir_servicio_activo(db, member.team_id)

    # Sprint 19: los bots 'llm' conversan con Claude (Bedrock); los 'flow'
    # siguen el motor de pasos. El contrato del endpoint no cambia.
    camino: str | None = None
    if getattr(bot, "engine", "flow") == "llm":
        result = llm_engine.advance(bot, payload.state, payload.user_input)
        # #255: las pruebas desde la ventana "Probar Chatbot" también quedan
        # registradas en bot_llm_decisions (source='simulador'), y el camino
        # tomado se devuelve para que el usuario lo VEA en el chat de prueba.
        llm_engine.record_decision(
            db, bot, result.get("telemetry"), source="simulador"
        )
        # Sprint 21 #276: una demo agendada desde la ventana de prueba también
        # queda registrada en `demo_bookings` (misma tabla que la landing).
        llm_engine.record_booking(
            db, bot, result.get("telemetry"), source="simulador"
        )
        # Un pedido cerrado desde la ventana de prueba también entra a la hoja
        # del equipo, marcado `simulador` en la columna de origen: así en una
        # demostración se ve la fila aparecer en vivo, y quien despacha
        # distingue de un vistazo la prueba del pedido de verdad.
        pedidos_sheet.registrar(
            db, bot, result.get("telemetry"), source="simulador",
            team_id=member.team_id,
        )
        camino = (result.get("telemetry") or {}).get("camino")
    else:
        result = bot_engine.advance(bot, payload.state, payload.user_input)
    return schemas.BotSimulateOut(
        actions=[schemas.BotAction(**a) for a in result["actions"]],
        next_state=result["next_state"],
        finished=result["finished"],
        camino=camino,
    )
