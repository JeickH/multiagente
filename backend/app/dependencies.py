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
