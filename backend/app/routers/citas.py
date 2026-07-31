"""Citas (demos agendadas por el bot institucional) — Sprint 21 #283.

Panel privado de la **cuenta oficial de Gloma**: lista y edita la tabla
`demo_bookings`, que llena la herramienta `registrar_demo` del bot desde
cualquiera de sus 3 canales (landing, simulador y WhatsApp).

Autorización: solo el owner de la cuenta Gloma y los miembros de su team. No
es un módulo del producto para los demás clientes — cualquier otra cuenta
recibe 403 aunque tenga sesión válida.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..dependencies import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/citas", tags=["citas"])

# Misma cuenta que sirve el chat público de la landing.
GLOMA_EMAIL = os.getenv("GLOMA_LANDING_EMAIL", "gloma@glomabeauty.com").lower()

ESTADOS = ("solicitada", "confirmada", "realizada", "cancelada", "no_asistio")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+\.[a-zA-Z]{2,}$")


def require_gloma_account(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Deja pasar solo a la cuenta de Gloma (owner o miembro de su team)."""
    if (user.correo or "").lower() == GLOMA_EMAIL:
        return user

    owner = (
        db.query(models.User).filter(models.User.correo == GLOMA_EMAIL).first()
    )
    if owner is not None:
        pertenece = (
            db.query(models.TeamMember)
            .join(models.Team, models.Team.id == models.TeamMember.team_id)
            .filter(
                models.TeamMember.user_id == user.id,
                models.Team.owner_user_id == owner.id,
            )
            .first()
        )
        if pertenece is not None:
            return user

    # Sin detalle del porqué al cliente (regla de seguridad #6).
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a este módulo",
    )


class CitaOut(BaseModel):
    id: int
    created_at: datetime
    source: str
    nombre: Optional[str] = None
    empresa: Optional[str] = None
    correo: str
    telefono: Optional[str] = None
    dia: Optional[str] = None
    hora: Optional[str] = None
    notas: Optional[str] = None
    estado: str

    class Config:
        from_attributes = True


class CitaUpdate(BaseModel):
    """Campos editables desde el panel. Todos opcionales (PATCH parcial)."""

    nombre: Optional[str] = Field(default=None, max_length=120)
    empresa: Optional[str] = Field(default=None, max_length=160)
    correo: Optional[str] = Field(default=None, max_length=255)
    telefono: Optional[str] = Field(default=None, max_length=32)
    dia: Optional[str] = Field(default=None, max_length=16)
    hora: Optional[str] = Field(default=None, max_length=16)
    notas: Optional[str] = Field(default=None, max_length=500)
    estado: Optional[str] = Field(default=None, max_length=24)

    @field_validator("correo")
    @classmethod
    def _check_correo(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Correo inválido")
        return v

    @field_validator("estado")
    @classmethod
    def _check_estado(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v not in ESTADOS:
            raise ValueError(f"Estado inválido. Usa uno de: {', '.join(ESTADOS)}")
        return v

    @field_validator("dia")
    @classmethod
    def _check_dia(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().lower()
        if v and v not in DIAS:
            raise ValueError(f"Día inválido. Usa uno de: {', '.join(DIAS)}")
        return v


class CitasResumen(BaseModel):
    total: int
    solicitadas: int
    confirmadas: int
    realizadas: int


class CitasOut(BaseModel):
    citas: List[CitaOut]
    resumen: CitasResumen
    estados: List[str] = list(ESTADOS)
    dias: List[str] = list(DIAS)


@router.get("", response_model=CitasOut)
def list_citas(
    estado: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Demos agendadas, la más reciente primero. Filtro opcional por estado."""
    q = db.query(models.DemoBooking)
    if estado:
        q = q.filter(models.DemoBooking.estado == estado.strip().lower())
    citas = q.order_by(models.DemoBooking.created_at.desc()).limit(500).all()

    def _count(valor: str) -> int:
        return (
            db.query(models.DemoBooking)
            .filter(models.DemoBooking.estado == valor)
            .count()
        )

    return CitasOut(
        citas=[CitaOut.model_validate(c) for c in citas],
        resumen=CitasResumen(
            total=db.query(models.DemoBooking).count(),
            solicitadas=_count("solicitada"),
            confirmadas=_count("confirmada"),
            realizadas=_count("realizada"),
        ),
    )


@router.patch("/{cita_id}", response_model=CitaOut)
def update_cita(
    cita_id: int,
    payload: CitaUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Edita una cita: datos de contacto, franja, estado o notas."""
    cita = (
        db.query(models.DemoBooking)
        .filter(models.DemoBooking.id == cita_id)
        .first()
    )
    if cita is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    cambios = payload.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        if isinstance(valor, str):
            valor = valor.strip() or None
        setattr(cita, campo, valor)
    db.commit()
    db.refresh(cita)
    # Sin PII en el log (regla de seguridad #1): solo qué campos cambiaron.
    logger.info(
        "cita actualizada id=%s campos=%s", cita.id, ",".join(sorted(cambios))
    )
    return CitaOut.model_validate(cita)


@router.delete("/{cita_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cita(
    cita_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Borra una cita (p. ej. registros de prueba o duplicados)."""
    cita = (
        db.query(models.DemoBooking)
        .filter(models.DemoBooking.id == cita_id)
        .first()
    )
    if cita is None:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    db.delete(cita)
    db.commit()
    logger.info("cita eliminada id=%s", cita_id)
    return None
