"""Cliente mínimo de Shopify Admin API para el motor de bots LLM (Sprint 19).

Reproduce la integración que tenía el bot WATI de Talulah:
  1. POST /admin/oauth/access_token (grant client_credentials) → access_token
     (expira en ~24h; se cachea en memoria por shop con margen de seguridad).
  2. GET /admin/api/{ver}/orders.json?name=<numero> con X-Shopify-Access-Token.

El `client_secret` es secreto de tenant: llega SIEMPRE cifrado (Fernet, columna
`bots.llm_config`) y se descifra solo en memoria al pedir token (regla #3).
Nunca se loggea (regla #1).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict

import httpx

logger = logging.getLogger(__name__)

API_VERSION = "2025-10"
_TIMEOUT = 10.0

# Cache de tokens por shop: {shop: (token, expira_epoch)}
_token_cache: Dict[str, tuple[str, float]] = {}


class ShopifyError(Exception):
    pass


def _get_token(shop: str, client_id: str, encrypted_client_secret: str) -> str:
    cached = _token_cache.get(shop)
    if cached and cached[1] > time.time():
        return cached[0]

    # Import perezoso: crypto exige APP_ENCRYPTION_KEY al usarse; así el módulo
    # (y llm_engine) se pueden importar sin esa env var (p. ej. en tests).
    from .crypto import decrypt_secret

    secret = decrypt_secret(encrypted_client_secret)
    resp = httpx.post(
        f"https://{shop}/admin/oauth/access_token",
        json={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": secret,
        },
        timeout=_TIMEOUT,
    )
    if resp.status_code != 200:
        raise ShopifyError(f"token exchange devolvió {resp.status_code}")
    data = resp.json()
    token = data.get("access_token")
    if not token:
        raise ShopifyError("token exchange sin access_token")
    # margen de 60s antes del expires_in real (~86400s)
    expires = time.time() + max(int(data.get("expires_in", 3600)) - 60, 60)
    _token_cache[shop] = (token, expires)
    return token


def get_order_status(
    *, shop: str, client_id: str, encrypted_client_secret: str, order_name: str
) -> Dict[str, Any]:
    """Estado de un pedido por número. Devuelve dict apto para el LLM."""
    if not (shop and client_id and encrypted_client_secret):
        raise ShopifyError("configuración Shopify incompleta")
    numero = re.sub(r"[^0-9A-Za-z\-]", "", order_name or "")
    if not numero:
        return {"encontrado": False, "detalle": "número de pedido vacío"}

    token = _get_token(shop, client_id, encrypted_client_secret)
    resp = httpx.get(
        f"https://{shop}/admin/api/{API_VERSION}/orders.json",
        params={
            "status": "any",
            "name": numero,
            "fields": "name,financial_status,fulfillment_status,order_status_url",
        },
        headers={"X-Shopify-Access-Token": token},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 401:
        # token vencido/revocado: invalidar cache para reintentar en el próximo turno
        _token_cache.pop(shop, None)
        raise ShopifyError("credenciales Shopify rechazadas")
    if resp.status_code != 200:
        raise ShopifyError(f"orders.json devolvió {resp.status_code}")

    orders = (resp.json() or {}).get("orders") or []
    if not orders:
        return {"encontrado": False}
    order = orders[0]
    return {
        "encontrado": True,
        "pedido": order.get("name"),
        "estado_pago": order.get("financial_status"),
        "estado_envio": order.get("fulfillment_status") or "sin despachar",
        "url_rastreo": order.get("order_status_url"),
    }
