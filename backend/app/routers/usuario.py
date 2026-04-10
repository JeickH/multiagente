import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import schemas, models, crud
from ..database import SessionLocal
from ..dependencies import get_current_owner_membership
from ..services import meta_whatsapp
from jose import jwt, JWTError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = os.getenv('ALGORITHM')

logger = logging.getLogger(__name__)

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

    Campos del ciclo de vida (Sprint 7):
    - status / last_validated_at / validation_error: estado actual de la cuenta.
    - can_manage_meta_account: True solo si el caller es owner del team.

    Hallazgo S-20: phone_number_id y waba_id SOLO se devuelven al owner;
    los agents ven `None` en esos campos para no exponer identificadores
    sensibles de la configuración de Meta.
    """
    member = crud.get_membership_for_user(db, user)
    if member is None:
        return schemas.MetaAccountStatusOut(
            registered=False,
            can_manage_meta_account=False,
        )

    is_owner = member.role == "owner"
    account = crud.get_meta_account_for_team(db, member.team_id)
    if account is None:
        return schemas.MetaAccountStatusOut(
            registered=False,
            can_manage_meta_account=is_owner,
        )

    return schemas.MetaAccountStatusOut(
        registered=True,
        display_phone=account.display_phone,
        verified_name=account.verified_name,
        phone_number_id=account.phone_number_id if is_owner else None,
        waba_id=account.waba_id if is_owner else None,
        is_active=account.is_active,
        status=account.status,
        last_validated_at=account.last_validated_at,
        validation_error=account.validation_error,
        can_manage_meta_account=is_owner,
    )


# TODO(seguridad S-08): añadir rate limiting (5/h/user, 20/h/IP) con slowapi
@router.post(
    '/usuario/me/meta-account',
    response_model=schemas.MetaAccountStatusOut,
    status_code=200,
)
async def register_my_meta_account(
    payload: schemas.MetaAccountRegisterIn,
    member: models.TeamMember = Depends(get_current_owner_membership),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Registra/actualiza la cuenta de Meta del team del owner autenticado.

    1. Pydantic valida formato (strip, prefix EAA, longitudes).
    2. get_current_owner_membership valida que el caller es owner.
    3. Llama a Meta Graph API para validar el token contra el phone_number_id.
    4. Solo si la validación pasa, cifra y persiste.
    5. Devuelve estado sanitizado (sin el token).
    """
    api_version = os.getenv("META_API_VERSION", "v22.0")

    # Paso 3: validar contra Meta antes de persistir
    try:
        info = await meta_whatsapp.get_phone_number_info(
            phone_number_id=payload.phone_number_id,
            access_token=payload.access_token,
            api_version=api_version,
        )
    except meta_whatsapp.MetaWhatsAppError as exc:
        logger.warning(
            "Validación Meta fallida al registrar cuenta: user_id=%s team_id=%s phone_number_id=%s",
            user.id,
            member.team_id,
            payload.phone_number_id,
        )
        raise HTTPException(
            status_code=400,
            detail="No se pudo validar el token con Meta. Revisa phone_number_id, waba_id y access_token.",
        ) from exc
    except Exception as exc:
        logger.exception(
            "Error inesperado validando Meta: type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="Error temporal al contactar con el proveedor. Intenta de nuevo.",
        ) from exc

    display_phone = info.get("display_phone_number") or ""
    verified_name = info.get("verified_name") or None

    # Paso 4: cifrar y persistir
    team = db.query(models.Team).filter(models.Team.id == member.team_id).first()
    if team is None:
        logger.error(
            "Team no encontrado al registrar cuenta Meta: user_id=%s team_id=%s",
            user.id,
            member.team_id,
        )
        raise HTTPException(status_code=404, detail="Team no encontrado")

    account = crud.register_meta_account(
        db=db,
        team=team,
        registered_by=user,
        phone_number_id=payload.phone_number_id,
        waba_id=payload.waba_id,
        access_token_plaintext=payload.access_token,
        display_phone=display_phone,
        verified_name=verified_name,
        api_version=api_version,
    )

    logger.info(
        "Cuenta Meta registrada: user_id=%s team_id=%s phone_number_id=%s",
        user.id,
        team.id,
        account.phone_number_id,
    )

    return schemas.MetaAccountStatusOut(
        registered=True,
        display_phone=account.display_phone,
        verified_name=account.verified_name,
        phone_number_id=account.phone_number_id,
        waba_id=account.waba_id,
        is_active=account.is_active,
        status=account.status,
        last_validated_at=account.last_validated_at,
        validation_error=account.validation_error,
        can_manage_meta_account=True,
    )


@router.delete(
    '/usuario/me/meta-account',
    status_code=200,
)
def disconnect_my_meta_account(
    member: models.TeamMember = Depends(get_current_owner_membership),
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Elimina la cuenta de Meta del team del owner autenticado."""
    team = db.query(models.Team).filter(models.Team.id == member.team_id).first()
    if team is None:
        logger.error(
            "Team no encontrado al desconectar cuenta Meta: user_id=%s team_id=%s",
            user.id,
            member.team_id,
        )
        raise HTTPException(status_code=404, detail="Team no encontrado")

    removed = crud.disconnect_meta_account(db, team)
    logger.info(
        "Cuenta Meta %s: user_id=%s team_id=%s",
        "desconectada" if removed else "no existía",
        user.id,
        team.id,
    )
    return {"disconnected": removed}
