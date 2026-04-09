from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import schemas, models, crud
from ..database import SessionLocal
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM')

router = APIRouter()
security = HTTPBearer()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
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

@router.get('/usuario/me', response_model=schemas.UserOut)
def get_me(user: models.User = Depends(get_current_user)):
    return user


@router.get('/usuario/me/meta-account', response_model=schemas.MetaAccountStatusOut)
def get_my_meta_account(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Devuelve el estado de la cuenta de Meta del usuario autenticado.

    Si el usuario no tiene team o no tiene cuenta de Meta asignada, devuelve
    `registered=False`. En caso contrario, incluye display_phone y verified_name
    (nombre visible) para mostrarse en el módulo Mi Plan.
    """
    member = crud.get_membership_for_user(db, user)
    if member is None:
        return schemas.MetaAccountStatusOut(registered=False)

    account = crud.get_meta_account_for_team(db, member.team_id)
    if account is None:
        return schemas.MetaAccountStatusOut(registered=False)

    return schemas.MetaAccountStatusOut(
        registered=True,
        display_phone=account.display_phone,
        verified_name=account.verified_name,
        phone_number_id=account.phone_number_id,
        waba_id=account.waba_id,
        is_active=account.is_active,
    )
