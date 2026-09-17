from datetime import datetime
from sqlalchemy import (
    BigInteger,
    Column,
    Integer,
    String,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    Text,
    UniqueConstraint,
    Index,
    CheckConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    tipo_documento = Column(String, nullable=False)
    documento = Column(String, unique=True, index=True, nullable=False)
    correo = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    # Cuenta habilitada. En `False` no puede entrar ni seguir usando un token
    # ya emitido (lo corta `dependencies.get_current_user`), que es lo que hace
    # falta para que "desactivar" signifique algo con tokens de 2 horas.
    # No se borra el usuario: se apaga. Sus mensajes y su historial siguen
    # colgando de él, y volver a prenderla es un UPDATE.
    activo = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Sprint 15: estado de tutoriales interactivos por módulo.
    # Llaves esperadas: mi_plan, mensajes, bots, campanas, agendamientos
    # Valor: {"done": bool, "skipped": bool, "completed_at": iso8601 | null}
    tutorials_completed = Column(JSONB, nullable=False, default=dict, server_default="{}")

    memberships = relationship(
        "TeamMember", back_populates="user", cascade="all, delete-orphan"
    )
    owned_teams = relationship(
        "Team", back_populates="owner", foreign_keys="Team.owner_user_id"
    )


# Sprint 22 #318: modo operativo de un tenant.
#   'demo'       → cuenta de demostración. Los envíos a WhatsApp se SIMULAN
#                  siempre, sin importar TWILIO_SANDBOX/META_SANDBOX. Así una
#                  cuenta de demo nunca gasta cuota de Meta ni le escribe a un
#                  número real por accidente.
#   'produccion' → cliente operando de verdad; los envíos salen reales.
# El default es 'demo' a propósito: un tenant nuevo no debe poder enviar hasta
# que alguien lo promueva explícitamente.
TEAM_MODO_DEMO = "demo"
TEAM_MODO_PRODUCCION = "produccion"
AVAILABLE_TEAM_MODOS = (TEAM_MODO_DEMO, TEAM_MODO_PRODUCCION)


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    modo = Column(
        String(16), nullable=False, default=TEAM_MODO_DEMO, server_default=TEAM_MODO_DEMO
    )
    # Créditos de mensajes disponibles para envíos masivos. Se recargan
    # comprando un paquete (ver `CreditPurchase`) y se descuentan al encolar
    # los destinatarios de una campaña.
    message_credits = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Turno del reparto round-robin de conversaciones entre los asesores del
    # team: índice del último asesor al que se le entregó un chat. Vive en el
    # team (no en memoria del proceso) porque con más de una task de ECS cada
    # una llevaría su propio turno y el reparto dejaría de alternar.
    handoff_turno = Column(Integer, nullable=False, default=0, server_default="0")
    # Nombres de los asesores entre los que rota el handoff, en orden de turno
    # (ej. ["Julián", "Camila"]). Es una lista de nombres y no de usuarios a
    # propósito: hoy el negocio tiene dos asesores atendiendo pero un solo
    # login compartido, y la etiqueta 👤 de la bandeja es texto libre. Cuando
    # cada asesor tenga su cuenta, esto se mapea a `team_members`.
    # Vacío = se reparte entre los miembros con rol `agent`; si tampoco hay,
    # cae al `asesor_1` de siempre.
    asesores_rotacion = Column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    owner = relationship("User", back_populates="owned_teams", foreign_keys=[owner_user_id])
    members = relationship(
        "TeamMember", back_populates="team", cascade="all, delete-orphan"
    )
    meta_account = relationship(
        "MetaAccount", back_populates="team", uselist=False, cascade="all, delete-orphan"
    )
    conversations = relationship(
        "Conversation", back_populates="team", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    __tablename__ = "team_members"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False, default="agent")  # owner | agent
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_user"),
    )

    team = relationship("Team", back_populates="members")
    user = relationship("User", back_populates="memberships")
    permissions = relationship(
        "TeamPermission", back_populates="member", cascade="all, delete-orphan"
    )


class TeamPermission(Base):
    """
    Sistema de permisos extensible: cada permiso es una fila con un permission_key
    y un boolean enabled. Para añadir un permiso nuevo basta con insertar filas
    con una nueva permission_key.
    """
    __tablename__ = "team_permissions"
    id = Column(Integer, primary_key=True, index=True)
    team_member_id = Column(
        Integer, ForeignKey("team_members.id", ondelete="CASCADE"), nullable=False
    )
    permission_key = Column(String, nullable=False)
    enabled = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("team_member_id", "permission_key", name="uq_member_permission"),
    )

    member = relationship("TeamMember", back_populates="permissions")


# Permisos disponibles en el sistema (extensible)
AVAILABLE_PERMISSIONS = [
    "can_reply_messages",   # Responder mensajes manualmente (sprint actual)
    "can_send_broadcasts",  # Enviar campañas masivas (futuro)
    "can_manage_bots",      # Editar bots de WhatsApp (futuro)
    "can_manage_team",      # Invitar/editar miembros del equipo (futuro)
    "can_view_analytics",   # Ver reportes (futuro)
    # Pagos y créditos de mensajes. Es de administrador: el asesor no ve
    # precios, ni saldo, ni el historial de compras. Va como permiso y no
    # solo como rol para que mañana un tenant pueda dárselo a alguien más
    # sin volverlo dueño de la cuenta.
    "can_manage_billing",
]

# Permisos que trae por defecto una cuenta de ASESOR (rol `agent`): puede
# atender, no puede tocar la plata ni la conexión de WhatsApp. Desconectar la
# cuenta de Meta ya es owner-only por `get_current_owner_membership`.
ASESOR_DEFAULT_PERMISSIONS = {
    "can_reply_messages": True,
    "can_send_broadcasts": False,
    "can_manage_bots": False,
    "can_manage_team": False,
    "can_view_analytics": True,
    "can_manage_billing": False,
}


class MetaAccount(Base):
    """Cuenta de Meta WhatsApp Cloud API asociada a un team."""
    __tablename__ = "meta_accounts"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    # Sprint 18: proveedor del canal de mensajería. 'meta' = WhatsApp Cloud API
    # directo (legacy); 'twilio' = Twilio como BSP autorizado. Los campos Meta de
    # abajo son nullable porque una fila 'twilio' no los usa (y viceversa).
    provider = Column(String(16), nullable=False, default="meta", server_default="meta")
    phone_number_id = Column(String, nullable=True)
    waba_id = Column(String, nullable=True)
    display_phone = Column(String, nullable=False)
    verified_name = Column(String, nullable=True)  # Nombre visible en WhatsApp Business
    # IMPORTANTE: este campo guarda el ciphertext Fernet del access token.
    # Para descifrarlo usa backend.app.services.crypto.decrypt_secret.
    # NUNCA lo incluyas en un schema Pydantic de salida.
    encrypted_access_token = Column(Text, nullable=True)
    api_version = Column(String, nullable=False, default="v22.0")
    # ─── Credenciales Twilio (Sprint 18) — sólo cuando provider='twilio' ─────
    twilio_account_sid = Column(String(64), nullable=True)
    # Ciphertext Fernet del Auth Token de la subcuenta Twilio. Secreto de tenant:
    # NUNCA en un schema de salida, nunca en logs (reglas de seguridad #1/#2/#3).
    encrypted_twilio_auth_token = Column(Text, nullable=True)
    twilio_messaging_service_sid = Column(String(64), nullable=True)
    twilio_from = Column(String(32), nullable=True)  # p.ej. 'whatsapp:+573001234567'
    is_active = Column(Boolean, nullable=False, default=True)
    status = Column(
        String(32), nullable=False, default="pending", index=True
    )  # pending | active | invalid | disconnected
    last_validated_at = Column(DateTime, nullable=True)
    validation_error = Column(String(512), nullable=True)
    registered_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("phone_number_id", name="uq_meta_accounts_phone_number_id"),
    )

    team = relationship("Team", back_populates="meta_account")

    def __repr__(self) -> str:
        return (
            f"<MetaAccount id={self.id} team_id={self.team_id} "
            f"provider={self.provider!r} phone_number_id={self.phone_number_id} "
            f"status={self.status!r} encrypted_access_token=<REDACTED> "
            f"encrypted_twilio_auth_token=<REDACTED>>"
        )

    __str__ = __repr__


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    contact_wa_id = Column(String, nullable=False)  # E.164 sin +
    contact_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="open")  # open | pending | closed
    # Quién atiende la conversación. Por defecto el bot; al hacer handoff se
    # reasigna a un asesor humano (ej. "asesor_1"). String simple para el MVP
    # (no FK a users) — basta para distinguir bot vs humano en la UI.
    assigned_to = Column(
        String, nullable=False, default="bot", server_default="bot"
    )
    # Marca libre sobre la conversación, puesta por el sistema (hoy sólo
    # "conversación abandonada", cuando el cliente deja de contestarle al bot).
    # NULL = sin etiqueta; no hay default a propósito, para que "sin marcar" y
    # "marcada" sean distinguibles sin inventar un valor centinela.
    etiqueta = Column(String, nullable=True)
    last_message_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("team_id", "contact_wa_id", name="uq_team_contact"),
        Index("ix_conversations_team_last_message", "team_id", "last_message_at"),
    )

    team = relationship("Team", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    direction = Column(String, nullable=False)  # inbound | outbound
    content = Column(Text, nullable=False)
    message_type = Column(String, nullable=False, default="text")  # text | template | image | ...
    meta_message_id = Column(String, nullable=True, index=True)
    sent_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    status = Column(String, nullable=False, default="sent")  # sent | delivered | read | failed | received
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        # Casi todo lo que se le pregunta a esta tabla es "los mensajes de esta
        # conversación, por fecha": la transcripción de un chat, el adelanto de
        # la bandeja, el conteo de la ventana de supervisión. `conversation_id`
        # no tenía índice y el de `created_at` suelto no sirve para eso, así que
        # cada una de esas consultas barría la tabla entera.
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    conversation = relationship("Conversation", back_populates="messages")
    sent_by_user = relationship("User")


# ===== Sprint 8: Bots =====
BOT_CHANNEL_WHATSAPP = "whatsapp"
BOT_CHANNEL_INSTAGRAM = "instagram"
BOT_CHANNEL_MESSENGER = "messenger"
AVAILABLE_BOT_CHANNELS = (
    BOT_CHANNEL_WHATSAPP,
    BOT_CHANNEL_INSTAGRAM,
    BOT_CHANNEL_MESSENGER,
)

BOT_STEP_TYPES = (
    "send_text",       # enviar mensaje de texto plano
    "send_template",   # enviar template aprobado (iniciar conversación)
    "send_media",      # enviar imagen/video/documento (uno o varios items)
    "wait_input",      # esperar respuesta del contacto
    "llm",             # bloque "interpretado por LLM" (demo: lógica predefinida)
    "delay",           # pausa en segundos
    "condition",       # ramificación por variable / keyword
    "handoff",         # pasar la conversación a un asesor humano
    "end",             # fin del flujo
)

BOT_TRIGGER_DEFAULT = "default"    # catch-all para mensajes nuevos (1 por user)
BOT_TRIGGER_KEYWORD = "keyword"    # se activa si el mensaje matchea keywords
BOT_TRIGGER_MANUAL = "manual"      # solo invocado por otro bot o manualmente
AVAILABLE_BOT_TRIGGERS = (
    BOT_TRIGGER_DEFAULT,
    BOT_TRIGGER_KEYWORD,
    BOT_TRIGGER_MANUAL,
)


class Bot(Base):
    __tablename__ = "bots"
    id = Column(Integer, primary_key=True, index=True)
    # Sprint 9: dueño = cuenta. team_id se mantiene por compat pero no se usa
    # como fuente de verdad para visibilidad.
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name = Column(String(120), nullable=False)
    description = Column(String(512), nullable=True)
    status = Column(String(32), nullable=False, default="active")  # active | paused | draft
    # CSV de canales vinculados. Ej: "whatsapp,instagram,messenger".
    channels = Column(String(255), nullable=False, default="whatsapp")
    # Sprint 19: motor del bot.
    #   'flow' → pasos/steps clásicos (bot_engine)
    #   'llm'  → conversacional con Claude vía Bedrock (llm_engine)
    engine = Column(String(16), nullable=False, default="flow", server_default="flow")
    # Sprint 19: JSON con la config del motor LLM. Ej:
    #   {"context_key": "talulah", "assignee": "asesor_1", "model_id": null,
    #    "media": {"guia_tallas_1": {"url": "...", "media_type": "image"}},
    #    "shopify": {"shop": "x.myshopify.com", "client_id": "...",
    #                "encrypted_client_secret": "<Fernet>"}}
    # El client_secret de Shopify es secreto de tenant → SIEMPRE cifrado (regla #3).
    llm_config = Column(Text, nullable=True)
    # Sprint 31: instrucciones de negocio del bot en prosa (nivel 2 del modelo
    # de `docs/bots_productos_modelo.puml`). Es lo que hoy vive escondido en un
    # `.md` del repo (`bot_contexts/`) y que el cliente tendría que poder
    # editar sin un despliegue. `llm_config` sigue siendo SOLO lo técnico
    # (modelo, medios, credenciales); esto es lo que el negocio dice de sí
    # mismo. Nivel 3 —lo específico de cada producto— vive en
    # `bot_productos.instrucciones`.
    instrucciones = Column(Text, nullable=True)
    # Sube en 1 cada vez que se guardan `instrucciones`. Sirve para invalidar
    # el prefijo cacheado del prompt sin comparar textos largos.
    instrucciones_version = Column(
        Integer, nullable=False, default=0, server_default="0"
    )
    # Sprint 9: trigger de activación
    trigger_type = Column(
        String(32), nullable=False, default=BOT_TRIGGER_MANUAL
    )
    trigger_config = Column(Text, nullable=True)  # JSON serializado
    triggered_count = Column(Integer, nullable=False, default=0)
    completed_steps_count = Column(Integer, nullable=False, default=0)
    finished_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_bots_user_updated", "user_id", "updated_at"),
    )

    user = relationship("User")
    team = relationship("Team")
    steps = relationship(
        "BotStep",
        back_populates="bot",
        cascade="all, delete-orphan",
        order_by="BotStep.position",
    )


