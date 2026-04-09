from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from .. import schemas, crud, models
from ..database import SessionLocal
from jose import jwt
import os
from datetime import timedelta, datetime
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM')
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv('ACCESS_TOKEN_EXPIRE_MINUTES', 30))

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _ensure_team_for_user(db: Session, user: models.User):
    """Crea un team + membership owner si el usuario no tiene, y provisiona
    la cuenta de Meta SOLO si el correo coincide con META_OWNER_EMAIL."""
    member = crud.get_membership_for_user(db, user)
    if member is None:
        team = crud.create_team(db, nombre=f"Equipo de {user.nombre}", owner=user)
    else:
        team = member.team
    crud.upsert_default_meta_account_for_team(db, team, owner_email=user.correo)


@router.post('/register', response_model=schemas.UserOut)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, user.correo) or crud.get_user_by_documento(db, user.documento):
        raise HTTPException(status_code=400, detail="Usuario ya registrado")
    new_user = crud.create_user(db, user)
    _ensure_team_for_user(db, new_user)
    return new_user

@router.post('/login')
def login(user: schemas.UserLogin, db: Session = Depends(get_db)):
    db_user = crud.authenticate_user(db, user.correo, user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="Credenciales incorrectas")
    # Auto-aprovisionar equipo para usuarios viejos que no tengan
    _ensure_team_for_user(db, db_user)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user.correo}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
