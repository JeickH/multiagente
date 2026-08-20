"""Cuenta de prueba con MUCHAS conversaciones, para medir rendimiento.

Por qué existe: los problemas de rendimiento de `/mensajes` y `/conversaciones`
no se ven con las 13 conversaciones que hay en local. Se ven a las 600. Este
script fabrica ese volumen en una cuenta desechable, para poder medir el antes y
el después de una optimización con números en vez de con impresiones.

Uso (local):
    docker compose exec backend python backend/scripts/seed_carga_conversaciones.py
    docker compose exec backend python backend/scripts/seed_carga_conversaciones.py \
        --conversaciones 1200 --mensajes 30 --limpiar

Qué crea, todo colgando de la cuenta de prueba:
  - un user + su team + un bot,
  - N conversaciones de WhatsApp con M mensajes cada una,
  - W chats web en `bot_llm_decisions` (los que no tienen `conversation_id`),
  - bitácora del motor para una parte de las conversaciones de WhatsApp.

Tres candados, porque este script escribe y borra a lo bruto:
  1. Solo corre si `APP_ENV` no es `production`.
  2. El correo tiene que terminar en un dominio de prueba (`--correo` incluido).
  3. `--limpiar` borra ÚNICAMENTE lo que cuelga de esa cuenta, y solo si se pide
     explícitamente. Sin la bandera, el script agrega y no borra nada.

Los teléfonos son sintéticos y se generan en tiempo de ejecución a partir de un
prefijo reservado para pruebas: no hay un solo número de una persona real ni
aquí ni en la base que esto llena (regla de seguridad #8).
"""
from __future__ import annotations

import argparse
import os
import random
import secrets
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import delete, select  # type: ignore  # noqa: E402

from app import crud, models, schemas  # type: ignore  # noqa: E402
from app.database import SessionLocal  # type: ignore  # noqa: E402

# Dominios donde se permite fabricar carga. Cualquier otro correo aborta.
DOMINIOS_DE_PRUEBA = ("@test.com", "@example.com", "@localhost")

# Prefijo sintético para los "teléfonos". No es un rango asignable en Colombia:
# los móviles reales empiezan en 3 y aquí el indicativo nacional va seguido de
# un 9, que no existe. Así ninguna prueba puede terminar escribiéndole a alguien.
PREFIJO_SINTETICO = "5790"

NOMBRES = [
    "Ana", "Bruno", "Carla", "Diego", "Elena", "Felipe", "Gabriela", "Hugo",
    "Irene", "Julián", "Karen", "Leo", "Marcela", "Nicolás", "Olga", "Pablo",
    "Quintero", "Rocío", "Santiago", "Tatiana", "Úrsula", "Valentina",
]
APELLIDOS = [
    "Gómez", "Rojas", "Martínez", "Suárez", "Cardona", "Vélez", "Ospina",
    "Restrepo", "Arango", "Mejía", "Zapata", "Herrera",
]

ENTRANTES = [
    "Hola, buenas tardes",
    "Quiero saber si tienen disponibilidad",
    "¿Cuánto cuesta?",
    "¿Me pueden ayudar con un pedido?",
    "Gracias, quedo atento",
    "¿Hasta qué hora atienden?",
    "Perfecto, ¿cómo hago para pagar?",
    "¿Tienen envío a Medellín?",
    "Necesito hablar con un asesor",
    "Listo, muchas gracias",
]
SALIENTES = [
    "¡Hola! Con gusto te ayudo 😊",
    "Claro que sí, te cuento las opciones que tenemos disponibles.",
    "El valor es de $120.000 e incluye el envío.",
    "Sí, hacemos envíos a todo el país en 2 a 3 días hábiles.",
    "Te paso el enlace de pago para que completes la compra.",
    "Atendemos de lunes a sábado, de 8:00 a.m. a 6:00 p.m.",
    "Ya quedó registrado tu pedido, te aviso cuando salga.",
    "Un asesor continúa contigo en un momento.",
]
CAMINOS = [
    "respuesta_libre", "estado_pedido", "tallas", "precios",
    "escalar_a_asesor", "agendar_cita", "catalogo",
]
ESTADOS = ["open", "open", "open", "pending", "pending", "closed"]


def _guardas(correo: str) -> None:
    if os.getenv("APP_ENV", "development").lower() == "production":
        sys.exit("ABORTA: este script no corre con APP_ENV=production.")
    if not correo.endswith(DOMINIOS_DE_PRUEBA):
        sys.exit(
            f"ABORTA: '{correo}' no es una cuenta de prueba. "
            f"Dominios permitidos: {', '.join(DOMINIOS_DE_PRUEBA)}"
        )


