"""Pedidos confirmados por el bot.

  - `GET   /pedidos/access`  ¿esta cuenta tiene el módulo? (lo pregunta el menú)
  - `GET   /pedidos`         la lista del equipo, el más reciente arriba
  - `PATCH /pedidos/{id}`    marcar despachado, cancelar o reabrir

Quién entra: **cualquier miembro del team**, igual que en Agendamientos. Es el
módulo de trabajo de quien despacha, y pedirle un permiso que hoy nadie tiene
configurado lo dejaría por fuera justamente a él. El aislamiento entre cuentas
sí se respeta: todo sale filtrado por `member.team_id`.

Qué cuenta lo ve: **la que tenga el bloque `pedidos` configurado en su bot**.
No hay lista de correos cableada — si mañana otra marca conecta su hoja, le
aparece la ventana sola. Ver `services/pedidos_sheet.py`.

Ojo con lo que se devuelve: aquí viajan nombre, dirección y teléfono de
personas reales. Es justamente para lo que existe la pantalla (hay que
despachar a esa dirección), pero por lo mismo no se loggea ninguno de los tres
(reglas 1 y 8).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from .. import crud, models
from ..dependencies import get_current_membership, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pedidos", tags=["pedidos"])

MAX_POR_PAGINA = 200


class AccesoOut(BaseModel):
    allowed: bool
    #: Nombre de la hoja conectada, para poder nombrarla en la pantalla.
    hoja: Optional[str] = None
    #: Si la hoja ya tiene su script publicado. Mientras sea `False` los
    #: pedidos se guardan igual (en la base, que es la copia que importa) y la
    #: pantalla NO alarma con un "no llegó a la hoja" que sería culpa de una
    #: configuración a medias, no de una falla.
    conectada: bool = False


class PedidoOut(BaseModel):
    id: int
    conversation_id: Optional[int] = None
    nombre: str
    direccion: str
    detalle: str
    total: Optional[str] = None
    telefono: Optional[str] = None
    origen: str
    estado: str
    en_hoja: bool
    created_at: datetime


class ResumenOut(BaseModel):
    total: int
    pendientes: int
    despachados: int
    #: Cuántos no alcanzaron a escribirse en la hoja. Si no es cero, hay algo
    #: que revisar del lado de Google.
    sin_hoja: int


class PedidosPageOut(BaseModel):
    pedidos: List[PedidoOut]
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
        if valor not in models.AVAILABLE_PEDIDO_ESTADOS:
            raise ValueError("estado no válido")
        return valor


def _config_pedidos(db: Session, member: models.TeamMember) -> Optional[dict]:
    """El bloque `pedidos` del bot de este team, si lo tiene."""
    bots = crud.list_bots_visible_to_member(db, member)
    for bot in bots:
        try:
            cfg = json.loads(bot.llm_config or "{}")
        except (TypeError, ValueError):
            continue
        pedidos = cfg.get("pedidos")
        if isinstance(pedidos, dict):
            return pedidos
    return None


def _fila(p: models.Pedido) -> PedidoOut:
    return PedidoOut(
        id=p.id,
        conversation_id=p.conversation_id,
        nombre=p.nombre,
        direccion=p.direccion,
        detalle=p.detalle,
        total=p.total,
        telefono=p.telefono,
        origen=p.origen,
        estado=p.estado,
        en_hoja=p.en_hoja,
        created_at=p.created_at,
    )


@router.get("/access", response_model=AccesoOut)
def check_access(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """¿Esta cuenta tiene el módulo de pedidos? Responde 200 siempre."""
    pedidos = _config_pedidos(db, member)
    if pedidos is None:
        return AccesoOut(allowed=False)
    # El nombre de la hoja se puede mostrar; la URL del script NO sale nunca
    # de aquí — es un secreto del tenant (regla 2: nada sensible en un `...Out`).
    # De la URL solo se dice si existe, que no revela nada.
    return AccesoOut(
        allowed=True,
        hoja=str(pedidos.get("hoja") or "") or None,
        conectada=bool(
            (pedidos.get("encrypted_webhook_url") or pedidos.get("webhook_url") or "").strip()
        ),
    )


@router.get("", response_model=PedidosPageOut)
@router.get("/", response_model=PedidosPageOut, include_in_schema=False)
def listar_pedidos(
    estado: Optional[str] = Query(
        None, description="pendiente | despachado | cancelado. Vacío = todos."
    ),
    limite: int = Query(20, ge=1, le=MAX_POR_PAGINA),
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Los pedidos del equipo, el más reciente arriba.

    Al revés que Agendamientos, que ordena por fecha de llamada: aquí lo que
    manda es "qué entró hoy", y un pedido viejo no sube por nada.
    """
    if estado and estado not in models.AVAILABLE_PEDIDO_ESTADOS:
        raise HTTPException(status_code=400, detail="Estado no válido")

    base = db.query(models.Pedido).filter(models.Pedido.team_id == member.team_id)

    consulta = base
    if estado:
        consulta = consulta.filter(models.Pedido.estado == estado)

    total = consulta.count()
    filas = (
        consulta.order_by(models.Pedido.created_at.desc(), models.Pedido.id.desc())
        .offset((pagina - 1) * limite)
        .limit(limite)
        .all()
    )

    # El resumen cuenta SIEMPRE sobre todo el equipo, no sobre el filtro: es el
    # marcador de "cuánto me falta", y con el filtro en "despachados" un
    # `pendientes` calculado sobre el filtro diría cero y sería mentira.
    pendientes = base.filter(models.Pedido.estado == models.PEDIDO_PENDIENTE).count()
    despachados = base.filter(
        models.Pedido.estado == models.PEDIDO_DESPACHADO
    ).count()
    sin_hoja = base.filter(models.Pedido.en_hoja.is_(False)).count()

    return PedidosPageOut(
        pedidos=[_fila(p) for p in filas],
        total=total,
        pagina=pagina,
        por_pagina=limite,
        resumen=ResumenOut(
            total=base.count(),
            pendientes=pendientes,
            despachados=despachados,
            sin_hoja=sin_hoja,
        ),
        estados=list(models.AVAILABLE_PEDIDO_ESTADOS),
    )


@router.patch("/{pedido_id}", response_model=PedidoOut)
def cambiar_estado(
    pedido_id: int,
    cambio: CambioEstadoIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Marca el pedido como despachado, lo cancela o lo vuelve a pendiente.

    El filtro por `team_id` va en el WHERE y no en un `if` posterior: así una
    cuenta que adivine el id de otra recibe 404 y no llega a tocar la fila.
    """
    fila = (
        db.query(models.Pedido)
        .filter(
            models.Pedido.id == pedido_id,
            models.Pedido.team_id == member.team_id,
        )
        .first()
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")

    fila.estado = cambio.estado
    fila.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(fila)
    # Sin datos del cliente en el log (reglas 1 y 8).
    logger.info("pedido %s → %s (team=%s)", fila.id, fila.estado, member.team_id)
    return _fila(fila)
