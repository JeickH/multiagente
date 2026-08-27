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
    # #318: 'demo' | 'produccion'. En 'demo' los envíos a WhatsApp se simulan.
    # El frontend lo usa para mostrar el distintivo de cuenta de demostración.
    # SIN default a propósito: con uno, un call-site que olvide pasarlo reporta
    # 'demo' para un tenant en producción y la API miente en silencio (pasó al
    # construir TeamOut campo por campo en /teams/me). Requerido = falla ruidosa.
    modo: str

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
    # Marca del sistema sobre la conversación (ej. "conversación abandonada").
    # None = sin etiqueta.
    etiqueta: Optional[str] = None
    last_message_at: datetime
    last_message_preview: Optional[str] = None

    class Config:
        from_attributes = True


class ConversationPageOut(BaseModel):
    """Una página de la bandeja, con el total del filtro aplicado.

    `total` es cuántas conversaciones matchean el filtro —no cuántas trae esta
    página— para que el contador pueda decir "1-20 de 87 pendientes" y para
    saber si hay página siguiente sin tener que pedirla.
    """

    conversaciones: List[ConversationOut]
    total: int
    pagina: int = 1
    por_pagina: int = 0


class ConversationWithMessages(BaseModel):
    id: int
    contact_wa_id: str
    contact_name: Optional[str] = None
    status: str
    assigned_to: str = "bot"
    etiqueta: Optional[str] = None
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


# ===== Adjuntos: subida directa a S3 (Sprint 26) =====
# El archivo no viaja por nuestra API porque entre el navegador y ECS hay dos
# saltos con techo propio (Amplify ~4,4 MB y API Gateway 10 MB). Ver el
# docstring de `services/adjuntos`.

class AdjuntoPrepararIn(BaseModel):
    """Lo que el navegador sabe del archivo ANTES de subirlo."""
    filename: Optional[str] = None
    content_type: Optional[str] = None
    size: int                    # bytes, para rebotar el archivo antes de subirlo


class AdjuntoPrepararOut(BaseModel):
    """Por dónde subir.

    `modo="s3"` trae el POST prefirmado; `modo="directo"` significa que no hay
    bucket (desarrollo local) y el navegador debe usar el endpoint de siempre.
    Los `campos` van tal cual al formulario, sin tocarlos: son parte de la firma.
    """
    modo: str                    # 's3' | 'directo'
    url: Optional[str] = None
    campos: Optional[dict] = None
    referencia: Optional[str] = None


class AdjuntoConfirmarIn(BaseModel):
    """"Ya subí; mándalo." El archivo se identifica por la referencia que
    devolvió `preparar`, nunca por una ruta que proponga el cliente."""
    referencia: str
    filename: Optional[str] = None
    content_type: Optional[str] = None
    caption: Optional[str] = None


# ===== Sprint 8/9: Bots =====
class BotListItem(BaseModel):
    """Fila del listado `/bots`."""
    id: int
    name: str
    status: str
    channels: List[str]                 # ["whatsapp", "instagram", ...]
    engine: str = "flow"                # 'flow' | 'llm' (Sprint 19)
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
    """Detalle de un bot con sus pasos ordenados para el diagrama.

    NOTA Sprint 19: `llm_config` NO se expone (contiene el secreto Shopify
    cifrado del tenant — regla de seguridad #2). Solo se expone `engine`.
    """
    id: int
    name: str
    description: Optional[str] = None
    status: str
    channels: List[str]
    engine: str = "flow"                # 'flow' | 'llm' (Sprint 19)
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
    # Sprint 19 #255: camino que tomó el motor LLM en este turno (solo bots
    # 'llm'; None para bots de flujo). El simulador lo muestra como chip.
    camino: Optional[str] = None


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


class ContactExcelRowError(BaseModel):
    """Una fila rechazada del Excel: en qué fila fue y por qué.

    SEGURIDAD (regla 1): `reason` es un motivo en español para que la usuaria
    encuentre la celda — NUNCA el teléfono, el correo ni la fila cruda.
    """
    row: int
    reason: str


class ContactExcelImportResult(BaseModel):
    """Resultado de POST /contacts/import-excel.

    A diferencia del CSV, aquí el rechazo viaja estructurado (`row` + `reason`)
    porque la pantalla lo pinta como una tabla y no como una lista de strings.
    """
    total: int
    created: int
    updated: int
    rejected: int
    errors: List[ContactExcelRowError] = []
    # Encabezados extra que se guardaron como atributos del contacto.
    detected_attributes: List[str] = []
    # Mensaje general cuando algo aplica a todo el archivo (no a una fila).
    notice: Optional[str] = None


