"""Conecta el bot de Natulcé con su hoja de pedidos en Drive.

Guarda en `bots.llm_config` la URL del Apps Script de la hoja, **cifrada con
Fernet**: quien la tenga puede escribir filas en la hoja del cliente, así que
es un secreto del tenant y vive en la base cifrado, nunca en el repositorio
(regla de seguridad #3).

Antes de correrlo hay que publicar el script de la hoja. Son tres pasos, se
hacen una sola vez, y el código está en el encabezado de
`app/services/pedidos_sheet.py`:

  1. En la hoja: Extensiones → Apps Script. Pegar el `doPost` y poner el mismo
     `TOKEN` que se pase aquí.
  2. Implementar → Nueva implementación → Aplicación web.
     Ejecutar como **yo**; con acceso **cualquier usuario**.
  3. Copiar la URL que termina en `/exec`. Ésa es la que se pasa aquí.

La URL **no** se imprime de vuelta ni se loggea, y viaja por env var — nunca
como argumento de línea de comandos, que queda en el historial del shell.

Uso:
    # Local
    docker compose -p wati exec -T backend env \\
        PEDIDOS_WEBHOOK_URL='https://script.google.com/.../exec' \\
        PEDIDOS_TOKEN='...' python scripts/configurar_pedidos_natulce.py

    # Producción (RDS). OJO: los overrides de ECS quedan en CloudTrail, así que
    # la URL se pasa YA CIFRADA (se cifra antes con este mismo script en
    # `--solo-cifrar`, que no toca la base).
    ./backend/scripts/rds_exec.sh backend/scripts/configurar_pedidos_natulce.py \\
        PEDIDOS_WEBHOOK_CIFRADA='gAAAAA...' PEDIDOS_TOKEN='...'

ENV:
    PEDIDOS_WEBHOOK_URL       URL del Apps Script en claro (local)
    PEDIDOS_WEBHOOK_CIFRADA   la misma URL ya cifrada con Fernet (producción)
    PEDIDOS_TOKEN             token compartido que valida el script
    SOLO_CIFRAR=1             imprime la URL cifrada y no toca la base
    NATULCE_EMAIL             default natulce@demo.com
"""
from __future__ import annotations

import json
import os
import sys

_RAIZ = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "__file__" in globals()
    else "/app"
)
sys.path.insert(0, _RAIZ)

from app import crud, models  # type: ignore
from app.database import SessionLocal  # type: ignore
from app.services.crypto import encrypt_secret  # type: ignore


OWNER_EMAIL = os.environ.get("NATULCE_EMAIL", "natulce@demo.com")


def main() -> int:
    url = (os.environ.get("PEDIDOS_WEBHOOK_URL") or "").strip()
    cifrada = (os.environ.get("PEDIDOS_WEBHOOK_CIFRADA") or "").strip()
    token = (os.environ.get("PEDIDOS_TOKEN") or "").strip()

    if not url and not cifrada:
        return _abortar(
            "Falta PEDIDOS_WEBHOOK_URL (o PEDIDOS_WEBHOOK_CIFRADA). "
            "La URL no va en el código: este repositorio es público."
        )
    if url and not url.startswith("https://"):
        return _abortar("La URL del Apps Script debe ser https.")

    if url and not cifrada:
        cifrada = encrypt_secret(url)

    if os.environ.get("SOLO_CIFRAR", "").strip() not in ("", "0", "false"):
        # Lo único que se imprime es el texto cifrado, que sin la clave maestra
        # no sirve de nada. La URL en claro nunca sale por stdout.
        print(cifrada)
        return 0

    db = SessionLocal()
    try:
        owner = crud.get_user_by_email(db, OWNER_EMAIL)
        if owner is None:
            return _abortar(f"No existe {OWNER_EMAIL} en esta base.")
        bot = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id)
            .order_by(models.Bot.id.desc())
            .first()
        )
        if bot is None:
            return _abortar(f"{OWNER_EMAIL} no tiene bot. Corre seed_bot_natulce.py.")

        cfg = json.loads(bot.llm_config or "{}")
        pedidos = cfg.get("pedidos")
        if not isinstance(pedidos, dict):
            pedidos = {"hoja": "Pedidos Natulcé — WhatsApp"}
        pedidos["encrypted_webhook_url"] = cifrada
        if token:
            pedidos["token"] = token
        cfg["pedidos"] = pedidos
        bot.llm_config = json.dumps(cfg, ensure_ascii=False)
        db.commit()

        print(f"OK: bot {bot.id} ({bot.name}) conectado a la hoja de pedidos")
        print(f"    hoja:  {pedidos.get('hoja')}")
        print(f"    token: {'sí' if pedidos.get('token') else 'NO (el script acepta cualquiera)'}")
        return 0
    finally:
        db.close()


def _abortar(mensaje: str) -> int:
    print(f"ERROR: {mensaje}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