class BotStep(Base):
    __tablename__ = "bot_steps"
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(
        Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = Column(Integer, nullable=False)
    step_type = Column(String(32), nullable=False)
    label = Column(String(255), nullable=False)
    # JSON serializado (string) con el payload específico del bloque.
    # Ej: {"text": "Hola"} | {"template_name": "x", "lang": "es_CO"} | {"seconds": 30}
    config = Column(Text, nullable=True)
    next_step_id = Column(
        Integer, ForeignKey("bot_steps.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("bot_id", "position", name="uq_bot_step_position"),
    )

    bot = relationship("Bot", back_populates="steps")


# ===== Sprint 10: ejecución real del bot contra Meta =====
BOT_SESSION_RUNNING = "running"
BOT_SESSION_WAITING = "waiting"
BOT_SESSION_FINISHED = "finished"
BOT_SESSION_CANCELLED = "cancelled"

BOT_PENDING_STATUS_PENDING = "pending"
BOT_PENDING_STATUS_DONE = "done"
BOT_PENDING_STATUS_FAILED = "failed"

# Tipos de acción programada (`bot_pending_actions.action_type`).
# RESUME es el histórico: retomar una sesión detenida en un paso `delay`.
# SEGUIMIENTO y ABANDONO son del bot LLM: reenganchar tras 15 min de silencio y,
# si tampoco contesta a eso, cerrar y etiquetar la conversación.
# OJO: SEGUIMIENTO y ABANDONO **no** pueden procesarse vía `run_turn(user_input=None)`
# — para un bot LLM ese camino genera un saludo, y saludaríamos a alguien que se fue.
BOT_PENDING_ACTION_RESUME = "resume_session"  # valor ya existente en base: no cambiar
BOT_PENDING_ACTION_SEGUIMIENTO = "seguimiento"
BOT_PENDING_ACTION_ABANDONO = "abandono"


class BotSession(Base):
    """Conversación activa entre un bot y un contacto.

    Máximo una BotSession en estado `running`/`waiting` por conversación
    (se garantiza en código, no en DB, para permitir historial).
    """

    __tablename__ = "bot_sessions"
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(
        Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # JSON con {"current_step_id": int, "variables": {...}} — mismo formato
    # que consume bot_engine.advance().
    state = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default=BOT_SESSION_RUNNING)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_bot_sessions_conv_status", "conversation_id", "status"),
    )

    bot = relationship("Bot")
    conversation = relationship("Conversation")


class BotLlmDecision(Base):
    """Sprint 19 #255: bitácora de decisiones del motor LLM (observabilidad).

    Una fila por turno de conversación: qué camino tomó el bot, qué
    herramientas llamó y con qué resultado, cuánto tardó y cómo terminó.
    El texto del usuario se guarda AQUÍ (la BD ya es el sistema de registro
    de mensajes); a los logs de CloudWatch solo van metadatos sin contenido
    (regla de seguridad #1/#6).
    """

    __tablename__ = "bot_llm_decisions"
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(
        Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id = Column(
        Integer, ForeignKey("bot_sessions.id", ondelete="SET NULL"), nullable=True
    )
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source = Column(String(16), nullable=False, default="whatsapp")  # whatsapp | simulador
    # Sprint 31. OJO con el parecido de los nombres, que se prestan a confusión:
    #   `source`       → por dónde ENTRÓ el turno: whatsapp | simulador.
    #   `fuente_datos` → de dónde salieron los DATOS que el bot usó para
    #                    responder: 'db' (tablas `bot_producto_*`),
    #                    'prompt' (venían escritos en el contexto) o
    #                    'json' (los archivos de `app/data/`).
    # Nullable y SIN default a propósito: así "turno viejo, anterior a esta
    # columna" (NULL) no se confunde con "turno nuevo que no consultó ninguna
    # fuente". Mismo criterio que `conversations.etiqueta`.
    fuente_datos = Column(String(16), nullable=True)
    user_input = Column(Text, nullable=True)          # None en el turno de saludo
    # Camino tomado: derivado de tools/media o clasificador por keywords
    # (llm_config.caminos). Ej: 'tallas', 'estado_pedido', 'escalar_a_asesor'.
    camino = Column(String(64), nullable=False, default="respuesta_libre")
    tools_called = Column(Text, nullable=True)        # JSON [{tool,input,resultado}]
    reply_preview = Column(String(300), nullable=True)
    model_id = Column(String(128), nullable=True)
    rounds = Column(Integer, nullable=False, default=1)   # llamadas al modelo en el turno
    latency_ms = Column(Integer, nullable=True)
    finished = Column(Boolean, nullable=False, default=False)
    escalated_to = Column(String(64), nullable=True)  # handle del asesor si hubo handoff
    failsafe = Column(Boolean, nullable=False, default=False)
    # Sprint "Ayuda a Cali": agrupa los turnos de una misma conversación en los
    # canales sin `conversation_id` (el chat web es anónimo). Hoy es un uuid de
    # la sesión; cuando el bot se conecte a WhatsApp será el número, que es
    # justamente como el equipo identifica a la persona.
    chat_ref = Column(String(64), nullable=True, index=True)
    # Nombre o teléfono que la persona dio durante la conversación, si lo dio.
    chat_contacto = Column(String(120), nullable=True)
    # Consumo del turno, sumando todas las rondas al modelo. Sin esto el costo
    # solo se puede estimar corriendo un benchmark aparte; con esto el panel
    # puede decir lo que costó de verdad cada conversación. `cache_read` es
    # además el termómetro del prompt caching: si se va a cero de forma
    # sostenida, el prefijo dejó de ser estable y el ahorro se perdió.
    tokens_in = Column(Integer, nullable=True)
    tokens_out = Column(Integer, nullable=True)
    cache_read = Column(Integer, nullable=True)
    cache_write = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_llm_decisions_bot_created", "bot_id", "created_at"),
        Index("ix_llm_decisions_chat_ref", "chat_ref", "created_at"),
    )

    bot = relationship("Bot")


class BotPendingAction(Base):
    """Acción del bot diferida para pasos `delay` de minutos/horas.

    Al encontrar un `delay`, en vez de bloquear el request guardamos aquí
    {scheduled_at, session_id} y seguimos. El scheduler tick retoma la
    sesión cuando llegue el tiempo.
    """

    __tablename__ = "bot_pending_actions"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("bot_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_at = Column(DateTime, nullable=False, index=True)
    action_type = Column(String(32), nullable=False, default=BOT_PENDING_ACTION_RESUME)
    payload = Column(Text, nullable=True)
    status = Column(
        String(16), nullable=False, default=BOT_PENDING_STATUS_PENDING
    )
    attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_pending_actions_due", "status", "scheduled_at"),
    )

    session = relationship("BotSession")


# ===== Sprint 11: Landing Gloma - leads del form de contacto =====
class Lead(Base):
    """Solicitudes de contacto que llenan el form de la landing /gloma.

    No tiene FK a users porque son prospects, no clientes aún.
    `source` permite distinguir orígenes cuando haya más de una landing.

    Sprint 21 #297: el form pide `nombre` y el CEO gestiona las solicitudes
    desde `/citas` → subsección "Solicitudes de contacto", así que la fila
    dejó de ser solo un registro y ahora tiene ciclo de vida: `estado`
    (`pendiente` | `contactado`), `notas` y `updated_at`. El booleano
    `contacted` original quedó reemplazado por `estado` (migración #297).

    Contiene PII de prospectos: nunca se loggea su contenido ni se expone en
    endpoints públicos (regla de seguridad #1).
    """

    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(120), nullable=True)
    email = Column(String(255), nullable=False, index=True)
    telefono = Column(String(32), nullable=False)
    source = Column(String(64), nullable=False, default="gloma_landing", index=True)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(64), nullable=True)
    estado = Column(String(16), nullable=False, default="pendiente", index=True)
    notas = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=True
    )

    def __repr__(self) -> str:  # PII fuera de los logs (regla de seguridad #1)
        return f"<Lead id={self.id} source={self.source} estado={self.estado}>"


