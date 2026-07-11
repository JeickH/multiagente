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
        "engine": getattr(bot, "engine", None) or "flow",
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
        "engine": getattr(bot, "engine", None) or "flow",
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
    engine: str = "flow",
    llm_config: Optional[dict] = None,
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
        engine=engine,
        llm_config=_json.dumps(llm_config, ensure_ascii=False) if llm_config else None,
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


# ===================== Sprint 13: Contactos + Grupos =====================
# Multi-tenant: TODA función recibe `team_id` y lo usa como filtro obligatorio.
# Nunca confiamos en IDs del cliente sin re-validar pertenencia (S13-001).

import csv as _csv
import io as _io
import logging as _logging
from sqlalchemy import or_, func as _sqlfunc

_log = _logging.getLogger(__name__)

# Tope defensivo del import CSV (S13-009). El endpoint enforcea el límite de
# 2MB de tamaño y el MIME; aquí ponemos el límite de filas para evitar abuso.
MAX_CSV_ROWS = 50000


# ----- Contactos -----

def list_contacts(
    db: Session,
    team_id: int,
    *,
    q: Optional[str] = None,
    group_id: Optional[int] = None,
    opt_in_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> List[models.Contact]:
    """Listado paginado de contactos del team con filtros opcionales.

    - `q`: busca por nombre o teléfono (ILIKE).
    - `group_id`: solo contactos miembros del grupo dado (validar antes
      que el grupo pertenece al team_id desde el router).
    - `opt_in_only`: True para excluir opt_in=False.
    """
    query = db.query(models.Contact).filter(models.Contact.team_id == team_id)

    if opt_in_only:
        query = query.filter(models.Contact.opt_in.is_(True))

    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                models.Contact.name.ilike(like),
                models.Contact.phone_e164.ilike(like),
            )
        )

    if group_id is not None:
        query = query.join(
            models.ContactGroupMember,
            models.ContactGroupMember.contact_id == models.Contact.id,
        ).filter(models.ContactGroupMember.group_id == group_id)

    return (
        query.order_by(desc(models.Contact.updated_at))
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )


def get_contact(
    db: Session, team_id: int, contact_id: int
) -> Optional[models.Contact]:
    """Devuelve el contacto SOLO si pertenece al team. S13-001 anti-IDOR.

    El router debe responder 404 si esto retorna None (no 403, no revelamos
    existencia de IDs ajenos).
    """
    return (
        db.query(models.Contact)
        .filter(
            models.Contact.id == contact_id,
            models.Contact.team_id == team_id,
        )
        .first()
    )


def _contact_attrs_dict(attrs) -> dict:
    if attrs is None:
        return {}
    if isinstance(attrs, dict):
        return attrs
    return {}


