"""Endpoints públicos de la landing Gloma."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/landing", tags=["landing"])


PHONE_RE = re.compile(r"^[+\d][\d\s\-()]{5,30}$")


class LeadIn(BaseModel):
    email: EmailStr
    telefono: str = Field(..., min_length=6, max_length=32)
    source: str = Field(default="gloma_landing", max_length=64)

    @field_validator("telefono")
    @classmethod
    def _strip_phone(cls, v: str) -> str:
        v = (v or "").strip()
        if not PHONE_RE.match(v):
            raise ValueError("Teléfono inválido")
        return v

    @field_validator("source")
    @classmethod
    def _strip_source(cls, v: str) -> str:
        return (v or "").strip() or "gloma_landing"


class LeadOut(BaseModel):
    ok: bool = True


@router.post("/leads", response_model=LeadOut)
def create_lead(
    payload: LeadIn, request: Request, db: Session = Depends(get_db)
):
    """Guarda un lead del form de contacto. Público (sin auth).

    Rate-limit MVP en memoria: max 5 leads/IP/hora.
    """
    ip = (request.client.host if request.client else "unknown")[:60]
    ua = (request.headers.get("user-agent") or "")[:500]

    # Rate-limit básico
    since = datetime.utcnow() - timedelta(hours=1)
    count = (
        db.query(models.Lead)
        .filter(models.Lead.ip_address == ip, models.Lead.created_at >= since)
        .count()
    )
    if count >= 5:
        raise HTTPException(
            status_code=429,
            detail="Hemos recibido demasiadas solicitudes desde tu conexión. Intenta más tarde.",
        )

    lead = models.Lead(
        email=str(payload.email).lower(),
        telefono=payload.telefono,
        source=payload.source,
        user_agent=ua,
        ip_address=ip,
    )
    db.add(lead)
    db.commit()
    logger.info("lead creado id=%s source=%s", lead.id, lead.source)
    return LeadOut(ok=True)
