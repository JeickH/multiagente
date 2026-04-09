from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, EmailStr


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
class MetaAccountOut(BaseModel):
    id: int
    phone_number_id: str
    waba_id: str
    display_phone: str
    verified_name: Optional[str] = None
    api_version: str
    is_active: bool

    class Config:
        from_attributes = True


class MetaAccountStatusOut(BaseModel):
    """Estado de la cuenta de Meta para el módulo Mi Plan.

    - registered=False: el usuario no tiene cuenta de WhatsApp asignada.
    - registered=True:  devuelve display_phone y verified_name (nombre visible).
    """
    registered: bool
    display_phone: Optional[str] = None
    verified_name: Optional[str] = None
    phone_number_id: Optional[str] = None
    waba_id: Optional[str] = None
    is_active: Optional[bool] = None


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
