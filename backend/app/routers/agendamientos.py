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
from sqlalchemy import func
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
    pagina: int = Query(1, ge=1, le=10_000),
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


# ===========================================================================
# Interesados (estrategia #22)
# ===========================================================================
#
#   - `GET   /agendamientos/interesados`              lista + resumen
#   - `POST  /agendamientos/interesados/{id}/tomar`   la asesora se queda el chat
#   - `PATCH /agendamientos/interesados/{id}`         contactado / descartado / deshacer
#
# Ver lo pueden todos los miembros del team (como las llamadas). **Tomar** pide
# `can_reply_messages`: es la única acción que cambia quién le responde al
# cliente, y es la diferencia con `POST /mensajes/conversaciones/{id}/asignar`,
# que sigue siendo solo del dueño porque mueve chats de otros. Aquí solo se
# toma un chat que hoy tiene el bot, y el destino es siempre quien lo pide.
#
# Todo va filtrado por `member.team_id` (del servidor, nunca del cliente) y lo
# ajeno da el mismo 404 que lo inexistente. Errores al cliente genéricos y
# logs solo con ids y estados (reglas 1, 6 y 8).

from .. import schemas  # noqa: E402
from ..dependencies import require_permission  # noqa: E402
from ..services import agendamientos as svc_agendamientos  # noqa: E402
from ..services import llm_engine  # noqa: E402

_NO_ENCONTRADO = "Interesado no encontrado"
_YA_TOMADO = "Esta conversación ya la tomó otra persona del equipo"
_YA_NO_ESTA = "Este cliente ya no está en la lista de interesados"


def _umbral_del_team(db: Session, bots: list) -> float:
    for bot in bots:
        cfg = llm_engine.config_de(bot)
        if svc_agendamientos.config_intencion(cfg) is not None:
            return svc_agendamientos.horas_para_interesado(cfg)
    return float(models.INTENCION_HORAS_DEFAULT)


def _nombres_de_usuarios(db: Session, ids) -> dict:
    """`{user_id: nombre}` en una sola consulta (nunca el correo)."""
    ids = {i for i in ids if i}
    if not ids:
        return {}
    return {
        uid: nombre
        for uid, nombre in db.query(models.User.id, models.User.nombre)
        .filter(models.User.id.in_(ids))
        .all()
    }


def _item(
    fila: models.IntencionCompra,
    conv: models.Conversation,
    sesion: Optional[models.BotSession],
    bot: models.Bot,
    ultimo: Optional[datetime],
    *,
    nombre_de_agenda: Optional[str],
    interes: Optional[dict],
    usuarios: dict,
) -> schemas.InteresadoOut:
    return schemas.InteresadoOut(
        id=fila.id,
        conversation_id=conv.id,
        contacto=conv.contact_name or nombre_de_agenda,
        telefono=conv.contact_wa_id,
        tipos=list(fila.tipos or []),
        fragmento=fila.fragmento,
        resumen=fila.resumen,
        detectado_at=fila.primera_at,
        conversacion_inicio_at=(sesion.started_at if sesion is not None else fila.primera_at),
        interesado_desde=fila.visible_desde,
        ultimo_mensaje_cliente_at=ultimo,
        ventana_cierra_at=(ultimo + svc_agendamientos.VENTANA_WHATSAPP) if ultimo else None,
        interes=schemas.InteresadoInteresOut(**interes) if interes else None,
        bot=schemas.InteresadoBotOut(id=bot.id, nombre=bot.name),
        estado=fila.estado,
        gestionado_por=usuarios.get(fila.gestionado_por_user_id),
        gestionado_at=fila.gestionado_at,
        motivo_descarte=fila.motivo_descarte,
        tomado_por=usuarios.get(fila.tomado_por_user_id),
        tomado_at=fila.tomado_at,
        atiende="bot" if (conv.assigned_to or "bot") == "bot" else "asesor",
    )


def _items(db: Session, team_id: int, filas: list) -> List[schemas.InteresadoOut]:
    """Arma la página con un número FIJO de consultas (sin N+1): nombres de
    agenda, consulta de precios por sesión y nombres de quien gestionó."""
    de_agenda = crud.nombres_de_agenda(
        db, team_id, [conv.contact_wa_id for _, conv, _, _, _ in filas if not conv.contact_name]
    )
    interes = svc_agendamientos.interes_por_sesion(
        db, [fila.session_id for fila, _, _, _, _ in filas]
    )
    usuarios = _nombres_de_usuarios(
        db,
        [f.gestionado_por_user_id for f, _, _, _, _ in filas]
        + [f.tomado_por_user_id for f, _, _, _, _ in filas],
    )
    return [
        _item(
            fila, conv, sesion, bot, ultimo,
            nombre_de_agenda=de_agenda.get(conv.contact_wa_id),
            interes=interes.get(fila.session_id),
            usuarios=usuarios,
        )
        for fila, conv, sesion, bot, ultimo in filas
    ]


