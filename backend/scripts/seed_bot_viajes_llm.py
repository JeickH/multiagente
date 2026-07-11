"""Seed idempotente Sprint 19: bot LLM para la demo Agencia de Viajes.

Para la cuenta existente `agencia@demo.com` (creada por seed_bot_covenas.py):
  - Crea/re-crea el bot "Plan Tolú & Coveñas (IA)" con engine='llm', contexto
    a priori `demo_viajes` y el catálogo de medios ya publicado en
    frontend/public/demo_viajes/.
  - El bot LLM queda como trigger DEFAULT de la cuenta; el bot de flujo legacy
    ("Plan Tolú & Coveñas") queda PAUSADO en trigger manual (rollback fácil:
    re-correr seed_bot_covenas.py y pausar este).

Requiere que seed_bot_covenas.py haya corrido antes (usa su cuenta y su asesor).

Uso:
    python backend/scripts/seed_bot_viajes_llm.py
    # MEDIA_BASE opcional (default https://app.glomabeauty.com)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models  # type: ignore


AGENCY_EMAIL = os.environ.get("DEMO_AGENCY_EMAIL", "agencia@demo.com")
ASESOR_HANDLE = "asesor_1"
BOT_NAME = "Plan Tolú & Coveñas (IA)"

M = os.environ.get("MEDIA_BASE", "https://app.glomabeauty.com").rstrip("/")

MEDIA = {
    "info_general": {
        "url": f"{M}/demo_viajes/info_general.jpeg", "media_type": "image",
        "descripcion": "imagen con la información general del plan Tolú & Coveñas",
    },
    "tours": {
        "url": f"{M}/demo_viajes/tours.jpeg", "media_type": "image",
        "descripcion": "imagen con los tours incluidos en el plan",
    },
    "tour_video": {
        "url": f"{M}/demo_viajes/tour.mp4", "media_type": "video",
        "descripcion": "video adelanto de los tours",
    },
    "tarifario1": {
        "url": f"{M}/demo_viajes/tarifario1.jpeg", "media_type": "image",
        "descripcion": "tarifario 1 de 3: precios del plan",
    },
    "tarifario2": {
        "url": f"{M}/demo_viajes/tarifario2.jpeg", "media_type": "image",
        "descripcion": "tarifario 2 de 3: precios del plan",
    },
    "tarifario3": {
        "url": f"{M}/demo_viajes/tarifario3.jpeg", "media_type": "image",
        "descripcion": "tarifario 3 de 3: precios del plan",
    },
    "hotel_video": {
        "url": f"{M}/demo_viajes/hotel.mp4", "media_type": "video",
        "descripcion": "video del hotel donde se hospedan",
    },
    "medios_pago": {
        "url": f"{M}/demo_viajes/medios_pago.jpeg", "media_type": "image",
        "descripcion": "imagen con los métodos de pago (transferencia, PSE, tarjeta)",
    },
    "formulario_reserva": {
        "url": f"{M}/demo_viajes/fomulario_reserva.jpeg", "media_type": "image",
        "descripcion": "imagen con los datos que se piden para reservar",
    },
}


def main() -> int:
    db = SessionLocal()
    try:
        owner = crud.get_user_by_email(db, AGENCY_EMAIL)
        if owner is None:
            print(f"ERROR: no existe {AGENCY_EMAIL}. Corre seed_bot_covenas.py primero.")
            return 1

        # Re-crear el bot LLM (config siempre fresca).
        previos = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id, models.Bot.name == BOT_NAME)
            .all()
        )
        for b in previos:
            db.delete(b)
        if previos:
            db.commit()
            print(f"OK: {len(previos)} bot(s) LLM previo(s) eliminado(s)")

        # Pausar/degradar ANTES de crear: el índice parcial
        # uq_one_default_bot_per_user solo admite un bot default por usuario.
        legacy = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id,
                    models.Bot.trigger_type == models.BOT_TRIGGER_DEFAULT)
            .all()
        )
        for b in legacy:
            b.status = "paused"
            b.trigger_type = models.BOT_TRIGGER_MANUAL
        if legacy:
            db.commit()
            print(f"OK: {len(legacy)} bot(s) default previo(s) pausado(s)")

        bot = crud.create_bot_with_steps(
            db, owner, name=BOT_NAME,
            description="Bot conversacional (Claude vía Bedrock) de venta del "
                        "plan Tolú & Coveñas — misma estrategia LLM que Talulah.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=[], engine="llm",
            llm_config={
                "context_key": "demo_viajes",
                "assignee": ASESOR_HANDLE,
                "media": MEDIA,
            },
        )
        print(f"OK: bot LLM creado id={bot.id}")

        print()
        print(f"=== Demo Viajes IA lista para {AGENCY_EMAIL} ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
