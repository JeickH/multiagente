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
    CheckConstraint,
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Sprint 15: estado de tutoriales interactivos por módulo.
    # Llaves esperadas: mi_plan, mensajes, bots, campanas
    # Valor: {"done": bool, "skipped": bool, "completed_at": iso8601 | null}
    tutorials_completed = Column(JSONB, nullable=False, default=dict, server_default="{}")

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
    # Quién atiende la conversación. Por defecto el bot; al hacer handoff se
    # reasigna a un asesor humano (ej. "asesor_1"). String simple para el MVP
    # (no FK a users) — basta para distinguir bot vs humano en la UI.
    assigned_to = Column(
        String, nullable=False, default="bot", server_default="bot"
    )
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
        Index("ix_contacts_team_id", "team_id"),
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
        Index("ix_contact_groups_team_id", "team_id"),
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
