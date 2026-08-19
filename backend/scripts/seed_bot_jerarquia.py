"""Seed idempotente: cuenta demo **Jerarquía** + bot de venta de la Promo Manada.

Jerarquía (`@jerarquia_oficial`) es una marca colombiana de camisetas tipo polo
para hombre. Esta cuenta es una **demostración**: no tiene WhatsApp conectado y
se prueba únicamente desde la ventana "Probar Chatbot" de la app.

Crea/asegura:
  - Cuenta dueña `jerarquia@demo.com` (+ su team "Jerarquía").
  - Asesor humano `asesor1.jerarquia@demo.com` (handle `asesor_1`), destino de
    los handoffs dentro de la app.
  - Bot "Jerarquía IA — Ventas" con engine='llm', contexto a priori `jerarquia`
    y la config `venta` que habilita la herramienta `registrar_venta`.

El bot vende **un solo producto** (3 camisetas tipo polo por $160.000) y tiene
exactamente dos salidas:

  1. `escalar_a_asesor` → cierra el turno (en la simulación, cierra el chat).
  2. `registrar_venta`  → número de pedido + **link de pago de demostración** y
     el aviso de que queda pendiente el comprobante para despachar. Los datos
     que pide son cédula, celular, nombre, dirección de envío y correo.

DATOS PROVISIONALES (confirmar con la marca antes de conectar un WhatsApp real):
tela, tallas, colores, tiempos de entrega y "envío incluido" son placeholders de
la demo y viven en `backend/app/bot_contexts/jerarquia.md`. El precio y la promo
sí los dio el CEO.

El link de pago es **falso a propósito**: apunta a `/pago-demo` del frontend,
una página que dice en letras grandes que es una simulación y no cobra nada.

Un único bot por cuenta (convención #254): el seed elimina los bots previos del
owner y re-crea el bot con la config más reciente.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend \\
        env JERARQUIA_PWD='...' python scripts/seed_bot_jerarquia.py

    # Producción (RDS) vía ECS run-task. Los overrides quedan en CloudTrail,
    # así que NUNCA se manda la contraseña en claro: se manda el hash bcrypt
    # ya calculado (convención adoptada en #303).
    ./backend/scripts/rds_exec.sh backend/scripts/seed_bot_jerarquia.py \\
        JERARQUIA_PWD_HASH='$2b$12$...'

ENV:
    JERARQUIA_PWD | JERARQUIA_PWD_HASH   (uno de los dos, solo al crear la cuenta)
    JERARQUIA_EMAIL                      (default jerarquia@demo.com)
    LINK_PAGO_BASE                       (default https://app.glomabeauty.com/pago-demo?ref={ref})
"""
from __future__ import annotations

import os
import sys

# `rds_exec.sh` manda este archivo como el cuerpo de un `python -c`, donde
# `__file__` no existe; ahí el código ya corre desde /app dentro del contenedor.
_RAIZ = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "__file__" in globals()
    else "/app"
)
sys.path.insert(0, _RAIZ)

from app.database import SessionLocal  # type: ignore
from app import crud, models, schemas  # type: ignore


OWNER_EMAIL = os.environ.get("JERARQUIA_EMAIL", "jerarquia@demo.com")
OWNER_NAME = "Jerarquía"
ASESOR_EMAIL = "asesor1.jerarquia@demo.com"
ASESOR_HANDLE = "asesor_1"
BOT_NAME = "Jerarquía IA — Ventas"

# `{ref}` lo reemplaza el motor por el número de pedido; `total` y `marca` los
# usa la página `/pago-demo` para mostrar el pedido (ver frontend/pages).
LINK_PAGO = os.environ.get(
    "LINK_PAGO_BASE",
    "https://app.glomabeauty.com/pago-demo?ref={ref}&total=160000"
    "&marca=Jerarqu%C3%ADa",
)


