"""Seed idempotente Sprint 19: bot LLM para la demo Agencia de Viajes.

Para la cuenta existente `agencia@demo.com` (creada por seed_bot_covenas.py):
  - Crea/re-crea el bot "Plan Tolú & Coveñas (IA)" con engine='llm', contexto
    a priori `demo_viajes` y el catálogo de medios ya publicado en
    frontend/public/demo_viajes/.
  - Decisión CEO (Sprint 19 #254): esta cuenta tiene UN ÚNICO bot — el LLM.
    Cualquier otro bot previo de la cuenta (p. ej. el de flujo legacy) se
    ELIMINA. Rollback: re-correr seed_bot_covenas.py y borrar este.

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
        "camino": "info_general",
    },
    "tours": {
        "url": f"{M}/demo_viajes/tours.jpeg", "media_type": "image",
        "descripcion": "imagen con los tours incluidos en el plan",
        "camino": "tours",
    },
    "tour_video": {
        "url": f"{M}/demo_viajes/tour.mp4", "media_type": "video",
        "descripcion": "video adelanto de los tours",
        "camino": "tours",
    },
    "tarifario1": {
        "url": f"{M}/demo_viajes/tarifario1.jpeg", "media_type": "image",
        "descripcion": "tarifario 1 de 3: precios del plan",
        "camino": "precios_condiciones",
    },
    "tarifario2": {
        "url": f"{M}/demo_viajes/tarifario2.jpeg", "media_type": "image",
        "descripcion": "tarifario 2 de 3: precios del plan",
        "camino": "precios_condiciones",
    },
    "tarifario3": {
        "url": f"{M}/demo_viajes/tarifario3.jpeg", "media_type": "image",
        "descripcion": "tarifario 3 de 3: precios del plan",
        "camino": "precios_condiciones",
    },
    "hotel_video": {
        "url": f"{M}/demo_viajes/hotel.mp4", "media_type": "video",
        "descripcion": "video del hotel donde se hospedan",
        "camino": "precios_condiciones",
    },
    "medios_pago": {
        "url": f"{M}/demo_viajes/medios_pago.jpeg", "media_type": "image",
        "descripcion": "imagen con los métodos de pago (transferencia, PSE, tarjeta)",
        "camino": "pagos",
    },
    "formulario_reserva": {
        "url": f"{M}/demo_viajes/fomulario_reserva.jpeg", "media_type": "image",
        "descripcion": "imagen con los datos que se piden para reservar",
        "camino": "reserva",
    },
}

# #255 observabilidad: clasificador de camino por keywords (fallback cuando el
# turno no llama tools ni envía media). Orden = prioridad de matcheo.
CAMINOS = {
    "reserva": ["reserva", "reservar", "apartar", "separar", "cedula", "cédula"],
    "itinerario": ["itinerario", "agenda", "cronograma", "dia a dia", "día a día",
                    "actividades", "que hacemos", "qué hacemos"],
    "precios_condiciones": ["precio", "precios", "cuesta", "cuanto", "cuánto",
                             "valor", "tarifa", "condicion", "condición", "hotel",
                             "abono", "reembolso", "cancelacion", "cancelación"],
    "tours": ["tour", "tours", "caimanera", "cienaga", "ciénaga", "paseo",
               "incluye", "incluido"],
    "pagos": ["pago", "pagar", "pse", "transferencia", "tarjeta", "nequi",
               "daviplata", "metodo", "método"],
    "info_general": ["informacion", "información", "info", "plan", "covenas",
                      "coveñas", "tolu", "tolú", "promo"],
    "asesor": ["asesor", "asesora", "humano", "persona", "agente"],
}


# ---------------------------------------------------------------------------
# Pasos VISUALES (#256): el motor es llm_engine (los pasos no se ejecutan);
# el visualizador muestra bloque LLM → caminos → bloques de acción LLM.
# ---------------------------------------------------------------------------
STEPS = [
    # 1 — bloque LLM de entrada
    {"step_type": "llm", "label": "🤖 LLM · Maria Camila decide el camino",
     "config": {"mode": "route", "intents": [], "default_step_id": None}},
    {"step_type": "llm", "label": "Info general del plan", "config": {
        "mode": "accion", "accion": "media", "fuente": "info_general.jpeg",
        "mensaje": "¡Un gusto! 🙌 Te cuento sobre nuestro *Plan a Tolú & "
                   "Coveñas* 🌴: salida el viernes y regreso el lunes, con "
                   "hotel, alimentación y transporte ida y regreso incluidos. "
                   "Aquí te dejo la info general 👆"}},
    {"step_type": "llm", "label": "Tours incluidos", "config": {
        "mode": "accion", "accion": "media", "fuente": "tours.jpeg + tour.mp4",
        "mensaje": "Estos son los tours incluidos en tu plan 🏝️ (Ciénaga de "
                   "La Caimanera y Tolú). Y mira un adelanto en video 🎥"}},
    {"step_type": "llm", "label": "Precios y condiciones", "config": {
        "mode": "accion", "accion": "media",
        "fuente": "tarifario1-3.jpeg + hotel.mp4",
        "mensaje": "💰 *Precios y tarifas* del plan a Tolú & Coveñas + 🏨 así "
                   "es el hotel. Se reserva con el *30% del valor por persona* "
                   "y se paga completo de 10 a 8 días hábiles antes del viaje 🤗"}},
    {"step_type": "llm", "label": "Itinerario", "config": {
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "🌴✨ ITINERARIO: 🚌 Viernes viaje (salida 6-9pm, Estación "
                   "Universidad) · 📍 Sábado Caimanera · 📍 Domingo Tolú · "
                   "🚌 Lunes regreso. Desayunos, almuerzos y cenas incluidos ⚠️ "
                   "sujeto a cambios logísticos."}},
    {"step_type": "llm", "label": "Métodos de pago", "config": {
        "mode": "accion", "accion": "media", "fuente": "medios_pago.jpeg",
        "mensaje": "Estos son los métodos de pago disponibles 💳. Aceptamos "
                   "transferencia, PSE y tarjeta."}},
    {"step_type": "llm", "label": "Reserva · pide los datos", "config": {  # 7
        "mode": "accion", "accion": "media",
        "fuente": "fomulario_reserva.jpeg",
        "mensaje": "¡Perfecto! Para tu reserva necesito estos datos 👆 Envíame "
                   "en un mensaje: *nombre completo*, *cédula*, *número de "
                   "personas* y *fecha de viaje* 😉"}},
    {"step_type": "llm", "label": "Reserva · datos recibidos", "config": {  # 8
        "mode": "accion", "accion": "registro",
        "fuente": "datos del cliente (nombre, cédula, personas, fecha)",
        "mensaje": "¡Listo, <nombre>! 🙌 Recibí tus datos. Te conecto con uno "
                   "de nuestros asesores para confirmar disponibilidad y "
                   "finalizar tu reserva 💬"}},
    # 9 — bloque LLM post-acción (#265): relee la respuesta del cliente tras
    # una acción; decide nuevo camino o despedida.
    {"step_type": "llm", "label": "🤖 LLM · ¿algo más o despedida?", "config": {
        "mode": "route", "intents": [],
        "mensaje": "La IA lee la respuesta: si trae un nuevo tema lo enruta al "
                   "camino correspondiente; si solo agradece o se despide, "
                   "cierra la conversación."}},
    # 10 — handoff
    {"step_type": "handoff", "label": "Pasar a asesor humano", "config": {
        "assignee": ASESOR_HANDLE,
        "text": "¡Listo! 🙌 Te conecto con uno de nuestros asesores para "
                "finalizar tu reserva. En un momento te escriben por aquí 💬"}},
    # 11 — fin
    {"step_type": "end", "label": "Fin de la conversación", "config": {}},
]


def _wire(db, bot: models.Bot) -> None:
    import json as _j
    P = {s.position: s for s in bot.steps}
    P[1].config = _j.dumps({
        "mode": "route",
        "intents": [
            {"keywords": ["Info general"], "step_id": P[2].id},
            {"keywords": ["Tours incluidos"], "step_id": P[3].id},
            {"keywords": ["Precios y condiciones"], "step_id": P[4].id},
            {"keywords": ["Itinerario"], "step_id": P[5].id},
            {"keywords": ["Métodos de pago"], "step_id": P[6].id},
            {"keywords": ["Reserva"], "step_id": P[7].id},
            {"keywords": ["Asesor humano"], "step_id": P[10].id},
            {"keywords": ["Despedida"], "step_id": P[11].id},
        ],
        "default_step_id": None,
    }, ensure_ascii=False)
    P[1].next_step_id = None
    for pos in (2, 3, 4, 5, 6):     # informativos → post-acción (#265)
        P[pos].next_step_id = P[9].id
    P[7].next_step_id = P[8].id      # pide datos → datos recibidos
    P[8].next_step_id = P[10].id     # → asesor
    # Post-acción: nuevo tema → router · asesor → handoff · despedida → fin
    cfg9 = _j.loads(P[9].config or "{}")
    cfg9.update({
        "mode": "route",
        "intents": [
            {"keywords": ["Nuevo tema"], "step_id": P[1].id},
            {"keywords": ["Asesor"], "step_id": P[10].id},
            {"keywords": ["Despedida"], "step_id": P[11].id},
        ],
        "default_step_id": None,
    })
    P[9].config = _j.dumps(cfg9, ensure_ascii=False)
    P[9].next_step_id = None
    P[10].next_step_id = None
    db.commit()


def main() -> int:
    db = SessionLocal()
    try:
        owner = crud.get_user_by_email(db, AGENCY_EMAIL)
        if owner is None:
            print(f"ERROR: no existe {AGENCY_EMAIL}. Corre seed_bot_covenas.py primero.")
            return 1

        # Un único bot por cuenta (#254): se eliminan TODOS los bots previos
        # del owner (incluye el LLM anterior y el flujo legacy) y se crea el
        # LLM fresco. Esto además libera el índice uq_one_default_bot_per_user.
        previos = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id)
            .all()
        )
        for b in previos:
            db.delete(b)
        if previos:
            db.commit()
            print(f"OK: {len(previos)} bot(s) previo(s) eliminado(s)")

        bot = crud.create_bot_with_steps(
            db, owner, name=BOT_NAME,
            description="Bot conversacional (Claude vía Bedrock) de venta del "
                        "plan Tolú & Coveñas — misma estrategia LLM que Talulah.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=STEPS, engine="llm",
            llm_config={
                "context_key": "demo_viajes",
                "assignee": ASESOR_HANDLE,
                "media": MEDIA,
                "caminos": CAMINOS,
            },
        )
        _wire(db, bot)
        print(f"OK: bot LLM creado id={bot.id} con {len(bot.steps)} bloques visuales")

        print()
        print(f"=== Demo Viajes IA lista para {AGENCY_EMAIL} ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
