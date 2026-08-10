"""Publicaciones de Instagram — módulo interno de la cuenta de Gloma.

Panel de solo lectura sobre la cola que maneja la herramienta de marketing
(`marketing/instagram/igpost.py`): qué piezas están programadas, cuándo salen y
un enlace para descargar el contenido que ya está cargado en S3.

Autorización: igual que `/citas` — solo la cuenta oficial de Gloma y los
miembros de su team. No es un módulo del producto; cualquier otra cuenta recibe
403 aunque tenga sesión válida.

Programar y publicar NO se hace desde aquí: Instagram no tiene API de
programación, así que la cola la escribe el CLI y el cron la ejecuta.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .. import models
from ..dependencies import get_current_user, get_db, require_gloma_account
from ..services import instagram_publisher, instagram_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/instagram", tags=["instagram"])


class AccesoOut(BaseModel):
    allowed: bool


class SlideOut(BaseModel):
    index: int
    filename: str
    download_url: str


class PublicacionOut(BaseModel):
    id: str
    slug: str
    caption: str
    status: str
    publish_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    permalink: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    slides: List[SlideOut] = []


class ResumenOut(BaseModel):
    total: int
    programadas: int
    publicadas: int
    fallidas: int
    canceladas: int


class ColaOut(BaseModel):
    publicaciones: List[PublicacionOut]
    resumen: ResumenOut


@router.get("/access", response_model=AccesoOut)
def check_access(
    user: models.User = Depends(get_current_user),
    db=Depends(get_db),
):
    """¿Esta sesión puede usar el módulo? Lo consulta el menú del frontend para
    mostrar la pestaña solo en la cuenta donde funciona. Responde 200 siempre."""
    try:
        require_gloma_account(user=user, db=db)
    except HTTPException:
        return AccesoOut(allowed=False)
    return AccesoOut(allowed=True)


@router.get("", response_model=ColaOut)
def listar_cola(user: models.User = Depends(require_gloma_account)):
    """Cola completa de publicaciones, con enlaces de descarga de cada slide."""
    try:
        posts = instagram_queue.load_queue()
    except instagram_queue.QueueUnavailable as exc:
        # El detalle ya quedó en el log del servicio (regla de seguridad #6).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )

    publicaciones = [
        PublicacionOut(
            id=p.id,
            slug=p.slug,
            caption=p.caption,
            status=p.status,
            publish_at=p.publish_at,
            published_at=p.published_at,
            permalink=p.permalink,
            error=p.error,
            attempts=p.attempts,
            slides=[
                SlideOut(index=s.index, filename=s.filename, download_url=s.download_url)
                for s in p.slides
            ],
        )
        for p in posts
    ]

    return ColaOut(
        publicaciones=publicaciones,
        resumen=ResumenOut(
            total=len(posts),
            programadas=sum(1 for p in posts if p.status == "pending"),
            publicadas=sum(1 for p in posts if p.status == "published"),
            fallidas=sum(1 for p in posts if p.status == "failed"),
            canceladas=sum(1 for p in posts if p.status == "cancelled"),
        ),
    )


class PublicarOut(BaseModel):
    id: str
    status: str
    media_id: Optional[str] = None
    permalink: Optional[str] = None
    error: Optional[str] = None


@router.post("/{post_id}/publish", response_model=PublicarOut)
def publicar_ahora(
    post_id: str,
    user: models.User = Depends(require_gloma_account),
):
    """Publica AHORA una pieza pendiente (o fallida) de la cola, sin esperar su
    hora programada. El claim con ETag garantiza que si el cron del Mac la está
    publicando en este instante, aquí se responde 409 en vez de duplicarla."""
    try:
        actualizado = instagram_publisher.publish_now(post_id)
    except instagram_publisher.AlreadyClaimed as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except instagram_publisher.NotPublishable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except instagram_publisher.PublishError as exc:
        # El detalle técnico ya quedó en el log del servicio (regla #6).
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return PublicarOut(
        id=actualizado.get("id", post_id),
        status=actualizado.get("status", "published"),
        media_id=actualizado.get("media_id"),
        permalink=actualizado.get("permalink"),
        error=actualizado.get("error"),
    )
