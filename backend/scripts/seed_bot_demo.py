"""Seed idempotente: crea un bot demo de 5 pasos para el team de prueba@gmail.com.

Sprint 8 — visualización read-only. Este script permite que el usuario
`prueba@gmail.com` vea al menos un bot en la UI sin pasar por un editor.

Comportamiento:
  - Si el usuario no existe → aborta con código 1 (se debe registrar primero).
  - Si el usuario ya tiene un bot con el nombre `catalogo_talulah` → no hace nada.
  - Si no lo tiene → crea el bot con 5 pasos lineales.

Uso:
    docker compose exec backend python backend/scripts/seed_bot_demo.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models  # type: ignore


DEMO_OWNER_EMAIL = os.environ.get("DEMO_OWNER_EMAIL", "prueba@gmail.com")
DEMO_BOT_NAME = "catalogo_talulah"

DEMO_STEPS = [
    {
        "step_type": "send_text",
        "label": "Saludo inicial",
        "config": {
            "text": "¡Hola! 👋 Bienvenido a Tienda Zeniv. Soy tu asistente virtual.",
        },
    },
    {
        "step_type": "wait_input",
        "label": "Pregunta menú",
        "config": {
            "prompt": "¿En qué te puedo ayudar hoy?",
            "options": ["1) Ver catálogo", "2) Mis pedidos", "3) Hablar con un humano"],
        },
    },
    {
        "step_type": "send_media",
        "label": "Enviar catálogo",
        "config": {
            "media_type": "image",
            "caption": "Aquí tienes nuestro catálogo de esta temporada 🛍️",
            "url_placeholder": "https://ejemplo.com/catalogo.pdf",
        },
    },
    {
        "step_type": "condition",
        "label": "¿Quiere algo más?",
        "config": {
            "prompt": "¿Deseas seguir explorando o cerrar la conversación?",
            "branches": {
                "seguir": "Volver al menú",
                "cerrar": "Terminar",
            },
        },
    },
    {
        "step_type": "end",
        "label": "Cierre",
        "config": {
            "text": "Gracias por contactarnos 🙏. Un asesor te escribirá muy pronto.",
        },
    },
]


def main() -> int:
    db = SessionLocal()
    try:
        owner = crud.get_user_by_email(db, DEMO_OWNER_EMAIL)
        if owner is None:
            print(f"ERROR: usuario {DEMO_OWNER_EMAIL} no existe. Regístralo primero.")
            return 1

        membership = crud.get_membership_for_user(db, owner)
        if membership is None:
            print(f"ERROR: {DEMO_OWNER_EMAIL} no tiene team. Haz login una vez para auto-provisionarlo.")
            return 1

        print(f"Usuario: {owner.correo} (id={owner.id})")

        existing = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id, models.Bot.name == DEMO_BOT_NAME)
            .first()
        )
        if existing:
            print(f"Ya existe el bot {DEMO_BOT_NAME!r} (id={existing.id}). Nada por hacer.")
            return 0

        # Bot 1: default (catch-all para mensajes nuevos)
        bot = crud.create_bot_with_steps(
            db,
            owner,
            name=DEMO_BOT_NAME,
            description="Bot demo de 5 pasos — catálogo Talulah.",
            channels=[models.BOT_CHANNEL_WHATSAPP],
            trigger_type=models.BOT_TRIGGER_DEFAULT,
            trigger_config=None,
            steps=DEMO_STEPS,
        )
        print(f"Creado bot id={bot.id} ({bot.trigger_type}) con {len(bot.steps)} pasos.")

        # Bot 2: activado por keyword
        second_exists = (
            db.query(models.Bot)
            .filter(
                models.Bot.user_id == owner.id,
                models.Bot.name == "Confirmación de pedido",
            )
            .first()
        )
        if not second_exists:
            bot2 = crud.create_bot_with_steps(
                db,
                owner,
                name="Confirmación de pedido",
                description="Bot de confirmación post-compra (demo).",
                channels=[
                    models.BOT_CHANNEL_WHATSAPP,
                    models.BOT_CHANNEL_INSTAGRAM,
                    models.BOT_CHANNEL_MESSENGER,
                ],
                trigger_type=models.BOT_TRIGGER_KEYWORD,
                trigger_config={"keywords": ["pedido", "compra", "orden"]},
                steps=[
                    {
                        "step_type": "send_text",
                        "label": "Confirmación",
                        "config": {"text": "¡Gracias por tu compra! Tu pedido ha sido recibido."},
                    },
                    {
                        "step_type": "delay",
                        "label": "Pausa 2h",
                        "config": {"seconds": 7200},
                    },
                    {
                        "step_type": "send_text",
                        "label": "Seguimiento",
                        "config": {"text": "Tu pedido ya está en preparación 📦."},
                    },
                    {
                        "step_type": "end",
                        "label": "Fin",
                        "config": {"text": "¡Hasta pronto!"},
                    },
                ],
            )
            print(f"Creado bot id={bot2.id} ({bot2.trigger_type}).")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
