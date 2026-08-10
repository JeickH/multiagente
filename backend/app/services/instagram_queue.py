"""Lectura de la cola de publicaciones de Instagram (módulo interno de Gloma).

La cola la escribe la herramienta de marketing `marketing/instagram/igpost.py`,
que vive fuera del producto. La fuente de verdad es un JSON en S3:

    s3://<bucket>/queue/schedule.json      ← la cola
    s3://<bucket>/posts/<slug>/NN-<hash>.jpg  ← las slides ya subidas

Aquí solo se **lee**: el panel muestra qué hay en cola, cuándo se publica cada
pieza y da un enlace de descarga de cada slide. Programar y publicar sigue
siendo responsabilidad del CLI de marketing.

Las descargas se sirven con URLs prefirmadas de vida corta — el bucket es
privado y no se expone nunca de forma pública.

Config por `os.getenv` (mismo patrón que `llm_engine.py`): las credenciales AWS
las provee el IAM task role en ECS y `~/.aws` en local.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

BUCKET = os.getenv("IG_MEDIA_BUCKET", "gloma-marketing-media-747456040509")
REGION = os.getenv("IG_MEDIA_REGION", os.getenv("AWS_DEFAULT_REGION", "sa-east-1"))
QUEUE_KEY = "queue/schedule.json"

# Vida de los enlaces de descarga. Corta a propósito: el panel los regenera en
# cada carga, así que no hace falta que sobrevivan a la sesión.
DOWNLOAD_TTL = 3600


class QueueUnavailable(RuntimeError):
    """No se pudo leer la cola (mensaje ya sanitizado para el cliente)."""


@dataclass
class Slide:
    index: int
    filename: str
    key: str
    download_url: str


@dataclass
class QueuedPost:
    id: str
    slug: str
    caption: str
    status: str
    publish_at: Optional[datetime]
    published_at: Optional[datetime]
    permalink: Optional[str]
    error: Optional[str]
    attempts: int
    slides: list[Slide]


def _client():
    return boto3.client("s3", region_name=REGION)


def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        logger.warning("Fecha ilegible en la cola de Instagram: %r", raw)
        return None


def _slides_for(s3, item: dict[str, Any]) -> list[Slide]:
    slides: list[Slide] = []
    for i, key in enumerate(item.get("media_keys") or [], start=1):
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": BUCKET,
                "Key": key,
                # Fuerza descarga en vez de abrir la imagen en el navegador.
                "ResponseContentDisposition": (
                    f'attachment; filename="{item.get("slug", "slide")}_{i:02d}.jpg"'
                ),
            },
            ExpiresIn=DOWNLOAD_TTL,
        )
        slides.append(
            Slide(index=i, filename=key.rsplit("/", 1)[-1], key=key, download_url=url)
        )
    return slides


def load_queue() -> list[QueuedPost]:
    """Devuelve la cola completa, más reciente primero por fecha de publicación.

    Si la cola todavía no existe (nadie ha programado nada), devuelve lista
    vacía en vez de error: es un estado válido, no una falla.
    """
    s3 = _client()
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=QUEUE_KEY)
        raw = json.loads(obj["Body"].read())
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404"):
            return []
        if code in ("NoSuchBucket",):
            logger.error("El bucket de marketing %s no existe", BUCKET)
            raise QueueUnavailable("La cola de publicaciones aún no está configurada.")
        logger.exception("Error de S3 leyendo la cola de Instagram")
        raise QueueUnavailable("No se pudo leer la cola de publicaciones.")
    except (BotoCoreError, ValueError):
        logger.exception("Error leyendo/parseando la cola de Instagram")
        raise QueueUnavailable("No se pudo leer la cola de publicaciones.")

    posts = [
        QueuedPost(
            id=item.get("id", ""),
            slug=item.get("slug", ""),
            caption=item.get("caption", ""),
            status=item.get("status", "pending"),
            publish_at=_parse_dt(item.get("publish_at")),
            published_at=_parse_dt(item.get("published_at")),
            permalink=item.get("permalink"),
            error=item.get("error"),
            attempts=int(item.get("attempts", 0)),
            slides=_slides_for(s3, item),
        )
        for item in raw
    ]
    # Lo próximo a publicarse primero; lo ya publicado, al final. El fallback es
    # aware: la cola guarda fechas con zona horaria y comparar aware con naive
    # revienta.
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    posts.sort(key=lambda p: (p.status != "pending", p.publish_at or epoch))
    return posts
