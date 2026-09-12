"""Seed idempotente: cuenta demo **Natulcé** + bot de venta de siropes.

Natulcé es una marca colombiana de **siropes naturales concentrados** para
sodas italianas y coctelería. Esta cuenta es una **demostración**: no tiene
WhatsApp conectado y se prueba únicamente desde la ventana "Probar Chatbot"
de la app.

Crea/asegura:
  - Cuenta dueña `natulce@demo.com` (+ su team "Natulcé").
  - Asesora humana `asesor1.natulce@demo.com` (handle `asesor_1`), destino de
    los handoffs dentro de la app.
  - Bot "Natulcé IA — Ventas" con engine='llm', contexto a priori `natulce` y
    el catálogo de medios de `app/data/bot_natulce.py`.

El bot tiene **tres caminos** y un cierre de pedido:

  1. Bienvenida e info general → texto de la marca + imagen + video + la
     mención de que hay promoción activa.
  2. Porciones y precios → imagen + presentación de 250 ml, más de 30
     preparaciones, $29.000 → $25.000 con el 15% de descuento.
  3. Sabores → los 4 siropes y los 2 endulzantes.
  4. Pedido → pide *nombre*, *dirección* y *pedido* en un solo mensaje, los
     confirma y escala a la asesora.

Un único bot por cuenta (convención #254): el seed elimina los bots previos del
owner y re-crea el bot con la config más reciente.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend \\
        env NATULCE_PWD='...' MEDIA_BASE='http://localhost:3000' \\
        python scripts/seed_bot_natulce.py

    # Producción (RDS) vía ECS run-task. Los overrides quedan en CloudTrail,
    # así que NUNCA se manda la contraseña en claro: se manda el hash bcrypt
    # ya calculado (convención adoptada en #303).
    ./backend/scripts/rds_exec.sh backend/scripts/seed_bot_natulce.py \\
        NATULCE_PWD_HASH='$2b$12$...'

ENV:
    NATULCE_PWD | NATULCE_PWD_HASH   (uno de los dos, solo al crear la cuenta)
    NATULCE_EMAIL                    (default natulce@demo.com)
    MEDIA_BASE                       (default https://glomacx.com)
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
from app.data.bot_natulce import LLM_CONFIG  # type: ignore


OWNER_EMAIL = os.environ.get("NATULCE_EMAIL", "natulce@demo.com")
OWNER_NAME = "Natulcé"
ASESOR_EMAIL = "asesor1.natulce@demo.com"
ASESOR_HANDLE = "asesor_1"
BOT_NAME = "Natulcé IA — Ventas"


# ---------------------------------------------------------------------------
# Pasos VISUALES (#256): el motor es llm_engine (los pasos NO se ejecutan);
# el visualizador de /bots/{id} muestra el bloque LLM de entrada, los tres
# caminos, el cierre de pedido y las dos salidas (asesora / fin).
# ---------------------------------------------------------------------------
STEPS = [
    # 1 — bloque LLM de entrada
    {"step_type": "llm", "label": "🤖 LLM · Naty recibe el mensaje y decide el camino",
     "config": {"mode": "route", "intents": [], "default_step_id": None,
                "mensaje": "Saluda con la voz de Natulcé, se presenta como Naty, "
                           "manda la bienvenida con imagen y video, avisa que "
                           "hay promoción y pide el nombre si no lo sabe."}},
    # 2 — camino 1
    {"step_type": "llm", "label": "1️⃣ Bienvenida · info general + imagen + video", "config": {
        "mode": "accion", "accion": "media",
        "fuente": "enviar_media → promo (imagen) + video_promo (video)",
        "mensaje": "¡Holaaa! ☀️ Aquí tus bebidas saben increíble y se disfrutan "
                   "sin culpa. 😎\n\nCreamos Siropes Naturales ideales para que "
                   "Prepares en Casa Sodas Italianas llenas de Sabor, Fruta Real "
                   "y Menos Calorias🍓🌿\n\n🎉 Y ahora tenemos *promoción "
                   "activa*: de $29mil a $25mil."}},
    # 3 — camino 2
    {"step_type": "llm", "label": "2️⃣ Porciones y precios · imagen + valor", "config": {
        "mode": "accion", "accion": "media",
        "fuente": "enviar_media → precios (imagen)",
        "mensaje": "Los Siropes y Endulzantes en presentación para el Hogar "
                   "*250ml* tienen un valor de *$29mil* y rinden más de *30 "
                   "preparaciones* 😁 Envío nacional $8.000.\n\nPromo: pasan de "
                   "$29mil a *$25mil* — Dsct 15%."}},
    # 4 — camino 3
    {"step_type": "llm", "label": "3️⃣ Sabores · listado de siropes y endulzantes", "config": {
        "mode": "accion", "accion": "info", "fuente": "contexto a priori",
        "mensaje": "*Siropes*: Frutos rojos 🍓 · Frutos amarillos 🍍 · Flor de "
                   "Jamaica 👌🏻 · Maracuyá 😁\n*Endulzantes saludables* 🍃 "
                   "(frías y calientes): Neutro 😊 · Limoncillo 🍋\n\n¿Qué "
                   "sabores te gustaría probar?"}},
    # 5 — cierre de pedido: pide los 3 datos
    {"step_type": "llm", "label": "🛒 Pedido · pide nombre, dirección y pedido", "config": {
        "mode": "accion", "accion": "registro",
        "fuente": "un solo mensaje del cliente",
        "mensaje": "¡Qué rico! 🍹 Para dejar tu pedido listo, mándame en un solo "
                   "mensaje:\n\n*Nombre:*\n*Dirección (con ciudad):*\n*Pedido "
                   "(sabores y cantidad):*"}},
    # 6 — confirma el pedido
    {"step_type": "llm", "label": "🛒 Pedido · confirma los datos y pasa a la asesora", "config": {
        "mode": "accion", "accion": "registro",
        "fuente": "datos del cliente (nombre, dirección, pedido)",
        "mensaje": "¡Listo, <nombre>! 🙌 Confirmo tu pedido: <pedido>, a nombre "
                   "de <nombre>, para <dirección>. Total con envío: <total>. "
                   "Te paso con una asesora para confirmar el pago y el "
                   "despacho 💬"}},
    # 7 — bloque LLM post-acción (#265): relee la respuesta del cliente tras
    # una acción; decide nuevo camino, asesora o despedida.
    {"step_type": "llm", "label": "🤖 LLM · ¿algo más o despedida?", "config": {
        "mode": "route", "intents": [],
        "mensaje": "Naty lee la respuesta: si trae un tema nuevo lo enruta; si "
                   "pide un humano, escala; si se despide, cierra."}},
    # 8 — handoff (cierra el turno) · 9 — fin
    {"step_type": "handoff", "label": "Pasar a una asesora humana", "config": {
        "assignee": ASESOR_HANDLE,
        "text": "Eso lo ve mejor una asesora del equipo 🌿 Ya te conecto con "
                "ella por aquí."}},
    {"step_type": "end", "label": "Fin de la conversación", "config": {}},
]

# Camino del router principal → posición del bloque que lo atiende.
ROUTER_INTENTS = [
    ("Bienvenida / info general", 2),
    ("Porciones y precios", 3),
    ("Sabores", 4),
    ("Quiere pedir", 5),
    ("Asesora humana", 8),
    ("Despedida", 9),
]


def _wire(db, bot: models.Bot) -> None:
    """Cablea el diagrama: router LLM → 3 caminos → pedido / asesora / fin."""
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

    # Router principal. Default → asesora humana: si el mensaje no cae en
    # ninguno de los caminos del bot, lo atiende una persona (regla del CEO).
    _route(1, ROUTER_INTENTS, default=8)

    for pos in (2, 3, 4):        # informativos → post-acción
        P[pos].next_step_id = P[7].id
    P[5].next_step_id = P[6].id   # pide datos → confirma el pedido
    P[6].next_step_id = P[8].id   # pedido confirmado → asesora

    _route(7, [("Nuevo tema", 1), ("Asesora", 8), ("Despedida", 9)])
    P[8].next_step_id = None      # el handoff cierra la conversación
    db.commit()


def _ensure_user(db, *, nombre, correo, documento) -> models.User:
    """Crea el usuario si no existe. La contraseña llega por env (en claro en
    local, o como hash bcrypt en producción — regla de #303)."""
    user = crud.get_user_by_email(db, correo)
    if user:
        print(f"OK: {correo} ya existía (contraseña sin tocar)")
        return user

    pwd = os.environ.get("NATULCE_PWD")
    pwd_hash = os.environ.get("NATULCE_PWD_HASH")
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
        "Falta NATULCE_PWD (local) o NATULCE_PWD_HASH (producción): la "
        "contraseña no va en el código — este repositorio es público."
    )


