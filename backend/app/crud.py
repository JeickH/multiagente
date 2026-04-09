import os
from datetime import datetime
from typing import Optional, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import desc
from passlib.context import CryptContext

from . import models, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ===================== Users =====================
def get_user_by_email(db: Session, correo: str):
    return db.query(models.User).filter(models.User.correo == correo).first()


def get_user_by_documento(db: Session, documento: str):
    return db.query(models.User).filter(models.User.documento == documento).first()


def create_user(db: Session, user: schemas.UserCreate) -> models.User:
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        nombre=user.nombre,
        tipo_documento=user.tipo_documento,
        documento=user.documento,
        correo=user.correo,
        hashed_password=hashed_password,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def authenticate_user(db: Session, correo: str, password: str):
    user = get_user_by_email(db, correo)
    if not user:
        return False
    if not pwd_context.verify(password, user.hashed_password):
        return False
    return user


# ===================== Teams =====================
def create_team(db: Session, nombre: str, owner: models.User) -> models.Team:
    team = models.Team(nombre=nombre, owner_user_id=owner.id)
    db.add(team)
    db.commit()
    db.refresh(team)
    # Crear membership owner con todos los permisos en true
    member = models.TeamMember(team_id=team.id, user_id=owner.id, role="owner")
    db.add(member)
    db.commit()
    db.refresh(member)
    set_member_permissions(
        db, member, {key: True for key in models.AVAILABLE_PERMISSIONS}
    )
    return team


def get_team_by_owner(db: Session, owner: models.User) -> Optional[models.Team]:
    return (
        db.query(models.Team)
        .filter(models.Team.owner_user_id == owner.id)
        .first()
    )


def get_membership_for_user(
    db: Session, user: models.User
) -> Optional[models.TeamMember]:
    """Devuelve el primer team al que pertenece el usuario (1 team por user en MVP)."""
    return (
        db.query(models.TeamMember)
        .filter(models.TeamMember.user_id == user.id)
        .first()
    )


def get_team_members(db: Session, team_id: int) -> List[models.TeamMember]:
    return (
        db.query(models.TeamMember)
        .filter(models.TeamMember.team_id == team_id)
        .all()
    )


def add_member_to_team(
    db: Session,
    team: models.Team,
    user: models.User,
    role: str = "agent",
    permissions: Optional[Dict[str, bool]] = None,
) -> models.TeamMember:
    member = models.TeamMember(team_id=team.id, user_id=user.id, role=role)
    db.add(member)
    db.commit()
    db.refresh(member)
    perms = {key: False for key in models.AVAILABLE_PERMISSIONS}
    if permissions:
        perms.update({k: bool(v) for k, v in permissions.items() if k in models.AVAILABLE_PERMISSIONS})
    set_member_permissions(db, member, perms)
    return member


def set_member_permissions(
    db: Session, member: models.TeamMember, permissions: Dict[str, bool]
):
    existing = {p.permission_key: p for p in member.permissions}
    for key in models.AVAILABLE_PERMISSIONS:
        enabled = bool(permissions.get(key, False))
        if key in existing:
            existing[key].enabled = enabled
        else:
            db.add(
                models.TeamPermission(
                    team_member_id=member.id,
                    permission_key=key,
                    enabled=enabled,
                )
            )
    db.commit()
    db.refresh(member)


def permissions_dict(member: models.TeamMember) -> Dict[str, bool]:
    out = {key: False for key in models.AVAILABLE_PERMISSIONS}
    for p in member.permissions:
        out[p.permission_key] = p.enabled
    return out


def member_has_permission(member: models.TeamMember, key: str) -> bool:
    return permissions_dict(member).get(key, False)


# ===================== Meta Account =====================
def get_meta_account_for_team(db: Session, team_id: int) -> Optional[models.MetaAccount]:
    return (
        db.query(models.MetaAccount)
        .filter(models.MetaAccount.team_id == team_id)
        .first()
    )


