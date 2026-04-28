"""Seed específico de PRODUCCIÓN para `demo@gmail.com`.

Ejecuta una sola task ECS one-off que:
  1. Crea o resetea password de `demo@gmail.com` (con password aleatorio o
     pasado por env var `DEMO_PWD`).
  2. Asegura que tenga un team owner.
  3. Seedea 2 bots demo (`catalogo_talulah` + `Confirmación de pedido`).
  4. Seedea 5 conversaciones (Mariana López larga + 4 cortas).

NO toca otras cuentas (incluyendo `ceo@gloma.co`). Es idempotente: si los
datos ya existen, los preserva.

Salida: imprime al stdout la línea final `DEMO_PWD=<password>` para que se
pueda capturar desde CloudWatch logs.
"""
from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models, schemas  # type: ignore

# Reusamos la lógica de los seeds de local para no duplicar.
from scripts.seed_bot_demo import DEMO_BOT_NAME, DEMO_STEPS  # type: ignore
from scripts.seed_demo_conversation import (  # type: ignore
    MAIN_CONTACT,
    MAIN_MESSAGES,
    SHORT_CONVERSATIONS,
    _seed_conv,
)


DEMO_EMAIL = "demo@gmail.com"
DEMO_DOC = "DEMO0001"
DEMO_NAME = "Demo Gloma"


def _gen_password() -> str:
    return secrets.token_urlsafe(10)[:14]


def _ensure_user(db) -> tuple[models.User, str, str]:
    """Crea o resetea demo@gmail.com. Devuelve (user, password, accion)."""
    pwd = os.environ.get("DEMO_PWD") or _gen_password()
    existing = crud.get_user_by_email(db, DEMO_EMAIL)
    if existing:
        existing.hashed_password = crud.pwd_context.hash(pwd)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        action = "reset"
    else:
        existing = crud.create_user(
            db,
            schemas.UserCreate(
                nombre=DEMO_NAME,
                tipo_documento="CC",
                documento=DEMO_DOC,
                correo=DEMO_EMAIL,
                password=pwd,
            ),
        )
        action = "nuevo"

    if crud.get_membership_for_user(db, existing) is None:
        crud.create_team(db, nombre=f"Equipo de {existing.nombre}", owner=existing)
    return existing, pwd, action


def _seed_bots(db, owner: models.User) -> int:
    """Crea bots demo si faltan. Devuelve el número de bots creados."""
    membership = crud.get_membership_for_user(db, owner)
    if membership is None:
        return 0
    created = 0

    if not (
        db.query(models.Bot)
        .filter(models.Bot.user_id == owner.id, models.Bot.name == DEMO_BOT_NAME)
        .first()
    ):
        crud.create_bot_with_steps(
            db, owner,
            name=DEMO_BOT_NAME,
            description="Bot demo de 5 pasos — catálogo Talulah.",
            channels=[models.BOT_CHANNEL_WHATSAPP],
            trigger_type=models.BOT_TRIGGER_DEFAULT,
            trigger_config=None,
            steps=DEMO_STEPS,
        )
        created += 1

    if not (
        db.query(models.Bot)
        .filter(
            models.Bot.user_id == owner.id,
            models.Bot.name == "Confirmación de pedido",
        )
        .first()
    ):
        crud.create_bot_with_steps(
            db, owner,
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
                {"step_type": "send_text", "label": "Confirmación",
                 "config": {"text": "¡Gracias por tu compra! Tu pedido ha sido recibido."}},
                {"step_type": "delay", "label": "Pausa 2h",
                 "config": {"seconds": 7200}},
                {"step_type": "send_text", "label": "Seguimiento",
                 "config": {"text": "Tu pedido ya está en preparación 📦."}},
                {"step_type": "end", "label": "Fin",
                 "config": {"text": "¡Hasta pronto!"}},
            ],
        )
        created += 1
    return created


def _seed_conversations(db, owner: models.User) -> list[str]:
    """Seedea las 5 conversaciones. Devuelve lista de acciones."""
    membership = crud.get_membership_for_user(db, owner)
    if membership is None:
        return []
    team_id = membership.team_id
    actions: list[str] = []

    actions.append(_seed_conv(
        db, owner, team_id,
        wa_id=MAIN_CONTACT["wa_id"], name=MAIN_CONTACT["name"],
        messages=MAIN_MESSAGES, status="open",
    ))
    for c in SHORT_CONVERSATIONS:
        actions.append(_seed_conv(
            db, owner, team_id,
            wa_id=c["wa_id"], name=c["name"],
            messages=c["messages"], status=c["status"],
        ))
    return actions


def main() -> int:
    db = SessionLocal()
    try:
        user, pwd, user_action = _ensure_user(db)
        print(f"USER: {DEMO_EMAIL} accion={user_action} id={user.id}")

        bots_created = _seed_bots(db, user)
        print(f"BOTS: {bots_created} creados (saltados los que ya existían)")

        conv_actions = _seed_conversations(db, user)
        print(f"CONVS: {conv_actions}")

        # Línea final fácil de parsear desde los logs:
        print(f"DEMO_PWD={pwd}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