def _ultimo_entrante(db: Session, conversation_id: int) -> Optional[datetime]:
    return (
        db.query(func.max(models.Message.created_at))
        .filter(
            models.Message.conversation_id == conversation_id,
            models.Message.direction == "inbound",
        )
        .scalar()
    )


def _item_suelto(db: Session, team_id: int, fila, conv, sesion, bot) -> schemas.InteresadoOut:
    return _items(db, team_id, [(fila, conv, sesion, bot, _ultimo_entrante(db, conv.id))])[0]


@router.get("/interesados", response_model=schemas.InteresadosPageOut)
def listar_interesados(
    estado: str = Query(
        models.INTENCION_POR_CONTACTAR,
        description="por_contactar | contactado | descartado",
    ),
    limite: int = Query(20, ge=1, le=MAX_POR_PAGINA),
    pagina: int = Query(1, ge=1, le=10_000),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Los interesados del team. Orden y resumen: ver
    `services.agendamientos.listar_interesados`."""
    if estado not in models.AVAILABLE_INTENCION_ESTADOS:
        raise HTTPException(status_code=400, detail="Estado no válido")

    ahora = datetime.utcnow()
    team = db.query(models.Team).get(member.team_id)
    bots = []
    if team is not None:
        bots = (
            db.query(models.Bot)
            .filter(
                models.Bot.status == "active",
                models.Bot.engine == "llm",
                (models.Bot.team_id == member.team_id)
                | (models.Bot.user_id == team.owner_user_id),
            )
            .all()
        )
    habilitado = any(
        svc_agendamientos.config_intencion(llm_engine.config_de(b)) is not None
        for b in bots
    )

    filas, total, resumen = svc_agendamientos.listar_interesados(
        db, team_id=member.team_id, estado=estado,
        pagina=pagina, limite=limite, ahora=ahora,
    )
    return schemas.InteresadosPageOut(
        habilitado=habilitado,
        interesados=_items(db, member.team_id, filas),
        total=total,
        pagina=pagina,
        por_pagina=limite,
        resumen=schemas.InteresadosResumenOut(**resumen),
        generado_at=ahora,
        umbral_horas=_umbral_del_team(db, bots),
        puede_tomar=crud.member_has_permission(member, "can_reply_messages"),
    )


@router.post("/interesados/{intencion_id}/tomar", response_model=schemas.InteresadoOut)
def tomar_interesado(
    intencion_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
    # El portero de verdad: sin `can_reply_messages` → 403 antes de tocar nada.
    # FastAPI cachea `get_current_membership` por request: es la misma fila.
    _puede_responder: models.TeamMember = Depends(
        require_permission("can_reply_messages")
    ),
    user: models.User = Depends(get_current_user),
):
    """La asesora se queda con la conversación (body vacío: el destino es
    quien hace la petición).

    200 → el interesado actualizado · 404 no existe o es de otra cuenta ·
    409 ya no la atiende el bot · 410 ya no es interesado · 403 sin
    `can_reply_messages`.
    """
    try:
        fila, conv, sesion, bot = svc_agendamientos.tomar_interesado(
            db, intencion_id=intencion_id, team_id=member.team_id, user=user,
        )
    except svc_agendamientos.InteresadoNoEncontrado:
        raise HTTPException(status_code=404, detail=_NO_ENCONTRADO)
    except svc_agendamientos.InteresadoYaTomado:
        raise HTTPException(status_code=409, detail=_YA_TOMADO)
    except svc_agendamientos.InteresadoVencido:
        raise HTTPException(status_code=410, detail=_YA_NO_ESTA)
    except Exception:
        db.rollback()
        logger.exception(
            "interesados.tomar falló id=%s team=%s por_user_id=%s",
            intencion_id, member.team_id, user.id,
        )
        raise HTTPException(status_code=500, detail="No se pudo tomar la conversación")
    return _item_suelto(db, member.team_id, fila, conv, sesion, bot)


@router.patch("/interesados/{intencion_id}", response_model=schemas.InteresadoOut)
def cambiar_estado_interesado(
    intencion_id: int,
    cambio: schemas.InteresadoCambioIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
    user: models.User = Depends(get_current_user),
):
    """Ya lo contacté · Descartar (motivo de la lista cerrada) · Deshacer.

    No cambia quién atiende: el bot sigue en el chat.
    """
    try:
        fila, conv, sesion, bot = svc_agendamientos.cambiar_estado_interesado(
            db,
            intencion_id=intencion_id,
            team_id=member.team_id,
            user_id=user.id,
            estado=cambio.estado,
            motivo=cambio.motivo,
        )
    except svc_agendamientos.InteresadoNoEncontrado:
        raise HTTPException(status_code=404, detail=_NO_ENCONTRADO)
    return _item_suelto(db, member.team_id, fila, conv, sesion, bot)
