"""Agendamientos: las llamadas por hacer a quien dejó la conversación a medias.

  - `GET   /agendamientos`        la lista del team, paginada, con su resumen
  - `PATCH /agendamientos/{id}`   el asesor la marca como cerrada (o la reabre)

Quién entra: **cualquier miembro del team**, administrador o asesor. No lleva
`require_permission` a propósito — es el módulo de trabajo del asesor, y
pedirle un permiso que hoy nadie tiene configurado lo dejaría por fuera
justamente a él. Lo que sí se respeta es el aislamiento entre cuentas: todo
sale filtrado por `member.team_id`, así que una cuenta jamás ve los clientes
potenciales de otra.

Ojo con lo que se devuelve: aquí viajan nombre y **teléfono** de personas
reales. Es el dato por el que existe la pantalla (el asesor tiene que marcar),
pero por lo mismo no se loggea ninguno de los dos (reglas 1 y 8).

Las filas las crea el bot solo, desde `services/agendamientos.py`, cuando da
una conversación por abandonada. Este router no crea nada: no hay POST.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .. import crud, models
from ..dependencies import get_current_membership, get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agendamientos", tags=["agendamientos"])

MAX_POR_PAGINA = 200


class AgendamientoOut(BaseModel):
    id: int
    conversation_id: int
    contacto: Optional[str] = None
    telefono: str
    nivel_interes: str
    fecha_llamada: date
    estado: str
    asesor: Optional[str] = None
    #: Cuándo el bot la dio por abandonada — el "hace cuánto se enfrió".
    abandonada_at: datetime
    cerrado_at: Optional[datetime] = None


class ResumenOut(BaseModel):
    total: int
    pendientes: int
    cerrados: int


class AgendamientosPageOut(BaseModel):
    agendamientos: List[AgendamientoOut]
    total: int
    pagina: int
    por_pagina: int
    resumen: ResumenOut
    estados: List[str]


class CambioEstadoIn(BaseModel):
    estado: str

    @field_validator("estado")
    @classmethod
    def _estado_valido(cls, v: str) -> str:
        valor = (v or "").strip().lower()
        if valor not in models.AVAILABLE_AGENDAMIENTO_ESTADOS:
            raise ValueError("estado no válido")
        return valor


def _fila(
    ag: models.Agendamiento,
    conv: models.Conversation,
    nombre_de_agenda: Optional[str],
) -> AgendamientoOut:
    return AgendamientoOut(
        id=ag.id,
        conversation_id=ag.conversation_id,
        # Mismo criterio que la bandeja: si la conversación no trae nombre, se
        # cae a la agenda del team antes de mostrar un número pelado.
        contacto=conv.contact_name or nombre_de_agenda,
        telefono=conv.contact_wa_id,
        nivel_interes=ag.nivel_interes,
        fecha_llamada=ag.fecha_llamada,
        estado=ag.estado,
        asesor=ag.asesor,
        abandonada_at=ag.created_at,
        cerrado_at=ag.cerrado_at,
    )


@router.get("", response_model=AgendamientosPageOut)
@router.get("/", response_model=AgendamientosPageOut, include_in_schema=False)
def listar_agendamientos(
    estado: Optional[str] = Query(
        None, description="pendiente | cerrado. Vacío = todos."
    ),
    limite: int = Query(20, ge=1, le=MAX_POR_PAGINA),
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Las llamadas del team, las más urgentes primero.

    El orden es por `fecha_llamada` ascendente: lo primero que ve el asesor es
    lo que ya se venció o lo que toca hoy. Ordenar por fecha de creación
    dejaría arriba al que hay que llamar la semana entrante.
    """
    if estado and estado not in models.AVAILABLE_AGENDAMIENTO_ESTADOS:
        raise HTTPException(status_code=400, detail="Estado no válido")

    base = (
        db.query(models.Agendamiento, models.Conversation)
        .join(
            models.Conversation,
            models.Conversation.id == models.Agendamiento.conversation_id,
        )
        .filter(models.Agendamiento.team_id == member.team_id)
    )

    consulta = base
    if estado:
        consulta = consulta.filter(models.Agendamiento.estado == estado)

    total = consulta.count()
    filas = (
        consulta.order_by(
            models.Agendamiento.fecha_llamada.asc(),
            models.Agendamiento.id.asc(),
        )
        .offset((pagina - 1) * limite)
        .limit(limite)
        .all()
    )

    # Una sola consulta para los nombres que falten, no una por fila (PR #3).
    de_agenda = crud.nombres_de_agenda(
        db,
        member.team_id,
        [conv.contact_wa_id for _, conv in filas if not conv.contact_name],
    )

    # El resumen cuenta SIEMPRE sobre todo el team, no sobre el filtro: es el
    # marcador de "cuánto me falta", y con el filtro puesto en "cerrados" un
    # `pendientes` calculado sobre el filtro diría cero y sería mentira.
    pendientes = base.filter(
        models.Agendamiento.estado == models.AGENDAMIENTO_PENDIENTE
    ).count()
    cerrados = base.filter(
        models.Agendamiento.estado == models.AGENDAMIENTO_CERRADO
    ).count()

    return AgendamientosPageOut(
        agendamientos=[
            _fila(ag, conv, de_agenda.get(conv.contact_wa_id))
            for ag, conv in filas
        ],
        total=total,
        pagina=pagina,
        por_pagina=limite,
        resumen=ResumenOut(
            total=pendientes + cerrados, pendientes=pendientes, cerrados=cerrados
        ),
        estados=list(models.AVAILABLE_AGENDAMIENTO_ESTADOS),
    )


@router.patch("/{agendamiento_id}", response_model=AgendamientoOut)
def cambiar_estado(
    agendamiento_id: int,
    cambio: CambioEstadoIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
    user: models.User = Depends(get_current_user),
):
    """El asesor marca la llamada como cerrada — o la vuelve a abrir.

    El filtro por `team_id` va en el WHERE y no en un `if` posterior: así una
    cuenta que adivine el id de otra recibe 404 y no llega a tocar la fila.
    """
    fila = (
        db.query(models.Agendamiento)
        .filter(
            models.Agendamiento.id == agendamiento_id,
            models.Agendamiento.team_id == member.team_id,
        )
        .first()
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="Agendamiento no encontrado")

    conv = (
        db.query(models.Conversation)
        .filter(models.Conversation.id == fila.conversation_id)
        .first()
    )
    if conv is None:  # pragma: no cover - la FK es CASCADE
        raise HTTPException(status_code=404, detail="Agendamiento no encontrado")

    if cambio.estado == models.AGENDAMIENTO_CERRADO:
        fila.estado = models.AGENDAMIENTO_CERRADO
        fila.cerrado_at = datetime.utcnow()
        fila.cerrado_por_user_id = user.id
    else:
        # Reabrir: se borra la marca de cierre para que no quede una fecha de
        # "cerrado el 8 de septiembre" en algo que está pendiente otra vez.
        fila.estado = models.AGENDAMIENTO_PENDIENTE
        fila.cerrado_at = None
        fila.cerrado_por_user_id = None

    db.add(fila)
    db.commit()
    db.refresh(fila)
    logger.info(
        "agendamientos: %s pasó a %s (team=%s)",
        fila.id, fila.estado, member.team_id,
    )

    de_agenda = crud.nombres_de_agenda(
        db, member.team_id, [] if conv.contact_name else [conv.contact_wa_id]
    )
    return _fila(fila, conv, de_agenda.get(conv.contact_wa_id))
