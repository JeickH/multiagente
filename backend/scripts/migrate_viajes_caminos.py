"""Actualiza la config del bot de viajes SIN borrar nada (2026-08-18).

Por qué existe pudiendo re-correr `seed_bot_viajes_llm.py`: ese seed **borra
todos los bots de la cuenta** antes de recrearlos (decisión #254, un solo bot
por cuenta). Contra producción eso se llevaría por delante el bot id=12 de
Arranquemos Pues con su historial. Este script solo hace UPDATE.

Qué cambia, todo salido de la corrida de 10 guiones en producción del
2026-08-18:
  - `llm_config.caminos`: la tabla nueva de keywords (chips del panel).
  - `llm_config.media.hotel_video.camino`: `precios_condiciones` → `hotel`.
  - Los dos bloques visuales cuya copia quedó desactualizada: el itinerario
    decía "desayunos, almuerzos y cenas incluidos" (el lunes solo hay
    desayuno) y los métodos de pago decían "transferencia, PSE y tarjeta"
    (la lista real es otra).

Idempotente: re-correrlo no toca nada y lo reporta.

Uso:
    docker compose exec backend python backend/scripts/migrate_viajes_caminos.py
    TASKDEF=multiagente-backend:45 ./backend/scripts/rds_exec.sh \
        backend/scripts/migrate_viajes_caminos.py
"""
from __future__ import annotations

import json
import os
import sys

# `rds_exec.sh` manda este archivo como cuerpo de un `python -c`, y ahí
# `__file__` no existe (en el contenedor `app` ya está en el path, así que no
# hace falta el insert).
if "__file__" in globals():
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import models  # type: ignore

CORREO = os.environ.get("VIAJES_EMAIL", "arranquemospues.contacto@gmail.com")

# Espejo de CAMINOS en seed_bot_viajes_llm.py. Va duplicado a propósito: este
# archivo viaja como cuerpo de un `python -c` a una task efímera de ECS y no
# puede importar a sus hermanos de backend/scripts/.
CAMINOS = {
    "reserva": ["reserva", "reservar", "apartar", "separar", "cedula", "cédula",
                 "cupo"],
    "otros_destinos": ["san andres", "san andrés", "cartagena", "santa marta",
                        "guajira", "eje cafetero", "providencia", "otro destino",
                        "otros destinos", "otro plan", "otros planes",
                        "otro viaje", "otros viajes"],
    "hotel": ["hotel", "hospedaje", "alojamiento", "habitacion", "habitación",
               "amor de dios"],
    "itinerario": ["itinerario", "agenda", "cronograma", "dia a dia", "día a día",
                    "actividades", "que hacemos", "qué hacemos", "a que hora",
                    "a qué hora"],
    "precios_condiciones": ["precio", "precios", "cuesta", "cuanto", "cuánto",
                             "valor", "tarifa", "condicion", "condición",
                             "descuento", "rebaja", "abono", "reembolso",
                             "cancelacion", "cancelación"],
    "pagos": ["pago", "pagar", "pse", "transferencia", "tarjeta", "nequi",
               "daviplata", "bre-b", "breb", "bancolombia", "davivienda",
               "bbva", "efectivo", "codensa", "metodo", "método"],
    "tours": ["tour", "tours", "caimanera", "cienaga", "ciénaga", "paseo",
               "incluye", "incluido", "playa"],
    "asesor": ["hablar con una persona", "con una persona", "asesor humano",
                "un asesor", "una asesora", "un humano", "con alguien",
                "atencion humana", "atención humana"],
    "info_general": ["informacion", "información", "info", "plan", "covenas",
                      "coveñas", "tolu", "tolú", "promo"],
}

COPIA_VISUAL = {
    "Itinerario": (
        "🌴✨ ITINERARIO: 🚌 Viernes viaje (salida 6-9pm, Estación Universidad) "
        "· 📍 Sábado Caimanera · 📍 Domingo Tolú · 🚌 Lunes regreso. "
        "Alimentación del desayuno del sábado al desayuno del lunes ⚠️ sujeto "
        "a cambios logísticos."
    ),
    "Métodos de pago": (
        "Estos son los métodos de pago disponibles 💳: llave Bre-B, "
        "Bancolombia, Davivienda, BBVA, efectivo, tarjetas Mastercard/Visa/Amex "
        "y Crédito Fácil Codensa."
    ),
}


def main() -> int:
    db = SessionLocal()
    try:
        user = (
            db.query(models.User).filter(models.User.correo == CORREO).first()
        )
        if user is None:
            print(f"ERROR: no existe la cuenta {CORREO}")
            return 1
        bots = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == user.id, models.Bot.engine == "llm")
            .order_by(models.Bot.id)
            .all()
        )
        if not bots:
            print(f"ERROR: {CORREO} no tiene bots LLM")
            return 1
        if len(bots) > 1:
            print(f"ERROR: hay {len(bots)} bots LLM; pasa BOT_ID para desempatar")
            return 1
        bot = bots[0]
        print(f"bot {bot.id} · {bot.name}")

        cfg = json.loads(bot.llm_config or "{}")
        cambios = []

        if cfg.get("caminos") != CAMINOS:
            cfg["caminos"] = CAMINOS
            cambios.append(f"caminos → {len(CAMINOS)} ({', '.join(CAMINOS)})")

        # Las descripciones de los medios van al system prompt: si dicen "PSE"
        # el modelo lo va a ofrecer aunque el contexto ya no lo mencione.
        media = cfg.get("media") or {}
        hotel = media.get("hotel_video")
        if isinstance(hotel, dict) and hotel.get("camino") != "hotel":
            print(f"  hotel_video.camino: {hotel.get('camino')!r} → 'hotel'")
            hotel["camino"] = "hotel"
            hotel["descripcion"] = (
                "video del hotel 'El Amor de Dios' donde se hospedan"
            )
            cambios.append("media.hotel_video.camino")

        pagos = media.get("medios_pago")
        desc_pagos = "imagen con los métodos de pago (Bre-B, bancos, efectivo, tarjetas)"
        if isinstance(pagos, dict) and pagos.get("descripcion") != desc_pagos:
            pagos["descripcion"] = desc_pagos
            cambios.append("media.medios_pago.descripcion")

        if cambios:
            bot.llm_config = json.dumps(cfg, ensure_ascii=False)

        for step in bot.steps:
            nuevo = COPIA_VISUAL.get(step.label)
            if not nuevo:
                continue
            scfg = json.loads(step.config or "{}")
            if scfg.get("mensaje") == nuevo:
                continue
            scfg["mensaje"] = nuevo
            step.config = json.dumps(scfg, ensure_ascii=False)
            cambios.append(f"bloque visual {step.label!r}")

        if not cambios:
            print("OK: ya estaba al día, nada que hacer")
            return 0
        db.commit()
        for c in cambios:
            print(f"OK: {c}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
