import logging
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from jose import jwt, JWTError
from dotenv import load_dotenv

from . import models, crud
from .database import SessionLocal

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

logger = logging.getLogger(__name__)

security = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> models.User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        correo: str = payload.get("sub")
        if correo is None:
            raise HTTPException(status_code=401, detail="Token inválido")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")
    user = db.query(models.User).filter(models.User.correo == correo).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    # Se revisa en CADA request y no solo al entrar: el token dura 2 horas, así
    # que sin esto una cuenta desactivada seguiría trabajando hasta que venza.
    # Es lo que convierte "desactivar" en algo inmediato.
    if not user.activo:
        raise HTTPException(status_code=401, detail="Sesión no válida")
    return user


def get_current_membership(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.TeamMember:
    member = crud.get_membership_for_user(db, user)
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no pertenece a ningún equipo",
        )
    return member


def require_permission(permission_key: str):
    def _checker(
        member: models.TeamMember = Depends(get_current_membership),
    ) -> models.TeamMember:
        if not crud.member_has_permission(member, permission_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No tienes el permiso '{permission_key}' en este equipo",
            )
        return member

    return _checker


# Cuenta oficial de Gloma: la misma que sirve el chat público de la landing.
GLOMA_EMAIL = os.getenv("GLOMA_LANDING_EMAIL", "gloma@glomabeauty.com").lower()


def require_gloma_account(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Deja pasar solo a la cuenta de Gloma (owner o miembro de su team).

    Portero de los módulos INTERNOS de Gloma (`/citas`, `/instagram`): no son
    parte del producto que se le vende a los clientes, así que cualquier otra
    cuenta recibe 403 aunque tenga sesión válida.
    """
    if (user.correo or "").lower() == GLOMA_EMAIL:
        return user

    owner = (
        db.query(models.User).filter(models.User.correo == GLOMA_EMAIL).first()
    )
    if owner is not None:
        pertenece = (
            db.query(models.TeamMember)
            .join(models.Team, models.Team.id == models.TeamMember.team_id)
            .filter(
                models.TeamMember.user_id == user.id,
                models.Team.owner_user_id == owner.id,
            )
            .first()
        )
        if pertenece is not None:
            return user

    # Sin detalle del porqué al cliente (regla de seguridad #6).
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a este módulo",
    )


def _require_account(user: models.User, db: Session, email: str) -> models.User:
    """Deja pasar al owner de `email` y a los miembros de su team; 403 al resto."""
    if (user.correo or "").lower() == email:
        return user

    owner = db.query(models.User).filter(models.User.correo == email).first()
    if owner is not None:
        pertenece = (
            db.query(models.TeamMember)
            .join(models.Team, models.Team.id == models.TeamMember.team_id)
            .filter(
                models.TeamMember.user_id == user.id,
                models.Team.owner_user_id == owner.id,
            )
            .first()
        )
        if pertenece is not None:
            return user

    # Sin detalle del porqué al cliente (regla de seguridad #6).
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes acceso a este módulo",
    )


# Sprint "Ayuda a Cali": cuenta dueña del bot de mascotas perdidas. Su panel
# (`/mascotas/panel`) es exclusivo de esta cuenta — ninguna otra lo ve.
MASCOTAS_EMAIL = os.getenv("MASCOTAS_ACCOUNT_EMAIL", "recuperatumascota@gmail.com").lower()


def require_mascotas_account(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """Portero del panel de mascotas perdidas: solo la cuenta de la iniciativa."""
    return _require_account(user, db, MASCOTAS_EMAIL)


def get_current_owner_membership(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
) -> models.TeamMember:
    """Devuelve el TeamMember del usuario autenticado si es OWNER de su team.

    Si el usuario no pertenece a ningún team, o si su rol no es 'owner', levanta
    403 con mensaje GENÉRICO ("No autorizado") para no revelar detalles al cliente.
    El detalle exacto se loggea server-side.

    NOTA (MVP): asume 1 team por usuario. En el futuro, cuando se soporte
    multi-team, este dependency debe recibir el team_id del path y validar
    ownership sobre ESE team específico (actualmente solo valida ownership
    sobre el primer team del usuario).
    """
    member = crud.get_membership_for_user(db, user)
    if member is None:
        logger.warning(
            "Intento de operación owner-only sin team: user_id=%s",
            user.id,
        )
        raise HTTPException(status_code=403, detail="No autorizado")
    if member.role != "owner":
        logger.warning(
            "Intento de operación owner-only por no-owner: user_id=%s team_id=%s role=%s",
            user.id,
            member.team_id,
            member.role,
        )
        raise HTTPException(status_code=403, detail="No autorizado")
    return member
