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


def register_meta_account(
    db: Session,
    team: models.Team,
    registered_by: models.User,
    phone_number_id: str,
    waba_id: str,
    access_token_plaintext: str,
    display_phone: str,
    verified_name: Optional[str] = None,
    api_version: str = "v22.0",
) -> models.MetaAccount:
    """Cifra el access_token y persiste una nueva MetaAccount para el team.

    IMPORTANTE: este helper NO valida el token contra Meta Graph API — esa validación
    debe ocurrir ANTES, en el router, para que los errores del Graph API se traduzcan
    a HTTPException sanitizadas antes de llegar aquí.

    Si ya existe una MetaAccount para el team, actualiza sus campos y re-cifra el
    token. Esto permite re-conectar con credenciales nuevas sin pasar por un DELETE.

    SEGURIDAD:
    - No loguees ni imprimas access_token_plaintext.
    - El ciphertext se guarda en encrypted_access_token.
    - status='active' porque la validación externa ya ocurrió antes de llamar esto.
    """
    from .services.crypto import encrypt_secret

    encrypted = encrypt_secret(access_token_plaintext)
    now = datetime.utcnow()

    existing = get_meta_account_for_team(db, team.id)
    if existing is not None:
        existing.phone_number_id = phone_number_id
        existing.waba_id = waba_id
        existing.encrypted_access_token = encrypted
        existing.display_phone = display_phone
        existing.verified_name = verified_name
        existing.api_version = api_version
        existing.is_active = True
        existing.status = "active"
        existing.last_validated_at = now
        existing.validation_error = None
        existing.registered_by_user_id = registered_by.id
        db.commit()
        db.refresh(existing)
        return existing

    account = models.MetaAccount(
        team_id=team.id,
        phone_number_id=phone_number_id,
        waba_id=waba_id,
        encrypted_access_token=encrypted,
        display_phone=display_phone,
        verified_name=verified_name,
        api_version=api_version,
        is_active=True,
        status="active",
        last_validated_at=now,
        validation_error=None,
        registered_by_user_id=registered_by.id,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def disconnect_meta_account(db: Session, team: models.Team) -> bool:
    """Elimina la MetaAccount del team si existe.

    Retorna True si se eliminó una fila, False si no había nada que eliminar.
    """
    account = get_meta_account_for_team(db, team.id)
    if account is None:
        return False
    db.delete(account)
    db.commit()
    return True


def is_meta_account_usable(account: Optional[models.MetaAccount]) -> bool:
    """True si la cuenta existe, está activa y su status permite enviar mensajes.

    Se usa desde routers/mensajes.py para bloquear envíos con cuentas pending o
    invalidas.
    """
    if account is None:
        return False
    if not account.is_active:
        return False
    if account.status != "active":
        return False
    return True


def get_decrypted_access_token(account: models.MetaAccount) -> str:
    """Descifra el access_token al vuelo.

    IMPORTANTE: el plaintext devuelto solo debe usarse como argumento inmediato
    a una llamada HTTP (ej: header Authorization). No lo guardes en variables de
    larga vida ni lo loguees.
    """
    from .services.crypto import decrypt_secret
    return decrypt_secret(account.encrypted_access_token)


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


# ===================== Sprint 8/9: Bots =====================
import json as _json


def _parse_channels(csv_value: Optional[str]) -> List[str]:
    if not csv_value:
        return []
    return [c.strip() for c in csv_value.split(",") if c.strip()]


def _parse_config(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        data = _json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _resolve_owner_user_id(db: Session, member: models.TeamMember) -> int:
    """Sprint 9: los bots son del owner del team. Cualquier miembro del
    team los ve, pero administrativamente pertenecen al owner.

    Para el MVP (1 team por user → que es owner de sí mismo) esto devuelve
    simplemente `member.user_id`. Cuando entren agents, los bots seguirán
    colgando del owner.
    """
    team = member.team
    return team.owner_user_id if team else member.user_id


def list_bots_visible_to_member(
    db: Session, member: models.TeamMember
) -> List[models.Bot]:
    """Bots que puede ver un miembro del team: los del owner del team."""
    owner_id = _resolve_owner_user_id(db, member)
    return (
        db.query(models.Bot)
        .filter(models.Bot.user_id == owner_id)
        .order_by(desc(models.Bot.updated_at))
        .all()
    )


def get_bot_visible_to_member(
    db: Session, member: models.TeamMember, bot_id: int
) -> Optional[models.Bot]:
    """IDOR-safe: el bot debe pertenecer al owner del team del miembro."""
    owner_id = _resolve_owner_user_id(db, member)
    return (
        db.query(models.Bot)
        .filter(models.Bot.id == bot_id, models.Bot.user_id == owner_id)
        .first()
    )


def bot_to_list_item(bot: models.Bot) -> dict:
    return {
        "id": bot.id,
        "name": bot.name,
        "status": bot.status,
        "channels": _parse_channels(bot.channels),
        "trigger_type": bot.trigger_type,
        "trigger_config": _parse_config(bot.trigger_config),
        "triggered_count": bot.triggered_count,
        "completed_steps_count": bot.completed_steps_count,
        "finished_count": bot.finished_count,
        "created_at": bot.created_at,
        "updated_at": bot.updated_at,
    }


def bot_to_detail(bot: models.Bot) -> dict:
    return {
        "id": bot.id,
        "name": bot.name,
        "description": bot.description,
        "status": bot.status,
        "channels": _parse_channels(bot.channels),
        "trigger_type": bot.trigger_type,
        "trigger_config": _parse_config(bot.trigger_config),
        "triggered_count": bot.triggered_count,
        "completed_steps_count": bot.completed_steps_count,
        "finished_count": bot.finished_count,
        "created_at": bot.created_at,
        "updated_at": bot.updated_at,
        "steps": [
            {
                "id": s.id,
                "position": s.position,
                "step_type": s.step_type,
                "label": s.label,
                "config": _parse_config(s.config),
                "next_step_id": s.next_step_id,
            }
            for s in bot.steps
        ],
    }


def bot_to_export_dict(bot: models.Bot) -> dict:
    """Representación portable para el export JSON — sin métricas ni IDs internos."""
    return {
        "name": bot.name,
        "description": bot.description,
        "status": bot.status,
        "channels": _parse_channels(bot.channels),
        "trigger_type": bot.trigger_type,
        "trigger_config": _parse_config(bot.trigger_config),
        "steps": [
            {
                "position": s.position,
                "step_type": s.step_type,
                "label": s.label,
                "config": _parse_config(s.config) or {},
            }
            for s in bot.steps
        ],
    }


def create_bot_with_steps(
    db: Session,
    owner: models.User,
    *,
    name: str,
    description: Optional[str],
    channels: List[str],
    trigger_type: str = models.BOT_TRIGGER_MANUAL,
    trigger_config: Optional[dict] = None,
    steps: Optional[List[dict]] = None,
) -> models.Bot:
    """Crea un bot + pasos lineales.

    Propietario = `owner` (la cuenta dueña, Sprint 9). El `team_id` se
    completa con el team propio del owner para no romper compat.
    """
    if trigger_type not in models.AVAILABLE_BOT_TRIGGERS:
        raise ValueError(f"trigger_type inválido: {trigger_type!r}")

    channels_csv = ",".join(
        c for c in channels if c in models.AVAILABLE_BOT_CHANNELS
    ) or models.BOT_CHANNEL_WHATSAPP

    own_team = get_team_by_owner(db, owner)

    bot = models.Bot(
        user_id=owner.id,
        team_id=own_team.id if own_team else None,
        name=name,
        description=description,
        channels=channels_csv,
        trigger_type=trigger_type,
        trigger_config=_json.dumps(trigger_config) if trigger_config else None,
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)

    created_steps: List[models.BotStep] = []
    for i, raw in enumerate(steps or [], start=1):
        step_type = raw.get("step_type")
        if step_type not in models.BOT_STEP_TYPES:
            raise ValueError(f"step_type inválido: {step_type!r}")
        step = models.BotStep(
            bot_id=bot.id,
            position=i,
            step_type=step_type,
            label=raw.get("label", ""),
            config=_json.dumps(raw.get("config") or {}),
        )
        db.add(step)
        db.commit()
        db.refresh(step)
        created_steps.append(step)

    for idx in range(len(created_steps) - 1):
        created_steps[idx].next_step_id = created_steps[idx + 1].id
    if created_steps:
        db.commit()
    db.refresh(bot)
    return bot
