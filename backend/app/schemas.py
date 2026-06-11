from datetime import datetime
from typing import Optional, List, Dict, Any
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


# ===== Tutoriales interactivos (Sprint 15) =====
ALLOWED_TUTORIAL_MODULES = {"mi_plan", "mensajes", "bots", "campanas"}


class TutorialStateOut(BaseModel):
    done: bool = False
    skipped: bool = False
    completed_at: Optional[str] = None


class TutorialsOut(BaseModel):
    """Estado de los tutoriales del usuario autenticado por módulo.

    Llaves: mi_plan, mensajes, bots, campanas (whitelist).
    Si una llave no está presente significa que el usuario NUNCA hizo
    ese tutorial → el frontend debe mostrarlo.
    """
    tutorials: Dict[str, TutorialStateOut]


class TutorialUpdateIn(BaseModel):
    done: bool = True
    skipped: bool = False

    model_config = ConfigDict(extra="forbid")


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
    assigned_to: str = "bot"
    last_message_at: datetime
    last_message_preview: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationWithMessages(BaseModel):
    id: int
    contact_wa_id: str
    contact_name: Optional[str] = None
    status: str
    assigned_to: str = "bot"
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


# ===== Sprint 8/9: Bots =====
class BotListItem(BaseModel):
    """Fila del listado `/bots`."""
    id: int
    name: str
    status: str
    channels: List[str]                 # ["whatsapp", "instagram", ...]
    trigger_type: str                   # 'default' | 'keyword' | 'manual'
    trigger_config: Optional[dict] = None
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
    status: str
    channels: List[str]
    trigger_type: str
    trigger_config: Optional[dict] = None
    triggered_count: int
    completed_steps_count: int
    finished_count: int
    created_at: datetime
    updated_at: datetime
    steps: List[BotStepOut] = []

    class Config:
        from_attributes = True


class BotSimulateIn(BaseModel):
    """Input para el endpoint de simulación del bot.

    El estado lo mantiene el cliente (frontend): en el primer turno envía
    `state=None` y `user_input=None`; en turnos siguientes envía el
    `next_state` que recibió del turno anterior más el `user_input`
    (si el paso previo pidió uno).
    """
    state: Optional[dict] = None        # {"current_step_id": int, "variables": {...}}
    user_input: Optional[str] = None


class BotAction(BaseModel):
    """Acción individual que el motor pide al cliente (pintar en el chat)."""
    type: str   # 'say' | 'say_media' | 'ask' | 'pause' | 'end'
    payload: dict = {}


class BotSimulateOut(BaseModel):
    """Output del endpoint de simulación."""
    actions: List[BotAction] = []
    next_state: Optional[dict] = None
    finished: bool = False


# ===== Sprint 13: Contactos + Grupos =====
import re as _re

# Reproduce CHECK ck_contacts_phone_e164 del DDL: + seguido de 7..19 dígitos,
# primer dígito no cero (E.164). Defensa en profundidad además del CHECK SQL.
_E164_RE = _re.compile(r"^\+[1-9][0-9]{6,18}$")


class ContactCreate(BaseModel):
    """Input para crear/upsert un contacto.

    SEGURIDAD (regla 6): NUNCA exponer `team_id` ni datos cruzados. El
    backend siempre infiere `team_id` del usuario autenticado.
    """
    phone_e164: str = Field(..., min_length=8, max_length=20)
    name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[EmailStr] = None
    attributes: Optional[dict] = None
    opt_in: Optional[bool] = True
    opt_in_source: Optional[str] = Field(default=None, max_length=50)

    @field_validator("phone_e164")
    @classmethod
    def _validate_e164(cls, v: str) -> str:
        v = (v or "").strip()
        if not _E164_RE.match(v):
            # Mensaje genérico: NO incluir el valor en el error (regla 1).
            raise ValueError("phone_e164 inválido (formato esperado: +<código país><número>)")
        return v


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    email: Optional[EmailStr] = None
    attributes: Optional[dict] = None
    opt_in: Optional[bool] = None
    opt_in_source: Optional[str] = Field(default=None, max_length=50)
    # phone_e164 NO es actualizable (rompería identidad/uq). Para "cambiar
    # teléfono" hay que crear un contacto nuevo o usar import.