def _llm_config() -> dict:
    return {
        "context_key": "jerarquia",
        "assignee": ASESOR_HANDLE,
        # Habilita la tool `registrar_venta`. `link_pago` es una plantilla:
        # el motor reemplaza {ref} por el número de pedido que él genera, y el
        # guardarraíl `_viola_link` descarta cualquier URL que el modelo
        # escriba por su cuenta.
        "venta": {
            "producto": "Promo Manada — 3 camisetas tipo polo",
            "valor": "$160.000",
            "prefijo": "JRQ",
            "link_pago": LINK_PAGO,
        },
        # #255 observabilidad: clasificador del camino por lo que PREGUNTÓ la
        # persona, para los turnos que no llaman herramientas (las tools SON la
        # decisión y tienen prioridad). Orden = prioridad de matcheo.
        "caminos": {
            "venta": ["comprar", "compro", "la quiero", "las quiero", "lo quiero",
                       "me las llevo", "pedido", "pedir", "cedula", "cédula",
                       "direccion", "dirección", "mis datos"],
            "pago": ["pago", "pagar", "link", "contra entrega", "contraentrega",
                      "contra-entrega", "transferencia", "nequi", "daviplata",
                      "tarjeta", "pse", "comprobante", "cuotas"],
            # "cuánto" a secas se lo robaba todo: "¿cuánto demora el envío?" y
            # "¿cuánto tarda el cambio?" salían marcados como consulta de
            # precio. Van las frases completas, no la palabra suelta.
            "precio": ["precio", "cuanto vale", "cuánto vale", "cuanto cuesta",
                        "cuánto cuesta", "cuanto sale", "cuánto sale", "cuesta",
                        "descuento", "rebaja", "barato", "barata", "baratas",
                        "economico", "económico", "ultimo precio",
                        "último precio", "cuanto es", "cuánto es"],
            # Antes de `tallas_colores`: "si no me sirve la talla, ¿la cambian?"
            # es un caso de cambios, no una consulta de tallas.
            "cambios_garantia": ["cambio", "cambios", "cambian", "cambiar",
                                  "devolucion", "devolución", "devolver",
                                  "garantia", "garantía", "no me sirve",
                                  "no me queda", "reclamo"],
            "tallas_colores": ["talla", "tallas", "color", "colores", "medida",
                                "medidas", "negro", "blanco", "vinotinto",
                                "gris", "azul"],
            "envio": ["envio", "envío", "envian", "envían", "domicilio", "llega",
                       "entrega", "flete", "transportadora", "guia", "guía",
                       "demora", "demoran", "tarda", "tardan"],
            "otros_productos": ["camisa", "chaqueta", "gorra", "pantalon",
                                 "pantalón", "buzo", "mujer", "niño", "nino",
                                 "al por mayor", "mayorista", "por mayor",
                                 "personalizada", "bordado", "estampado"],
            # Frases, no palabras sueltas: "persona" a secas marcaba como
            # `asesor` un "¿eres una persona real?", que no pide un humano.
            "asesor": ["hablar con una persona", "con una persona", "un asesor",
                        "una asesora", "asesor humano", "un humano",
                        "con alguien", "atencion humana", "atención humana"],
            "promo": ["promo", "promocion", "promoción", "oferta", "combo",
                       "3 por", "tres por"],
            "producto": ["camiseta", "camisetas", "polo", "polos", "tela",
                          "material", "algodon", "algodón", "calidad", "prenda",
                          "jerarquia", "jerarquía"],
        },
    }


# ---------------------------------------------------------------------------
# Pasos VISUALES (#256): el motor es llm_engine (los pasos NO se ejecutan);
# el visualizador de /bots/{id} muestra el bloque LLM de entrada, los caminos
# y los dos cierres (asesor / venta registrada).
# ---------------------------------------------------------------------------
STEPS = [
    # 1 — bloque LLM de entrada
    {"step_type": "llm", "label": "🤖 LLM · Samuel recibe el mensaje y decide el camino",
     "config": {"mode": "route", "intents": [], "default_step_id": None,
                "mensaje": "Saluda con la voz de Jerarquía, se presenta como "
                           "Samuel, pide el nombre si no lo sabe y presenta la "
                           "única promoción activa."}},
    {"step_type": "llm", "label": "Promo Manada · 3 polos por $160.000", "config": {  # 2
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "Tenemos una sola promoción activa y está fuerte: *3 "
                   "camisetas tipo polo por $160.000* 🔱 con envío a toda "
                   "Colombia."}},
    {"step_type": "llm", "label": "Ficha del producto · tela, tallas y colores", "config": {  # 3
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "Polo en algodón piqué, cuello y puños tejidos. Tallas S, M, "
                   "L y XL en negro, blanco, azul oscuro, gris jaspe y "
                   "vinotinto 👕 Las 3 se combinan libres."}},
    {"step_type": "llm", "label": "Precio fijo · maneja la objeción", "config": {  # 4
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "El precio de la promo es fijo: *$160.000 por las 3*, con el "
                   "envío incluido. Sin descuentos ni precio por unidad — si "
                   "quieren una sola, va a un asesor."}},
    {"step_type": "llm", "label": "Envío y entrega", "config": {  # 5
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "Envío a toda Colombia incluido en el precio 🚛 Entrega "
                   "estimada de 2 a 5 días hábiles según la ciudad."}},
    {"step_type": "llm", "label": "Cómo se paga", "config": {  # 6
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "El pago es por *link de pago en línea*. Cualquier otro "
                   "medio (contra entrega, transferencia, cuotas) lo revisa un "
                   "asesor humano."}},
    {"step_type": "llm", "label": "Venta · pide los 5 datos", "config": {  # 7
        "mode": "accion", "accion": "registro",
        "fuente": "un solo mensaje del cliente",
        "mensaje": "¡De una! 🔥 Mándame en un solo mensaje: *nombre completo*, "
                   "*cédula*, *celular*, *correo* y *dirección de envío con la "
                   "ciudad*. Y dime las *tallas y colores* de las 3 👕"}},
    {"step_type": "llm", "label": "Venta · registra el pedido y manda el link", "config": {  # 8
        "mode": "accion", "accion": "registro",
        "fuente": "tool registrar_venta → número de pedido + link de pago",
        "mensaje": "Pedido *JRQ-XXXXXX* registrado ✅ Este es tu link de pago: "
                   "<link>. Apenas pagues, mándame el *comprobante* por aquí y "
                   "despachamos a la dirección que registraste 🚛"}},
    # 9 — bloque LLM post-acción (#265): relee la respuesta del cliente tras
    # una acción; decide nuevo camino, asesor o despedida.
    {"step_type": "llm", "label": "🤖 LLM · ¿algo más o despedida?", "config": {
        "mode": "route", "intents": [],
        "mensaje": "Samuel lee la respuesta: si trae un tema nuevo lo enruta; "
                   "si pide un humano, escala; si se despide, cierra."}},
    # 10 — handoff (cierra el turno) · 11 — fin
    {"step_type": "handoff", "label": "Pasar a un asesor humano", "config": {
        "assignee": ASESOR_HANDLE,
        "text": "Eso lo ve mejor un asesor del equipo. Ya te conecto con uno "
                "por aquí 🐺"}},
    {"step_type": "end", "label": "Fin de la conversación", "config": {}},
]

