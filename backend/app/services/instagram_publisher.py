"""Publicación manual de una pieza de la cola de Instagram (botón del panel).

Réplica server-side del camino de publicación del CLI de marketing
(`marketing/instagram/igpost.py`), porque ese código no viaja en la imagen del
backend. Comparte la MISMA cola en S3, así que el botón y el cron del Mac se
coordinan por el estado de cada pieza:

    pending/failed ──claim──► publishing ──► published
                                  │
                                  └─ error ► pending (reintento) o failed

El *claim* se escribe con precondición de ETag: si el cron reclamó la pieza un
instante antes, la escritura falla y el botón responde 409 en vez de publicar
dos veces. Es la misma barrera que usa el CLI.

Credenciales: token de la cuenta en SSM `/gloma/marketing/instagram/` (por eso
el task role necesita `ssm:GetParameter` sobre ese path). Nunca se loggea.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
import requests
from botocore.exceptions import ClientError

from .instagram_queue import BUCKET, QUEUE_KEY, REGION

logger = logging.getLogger(__name__)

SSM_PREFIX = "/gloma/marketing/instagram"
GRAPH = "https://graph.instagram.com"
API_VERSION = os.getenv("IG_API_VERSION", "v23.0")
TIMEOUT = 60
MAX_ATTEMPTS = 3  # mismo tope que el CLI

PRESIGN_TTL = 3600


class PublishError(RuntimeError):
    """Fallo al publicar (mensaje ya sanitizado para el cliente)."""


class AlreadyClaimed(RuntimeError):
    """Otro proceso (el cron) está publicando esta pieza ahora mismo."""


class NotPublishable(RuntimeError):
    """La pieza no está en un estado publicable (ya salió o está cancelada)."""


def _s3():
    return boto3.client("s3", region_name=REGION)


def _credentials() -> tuple[str, str]:
    """(access_token, ig_user_id) desde SSM. El token NUNCA se loggea."""
    ssm = boto3.client("ssm", region_name=REGION)
    try:
        token = ssm.get_parameter(
            Name=f"{SSM_PREFIX}/ACCESS_TOKEN", WithDecryption=True
        )["Parameter"]["Value"]
        user_id = ssm.get_parameter(Name=f"{SSM_PREFIX}/IG_USER_ID")["Parameter"]["Value"]
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ParameterNotFound":
            raise PublishError("La cuenta de Instagram aún no está conectada.")
        logger.exception("Error leyendo credenciales de Instagram de SSM")
        raise PublishError("No se pudieron leer las credenciales de Instagram.")
    return token, user_id


# ── cola: lectura y escrituras condicionadas ─────────────────────────────────

def _load_raw() -> tuple[list[dict[str, Any]], Optional[str]]:
    obj = _s3().get_object(Bucket=BUCKET, Key=QUEUE_KEY)
    return json.loads(obj["Body"].read()), obj["ETag"]


def _save(items: list[dict[str, Any]], etag: Optional[str]) -> bool:
    """Escritura condicionada. False si la cola cambió desde la lectura."""
    kwargs: dict[str, Any] = {"IfMatch": etag} if etag else {"IfNoneMatch": "*"}
    try:
        _s3().put_object(
            Bucket=BUCKET,
            Key=QUEUE_KEY,
            Body=json.dumps(items, indent=2, ensure_ascii=False).encode(),
            ContentType="application/json",
            **kwargs,
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in (
            "PreconditionFailed",
            "ConditionalRequestConflict",
        ):
            return False
        raise


def _claim(post_id: str) -> dict[str, Any]:
    """pending/failed → publishing, con precondición de ETag."""
    items, etag = _load_raw()
    target = next((i for i in items if i.get("id") == post_id), None)
    if target is None:
        raise NotPublishable("La publicación no existe.")
    if target.get("status") == "publishing":
        raise AlreadyClaimed("Esa pieza se está publicando en este momento.")
    if target.get("status") not in ("pending", "failed"):
        raise NotPublishable(f"La pieza ya está en estado '{target.get('status')}'.")
    target["status"] = "publishing"
    target["claimed_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    if not _save(items, etag):
        raise AlreadyClaimed("Otro proceso tomó la pieza justo antes; reintenta en un momento.")
    return target


def _finish(post_id: str, **changes: Any) -> dict[str, Any]:
    """Actualiza la pieza reintentando si el ETag cambió (pequeño CAS-loop)."""
    for _ in range(5):
        items, etag = _load_raw()
        target = next((i for i in items if i.get("id") == post_id), None)
        if target is None:
            raise PublishError("La publicación desapareció de la cola.")
        target.update(changes)
        if _save(items, etag):
            return target
        time.sleep(0.5)
    raise PublishError("No se pudo actualizar la cola tras varios intentos.")


# ── Graph API ────────────────────────────────────────────────────────────────

def _graph(method: str, path: str, token: str, what: str, **params: Any) -> dict[str, Any]:
    url = f"{GRAPH}/{API_VERSION}/{path}"
    if method == "post":
        resp = requests.post(url, data={**params, "access_token": token}, timeout=TIMEOUT)
    else:
        resp = requests.get(url, params={**params, "access_token": token}, timeout=TIMEOUT)
    try:
        data = resp.json()
    except ValueError:
        logger.error("%s: respuesta no-JSON (HTTP %s)", what, resp.status_code)
        raise PublishError(f"{what}: respuesta inesperada de Instagram.")
    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        logger.error(
            "%s falló (HTTP %s): code=%s msg=%s",
            what, resp.status_code, err.get("code"), err.get("message"),
        )
        raise PublishError(f"{what}: {err.get('message', 'error desconocido')}")
    return data


def _wait_ready(container_id: str, token: str, timeout: int = 180) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = _graph(
            "get", container_id, token, "Estado del contenedor", fields="status_code"
        ).get("status_code")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram rechazó el contenido (estado {status}).")
        time.sleep(5)
    raise PublishError("Instagram no terminó de procesar el contenido a tiempo.")


def _publish_media(media_keys: list[str], caption: str, token: str, user_id: str) -> str:
    s3 = _s3()
    urls = [
        s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET, "Key": k}, ExpiresIn=PRESIGN_TTL
        )
        for k in media_keys
    ]

    if len(urls) == 1:
        container = _graph(
            "post", f"{user_id}/media", token, "Creación del contenedor",
            image_url=urls[0], caption=caption,
        )["id"]
    else:
        children = [
            _graph(
                "post", f"{user_id}/media", token, "Creación del contenedor",
                image_url=u, is_carousel_item="true",
            )["id"]
            for u in urls
        ]
        for child in children:
            _wait_ready(child, token)
        container = _graph(
            "post", f"{user_id}/media", token, "Creación del carrusel",
            media_type="CAROUSEL", children=",".join(children), caption=caption,
        )["id"]

    _wait_ready(container, token)
    return _graph(
        "post", f"{user_id}/media_publish", token, "Publicación", creation_id=container
    )["id"]


# ── entrada del router ───────────────────────────────────────────────────────

def publish_now(post_id: str) -> dict[str, Any]:
    """Publica una pieza de la cola AHORA. Devuelve la entrada actualizada."""
    token, user_id = _credentials()
    post = _claim(post_id)

    try:
        media_id = _publish_media(
            post.get("media_keys") or [], post.get("caption", ""), token, user_id
        )
        permalink = None
        try:
            permalink = _graph(
                "get", media_id, token, "Consulta del permalink", fields="permalink"
            ).get("permalink")
        except PublishError:
            pass
        return _finish(
            post_id,
            status="published",
            media_id=media_id,
            permalink=permalink,
            published_at=datetime.now(timezone.utc).astimezone().isoformat(),
            error=None,
            claimed_at=None,
        )
    except PublishError as exc:
        attempts = int(post.get("attempts", 0)) + 1
        _finish(
            post_id,
            status="failed" if attempts >= MAX_ATTEMPTS else "pending",
            attempts=attempts,
            error=str(exc),
            claimed_at=None,
        )
        raise