class ContactOut(BaseModel):
    """Salida segura del contacto.

    SEGURIDAD (regla 2): NO incluye `team_id`. Aunque sea propio, no se filtra
    porque el endpoint ya filtró por team del usuario. NO incluye secretos.
    """
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    phone_e164: str
    name: Optional[str] = None
    email: Optional[str] = None
    attributes: dict = {}
    opt_in: bool
    opt_in_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ContactGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = None


class ContactGroupUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = None


class ContactGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    description: Optional[str] = None
    member_count: int = 0
    created_at: datetime


class ContactGroupDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    description: Optional[str] = None
    member_count: int = 0
    created_at: datetime
    members: List[ContactOut] = []


class ContactGroupAddMembersIn(BaseModel):
    """Body del endpoint POST /contact-groups/{id}/members.

    `contact_ids` debe contener IDs del MISMO team del usuario (S13-001).
    El router valida ownership de cada ID antes de insertar.
    """
    contact_ids: List[int] = Field(..., min_length=1, max_length=10000)


class ContactBulkImportResult(BaseModel):
    """Resultado de POST /contacts/import-csv.

    SEGURIDAD (regla 1, S13-009): los mensajes en `errors` NUNCA deben
    contener el teléfono crudo ni datos PII. Solo `fila N: motivo`.
    """
    total: int
    created: int
    updated: int
    skipped: int
    errors: List[str] = []


# ─── Sprint 13 / templates ────────────────────────────────────────────────
# Schemas para WhatsApp Templates. Reglas clave aplicadas:
#   - Regla 2 / S13-010: NUNCA exponer `MetaAccountOut` embebido —
#     `meta_account_id` (int) es lo único que sale.
#   - S13-006: `rejection_reason` se trunca (500 chars) y se sanitizan tags
#     HTML antes de exponer; el crudo se persiste en DB para auditoría.
import re as _html_re

_HTML_TAG_RE = _html_re.compile(r"<[^>]+>")
_REJECTION_REASON_MAX = 500


def _sanitize_rejection_reason(raw: Optional[str]) -> Optional[str]:
    """Strip tags + truncate. Defensa-en-profundidad contra XSS si la UI
    olvidara escapar (React por defecto sí escapa, pero si alguien usara
    `dangerouslySetInnerHTML`...). Persiste el crudo en DB para auditoría;
    solo este helper sanea para el `...Out`.
    """
    if not raw:
        return None
    cleaned = _HTML_TAG_RE.sub("", raw).strip()
    if len(cleaned) > _REJECTION_REASON_MAX:
        cleaned = cleaned[:_REJECTION_REASON_MAX] + "…"
    return cleaned or None


class WhatsappTemplateOut(BaseModel):
    """Salida segura de una plantilla.

    SEGURIDAD (regla 2): NO incluye `meta_account` embebido. Solo el id
    numérico. Nunca debería aparecer `encrypted_access_token` ni nada
    derivado del token de Meta en esta respuesta.
    """
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    meta_account_id: int
    meta_template_id: Optional[str] = None
    name: str
    category: Optional[str] = None
    language: str
    status: str
    components_json: Any
    rejection_reason: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    @field_validator("rejection_reason", mode="before")
    @classmethod
    def _sanitize_reason(cls, v):
        if v is None:
            return None
        return _sanitize_rejection_reason(v if isinstance(v, str) else str(v))


class WhatsappTemplateCreatePayload(BaseModel):
    """Input para `POST /templates`.

    El cuerpo se pasa a Meta tal cual lo construya el servicio. Los `components`
    deben matchear el formato de Meta Graph API:
      - header: {type, format, text|example}
      - body:   {type:'BODY', text, example?}
      - footer: {type:'FOOTER', text}
      - buttons: {type:'BUTTONS', buttons: [...]}
    El servicio valida la estructura mínima antes de POSTear a Meta.
    """
    name: str = Field(..., min_length=1, max_length=120, pattern=r"^[a-z0-9_]+$")
    category: str = Field(..., min_length=1, max_length=40)
    language: str = Field(..., min_length=2, max_length=20)
    components: List[Dict] = Field(..., min_length=1, max_length=10)

    @field_validator("category")
    @classmethod
    def _check_category(cls, v: str) -> str:
        if v not in ("MARKETING", "UTILITY", "AUTHENTICATION"):
            raise ValueError("category inválida")
        return v


class WhatsappTemplateSyncResult(BaseModel):
    """Resultado de `POST /templates/sync`."""
    synced: int = 0
    created: int = 0
    updated: int = 0
    deleted_upstream: int = 0
    errors: List[str] = []
    sandbox: bool = False