def main() -> int:
    db = SessionLocal()
    try:
        owner = _ensure_user(
            db, nombre=OWNER_NAME, correo=OWNER_EMAIL, documento="NATULCE1",
        )
        team = crud.get_team_by_owner(db, owner)
        if team is None:
            team = crud.create_team(db, OWNER_NAME, owner)
        print(f"OK: owner={owner.correo} team_id={team.id}")

        asesora = _ensure_user(
            db, nombre="Asesora Natulcé", correo=ASESOR_EMAIL,
            documento="NATULCEAS1",
        )
        if crud.get_membership_for_user(db, asesora) is None:
            crud.add_member_to_team(db, team, asesora, role="agent")
        print(f"OK: asesora={asesora.correo} (handle={ASESOR_HANDLE})")

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
            description="Bot de ventas de Natulcé (Claude vía Bedrock): "
                        "siropes naturales concentrados para sodas italianas. "
                        "Tres caminos — bienvenida con imagen y video, "
                        "porciones y precios, y sabores — y cierre de pedido "
                        "con nombre, dirección y pedido. Cuenta de "
                        "demostración: sin WhatsApp conectado, se prueba desde "
                        "el simulador.",
            channels=["whatsapp"], trigger_type=models.BOT_TRIGGER_DEFAULT,
            steps=STEPS, engine="llm", llm_config=LLM_CONFIG,
        )
        _wire(db, bot)
        print(f"OK: bot LLM creado id={bot.id} con {len(bot.steps)} bloques visuales")

        print()
        print("=== Cuenta demo de Natulcé lista ===")
        print(f"  login:   {OWNER_EMAIL}")
        print(f"  bot_id:  {bot.id}  (engine=llm, contexto 'natulce')")
        print(f"  medios:  {LLM_CONFIG['media']['promo']['url']}")
        print(f"  canales: solo simulador (WhatsApp sin conectar)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
