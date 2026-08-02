"""Citas (demos agendadas por el bot institucional) — Sprint 21 #283.

Panel privado de la **cuenta oficial de Gloma**. Dos subsecciones, la misma
autorización:

- `/citas`             → tabla `demo_bookings`: las demos que agenda la
  herramienta `registrar_demo` del bot desde sus 3 canales (landing,
  simulador y WhatsApp), más las que se agreguen a mano.
- `/citas/solicitudes` → tabla `leads`: las solicitudes "Quiero que me
  contacten" del formulario de la landing (#298), con seguimiento
  `pendiente` / `contactado`.

Autorización: solo el owner de la cuenta Gloma y los miembros de su team. No
es un módulo del producto para los demás clientes — cualquier otra cuenta
recibe 403 aunque tenga sesión válida.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import date as dt_date, datetime
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

# Solicitudes de contacto (#298): el CEO solo necesita saber si ya se contactó
# al prospecto o si sigue pendiente.
ESTADOS_SOLICITUD = ("pendiente", "contactado")


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
    fecha: Optional[dt_date] = None
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
    fecha: Optional[dt_date] = None
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


class CitaCreate(BaseModel):
    """Alta manual desde el panel (una demo agendada por teléfono, correo, etc.)."""

    correo: str = Field(..., max_length=255)
    nombre: Optional[str] = Field(default=None, max_length=120)
    empresa: Optional[str] = Field(default=None, max_length=160)
    telefono: Optional[str] = Field(default=None, max_length=32)
    fecha: Optional[dt_date] = None
    dia: Optional[str] = Field(default=None, max_length=16)
    hora: Optional[str] = Field(default=None, max_length=16)
    notas: Optional[str] = Field(default=None, max_length=500)
    estado: str = Field(default="solicitada", max_length=24)

    @field_validator("correo")
    @classmethod
    def _check_correo(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Correo inválido")
        return v

    @field_validator("estado")
    @classmethod
    def _check_estado(cls, v: str) -> str:
        v = (v or "solicitada").strip().lower()
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
        return v or None


class AccesoOut(BaseModel):
    allowed: bool


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


# --- Solicitudes de contacto (#298) ---------------------------------------


class SolicitudOut(BaseModel):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    source: str
    nombre: Optional[str] = None
    email: str
    telefono: Optional[str] = None
    notas: Optional[str] = None
    estado: str

    class Config:
        from_attributes = True


class SolicitudCreate(BaseModel):
    """Alta manual de una solicitud (la que llegó por fuera del formulario)."""

    email: str = Field(..., max_length=255)
    nombre: Optional[str] = Field(default=None, max_length=120)
    telefono: Optional[str] = Field(default=None, max_length=32)
    notas: Optional[str] = Field(default=None, max_length=500)
    estado: str = Field(default="pendiente", max_length=16)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Correo inválido")
        return v

    @field_validator("estado")
    @classmethod
    def _check_estado(cls, v: str) -> str:
        v = (v or "pendiente").strip().lower()
        if v not in ESTADOS_SOLICITUD:
            raise ValueError(
                f"Estado inválido. Usa uno de: {', '.join(ESTADOS_SOLICITUD)}"
            )
        return v


class SolicitudUpdate(BaseModel):
    """Campos editables desde el panel. Todos opcionales (PATCH parcial)."""

    nombre: Optional[str] = Field(default=None, max_length=120)
    email: Optional[str] = Field(default=None, max_length=255)
    telefono: Optional[str] = Field(default=None, max_length=32)
    notas: Optional[str] = Field(default=None, max_length=500)
    estado: Optional[str] = Field(default=None, max_length=16)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: Optional[str]) -> Optional[str]:
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
        if v not in ESTADOS_SOLICITUD:
            raise ValueError(
                f"Estado inválido. Usa uno de: {', '.join(ESTADOS_SOLICITUD)}"
            )
        return v


class SolicitudesResumen(BaseModel):
    total: int
    pendientes: int
    contactados: int


class SolicitudesOut(BaseModel):
    solicitudes: List[SolicitudOut]
    resumen: SolicitudesResumen
    estados: List[str] = list(ESTADOS_SOLICITUD)


@router.get("/access", response_model=AccesoOut)
def check_access(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """¿Esta sesión puede usar el módulo? Lo consulta el menú del frontend
    para mostrar la pestaña solo en la cuenta donde realmente funciona (#288).
    Responde 200 siempre (no filtra nada: solo dice sí o no)."""
    try:
        require_gloma_account(user=user, db=db)
    except HTTPException:
        return AccesoOut(allowed=False)
    return AccesoOut(allowed=True)


@router.post("", response_model=CitaOut, status_code=status.HTTP_201_CREATED)
def create_cita(
    payload: CitaCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Agrega una cita a mano (la que no llegó por el bot). `source='manual'`."""
    cita = models.DemoBooking(
        bot_id=None,
        source="manual",
        **payload.model_dump(),
    )
    db.add(cita)
    db.commit()
    db.refresh(cita)
    logger.info("cita creada manualmente id=%s", cita.id)
    return CitaOut.model_validate(cita)


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


# ===========================================================================
# Solicitudes de contacto (#298) — tabla `leads`
#
# Las rutas viven bajo el mismo router (y por lo tanto bajo la misma
# autorización) porque para el CEO son la otra mitad del mismo trabajo:
# a quién hay que llamar hoy. No colisionan con `/{cita_id}` porque ese
# parámetro es `int` y estas rutas tienen un segmento literal.
# ===========================================================================


def _get_solicitud(db: Session, solicitud_id: int) -> models.Lead:
    solicitud = (
        db.query(models.Lead).filter(models.Lead.id == solicitud_id).first()
    )
    if solicitud is None:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")
    return solicitud


@router.get("/solicitudes", response_model=SolicitudesOut)
def list_solicitudes(
    estado: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Solicitudes "Quiero que me contacten", la más reciente primero."""
    q = db.query(models.Lead)
    if estado:
        q = q.filter(models.Lead.estado == estado.strip().lower())
    solicitudes = q.order_by(models.Lead.created_at.desc()).limit(500).all()

    def _count(valor: str) -> int:
        return db.query(models.Lead).filter(models.Lead.estado == valor).count()

    return SolicitudesOut(
        solicitudes=[SolicitudOut.model_validate(s) for s in solicitudes],
        resumen=SolicitudesResumen(
            total=db.query(models.Lead).count(),
            pendientes=_count("pendiente"),
            contactados=_count("contactado"),
        ),
    )


@router.post(
    "/solicitudes", response_model=SolicitudOut, status_code=status.HTTP_201_CREATED
)
def create_solicitud(
    payload: SolicitudCreate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Agrega una solicitud a mano (la que llegó por otro canal). `source='manual'`."""
    datos = payload.model_dump()
    solicitud = models.Lead(
        email=datos["email"],
        nombre=(datos.get("nombre") or "").strip() or None,
        # `leads.telefono` es NOT NULL desde Sprint 11; en el alta manual puede
        # no conocerse todavía, así que se guarda vacío en vez de inventarlo.
        telefono=(datos.get("telefono") or "").strip(),
        notas=(datos.get("notas") or "").strip() or None,
        estado=datos["estado"],
        source="manual",
    )
    db.add(solicitud)
    db.commit()
    db.refresh(solicitud)
    logger.info("solicitud creada manualmente id=%s", solicitud.id)
    return SolicitudOut.model_validate(solicitud)


@router.patch("/solicitudes/{solicitud_id}", response_model=SolicitudOut)
def update_solicitud(
    solicitud_id: int,
    payload: SolicitudUpdate,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Edita una solicitud: datos de contacto, estado del seguimiento o notas."""
    solicitud = _get_solicitud(db, solicitud_id)

    cambios = payload.model_dump(exclude_unset=True)
    for campo, valor in cambios.items():
        if isinstance(valor, str):
            valor = valor.strip()
            # `telefono` es NOT NULL: vaciarlo guarda "", no NULL.
            valor = valor or ("" if campo == "telefono" else None)
        if campo == "email" and not valor:
            raise HTTPException(status_code=422, detail="El correo es obligatorio")
        setattr(solicitud, campo, valor)
    db.commit()
    db.refresh(solicitud)
    # Sin PII en el log (regla de seguridad #1): solo qué campos cambiaron.
    logger.info(
        "solicitud actualizada id=%s campos=%s",
        solicitud.id,
        ",".join(sorted(cambios)),
    )
    return SolicitudOut.model_validate(solicitud)


@router.delete("/solicitudes/{solicitud_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_solicitud(
    solicitud_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_gloma_account),
):
    """Borra una solicitud (p. ej. spam del formulario o duplicados)."""
    solicitud = _get_solicitud(db, solicitud_id)
    db.delete(solicitud)
    db.commit()
    logger.info("solicitud eliminada id=%s", solicitud_id)
    return None
