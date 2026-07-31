"""Seed idempotente Sprint 20: cuenta oficial de Gloma + bot institucional LLM.

Crea/asegura:
  - Cuenta dueña `gloma@glomabeauty.com` (+ su team "Gloma").
  - Asesor comercial `asesor1.gloma@glomabeauty.com` en el team (handle
    `asesor_1`, destino de los handoffs del bot dentro de la app).
  - Bot "Gloma IA — Ventas y Servicio" con engine='llm':
      * contexto a priori `gloma` (backend/app/bot_contexts/gloma.md) con las
        15 preguntas frecuentes y su respuesta ideal (#267).
      * sin integraciones externas (no consulta Shopify ni envía media): el bot
        institucional conversa y escala al equipo comercial.

Es el MISMO bot para los 3 canales (#269/#270):
  1. WhatsApp de Gloma  → cuando se conecte el número (webhooks Twilio/Meta).
  2. Simulador de la app→ POST /bots/{id}/simulate (con JWT).
  3. Landing pública    → POST /landing/chat (sin JWT, widget de glomabeauty.com).

Un único bot por cuenta (convención #254): el seed elimina los bots previos del
owner y re-crea el bot con la config más reciente. Correr en local y en RDS
(convención #1 de paridad).

Uso:
    docker compose exec backend python scripts/seed_bot_gloma.py

ENV opcionales:
    GLOMA_EMAIL   (default gloma@glomabeauty.com)
    GLOMA_PWD     (default Gloma2026*)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models, schemas  # type: ignore


OWNER_EMAIL = os.environ.get("GLOMA_EMAIL", "gloma@glomabeauty.com")
OWNER_PWD = os.environ.get("GLOMA_PWD", "Gloma2026*")
OWNER_NAME = "Gloma"
ASESOR_EMAIL = "asesor1.gloma@glomabeauty.com"
ASESOR_HANDLE = "asesor_1"
BOT_NAME = "Gloma IA — Ventas y Servicio"


def _llm_config() -> dict:
    return {
        "context_key": "gloma",
        "assignee": ASESOR_HANDLE,
        # #255 observabilidad: clasificador de camino por keywords cuando el
        # turno no llama tools (las tools SON la decisión y tienen prioridad).
        # Orden = prioridad de matcheo: primero lo comercial (precio/demo),
        # que es lo que el CEO quiere ver en el tablero de prospectos.
        "caminos": {
            "precios": ["precio", "precios", "cuanto cuesta", "cuánto cuesta",
                         "vale", "tarifa", "cotiza", "cotización", "cotizacion",
                         "planes", "mensualidad", "presupuesto", "inversion",
                         "inversión"],
            "demo_inicio": ["demo", "demostracion", "demostración", "agendar",
                             "reunion", "reunión", "empezar", "comenzar",
                             "contratar", "quiero uno", "me interesa"],
            "implementacion": ["implementacion", "implementación", "demora",
                                "cuanto tarda", "cuánto tarda", "tiempo",
                                "que necesitan", "qué necesitan", "requisitos",
                                "onboarding", "piloto"],
            "conexion_whatsapp": ["numero", "número", "mi whatsapp",
                                   "whatsapp business", "api de whatsapp",
                                   "cambiar de numero", "cambiar de número",
                                   "meta", "linea", "línea"],
            "integraciones": ["integra", "integracion", "integración", "shopify",
                               "erp", "crm", "woocommerce", "api", "inventario",
                               "sistema", "pedidos"],
            "seguridad_datos": ["seguridad", "seguro", "datos", "privacidad",
                                 "habeas", "confidencial", "entrenan",
                                 "proteccion de datos", "protección de datos"],
            "alucinaciones": ["equivoca", "inventa", "alucina", "error",
                               "confiable", "control", "se equivoca"],
            "escalamiento": ["asesor", "humano", "persona", "agente real",
                              "escala", "mi equipo", "vendedor"],
            "ventas": ["vender", "vende", "ventas", "cerrar", "catalogo",
                        "catálogo", "recomienda", "carrito"],
            "campanas": ["campana", "campaña", "campanas", "campañas", "masivo",
                          "masivos", "plantilla", "recuperar", "remarketing"],
            "medicion": ["medir", "metrica", "métrica", "reporte", "tablero",
                          "dashboard", "resultados", "roi", "indicador"],
            "personalidad_marca": ["tono", "personalidad", "marca", "estilo",
                                    "voz", "como habla", "cómo habla"],
            "publicos_b2b": ["mayorista", "mayoristas", "b2b", "distribuidor",
                              "distribuidores", "publicos", "públicos"],
            "diferencia_chatbot": ["chatbot", "bot de botones", "menu", "menú",
                                    "diferencia", "diferente", "wati", "botones"],
            "que_es_gloma": ["que es gloma", "qué es gloma", "quienes son",
                              "quiénes son", "que hacen", "qué hacen", "gloma",
                              "empresa"],
        },
    }


# ---------------------------------------------------------------------------
# Pasos VISUALES (#256): el motor es llm_engine (los pasos NO se ejecutan);
# el visualizador de /bots/{id} muestra el bloque LLM de entrada, los caminos
# de las 15 preguntas y los cierres (asesor / fin).
# ---------------------------------------------------------------------------
STEPS = [
    # 1 — bloque LLM de entrada
    {"step_type": "llm", "label": "🤖 LLM · Lía recibe el mensaje y decide el camino",
     "config": {"mode": "route", "intents": [], "default_step_id": None,
                "mensaje": "Saluda, se presenta como asistente de Gloma, pide "
                           "el nombre y a qué se dedica la empresa, y enruta "
                           "según lo que pregunte el prospecto."}},
    {"step_type": "llm", "label": "Qué es Gloma", "config": {  # 2
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P1",
        "mensaje": "Gloma pone un agente de IA en el WhatsApp de tu empresa: "
                   "atiende 24/7, resuelve, vende y escala a tu equipo cuando "
                   "el caso lo amerita ✨"}},
    {"step_type": "llm", "label": "Diferencia vs chatbot de botones", "config": {  # 3
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P2",
        "mensaje": "Un chatbot de menús obliga al cliente a caber en tus "
                   "opciones; nuestro agente entiende lo que quiere decir y "
                   "responde con criterio."}},
    {"step_type": "llm", "label": "Personalidad de tu marca", "config": {  # 4
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P3",
        "mensaje": "Cargamos el contexto a priori de tu marca: tono, palabras, "
                   "políticas y procesos. Responde como tu mejor asesor 🤍"}},
    {"step_type": "llm", "label": "Escalamiento a humano", "config": {  # 5
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P4",
        "mensaje": "Cuando el cliente lo pide, el caso es delicado o el agente "
                   "no está seguro: avisa y entrega la conversación a tu equipo "
                   "con todo el historial."}},
    {"step_type": "llm", "label": "Integraciones (Shopify, ERP, CRM)", "config": {  # 6
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P5",
        "mensaje": "Consulta tus sistemas en vivo: Shopify probado (estado de "
                   "pedido, pago, envío, rastreo), catálogo de WhatsApp y APIs "
                   "propias."}},
    {"step_type": "llm", "label": "¿También vende?", "config": {  # 7
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P6",
        "mensaje": "Recomienda producto, comparte catálogo y medios, toma los "
                   "datos y deja la venta lista para tu asesor 📈"}},
    {"step_type": "llm", "label": "Conexión del número a WhatsApp", "config": {  # 8
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P7",
        "mensaje": "API oficial de WhatsApp Business: normalmente conservas tu "
                   "número (se migra desde la app). Nosotros hacemos la gestión "
                   "técnica con Meta."}},
    {"step_type": "llm", "label": "Implementación y requisitos", "config": {  # 9
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P8",
        "mensaje": "Tres frentes: contexto de tu marca, integraciones y "
                   "conexión del número. El tiempo exacto lo estima el equipo "
                   "con tu alcance (nunca prometer plazos)."}},
    {"step_type": "llm", "label": "Precios · modelo de cobro → asesor", "config": {  # 10
        "mode": "accion", "accion": "escalar", "fuente": "contexto a priori · P9",
        "mensaje": "Implementación inicial + plan mensual según volumen y "
                   "alcance, más el costo de Meta por conversación. La cifra la "
                   "arma un especialista (ROI promedio: 4 meses)."}},
    {"step_type": "llm", "label": "Seguridad y datos", "config": {  # 11
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P10",
        "mensaje": "Cuenta aislada por cliente en AWS, credenciales cifradas, "
                   "no se entrenan modelos con tus datos, alineado a la Ley "
                   "1581 de 2012."}},
    {"step_type": "llm", "label": "¿Se equivoca? Guardarraíles", "config": {  # 12
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P11",
        "mensaje": "Responde solo con tu contexto, tiene prohibido inventar "
                   "precios/stock/plazos, consulta el sistema para datos vivos "
                   "y escala si no sabe. Todo queda registrado."}},
    {"step_type": "llm", "label": "Medición de resultados", "config": {  # 13
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P12",
        "mensaje": "Tablero con conversaciones atendidas, temas más "
                   "preguntados, resueltas vs escaladas, tiempos y desempeño "
                   "de campañas."}},
    {"step_type": "llm", "label": "Campañas masivas", "config": {  # 14
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P13",
        "mensaje": "Envíos segmentados con plantillas aprobadas por Meta — y "
                   "quien responde cae en el agente, que continúa y cierra 🚀"}},
    {"step_type": "llm", "label": "Varios públicos (B2C + B2B)", "config": {  # 15
        "mode": "accion", "accion": "info", "fuente": "contexto a priori · P14",
        "mensaje": "El agente deduce con quién habla (cliente final o tienda "
                   "mayorista) y toma el camino correspondiente, en el mismo "
                   "número y sin menús."}},
    {"step_type": "llm", "label": "Cómo empezar · demo con tu caso", "config": {  # 16
        "mode": "accion", "accion": "registro",
        "fuente": "datos de contacto del prospecto",
        "mensaje": "Agendamos una sesión y armamos una demo del agente con TU "
                   "información. Pide nombre, empresa y correo/teléfono antes "
                   "de pasar al especialista."}},
    # 17 — bloque LLM post-acción (#265)
    {"step_type": "llm", "label": "🤖 LLM · ¿algo más o despedida?", "config": {
        "mode": "route", "intents": [],
        "mensaje": "Lía lee la respuesta: si trae una pregunta nueva la enruta; "
                   "si pide hablar con alguien, escala; si se despide, cierra."}},
    # 18 — handoff · 19 — fin
    {"step_type": "handoff", "label": "Pasar a un especialista de Gloma", "config": {
        "assignee": ASESOR_HANDLE,
        "text": "Te conecto con un especialista de nuestro equipo para verlo "
                "con tu caso en la mano ✨. Dame un momento 🤍"}},
    {"step_type": "end", "label": "Fin de la conversación", "config": {}},
]

# Camino del router principal → posición del bloque que lo atiende.
ROUTER_INTENTS = [
    ("Qué es Gloma", 2),
    ("Diferencia vs chatbot", 3),
    ("Personalidad de marca", 4),
    ("Escalamiento a humano", 5),
    ("Integraciones", 6),
    ("¿También vende?", 7),
    ("Conexión de WhatsApp", 8),
    ("Implementación", 9),
    ("Precios", 10),
    ("Seguridad y datos", 11),
    ("Guardarraíles", 12),
    ("Medición", 13),
    ("Campañas", 14),
    ("Varios públicos", 15),
    ("Cómo empezar / demo", 16),
    ("Asesor humano", 18),
    ("Despedida", 19),
]


def _wire(db, bot: models.Bot) -> None:
    """Cablea el diagrama: router LLM → 15 caminos → post-acción → asesor/fin."""
    import json as _j
    P = {s.position: s for s in bot.steps}

    def _route(pos: int, intents: list, default=None):
        cfg = _j.loads(P[pos].config or "{}")
        cfg.update({
            "mode": "route",
            "intents": [{"keywords": [k], "step_id": P[t].id} for k, t in intents],
            "default_step_id": P[default].id if default else None,
        })
        P[pos].config = _j.dumps(cfg, ensure_ascii=False)
        P[pos].next_step_id = None

    # Router principal. Default → asesor humano (nunca dejar al prospecto sin
    # salida: si no entendemos qué quiere, lo atiende una persona).
    _route(1, ROUTER_INTENTS, default=18)

    # Informativos → bloque post-acción (¿algo más o despedida?)
    for pos in range(2, 10):
        P[pos].next_step_id = P[17].id
    for pos in (11, 12, 13, 14, 15):
        P[pos].next_step_id = P[17].id
    # Precios y "cómo empezar" terminan en un especialista humano
    P[10].next_step_id = P[18].id
    P[16].next_step_id = P[18].id

    _route(17, [("Nueva pregunta", 1), ("Asesor", 18), ("Despedida", 19)])
    P[18].next_step_id = None
    db.commit()


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
            documento="GLOMA0001", password=OWNER_PWD,
        )
        team = crud.get_team_by_owner(db, owner)
        if team is None:
            team = crud.create_team(db, OWNER_NAME, owner)
        print(f"OK: owner={owner.correo} team_id={team.id}")

        asesor = _ensure_user(
            db, nombre="Especialista Gloma", correo=ASESOR_EMAIL,
            documento="GLOMAASESOR1", password=OWNER_PWD,
        )
        if crud.get_membership_for_user(db, asesor) is None:
            crud.add_member_to_team(db, team, asesor, role="agent")
        print(f"OK: asesor={asesor.correo} (handle={ASESOR_HANDLE})")

        # Un único bot por cuenta (#254): se eliminan los previos y se re-crea
        # con la config más reciente (también libera uq_one_default_bot_per_user).
        previos = (
            db.query(models.Bot).filter(models.Bot.user_id == owner.id).all()
        )
        for b in previos:
            db.delete(b)
        if previos:
            db.commit()
            print(f"OK: {len(previos)} bot(s) previo(s) eliminado(s) para recrear")

        bot = crud.create_bot_with_steps(
            db, owner, name=BOT_NAME,
            description="Bot institucional de Gloma (Claude vía Bedrock): "
                        "explica qué hace Gloma, responde las 15 preguntas "
                        "frecuentes de una empresa que quiere un agente en "
                        "WhatsApp y escala al equipo comercial. Mismo bot en "
                        "WhatsApp, en el simulador y en la landing.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=STEPS, engine="llm", llm_config=_llm_config(),
        )
        _wire(db, bot)
        print(f"OK: bot LLM creado id={bot.id} con {len(bot.steps)} bloques visuales")

        print()
        print(f"=== Cuenta oficial de Gloma lista ===")
        print(f"  login:   {OWNER_EMAIL}")
        print(f"  bot_id:  {bot.id}  (engine=llm, contexto 'gloma')")
        print(f"  canales: WhatsApp (pendiente conectar) · simulador · landing")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
