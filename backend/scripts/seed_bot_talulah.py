"""Seed idempotente Sprint 19: cuenta Talulah + bot LLM de servicio al cliente.

Crea/asegura:
  - Cuenta dueña `talulah@gloma.com` (+ su team "Talulah").
  - Asesora humana `asesora1.talulah@gloma.com` en el team (handle `asesor_1`,
    destino de los handoffs del bot dentro de la app).
  - Bot "Talulah IA — Servicio al Cliente" con engine='llm':
      * contexto a priori `talulah` (backend/app/bot_contexts/talulah.md)
      * catálogo de medios: guía de tallas (frontend/public/talulah/)
      * integración Shopify (client_credentials) — el client_secret se cifra
        con Fernet ANTES de guardarse en bots.llm_config (regla de seguridad #3).

Credenciales Shopify: se pasan por ENV SOLO al momento de correr el seed
(nunca quedan en el repo ni en .env de la app):

    TALULAH_SHOPIFY_SHOP=grupogyc.myshopify.com \
    TALULAH_SHOPIFY_CLIENT_ID=... \
    TALULAH_SHOPIFY_CLIENT_SECRET=... \
    python backend/scripts/seed_bot_talulah.py

Si faltan las credenciales Shopify, el bot se crea igual pero sin la tool de
pedidos (se puede re-correr el seed después: es idempotente y re-crea el bot).

Otros ENV opcionales:
    TALULAH_EMAIL   (default talulah@gloma.com)
    TALULAH_PWD     (default Talulah2026*)
    MEDIA_BASE      (default https://app.glomabeauty.com)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models, schemas  # type: ignore
from app.services.crypto import encrypt_secret  # type: ignore


OWNER_EMAIL = os.environ.get("TALULAH_EMAIL", "talulah@gloma.com")
OWNER_PWD = os.environ.get("TALULAH_PWD", "Talulah2026*")
OWNER_NAME = "Talulah"
ASESORA_EMAIL = "asesora1.talulah@gloma.com"
ASESORA_HANDLE = "asesor_1"
BOT_NAME = "Talulah IA — Servicio al Cliente"

M = os.environ.get("MEDIA_BASE", "https://app.glomabeauty.com").rstrip("/")

SHOPIFY_SHOP = os.environ.get("TALULAH_SHOPIFY_SHOP", "")
SHOPIFY_CLIENT_ID = os.environ.get("TALULAH_SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.environ.get("TALULAH_SHOPIFY_CLIENT_SECRET", "")


def _llm_config() -> dict:
    cfg: dict = {
        "context_key": "talulah",
        "assignee": ASESORA_HANDLE,
        "media": {
            f"guia_tallas_{i}": {
                "url": f"{M}/talulah/guia_tallas_{i}.jpeg",
                "media_type": "image",
                "descripcion": f"guía de tallas Talulah (imagen {i} de 6)",
                "caption": "Guía de tallas Talulah 🌿" if i == 1 else "",
            }
            for i in range(1, 7)
        },
    }
    if SHOPIFY_SHOP and SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET:
        cfg["shopify"] = {
            "shop": SHOPIFY_SHOP,
            "client_id": SHOPIFY_CLIENT_ID,
            # Secreto de tenant → SIEMPRE cifrado en BD (regla #3).
            "encrypted_client_secret": encrypt_secret(SHOPIFY_CLIENT_SECRET),
        }
    return cfg


def _ensure_user(db, *, nombre, correo, documento, password) -> models.User:
    user = crud.get_user_by_email(db, correo)
    if user:
        return user
    return crud.create_user(db, schemas.UserCreate(
        nombre=nombre, tipo_documento="CC", documento=documento,
        correo=correo, password=password,
    ))


def main() -> int:
    db = SessionLocal()
    try:
        owner = _ensure_user(
            db, nombre=OWNER_NAME, correo=OWNER_EMAIL,
            documento="TALULAH01", password=OWNER_PWD,
        )
        team = crud.get_team_by_owner(db, owner)
        if team is None:
            team = crud.create_team(db, OWNER_NAME, owner)
        print(f"OK: owner={owner.correo} team_id={team.id}")

        asesora = _ensure_user(
            db, nombre="Asesora Talulah", correo=ASESORA_EMAIL,
            documento="TALASESORA1", password=OWNER_PWD,
        )
        if crud.get_membership_for_user(db, asesora) is None:
            crud.add_member_to_team(db, team, asesora, role="agent")
        print(f"OK: asesora={asesora.correo} (handle={ASESORA_HANDLE})")

        # Bot LLM: se re-crea en cada corrida para reflejar siempre la config
        # más reciente (mismo patrón que seed_bot_covenas).
        previos = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id, models.Bot.name == BOT_NAME)
            .all()
        )
        for b in previos:
            db.delete(b)
        if previos:
            db.commit()
            print(f"OK: {len(previos)} bot(s) previo(s) eliminado(s) para recrear")

        cfg = _llm_config()
        bot = crud.create_bot_with_steps(
            db, owner, name=BOT_NAME,
            description="Bot conversacional (Claude vía Bedrock) de servicio al "
                        "cliente Talulah: minoristas y mayoristas, pedidos "
                        "Shopify, guía de tallas y escalamiento a asesora.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=[], engine="llm", llm_config=cfg,
        )
        shopify_estado = "con Shopify" if "shopify" in cfg else "SIN Shopify (faltan env)"
        print(f"OK: bot LLM creado id={bot.id} ({shopify_estado})")

        print()
        print(f"=== Talulah lista. Login: {OWNER_EMAIL} / {OWNER_PWD} ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
