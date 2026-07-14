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


_ORDER_FIELDS = (
    "name,created_at,financial_status,fulfillment_status,order_status_url,"
    "customer,note_attributes,shipping_address,billing_address"
)


def _fetch_orders(
    shop: str, token: str, params: Dict[str, Any]
) -> list[Dict[str, Any]]:
    resp = httpx.get(
        f"https://{shop}/admin/api/{API_VERSION}/orders.json",
        params={"status": "any", "fields": _ORDER_FIELDS, **params},
        headers={"X-Shopify-Access-Token": token},
        timeout=_TIMEOUT,
    )
    if resp.status_code == 401:
        # token vencido/revocado: invalidar cache para reintentar en el próximo turno
        _token_cache.pop(shop, None)
        raise ShopifyError("credenciales Shopify rechazadas")
    if resp.status_code != 200:
        raise ShopifyError(f"orders.json devolvió {resp.status_code}")
    return (resp.json() or {}).get("orders") or []


def _norm(s: str) -> str:
    """minúsculas y sin tildes, para comparar nombres."""
    import unicodedata

    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _order_names(order: Dict[str, Any]) -> list[str]:
    cust = order.get("customer") or {}
    out = [f"{cust.get('first_name') or ''} {cust.get('last_name') or ''}"]
    for addr_key in ("shipping_address", "billing_address"):
        name = (order.get(addr_key) or {}).get("name")
        if name:
            out.append(name)
    attrs = {a.get("name"): a.get("value") for a in order.get("note_attributes") or []}
    if attrs.get("Nombre") or attrs.get("Apellido"):
        out.append(f"{attrs.get('Nombre') or ''} {attrs.get('Apellido') or ''}")
    return [n for n in out if n.strip()]


def _order_documents(order: Dict[str, Any]) -> list[str]:
    """Cédula/documento: viene en note_attributes ('Número de documento') y
    espejada en shipping/billing_address.company en pedidos web."""
    docs = []
    for a in order.get("note_attributes") or []:
        if "documento" in _norm(a.get("name") or "") and a.get("value"):
            docs.append(str(a["value"]))
    for addr_key in ("shipping_address", "billing_address"):
        comp = (order.get(addr_key) or {}).get("company")
        if comp:
            docs.append(str(comp))
    return docs


def _order_summary(order: Dict[str, Any]) -> Dict[str, Any]:
    cust = order.get("customer") or {}
    cliente = f"{cust.get('first_name') or ''} {cust.get('last_name') or ''}".strip()
    return {
        "pedido": order.get("name"),
        "fecha": (order.get("created_at") or "")[:10],
        "cliente": cliente or None,
        "estado_pago": order.get("financial_status"),
        "estado_envio": order.get("fulfillment_status") or "sin despachar",
        "url_rastreo": order.get("order_status_url"),
    }


def search_orders(
    *,
    shop: str,
    client_id: str,
    encrypted_client_secret: str,
    numero: str = "",
    nombre: str = "",
    documento: str = "",
    fecha: str = "",
) -> Dict[str, Any]:
    """Busca pedidos por número, nombre del cliente, documento y/o fecha.

    - `numero`: búsqueda exacta por name en la API.
    - `fecha` (YYYY-MM-DD): acota con created_at_min/max en la API.
    - `nombre` / `documento`: se filtran EN EL BACKEND sobre los pedidos
      recientes (la app no tiene scope read_customers para /customers/search).
    Devuelve hasta 3 coincidencias, apto para que el LLM redacte la respuesta.
    """
    if not (shop and client_id and encrypted_client_secret):
        raise ShopifyError("configuración Shopify incompleta")
    numero = re.sub(r"[^0-9A-Za-z\-]", "", numero or "")
    documento_d = re.sub(r"[^0-9]", "", documento or "")
    if not (numero or nombre.strip() or documento_d or fecha.strip()):
        return {"encontrado": False,
                "detalle": "se necesita número, nombre, documento o fecha"}

    token = _get_token(shop, client_id, encrypted_client_secret)

    if numero:
        orders = _fetch_orders(shop, token, {"name": numero, "limit": 5})
    else:
        params: Dict[str, Any] = {"limit": 100, "order": "created_at desc"}
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha or ""):
            # Día completo en hora Colombia (UTC-5).
            params["created_at_min"] = f"{fecha}T00:00:00-05:00"
            params["created_at_max"] = f"{fecha}T23:59:59-05:00"
        orders = _fetch_orders(shop, token, params)

    nombre_n = _norm(nombre)
    matches = []
    for o in orders:
        if nombre_n and not any(nombre_n in _norm(n) for n in _order_names(o)):
            continue
        if documento_d and documento_d not in _order_documents(o):
            continue
        matches.append(o)

    if not matches:
        return {
            "encontrado": False,
            "detalle": "sin coincidencias" + (
                " en los pedidos recientes (si el pedido es antiguo, pedir el número)"
                if not numero else ""
            ),
        }
    return {
        "encontrado": True,
        "total_coincidencias": len(matches),
        "pedidos": [_order_summary(o) for o in matches[:3]],
    }


def get_order_status(
    *, shop: str, client_id: str, encrypted_client_secret: str, order_name: str
) -> Dict[str, Any]:
    """Compat: estado de un pedido por número (usa search_orders)."""
    return search_orders(
        shop=shop, client_id=client_id,
        encrypted_client_secret=encrypted_client_secret, numero=order_name,
    )
