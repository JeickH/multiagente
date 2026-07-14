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
                "camino": "tallas",
            }
            for i in range(1, 7)
        },
        # #255 observabilidad: clasificador de camino por keywords cuando el
        # turno no llama tools ni envía media (las tools SON la decisión y
        # tienen prioridad). Orden = prioridad de matcheo — afinado tras los
        # guiones QA #259: lo B2B va primero (sus mensajes contienen palabras
        # de otros caminos como "pedido" o "envío") y las keywords ambiguas
        # ("tienda", "envio", "pedido" a secas) se volvieron frases específicas.
        "caminos": {
            "mayorista_faltantes": ["faltante", "faltantes", "faltaron", "lote",
                                     "factura", "defectuos"],
            "mayorista_despachos": ["despacho", "despachos"],
            "mayorista_credito": ["credito", "crédito", "cartera", "cupo",
                                   "estado de cuenta", "facturacion", "facturación"],
            "mayorista_ventas": ["repedido", "repedidos", "mayorista", "mayoreo",
                                  "al por mayor", "tengo una tienda",
                                  "vendo talulah", "mi tienda"],
            "tallas": ["talla", "tallas", "medida", "medidas", "fit"],
            "cambios_garantias": ["cambio", "cambiar", "garantia", "garantía",
                                   "devolucion", "devolución", "defecto",
                                   "quedo grande", "quedó grande", "quedo pequeñ",
                                   "quedó pequeñ"],
            "sedes": ["sede", "sedes", "tienda fisica", "tienda física",
                       "tiendas fisicas", "tiendas físicas", "direccion",
                       "dirección", "horario", "ubicad", "donde queda",
                       "dónde queda", "donde tienen", "dónde tienen"],
            "pagos_promos": ["cupon", "cupón", "descuento", "promo", "pse",
                              "no puedo pagar", "problema con el pago",
                              "error al pagar"],
            "fallas_web": ["pagina", "página", "no carga", "no funciona",
                            "caida", "caída", "la web"],
            "estado_pedido": ["mi pedido", "numero de pedido", "número de pedido",
                               "rastrear", "rastreo", "tracking", "como va",
                               "cómo va", "estado de mi", "mi orden"],
            "tiempos_envio": ["cuanto tarda", "cuánto tarda", "demora",
                               "cuando llega", "cuándo llega", "tiempo de entrega",
                               "tiempos de envio", "tiempos de envío"],
            "catalogo": ["catalogo", "catálogo", "pantalon", "pantalón", "short",
                          "capri", "batola", "satin", "satín", "plus size", "niña",
                          "vestido de baño", "sale", "lo mas nuevo",
                          "lo más nuevo"],
            "asesor": ["asesor", "asesora", "humano", "persona", "agente"],
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


# ---------------------------------------------------------------------------
# Pasos VISUALES del bot (#256/#257): el motor sigue siendo llm_engine (los
# pasos no se ejecutan), pero el visualizador /bots/{id} muestra el flujo real
# con la MISMA estructura de los JSON WATI ("talulah bots/descargados"):
# cadenas de bloques por camino, condiciones (¿pedido encontrado? Sí/No) y
# los menús de botones convertidos en bloques LLM que deciden.
# Posición = índice 1-based; el branching se cablea en _wire().
# ---------------------------------------------------------------------------
STEPS = [
    # 1 — bloque LLM de entrada (reemplaza SAC Orquestador + menús)
    {"step_type": "llm", "label": "🤖 LLM · recibe el mensaje y decide el camino",
     "config": {"mode": "route", "intents": [], "default_step_id": None}},
    # ── Estado de pedido (JSON: Question → Webhook Shopify → Condition) ──
    {"step_type": "llm", "label": "Pedido · pide el dato", "config": {  # 2
        "mode": "accion", "accion": "info", "fuente": "conversación",
        "mensaje": "Para revisar el viaje de tu paquete 🌿✨, escríbeme tu "
                   "número de pedido (sin puntos ni comas, ej: 1234). Si no lo "
                   "tienes, puedo buscarlo con tu nombre, cédula o la fecha "
                   "del pedido."}},
    {"step_type": "llm", "label": "Pedido · consulta Shopify", "config": {  # 3
        "mode": "accion", "accion": "api",
        "fuente": "API Shopify orders.json (número, nombre, cédula o fecha)",
        "mensaje": "Un momentito que reviso tu pedido... 🌿"}},
    {"step_type": "condition", "label": "¿Pedido encontrado?", "config": {  # 4
        "prompt": "¿La consulta a Shopify encontró el pedido?", "branches": {}}},
    {"step_type": "llm", "label": "Pedido · informa estado", "config": {  # 5
        "mode": "accion", "accion": "info", "fuente": "respuesta de Shopify",
        "mensaje": "¡Listo! 🌿 Encontré tu pedido #<número> (<fecha>). "
                   "• Estado de envío: ... • Estado de pago: ... "
                   "• Rastreo: <url>. Te dejo acompañada por aquí ✨"}},
    {"step_type": "llm", "label": "Pedido · no encontrado", "config": {  # 6
        "mode": "accion", "accion": "escalar", "fuente": "conversación",
        "mensaje": "No pude encontrar un pedido con esos datos 🙏🌿. No te "
                   "preocupes — te conecto con una de nuestras asesoras para "
                   "que lo revise contigo 🤎"}},
    # ── Cambios y garantías (JSON: Buttons Cambio|Garantía → sub-flujos) ──
    {"step_type": "llm", "label": "Cambios/Garantías · ¿cuál necesitas?",  # 7
     "config": {"mode": "route", "intents": [],
                "mensaje": "Queremos que te sientas perfecta con tus prendas "
                           "🤎. ¿Necesitas un cambio o una garantía?"}},
    {"step_type": "llm", "label": "Cambio · política", "config": {  # 8
        "mode": "accion", "accion": "info", "fuente": "refund-policy",
        "mensaje": "Qué bueno que nos cuentes 🌿. Los detalles están en "
                   "talulah.com.co/policies/refund-policy ✨ Puedes acercarte "
                   "a cualquiera de nuestras tiendas a nivel nacional y con "
                   "gusto te ayudan. ¿Te puedo ayudar con algo más?"}},
    {"step_type": "llm", "label": "Cambio · ¿algo más?", "config": {  # 9
        "mode": "route", "intents": [],
        "mensaje": "La IA decide: seguir ayudando o pasar a asesora."}},
    {"step_type": "llm", "label": "Garantía · política", "config": {  # 10
        "mode": "accion", "accion": "info", "fuente": "refund-policy",
        "mensaje": "Tranquila, lo solucionamos juntas 🤎. Consulta la política "
                   "en talulah.com.co/policies/refund-policy ✨ ¿Quieres "
                   "enviarnos un caso de garantía?"}},
    {"step_type": "llm", "label": "Garantía · ¿registrar caso?", "config": {  # 11
        "mode": "route", "intents": [],
        "mensaje": "La IA decide: registrar caso, volver o asesora."}},
    {"step_type": "llm", "label": "Garantía · recolecta el caso", "config": {  # 12
        "mode": "accion", "accion": "caso", "fuente": "caso de garantía",
        "mensaje": "Con cariño te ayudo a registrar tu caso 🌿🤎. Envíame: "
                   "• Número de orden • Descripción del detalle • Fotos que "
                   "lo evidencien. Puede ser en uno o varios mensajes ✨"}},
    {"step_type": "llm", "label": "Garantía · caso registrado", "config": {  # 13
        "mode": "accion", "accion": "caso", "fuente": "registro interno",
        "mensaje": "¡Listo! 🌿🤎 Tu caso de garantía quedó registrado. Nuestro "
                   "equipo lo revisa y te responde en ~5 días hábiles. Te "
                   "avisamos por aquí mismo ✨"}},
    # ── Informativos (vuelven al bloque LLM, como InvokeFlow→Orquestador) ──
    {"step_type": "llm", "label": "Tiempos de envío", "config": {  # 14
        "mode": "accion", "accion": "info", "fuente": "shipping-policy",
        "mensaje": "Trabajamos con cariño para que tus prendas lleguen pronto "
                   "📦🌿. Tiempos y condiciones en "
                   "talulah.com.co/policies/shipping-policy ✨ ¿Algo más?"}},
    {"step_type": "llm", "label": "Guía de tallas", "config": {  # 15
        "mode": "accion", "accion": "media", "fuente": "guia_tallas_1..6.jpeg",
        "mensaje": "¡Aquí te dejo nuestra guía de tallas para que encuentres "
                   "tu fit perfecto 🌿! Si necesitas ayuda con las medidas, "
                   "con gusto te acompaño ✨"}},
    {"step_type": "llm", "label": "Sedes físicas", "config": {  # 16
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "¡Nos encantaría recibirte! 🌿 Tiendas Talulah 🤎: Envigado, "
                   "Junín (Medellín), Outlet Envigado y Santafé — dirección, "
                   "teléfono y horarios (L-S 10am-8pm, dom/fest 11am-7pm)."}},
    # ── Con escalamiento directo (JSON: mensaje + AssignAgent) ──
    {"step_type": "llm", "label": "Pagos y promos · tip", "config": {  # 17
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "Tranquila, lo solucionamos juntas 🌿. Tip: intenta el pago "
                   "en incógnito o desde otro dispositivo. Los cupones no "
                   "aplican en SALE ni son acumulables. Una asesora tomará la "
                   "conversación ✨"}},
    {"step_type": "llm", "label": "Fallas web · tips", "config": {  # 18
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "¡Ups! A veces la tecnología necesita un respiro 🌿. "
                   "Intenta: refrescar, otro navegador o dispositivo, borrar "
                   "caché. Una asesora te ayudará a entrar ✨"}},
    {"step_type": "llm", "label": "Catálogo", "config": {  # 19
        "mode": "accion", "accion": "info", "fuente": "talulah.com.co",
        "mensaje": "Con gusto 🤍 te muestro nuestra colección ✨ Pantalón, "
                   "Short, Capri, Batola, Satín, Plus Size, Niña, SALE y "
                   "Hombre en talulah.com.co"}},
    # ── B2B mayoristas (JSON SAC Mayoristas) ──
    {"step_type": "llm", "label": "B2B Despachos · pide nº pedido", "config": {  # 20
        "mode": "accion", "accion": "registro", "fuente": "conversación",
        "mensaje": "Con gusto te ayudo a rastrear tu pedido 🌿. Escríbeme en "
                   "un solo mensaje el número de pedido, sin puntos ni comas."}},
    {"step_type": "llm", "label": "B2B Despachos · registrado", "config": {  # 21
        "mode": "accion", "accion": "registro", "fuente": "registro interno",
        "mensaje": "¡Gracias! 🌿 Registramos tu número de pedido. Una asesora "
                   "de logística se comunicará contigo en breve para darte el "
                   "estado 🤎"}},
    {"step_type": "llm", "label": "B2B Faltantes · recolecta el caso", "config": {  # 22
        "mode": "accion", "accion": "caso", "fuente": "caso B2B",
        "mensaje": "Lamentamos mucho este inconveniente 🙏🌿. Envíanos: "
                   "• Número de lote o factura • Descripción de la novedad "
                   "• Fotos/videos que evidencien el detalle 🤎"}},
    {"step_type": "llm", "label": "B2B Faltantes · caso registrado", "config": {  # 23
        "mode": "accion", "accion": "caso", "fuente": "registro interno",
        "mensaje": "¡Gracias! 🌿🤎 Tu caso quedó registrado. Soporte B2B te "
                   "responde en ~5 días hábiles. Te avisamos por aquí ✨"}},
    {"step_type": "llm", "label": "B2B Cuenta y crédito", "config": {  # 24
        "mode": "accion", "accion": "escalar", "fuente": "asesora de cartera",
        "mensaje": "Perfecto 🌿. Una asesora de cartera se comunicará contigo "
                   "muy pronto para revisar tu facturación, cupos o estado de "
                   "cuenta ✨"}},
    {"step_type": "llm", "label": "B2B Ventas y repedidos", "config": {  # 25
        "mode": "accion", "accion": "escalar", "fuente": "asesor comercial",
        "mensaje": "¡Qué emoción que sigamos creciendo juntas! 🤎 Un asesor "
                   "comercial se comunicará contigo en breve para tomar tu "
                   "pedido y compartirte el catálogo más reciente ✨"}},
    # 26 — bloque LLM post-acción (#265): si el cliente vuelve a escribir tras
    # una acción/mensaje final, la IA relee y decide: nuevo camino o despedida.
    {"step_type": "llm", "label": "🤖 LLM · ¿algo más o despedida?", "config": {
        "mode": "route", "intents": [],
        "mensaje": "La IA lee la respuesta del cliente: si trae un nuevo tema "
                   "lo enruta al camino correspondiente; si solo agradece o se "
                   "despide, cierra la conversación con cariño."}},
    # 27 — handoff · 28 — fin
    {"step_type": "handoff", "label": "Pasar a asesora humana", "config": {
        "assignee": ASESORA_HANDLE,
        "text": "Te voy a comunicar con una de nuestras asesoras para que te "
                "acompañe de forma personal 🌿. Dame un momentito 🤎"}},
    {"step_type": "end", "label": "Fin de la conversación", "config": {}},
]


def _wire(db, bot: models.Bot) -> None:
    """Cablea el diagrama fiel a los JSON WATI: cadenas por camino, condición
    Sí/No del pedido, mini-decisiones LLM donde había botones, retornos al
    bloque de entrada (ex-InvokeFlow→Orquestador) y escalamientos."""
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

    # Router principal (14 caminos, default → asesora como el fallback WATI)
    _route(1, [
        ("Estado de pedido", 2), ("Cambios y garantías", 7),
        ("Tiempos de envío", 14), ("Guía de tallas", 15),
        ("Sedes físicas", 16), ("Pagos y promos", 17), ("Fallas web", 18),
        ("Catálogo", 19), ("B2B Despachos", 20), ("B2B Faltantes", 22),
        ("B2B Cartera", 24), ("B2B Ventas", 25), ("Asesor humano", 27),
        ("Despedida", 28),
    ], default=27)

    # Estado de pedido: pide dato → consulta → ¿encontrado? Sí/No
    P[2].next_step_id = P[3].id
    P[3].next_step_id = P[4].id
    cfg4 = _j.loads(P[4].config or "{}")
    cfg4["branches"] = {"Sí": P[5].id, "No": P[6].id}
    P[4].config = _j.dumps(cfg4, ensure_ascii=False)
    P[4].next_step_id = None
    P[5].next_step_id = P[26].id   # informa → ¿algo más o despedida? (#265)
    P[6].next_step_id = P[27].id   # no encontrado → escalar

    # Cambios/garantías: botones WATI → mini-decisiones LLM
    _route(7, [("Cambio", 8), ("Garantía", 10)])
    P[8].next_step_id = P[9].id
    _route(9, [("Volver al inicio", 1), ("Asesora", 27)])
    P[10].next_step_id = P[11].id
    _route(11, [("Registrar caso", 12), ("Volver al inicio", 1), ("Asesora", 27)])
    P[12].next_step_id = P[13].id
    P[13].next_step_id = P[26].id

    # Informativos → bloque post-acción (#265): nuevo camino o despedida
    for pos in (14, 15, 16, 19):
        P[pos].next_step_id = P[26].id
    # Con escalamiento directo (mensaje + AssignAgent en WATI)
    for pos in (17, 18):
        P[pos].next_step_id = P[27].id

    # B2B: despachos y faltantes en 2 pasos; al cerrar, post-acción (#265);
    # cartera/ventas escalan directo
    P[20].next_step_id = P[21].id
    P[21].next_step_id = P[26].id
    P[22].next_step_id = P[23].id
    P[23].next_step_id = P[26].id
    P[24].next_step_id = P[27].id
    P[25].next_step_id = P[27].id

    # Post-acción: nuevo tema → router · asesora → handoff · despedida → fin
    _route(26, [("Nuevo tema", 1), ("Asesora", 27), ("Despedida", 28)])

    P[27].next_step_id = None
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

        # Un único bot por cuenta (#254): se eliminan TODOS los bots previos
        # del owner y se re-crea el LLM con la config más reciente.
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

        cfg = _llm_config()
        bot = crud.create_bot_with_steps(
            db, owner, name=BOT_NAME,
            description="Bot conversacional (Claude vía Bedrock) de servicio al "
                        "cliente Talulah: minoristas y mayoristas, pedidos "
                        "Shopify, guía de tallas y escalamiento a asesora.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=STEPS, engine="llm", llm_config=cfg,
        )
        _wire(db, bot)
        shopify_estado = "con Shopify" if "shopify" in cfg else "SIN Shopify (faltan env)"
        print(f"OK: bot LLM creado id={bot.id} ({shopify_estado})")

        print()
        print(f"=== Talulah lista. Login: {OWNER_EMAIL} / {OWNER_PWD} ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