class ContactFieldOut(BaseModel):
    """Un campo del contacto utilizable para personalizar un mensaje.

    SEGURIDAD (regla 2): es el CATÁLOGO, no los valores. Aquí no viaja PII.
    """
    key: str
    label: str
    # Convención que se guarda en `campaigns.template_variables_json` cuando
    # la campaña usa el dato del contacto en vez de un texto fijo.
    token: str
    source: str  # 'base' | 'attribute'
    contacts: int = 0


class ContactFieldsOut(BaseModel):
    fields: List[ContactFieldOut] = []
    scanned_contacts: int = 0


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


# ===== Pagos: paquetes de mensajes (Wompi) =====
#
# SEGURIDAD (regla 2): ningún `...Out` de acá lleva llaves de Wompi. Lo único
# que sale al navegador es la **llave pública** y la **firma** ya calculada,
# ambas dentro de `checkout.fields` — la pública es pública por definición y
# la firma es el resultado del secreto, no el secreto. `WOMPI_PRIVATE_KEY`,
# `WOMPI_INTEGRITY_SECRET` y `WOMPI_EVENTS_SECRET` no aparecen en ningún
# schema de respuesta ni pueden aparecer: no hay campo donde quepan.


class PagosAccesoOut(BaseModel):
    """`GET /pagos/access` — ¿esta sesión ve el módulo de pagos?"""
    allowed: bool


class PaqueteDesgloseOut(BaseModel):
    """En qué se va cada peso del precio de un paquete.

    Va en el catálogo para que el CEO pueda auditar el precio desde la
    pantalla, sin abrir el código. Es información de costos del negocio, así
    que solo la ve un administrador — el endpoint que la sirve exige
    `can_manage_billing`.
    """
    costo_cop: int
    margen_objetivo_cop: int
    neto_objetivo_cop: int
    comision_wompi_cop: int
    neto_real_cop: int
    margen_real_cop: int
    margen_real_pct: float
    trm: float
    trm_fecha: str
    costo_usd_por_mensaje: float


class PaqueteOut(BaseModel):
    """Un paquete del catálogo. El precio ya viene calculado del servidor."""
    key: str
    nombre: str
    descripcion: str
    messages: int
    amount_cents: int          # centavos de COP — el formato que exige Wompi
    amount_cop: int            # pesos enteros, para pintar
    precio_por_mensaje_cop: int
    currency: str
    #: Link de pago de Wompi creado a mano para este paquete, si existe. NO es
    #: un secreto: es una página pública de cobro. Cuando viene, el frontend
    #: manda al usuario ahí en vez de armar el checkout por API.
    link_pago: Optional[str] = None
    desglose: PaqueteDesgloseOut


class PaquetesOut(BaseModel):
    paquetes: List[PaqueteOut]
    #: `false` si al backend le faltan llaves de Wompi: la pantalla avisa
    #: "pagos no disponible" en vez de mandar al usuario a un checkout roto.
    pagos_habilitados: bool


class CompraOut(BaseModel):
    """Una compra en el historial. Sin datos del pagador ni del medio de pago."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    package_key: str
    messages: int
    amount_cents: int
    currency: str
    reference: str
    status: str
    provider_tx_id: Optional[str] = None
    credited_at: Optional[datetime] = None
    created_at: datetime


class SaldoOut(BaseModel):
    """`GET /pagos/saldo` — créditos disponibles + historial de compras."""
    message_credits: int
    compras: List[CompraOut] = []


class CheckoutCreate(BaseModel):
    """Input de `POST /pagos/checkout`: qué paquete se quiere comprar.

    `redirect_url` es a dónde vuelve el usuario tras pagar. Se valida y se
    restringe en el router (solo rutas propias): un `redirect-url` libre
    convierte el checkout en un redirector abierto hacia cualquier dominio.
    """
    package_key: str = Field(..., min_length=1, max_length=40)
    redirect_url: Optional[str] = Field(default=None, max_length=300)


class CheckoutFormOut(BaseModel):
    """El form de Web Checkout listo para enviar.

    `fields` lleva las llaves con el nombre EXACTO de Wompi
    (`amount-in-cents`, `signature:integrity`, …), que no son identificadores
    válidos de Python; por eso es un dict y no un modelo con atributos.
    """
    url: str
    method: str
    fields: Dict[str, Any]


class EstadoPagoOut(BaseModel):
    """Resultado informativo de un pago hecho por link.

    `estado` es uno de: `aprobado`, `rechazado`, `pendiente`, `desconocido`.
    No expone nada del pagador: solo si entró la plata y por cuánto.
    """
    estado: str
    amount_cents: Optional[int] = None


class CheckoutOut(BaseModel):
    """Respuesta de `POST /pagos/checkout`."""
    reference: str
    purchase_id: int
    amount_cents: int
    currency: str
    messages: int
    checkout: CheckoutFormOut
