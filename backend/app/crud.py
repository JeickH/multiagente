from sqlalchemy.orm import Session
from . import models, schemas
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_user_by_email(db: Session, correo: str):
    return db.query(models.User).filter(models.User.correo == correo).first()

def get_user_by_documento(db: Session, documento: str):
    return db.query(models.User).filter(models.User.documento == documento).first()

def create_user(db: Session, user: schemas.UserCreate):
    hashed_password = pwd_context.hash(user.password)
    db_user = models.User(
        nombre=user.nombre,
        tipo_documento=user.tipo_documento,
        documento=user.documento,
        correo=user.correo,
        hashed_password=hashed_password
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