class DemoBooking(Base):
    """Sprint 21 #275: demos que el bot de Gloma agenda con un prospecto.

    La escribe la herramienta `registrar_demo` del motor LLM, desde cualquiera
    de los 3 canales del bot (`source`: landing | simulador | whatsapp). Es la
    tabla que el CEO monitorea; por eso `estado` empieza en 'solicitada' y se
    mueve a mano (o desde la app más adelante).

    Contiene datos de contacto de un prospecto (PII): nunca se loggea su
    contenido ni se expone en endpoints públicos.
    """

    __tablename__ = "demo_bookings"
    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(
        Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source = Column(String(16), nullable=False, default="landing", index=True)
    nombre = Column(String(120), nullable=True)
    empresa = Column(String(160), nullable=True)
    correo = Column(String(255), nullable=False, index=True)
    telefono = Column(String(32), nullable=True)
    # Sprint 21 #293: la fecha real de la cita (el motor la calcula con la
    # política de agenda: +3 días hábiles, L-V, 10:00-16:00). `dia` y `hora`
    # quedan como etiquetas legibles de esa misma fecha.
    fecha = Column(Date, nullable=True, index=True)
    dia = Column(String(16), nullable=True)        # lunes..viernes
    hora = Column(String(16), nullable=True)       # 10:00 a.m. .. 4:00 p.m.
    notas = Column(String(500), nullable=True)     # lo que el prospecto contó
    estado = Column(String(24), nullable=False, default="solicitada", index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    def __repr__(self) -> str:  # PII fuera de los logs (regla de seguridad #1)
        return f"<DemoBooking id={self.id} source={self.source} estado={self.estado}>"


# ===== Sprint 13: Contactos + Grupos =====
# Estos modelos replican 1:1 el DDL definido en
# backend/docs/sprint13_schema.md (§1.1, §1.2, §1.3). La migración #158 ya
# aplicó el schema en local (docker-compose `db`); aquí solo mapeamos las
# tablas a SQLAlchemy. No usar Base.metadata.create_all() para alterar:
# las tablas se crean vía el script de migración, no aquí.


def _mask_phone(phone: str) -> str:
    """Enmascara teléfono E.164 dejando solo los últimos 4 dígitos.
    Regla 1 (CLAUDE.md): los modelos con PII deben tener __repr__ redactado."""
    if not phone:
        return "<empty>"
    if len(phone) <= 5:
        return "***"
    return phone[:3] + "***" + phone[-4:]


def _mask_name(name) -> str:
    if not name:
        return "<empty>"
    return name[0] + "***"


class Contact(Base):
    """Contacto perteneciente a un team (multi-tenant).

    PII: `phone_e164`, `name`, `email`, `attributes` son datos del cliente.
    `__repr__` redacta los campos sensibles (regla 1 de seguridad).
    """

    __tablename__ = "contacts"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phone_e164 = Column(String(20), nullable=False)
    name = Column(String(120), nullable=True)
    email = Column(String(255), nullable=True)
    attributes = Column(JSONB, nullable=False, default=dict, server_default="{}")
    opt_in = Column(Boolean, nullable=False, default=True, server_default="true")
    opt_in_source = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("team_id", "phone_e164", name="uq_contacts_team_phone"),
        CheckConstraint(
            r"phone_e164 ~ '^\+[1-9][0-9]{6,18}$'",
            name="ck_contacts_phone_e164",
        ),
        # `team_id` ya declara `index=True`, que crea ese mismo índice con este
        # mismo nombre: repetirlo aquí hacía que `create_all()` emitiera dos
        # veces el CREATE INDEX y fallara contra una base vacía.
        Index("ix_contacts_team_name", "team_id", "name"),
    )

    team = relationship("Team")
    group_memberships = relationship(
        "ContactGroupMember",
        back_populates="contact",
        cascade="all, delete-orphan",
    )

    @property
    def groups(self):
        return [m.group for m in self.group_memberships]

    def __repr__(self) -> str:
        return (
            f"<Contact id={self.id} team_id={self.team_id} "
            f"phone={_mask_phone(self.phone_e164)!r} "
            f"name={_mask_name(self.name)!r} "
            f"email=<REDACTED>>"
        )

    __str__ = __repr__


class ContactGroup(Base):
    __tablename__ = "contact_groups"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("team_id", "name", name="uq_contact_groups_team_name"),
        # Igual que en `contacts`: `team_id` ya lo indexa con `index=True`.
    )

    team = relationship("Team")
    members = relationship(
        "ContactGroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )

    @property
    def contacts(self):
        return [m.contact for m in self.members]


class ContactGroupMember(Base):
    __tablename__ = "contact_group_members"
    group_id = Column(
        Integer,
        ForeignKey("contact_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    contact_id = Column(
        Integer,
        ForeignKey("contacts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_contact_group_members_contact", "contact_id"),
    )

    group = relationship("ContactGroup", back_populates="members")
    contact = relationship("Contact", back_populates="group_memberships")


# ─── Sprint 13 / templates ────────────────────────────────────────────────
# Mapea la tabla `whatsapp_templates` ya creada por la migración #158
# (ver `backend/docs/sprint13_schema.md` §1.4). NO se crea aquí vía
# Base.metadata.create_all() — la migración Python es la fuente de verdad.

WHATSAPP_TEMPLATE_STATUSES = (
    "PENDING",
    "APPROVED",
    "REJECTED",
    "DISABLED",
    "PAUSED",
    "DELETED",
)
WHATSAPP_TEMPLATE_CATEGORIES = ("MARKETING", "UTILITY", "AUTHENTICATION")


class WhatsappTemplate(Base):
    """Cache local de las plantillas WhatsApp de Meta para una `MetaAccount`.

    La fuente de verdad es Meta. Se sincroniza:
      - On-demand (`POST /templates/sync`).
      - Lazy (TTL 15 min al entrar a /campanas/plantillas).
      - Por scheduler para PENDING (#162 sub-tick, fuera de scope #160).

    Borrados upstream → status='DELETED' (no DELETE físico, preserva FK
    desde `campaigns.template_id`).
    """

    __tablename__ = "whatsapp_templates"

    id = Column(Integer, primary_key=True, index=True)
    meta_account_id = Column(
        Integer,
        ForeignKey("meta_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meta_template_id = Column(String(64), nullable=True, index=True)
    name = Column(String(120), nullable=False)
    category = Column(String(40), nullable=True)
    language = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", server_default="PENDING")
    components_json = Column(JSONB, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "meta_account_id", "name", "language",
            name="uq_templates_account_name_lang",
        ),
        CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED','DISABLED','PAUSED','DELETED')",
            name="ck_templates_status",
        ),
        CheckConstraint(
            "category IS NULL OR category IN ('MARKETING','UTILITY','AUTHENTICATION')",
            name="ck_templates_category",
        ),
        Index("ix_templates_account_status", "meta_account_id", "status"),
    )

    meta_account = relationship("MetaAccount")

    def __repr__(self) -> str:
        # Regla 1 (CLAUDE.md): nunca loggear contenido crudo de la plantilla
        # (puede contener PII de ejemplo, S13-014). `components_json` se omite.
        return (
            f"<WhatsappTemplate id={self.id} meta_account_id={self.meta_account_id} "
            f"name={self.name!r} language={self.language!r} status={self.status!r} "
            f"components_json=<REDACTED> rejection_reason=<REDACTED>>"
        )

    __str__ = __repr__


# ─── Sprint 13 / campaigns ────────────────────────────────────────────────
# Mapea las tablas `campaigns`, `campaign_recipients`, `campaign_events`
# creadas por la migración #158 (ver `backend/docs/sprint13_schema.md` §1.5,
# §1.6, §1.7). NO usar Base.metadata.create_all() para alterar: la fuente de
# verdad es el script de migración.

CAMPAIGN_STATUSES = (
    "draft",
    "scheduled",
    "running",
    "completed",
    "failed",
    "cancelled",
)
CAMPAIGN_STATUS_DRAFT = "draft"
CAMPAIGN_STATUS_SCHEDULED = "scheduled"
CAMPAIGN_STATUS_RUNNING = "running"
CAMPAIGN_STATUS_COMPLETED = "completed"
CAMPAIGN_STATUS_FAILED = "failed"
CAMPAIGN_STATUS_CANCELLED = "cancelled"

CAMPAIGN_RECIPIENT_STATUSES = (
    "queued",
    "sending",
    "sent",
    "delivered",
    "read",
    "failed",
    "skipped",
)
CR_STATUS_QUEUED = "queued"
CR_STATUS_SENDING = "sending"
CR_STATUS_SENT = "sent"
CR_STATUS_DELIVERED = "delivered"
CR_STATUS_READ = "read"
CR_STATUS_FAILED = "failed"
CR_STATUS_SKIPPED = "skipped"

CAMPAIGN_EVENT_TYPES = (
    "queued",
    "sent",
    "delivered",
    "read",
    "failed",
    "clicked",
    "sync_warning",
)


class Campaign(Base):
    """Campaña de envío masivo perteneciente a un team.

    Multi-tenant via `team_id` directo. Apunta a una `WhatsappTemplate`
    aprobada y a una `MetaAccount` del mismo team. La validación cruzada
    `template.meta_account_id == campaign.meta_account_id == user_team` es
    responsabilidad del CRUD/router (S13-001).
    """

    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    meta_account_id = Column(
        Integer,
        ForeignKey("meta_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    template_id = Column(
        Integer,
        ForeignKey("whatsapp_templates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    name = Column(String(120), nullable=False)
    status = Column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    scheduled_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    template_variables_json = Column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft','scheduled','running','completed','failed','cancelled')",
            name="ck_campaigns_status",
        ),
        Index("ix_campaigns_team_status", "team_id", "status"),
        Index("ix_campaigns_team_created", "team_id", "created_at"),
    )

    team = relationship("Team")
    meta_account = relationship("MetaAccount")
    template = relationship("WhatsappTemplate")
    created_by = relationship("User")
    recipients = relationship(
        "CampaignRecipient",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )
    events = relationship(
        "CampaignEvent",
        back_populates="campaign",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        # No PII en Campaign directamente, pero `template_variables_json`
        # podría tener nombres de cliente; lo omitimos por defensa.
        return (
            f"<Campaign id={self.id} team_id={self.team_id} "
            f"template_id={self.template_id} status={self.status!r} "
            f"template_variables_json=<REDACTED>>"
        )

    __str__ = __repr__


class CampaignRecipient(Base):
    """Snapshot de un destinatario de campaña.

    `phone_e164` es snapshot al momento de encolar, así si el contacto se
    edita después el histórico no cambia. Para opt-in fail-closed (S13-003)
    el sender re-lee `contacts.opt_in` antes del POST a Meta.
    """

    __tablename__ = "campaign_recipients"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    contact_id = Column(
        Integer,
        ForeignKey("contacts.id", ondelete="RESTRICT"),
        nullable=False,
    )
    phone_e164 = Column(String(20), nullable=False)
    meta_message_id = Column(String(80), nullable=True)
    # Sprint 18: id de mensaje agnóstico de proveedor (wamid de Meta o MessageSid
    # de Twilio). Se correlacionan los callbacks de estado por esta columna.
    provider_message_id = Column(String(128), nullable=True, index=True)
    status = Column(
        String(20), nullable=False, default="queued", server_default="queued"
    )
    error_code = Column(String(40), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "contact_id", name="uq_recipients_campaign_contact"
        ),
        UniqueConstraint("meta_message_id", name="uq_recipients_meta_message_id"),
        CheckConstraint(
            "status IN ('queued','sending','sent','delivered','read','failed','skipped')",
            name="ck_recipients_status",
        ),
        Index("ix_recipients_campaign_status", "campaign_id", "status"),
    )

    campaign = relationship("Campaign", back_populates="recipients")
    contact = relationship("Contact")

    def __repr__(self) -> str:
        # Regla 1 (CLAUDE.md): enmascarar PII (`phone_e164`).
        return (
            f"<CampaignRecipient id={self.id} campaign_id={self.campaign_id} "
            f"contact_id={self.contact_id} phone={_mask_phone(self.phone_e164)!r} "
            f"status={self.status!r} error_code={self.error_code!r}>"
        )

    __str__ = __repr__


class CampaignEvent(Base):
    """Evento atómico de una campaña (queued/sent/delivered/read/failed/...).

    `payload_json` puede contener PII (números, mensajes de respuesta);
    `__repr__` lo redacta (regla 1) y los schemas `...Out` por defecto NO
    lo exponen (S13-011).
    """

    __tablename__ = "campaign_events"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(
        Integer,
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
    )
    recipient_id = Column(
        Integer,
        ForeignKey("campaign_recipients.id", ondelete="CASCADE"),
        nullable=True,
    )
    event_type = Column(String(30), nullable=False)
    payload_json = Column(JSONB, nullable=True)
    meta_message_id = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "event_type IN ('queued','sent','delivered','read','failed','clicked','sync_warning')",
            name="ck_events_type",
        ),
        Index("ix_events_campaign_type", "campaign_id", "event_type"),
        Index("ix_events_meta_message_id", "meta_message_id"),
        Index("ix_events_campaign_created", "campaign_id", "created_at"),
    )

    campaign = relationship("Campaign", back_populates="events")
    recipient = relationship("CampaignRecipient")

    def __repr__(self) -> str:
        return (
            f"<CampaignEvent id={self.id} campaign_id={self.campaign_id} "
            f"recipient_id={self.recipient_id} event_type={self.event_type!r} "
            f"payload_json=<REDACTED>>"
        )

    __str__ = __repr__


# ─── Créditos de mensajes y pagos (Wompi) ─────────────────────────────────
# Un envío masivo consume créditos; los créditos se compran por paquetes.
# El catálogo vive en `app/services/creditos.py` (no en la BD) porque hoy son
# dos paquetes fijos y el precio se recalcula con el costo de Twilio: tenerlo
# en código lo hace revisable en el diff en vez de editable a mano en prod.

CREDIT_PURCHASE_PENDING = "pending"    # referencia creada, sin pagar aún
CREDIT_PURCHASE_APPROVED = "approved"  # Wompi confirmó el pago → créditos sumados
CREDIT_PURCHASE_DECLINED = "declined"  # rechazada por el banco / el usuario
CREDIT_PURCHASE_ERROR = "error"        # error del proveedor
CREDIT_PURCHASE_VOIDED = "voided"      # anulada
AVAILABLE_CREDIT_PURCHASE_STATUSES = (
    CREDIT_PURCHASE_PENDING,
    CREDIT_PURCHASE_APPROVED,
    CREDIT_PURCHASE_DECLINED,
    CREDIT_PURCHASE_ERROR,
    CREDIT_PURCHASE_VOIDED,
)


class CreditPurchase(Base):
    """Compra de un paquete de mensajes por la pasarela de pagos.

    `reference` es nuestra idea del pago y viaja a Wompi; `provider_tx_id` es
    la de ellos. Los créditos se suman UNA sola vez, cuando el webhook confirma
    `APPROVED`: por eso `status` y el `UNIQUE` sobre `reference` son la defensa
    contra sumar dos veces si el webhook llega repetido (Wompi reintenta).
    """

    __tablename__ = "credit_purchases"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    package_key = Column(String(40), nullable=False)   # ej. "mensajes_1000"
    messages = Column(Integer, nullable=False)         # créditos que otorga
    amount_cents = Column(Integer, nullable=False)     # en centavos de COP
    currency = Column(String(8), nullable=False, default="COP", server_default="COP")
    reference = Column(String(80), nullable=False)     # la nuestra, va a Wompi
    provider = Column(String(20), nullable=False, default="wompi", server_default="wompi")
    provider_tx_id = Column(String(80), nullable=True, index=True)
    status = Column(
        String(20), nullable=False,
        default=CREDIT_PURCHASE_PENDING, server_default=CREDIT_PURCHASE_PENDING,
    )
    credited_at = Column(DateTime, nullable=True)      # cuándo se sumaron
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("reference", name="uq_credit_purchases_reference"),
        CheckConstraint(
            "status IN ('pending','approved','declined','error','voided')",
            name="ck_credit_purchases_status",
        ),
        CheckConstraint("messages > 0", name="ck_credit_purchases_messages"),
        CheckConstraint("amount_cents > 0", name="ck_credit_purchases_amount"),
        Index("ix_credit_purchases_team_created", "team_id", "created_at"),
    )

    team = relationship("Team")
    created_by = relationship("User")

    def __repr__(self) -> str:
        return (
            f"<CreditPurchase id={self.id} team_id={self.team_id} "
            f"package={self.package_key!r} messages={self.messages} "
            f"status={self.status!r} reference={self.reference!r}>"
        )

    __str__ = __repr__


