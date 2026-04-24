from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    UniqueConstraint,
    Index,
)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    memberships = relationship(
        "TeamMember", back_populates="user", cascade="all, delete-orphan"
    )
    owned_teams = relationship(
        "Team", back_populates="owner", foreign_keys="Team.owner_user_id"
    )


class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
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
]


class MetaAccount(Base):
    """Cuenta de Meta WhatsApp Cloud API asociada a un team."""
    __tablename__ = "meta_accounts"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(
        Integer, ForeignKey("teams.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    phone_number_id = Column(String, nullable=False)
    waba_id = Column(String, nullable=False)
    display_phone = Column(String, nullable=False)
    verified_name = Column(String, nullable=True)  # Nombre visible en WhatsApp Business
    # IMPORTANTE: este campo guarda el ciphertext Fernet del access token.
    # Para descifrarlo usa backend.app.services.crypto.decrypt_secret.
    # NUNCA lo incluyas en un schema Pydantic de salida.
    encrypted_access_token = Column(Text, nullable=False)
    api_version = Column(String, nullable=False, default="v22.0")
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
            f"phone_number_id={self.phone_number_id} status={self.status!r} "
            f"encrypted_access_token=<REDACTED>>"
        )

    __str__ = __repr__


class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    contact_wa_id = Column(String, nullable=False)  # E.164 sin +
    contact_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="open")  # open | pending | closed
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
    "send_media",      # enviar imagen/video/documento
    "wait_input",      # esperar respuesta del contacto
    "delay",           # pausa en segundos
    "condition",       # ramificación por variable / keyword
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
    action_type = Column(String(32), nullable=False, default="resume_session")
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
    """Contactos que llenan el form de la landing /gloma.

    No tiene FK a users porque son prospects, no clientes aún.
    `source` permite distinguir orígenes cuando haya más de una landing.
    """

    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, index=True)
    telefono = Column(String(32), nullable=False)
    source = Column(String(64), nullable=False, default="gloma_landing", index=True)
    user_agent = Column(String(512), nullable=True)
    ip_address = Column(String(64), nullable=True)
    contacted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