def upsert_default_meta_account_for_team(
    db: Session, team: models.Team, owner_email: Optional[str] = None
) -> Optional[models.MetaAccount]:
    """Crea (si no existe) la MetaAccount del team con los datos del .env.

    Solo provisiona la cuenta si el correo del owner del team coincide con
    META_OWNER_EMAIL. Esto garantiza que únicamente un usuario específico tenga
    la cuenta de WhatsApp registrada; el resto queda sin cuenta.

    Adicionalmente, si el usuario NO es el propietario pero su team tiene una
    MetaAccount residual (de pruebas viejas), la elimina para dejar el estado
    consistente con la regla de negocio.
    """
    existing = get_meta_account_for_team(db, team.id)

    meta_owner_email = (os.getenv("META_OWNER_EMAIL") or "").strip().lower()
    team_owner_email = (owner_email or "").strip().lower()
    is_meta_owner = bool(meta_owner_email) and team_owner_email == meta_owner_email

    if not is_meta_owner:
        # Este usuario no debe tener cuenta de Meta: limpiar leftovers
        if existing:
            db.delete(existing)
            db.commit()
        return None

    if existing:
        return existing

    phone_number_id = os.getenv("META_PHONE_NUMBER_ID")
    waba_id = os.getenv("META_WABA_ID")
    access_token = os.getenv("META_ACCESS_TOKEN")
    display_phone = os.getenv("META_DISPLAY_PHONE", "")
    verified_name = os.getenv("META_VERIFIED_NAME", "") or None
    api_version = os.getenv("META_API_VERSION", "v22.0")

    if not (phone_number_id and waba_id and access_token):
        return None  # No hay credenciales configuradas todavía

    account = models.MetaAccount(
        team_id=team.id,
        phone_number_id=phone_number_id,
        waba_id=waba_id,
        display_phone=display_phone,
        verified_name=verified_name,
        access_token=access_token,
        api_version=api_version,
        is_active=True,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


# ===================== Conversations & Messages =====================
def get_or_create_conversation(
    db: Session,
    team_id: int,
    contact_wa_id: str,
    contact_name: Optional[str] = None,
) -> models.Conversation:
    conv = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.team_id == team_id,
            models.Conversation.contact_wa_id == contact_wa_id,
        )
        .first()
    )
    if conv:
        if contact_name and not conv.contact_name:
            conv.contact_name = contact_name
            db.commit()
            db.refresh(conv)
        return conv

    conv = models.Conversation(
        team_id=team_id,
        contact_wa_id=contact_wa_id,
        contact_name=contact_name,
        status="open",
        last_message_at=datetime.utcnow(),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def list_conversations(db: Session, team_id: int) -> List[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(models.Conversation.team_id == team_id)
        .order_by(desc(models.Conversation.last_message_at))
        .all()
    )


def get_conversation(db: Session, team_id: int, conversation_id: int) -> Optional[models.Conversation]:
    return (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conversation_id,
            models.Conversation.team_id == team_id,
        )
        .first()
    )


def add_message(
    db: Session,
    conversation: models.Conversation,
    direction: str,
    content: str,
    message_type: str = "text",
    meta_message_id: Optional[str] = None,
    sent_by_user_id: Optional[int] = None,
    status: str = "sent",
    error_detail: Optional[str] = None,
) -> models.Message:
    msg = models.Message(
        conversation_id=conversation.id,
        direction=direction,
        content=content,
        message_type=message_type,
        meta_message_id=meta_message_id,
        sent_by_user_id=sent_by_user_id,
        status=status,
        error_detail=error_detail,
    )
    db.add(msg)
    conversation.last_message_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)
    return msg


def last_message_preview(conv: models.Conversation) -> Optional[str]:
    if not conv.messages:
        return None
    last = conv.messages[-1]
    text = last.content or ""
    return text[:80]
