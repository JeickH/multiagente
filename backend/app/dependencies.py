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
