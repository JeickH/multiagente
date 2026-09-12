"""Seed idempotente: datos de demostración de **Natulcé** (conversaciones +
campañas), para que la app se vea viva cuando se le muestra al cliente.

Requiere que `seed_bot_natulce.py` haya corrido antes (usa su cuenta y su
asesora).

Qué crea, todo colgando del team de `natulce@demo.com`:

  - **6 conversaciones** con su historial completo, incluidas las burbujas de
    imagen y video que manda el bot:
      1. Daniela Ospina — recorre los tres caminos y **cierra el pedido**
         (nombre, dirección y pedido) → pasa a la asesora.
      2. Camila Restrepo — **abandona y retoma**: pregunta el precio, se queda
         callada, a las 3 horas le llega el recordatorio ("Hola 👀 me dejaste
         en visto 🙊…") y vuelve a escribir.
      3. Andrés Mejía — pregunta por endulzantes para el café.
      4. Valentina Suárez — pregunta cuánto rinde y queda de pensarlo.
      5. Julián Cardona — pide precio al por mayor → escalado a la asesora.
      6. Marcela Gil — **abandonada de verdad**: no contestó ni al segundo
         recordatorio, queda con la etiqueta "conversación abandonada".
  - **18 contactos** sintéticos, 2 grupos y 2 plantillas WhatsApp mock
    APPROVED, para el módulo de Campañas.
  - **3 campañas**: dos completadas con métricas (enviado / entregado / leído /
    fallido) y una agendada a futuro.

Los teléfonos son **sintéticos** (`+57 300 000 00XX`): no hay un solo número de
una persona real ni aquí ni en la base que esto llena (regla de seguridad #8).

Idempotencia: las conversaciones se saltan si ya tienen mensajes; contactos por
`(team_id, phone_e164)`, grupos por `(team_id, name)`, plantillas por
`(meta_account_id, name, language)` y campañas por `(team_id, name)`.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend \\
        env MEDIA_BASE='http://localhost:3000' python scripts/seed_demo_natulce.py

    # Producción (RDS) vía ECS run-task
    ./backend/scripts/rds_exec.sh backend/scripts/seed_demo_natulce.py
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta

_RAIZ = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "__file__" in globals()
    else "/app"
)
sys.path.insert(0, _RAIZ)

from app.database import SessionLocal  # type: ignore
from app import crud, models  # type: ignore
from app.data.bot_natulce import MEDIA  # type: ignore


OWNER_EMAIL = os.environ.get("NATULCE_EMAIL", "natulce@demo.com")
ASESOR_HANDLE = "asesor_1"

IMG_PROMO = MEDIA["promo"]["url"]
VID_PROMO = MEDIA["video_promo"]["url"]
IMG_PRECIOS = MEDIA["precios"]["url"]

BIENVENIDA = (
    "¡Holaaa! ☀️ Aquí tus bebidas saben increíble y se disfrutan sin culpa. 😎\n\n"
    "Creamos Siropes Naturales ideales para que Prepares en Casa Sodas "
    "Italianas llenas de Sabor, Fruta Real y Menos Calorias🍓🌿\n\n"
    "🎉 Y esta semana tenemos *promoción activa*. ¿Con quién tengo el gusto? 😊"
)
SABORES = (
    "*Siropes*\n"
    "Frutos rojos 🍓\n"
    "Frutos amarillos 🍍\n"
    "Flor de Jamaica 👌🏻\n"
    "Maracuyá 😁\n\n"
    "*Endulzantes Saludables* 🍃 (para bebidas frías y calientes):\n"
    "Neutro 😊\n"
    "Limoncillo 🍋\n\n"
    "Cuéntame entonces qué sabores te gustaría probar?"
)
PRECIOS = (
    "Los Siropes y Endulzantes en presentación para el Hogar *250ml* tienen un "
    "valor de *$29mil* y rinden más de *30 preparaciones* 😁\n\n"
    "Cuéntame qué dudas te puedo ayudar a resolver o qué sabores te gustaría "
    "probar? 🍹\n"
    "Los endulzantes y siropes pasan de estar en $29mil a *$25mil* Dsct 15%"
)
PIDE_DATOS = (
    "¡Qué rico! 🍹 Para dejar tu pedido listo, mándame en un solo mensaje:\n\n"
    "*Nombre:*\n*Dirección (con ciudad):*\n*Pedido (sabores y cantidad):*"
)
RECORDATORIO_3H = "Hola 👀 me dejaste en visto 🙊…"
RECORDATORIO_23H = (
    "Última razón por hoy 🍹 Si más adelante quieres probar los siropes, aquí "
    "estoy. ¡Que estés muy bien! 😊"
)


# ---------------------------------------------------------------------------
# Conversaciones. Cada mensaje es (direction, tipo, contenido, minutos_atrás).
# `tipo` es el `message_type`: text | image | video. En los de media el
# contenido va "caption\nURL", igual que lo persiste `bot_runner._send_media`.
# ---------------------------------------------------------------------------
H = 60  # minutos en una hora

CONVERSACIONES = [
    # 1 ── El pedido cerrado. Recorre los tres caminos y termina en la asesora.
    {
        "wa_id": "573000000011",
        "name": "Daniela Ospina",
        "status": "open",
        "assigned_to": ASESOR_HANDLE,
        "etiqueta": None,
        "messages": [
            ("inbound", "text", "Hola, buenas 🙌", 95),
            ("outbound", "text", BIENVENIDA, 95),
            ("outbound", "image", f"\n{IMG_PROMO}", 94),
            ("outbound", "video", f"\n{VID_PROMO}", 94),
            ("inbound", "text", "Soy Daniela. Qué sabores tienen?", 92),
            ("outbound", "text", "¡Hola Daniela! 😊\n\n" + SABORES, 92),
            ("inbound", "text", "Y cuánto vale el de frutos rojos?", 89),
            ("outbound", "image", f"{PRECIOS}\n{IMG_PRECIOS}", 88),
            ("inbound", "text", "Buenísimo, y cuántos vasos salen de un frasco?", 85),
            (
                "outbound",
                "text",
                "Rinde más de *30 preparaciones* 🍹 vasos de 22 oz, así que te "
                "dura bastante. Y con la promo te queda en *$25mil* 🌿",
                85,
            ),
            ("inbound", "text", "Listo, quiero hacer el pedido", 82),
            ("outbound", "text", PIDE_DATOS, 82),
            (
                "inbound",
                "text",
                "Daniela Ospina\nCra 43A #18-95, Medellín\n2 frutos rojos y 1 maracuyá",
                78,
            ),
            (
                "outbound",
                "text",
                "¡Listo, Daniela! 🙌 Confirmo tu pedido:\n\n*Nombre:* Daniela "
                "Ospina\n*Dirección:* Cra 43A #18-95, Medellín\n*Pedido:* 2 "
                "frutos rojos 🍓 y 1 maracuyá 😁\n\n3 unidades x $25.000 = "
                "$75.000 + $8.000 de envío = *$83.000*",
                77,
            ),
            (
                "outbound",
                "text",
                "Te paso con una asesora para confirmar el pago y el despacho 💬",
                77,
            ),
        ],
    },
    # 2 ── ABANDONÓ Y RETOMÓ. Es la que se muestra en la demo.
    {
        "wa_id": "573000000012",
        "name": "Camila Restrepo",
        "status": "open",
        "assigned_to": "bot",
        "etiqueta": None,   # ya retomó: la etiqueta de abandono se levantó
        "messages": [
            ("inbound", "text", "Hola! vi el sirope en Instagram", 8 * H),
            ("outbound", "text", BIENVENIDA, 8 * H),
            ("outbound", "image", f"\n{IMG_PROMO}", 8 * H - 1),
            ("outbound", "video", f"\n{VID_PROMO}", 8 * H - 1),
            ("inbound", "text", "Camila. Cuánto cuesta?", 8 * H - 4),
            ("outbound", "image", f"{PRECIOS}\n{IMG_PRECIOS}", 8 * H - 5),
            # ── 3 horas de silencio ──
            ("outbound", "text", RECORDATORIO_3H, 5 * H - 5),
            # ── y contestó ──
            (
                "inbound",
                "text",
                "Jajaja perdón, se me pasó 🙈 sí me interesa, qué sabores tienen?",
                4 * H - 20,
            ),
            ("outbound", "text", SABORES, 4 * H - 20),
            ("inbound", "text", "El de flor de jamaica suena rico, lo tienen disponible?", 4 * H - 15),
            (
                "outbound",
                "text",
                "¡Sí, disponible! 🌺 Flor de Jamaica es de los más pedidos. "
                "Con la promo te queda en *$25mil* el frasco de 250ml 😊 "
                "¿Te lo aparto?",
                4 * H - 15,
            ),
        ],
    },
    # 3 ── Endulzantes para bebidas calientes. Cerrada.
    {
        "wa_id": "573000000013",
        "name": "Andrés Mejía",
        "status": "closed",
        "assigned_to": "bot",
        "etiqueta": None,
        "messages": [
            ("inbound", "text", "Buenas, esto sirve para endulzar el café?", 26 * H),
            (
                "outbound",
                "text",
                "¡Hola! 🌿 Sí: los *endulzantes saludables* (Neutro 😊 y "
                "Limoncillo 🍋) sirven para bebidas frías *y calientes* — café, "
                "té, aromáticas. Endulzan sin aportar sabor de fruta.\n\n"
                "¿Con quién tengo el gusto? 😊",
                26 * H,
            ),
            ("inbound", "text", "Andrés. El neutro entonces, cuánto vale?", 25 * H - 40),
            ("outbound", "image", f"{PRECIOS}\n{IMG_PRECIOS}", 25 * H - 41),
            ("inbound", "text", "Perfecto, gracias! lo pienso y te escribo", 25 * H - 35),
            (
                "outbound",
                "text",
                "¡Con gusto, Andrés! 😊 Aquí estoy cuando quieras. Que tengas un "
                "buen día 🌿",
                25 * H - 35,
            ),
        ],
    },
    # 4 ── Consulta de rendimiento, sin cerrar.
    {
        "wa_id": "573000000014",
        "name": "Valentina Suárez",
        "status": "open",
        "assigned_to": "bot",
        "etiqueta": None,
        "messages": [
            ("inbound", "text", "Hola, cuánto rinde un frasco?", 3 * H),
            ("outbound", "text", BIENVENIDA, 3 * H),
            ("outbound", "image", f"\n{IMG_PROMO}", 3 * H - 1),
            ("outbound", "video", f"\n{VID_PROMO}", 3 * H - 1),
            ("inbound", "text", "Valentina 😊", 2 * H - 50),
            ("outbound", "image", f"{PRECIOS}\n{IMG_PRECIOS}", 2 * H - 51),
            ("inbound", "text", "Uy qué bueno, y hacen envíos a Cali?", 2 * H - 45),
            (
                "outbound",
                "text",
                "¡Sí, Valentina! 🚚 Enviamos a toda Colombia, el envío nacional "
                "es de $8.000. ¿Qué sabor te gustaría probar? 🍓",
                2 * H - 45,
            ),
        ],
    },
    # 5 ── Al por mayor → escalado a la asesora.
    {
        "wa_id": "573000000015",
        "name": "Julián Cardona",
        "status": "pending",
        "assigned_to": ASESOR_HANDLE,
        "etiqueta": None,
        "messages": [
            (
                "inbound",
                "text",
                "Buenas tardes, tengo una cafetería y quiero comprar al por mayor",
                6 * H,
            ),
            (
                "outbound",
                "text",
                "¡Hola! 🌿 Qué chévere. El precio al por mayor lo maneja "
                "directamente una asesora del equipo, ya te conecto con ella "
                "por aquí 💬",
                6 * H,
            ),
        ],
    },
    # 6 ── ABANDONADA de verdad: ni con el segundo recordatorio contestó.
    {
        "wa_id": "573000000016",
        "name": "Marcela Gil",
        "status": "open",
        "assigned_to": ASESOR_HANDLE,
        "etiqueta": "conversación abandonada",
        "messages": [
            ("inbound", "text", "Hola, me interesa el de maracuyá", 30 * H),
            ("outbound", "text", BIENVENIDA, 30 * H),
            ("outbound", "image", f"\n{IMG_PROMO}", 30 * H - 1),
            ("outbound", "video", f"\n{VID_PROMO}", 30 * H - 1),
            ("inbound", "text", "Marcela. Cuánto vale?", 29 * H - 50),
            ("outbound", "image", f"{PRECIOS}\n{IMG_PRECIOS}", 29 * H - 51),
            ("outbound", "text", RECORDATORIO_3H, 26 * H - 51),
            ("outbound", "text", RECORDATORIO_23H, 6 * H - 51),
        ],
    },
]


# ---------------------------------------------------------------------------
# Campañas
# ---------------------------------------------------------------------------
CONTACTOS = [
    ("Daniela Ospina", "Medellín", "cliente"),
    ("Camila Restrepo", "Bogotá", "prospecto"),
    ("Andrés Mejía", "Medellín", "prospecto"),
    ("Valentina Suárez", "Cali", "prospecto"),
    ("Julián Cardona", "Medellín", "mayorista"),
    ("Marcela Gil", "Bogotá", "prospecto"),
    ("Laura Betancur", "Medellín", "cliente"),
    ("Santiago Arango", "Bogotá", "cliente"),
    ("Paula Zapata", "Cali", "cliente"),
    ("Mateo Vélez", "Medellín", "cliente"),
    ("Isabella Henao", "Bogotá", "prospecto"),
    ("Tomás Giraldo", "Cali", "cliente"),
    ("Sara Montoya", "Medellín", "cliente"),
    ("Nicolás Rendón", "Bogotá", "prospecto"),
    ("Juliana Posada", "Cali", "cliente"),
    ("Emilio Salazar", "Medellín", "mayorista"),
    ("Antonia Correa", "Bogotá", "cliente"),
    ("Simón Uribe", "Medellín", "prospecto"),
]

PLANTILLAS = [
    {
        "name": "promo_siropes_natulce",
        "language": "es",
        "category": "MARKETING",
        "components_json": [
            {"type": "HEADER", "format": "TEXT", "text": "Promo Natulcé 🍓"},
            {
                "type": "BODY",
                "text": (
                    "Hola {{1}}, esta semana los siropes y endulzantes Natulcé "
                    "pasan de $29mil a {{2}} (15% de descuento). Un frasco de "
                    "250ml rinde más de 30 preparaciones 🍹"
                ),
                "example": {"body_text": [["Daniela", "$25mil"]]},
            },
            {"type": "FOOTER", "text": "Responde STOP para no recibir más"},
        ],
    },
    {
        "name": "nuevo_sabor_jamaica",
        "language": "es",
        "category": "MARKETING",
        "components_json": [
            {
                "type": "BODY",
                "text": (
                    "¡Llegó Flor de Jamaica! 🌺 Nuestro nuevo sirope natural, "
                    "endulzado con stevia y 90% menos calorías. ¿Te contamos "
                    "cómo prepararlo?"
                ),
            },
        ],
    },
]

GRUPOS = [
    {
        "name": "Clientes que ya compraron",
        "description": "Contactos marcados como cliente",
        "filtro": lambda c: c[2] == "cliente",
    },
    {
        "name": "Prospectos de Instagram",
        "description": "Contactos que escribieron y aún no compran",
        "filtro": lambda c: c[2] == "prospecto",
    },
]


def _telefono(i: int) -> str:
    """Teléfono sintético `+57 300 000 00XX`. No es un número asignable: la
    demo nunca puede terminar escribiéndole a una persona real (regla #8)."""
    return f"+5730000000{i:02d}"


def _wamid(idx: int) -> str:
    return f"wamid.natulce-{idx}-{uuid.uuid4().hex[:8]}"


def _seed_conversacion(db, team_id: int, spec: dict) -> str:
    conv = crud.get_or_create_conversation(
        db, team_id=team_id, contact_wa_id=spec["wa_id"], contact_name=spec["name"],
    )
    if conv.messages:
        return "skip"

    ahora = datetime.utcnow()
    for direction, tipo, contenido, mins in spec["messages"]:
        db.add(
            models.Message(
                conversation_id=conv.id,
                direction=direction,
                content=contenido,
                message_type=tipo,
                status="received" if direction == "inbound" else "delivered",
                created_at=ahora - timedelta(minutes=mins),
                sent_by_user_id=None,   # todo lo saliente lo mandó el bot
            )
        )

    conv.last_message_at = ahora - timedelta(minutes=spec["messages"][-1][3])
    conv.status = spec["status"]
    conv.assigned_to = spec["assigned_to"]
    conv.etiqueta = spec["etiqueta"]
    db.commit()
    return "nuevo"


def _meta_account(db, team_id: int) -> models.MetaAccount:
    """La MetaAccount del team; si no hay, una sandbox mock (la columna del
    token es NOT NULL, así que se cifra un placeholder)."""
    meta = (
        db.query(models.MetaAccount)
        .filter(models.MetaAccount.team_id == team_id)
        .first()
    )
    if meta is not None:
        return meta
    try:
        from app.services.crypto import encrypt_secret  # type: ignore
        placeholder = encrypt_secret("sandbox-placeholder")
    except Exception:
        placeholder = "sandbox-placeholder"
    meta = models.MetaAccount(
        team_id=team_id,
        phone_number_id="natulce-demo-phone",
        waba_id="natulce-demo-waba",
        display_phone="+57 300 000 0000",
        verified_name="Natulcé",
        encrypted_access_token=placeholder,
        api_version="v22.0",
        is_active=True,
        status="active",
    )
    db.add(meta)
    db.commit()
    db.refresh(meta)
    return meta


def _seed_contactos(db, team_id: int) -> list[models.Contact]:
    out: list[models.Contact] = []
    for i, (nombre, ciudad, segmento) in enumerate(CONTACTOS):
        tel = _telefono(i + 11)
        c = (
            db.query(models.Contact)
            .filter(
                models.Contact.team_id == team_id,
                models.Contact.phone_e164 == tel,
            )
            .first()
        )
        if c is None:
            c = models.Contact(
                team_id=team_id, phone_e164=tel, name=nombre,
                attributes={"city": ciudad, "segment": segmento},
                opt_in=True, opt_in_source="import_csv",
            )
            db.add(c)
            db.flush()
        else:
            c.name = nombre
            c.attributes = {"city": ciudad, "segment": segmento}
            c.opt_in = True
        out.append(c)
    db.commit()
    return out


def _seed_grupos(db, team_id: int, contactos: list[models.Contact]) -> dict:
    grupos = {}
    for g in GRUPOS:
        grupo = (
            db.query(models.ContactGroup)
            .filter(
                models.ContactGroup.team_id == team_id,
                models.ContactGroup.name == g["name"],
            )
            .first()
        )
        if grupo is None:
            grupo = models.ContactGroup(
                team_id=team_id, name=g["name"], description=g["description"]
            )
            db.add(grupo)
            db.flush()
        elegidos = [contactos[i] for i, c in enumerate(CONTACTOS) if g["filtro"](c)]
        for contacto in elegidos:
            ya = (
                db.query(models.ContactGroupMember)
                .filter(
                    models.ContactGroupMember.group_id == grupo.id,
                    models.ContactGroupMember.contact_id == contacto.id,
                )
                .first()
            )
            if ya is None:
                db.add(
                    models.ContactGroupMember(
                        group_id=grupo.id, contact_id=contacto.id
                    )
                )
        grupos[g["name"]] = (grupo, elegidos)
    db.commit()
    return grupos


def _seed_plantillas(db, meta_account_id: int) -> dict:
    out = {}
    ahora = datetime.utcnow()
    for t in PLANTILLAS:
        tpl = (
            db.query(models.WhatsappTemplate)
            .filter(
                models.WhatsappTemplate.meta_account_id == meta_account_id,
                models.WhatsappTemplate.name == t["name"],
                models.WhatsappTemplate.language == t["language"],
            )
            .first()
        )
        if tpl is None:
            tpl = models.WhatsappTemplate(
                meta_account_id=meta_account_id,
                meta_template_id=f"mock-tpl-{t['name']}",
                name=t["name"], category=t["category"], language=t["language"],
                status="APPROVED", components_json=t["components_json"],
                last_synced_at=ahora,
            )
            db.add(tpl)
            db.flush()
        else:
            tpl.status = "APPROVED"
            tpl.category = t["category"]
            tpl.components_json = t["components_json"]
            tpl.last_synced_at = ahora
        out[t["name"]] = tpl
    db.commit()
    return out


def _seed_campana(
    db, *, team_id, meta_account_id, template, created_by, name, status,
    scheduled_at, started_at, completed_at, plan, variables=None,
) -> str:
    """`plan` es una lista de (contacto, estado_final)."""
    ya = (
        db.query(models.Campaign)
        .filter(models.Campaign.team_id == team_id, models.Campaign.name == name)
        .first()
    )
    if ya is not None:
        return "skip"

    camp = models.Campaign(
        team_id=team_id, meta_account_id=meta_account_id, template_id=template.id,
        name=name, status=status, scheduled_at=scheduled_at,
        started_at=started_at, completed_at=completed_at,
        template_variables_json=variables or {}, created_by_user_id=created_by,
    )
    db.add(camp)
    db.flush()

    base = started_at or scheduled_at or camp.created_at
    db.add(
        models.CampaignEvent(
            campaign_id=camp.id, recipient_id=None, event_type="queued",
            payload_json={"queued": len(plan), "skipped_opt_out": 0},
            created_at=base,
        )
    )

    for idx, (contacto, estado) in enumerate(plan):
        wamid = _wamid(idx + camp.id * 1000) if estado != "queued" else None
        sent_at = base + timedelta(minutes=1 + idx // 4) if estado != "queued" else None
        delivered_at = (
            sent_at + timedelta(minutes=1) if estado in ("delivered", "read") else None
        )
        read_at = delivered_at + timedelta(minutes=3) if estado == "read" else None
        failed_at = sent_at + timedelta(minutes=1) if estado == "failed" else None

        rec = models.CampaignRecipient(
            campaign_id=camp.id, contact_id=contacto.id,
            phone_e164=contacto.phone_e164, meta_message_id=wamid, status=estado,
            error_code="131026" if estado == "failed" else None,
            sent_at=sent_at, delivered_at=delivered_at, read_at=read_at,
            failed_at=failed_at,
        )
        db.add(rec)
        db.flush()

        for tipo, cuando in (
            ("sent", sent_at), ("delivered", delivered_at),
            ("read", read_at), ("failed", failed_at),
        ):
            if cuando is None:
                continue
            db.add(
                models.CampaignEvent(
                    campaign_id=camp.id, recipient_id=rec.id, event_type=tipo,
                    meta_message_id=wamid, created_at=cuando,
                    payload_json={"wamid": wamid},
                )
            )
    db.commit()
    return "nuevo"


def main() -> int:
    db = SessionLocal()
    try:
        owner = crud.get_user_by_email(db, OWNER_EMAIL)
        if owner is None:
            print(f"ERROR: no existe {OWNER_EMAIL}. Corre seed_bot_natulce.py primero.")
            return 1
        membresia = crud.get_membership_for_user(db, owner)
        if membresia is None:
            print(f"ERROR: {OWNER_EMAIL} no tiene team.")
            return 1
        team_id = membresia.team_id
        print(f"Owner={OWNER_EMAIL} team_id={team_id}\n")

        print("Conversaciones:")
        for spec in CONVERSACIONES:
            accion = _seed_conversacion(db, team_id, spec)
            marca = f" [{spec['etiqueta']}]" if spec["etiqueta"] else ""
            print(
                f"  [{accion:<5}] {spec['name']:<20} "
                f"{len(spec['messages']):>2} msgs · {spec['status']}{marca}"
            )

        meta = _meta_account(db, team_id)
        contactos = _seed_contactos(db, team_id)
        grupos = _seed_grupos(db, team_id, contactos)
        plantillas = _seed_plantillas(db, meta.id)
        print(
            f"\nCampañas: {len(contactos)} contactos · {len(grupos)} grupos · "
            f"{len(plantillas)} plantillas"
        )

        ahora = datetime.utcnow()
        clientes = grupos["Clientes que ya compraron"][1]
        prospectos = grupos["Prospectos de Instagram"][1]

        # Campaña 1 — completada, buenos números.
        plan1 = [(c, e) for c, e in zip(
            clientes,
            ["read", "read", "read", "delivered", "read", "delivered",
             "read", "read", "failed"],
        )]
        a1 = _seed_campana(
            db, team_id=team_id, meta_account_id=meta.id,
            template=plantillas["promo_siropes_natulce"], created_by=owner.id,
            name="Promo 15% — clientes", status="completed",
            scheduled_at=None, started_at=ahora - timedelta(days=2),
            completed_at=ahora - timedelta(days=2) + timedelta(minutes=6),
            plan=plan1, variables={"1": "nombre", "2": "$25mil"},
        )
        print(f"  [{a1:<5}] Promo 15% — clientes ({len(plan1)} destinatarios)")

        # Campaña 2 — completada, sobre prospectos.
        plan2 = [(c, e) for c, e in zip(
            prospectos, ["delivered", "read", "delivered", "read", "sent", "delivered"],
        )]
        a2 = _seed_campana(
            db, team_id=team_id, meta_account_id=meta.id,
            template=plantillas["nuevo_sabor_jamaica"], created_by=owner.id,
            name="Lanzamiento Flor de Jamaica", status="completed",
            scheduled_at=None, started_at=ahora - timedelta(days=6),
            completed_at=ahora - timedelta(days=6) + timedelta(minutes=4),
            plan=plan2,
        )
        print(f"  [{a2:<5}] Lanzamiento Flor de Jamaica ({len(plan2)} destinatarios)")

        # Campaña 3 — agendada a futuro (queda visible como "programada").
        plan3 = [(c, "queued") for c in clientes[:6]]
        a3 = _seed_campana(
            db, team_id=team_id, meta_account_id=meta.id,
            template=plantillas["promo_siropes_natulce"], created_by=owner.id,
            name="Recompra mensual — diciembre", status="scheduled",
            scheduled_at=ahora + timedelta(days=3), started_at=None,
            completed_at=None, plan=plan3,
            variables={"1": "nombre", "2": "$25mil"},
        )
        print(f"  [{a3:<5}] Recompra mensual — diciembre ({len(plan3)} destinatarios)")

        print("\n=== Datos de demostración de Natulcé listos ===")
        print("  Abandonada y retomada: Camila Restrepo (+57 300 000 0012)")
        print("  Abandonada sin respuesta: Marcela Gil (+57 300 000 0016)")
        print("  Pedido cerrado: Daniela Ospina (+57 300 000 0011)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
