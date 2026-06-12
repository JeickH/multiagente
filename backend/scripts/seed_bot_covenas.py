"""Seed idempotente: cuenta demo "Agencia de Viajes" + bot "Plan Coveñas".

Para la demostración al equipo de negocio:
  - Crea/asegura la cuenta dueña `agencia@demo.com` (+ su team).
  - Crea/asegura el usuario asesor humano `asesor1@demo.com` y lo agrega al team.
  - Crea el bot "Plan Coveñas" con el esqueleto completo (texto abierto + bloques
    LLM que enrutan por lógica predefinida + handoff a asesor).
  - Seedea 2 conversaciones de muestra (una atendida por el bot, otra ya
    escalada a `asesor_1`) para que la vista de Mensajes tenga contenido.

Los copys son PLACEHOLDER (se afinan en T10). Las imágenes/videos se sirven
desde `frontend/public/demo_viajes/` en local; en prod irían a S3+CloudFront.

Uso:
    docker compose exec backend python backend/scripts/seed_bot_covenas.py
    # o local con venv:
    POSTGRES_HOST=localhost python backend/scripts/seed_bot_covenas.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models, schemas  # type: ignore


AGENCY_EMAIL = os.environ.get("DEMO_AGENCY_EMAIL", "agencia@demo.com")
AGENCY_PWD = os.environ.get("DEMO_PWD", "Demo1234*")
AGENCY_NAME = "Agencia de Viajes Arranquemos Pues"
ASESOR_EMAIL = "asesor1@demo.com"
ASESOR_HANDLE = "asesor_1"            # lo que se guarda en conversation.assigned_to
BOT_NAME = "Plan Tolú & Coveñas"

# Base pública de los assets. Local: ruta servida por Next (`/demo_viajes`).
# Prod: setear MEDIA_BASE a la URL de S3/CloudFront (ej. https://cdn.../demo_viajes).
M = os.environ.get("MEDIA_BASE", "/demo_viajes").rstrip("/")


# ---------------------------------------------------------------------------
# Esqueleto del bot. Orden = posición (1..N). El branching (loops + LLM route)
# se cablea en `_wire()` después de crear los pasos, usando los ids reales.
# ---------------------------------------------------------------------------
STEPS = [
    # 1 — saludo + pedir nombre
    {"step_type": "send_text", "label": "Saludo + pedir nombre", "config": {
        "text": "Hola, ¡Buen día! Espero que se encuentre muy bien el día de hoy, "
                "mi nombre es *Maria Camila*, asesora de la *Agencia de Viajes "
                "Arranquemos Pues*. ¿Con quién tengo el gusto? 😊"}},
    # 2 — espera el nombre (texto abierto)
    {"step_type": "wait_input", "label": "Espera nombre", "config": {"prompt": ""}},
    # 3 — LLM: extrae el nombre
    {"step_type": "llm", "label": "LLM · extraer nombre", "config": {
        "mode": "extract", "variable": "nombre"}},
    # 4 — info general (imagen + caption)
    {"step_type": "send_media", "label": "Info general del tour", "config": {
        "media_type": "image", "url": f"{M}/info_general.jpeg",
        "caption": "¡Un gusto, {nombre}! 🙌 Con gusto te cuento sobre nuestro "
                   "*Plan a Tolú & Coveñas* 🌴: salida el viernes y regreso el "
                   "lunes, con hotel, alimentación y transporte ida y regreso "
                   "incluidos. Aquí te dejo la info general 👆"}},
    # 5 — menú (pregunta abierta) — punto de retorno del bucle
    {"step_type": "wait_input", "label": "Menú (pregunta abierta)", "config": {
        "prompt": "¿Qué te gustaría saber? Pregúntame por los *tours incluidos*, "
                  "*precios y condiciones*, el *itinerario* o los *métodos de pago*. "
                  "Y cuando estés listo para reservar, envíame tus datos 😉"}},
    # 6 — LLM: interpreta y enruta (cableado en _wire)
    {"step_type": "llm", "label": "LLM · interpreta y enruta", "config": {
        "mode": "route", "intents": [], "default_step_id": None}},
    # 7 — tours incluidos (imagen + video)
    {"step_type": "send_media", "label": "Tours incluidos", "config": {"items": [
        {"media_type": "image", "url": f"{M}/tours.jpeg",
         "caption": "Estos son los tours incluidos en tu plan 🏝️"},
        {"media_type": "video", "url": f"{M}/tour.mp4",
         "caption": "Y mira un adelanto en video 🎥"}]}},
    # 8 — precios + condiciones + hotel (tarifario1/2/3 + video, todo junto)
    {"step_type": "send_media", "label": "Precios y condiciones", "config": {"items": [
        {"media_type": "image", "url": f"{M}/tarifario1.jpeg",
         "caption": "💰 *Precios y tarifas* del plan a Tolú & Coveñas:"},
        {"media_type": "image", "url": f"{M}/tarifario2.jpeg"},
        {"media_type": "image", "url": f"{M}/tarifario3.jpeg"},
        {"media_type": "video", "url": f"{M}/hotel.mp4",
         "caption": "🏨 Así es el hotel donde te hospedarás.\n\n"
                    "Se reserva con el *30% del valor total por persona* y debe "
                    "estar cancelado de 10 a 8 días hábiles antes del viaje 🤗"}]}},
    # 9 — itinerario (solo mensaje)
    {"step_type": "send_text", "label": "Itinerario", "config": {
        "text": "🌴✨ ITINERARIO TOLÚ & COVEÑAS ✨🌴\n\n"
                "🚌 *Viernes – Viaje*\n"
                "Salida tarde/noche entre 6:00 a 9:00 pm aproximadamente.\n"
                "Desde la Estación Universidad – Calle Carabobo.\n"
                "Transporte ida y regreso incluido.\n"
                "La hora exacta se confirma un día antes por grupo de WhatsApp.\n\n"
                "📍 *Sábado – Caimanera*\n"
                "🍽️ Desayuno, almuerzo y cena incluidos.\n"
                "🌿 Tour a la Ciénaga de La Caimanera.\n"
                "🚣‍♀️ No incluye Canoa a la Casa Flotante (opcional $25.000 aprox. por persona).\n\n"
                "📍 *Domingo – Tolú*\n"
                "🍽️ Desayuno, almuerzo y cena incluidos.\n"
                "🌴 Tour a Tolú, ideal para compras y artesanías 🛍️.\n"
                "🚲 No incluye Bici-taxi al Malecón ($3.000 – $4.000) o caminata de 15 min.\n\n"
                "🚌 *Lunes – Regreso*\n"
                "🍽️ Desayuno incluido.\n"
                "Salida entre 9:00 a.m. y 1:00 p.m. (hora indicada por el guía).\n\n"
                "⚠️ *Este itinerario está sujeto a modificación sin previo aviso "
                "por temas logísticos*"}},
    # 10 — métodos de pago (imagen + mensaje)
    {"step_type": "send_media", "label": "Métodos de pago", "config": {
        "media_type": "image", "url": f"{M}/medios_pago.jpeg",
        "caption": "Estos son los métodos de pago disponibles 💳. Aceptamos "
                   "transferencia, PSE y tarjeta."}},
    # 11 — formulario de reserva (imagen + mensaje)
    {"step_type": "send_media", "label": "Formulario de reserva", "config": {
        "media_type": "image", "url": f"{M}/fomulario_reserva.jpeg",
        "caption": "¡Perfecto! Para tu reserva necesito estos datos 👆\n"
                   "Envíame en un mensaje: *nombre completo*, *cédula*, "
                   "*número de personas* y *fecha de viaje*."}},
    # 12 — espera los datos de reserva (texto abierto)
    {"step_type": "wait_input", "label": "Espera datos de reserva", "config": {
        "prompt": ""}},
    # 13 — LLM: detecta datos de reserva (cableado en _wire)
    {"step_type": "llm", "label": "LLM · detecta datos de reserva", "config": {
        "mode": "route", "intents": [], "default_step_id": None}},
    # 14 — handoff a asesor humano
    {"step_type": "handoff", "label": "Pasar a asesor", "config": {
        "assignee": ASESOR_HANDLE,
        "text": "¡Listo, {nombre}! 🙌 Recibí tus datos. Te conecto con uno de "
                "nuestros asesores para confirmar disponibilidad y finalizar tu "
                "reserva. En un momento te escriben por aquí 💬"}},
    # 15 — fallback (no entendió) — vuelve al menú
    {"step_type": "send_text", "label": "Fallback (no entendió)", "config": {
        "text": "Mmm, no estoy seguro de haberte entendido 🤔. Puedo contarte "
                "sobre los *tours*, las *condiciones*, el *itinerario* o los "
                "*métodos de pago*. O si quieres reservar, envíame tus datos."}},
]


def _wire(db, bot: models.Bot) -> None:
    """Cablea branching del bot ya creado: bucle al menú + LLM route por ids."""
    P = {s.position: s for s in bot.steps}  # posición(1-based) -> BotStep

    # LLM menú (paso 6): keywords -> step_id. Orden importa (primera que matchea).
    P[6].config = _json_dumps({
        "mode": "route",
        "intents": [
            {"keywords": ["tour", "tours", "incluye", "incluido", "playa", "isla",
                          "islas", "ciénaga", "cienaga", "caimanera", "paseo"],
             "step_id": P[7].id},
            {"keywords": ["precio", "precios", "cuesta", "cuanto", "cuánto", "valor",
                          "tarifa", "tarifas", "tarifario", "condicion", "condiciones",
                          "reembolso", "politica", "política", "cancela", "cancelacion",
                          "cancelación", "abono", "descuento", "hotel", "alojamiento",
                          "hospeda", "habitacion", "habitación"],
             "step_id": P[8].id},
            {"keywords": ["itinerario", "dia a dia", "día a día", "agenda",
                          "cronograma", "actividad", "que hacemos", "qué hacemos"],
             "step_id": P[9].id},
            {"keywords": ["pago", "pagar", "metodo", "método", "metodos", "métodos",
                          "transferencia", "pse", "tarjeta", "consignar", "nequi",
                          "daviplata"],
             "step_id": P[10].id},
            {"keywords": ["quiero reservar", "reservar", "reserva", "apartar",
                          "separar", "quiero el plan", "lo quiero"],
             "step_id": P[11].id},
            {"keywords": ["nombre completo", "cedula", "cédula", "documento",
                          "personas", "somos", "viajamos", "fecha", "correo",
                          "telefono", "teléfono"],
             "step_id": P[14].id},
        ],
        "default_step_id": P[15].id,
    })

    # LLM detección de datos de reserva (paso 13). Tras el formulario somos
    # permisivos: si no detecta keywords igual escala (default -> handoff).
    P[13].config = _json_dumps({
        "mode": "route",
        "intents": [
            {"keywords": ["nombre", "cedula", "cédula", "documento", "persona",
                          "somos", "fecha", "correo", "@", "telefono", "teléfono", "cc"],
             "step_id": P[14].id},
        ],
        "default_step_id": P[14].id,
    })

    # Bucle: cada respuesta de tema y el fallback vuelven al menú (paso 5).
    for pos in (7, 8, 9, 10, 15):
        P[pos].next_step_id = P[5].id
    # El handoff es terminal: el humano toma el control.
    P[14].next_step_id = None

    db.commit()


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


def _ensure_user(db, *, nombre, correo, documento, password) -> models.User:
    user = crud.get_user_by_email(db, correo)
    if user:
        return user
    return crud.create_user(db, schemas.UserCreate(
        nombre=nombre, tipo_documento="CC", documento=documento,
        correo=correo, password=password,
    ))


def _seed_sample_conversations(db, team_id: int) -> None:
    """2 conversaciones de muestra para la vista de Mensajes (idempotente)."""
    samples = [
        {
            "wa_id": "573001112233", "name": "Laura Gómez",
            "assigned_to": "bot", "status": "open",
            "messages": [
                ("inbound", "Hola, vi la promo del plan a Coveñas 🌴"),
                ("outbound", "¡Hola! 🌴 Gracias por escribirnos. ¿Con quién tengo el gusto?"),
                ("inbound", "Soy Laura"),
                ("outbound", "¡Un gusto, Laura! 🙌 Te cuento lo esencial del plan…"),
            ],
        },
        {
            "wa_id": "573004445566", "name": "Andrés Ruiz",
            "assigned_to": ASESOR_HANDLE, "status": "pending",
            "messages": [
                ("inbound", "Quiero reservar para 2 personas"),
                ("outbound", "¡Perfecto! Envíame nombre completo, cédula, # personas y fecha."),
                ("inbound", "Andrés Ruiz, CC 1020304050, 2 personas, 20 de julio"),
                ("outbound", "¡Listo, Andrés! 🙌 Te conecto con un asesor para finalizar tu reserva 💬"),
            ],
        },
    ]
    for s in samples:
        conv = crud.get_or_create_conversation(
            db, team_id, s["wa_id"], contact_name=s["name"]
        )
        conv.status = s["status"]
        conv.assigned_to = s["assigned_to"]
        db.commit()
        if conv.messages:  # ya tenía mensajes -> no duplicar
            continue
        for direction, content in s["messages"]:
            crud.add_message(db, conv, direction=direction, content=content,
                             message_type="text", status="sent")


def main() -> int:
    db = SessionLocal()
    try:
        # 1. Cuenta dueña (agencia) + team
        owner = _ensure_user(
            db, nombre=AGENCY_NAME, correo=AGENCY_EMAIL,
            documento="AGENCIA01", password=AGENCY_PWD,
        )
        if owner.nombre != AGENCY_NAME:
            owner.nombre = AGENCY_NAME
            db.commit()
        team = crud.get_team_by_owner(db, owner)
        if team is None:
            team = crud.create_team(db, AGENCY_NAME, owner)
        print(f"OK: owner={owner.correo} team_id={team.id}")

        # 2. Asesor humano
        asesor = _ensure_user(
            db, nombre="Asesor 1", correo=ASESOR_EMAIL,
            documento="ASESOR001", password=AGENCY_PWD,
        )
        if crud.get_membership_for_user(db, asesor) is None:
            crud.add_member_to_team(db, team, asesor, role="agent")
        print(f"OK: asesor={asesor.correo} (handle={ASESOR_HANDLE})")

        # 3. Bot demo: lo re-creamos en cada corrida para reflejar siempre los
        #    copys más recientes. Borramos cualquier bot previo de esta cuenta
        #    demo (incluyendo nombres antiguos como "Plan Coveñas").
        previos = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id)
            .all()
        )
        for b in previos:
            db.delete(b)
        if previos:
            db.commit()
            print(f"OK: {len(previos)} bot(s) previo(s) eliminado(s) para recrear")
        bot = crud.create_bot_with_steps(
            db, owner, name=BOT_NAME,
            description="Bot demo de venta del plan a Tolú & Coveñas "
                        "(Agencia de Viajes Arranquemos Pues).",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=STEPS,
        )
        _wire(db, bot)
        print(f"OK: bot creado id={bot.id} con {len(bot.steps)} pasos")

        # 4. Conversaciones de muestra
        _seed_sample_conversations(db, team.id)
        print("OK: conversaciones de muestra listas")

        print()
        print(f"=== Demo lista. Login: {AGENCY_EMAIL} / {AGENCY_PWD} ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