def _cuenta(db, correo: str, nombre: str) -> tuple[models.User, models.Team, str | None]:
    """Devuelve (user, team, password_nuevo). El password es None si ya existía."""
    user = crud.get_user_by_email(db, correo)
    password = None
    if user is None:
        password = secrets.token_urlsafe(10)[:14]
        user = crud.create_user(
            db,
            schemas.UserCreate(
                nombre=nombre,
                tipo_documento="CC",
                documento=f"CARGA{secrets.token_hex(4).upper()}",
                correo=correo,
                password=password,
            ),
        )
    membresia = crud.get_membership_for_user(db, user)
    if membresia is None:
        team = crud.create_team(db, nombre=f"Equipo de {nombre}", owner=user)
    else:
        team = db.get(models.Team, membresia.team_id)
    return user, team, password


def _bot(db, user: models.User, team: models.Team) -> models.Bot:
    bot = (
        db.query(models.Bot)
        .filter(models.Bot.user_id == user.id, models.Bot.name == "Bot de carga")
        .first()
    )
    if bot is None:
        bot = models.Bot(
            user_id=user.id,
            team_id=team.id,
            name="Bot de carga",
            description="Bot sintético para pruebas de rendimiento",
            engine="llm",
            channels="whatsapp",
        )
        db.add(bot)
        db.commit()
        db.refresh(bot)
    return bot


def _limpiar(db, team: models.Team, bot: models.Bot) -> tuple[int, int]:
    """Borra lo que este mismo script creó, y nada más.

    Las conversaciones se llevan sus mensajes por el ON DELETE CASCADE de la FK,
    pero `bot_llm_decisions.conversation_id` es SET NULL: si no se borran primero
    las decisiones, quedarían huérfanas apareciendo como "chats web" fantasma.
    """
    decisiones = db.execute(
        delete(models.BotLlmDecision).where(models.BotLlmDecision.bot_id == bot.id)
    ).rowcount
    convs = db.execute(
        delete(models.Conversation).where(models.Conversation.team_id == team.id)
    ).rowcount
    db.commit()
    return convs, decisiones


def _telefono(i: int) -> str:
    return f"{PREFIJO_SINTETICO}{i:07d}"


def _contacto(rnd: random.Random) -> str:
    return f"{rnd.choice(NOMBRES)} {rnd.choice(APELLIDOS)}"