def create_contact(
    db: Session, team_id: int, payload: schemas.ContactCreate
) -> tuple[models.Contact, bool]:
    """Crea o actualiza (upsert) por (team_id, phone_e164).

    Retorna (contact, created) donde `created=True` si fue insert nuevo,
    `False` si fue update de uno existente. La unicidad la garantiza el
    constraint `uq_contacts_team_phone`.
    """
    existing = (
        db.query(models.Contact)
        .filter(
            models.Contact.team_id == team_id,
            models.Contact.phone_e164 == payload.phone_e164,
        )
        .first()
    )
    if existing is not None:
        if payload.name is not None:
            existing.name = payload.name
        if payload.email is not None:
            existing.email = payload.email
        if payload.attributes is not None:
            existing.attributes = _contact_attrs_dict(payload.attributes)
        if payload.opt_in is not None:
            existing.opt_in = bool(payload.opt_in)
        if payload.opt_in_source is not None:
            existing.opt_in_source = payload.opt_in_source
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing, False

    contact = models.Contact(
        team_id=team_id,
        phone_e164=payload.phone_e164,
        name=payload.name,
        email=payload.email,
        attributes=_contact_attrs_dict(payload.attributes),
        opt_in=True if payload.opt_in is None else bool(payload.opt_in),
        opt_in_source=payload.opt_in_source,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact, True


def update_contact(
    db: Session, team_id: int, contact_id: int, payload: schemas.ContactUpdate
) -> Optional[models.Contact]:
    contact = get_contact(db, team_id, contact_id)
    if contact is None:
        return None
    if payload.name is not None:
        contact.name = payload.name
    if payload.email is not None:
        contact.email = payload.email
    if payload.attributes is not None:
        contact.attributes = _contact_attrs_dict(payload.attributes)
    if payload.opt_in is not None:
        contact.opt_in = bool(payload.opt_in)
    if payload.opt_in_source is not None:
        contact.opt_in_source = payload.opt_in_source
    contact.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(contact)
    return contact


def delete_contact(db: Session, team_id: int, contact_id: int) -> bool:
    contact = get_contact(db, team_id, contact_id)
    if contact is None:
        return False
    db.delete(contact)
    db.commit()
    return True


def import_contacts_csv(
    db: Session, team_id: int, csv_text: str
) -> schemas.ContactBulkImportResult:
    """Parsea un CSV y hace upsert masivo por (team_id, phone_e164).

    Columnas reconocidas (header-insensitive a mayúsculas):
      - `phone_e164` (obligatoria)
      - `name`, `email`, `opt_in`, `opt_in_source` (opcionales)

    SEGURIDAD (regla 1, S13-009): los mensajes de error NUNCA contienen el
    teléfono ni el row crudo, solo `fila N: motivo`. El contenido del CSV
    nunca se loguea. Aborta si excede MAX_CSV_ROWS.
    """
    total = 0
    created = 0
    updated = 0
    skipped = 0
    errors: List[str] = []

    try:
        reader = _csv.DictReader(_io.StringIO(csv_text))
    except Exception:
        _log.exception("import_contacts_csv: error abriendo DictReader (team_id=%s)", team_id)
        return schemas.ContactBulkImportResult(
            total=0, created=0, updated=0, skipped=0,
            errors=["No se pudo leer el archivo CSV."],
        )

    # Normaliza headers a lower-case sin espacios.
    if reader.fieldnames:
        reader.fieldnames = [(h or "").strip().lower() for h in reader.fieldnames]
    if not reader.fieldnames or "phone_e164" not in reader.fieldnames:
        return schemas.ContactBulkImportResult(
            total=0, created=0, updated=0, skipped=0,
            errors=["El CSV debe incluir la columna 'phone_e164'."],
        )

    for idx, row in enumerate(reader, start=2):  # fila 1 = header
        total += 1
        if total > MAX_CSV_ROWS:
            errors.append(
                f"El archivo excede el máximo de {MAX_CSV_ROWS} filas; importación abortada."
            )
            break

        phone = (row.get("phone_e164") or "").strip()
        if not phone:
            skipped += 1
            errors.append(f"fila {idx}: phone_e164 vacío")
            continue

        # Validación E.164 antes de tocar BD (mensaje genérico, sin PII).
        try:
            payload = schemas.ContactCreate(
                phone_e164=phone,
                name=(row.get("name") or "").strip() or None,
                email=(row.get("email") or "").strip() or None,
                opt_in=_parse_csv_bool(row.get("opt_in")),
                opt_in_source=(row.get("opt_in_source") or "").strip() or "import_csv",
            )
        except Exception:
            skipped += 1
            errors.append(f"fila {idx}: datos inválidos")
            continue

        try:
            _, was_created = create_contact(db, team_id, payload)
            if was_created:
                created += 1
            else:
                updated += 1
        except Exception:
            # NO incluir teléfono ni payload en logs/respuesta.
            _log.exception(
                "import_contacts_csv: error persistiendo fila (team_id=%s, fila=%s)",
                team_id,
                idx,
            )
            skipped += 1
            errors.append(f"fila {idx}: error al guardar")

    return schemas.ContactBulkImportResult(
        total=total,
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )


def _parse_csv_bool(raw) -> Optional[bool]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in ("", "null", "none"):
        return None
    if s in ("1", "true", "t", "yes", "y", "si", "sí"):
        return True
    if s in ("0", "false", "f", "no", "n"):
        return False
    return None


# ----- Grupos de contactos -----

def list_contact_groups(db: Session, team_id: int) -> List[tuple]:
    """Devuelve lista de tuplas (ContactGroup, member_count)."""
    rows = (
        db.query(
            models.ContactGroup,
            _sqlfunc.count(models.ContactGroupMember.contact_id).label("member_count"),
        )
        .outerjoin(
            models.ContactGroupMember,
            models.ContactGroupMember.group_id == models.ContactGroup.id,
        )
        .filter(models.ContactGroup.team_id == team_id)
        .group_by(models.ContactGroup.id)
        .order_by(models.ContactGroup.name.asc())
        .all()
    )
    return rows


def get_contact_group(
    db: Session, team_id: int, group_id: int
) -> Optional[models.ContactGroup]:
    """S13-001: solo retorna grupo si pertenece al team."""
    return (
        db.query(models.ContactGroup)
        .filter(
            models.ContactGroup.id == group_id,
            models.ContactGroup.team_id == team_id,
        )
        .first()
    )


def get_contact_group_with_count(
    db: Session, team_id: int, group_id: int
) -> Optional[tuple]:
    """(group, count) para el endpoint de detalle."""
    row = (
        db.query(
            models.ContactGroup,
            _sqlfunc.count(models.ContactGroupMember.contact_id).label("member_count"),
        )
        .outerjoin(
            models.ContactGroupMember,
            models.ContactGroupMember.group_id == models.ContactGroup.id,
        )
        .filter(
            models.ContactGroup.id == group_id,
            models.ContactGroup.team_id == team_id,
        )
        .group_by(models.ContactGroup.id)
        .first()
    )
    return row


def create_contact_group(
    db: Session, team_id: int, payload: schemas.ContactGroupCreate
) -> models.ContactGroup:
    group = models.ContactGroup(
        team_id=team_id,
        name=payload.name.strip(),
        description=payload.description,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def update_contact_group(
    db: Session, team_id: int, group_id: int, payload: schemas.ContactGroupUpdate
) -> Optional[models.ContactGroup]:
    group = get_contact_group(db, team_id, group_id)
    if group is None:
        return None
    if payload.name is not None:
        group.name = payload.name.strip()
    if payload.description is not None:
        group.description = payload.description
    db.commit()
    db.refresh(group)
    return group


def delete_contact_group(db: Session, team_id: int, group_id: int) -> bool:
    group = get_contact_group(db, team_id, group_id)
    if group is None:
        return False
    db.delete(group)
    db.commit()
    return True


def add_group_members(
    db: Session, team_id: int, group_id: int, contact_ids: List[int]
) -> tuple[Optional[models.ContactGroup], int, List[int]]:
    """Añade contactos al grupo.

    S13-001: valida que (a) el grupo pertenece al team, (b) TODOS los
    contact_ids pertenecen al team. Si alguno no pertenece, NO se hace
    ningún insert y retorna la lista de IDs inválidos (el router responde 404
    sin revelar cuáles eran reales y cuáles no).

    Retorna: (group, added_count, invalid_ids). Si group es None → el grupo
    no pertenece al team (404 desde el router).
    """
    group = get_contact_group(db, team_id, group_id)
    if group is None:
        return None, 0, []

    unique_ids = list({int(cid) for cid in contact_ids})
    if not unique_ids:
        return group, 0, []

    # Validar que TODOS los contact_ids pertenecen al team.
    owned = (
        db.query(models.Contact.id)
        .filter(
            models.Contact.team_id == team_id,
            models.Contact.id.in_(unique_ids),
        )
        .all()
    )
    owned_ids = {row[0] for row in owned}
    invalid = [cid for cid in unique_ids if cid not in owned_ids]
    if invalid:
        return group, 0, invalid

    # Insertar los que aún no son miembros. ON CONFLICT DO NOTHING vía check previo.
    existing = (
        db.query(models.ContactGroupMember.contact_id)
        .filter(
            models.ContactGroupMember.group_id == group_id,
            models.ContactGroupMember.contact_id.in_(unique_ids),
        )
        .all()
    )
    existing_set = {row[0] for row in existing}
    added = 0
    for cid in unique_ids:
        if cid in existing_set:
            continue
        db.add(
            models.ContactGroupMember(
                group_id=group_id,
                contact_id=cid,
            )
        )
        added += 1
    db.commit()
    return group, added, []


def remove_group_member(
    db: Session, team_id: int, group_id: int, contact_id: int
) -> bool:
    """S13-001: valida grupo y contacto pertenecen al team antes de borrar."""
    group = get_contact_group(db, team_id, group_id)
    if group is None:
        return False
    contact = get_contact(db, team_id, contact_id)
    if contact is None:
        return False
    member = (
        db.query(models.ContactGroupMember)
        .filter(
            models.ContactGroupMember.group_id == group_id,
            models.ContactGroupMember.contact_id == contact_id,
        )
        .first()
    )
    if member is None:
        return False
    db.delete(member)
    db.commit()
    return True


# ─── Sprint 13 / templates ────────────────────────────────────────────────
# CRUD para WhatsappTemplate. SIEMPRE filtran por `meta_account_id`. El
# router es responsable de validar que el meta_account pertenezca al team
# del usuario antes de llamar a estos helpers (S13-001 anti-IDOR).


def list_templates(
    db: Session,
    meta_account_id: int,
    status_filter: Optional[str] = None,
) -> List[models.WhatsappTemplate]:
    q = db.query(models.WhatsappTemplate).filter(
        models.WhatsappTemplate.meta_account_id == meta_account_id
    )
    if status_filter:
        q = q.filter(models.WhatsappTemplate.status == status_filter)
    return q.order_by(desc(models.WhatsappTemplate.created_at)).all()


def get_template(
    db: Session, meta_account_id: int, template_id: int
) -> Optional[models.WhatsappTemplate]:
    """Lookup escoped por meta_account_id. Devuelve None si no pertenece (S13-001)."""
    return (
        db.query(models.WhatsappTemplate)
        .filter(
            models.WhatsappTemplate.id == template_id,
            models.WhatsappTemplate.meta_account_id == meta_account_id,
        )
        .first()
    )


def get_template_by_name_lang(
    db: Session, meta_account_id: int, name: str, language: str
) -> Optional[models.WhatsappTemplate]:
    return (
        db.query(models.WhatsappTemplate)
        .filter(
            models.WhatsappTemplate.meta_account_id == meta_account_id,
            models.WhatsappTemplate.name == name,
            models.WhatsappTemplate.language == language,
        )
        .first()
    )


def upsert_template_from_meta(
    db: Session,
    meta_account_id: int,
    *,
    meta_template_id: Optional[str],
    name: str,
    category: Optional[str],
    language: str,
    status: str,
    components_json: dict,
    rejection_reason: Optional[str],
) -> tuple[models.WhatsappTemplate, bool]:
    """Upsert por (meta_account_id, name, language). Devuelve (template, created)."""
    existing = get_template_by_name_lang(db, meta_account_id, name, language)
    now = datetime.utcnow()
    if existing is None:
        tpl = models.WhatsappTemplate(
            meta_account_id=meta_account_id,
            meta_template_id=meta_template_id,
            name=name,
            category=category,
            language=language,
            status=status,
            components_json=components_json or {},
            rejection_reason=rejection_reason,
            last_synced_at=now,
        )
        db.add(tpl)
        db.commit()
        db.refresh(tpl)
        return tpl, True

    existing.meta_template_id = meta_template_id or existing.meta_template_id
    existing.category = category
    existing.status = status
    existing.components_json = components_json or {}
    existing.rejection_reason = rejection_reason
    existing.last_synced_at = now
    db.commit()
    db.refresh(existing)
    return existing, False


def mark_template_deleted_upstream(
    db: Session, template: models.WhatsappTemplate
) -> None:
    """Marca como DELETED (no DELETE físico — preserva FK desde campaigns)."""
    template.status = "DELETED"
    template.last_synced_at = datetime.utcnow()
    db.commit()


def create_template_pending(
    db: Session,
    meta_account_id: int,
    *,
    name: str,
    category: str,
    language: str,
    components_json: dict,
    meta_template_id: Optional[str] = None,
) -> models.WhatsappTemplate:
    """Persiste una plantilla nueva en estado PENDING (post-POST a Meta o sandbox)."""
    tpl = models.WhatsappTemplate(
        meta_account_id=meta_account_id,
        meta_template_id=meta_template_id,
        name=name,
        category=category,
        language=language,
        status="PENDING",
        components_json=components_json or {},
        last_synced_at=datetime.utcnow(),
    )
    db.add(tpl)
    db.commit()
    db.refresh(tpl)
    return tpl


# ─── Sprint 13 / campaigns ────────────────────────────────────────────────
# CRUD para Campaign / CampaignRecipient / CampaignEvent. Mitigaciones:
#   - S13-001 anti-IDOR: cada función recibe `team_id` y lo usa como filtro
#     en TODAS las queries. Validación cruzada template↔meta_account↔team
#     dentro de `create_campaign`.
#   - S13-002 anti-abuso: `MAX_RECIPIENTS_PER_CAMPAIGN` constante; 422 si
#     `len(contact_ids) > MAX`.
#   - S13-003 opt-in fail-closed: contactos con `opt_in=False` se persisten
#     como `status='skipped', error_code='opt_out_at_enqueue'`.

from fastapi import HTTPException as _HTTPException
from sqlalchemy import and_ as _and, text as _text

# Re-export para que el router pueda usar la constante.
MAX_RECIPIENTS_PER_CAMPAIGN = schemas.MAX_RECIPIENTS_PER_CAMPAIGN


def _campaign_kpis_query(db: Session, campaign_ids: List[int]) -> Dict[int, dict]:
    """Devuelve {campaign_id: {total_recipients, sent, delivered, read, failed,
    pending, skipped}} para los IDs dados. Una sola query con agregaciones
    `FILTER (WHERE ...)` (PostgreSQL) — coincide con §3.2 del schema.
    """
    if not campaign_ids:
        return {}
    sql = _text(
        """
        SELECT
            campaign_id,
            COUNT(*)                                                         AS total_recipients,
            COUNT(*) FILTER (WHERE status IN ('sent','delivered','read'))    AS sent,
            COUNT(*) FILTER (WHERE status IN ('delivered','read'))           AS delivered,
            COUNT(*) FILTER (WHERE status = 'read')                          AS read_count,
            COUNT(*) FILTER (WHERE status = 'failed')                        AS failed,
            COUNT(*) FILTER (WHERE status IN ('queued','sending'))           AS pending,
            COUNT(*) FILTER (WHERE status = 'skipped')                       AS skipped
        FROM campaign_recipients
        WHERE campaign_id = ANY(:ids)
        GROUP BY campaign_id
        """
    )
    rows = db.execute(sql, {"ids": campaign_ids}).mappings().all()
    out: Dict[int, dict] = {}
    for r in rows:
        out[int(r["campaign_id"])] = {
            "total_recipients": int(r["total_recipients"] or 0),
            "sent": int(r["sent"] or 0),
            "delivered": int(r["delivered"] or 0),
            "read": int(r["read_count"] or 0),
            "failed": int(r["failed"] or 0),
            "pending": int(r["pending"] or 0),
            "skipped": int(r["skipped"] or 0),
        }
    return out


def _campaign_event_counts(db: Session, campaign_id: int) -> Dict[str, int]:
    """{event_type: count} para una campaña."""
    sql = _text(
        """
        SELECT event_type, COUNT(*) AS cnt
        FROM campaign_events
        WHERE campaign_id = :cid
        GROUP BY event_type
        """
    )
    rows = db.execute(sql, {"cid": campaign_id}).mappings().all()
    return {r["event_type"]: int(r["cnt"] or 0) for r in rows}


def _resolve_recipient_contact_ids(
    db: Session, team_id: int, recipients: schemas.CampaignRecipientsIn
) -> List[int]:
    """Resuelve la lista final de `contact_id`s para una nueva campaña.

    - mode='individual': valida que TODOS los IDs pertenezcan al team.
      Si algún ID es ajeno, levanta 404 (S13-001).
    - mode='group': resuelve el grupo del team y expande sus miembros.
      404 si grupo no pertenece al team.
    """
    if recipients.mode == "individual":
        raw_ids = recipients.contact_ids or []
        # S13-002 anti-abuso: validar tope ANTES de cualquier query a BD.
        # Esto previene un atacante que envía 1M de IDs random gastando CPU.
        if len(raw_ids) > MAX_RECIPIENTS_PER_CAMPAIGN:
            raise _HTTPException(
                status_code=422,
                detail=(
                    f"La campaña excede el máximo permitido de "
                    f"{MAX_RECIPIENTS_PER_CAMPAIGN} destinatarios."
                ),
            )
        contact_ids = list({int(x) for x in raw_ids})
        if not contact_ids:
            raise _HTTPException(
                status_code=422,
                detail="Debes incluir al menos un contacto.",
            )
        owned = (
            db.query(models.Contact.id)
            .filter(
                models.Contact.team_id == team_id,
                models.Contact.id.in_(contact_ids),
            )
            .all()
        )
        owned_ids = {row[0] for row in owned}
        if len(owned_ids) != len(contact_ids):
            # Algún ID no pertenece al team → 404 genérico (S13-001).
            raise _HTTPException(
                status_code=404,
                detail="Uno o más contactos no fueron encontrados",
            )
        return list(owned_ids)

    if recipients.mode == "group":
        if not recipients.contact_group_id:
            raise _HTTPException(
                status_code=422,
                detail="Debes indicar un grupo de contactos.",
            )
        group = get_contact_group(db, team_id, int(recipients.contact_group_id))
        if group is None:
            raise _HTTPException(status_code=404, detail="Grupo no encontrado")
        rows = (
            db.query(models.ContactGroupMember.contact_id)
            .filter(models.ContactGroupMember.group_id == group.id)
            .all()
        )
        return [int(r[0]) for r in rows]

    # No debería pasar (Pydantic lo valida), pero defensa.
    raise _HTTPException(status_code=422, detail="Modo de destinatarios inválido.")


def _build_campaign_detail_out(
    db: Session, campaign: models.Campaign, preview_limit: int = 20
) -> "schemas.CampaignDetailOut":
    """Construye un `CampaignDetailOut` a partir de un Campaign ya cargado."""
    kpis = _campaign_kpis_query(db, [campaign.id]).get(campaign.id, {})
    preview = (
        db.query(models.CampaignRecipient)
        .filter(models.CampaignRecipient.campaign_id == campaign.id)
        .order_by(models.CampaignRecipient.id.asc())
        .limit(preview_limit)
        .all()
    )
    event_counts = _campaign_event_counts(db, campaign.id)

    tpl = campaign.template
    return schemas.CampaignDetailOut(
        id=campaign.id,
        name=campaign.name,
        status=campaign.status,
        meta_account_id=campaign.meta_account_id,
        template_id=campaign.template_id,
        scheduled_at=campaign.scheduled_at,
        started_at=campaign.started_at,
        completed_at=campaign.completed_at,
        created_at=campaign.created_at,
        total_recipients=kpis.get("total_recipients", 0),
        sent=kpis.get("sent", 0),
        delivered=kpis.get("delivered", 0),
        read=kpis.get("read", 0),
        failed=kpis.get("failed", 0),
        pending=kpis.get("pending", 0),
        skipped=kpis.get("skipped", 0),
        template_name=tpl.name if tpl else None,
        template_language=tpl.language if tpl else None,
        template_variables_json=(campaign.template_variables_json or {}),
        recipients_preview=[
            schemas.CampaignRecipientOut.model_validate(r) for r in preview
        ],
        kpis_by_event_type=event_counts,
    )


def create_campaign(
    db: Session,
    team_id: int,
    current_user_id: int,
    payload: schemas.CampaignCreate,
) -> schemas.CampaignDetailOut:
    """Crea una campaña + sus recipients.

    Validaciones (en orden):
      1. Resolver `template` por `template_id` filtrando por meta_account.
         404 si no pertenece al team (S13-001).
      2. Validar `template.status == 'APPROVED'`.
      3. Resolver `meta_account` del team; matchear con
         `payload.meta_account_id` y con `template.meta_account_id`.
      4. Resolver `contact_ids` (modo individual o group), validar ownership.
      5. Tope `len(contact_ids) <= MAX_RECIPIENTS_PER_CAMPAIGN` (S13-002).
      6. Crear Campaign + Recipients (filtrar opt_in fail-closed S13-003) +
         CampaignEvent inicial `queued`.
      7. Estado inicial: `scheduled` (si hay `scheduled_at` futuro) o
         `scheduled` también si NULL/pasado (lo recoge el sender tick).

    Retorna `CampaignDetailOut` ya hidratado.
    """
    # 1) Resolver meta_account del team.
    meta_account = get_meta_account_for_team(db, team_id)
    if meta_account is None:
        raise _HTTPException(
            status_code=404, detail="Cuenta de WhatsApp no encontrada"
        )

    # S13-001: el meta_account_id del payload DEBE coincidir con el del team.
    if int(payload.meta_account_id) != int(meta_account.id):
        raise _HTTPException(status_code=404, detail="Plantilla no encontrada")

    # 2) Resolver template y validar pertenencia a meta_account + APPROVED.
    template = get_template(db, meta_account.id, payload.template_id)
    if template is None:
        raise _HTTPException(status_code=404, detail="Plantilla no encontrada")
    if int(template.meta_account_id) != int(meta_account.id):
        # Defensa-en-profundidad (get_template ya filtra).
        raise _HTTPException(status_code=404, detail="Plantilla no encontrada")
    if template.status != "APPROVED":
        raise _HTTPException(
            status_code=400,
            detail="La plantilla aún no está aprobada por Meta.",
        )

    # 3) Resolver lista de contact_ids.
    contact_ids = _resolve_recipient_contact_ids(db, team_id, payload.recipients)

    # 4) Tope anti-abuso (S13-002).
    if len(contact_ids) > MAX_RECIPIENTS_PER_CAMPAIGN:
        raise _HTTPException(
            status_code=422,
            detail=(
                f"La campaña excede el máximo permitido de "
                f"{MAX_RECIPIENTS_PER_CAMPAIGN} destinatarios."
            ),
        )
    if not contact_ids:
        raise _HTTPException(
            status_code=422,
            detail="La campaña no tiene destinatarios.",
        )

    # 5) Determinar status inicial. scheduled_at NULL o pasado → 'scheduled'
    # (el sender lo recoge en el tick siguiente). scheduled_at futuro →
    # también 'scheduled' (mismo flujo; el sender filtra por scheduled_at).
    now = datetime.utcnow()
    initial_status = models.CAMPAIGN_STATUS_SCHEDULED

    # 6) Crear Campaign.
    campaign = models.Campaign(
        team_id=team_id,
        meta_account_id=meta_account.id,
        template_id=template.id,
        name=payload.name.strip(),
        status=initial_status,
        scheduled_at=payload.scheduled_at,
        template_variables_json=payload.template_variables_json or {},
        created_by_user_id=current_user_id,
    )
    db.add(campaign)
    db.flush()  # obtener id sin commit aún

    # 7) Cargar contactos con su opt_in para fail-closed (S13-003).
    contacts_rows = (
        db.query(models.Contact)
        .filter(
            models.Contact.team_id == team_id,
            models.Contact.id.in_(contact_ids),
        )
        .all()
    )
    queued_count = 0
    skipped_count = 0
    for ct in contacts_rows:
        if not ct.opt_in:
            # S13-003: NO se envía. Persistimos como `skipped` con error_code.
            recipient = models.CampaignRecipient(
                campaign_id=campaign.id,
                contact_id=ct.id,
                phone_e164=ct.phone_e164,
                status=models.CR_STATUS_SKIPPED,
                error_code="opt_out_at_enqueue",
            )
            skipped_count += 1
        else:
            recipient = models.CampaignRecipient(
                campaign_id=campaign.id,
                contact_id=ct.id,
                phone_e164=ct.phone_e164,
                status=models.CR_STATUS_QUEUED,
            )
            queued_count += 1
        db.add(recipient)

    # 8) Insertar evento `queued` a nivel campaña.
    event = models.CampaignEvent(
        campaign_id=campaign.id,
        recipient_id=None,
        event_type="queued",
        payload_json={
            "queued": queued_count,
            "skipped_opt_out": skipped_count,
        },
    )
    db.add(event)

    db.commit()
    db.refresh(campaign)

    return _build_campaign_detail_out(db, campaign)


def list_campaigns(
    db: Session,
    team_id: int,
    *,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[schemas.CampaignOut]:
    """Listado paginado con KPIs agregados (1 query de campañas + 1 query
    agregada de recipients). Coincide con §3.2 del schema."""
    q = db.query(models.Campaign).filter(models.Campaign.team_id == team_id)
    if status_filter:
        q = q.filter(models.Campaign.status == status_filter)
    rows = (
        q.order_by(desc(models.Campaign.created_at))
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    if not rows:
        return []
    ids = [c.id for c in rows]
    kpis = _campaign_kpis_query(db, ids)
    out: List[schemas.CampaignOut] = []
    for c in rows:
        k = kpis.get(c.id, {})
        out.append(
            schemas.CampaignOut(
                id=c.id,
                name=c.name,
                status=c.status,
                meta_account_id=c.meta_account_id,
                template_id=c.template_id,
                scheduled_at=c.scheduled_at,
                started_at=c.started_at,
                completed_at=c.completed_at,
                created_at=c.created_at,
                total_recipients=k.get("total_recipients", 0),
                sent=k.get("sent", 0),
                delivered=k.get("delivered", 0),
                read=k.get("read", 0),
                failed=k.get("failed", 0),
                pending=k.get("pending", 0),
                skipped=k.get("skipped", 0),
            )
        )
    return out


def get_campaign(
    db: Session, team_id: int, campaign_id: int
) -> Optional[models.Campaign]:
    """S13-001: 404 (en el router) si no pertenece al team."""
    return (
        db.query(models.Campaign)
        .filter(
            models.Campaign.id == campaign_id,
            models.Campaign.team_id == team_id,
        )
        .first()
    )


def list_campaign_recipients(
    db: Session, team_id: int, campaign_id: int, *, limit: int = 50, offset: int = 0
) -> Optional[tuple[int, List[models.CampaignRecipient]]]:
    """Lista paginada de recipients. Retorna None si la campaña no
    pertenece al team (S13-001)."""
    campaign = get_campaign(db, team_id, campaign_id)
    if campaign is None:
        return None
    total = (
        db.query(_sqlfunc.count(models.CampaignRecipient.id))
        .filter(models.CampaignRecipient.campaign_id == campaign_id)
        .scalar()
    )
    items = (
        db.query(models.CampaignRecipient)
        .filter(models.CampaignRecipient.campaign_id == campaign_id)
        .order_by(models.CampaignRecipient.id.asc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return int(total or 0), items


def campaign_kpis_global(
    db: Session,
    team_id: int,
    *,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> schemas.CampaignsGlobalKPIs:
    """KPIs agregados de todas las campañas del team. §3.1 del schema."""
    params = {"team_id": team_id}
    where_extra = ""
    if date_from is not None:
        where_extra += " AND c.created_at >= :date_from"
        params["date_from"] = date_from
    if date_to is not None:
        where_extra += " AND c.created_at <  :date_to"
        params["date_to"] = date_to

    sql = _text(
        f"""
        SELECT
            COUNT(DISTINCT c.id)                                              AS total_campaigns,
            COUNT(cr.id)                                                      AS total_recipients,
            COUNT(*) FILTER (WHERE cr.status IN ('sent','delivered','read'))  AS sent_count,
            COUNT(*) FILTER (WHERE cr.status IN ('delivered','read'))         AS delivered_count,
            COUNT(*) FILTER (WHERE cr.status = 'read')                        AS read_count,
            COUNT(*) FILTER (WHERE cr.status = 'failed')                      AS failed_count,
            COUNT(*) FILTER (WHERE cr.status = 'queued')                      AS queued_count,
            COUNT(*) FILTER (WHERE cr.status = 'skipped')                     AS skipped_count,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE cr.status IN ('delivered','read'))::numeric
                / NULLIF(COUNT(*) FILTER (WHERE cr.status IN ('sent','delivered','read')), 0),
                2
            )                                                                 AS delivery_rate_pct,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE cr.status = 'read')::numeric
                / NULLIF(COUNT(*) FILTER (WHERE cr.status IN ('delivered','read')), 0),
                2
            )                                                                 AS read_rate_pct
        FROM campaigns c
        LEFT JOIN campaign_recipients cr ON cr.campaign_id = c.id
        WHERE c.team_id = :team_id
          {where_extra}
        """
    )
    row = db.execute(sql, params).mappings().first()
    if row is None:
        return schemas.CampaignsGlobalKPIs()
    return schemas.CampaignsGlobalKPIs(
        total_campaigns=int(row["total_campaigns"] or 0),
        total_recipients=int(row["total_recipients"] or 0),
        sent_count=int(row["sent_count"] or 0),
        delivered_count=int(row["delivered_count"] or 0),
        read_count=int(row["read_count"] or 0),
        failed_count=int(row["failed_count"] or 0),
        queued_count=int(row["queued_count"] or 0),
        skipped_count=int(row["skipped_count"] or 0),
        delivery_rate_pct=(
            float(row["delivery_rate_pct"]) if row["delivery_rate_pct"] is not None else None
        ),
        read_rate_pct=(
            float(row["read_rate_pct"]) if row["read_rate_pct"] is not None else None
        ),
    )


def cancel_campaign(
    db: Session, team_id: int, campaign_id: int
) -> tuple[str, Optional[models.Campaign]]:
    """Transiciona la campaña a `cancelled`.

    Retorna:
      - ('not_found', None) si no pertenece al team.
      - ('conflict', None) si está `running` o `completed` (no se puede cancelar).
      - ('ok', campaign) si se cancela.
    """
    campaign = get_campaign(db, team_id, campaign_id)
    if campaign is None:
        return "not_found", None
    if campaign.status in (
        models.CAMPAIGN_STATUS_RUNNING,
        models.CAMPAIGN_STATUS_COMPLETED,
        models.CAMPAIGN_STATUS_CANCELLED,
    ):
        return "conflict", None
    campaign.status = models.CAMPAIGN_STATUS_CANCELLED
    campaign.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(campaign)
    return "ok", campaign


def build_campaign_detail_out(
    db: Session, campaign: models.Campaign
) -> schemas.CampaignDetailOut:
    """Wrapper público sobre `_build_campaign_detail_out` (para el router)."""
    return _build_campaign_detail_out(db, campaign)