# ─── Sprint 13 / campaigns ────────────────────────────────────────────────
# Schemas para Campaign / CampaignRecipient / CampaignEvent.
# Reglas clave aplicadas:
#   - Regla 2 / S13-010: NUNCA exponer `MetaAccountOut` embebido — solo
#     `meta_account_id` (int).
#   - S13-011: `CampaignEventOut` (default) NO incluye `payload_json` por
#     defecto. Hay un schema separado `CampaignEventPayloadOut` para el
#     endpoint guardado por permiso de owner.
#   - S13-001 (en CRUD/router): `template_id`/`meta_account_id` se validan
#     contra el team del usuario antes de crear; 404 (no 403) si no matchea.
#   - S13-002: `MAX_RECIPIENTS_PER_CAMPAIGN = 10000` enforce'd en CRUD,
#     pero `min_length`/`max_length` aquí no se imponen para permitir el
#     modo `group` (donde la lista la resuelve el backend).


# Tope absoluto de destinatarios por campaña. Validado en CRUD; 422 si
# excede. Coincidente con la directriz S13-002 del review de Seguridad.
MAX_RECIPIENTS_PER_CAMPAIGN = 10000


class CampaignRecipientsIn(BaseModel):
    """Sub-payload de `CampaignCreate.recipients`.

    Dos modos excluyentes (validados en CRUD):
      - mode='individual' → usa `contact_ids` (lista de IDs del team).
      - mode='group'      → usa `contact_group_id` (grupo del team).
    """
    mode: str = Field(..., pattern=r"^(individual|group)$")
    contact_ids: Optional[List[int]] = None
    contact_group_id: Optional[int] = None


class CampaignCreate(BaseModel):
    """Input para `POST /campaigns`.

    SEGURIDAD: `meta_account_id` se valida contra el team del usuario
    (S13-001). `template_id` debe pertenecer al mismo `meta_account_id`
    y tener `status='APPROVED'`.
    """
    name: str = Field(..., min_length=1, max_length=120)
    template_id: int = Field(..., ge=1)
    meta_account_id: int = Field(..., ge=1)
    template_variables_json: Optional[dict] = None
    scheduled_at: Optional[datetime] = None
    recipients: CampaignRecipientsIn


class CampaignRecipientOut(BaseModel):
    """Salida segura de un destinatario.

    El dueño del team SÍ puede ver `phone_e164` y `name` (es su propio
    contacto). Endpoints públicos NUNCA exponen este schema.
    """
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    contact_id: int
    phone_e164: str
    status: str
    error_code: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None


class CampaignKPIs(BaseModel):
    """KPIs agregados por campaña (computados desde campaign_recipients)."""
    total_recipients: int = 0
    sent: int = 0           # incluye sent + delivered + read
    delivered: int = 0      # incluye delivered + read
    read: int = 0
    failed: int = 0
    pending: int = 0        # queued + sending
    skipped: int = 0


class CampaignOut(BaseModel):
    """Salida de listado de campañas.

    SEGURIDAD (regla 2 / S13-010): NO incluye `meta_account` embebido,
    solo `meta_account_id` (int).
    """
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    name: str
    status: str
    meta_account_id: int
    template_id: int
    scheduled_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    # KPIs agregados
    total_recipients: int = 0
    sent: int = 0
    delivered: int = 0
    read: int = 0
    failed: int = 0
    pending: int = 0
    skipped: int = 0


class CampaignDetailOut(CampaignOut):
    """Detalle de una campaña con preview de destinatarios."""
    template_name: Optional[str] = None
    template_language: Optional[str] = None
    template_variables_json: dict = {}
    recipients_preview: List[CampaignRecipientOut] = []
    kpis_by_event_type: Dict[str, int] = {}


class CampaignsGlobalKPIs(BaseModel):
    """KPIs agregados de TODAS las campañas del team (dashboard /campanas)."""
    total_campaigns: int = 0
    total_recipients: int = 0
    sent_count: int = 0
    delivered_count: int = 0
    read_count: int = 0
    failed_count: int = 0
    queued_count: int = 0
    skipped_count: int = 0
    delivery_rate_pct: Optional[float] = None
    read_rate_pct: Optional[float] = None


class CampaignRecipientsPage(BaseModel):
    """Página de destinatarios para `GET /campaigns/{id}/recipients`."""
    items: List[CampaignRecipientOut] = []
    total: int = 0
    limit: int = 50
    offset: int = 0