def sembrar(args: argparse.Namespace) -> None:
    _guardas(args.correo)
    rnd = random.Random(args.semilla)
    db = SessionLocal()
    try:
        user, team, password = _cuenta(db, args.correo, args.nombre)
        bot = _bot(db, user, team)

        if args.limpiar:
            convs, decs = _limpiar(db, team, bot)
            print(f"🧹 Limpieza previa: {convs} conversaciones y {decs} decisiones borradas.")

        # Los teléfonos ya usados no se pueden repetir: `uq_team_contact` es
        # única por (team, contacto). Se arranca después del último para poder
        # correr el script varias veces y acumular carga.
        usados = db.execute(
            select(models.Conversation.contact_wa_id)
            .where(models.Conversation.team_id == team.id)
        ).scalars().all()
        offset = len(usados)

        ahora = datetime.utcnow()
        convs: list[models.Conversation] = []
        for i in range(args.conversaciones):
            # Repartidas hacia atrás en el tiempo, unos minutos entre cada una,
            # para que ordenar por `last_message_at` tenga sentido.
            fin = ahora - timedelta(minutes=7 * i)
            convs.append(models.Conversation(
                team_id=team.id,
                contact_wa_id=_telefono(offset + i + 1),
                contact_name=_contacto(rnd),
                status=rnd.choice(ESTADOS),
                assigned_to="bot" if rnd.random() < 0.75 else f"asesor_{rnd.randint(1, 3)}",
                created_at=fin - timedelta(hours=2),
                last_message_at=fin,
            ))
        db.bulk_save_objects(convs, return_defaults=True)
        db.commit()
        print(f"💬 {len(convs)} conversaciones creadas.")

        # Mensajes: en lotes, porque 600 × 20 son 12.000 filas y mandarlas de a
        # una tarda minutos.
        total_msgs = 0
        lote: list[models.Message] = []
        for conv in convs:
            base = conv.last_message_at - timedelta(minutes=2 * args.mensajes)
            for t in range(args.mensajes):
                entrante = t % 2 == 0
                lote.append(models.Message(
                    conversation_id=conv.id,
                    direction="inbound" if entrante else "outbound",
                    content=rnd.choice(ENTRANTES if entrante else SALIENTES),
                    message_type="text",
                    status="received" if entrante else "sent",
                    created_at=base + timedelta(minutes=2 * t),
                ))
            if len(lote) >= 2000:
                db.bulk_save_objects(lote)
                db.commit()
                total_msgs += len(lote)
                lote = []
        if lote:
            db.bulk_save_objects(lote)
            db.commit()
            total_msgs += len(lote)
        print(f"✉️  {total_msgs} mensajes creados.")

        # Bitácora del motor. Dos sabores, porque la ventana de supervisión lee
        # los dos: con `conversation_id` (WhatsApp) y sin él (chat web).
        decisiones: list[models.BotLlmDecision] = []
        con_bitacora = convs[: int(len(convs) * args.proporcion_bitacora)]
        for conv in con_bitacora:
            for t in range(args.turnos_bitacora):
                decisiones.append(models.BotLlmDecision(
                    bot_id=bot.id,
                    conversation_id=conv.id,
                    source="whatsapp",
                    user_input=rnd.choice(ENTRANTES),
                    camino=rnd.choice(CAMINOS),
                    reply_preview=rnd.choice(SALIENTES),
                    rounds=1,
                    latency_ms=rnd.randint(800, 4200),
                    created_at=conv.last_message_at - timedelta(minutes=3 * t),
                ))
        for w in range(args.chats_web):
            chat_ref = f"carga-{secrets.token_hex(6)}"
            inicio = ahora - timedelta(minutes=11 * w)
            contacto = _contacto(rnd) if rnd.random() < 0.4 else None
            for t in range(args.turnos_web):
                decisiones.append(models.BotLlmDecision(
                    bot_id=bot.id,
                    conversation_id=None,
                    source="web",
                    user_input=rnd.choice(ENTRANTES),
                    camino=rnd.choice(CAMINOS),
                    reply_preview=rnd.choice(SALIENTES),
                    chat_ref=chat_ref,
                    chat_contacto=contacto,
                    rounds=1,
                    latency_ms=rnd.randint(800, 4200),
                    created_at=inicio + timedelta(minutes=2 * t),
                ))
            if len(decisiones) >= 2000:
                db.bulk_save_objects(decisiones)
                db.commit()
                decisiones = []
        if decisiones:
            db.bulk_save_objects(decisiones)
            db.commit()

        totales = _totales(db, team, bot)
        print(
            f"🤖 bitácora del motor: {totales['decisiones']} turnos "
            f"({args.chats_web} chats web + {len(con_bitacora)} conversaciones con bitácora)."
        )
        print()
        print(f"✅ Cuenta de carga lista: {args.correo}")
        print(f"   team_id={team.id}  bot_id={bot.id}")
        print(f"   conversaciones={totales['conversaciones']}  mensajes={totales['mensajes']}")
        if password:
            print(f"   password (NUEVO, guárdalo): {password}")
        else:
            print("   password: el que ya tenía (no se tocó).")
    finally:
        db.close()


def _totales(db, team: models.Team, bot: models.Bot) -> dict[str, int]:
    convs = db.query(models.Conversation).filter(
        models.Conversation.team_id == team.id).count()
    msgs = db.query(models.Message).join(models.Conversation).filter(
        models.Conversation.team_id == team.id).count()
    decs = db.query(models.BotLlmDecision).filter(
        models.BotLlmDecision.bot_id == bot.id).count()
    return {"conversaciones": convs, "mensajes": msgs, "decisiones": decs}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--correo", default="carga@test.com")
    p.add_argument("--nombre", default="Cuenta de Carga")
    p.add_argument("--conversaciones", type=int, default=600)
    p.add_argument("--mensajes", type=int, default=20,
                   help="mensajes por conversación")
    p.add_argument("--chats-web", type=int, default=300,
                   help="chats web (sin conversation_id) en la bitácora")
    p.add_argument("--turnos-web", type=int, default=6)
    p.add_argument("--turnos-bitacora", type=int, default=4,
                   help="turnos de bitácora por conversación de WhatsApp")
    p.add_argument("--proporcion-bitacora", type=float, default=0.5,
                   help="qué fracción de las conversaciones tiene bitácora del motor")
    p.add_argument("--semilla", type=int, default=42)
    p.add_argument("--limpiar", action="store_true",
                   help="borra la carga anterior DE ESTA CUENTA antes de sembrar")
    sembrar(p.parse_args())


if __name__ == "__main__":
    main()
