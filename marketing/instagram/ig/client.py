"""Cliente de la Instagram Graph API (flujo *Instagram Login*).

Usamos el flujo de Instagram Login (disponible desde 2024) en lugar del clásico
Facebook Login: una cuenta **Creator** no necesita Página de Facebook vinculada,
lo que simplifica el setup a una sola autorización desde la propia cuenta.

Publicar es un proceso de dos pasos —y para carruseles, de tres:
  1. Un contenedor por cada slide (`is_carousel_item=true`).
  2. Un contenedor padre `media_type=CAROUSEL` con los hijos y el caption.
  3. `media_publish` con el id del contenedor padre.

Los contenedores **expiran a las 24 h**, así que se crean recién en el momento de
publicar, nunca al programar.

Regla de seguridad #6: el detalle de los errores de Meta va a `logger.exception`;
al usuario le llega un mensaje corto y limpio.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

from .config import API_VERSION

logger = logging.getLogger(__name__)

GRAPH = "https://graph.instagram.com"
OAUTH_AUTHORIZE = "https://www.instagram.com/oauth/authorize"
OAUTH_TOKEN = "https://api.instagram.com/oauth/access_token"

SCOPES = ["instagram_business_basic", "instagram_business_content_publish"]

# Instagram permite 100 publicaciones por API en una ventana móvil de 24 h.
# Un carrusel cuenta como una sola publicación.
DAILY_PUBLISH_LIMIT = 100

TIMEOUT = 60


class IGError(RuntimeError):
    """Error al hablar con la API de Instagram (mensaje ya sanitizado)."""


def _check(resp: requests.Response, what: str) -> dict[str, Any]:
    """Parsea la respuesta de Meta, dejando el detalle solo en el log."""
    try:
        data = resp.json()
    except ValueError:
        logger.error("%s: respuesta no-JSON (HTTP %s): %s", what, resp.status_code, resp.text[:500])
        raise IGError(f"{what}: respuesta inesperada de Instagram (HTTP {resp.status_code}).")

    if resp.status_code >= 400 or "error" in data:
        err = data.get("error", {})
        logger.error(
            "%s falló (HTTP %s): code=%s subcode=%s msg=%s",
            what, resp.status_code, err.get("code"), err.get("error_subcode"),
            err.get("message"),
        )
        # El mensaje de Meta es útil y no contiene secretos; lo pasamos tal cual.
        raise IGError(f"{what}: {err.get('message', 'error desconocido')}")
    return data


def authorization_url(app_id: str, redirect_uri: str, state: str = "gloma") -> str:
    """URL que el CEO abre para autorizar la app sobre la cuenta de Gloma."""
    from urllib.parse import urlencode

    return f"{OAUTH_AUTHORIZE}?" + urlencode(
        {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": ",".join(SCOPES),
            "state": state,
        }
    )


def exchange_code(app_id: str, app_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
    """Canjea el `code` de la redirección por un token de corta duración (1 h)."""
    resp = requests.post(
        OAUTH_TOKEN,
        data={
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
            "code": code,
        },
        timeout=TIMEOUT,
    )
    return _check(resp, "Canje del código de autorización")


def to_long_lived(app_secret: str, short_token: str) -> dict[str, Any]:
    """Convierte el token de 1 h en uno de larga duración (60 días)."""
    resp = requests.get(
        f"{GRAPH}/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": short_token,
        },
        timeout=TIMEOUT,
    )
    return _check(resp, "Canje a token de larga duración")


def refresh(long_token: str) -> dict[str, Any]:
    """Renueva un token de larga duración por otros 60 días.

    Meta exige que el token tenga al menos 24 h de vida y no esté vencido.
    """
    resp = requests.get(
        f"{GRAPH}/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": long_token},
        timeout=TIMEOUT,
    )
    return _check(resp, "Renovación del token")


class InstagramClient:
    """Operaciones sobre una cuenta profesional de Instagram ya conectada."""

    def __init__(self, access_token: str, ig_user_id: str, api_version: str = API_VERSION):
        self._token = access_token
        self.ig_user_id = ig_user_id
        self.base = f"{GRAPH}/{api_version}"

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<InstagramClient ig_user_id={self.ig_user_id!r} token=<REDACTED>>"

    def _post(self, path: str, params: dict[str, Any], what: str) -> dict[str, Any]:
        resp = requests.post(
            f"{self.base}/{path}", data={**params, "access_token": self._token}, timeout=TIMEOUT
        )
        return _check(resp, what)

    def _get(self, path: str, params: dict[str, Any], what: str) -> dict[str, Any]:
        resp = requests.get(
            f"{self.base}/{path}", params={**params, "access_token": self._token}, timeout=TIMEOUT
        )
        return _check(resp, what)

    # ── Cuenta ────────────────────────────────────────────────────────────────

    def me(self) -> dict[str, Any]:
        """Datos de la cuenta conectada. Sirve para validar que el token vive."""
        return self._get(
            "me",
            {"fields": "id,username,account_type,media_count,followers_count"},
            "Consulta de la cuenta",
        )

    def published_today(self) -> int:
        """Publicaciones hechas por API en la ventana móvil de 24 h."""
        data = self._get(
            f"{self.ig_user_id}/content_publishing_limit",
            {"fields": "quota_usage,config"},
            "Consulta del límite de publicación",
        )
        entries = data.get("data") or [{}]
        return int(entries[0].get("quota_usage", 0))

    # ── Contenedores ──────────────────────────────────────────────────────────

    def create_image(
        self, image_url: str, *, caption: Optional[str] = None, carousel_item: bool = False
    ) -> str:
        params: dict[str, Any] = {"image_url": image_url}
        if carousel_item:
            params["is_carousel_item"] = "true"
        if caption is not None:
            params["caption"] = caption
        data = self._post(f"{self.ig_user_id}/media", params, "Creación del contenedor de imagen")
        return data["id"]

    def create_carousel(self, children: list[str], caption: str) -> str:
        if not 2 <= len(children) <= 10:
            raise IGError(
                f"Un carrusel debe tener entre 2 y 10 slides; se recibieron {len(children)}."
            )
        data = self._post(
            f"{self.ig_user_id}/media",
            {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption},
            "Creación del carrusel",
        )
        return data["id"]

    def container_status(self, container_id: str) -> str:
        data = self._get(
            container_id, {"fields": "status_code"}, "Consulta del estado del contenedor"
        )
        return data.get("status_code", "UNKNOWN")

    def wait_ready(self, container_id: str, *, timeout: int = 180, interval: int = 5) -> None:
        """Espera a que Meta termine de procesar el contenedor."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            status = self.container_status(container_id)
            if status == "FINISHED":
                return
            if status in ("ERROR", "EXPIRED"):
                raise IGError(f"Instagram rechazó el contenido (estado {status}).")
            time.sleep(interval)
        raise IGError(f"El contenedor {container_id} no quedó listo en {timeout}s.")

    # ── Publicación ───────────────────────────────────────────────────────────

    def publish(self, creation_id: str) -> str:
        data = self._post(
            f"{self.ig_user_id}/media_publish",
            {"creation_id": creation_id},
            "Publicación",
        )
        return data["id"]

    def permalink(self, media_id: str) -> Optional[str]:
        try:
            return self._get(media_id, {"fields": "permalink"}, "Consulta del permalink").get(
                "permalink"
            )
        except IGError:
            return None
