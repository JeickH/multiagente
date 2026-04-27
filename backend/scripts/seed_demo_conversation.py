"""Seed idempotente: bandeja de mensajes demo para demo@gmail.com.

Genera 5 conversaciones para que la UI de /mensajes se vea poblada para
screenshots de la landing:
  1. Mariana López — conversación larga sobre dimensiones de una blusa
     (la única que se va a abrir en el screenshot).
  2-5. Conversaciones cortas (1-2 mensajes) variando status (open/pending/
     closed) y timestamps escalonados — solo aparecen en la lista lateral.

Aislamiento: todo queda asociado al `team_id` de demo@gmail.com.

Uso:
    docker compose exec backend python scripts/seed_demo_conversation.py
"""
from __future__ import annotations

from datetime import datetime, timedelta
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models  # type: ignore


DEMO_EMAIL = "demo@gmail.com"


# ===== Conversación principal (larga) =====
MAIN_CONTACT = {"wa_id": "573008765432", "name": "Mariana López"}

# (direction, content, minutos_atrás_relativo_a_now)
MAIN_MESSAGES = [
    ("inbound",  "Hola, buenas tardes 👋", 12),
    ("outbound", "¡Hola Mariana! 👋 Bienvenida a Gloma. Soy Aurora, tu asistente virtual. ¿En qué puedo ayudarte hoy?", 11),
    ("inbound",  "Quería preguntar por la blusa de lino color crema que vi en su catálogo", 10),
    ("outbound", "¡Claro! Es una de nuestras prendas estrella esta temporada 🌿. ¿Tienes alguna pregunta puntual sobre ella?", 9),
    ("inbound",  "Sí, necesito saber las dimensiones, talla S por favor", 8),
    (
        "outbound",
        "Para la talla S las medidas son:\n"
        "• Ancho de pecho: 46 cm\n"
        "• Largo total: 62 cm\n"
        "• Manga: 18 cm\n\n"
        "La tela es 100% lino con caída suave y la talla tiene un fit holgado tipo oversize. "
        "¿Quieres que te comparta también las medidas de otras tallas?",
        7,
    ),
    ("inbound",  "Perfecta, muchas gracias!", 5),
    (
        "outbound",
        "¡Con gusto! 💕 Si te animas a llevarla puedo ayudarte con el pedido en este "
        "mismo chat. ¿Te gustaría que te muestre cómo combinarla?",
        4,
    ),
]


# ===== 4 conversaciones cortas =====
# Cada una tiene su `last_message_at` definido por el último mensaje.
SHORT_CONVERSATIONS = [
    {
        "wa_id": "573157894521",
        "name": "Valentina Ruiz",
        "status": "open",
        "messages": [
            ("inbound",  "Hola, ¿tienen el vestido floral en talla M? 🌸", 38),
            ("outbound", "¡Hola Valentina! Sí lo tenemos. Te comparto el catálogo en un momento.", 35),
        ],
    },
    {
        "wa_id": "573201478965",
        "name": "Camila Torres",
        "status": "pending",
        "messages": [
            ("inbound", "¿Cuándo vuelven a tener stock del kimono crema? 🥺", 62),
        ],
    },
    {
        "wa_id": "573102589654",
        "name": "Lucía Ramírez",
        "status": "open",
        "messages": [
            ("inbound",  "Hola, ¿se puede pagar contra entrega? 🤔", 125),
            ("outbound", "¡Sí, Lucía! Aceptamos contra entrega en Bogotá, Medellín y Cali. ¿En qué ciudad estás?", 122),
        ],
    },
    {
        "wa_id": "573158963214",
        "name": "Sara Mendoza",
        "status": "closed",
        "messages": [
            ("inbound",  "Gracias por el envío, todo llegó perfecto 💕", 305),
            ("outbound", "¡Qué alegría leerte, Sara! Nos encanta que te haya gustado. Esperamos verte pronto por acá ✨", 302),
        ],
    },
]


def _seed_conv(db, owner, team_id, *, wa_id, name, messages, status="open") -> str:
    """Crea conversación + mensajes si falta. Devuelve la acción ('nuevo'|'skip')."""
    conv = crud.get_or_create_conversation(
        db, team_id=team_id, contact_wa_id=wa_id, contact_name=name,
    )
    if conv.messages:
        return "skip"

    now = datetime.utcnow()
    for direction, content, mins_ago in messages:
        ts = now - timedelta(minutes=mins_ago)
        msg_status = "delivered" if direction == "outbound" else "received"
        db.add(
            models.Message(
                conversation_id=conv.id,
                direction=direction,
                content=content,
                message_type="text",
                status=msg_status,
                created_at=ts,
                sent_by_user_id=owner.id if direction == "outbound" else None,
            )
        )

    conv.last_message_at = now - timedelta(minutes=messages[-1][2])
    conv.status = status
    db.commit()
    return "nuevo"


def main() -> int:
    db = SessionLocal()
    try:
        owner = crud.get_user_by_email(db, DEMO_EMAIL)
        if owner is None:
            print(f"ERROR: user {DEMO_EMAIL} no existe. Crea la cuenta primero.")
            return 1

        membership = crud.get_membership_for_user(db, owner)
        if membership is None:
            print(f"ERROR: {DEMO_EMAIL} no tiene team asociado.")
            return 1

        team_id = membership.team_id
        print(f"Owner={DEMO_EMAIL} team_id={team_id}\n")

        # Conversación principal (larga)
        action = _seed_conv(
            db, owner, team_id,
            wa_id=MAIN_CONTACT["wa_id"],
            name=MAIN_CONTACT["name"],
            messages=MAIN_MESSAGES,
            status="open",
        )
        print(f"  [{action:<5}] {MAIN_CONTACT['name']:<22} ({len(MAIN_MESSAGES)} msgs)")

        # 4 conversaciones cortas
        for c in SHORT_CONVERSATIONS:
            action = _seed_conv(
                db, owner, team_id,
                wa_id=c["wa_id"], name=c["name"],
                messages=c["messages"], status=c["status"],
            )
            print(f"  [{action:<5}] {c['name']:<22} ({len(c['messages'])} msgs, {c['status']})")

        print("\nOK.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
