"""Cola de publicaciones programadas.

La API de Instagram **no permite programar**: los contenedores de media expiran
a las 24 h y no existe ningún parámetro de fecha futura. Así que la programación
la llevamos nosotros: aquí queda la cola, y `igpost.py run-due` la revisa
periódicamente y publica lo que ya venció.

La cola vive en S3 (el mismo bucket que las imágenes) y no en disco, para que el
runner programado pueda leerla sin depender del Mac. Las escrituras usan
optimistic locking con el ETag: si dos procesos escriben a la vez, el segundo
falla en vez de pisar al primero.
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional

import boto3
from botocore.exceptions import ClientError

from .config import AWS_REGION, MEDIA_BUCKET

logger = logging.getLogger(__name__)

QUEUE_KEY = "queue/schedule.json"

# 'publishing' es un estado transitorio: alguien (el cron o el botón del panel)
# reclamó la pieza y está llamando a la API. Evita la publicación doble.
Status = Literal["pending", "publishing", "published", "failed", "cancelled"]


class QueueConflict(RuntimeError):
    """Otro proceso modificó la cola mientras escribíamos."""


@dataclass
class ScheduledPost:
    id: str
    slug: str
    caption: str
    media_keys: list[str]
    publish_at: str                      # ISO 8601 con zona horaria
    status: Status = "pending"
    created_at: str = ""
    published_at: Optional[str] = None
    media_id: Optional[str] = None
    permalink: Optional[str] = None
    error: Optional[str] = None
    attempts: int = 0
    # Cuándo se reclamó ('publishing'). Permite rescatar piezas que quedaron
    # atascadas si el proceso murió a mitad de la publicación.
    claimed_at: Optional[str] = None

    @property
    def due_at(self) -> datetime:
        return datetime.fromisoformat(self.publish_at)

    def is_due(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now(timezone.utc)
        return self.status == "pending" and self.due_at <= now


def _s3():
    return boto3.client("s3", region_name=AWS_REGION)


def _load_raw() -> tuple[list[dict[str, Any]], Optional[str]]:
    try:
        obj = _s3().get_object(Bucket=MEDIA_BUCKET, Key=QUEUE_KEY)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            return [], None
        raise
    return json.loads(obj["Body"].read()), obj["ETag"]


def load() -> list[ScheduledPost]:
    raw, _ = _load_raw()
    return [ScheduledPost(**item) for item in raw]


def _save(posts: list[ScheduledPost], etag: Optional[str]) -> None:
    """Guarda la cola. Falla si cambió desde que la leímos."""
    kwargs: dict[str, Any] = {}
    if etag:
        kwargs["IfMatch"] = etag
    else:
        kwargs["IfNoneMatch"] = "*"
    try:
        _s3().put_object(
            Bucket=MEDIA_BUCKET,
            Key=QUEUE_KEY,
            Body=json.dumps([asdict(p) for p in posts], indent=2, ensure_ascii=False).encode(),
            ContentType="application/json",
            **kwargs,
        )
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("PreconditionFailed", "ConditionalRequestConflict"):
            raise QueueConflict(
                "La cola cambió mientras se escribía. Reintenta el comando."
            ) from exc
        raise


def add(slug: str, caption: str, media_keys: list[str], publish_at: datetime) -> ScheduledPost:
    raw, etag = _load_raw()
    posts = [ScheduledPost(**item) for item in raw]
    post = ScheduledPost(
        id=uuid.uuid4().hex[:8],
        slug=slug,
        caption=caption,
        media_keys=media_keys,
        publish_at=publish_at.isoformat(),
        created_at=datetime.now(timezone.utc).astimezone().isoformat(),
    )
    posts.append(post)
    posts.sort(key=lambda p: p.publish_at)
    _save(posts, etag)
    return post


def update(post_id: str, **changes: Any) -> ScheduledPost:
    raw, etag = _load_raw()
    posts = [ScheduledPost(**item) for item in raw]
    target = next((p for p in posts if p.id == post_id), None)
    if target is None:
        raise KeyError(f"No existe una publicación con id {post_id}")
    for key, value in changes.items():
        setattr(target, key, value)
    _save(posts, etag)
    return target


def due(now: Optional[datetime] = None) -> list[ScheduledPost]:
    return [p for p in load() if p.is_due(now)]


def claim(post_id: str) -> Optional[ScheduledPost]:
    """Reclama una pieza para publicarla: pending/failed → publishing.

    Relee la cola y escribe con IfMatch, así que si otro proceso (el cron o el
    botón del panel) la reclamó un instante antes, esta llamada devuelve None y
    el llamador simplemente no publica. Es la barrera anti-duplicados.
    """
    raw, etag = _load_raw()
    posts = [ScheduledPost(**item) for item in raw]
    target = next((p for p in posts if p.id == post_id), None)
    if target is None or target.status not in ("pending", "failed"):
        return None
    target.status = "publishing"
    target.claimed_at = datetime.now(timezone.utc).astimezone().isoformat()
    try:
        _save(posts, etag)
    except QueueConflict:
        return None
    return target


# Una pieza 'publishing' más vieja que esto quedó huérfana (el proceso murió a
# mitad de camino): run-due la devuelve a 'pending' para reintentarla.
STALE_CLAIM_MINUTES = 30


def rescue_stale(now: Optional[datetime] = None) -> list[ScheduledPost]:
    from datetime import timedelta

    now = now or datetime.now(timezone.utc)
    rescued = []
    for p in load():
        if p.status != "publishing" or not p.claimed_at:
            continue
        edad = now - datetime.fromisoformat(p.claimed_at)
        if edad > timedelta(minutes=STALE_CLAIM_MINUTES):
            rescued.append(update(p.id, status="pending", claimed_at=None))
    return rescued