# ─── Suscripción mensual a la plataforma ──────────────────────────────────
# Distinta de los paquetes de mensajes: la suscripción es la cuota por usar la
# plataforma y se cobra sola cada mes contra una tarjeta guardada en Wompi. El
# plan y las reglas de fechas viven en `app/services/suscripciones.py`.

SUBSCRIPTION_PENDING = "pending"    # nunca se activó: falta el primer pago
SUBSCRIPTION_ACTIVE = "active"      # cobrando cada mes
SUBSCRIPTION_PAST_DUE = "past_due"  # se agotaron los intentos de un ciclo
SUBSCRIPTION_CANCELED = "canceled"  # la apagó el cliente
AVAILABLE_SUBSCRIPTION_STATUSES = (
    SUBSCRIPTION_PENDING,
    SUBSCRIPTION_ACTIVE,
    SUBSCRIPTION_PAST_DUE,
    SUBSCRIPTION_CANCELED,
)

#: Estados de un cobro. Mismos nombres que los de `CreditPurchase` a propósito:
#: los dos traducen los estados de Wompi y no hay razón para que difieran.
SUBSCRIPTION_CHARGE_PENDING = "pending"
SUBSCRIPTION_CHARGE_APPROVED = "approved"
SUBSCRIPTION_CHARGE_DECLINED = "declined"
SUBSCRIPTION_CHARGE_ERROR = "error"
SUBSCRIPTION_CHARGE_VOIDED = "voided"
AVAILABLE_SUBSCRIPTION_CHARGE_STATUSES = (
    SUBSCRIPTION_CHARGE_PENDING,
    SUBSCRIPTION_CHARGE_APPROVED,
    SUBSCRIPTION_CHARGE_DECLINED,
    SUBSCRIPTION_CHARGE_ERROR,
    SUBSCRIPTION_CHARGE_VOIDED,
)