# Camino del router principal → posición del bloque que lo atiende.
ROUTER_INTENTS = [
    ("Promo Manada", 2),
    ("Tallas y colores", 3),
    ("Precio / descuento", 4),
    ("Envío", 5),
    ("Medios de pago", 6),
    ("Quiere comprar", 7),
    ("Asesor humano", 10),
    ("Despedida", 11),
]


def _wire(db, bot: models.Bot) -> None:
    """Cablea el diagrama: router LLM → caminos → venta / asesor / fin."""
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

    # Router principal. Default → asesor humano: si el mensaje no cae en
    # ninguno de los caminos del bot, lo atiende una persona (regla del CEO).
    _route(1, ROUTER_INTENTS, default=10)

    for pos in (2, 3, 4, 5, 6):          # informativos → post-acción
        P[pos].next_step_id = P[9].id
    P[7].next_step_id = P[8].id           # pide datos → registra la venta
    P[8].next_step_id = P[9].id           # venta registrada → ¿algo más?

    _route(9, [("Nuevo tema", 1), ("Asesor", 10), ("Despedida", 11)])
    P[10].next_step_id = None             # el handoff cierra la conversación
    db.commit()


def _ensure_user(db, *, nombre, correo, documento) -> models.User:
    """Crea el usuario si no existe. La contraseña llega por env (en claro en
    local, o como hash bcrypt en producción — regla de #303)."""
    user = crud.get_user_by_email(db, correo)
    if user:
        print(f"OK: {correo} ya existía (contraseña sin tocar)")
        return user

    pwd = os.environ.get("JERARQUIA_PWD")
    pwd_hash = os.environ.get("JERARQUIA_PWD_HASH")
    if pwd:
        return crud.create_user(db, schemas.UserCreate(
            nombre=nombre, tipo_documento="CC", documento=documento,
            correo=correo, password=pwd,
        ))
    if pwd_hash:
        user = models.User(
            nombre=nombre, tipo_documento="CC", documento=documento,
            correo=correo, hashed_password=pwd_hash,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    sys.exit(
        "Falta JERARQUIA_PWD (local) o JERARQUIA_PWD_HASH (producción): la "
        "contraseña no va en el código — este repositorio es público."
    )


def main() -> int:
    db = SessionLocal()
    try:
        owner = _ensure_user(
            db, nombre=OWNER_NAME, correo=OWNER_EMAIL, documento="JERARQUIA1",
        )
        team = crud.get_team_by_owner(db, owner)
        if team is None:
            team = crud.create_team(db, OWNER_NAME, owner)
        print(f"OK: owner={owner.correo} team_id={team.id}")

        asesor = _ensure_user(
            db, nombre="Asesor Jerarquía", correo=ASESOR_EMAIL,
            documento="JERARQUIAAS1",
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
            description="Bot de ventas de Jerarquía (Claude vía Bedrock): "
                        "vende la Promo Manada (3 camisetas tipo polo por "
                        "$160.000), registra el pedido con link de pago de "
                        "demostración y escala a un asesor humano todo lo "
                        "demás. Cuenta de demostración: sin WhatsApp "
                        "conectado, se prueba desde el simulador.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=STEPS, engine="llm", llm_config=_llm_config(),
        )
        _wire(db, bot)
        print(f"OK: bot LLM creado id={bot.id} con {len(bot.steps)} bloques visuales")

        print()
        print("=== Cuenta demo de Jerarquía lista ===")
        print(f"  login:   {OWNER_EMAIL}")
        print(f"  bot_id:  {bot.id}  (engine=llm, contexto 'jerarquia')")
        print(f"  canales: solo simulador (WhatsApp sin conectar)")
        print(f"  pago:    {LINK_PAGO}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
