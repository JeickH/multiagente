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
    access_token = Column(Text, nullable=False)
    api_version = Column(String, nullable=False, default="v22.0")
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    team = relationship("Team", back_populates="meta_account")


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