class Subscription(Base):
    """La suscripción de una cuenta: una fila por team, para siempre.

    `team_id` es UNIQUE **a propósito**. Cancelar no borra la fila ni crea una
    nueva al reactivar: se reusa la misma y cambia `status`. Así el estado de
    una cuenta se lee sin ordenar por fecha ni desempatar entre filas viejas,
    que es de donde salen los errores de "se cobró dos veces". El historial no
    se pierde porque vive completo en `subscription_charges`.

    `payment_source_id` es el identificador de la tarjeta guardada en Wompi.
    **No es un número de tarjeta** y por sí solo no cobra nada: sin nuestra
    llave privada no sirve para nada. Aun así no se expone en ningún schema de
    respuesta ni se loggea — lo único que sale a la pantalla es
    `card_brand` + `card_last_four`, que es lo que le permite al dueño
    reconocer cuál de sus tarjetas quedó registrada.
    """

    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_key = Column(String(40), nullable=False)
    status = Column(
        String(20), nullable=False,
        default=SUBSCRIPTION_PENDING, server_default=SUBSCRIPTION_PENDING,
    )
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, default="COP", server_default="COP")
    provider = Column(String(20), nullable=False, default="wompi", server_default="wompi")

    # --- la tarjeta guardada -------------------------------------------------
    payment_source_id = Column(Integer, nullable=True)
    card_brand = Column(String(20), nullable=True)     # VISA, MASTERCARD…
    card_last_four = Column(String(4), nullable=True)  # para "····4242"
    #: Correo con el que se creó la fuente de pago. Wompi lo exige en CADA
    #: cobro, y tiene que ser el mismo con el que se registró la tarjeta.
    customer_email = Column(String(255), nullable=True)

    # --- el ciclo ------------------------------------------------------------
    #: Día del mes (1–31) en hora de Colombia en que se activó. Se guarda
    #: aparte de `next_charge_at` para que un 31 no se degrade a 28 para
    #: siempre después de pasar por febrero.
    billing_day = Column(Integer, nullable=True)
    next_charge_at = Column(DateTime, nullable=True, index=True)
    last_charge_at = Column(DateTime, nullable=True)
    activated_at = Column(DateTime, nullable=True)
    canceled_at = Column(DateTime, nullable=True)
    #: Intentos gastados en el ciclo EN CURSO. Vuelve a 0 cuando un cobro entra.
    attempts = Column(Integer, nullable=False, default=0, server_default="0")

    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    canceled_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("team_id", name="uq_subscriptions_team"),
        CheckConstraint(
            "status IN ('pending','active','past_due','canceled')",
            name="ck_subscriptions_status",
        ),
        CheckConstraint("amount_cents > 0", name="ck_subscriptions_amount"),
        CheckConstraint(
            "billing_day IS NULL OR (billing_day >= 1 AND billing_day <= 31)",
            name="ck_subscriptions_billing_day",
        ),
    )

    team = relationship("Team")
    charges = relationship(
        "SubscriptionCharge", back_populates="subscription", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        # `payment_source_id` y `customer_email` NO salen acá: el primero es la
        # llave de cobro de un cliente y el segundo es PII.
        return (
            f"<Subscription id={self.id} team_id={self.team_id} "
            f"plan={self.plan_key!r} status={self.status!r} "
            f"payment_source_id=<REDACTED>>"
        )

    __str__ = __repr__


class SubscriptionCharge(Base):
    """Un intento de cobro mensual. Una fila por intento, no por mes.

    Los reintentos de un mismo ciclo comparten `scheduled_for` y se distinguen
    por `attempt`: así queda registrado que se intentó tres veces y por qué
    falló cada una, en vez de sobrescribir la fila y perder el rastro.

    `reference` es UNIQUE por lo mismo que en `credit_purchases`: es el candado
    que impide que un webhook repetido de Wompi se procese dos veces.
    """

    __tablename__ = "subscription_charges"

    id = Column(Integer, primary_key=True, index=True)
    subscription_id = Column(
        Integer, ForeignKey("subscriptions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference = Column(String(80), nullable=False)
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String(8), nullable=False, default="COP", server_default="COP")
    status = Column(
        String(20), nullable=False,
        default=SUBSCRIPTION_CHARGE_PENDING, server_default=SUBSCRIPTION_CHARGE_PENDING,
    )
    provider_tx_id = Column(String(80), nullable=True, index=True)
    #: El momento del ciclo que este cobro paga. Los reintentos lo repiten.
    scheduled_for = Column(DateTime, nullable=False)
    attempt = Column(Integer, nullable=False, default=1, server_default="1")
    #: Código del fallo, NO el mensaje de Wompi: `DECLINED`, `SIN_RESPUESTA`,
    #: `INPUT_VALIDATION_ERROR`… El texto completo va solo al log del servidor
    #: (regla 6); acá cabe un código porque no dice nada del pagador.
    failure_code = Column(String(40), nullable=True)
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("reference", name="uq_subscription_charges_reference"),
        CheckConstraint(
            "status IN ('pending','approved','declined','error','voided')",
            name="ck_subscription_charges_status",
        ),
        CheckConstraint("amount_cents > 0", name="ck_subscription_charges_amount"),
        Index("ix_subscription_charges_team_created", "team_id", "created_at"),
    )

    subscription = relationship("Subscription", back_populates="charges")
    team = relationship("Team")

    def __repr__(self) -> str:
        return (
            f"<SubscriptionCharge id={self.id} sub={self.subscription_id} "
            f"status={self.status!r} attempt={self.attempt} "
            f"reference={self.reference!r}>"
        )

    __str__ = __repr__


# ===== Sprint "Ayuda a Cali": mascotas perdidas =====
# Dos naturalezas de registro en la MISMA tabla, distinguidas por
# `tipo_registro`, porque el cruce que hace el bot es justamente entre ambas:
#   'perdida'    → alguien BUSCA a su mascota (la perdió).
#   'encontrada' → alguien HALLÓ una mascota y la reporta para devolverla.
# Casi todos los campos descriptivos son NULL-ables a propósito: quien reporta
# rara vez conoce raza, edad y nombre a la vez. Los dos únicos obligatorios son
# `ubicacion` (dónde se perdió / dónde está) y `contacto_telefono` (sin eso el
# reporte no sirve para reunir a nadie).
MASCOTA_TIPO_PERDIDA = "perdida"
MASCOTA_TIPO_ENCONTRADA = "encontrada"
AVAILABLE_MASCOTA_TIPOS = (MASCOTA_TIPO_PERDIDA, MASCOTA_TIPO_ENCONTRADA)

MASCOTA_ESTADO_ACTIVO = "activo"
# Alguien dijo en el chat "esa es mi mascota" y el bot le entregó el contacto.
# Es una afirmación sin verificar: el equipo llama y recién ahí se confirma.
MASCOTA_ESTADO_RECONOCIDA = "reconocida"
MASCOTA_ESTADO_REUNIDA = "reunida"     # reencuentro confirmado por el equipo
MASCOTA_ESTADO_CERRADO = "cerrado"     # reporte descartado / duplicado
AVAILABLE_MASCOTA_ESTADOS = (
    MASCOTA_ESTADO_ACTIVO, MASCOTA_ESTADO_RECONOCIDA,
    MASCOTA_ESTADO_REUNIDA, MASCOTA_ESTADO_CERRADO,
)


class Mascota(Base):
    """Un reporte de mascota perdida o encontrada.

    Contiene PII de quien reporta (nombre y teléfono de contacto): `__repr__`
    la redacta (regla 1) y el listado público del bot nunca entrega el teléfono
    hasta que la persona confirma que la mascota es suya.
    """

    __tablename__ = "mascotas"

    id = Column(Integer, primary_key=True, index=True)
    # Identificador legible que ve el ciudadano y que nombra la carpeta de
    # fotos en el storage (`mascotas/<codigo>/`). Se deriva del id al crear.
    codigo = Column(String(16), unique=True, nullable=False, index=True)
    tipo_registro = Column(String(16), nullable=False, index=True)

    especie = Column(String(24), nullable=False, index=True)  # perro|gato|otra
    especie_otra = Column(String(60), nullable=True)          # si especie='otra'
    raza = Column(String(80), nullable=True)
    color = Column(String(80), nullable=True)
    nombre = Column(String(80), nullable=True)   # nombre al que responde
    sexo = Column(String(16), nullable=True)     # macho|hembra|desconocido
    edad = Column(String(40), nullable=True)     # texto libre: "2 años", "cachorro"
    tamano = Column(String(24), nullable=True)   # pequeño|mediano|grande
    senas = Column(Text, nullable=True)          # señas particulares

    # Obligatorio: dónde se perdió (tipo 'perdida') o dónde está / se encontró
    # (tipo 'encontrada'). El link de Maps es opcional a propósito: mucha gente
    # sabe dar la dirección pero no compartir una ubicación.
    ubicacion = Column(String(255), nullable=False)
    maps_url = Column(String(500), nullable=True)
    barrio = Column(String(120), nullable=True, index=True)

    contacto_nombre = Column(String(120), nullable=True)
    # Obligatorio para los reportes que entran por nuestro bot; NULL solo en
    # los importados de otras plataformas, donde el contacto se resuelve
    # mandando a la ficha original (`origen_url`). La regla "teléfono u
    # origen_url" se valida en `services/mascotas`, no en la BD, porque el
    # motivo es de negocio y no de integridad referencial.
    contacto_telefono = Column(String(32), nullable=True)

    # Sprint "Ayuda a Cali": reportes importados de plataformas hermanas
    # (mascotasporcolombia.com). `origen_id` es el identificador del sitio de
    # origen y sirve para deduplicar entre corridas del importador.
    origen_url = Column(String(500), nullable=True)
    origen_id = Column(String(120), nullable=True, index=True)

    # -- Campos multi-fuente (2026-08-17) --------------------------------
    # La unión de lo que traen las seis fuentes que alimentan la tabla. Antes
    # todo esto terminaba concatenado dentro de `notas`, donde no se puede
    # filtrar ni contar. Cada columna existe porque al menos una fuente la
    # publica como dato aparte: ver `documentacion_bd/mapeo_fuentes.md`.
    # Ninguna es obligatoria — casi ninguna fuente las trae todas.

    # Geografía. `barrio` ya existía y sigue siendo la zona fina; estas dos son
    # los niveles de arriba, que varias fuentes sí separan y antes se perdían
    # aplastados dentro de `ubicacion`.
    ciudad = Column(String(120), nullable=True, index=True)
    departamento = Column(String(120), nullable=True, index=True)

    # Salud y estado sanitario. Tri-estado a propósito: NULL es "la fuente no
    # lo dice", que no es lo mismo que False ("dice que no está esterilizada").
    esterilizado = Column(Boolean, nullable=True)
    vacunado = Column(Boolean, nullable=True)
    desparasitado = Column(Boolean, nullable=True)
    peso_kg = Column(Numeric(5, 2), nullable=True)
    salud = Column(String(255), nullable=True)   # lesiones / estado reportado

    # Dónde está durmiendo el animal hoy, que no es lo mismo que dónde lo
    # encontraron (`barrio`) ni dónde se atiende al público (`ubicacion`).
    # Vocabulario sin CHECK a propósito: lo alimentan fuentes externas y una
    # restricción nueva rompería un importador cada vez que aparezca un valor.
    #   hospital · hogar_de_paso · albergue · con_quien_la_encontro ·
    #   en_la_calle · con_su_familia
    resguardo = Column(String(40), nullable=True, index=True)
    resguardo_nombre = Column(String(120), nullable=True)

    # Quién llevó al animal al refugio. Es una tercera persona distinta del
    # contacto: quien lo recogió de la calle no siempre es quien lo cuida.
    rescatado_por = Column(String(120), nullable=True)
    rescatado_por_telefono = Column(String(32), nullable=True)

    recompensa = Column(Boolean, nullable=True)

    # El estado tal como lo escribe la fuente ("DISPONIBLE (ADAPTACIÓN)",
    # "stray", "Perdido"). No se traduce: sirve para auditar de dónde salió
    # nuestro `tipo_registro` cuando hubo que deducirlo.
    estado_origen = Column(String(60), nullable=True)

    # Cuándo lo publicó la fuente (≠ `created_at`, que es cuándo lo trajimos)
    # y cuándo fue la última vez que lo vimos en ella.
    publicado_origen_at = Column(DateTime, nullable=True)
    sincronizado_at = Column(DateTime, nullable=True)

    fecha_evento = Column(Date, nullable=True)   # cuándo se perdió / encontró
    estado = Column(
        String(24), nullable=False, default=MASCOTA_ESTADO_ACTIVO,
        server_default=MASCOTA_ESTADO_ACTIVO, index=True,
    )
    notas = Column(Text, nullable=True)

    bot_id = Column(
        Integer, ForeignKey("bots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source = Column(String(24), nullable=False, default="web", index=True)

    # Cuándo alguien dijo en el chat que reconocía a esta mascota (el momento
    # en que el bot le entregó el contacto) y desde qué conversación. Sirve para
    # que el equipo sepa a quién llamar para confirmar el reencuentro.
    reconocida_at = Column(DateTime, nullable=True)
    reconocida_chat = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "tipo_registro IN ('perdida','encontrada')", name="ck_mascotas_tipo"
        ),
        CheckConstraint(
            "estado IN ('activo','reconocida','reunida','cerrado')",
            name="ck_mascotas_estado",
        ),
        Index("ix_mascotas_tipo_estado", "tipo_registro", "estado"),
        # Un reporte por ficha de origen: el importador re-corre sin duplicar.
        UniqueConstraint("source", "origen_id", name="uq_mascota_origen"),
    )

    fotos = relationship(
        "MascotaFoto",
        back_populates="mascota",
        cascade="all, delete-orphan",
        order_by="MascotaFoto.id",
    )

    def __repr__(self) -> str:  # PII fuera de los logs (regla de seguridad #1)
        return (
            f"<Mascota id={self.id} codigo={self.codigo} "
            f"tipo={self.tipo_registro} especie={self.especie} "
            f"estado={self.estado} contacto=<REDACTED>>"
        )

    __str__ = __repr__


MATCH_ESTADO_NUEVA = "nueva"
MATCH_ESTADO_REVISADA = "revisada"
# Alguien dijo en el chat que esta ES su mascota y se le entregó el contacto.
# Va entre "nueva" y "confirmada": no lo revisó el equipo (por eso no es
# `revisada`) y nadie ha verificado el reencuentro (por eso no es `confirmada`),
# pero es la coincidencia más caliente del panel — hay una familia marcando un
# número ahora mismo. Se pone sola desde `entregar_contacto`.
MATCH_ESTADO_RECONOCIDA = "reconocida"
MATCH_ESTADO_CONFIRMADA = "confirmada"
MATCH_ESTADO_DESCARTADA = "descartada"
AVAILABLE_MATCH_ESTADOS = (
    MATCH_ESTADO_NUEVA, MATCH_ESTADO_REVISADA, MATCH_ESTADO_RECONOCIDA,
    MATCH_ESTADO_CONFIRMADA, MATCH_ESTADO_DESCARTADA,
)


class MascotaCoincidencia(Base):
    """Posible cruce entre una mascota que buscan y una que encontraron.

    Las escribe el job diario (`scripts/job_coincidencias_mascotas.py`, 12:00
    hora Colombia), que compara cada reporte 'perdida' activo contra cada
    'encontrada' activo con el mismo scoring que usa el bot en vivo. Sirve para
    lo que la conversación no alcanza a ver: la mascota que reportaron *después*
    de que la familia ya había escrito.

    Una fila por par (única): si el job vuelve a encontrarlo, actualiza el
    puntaje en vez de duplicar, y respeta el estado que le puso el equipo.
    """

    __tablename__ = "mascota_coincidencias"

    id = Column(Integer, primary_key=True, index=True)
    perdida_id = Column(
        Integer, ForeignKey("mascotas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    encontrada_id = Column(
        Integer, ForeignKey("mascotas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    score = Column(Integer, nullable=False, default=0, index=True)
    # Qué campos coincidieron y cuánto sumó cada uno: el equipo necesita ver el
    # porqué antes de llamar a una familia.
    detalle = Column(JSONB, nullable=True)
    estado = Column(
        String(16), nullable=False, default=MATCH_ESTADO_NUEVA,
        server_default=MATCH_ESTADO_NUEVA, index=True,
    )
    notas = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("perdida_id", "encontrada_id", name="uq_mascota_par"),
        CheckConstraint(
            "estado IN ('nueva','revisada','confirmada','descartada')",
            name="ck_match_estado",
        ),
        Index("ix_match_estado_score", "estado", "score"),
    )

    perdida = relationship("Mascota", foreign_keys=[perdida_id])
    encontrada = relationship("Mascota", foreign_keys=[encontrada_id])

    def __repr__(self) -> str:
        return (
            f"<MascotaCoincidencia id={self.id} perdida={self.perdida_id} "
            f"encontrada={self.encontrada_id} score={self.score} "
            f"estado={self.estado}>"
        )

    __str__ = __repr__


class MascotaFoto(Base):
    """Foto de un reporte, guardada en el storage bajo `mascotas/<codigo>/`.

    `mascota_id` es NULL mientras la foto está en el limbo: el ciudadano suele
    mandar las fotos ANTES de que el bot termine de recoger los datos, así que
    se suben contra `upload_session` (uuid efímero del chat) y se adoptan
    cuando el reporte se crea.
    """

    __tablename__ = "mascota_fotos"

    id = Column(Integer, primary_key=True, index=True)
    mascota_id = Column(
        Integer, ForeignKey("mascotas.id", ondelete="CASCADE"), nullable=True, index=True
    )
    upload_session = Column(String(64), nullable=True, index=True)
    storage_key = Column(String(400), nullable=False)
    content_type = Column(String(60), nullable=False, default="image/jpeg")
    bytes_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Compresión: `scripts/optimizar_fotos_mascotas.py` (que corre desde el
    # equipo del CEO, porque el bucket es privado) re-comprime cada foto y
    # marca aquí que ya pasó, para no volver a procesarla nunca. `bytes_size`
    # es el peso actual; `bytes_original`, lo que pesaba antes.
    optimizada = Column(
        Boolean, nullable=False, default=False, server_default="false", index=True
    )
    optimizada_at = Column(DateTime, nullable=True)
    bytes_original = Column(Integer, nullable=True)

    mascota = relationship("Mascota", back_populates="fotos")

    def __repr__(self) -> str:
        return (
            f"<MascotaFoto id={self.id} mascota_id={self.mascota_id} "
            f"key={self.storage_key!r}>"
        )

    __str__ = __repr__


# ===== Agendamientos: la llamada de rescate de un chat abandonado ==========
#
# Cuando el bot da una conversación por abandonada, hoy la etiqueta y se la
# asigna a un asesor en la bandeja. Eso alcanza para que alguien la vea, pero
# no para que alguien la *llame*: la bandeja se ordena por actividad y un chat
# frío se hunde. Esta tabla es la lista de llamadas pendientes — un renglón por
# cliente potencial que se fue a mitad de camino, con la fecha en que hay que
# marcarle y un estado que el asesor cierra cuando ya lo hizo.
#
# La llamada NO se hace desde la plataforma (decisión del CEO): aquí sólo se
# registra a quién hay que llamar y cuándo.

AGENDAMIENTO_PENDIENTE = "pendiente"
AGENDAMIENTO_CERRADO = "cerrado"
AVAILABLE_AGENDAMIENTO_ESTADOS = (AGENDAMIENTO_PENDIENTE, AGENDAMIENTO_CERRADO)

#: Qué tan lejos llegó la conversación antes de que la persona dejara de
#: contestar. Es el nivel de interés del cliente potencial:
#:  - `con_informacion`: el bot alcanzó a responderle algo. Son los que valen
#:    una llamada — preguntaron, recibieron respuesta y aun así se fueron.
#:  - `solo_bienvenida`: escribió una vez, recibió el saludo y nunca volvió.
#:    No se les agenda llamada (ver `services/agendamientos.py`); el nivel
#:    existe igual para poder distinguirlos si mañana se quieren trabajar.
AGENDAMIENTO_NIVEL_CON_INFORMACION = "con_informacion"
AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA = "solo_bienvenida"
AVAILABLE_AGENDAMIENTO_NIVELES = (
    AGENDAMIENTO_NIVEL_CON_INFORMACION,
    AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA,
)

#: Días entre el abandono y la llamada tentativa (pedido del CEO).
AGENDAMIENTO_DIAS_PARA_LLAMAR = 3


class Agendamiento(Base):
    """Una llamada por hacer a alguien que dejó la conversación a medias.

    Los datos del cliente (nombre y teléfono) **no se copian aquí**: viven en
    `conversations` y se leen por el join. Duplicarlos abriría la puerta a que
    la lista muestre un teléfono viejo después de que el contacto se corrigiera
    en la bandeja, y el teléfono es justamente el dato por el que existe esta
    pantalla.

    `asesor` sí se guarda, y es a propósito: es el nombre del turno **en el
    momento del abandono** (`conversations.assigned_to` puede reasignarse
    después). Es un nombre de rotación, no un usuario — la cuenta de asesores
    de Arranquemos Pues es un solo login compartido.
    """

    __tablename__ = "agendamientos"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nivel_interes = Column(
        String(24),
        nullable=False,
        default=AGENDAMIENTO_NIVEL_CON_INFORMACION,
        server_default=AGENDAMIENTO_NIVEL_CON_INFORMACION,
    )
    #: Cuándo hay que llamar. Es `Date` y no `DateTime` porque lo que se acordó
    #: es el día, no la hora: quien llama elige el momento.
    fecha_llamada = Column(Date, nullable=False, index=True)
    estado = Column(
        String(16),
        nullable=False,
        default=AGENDAMIENTO_PENDIENTE,
        server_default=AGENDAMIENTO_PENDIENTE,
        index=True,
    )
    asesor = Column(String(64), nullable=True)

    cerrado_at = Column(DateTime, nullable=True)
    cerrado_por_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    conversation = relationship("Conversation")

    __table_args__ = (
        # La pantalla siempre pregunta lo mismo: "lo de este team, por fecha
        # de llamada".
        Index("ix_agendamientos_team_fecha", "team_id", "fecha_llamada"),
        # Un chat no puede tener DOS llamadas pendientes: si la persona vuelve,
        # se calla otra vez y el bot la vuelve a abandonar, el asesor no
        # necesita dos renglones de la misma persona. El índice es parcial
        # a propósito — una vez cerrado, el mismo chat sí puede volver a
        # generar un agendamiento nuevo, que es una oportunidad nueva.
        Index(
            "uq_agendamientos_conv_pendiente",
            "conversation_id",
            unique=True,
            postgresql_where=text("estado = 'pendiente'"),
            sqlite_where=text("estado = 'pendiente'"),
        ),
    )

    def __repr__(self) -> str:
        # Sin nombre ni teléfono: son datos de un tercero (regla 8).
        return (
            f"<Agendamiento id={self.id} team_id={self.team_id} "
            f"conversation_id={self.conversation_id} estado={self.estado!r} "
            f"fecha_llamada={self.fecha_llamada}>"
        )

    __str__ = __repr__


# ===== Pedidos cerrados por el bot =====
#
# Cuando el cliente manda nombre, dirección y pedido, el bot llama a
# `registrar_pedido` y la fila termina en dos lugares: la hoja de cálculo del
# equipo (`services/pedidos_sheet.py`, que es donde trabaja quien despacha) y
# esta tabla, que es la que puede mostrar la app.
#
# Los datos SÍ se copian aquí, a diferencia de `agendamientos` —que los lee de
# la conversación—. Un pedido es un documento: dice a qué dirección se despachó
# el 12 de septiembre, y esa dirección no puede cambiar porque el contacto se
# corrigió después. Lo mismo con el nombre y el total.

PEDIDO_PENDIENTE = "pendiente"
PEDIDO_DESPACHADO = "despachado"
PEDIDO_CANCELADO = "cancelado"
AVAILABLE_PEDIDO_ESTADOS = (PEDIDO_PENDIENTE, PEDIDO_DESPACHADO, PEDIDO_CANCELADO)


class Pedido(Base):
    """Un pedido que el bot cerró en el chat."""

    __tablename__ = "pedidos"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Nulo cuando el pedido viene del simulador: ahí no hay conversación real.
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    nombre = Column(String(120), nullable=False)
    direccion = Column(String(250), nullable=False)
    detalle = Column(Text, nullable=False)
    total = Column(String(40), nullable=True)
    telefono = Column(String(32), nullable=True)
    #: whatsapp | simulador — de dónde salió. En una demostración la fila del
    #: simulador se ve igual que una de verdad, y quien despacha tiene que poder
    #: distinguirlas de un vistazo.
    origen = Column(String(24), nullable=False, default="whatsapp", server_default="whatsapp")
    estado = Column(
        String(16), nullable=False, default=PEDIDO_PENDIENTE,
        server_default=PEDIDO_PENDIENTE, index=True,
    )
    #: Si la fila alcanzó a escribirse en la hoja de Drive. Cuando es False el
    #: pedido existe igual —está aquí— pero nadie lo vio en la hoja: es el
    #: aviso de que hay que copiarlo a mano o revisar el script.
    en_hoja = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    conversation = relationship("Conversation")

    __table_args__ = (
        CheckConstraint(
            "estado IN ('pendiente','despachado','cancelado')",
            name="ck_pedidos_estado",
        ),
        # La pantalla siempre pregunta lo mismo: "los de este equipo, el más
        # reciente arriba".
        Index("ix_pedidos_team_creado", "team_id", "created_at"),
    )

    def __repr__(self) -> str:
        # Nombre, dirección y teléfono son datos de un tercero (reglas 1 y 8):
        # no salen ni en un repr de debug.
        return (
            f"<Pedido id={self.id} team_id={self.team_id} "
            f"estado={self.estado!r} origen={self.origen!r} "
            f"nombre=<REDACTED> direccion=<REDACTED> telefono=<REDACTED>>"
        )

    __str__ = __repr__


# ===== Sprint 31: lo que vende cada cuenta, en la base ====================
#
# Modelo completo en `docs/bots_productos_modelo.puml`. La idea de fondo: hoy
# lo que vende un cliente vive en un `.md` del repo y en JSON sueltos, así que
# cambiar un precio es un despliegue. Estas ocho tablas lo mueven a la base,
# con aislamiento por cuenta: TODO cuelga de `teams.id`, directo (`team_id`) o
# a través de `bot_productos`. Un producto nunca es visible para otra cuenta.
#
# Dos decisiones transversales que conviene leer antes de tocar nada:
#
# 1. **Centinela `0` en vez de NULL** en `bot_producto_filas.variante_id`,
#    `bot_producto_medios.variante_id` y `bot_recordatorios.bot_id`. En
#    Postgres `NULL <> NULL`, así que un UNIQUE que incluya una columna
#    nullable NO impide duplicados cuando esa columna viene vacía: el
#    importador volvería a insertar las mismas filas en cada corrida. Ya lo
#    mordimos con `uq_mascota_origen` (`origen_id` nullable). Aquí `0`
#    significa "aplica a todas" y es un valor real, así que el UNIQUE sí
#    muerde. Por eso tampoco llevan FK: `0` no existe en la tabla apuntada.
#    Mismo motivo para `externo_id`, que es `''` y no NULL cuando la fila no
#    viene de un archivo externo.
#
# 2. **Enums con constantes + CheckConstraint**, como el resto del modelo. Sin
#    el CHECK, el primer typo del importador ('publicad@') entra a la base y
#    nadie se entera hasta que el bot deja de mostrar el producto.
#
# 3. **Toda columna con default lleva `server_default`, no sólo `default=`.**
#    `default=` lo aplica el ORM al insertar y NO llega al DDL: una tabla que
#    cree `create_all()` queda sin ese DEFAULT en la base. Eso fue justo lo que
#    pasó en RDS el 2026-09-16: el `create_all()` del arranque se adelantó a
#    `migrate_sprint31_productos.py`, creó las ocho tablas y dejó 21 columnas
#    sin default; como las tablas ya existían, el `CREATE TABLE IF NOT EXISTS`
#    de la migración fue un no-op y no reparó nada.
#
#    Los timestamps van con `server_default=func.now()` y no con
#    `text("NOW()")`: `func.now()` es genérico y lo compila cada dialecto
#    —`now()` en Postgres, `CURRENT_TIMESTAMP` en SQLite—, que es lo que hace
#    falta porque la suite corre `create_all()` sobre SQLite en cada fixture y
#    ahí `NOW()` no existe.
#
#    Estos defaults tienen que coincidir con la tabla `DEFAULTS` de
#    `backend/scripts/migrate_sprint31_productos.py`. No se comparten por
#    import a propósito (una migración es una foto del pasado y no debe
#    moverse cuando cambie el modelo); quien los mantiene honestos es
#    `tests/test_defaults_schema_productos.py`, que falla si divergen.

# `bot_productos.tipo`
PRODUCTO_TIPO_PLAN = "plan"                          # un plan de viaje, un paquete
PRODUCTO_TIPO_PRODUCTO = "producto"                  # un SKU físico
PRODUCTO_TIPO_CATALOGO_EXTERNO = "catalogo_externo"  # espejo de Shopify/Meta
PRODUCTO_TIPO_FICHA = "ficha"                        # info que no se vende (sedes, envíos)
AVAILABLE_PRODUCTO_TIPOS = (
    PRODUCTO_TIPO_PLAN,
    PRODUCTO_TIPO_PRODUCTO,
    PRODUCTO_TIPO_CATALOGO_EXTERNO,
    PRODUCTO_TIPO_FICHA,
)

# `bot_productos.estado`
PRODUCTO_ESTADO_BORRADOR = "borrador"    # se edita; el bot no lo ve
PRODUCTO_ESTADO_PUBLICADO = "publicado"  # el bot lo puede vender
PRODUCTO_ESTADO_ARCHIVADO = "archivado"  # ya no se vende, se conserva el historial
AVAILABLE_PRODUCTO_ESTADOS = (
    PRODUCTO_ESTADO_BORRADOR,
    PRODUCTO_ESTADO_PUBLICADO,
    PRODUCTO_ESTADO_ARCHIVADO,
)

# `bot_producto_filas.tipo`
FILA_TIPO_SALIDA = "salida"  # viajes: una fecha de salida con su precio
FILA_TIPO_PRECIO = "precio"  # una lista de precios sin fecha
FILA_TIPO_SEDE = "sede"      # Talulah: una sede con su dirección y horario
FILA_TIPO_ENVIO = "envio"    # tiempos y costos de envío por ciudad
FILA_TIPO_FAQ = "faq"        # pregunta/respuesta puntual
AVAILABLE_FILA_TIPOS = (
    FILA_TIPO_SALIDA,
    FILA_TIPO_PRECIO,
    FILA_TIPO_SEDE,
    FILA_TIPO_ENVIO,
    FILA_TIPO_FAQ,
)

# `bot_producto_alias.nivel`
ALIAS_NIVEL_PRODUCTO = "producto"
ALIAS_NIVEL_VARIANTE = "variante"
AVAILABLE_ALIAS_NIVELES = (ALIAS_NIVEL_PRODUCTO, ALIAS_NIVEL_VARIANTE)

# `bot_producto_cargas.estado`
CARGA_ESTADO_REVISION = "revision"    # el diff está esperando aprobación humana
CARGA_ESTADO_APLICADO = "aplicado"
CARGA_ESTADO_RECHAZADO = "rechazado"
AVAILABLE_CARGA_ESTADOS = (
    CARGA_ESTADO_REVISION,
    CARGA_ESTADO_APLICADO,
    CARGA_ESTADO_RECHAZADO,
)

#: Valor de "aplica a todas/todos" en las columnas con centinela (ver arriba).
REF_TODAS = 0


class BotProducto(Base):
    """Algo que una cuenta vende o cuenta: un plan, un SKU, una ficha."""

    __tablename__ = "bot_productos"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Identificador estable y legible dentro de la cuenta ('covenas_4d3n').
    #: Es lo que el bot nombra en sus tools, así que no cambia con el nombre
    #: comercial.
    slug = Column(String(80), nullable=False)
    tipo = Column(
        String(24),
        nullable=False,
        default=PRODUCTO_TIPO_PRODUCTO,
        server_default=PRODUCTO_TIPO_PRODUCTO,
    )
    nombre = Column(String(160), nullable=False)
    estado = Column(
        String(16),
        nullable=False,
        default=PRODUCTO_ESTADO_BORRADOR,
        server_default=PRODUCTO_ESTADO_BORRADOR,
        index=True,
    )
    #: Una línea. Es lo único de este producto que entra al índice del prompt,
    #: de ahí el límite duro: 240 caracteres × N productos es el presupuesto
    #: de tokens del prefijo cacheado.
    resumen = Column(String(240), nullable=True)
    #: Nivel 3: lo que el bot debe saber al vender ESTE producto. Se carga solo
    #: cuando la conversación llega a él, no en el prefijo.
    instrucciones = Column(Text, nullable=True)
    atributos = Column(JSONB, nullable=False, default=dict, server_default="{}")
    vigencia_desde = Column(Date, nullable=True)
    vigencia_hasta = Column(Date, nullable=True)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("team_id", "slug", name="uq_bot_productos_team_slug"),
        CheckConstraint(
            "tipo IN ('plan','producto','catalogo_externo','ficha')",
            name="ck_bot_productos_tipo",
        ),
        CheckConstraint(
            "estado IN ('borrador','publicado','archivado')",
            name="ck_bot_productos_estado",
        ),
        # La consulta de siempre: "los publicados de esta cuenta".
        Index("ix_bot_productos_team_estado", "team_id", "estado"),
    )

    team = relationship("Team")
    variantes = relationship(
        "BotProductoVariante",
        back_populates="producto",
        cascade="all, delete-orphan",
    )
    filas = relationship(
        "BotProductoFila", back_populates="producto", cascade="all, delete-orphan"
    )
    medios = relationship(
        "BotProductoMedio", back_populates="producto", cascade="all, delete-orphan"
    )
    alias = relationship(
        "BotProductoAlias", back_populates="producto", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        # Regla 1 (CLAUDE.md): `instrucciones` lo escribe el cliente y suele
        # traer datos de contacto —"si preguntan, el WhatsApp de la sede es
        # …"—. No sale ni en un repr de debug.
        return (
            f"<BotProducto id={self.id} team_id={self.team_id} "
            f"slug={self.slug!r} tipo={self.tipo!r} estado={self.estado!r} "
            f"instrucciones=<REDACTED> resumen=<REDACTED>>"
        )

    __str__ = __repr__


class BotProductoVariante(Base):
    """Una versión del producto: una habitación, un sabor, una talla."""

    __tablename__ = "bot_producto_variantes"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(
        Integer,
        ForeignKey("bot_productos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    slug = Column(String(80), nullable=False)
    nombre = Column(String(160), nullable=False)
    #: Notas cortas para el bot sobre esta variante en particular.
    instrucciones = Column(Text, nullable=True)
    atributos = Column(JSONB, nullable=False, default=dict, server_default="{}")
    #: Auto-FK: "esta variante cobra lo mismo que aquella". Evita duplicar la
    #: tabla de precios entre dos hoteles que comparten tarifario.
    precios_de_variante_id = Column(
        Integer,
        ForeignKey("bot_producto_variantes.id", ondelete="SET NULL"),
        nullable=True,
    )
    activo = Column(Boolean, nullable=False, default=True, server_default="true")
    orden = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "producto_id", "slug", name="uq_bot_producto_variantes_slug"
        ),
    )

    producto = relationship("BotProducto", back_populates="variantes")
    precios_de = relationship("BotProductoVariante", remote_side=[id])


class BotProductoFila(Base):
    """Una fila del catálogo: una salida, un precio, una sede, un envío.

    Una sola tabla para todos los negocios. Lo que se filtra y se ordena son
    columnas (`inicio`, `activo`, `tipo`); lo que solo se muestra va en
    `valores` (JSONB), que es donde caben las columnas que cada cliente trae
    en su Excel sin migrar la tabla.
    """

    __tablename__ = "bot_producto_filas"

    # `BigInteger` pelado rompe la suite entera: los fixtures hacen
    # `create_all()` del metadata completo sobre SQLite, y ahí un BIGINT no
    # autoincrementa — el primer INSERT muere con "NOT NULL constraint
    # failed". La variante deja BIGSERIAL en Postgres e INTEGER en SQLite.
    id = Column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True
    )
    producto_id = Column(
        Integer,
        ForeignKey("bot_productos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Centinela: `0` = la fila aplica a todas las variantes. NOT NULL y sin FK
    #: a propósito — ver la nota de cabecera de la sección.
    variante_id = Column(
        Integer, nullable=False, default=REF_TODAS, server_default="0"
    )
    tipo = Column(
        String(16),
        nullable=False,
        default=FILA_TIPO_PRECIO,
        server_default=FILA_TIPO_PRECIO,
    )
    #: Cómo la nombra el cliente: 'AGOSTO 21 AL 24', 'Sede Poblado'.
    etiqueta = Column(String(160), nullable=True)
    inicio = Column(Date, nullable=True)
    fin = Column(Date, nullable=True)
    valores = Column(JSONB, nullable=False, default=dict, server_default="{}")
    nota = Column(Text, nullable=True)
    orden = Column(Integer, nullable=False, default=0, server_default="0")
    activo = Column(Boolean, nullable=False, default=True, server_default="true")
    #: Id de la fila en el archivo de origen. `''` (no NULL) cuando se creó a
    #: mano: es lo que hace que el UNIQUE sirva de candado al reimportar.
    externo_id = Column(String(120), nullable=False, default="", server_default="")
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "producto_id",
            "variante_id",
            "externo_id",
            name="uq_bot_producto_filas_externo",
        ),
        CheckConstraint(
            "tipo IN ('salida','precio','sede','envio','faq')",
            name="ck_bot_producto_filas_tipo",
        ),
        # La consulta caliente del bot: "las próximas salidas vigentes de este
        # producto". Parcial sobre `activo` porque las retiradas no se
        # consultan nunca y son la mayoría tras unas cuantas temporadas.
        # Los dos kwargs de dialecto son necesarios: sin `sqlite_where` el
        # índice se crea completo en la suite (precedente:
        # `uq_agendamientos_conv_pendiente`).
        Index(
            "ix_bot_producto_filas_prod_inicio",
            "producto_id",
            "inicio",
            postgresql_where=text("activo"),
            sqlite_where=text("activo"),
        ),
        # Para preguntar por dentro del JSONB ("las que tengan tarifa doble")
        # sin escanear la tabla.
        Index(
            "ix_bot_producto_filas_valores",
            "valores",
            postgresql_using="gin",
        ),
    )

    producto = relationship("BotProducto", back_populates="filas")


class BotProductoMedio(Base):
    """Una foto, un video o un PDF que ilustra un producto o una variante."""

    __tablename__ = "bot_producto_medios"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(
        Integer,
        ForeignKey("bot_productos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Centinela `0` = ilustra al producto entero, no a una variante.
    variante_id = Column(
        Integer, nullable=False, default=REF_TODAS, server_default="0"
    )
    #: Nombre con el que el bot lo pide ('flyer_siropes').
    clave = Column(String(80), nullable=False)
    url = Column(String(1024), nullable=False)
    #: image | video | document — el mismo vocabulario que ya usa `llm_config`.
    tipo = Column(String(24), nullable=False, default="image", server_default="image")
    descripcion = Column(String(300), nullable=True)
    #: Cuándo corresponde mandarlo. Ej: {"meses": [8, 9, 10, 11]}.
    aplica = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_bot_producto_medios_prod_clave", "producto_id", "clave"),
    )

    producto = relationship("BotProducto", back_populates="medios")


class BotProductoAlias(Base):
    """Cómo le dice la gente a un producto o a una variante.

    'el de cove', 'coveñas', 'el del 21' apuntan todos a la misma salida. Sin
    esto, el bot depende de que el cliente escriba el nombre comercial exacto.
    """

    __tablename__ = "bot_producto_alias"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(
        Integer,
        ForeignKey("bot_productos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: producto | variante — a qué apunta `ref_id`. No hay FK porque el destino
    #: depende del nivel.
    nivel = Column(
        String(16),
        nullable=False,
        default=ALIAS_NIVEL_PRODUCTO,
        server_default=ALIAS_NIVEL_PRODUCTO,
    )
    ref_id = Column(Integer, nullable=False, default=REF_TODAS, server_default="0")
    alias = Column(String(160), nullable=False)
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "producto_id", "nivel", "alias", name="uq_bot_producto_alias"
        ),
        CheckConstraint(
            "nivel IN ('producto','variante')", name="ck_bot_producto_alias_nivel"
        ),
    )

    producto = relationship("BotProducto", back_populates="alias")


class BotProductoBot(Base):
    """Qué productos ve cada bot. Un bot de soporte no vende el catálogo."""

    __tablename__ = "bot_producto_bots"

    id = Column(Integer, primary_key=True, index=True)
    bot_id = Column(
        Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    producto_id = Column(
        Integer,
        ForeignKey("bot_productos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    activo = Column(Boolean, nullable=False, default=True, server_default="true")
    orden = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("bot_id", "producto_id", name="uq_bot_producto_bots"),
    )

    bot = relationship("Bot")
    producto = relationship("BotProducto")


class BotProductoCarga(Base):
    """Bitácora de cada intento de cargar un archivo del cliente.

    Ninguna fuente entra a la base sin revisión humana: el importador escribe
    el `diff` en estado `revision`, alguien lo aprueba y recién ahí se aplica.
    Es el mismo procedimiento de `actualizar_fuente.py` para las mascotas.
    """

    __tablename__ = "bot_producto_cargas"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(
        Integer,
        ForeignKey("bot_productos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    archivo = Column(String(300), nullable=False)
    #: Hash del archivo. Si repite, es el mismo Excel de la vez pasada.
    hash_sha256 = Column(String(64), nullable=True, index=True)
    filas_nuevas = Column(Integer, nullable=False, default=0, server_default="0")
    filas_cambiadas = Column(Integer, nullable=False, default=0, server_default="0")
    filas_retiradas = Column(Integer, nullable=False, default=0, server_default="0")
    estado = Column(
        String(16),
        nullable=False,
        default=CARGA_ESTADO_REVISION,
        server_default=CARGA_ESTADO_REVISION,
        index=True,
    )
    #: El antes/después que se le muestra a quien aprueba.
    diff = Column(JSONB, nullable=False, default=dict, server_default="{}")
    aprobado_por_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "estado IN ('revision','aplicado','rechazado')",
            name="ck_bot_producto_cargas_estado",
        ),
        Index("ix_bot_producto_cargas_prod_creado", "producto_id", "created_at"),
    )

    producto = relationship("BotProducto")

    def __repr__(self) -> str:
        # Regla 1 (CLAUDE.md): `diff` trae filas crudas del Excel del cliente y
        # ahí puede venir de todo —nombres, teléfonos, direcciones de clientes
        # finales—. El nombre del archivo también, así que tampoco sale.
        return (
            f"<BotProductoCarga id={self.id} producto_id={self.producto_id} "
            f"estado={self.estado!r} filas_nuevas={self.filas_nuevas} "
            f"filas_cambiadas={self.filas_cambiadas} "
            f"filas_retiradas={self.filas_retiradas} "
            f"archivo=<REDACTED> diff=<REDACTED>>"
        )

    __str__ = __repr__


class BotRecordatorio(Base):
    """Reenganche a quien dejó de contestar. Configurable por cuenta.

    Hoy la cadena de recordatorios vive quemada en el código del tick; esto la
    mueve a la base para que cada cliente ponga sus tiempos y sus textos.
    """

    __tablename__ = "bot_recordatorios"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Centinela `0` = aplica a todos los bots de la cuenta. NOT NULL y sin FK
    #: por lo mismo que las otras: con NULL el UNIQUE no muerde.
    bot_id = Column(Integer, nullable=False, default=REF_TODAS, server_default="0")
    orden = Column(Integer, nullable=False, default=1, server_default="1")
    #: Minutos de silencio antes de mandarlo.
    minutos = Column(Integer, nullable=False)
    texto = Column(Text, nullable=False)
    #: Condiciones para saltárselo. Ej: {"tools": ["registrar_venta"]} =
    #: no molestar a quien ya compró.
    omitir_si = Column(JSONB, nullable=False, default=dict, server_default="{}")
    #: Franja horaria permitida, hora de Colombia. Nadie quiere un recordatorio
    #: comercial a las 3 de la mañana.
    hora_min = Column(Integer, nullable=False, default=8, server_default="8")
    hora_max = Column(Integer, nullable=False, default=20, server_default="20")
    activo = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        # `team_id` va en el UNIQUE aunque el .puml lo omita: sin él, dos
        # cuentas que configuren "todos los bots" (bot_id = 0) chocarían en el
        # recordatorio 1, y la segunda cuenta no podría configurar nada.
        UniqueConstraint(
            "team_id", "bot_id", "orden", name="uq_bot_recordatorios_orden"
        ),
        # Pasada la ventana de 24 h de WhatsApp ya no se puede escribir sin
        # plantilla aprobada, así que un recordatorio a los 1500 minutos no
        # llegaría nunca.
        CheckConstraint(
            "minutos > 0 AND minutos < 1440", name="ck_bot_recordatorios_minutos"
        ),
        CheckConstraint("orden > 0", name="ck_bot_recordatorios_orden"),
        CheckConstraint(
            "hora_min >= 0 AND hora_min <= 23 AND hora_max >= 0 AND hora_max <= 23 "
            "AND hora_min <= hora_max",
            name="ck_bot_recordatorios_franja",
        ),
        Index("ix_bot_recordatorios_team_bot", "team_id", "bot_id"),
    )

    team = relationship("Team")

    def __repr__(self) -> str:
        # `texto` lo escribe el cliente y puede traer datos de contacto.
        return (
            f"<BotRecordatorio id={self.id} team_id={self.team_id} "
            f"bot_id={self.bot_id} orden={self.orden} minutos={self.minutos} "
            f"activo={self.activo} texto=<REDACTED>>"
        )

    __str__ = __repr__
