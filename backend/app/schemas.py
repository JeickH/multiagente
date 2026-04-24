from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ===== Users =====
class UserCreate(BaseModel):
    nombre: str
    tipo_documento: str
    documento: str
    correo: EmailStr
    password: str


class UserLogin(BaseModel):
    correo: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    nombre: str
    tipo_documento: str
    documento: str
    correo: EmailStr

    class Config:
        from_attributes = True


# ===== Teams & Permissions =====
class TeamPermissionOut(BaseModel):
    permission_key: str
    enabled: bool

    class Config:
        from_attributes = True


class TeamMemberOut(BaseModel):
    id: int
    user_id: int
    role: str
    nombre: Optional[str] = None
    correo: Optional[str] = None
    permissions: Dict[str, bool] = {}

    class Config:
        from_attributes = True


class TeamOut(BaseModel):
    id: int
    nombre: str
    owner_user_id: int

    class Config:
        from_attributes = True


class TeamMeOut(BaseModel):
    """Lo que el frontend pide para saber a qué team pertenezco y mis permisos."""
    team: TeamOut
    member: TeamMemberOut


class TeamMemberInvite(BaseModel):
    correo: EmailStr
    nombre: str
    password: str
    role: str = "agent"
    permissions: Dict[str, bool] = {}


class PermissionUpdate(BaseModel):
    permissions: Dict[str, bool]


# ===== Meta Account =====
# SEGURIDAD: este schema de salida NUNCA debe contener encrypted_access_token
# ni ningún otro secreto. extra='forbid' previene que un dev añada accidentalmente
# un campo sensible al modelo y se serialice al cliente.
class MetaAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    phone_number_id: str
    waba_id: str
    display_phone: str
    verified_name: Optional[str] = None
    api_version: str
    is_active: bool


class MetaAccountStatusOut(BaseModel):
    """Estado de la cuenta de Meta para el módulo Mi Plan.

    - registered=False: el usuario no tiene cuenta de WhatsApp asignada.
    - registered=True:  devuelve display_phone y verified_name (nombre visible).

    Campos adicionales para el flujo de conexión/validación (Sprint 7):
    - status: estado del ciclo de vida de la cuenta
      (pending/active/invalid/disconnected).
    - last_validated_at: última vez que el backend validó el token contra
      Meta Graph API.
    - validation_error: mensaje del último error de validación (si aplica).
    - can_manage_meta_account: true si el usuario actual es owner del team
      y por tanto puede conectar/desconectar la cuenta desde la UI.
    """
    registered: bool
    display_phone: Optional[str] = None
    verified_name: Optional[str] = None
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    is_active: Optional[bool] = None
    status: Optional[str] = None
    last_validated_at: Optional[datetime] = None
    validation_error: Optional[str] = None
    can_manage_meta_account: bool = False


class MetaAccountRegisterIn(BaseModel):
    """Entrada del formulario de conexión de cuenta Meta.

    El owner del team pega estos 3 datos desde la UI de Mi Plan. El backend:
    1. Valida el formato (prefix, longitud, strip).
    2. Valida el token contra Meta Graph API (GET /{phone_number_id}).
    3. Cifra el access_token con Fernet antes de persistir.

    SEGURIDAD: este schema solo se usa como INPUT. El token nunca se devuelve
    al cliente en schemas de salida.
    """
    phone_number_id: str = Field(..., min_length=5, max_length=64)
    waba_id: str = Field(..., min_length=5, max_length=64)
    access_token: str = Field(..., min_length=20, max_length=4096)

    @field_validator("phone_number_id", "waba_id")
    @classmethod
    def _strip_and_validate_id(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.isdigit():
            raise ValueError("debe ser numérico")
        return v

    @field_validator("access_token")
    @classmethod
    def _strip_and_validate_token(cls, v: str) -> str:
        v = (v or "").strip()
        if not v.startswith("EAA"):
            raise ValueError("formato de token inválido")
        return v


# ===== Conversations & Messages =====
class MessageOut(BaseModel):
    id: int
    direction: str
    content: str
    message_type: str
    meta_message_id: Optional[str] = None
    sent_by_user_id: Optional[int] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationOut(BaseModel):
    id: int
    contact_wa_id: str
    contact_name: Optional[str] = None
    status: str
    last_message_at: datetime
    last_message_preview: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationWithMessages(BaseModel):
    id: int
    contact_wa_id: str
    contact_name: Optional[str] = None
    status: str
    last_message_at: datetime
    messages: List[MessageOut] = []

    class Config:
        from_attributes = True


class MessageSendIn(BaseModel):
    """Enviar un mensaje libre dentro de una conversación existente (ventana de 24h)."""
    content: str


class NewConversationMessageIn(BaseModel):
    """Iniciar una conversación con un contacto nuevo enviando un template aprobado."""
    contact_wa_id: str           # E.164 sin +
    contact_name: Optional[str] = None
    template_name: str           # ej: "plantilla_prueba_1"
    language_code: str = "es_CO"


# ===== Sprint 8: Bots =====
class BotListItem(BaseModel):
    """Fila del listado `/bots` (cada fila de la tabla del mock)."""
    id: int
    name: str
    is_premium: bool
    status: str
    channels: List[str]                 # ["whatsapp", "instagram", ...]
    triggered_count: int
    completed_steps_count: int
    finished_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class BotStepOut(BaseModel):
    """Paso individual del diagrama de flujo (nodo)."""
    id: int
    position: int
    step_type: str
    label: str
    config: Optional[dict] = None
    next_step_id: Optional[int] = None

    class Config:
        from_attributes = True


class BotDetail(BaseModel):
    """Detalle de un bot con sus pasos ordenados para el diagrama."""
    id: int
    name: str
    description: Optional[str] = None
    is_premium: bool
    status: str
    channels: List[str]
    triggered_count: int
    completed_steps_count: int
    finished_count: int
    created_at: datetime
    updated_at: datetime
    steps: List[BotStepOut] = []

    class Config:
        from_attributes = True
