"""API pública de la demo interactiva de glomacx.com/demo (Sprint 32, #613).

Tres endpoints SIN autenticación de usuario:

- `POST /demo/iniciar`          → guarda al prospecto y arma su bot de demo.
- `GET  /demo/{demo_id}/estado` → ¿ya está listo el bot? (el front lo consulta
  cada ~1,5 s mientras pasan las slides).
- `POST /demo/{demo_id}/chat`   → un turno de conversación con ese bot.

El contrato está en la BITACORA (Sprint 32). Lo que este archivo hace cumplir
de la revisión de seguridad #608:

* **A1 — topes en la BASE, no en memoria** (la memoria se borra en cada
  deploy): demos por IP (hora y día), por correo y por teléfono (día) y un
  techo global diario, más un freno mensual de turnos. Correo en minúsculas y
  teléfono en E.164 ANTES de guardar y de contar: si no, el tope se evade con
  mayúsculas o con espacios. Todos los 429 dicen lo mismo (M8). La IP sale de
  `DEMO_IP_HEADER` cuando existe (API Gateway la escribe desde
  `$context.identity.sourceIp`, #617); sin ella, del primer valor de
  `X-Forwarded-For`, que es **higiene**, no un control: el cliente lo escribe.
  El control real son los topes por correo, teléfono y global.
* **A2 — una demo no ahoga el único proceso**: la generación corre en segundo
  plano con su propia sesión de BD y el semáforo de `demo_bot` (2); los turnos
  de chat tienen su semáforo (4) y su rate-limit en memoria (por IP y global).
  Lleno → "muy solicitada", sin consumir turno. Una demo que lleva más de 60 s
  en `generando` (p. ej. la task se reinició) se resuelve con el respaldo
  determinista al consultar el estado.
* **A3 — el contador de turnos vive en la fila**: `UPDATE … SET turnos =
  turnos + 1 WHERE turnos < :max RETURNING turnos`, y el historial del chat
  también (`chat_state`). Reenviar un token viejo no reinicia nada. El campo
  `session` del contrato se ignora y se devuelve `null`.
* **Token de acceso** `{"p":"demo","v":1,"d":<public_id>}` cifrado con una
  subclave HKDF de `APP_ENCRYPTION_KEY` (info `demo-token-v1`: un token de la
  demo no sirve como ningún otro token Fernet de la app ni al revés), TTL 6 h.
  Se descifra y se compara con el path (`hmac.compare_digest`) ANTES de tocar
  la base. Sin token, inválido, vencido, de otra demo, UUID mal formado o demo
  inexistente → SIEMPRE el mismo 404.
* **M5 — PII**: nombre, correo y teléfono van solo a `leads`; nunca al prompt,
  nunca a una respuesta, nunca a un log. La transcripción vive en un solo lugar
  (`demos.transcripcion`, acotada); la telemetría del turno guarda tokens y
  costo pero no el texto.
* **M6 — aislamiento**: el bot se carga SOLO como `id = demo.bot_id AND user_id
  = <dueño de las demos> AND engine = 'llm'`; el cliente nunca elige un bot.
* **M7 — honeypot + tiempo mínimo de llenado**, y Cloudflare Turnstile solo si
  existe `DEMO_TURNSTILE_SECRET`.
"""
from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

import httpx
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import APIRouter, BackgroundTasks, Body, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, ValidationInfo, field_validator, model_validator
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from .. import models
from ..database import SessionLocal
from ..dependencies import get_db
from ..services import demo_bot, llm_engine, productos, ratelimit
from .landing import ChatAction, ChatIn, ChatOut

logger = logging.getLogger(__name__)

_ORIGENES_DEFAULT = "https://glomacx.com,https://www.glomacx.com"


def origenes_permitidos() -> set:
    crudo = os.getenv("DEMO_ALLOWED_ORIGINS", "").strip() or _ORIGENES_DEFAULT
    return {o.strip().rstrip("/").lower() for o in crudo.split(",") if o.strip()}


def origen_permitido(request: Request) -> None:
    """#616: un navegador en otro sitio no puede usar `/demo/*`. Si llega
    `Origin` y no es de la landing, el mismo 404 de siempre. Sin `Origin`
    (curl, servidor a servidor) pasa: los topes son los que mandan ahí. El CORS
    global no se toca (backlog: `allow_credentials=False`)."""
    origen = request.headers.get("origin")
    if origen is None:
        return
    if origen.strip().rstrip("/").lower() not in origenes_permitidos():
        raise HTTPException(status_code=404, detail="Demo no encontrada")


router = APIRouter(
    prefix="/demo", tags=["demo"], dependencies=[Depends(origen_permitido)],
)


# ---------------------------------------------------------------------------
# Configuración (todo por env, leído en cada request salvo los semáforos)
# ---------------------------------------------------------------------------

#: Sube cada vez que cambia el texto de /privacidad que acepta el prospecto
#: (#635: el texto nombra Cal.com y AWS Bedrock).
CONSENT_VERSION = "demo-2026-10b"
LEAD_SOURCE = "gloma_demo"
TOKEN_TTL_SEGUNDOS = 6 * 3600
GENERANDO_VENCE_SEGUNDOS = 60
FORM_MS_MINIMO = 3000
MAX_TRANSCRIPCION_TEXTO = 500
_TOKEN_INFO = b"demo-token-v1"
_TURNSTILE_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def _env_int(nombre: str, defecto: int) -> int:
    try:
        return max(0, int(os.getenv(nombre, "") or defecto))
    except ValueError:
        return defecto


def _tope(nombre: str) -> int:
    return _env_int(nombre, _TOPES_DEFAULT[nombre])


_TOPES_DEFAULT = {
    "DEMO_MAX_POR_IP_HORA": 5,
    "DEMO_MAX_POR_IP_DIA": 15,
    "DEMO_MAX_POR_CORREO_DIA": 3,
    "DEMO_MAX_POR_TELEFONO_DIA": 3,
    "DEMO_MAX_GLOBAL_DIA": 50,
    "DEMO_MAX_TURNOS_MES": 4000,
    "DEMO_MAX_TURNOS": 15,
    "DEMO_MAX_LEADS_DIA": 200,
}


def _owner_email() -> str:
    return (os.getenv("DEMO_OWNER_EMAIL") or "demos@glomacx.com").strip().lower()


# Textos que ve el visitante. Uno solo para TODOS los 429 (M8): no se dice qué
# tope saltó.
TEXTO_429 = (
    "Recibimos muchas solicitudes de demo en este momento. Intenta de nuevo "
    "más tarde."
)
TEXTO_MUY_SOLICITADA = (
    "La demo está muy solicitada en este momento 🙏 Escríbeme de nuevo en un "
    "minuto."
)
#: Cierre fijo del último turno (#619, QA #615): el turno 15 terminaba con una
#: pregunta del bot que el visitante ya no podía contestar.
TEXTO_CIERRE_DEMO = (
    "Hasta aquí llega esta demostración 🙌 En tu cuenta, la conversación "
    "seguiría hasta cerrar la reserva con tu equipo."
)
TEXTO_FIN_TURNOS = (
    "Hasta aquí llega esta demostración 🙌 ¡Gracias por probarla!"
)
TEXTO_HANDOFF = (
    "Te paso con una persona del equipo para seguir con tu reserva 🙌"
)
_NO_ENCONTRADA = "Demo no encontrada"


def _no_encontrada() -> HTTPException:
    return HTTPException(status_code=404, detail=_NO_ENCONTRADA)


# ---------------------------------------------------------------------------
# Token de acceso
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def _fernet_para(primaria: str, anterior: str) -> MultiFernet:
    """MultiFernet con subclaves HKDF de las claves maestras (actual primero)."""
    fernets = []
    for raw in (primaria, anterior):
        if not raw:
            continue
        material = base64.urlsafe_b64decode(raw.encode("utf-8"))
        sub = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=_TOKEN_INFO
        ).derive(material)
        fernets.append(Fernet(base64.urlsafe_b64encode(sub)))
    if not fernets:
        raise RuntimeError("APP_ENCRYPTION_KEY no está configurada")
    return MultiFernet(fernets)


def _fernet() -> MultiFernet:
    return _fernet_para(
        os.getenv("APP_ENCRYPTION_KEY") or "", os.getenv("APP_ENCRYPTION_KEY_OLD") or ""
    )


def emitir_token(public_id: uuid.UUID) -> str:
    carga = json.dumps({"p": "demo", "v": 1, "d": str(public_id)}, separators=(",", ":"))
    return _fernet().encrypt(carga.encode("utf-8")).decode("utf-8")


def verificar_token(token: Optional[str], demo_id: str) -> Optional[uuid.UUID]:
    """El `public_id` si el token es válido PARA ESE path; si no, `None`.

    No toca la base. Cualquier falla devuelve `None` y el caller responde el
    mismo 404 — sin distinguir "no existe" de "no es tuya" de "venció".
    """
    if not token or len(token) > 2048:
        return None
    try:
        pedido = uuid.UUID(str(demo_id))
    except (ValueError, AttributeError, TypeError):
        return None
    try:
        crudo = _fernet().decrypt(token.encode("utf-8"), ttl=TOKEN_TTL_SEGUNDOS)
        datos = json.loads(crudo.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, UnicodeError):
        return None
    if not isinstance(datos, dict) or datos.get("v") != 1:
        return None
    p, d = datos.get("p"), datos.get("d")
    if not isinstance(p, str) or not isinstance(d, str):
        return None
    ok_p = hmac.compare_digest(p.encode("utf-8"), b"demo")
    ok_d = hmac.compare_digest(d.encode("utf-8"), str(pedido).encode("utf-8"))
    if not (ok_p and ok_d):
        return None
    return pedido


def _demo_autorizada(db: Session, demo_id: str, token: Optional[str]) -> models.Demo:
    public_id = verificar_token(token, demo_id)
    if public_id is None:
        raise _no_encontrada()
    demo = db.query(models.Demo).filter(models.Demo.public_id == public_id).first()
    if demo is None:
        raise _no_encontrada()
    return demo


# ---------------------------------------------------------------------------
# Normalización de la entrada
# ---------------------------------------------------------------------------

_PHONE_RE = re.compile(r"^[+\d(][\d\s\-().]{5,30}$")


def normalizar_telefono(valor: str) -> str:
    """E.164 (`+573001234567`). Sin indicativo y con 10 dígitos se asume
    Colombia (celulares 3XX y fijos 60X). Lanza `ValueError`."""
    v = (valor or "").strip()
    if not _PHONE_RE.match(v):
        raise ValueError("Teléfono inválido")
    digitos = re.sub(r"\D", "", v)
    if v.startswith("+"):
        pass
    elif digitos.startswith("00"):
        digitos = digitos[2:]
    elif len(digitos) == 10:
        digitos = "57" + digitos
    if not (8 <= len(digitos) <= 15) or digitos.startswith("0"):
        raise ValueError("Teléfono inválido")
    return "+" + digitos


def _limpiar_texto(v: str) -> str:
    v = re.sub(r"[\x00-\x1f\x7f]", " ", v or "")
    return re.sub(r"\s+", " ", v).strip()


class IniciarIn(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=120)
    empresa: str = Field(..., min_length=1, max_length=200)
    telefono: str = Field(..., min_length=6, max_length=40)
    correo: EmailStr
    tipo_empresa: str = Field(..., max_length=40)
    tipo_otro: Optional[str] = Field(default=None, max_length=200)
    acepta_contacto: bool = False
    acepta_promociones: bool = False
    # M7: el honeypot (una persona lo deja vacío) y cuánto tardó en llenarlo.
    sitio_web: Optional[str] = Field(default=None, max_length=500)
    form_ms: Optional[int] = None
    turnstile_token: Optional[str] = Field(default=None, max_length=4096)

    @field_validator("nombre")
    @classmethod
    def _v_nombre(cls, v: str) -> str:
        v = _limpiar_texto(v)
        if len(v) < 2:
            raise ValueError("Nombre inválido")
        return v

    @field_validator("tipo_empresa")
    @classmethod
    def _v_tipo(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in demo_bot.TIPOS_EMPRESA:
            raise ValueError("Tipo de empresa inválido")
        return v

    @field_validator("empresa")
    @classmethod
    def _v_empresa(cls, v: str) -> str:
        # La misma regla que la generación (lista blanca, largos, sin
        # contacto). El tipo da igual para validar el nombre.
        return demo_bot.validar_entrada(v, "otro")[0]

    @field_validator("tipo_otro")
    @classmethod
    def _v_tipo_otro(cls, v: Optional[str], info: ValidationInfo) -> Optional[str]:
        # Solo existe con «Otro»: con cualquier otro tipo se descarta, así no
        # entra texto libre al prompt por un tipo de la lista.
        if info.data.get("tipo_empresa") != "otro" or v is None or not v.strip():
            return None
        return demo_bot.validar_entrada("Empresa", "otro", v)[2]

    @field_validator("telefono")
    @classmethod
    def _v_telefono(cls, v: str) -> str:
        return normalizar_telefono(v)

    @field_validator("correo")
    @classmethod
    def _v_correo(cls, v: str) -> str:
        return str(v).strip().lower()

    @model_validator(mode="after")
    def _exige_autorizacion(self) -> "IniciarIn":
        # Ley 1581: sin autorización expresa no se guarda nada.
        if not self.acepta_contacto:
            raise ValueError("Debes aceptar que te contactemos")
        return self


class IniciarOut(BaseModel):
    demo_id: str
    token: str


class ProductoOut(BaseModel):
    nombre: str
    resumen: str


class EstadoOut(BaseModel):
    estado: str
    empresa: str
    productos: List[ProductoOut] = []
    mensaje_sugerido: Optional[str] = None


# ---------------------------------------------------------------------------
# IP, cuenta dueña y sesiones
# ---------------------------------------------------------------------------

def _ip_cliente(request: Request) -> str:
    """Con `DEMO_IP_HEADER` se usa SOLO ese header (lo escribe API Gateway y el
    cliente no lo puede pisar). Sin él, el primer valor de XFF: higiene."""
    header = (os.getenv("DEMO_IP_HEADER") or "").strip().lower()
    if header:
        return (request.headers.get(header) or "").strip()[:64] or "desconocida"
    return ratelimit.client_ip(request)[:64]


_DUENO: Dict[str, Tuple[int, int]] = {}
_DUENO_LOCK = threading.Lock()


def _dueno_demos(db: Session) -> Optional[Tuple[int, int]]:
    """`(user_id, team_id)` de la cuenta dueña de las demos, cacheado."""
    correo = _owner_email()
    with _DUENO_LOCK:
        if correo in _DUENO:
            return _DUENO[correo]
    user = db.query(models.User).filter(models.User.correo == correo).first()
    if user is None:
        return None
    team = (
        db.query(models.Team)
        .filter(models.Team.owner_user_id == user.id)
        .order_by(models.Team.id)
        .first()
    )
    if team is None:
        return None
    with _DUENO_LOCK:
        _DUENO[correo] = (user.id, team.id)
    return user.id, team.id


def limpiar_cache_dueno() -> None:
    with _DUENO_LOCK:
        _DUENO.clear()


def _nueva_sesion() -> Session:
    """Sesión propia de la tarea de fondo (la del request ya se cerró)."""
    return SessionLocal()


@lru_cache(maxsize=1)
def _plantilla() -> str:
    ruta = Path(__file__).resolve().parent.parent / "bot_contexts" / "demo_plantilla.md"
    return ruta.read_text(encoding="utf-8")


def _etiqueta_tipo(demo: models.Demo) -> str:
    if demo.tipo_empresa == "otro":
        return demo.tipo_otro or "Negocio de turismo"
    return demo_bot.TIPOS_EMPRESA.get(demo.tipo_empresa, "Negocio de turismo")


_ENCABEZADO_FICHAS = (
    "## Fichas de los productos\n"
    "Esto es lo que sabes de cada producto. Lo que no esté aquí no lo sabes: "
    "no lo afirmes ni lo niegues, y NUNCA inventes una condición, un requisito "
    "o una restricción (mínimos, máximos, edades, documentos). Cada ficha trae "
    "su precio exacto, que es el mismo todo el año: cítalo tal cual, nunca "
    "otro. Si la unidad del precio ya incluye noches («por persona, 7 "
    "noches»), ese precio cubre esas noches: multiplícalo solo por personas."
)


def _pesos(valor: int) -> str:
    return f"${int(valor):,}".replace(",", ".")


def instrucciones_de(
    demo: models.Demo, productos_demo: Tuple[demo_bot.ProductoDemo, ...] = ()
) -> str:
    """La plantilla rellena, con las fichas de los 3 productos al final.

    `str.replace`, NUNCA `.format`: `empresa` la escribió un desconocido (ya
    pasó por la lista blanca de `validar_entrada`, que no deja `{` ni `}`).

    Las fichas van en el prefijo (#619, QA #615): servidas solo por
    `abrir_producto`, el bot las olvidaba después del primer turno y llegó a
    inventar «máximo 6 personas» donde la ficha decía «mínimo 2». El prefijo ya
    es propio de cada demo y se cachea, así que repetirlas por turno es barato.
    """
    texto = (
        _plantilla()
        .replace("{empresa}", demo.empresa)
        .replace("{tipo_empresa}", _etiqueta_tipo(demo))
    )
    if productos_demo:
        # El precio va pegado a su ficha (#621, QA #620): con las fichas en el
        # prefijo el modelo dejó de llamar `consultar_precios` y se inventó
        # cifras. El precio es plano, así que no hay nada que adivinar.
        fichas = "\n\n".join(
            f"### {p.nombre}\n{p.ficha.strip()}\n"
            f"Precio: {_pesos(p.precio_cop)} {p.unidad_precio} (igual todo el año)"
            for p in productos_demo
        )
        texto = f"{texto.rstrip()}\n\n{_ENCABEZADO_FICHAS}\n\n{fichas}\n"
    return texto


#: Haiku 4.5 (perfil global), el mismo de la generación. El bot de demo NO
#: hereda `LLM_MODEL_ID` (#616 B3): si los bots de clientes pasan a un modelo
#: más caro, el costo de una demo pública no tiene por qué subir con ellos.
_MODELO_CHAT_DEFAULT = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


def modelo_chat() -> str:
    return (os.getenv("DEMO_CHAT_MODEL_ID") or "").strip() or _MODELO_CHAT_DEFAULT


def llm_config_demo() -> str:
    return json.dumps(
        {"fuente_datos": "productos", "demo": True, "model_id": modelo_chat()}
    )


# ---------------------------------------------------------------------------
# Topes en la base (A1)
# ---------------------------------------------------------------------------

def _hace(horas: float) -> datetime:
    return datetime.utcnow() - timedelta(hours=horas)


def _inicio_mes_utc() -> datetime:
    """El 1 del mes en Colombia (UTC-5, sin horario de verano), en UTC naive."""
    ahora_co = datetime.utcnow() - timedelta(hours=5)
    return datetime(ahora_co.year, ahora_co.month, 1) + timedelta(hours=5)


def _leads_demo(db: Session):
    return db.query(func.count(models.Lead.id)).filter(models.Lead.source == LEAD_SOURCE)


def _tope_personal(db: Session, ip: str, correo: str, telefono: str) -> Optional[str]:
    """Qué tope personal saltó (para el log), o `None`.

    Se cuentan los LEADS de la demo, no solo las filas de `demos`: cuando salta
    el tope global el lead se guarda sin demo, y esos intentos también tienen
    que contar contra la IP, el correo y el teléfono.
    """
    if _leads_demo(db).filter(
        models.Lead.ip_address == ip, models.Lead.created_at >= _hace(1)
    ).scalar() >= _tope("DEMO_MAX_POR_IP_HORA"):
        return "ip_hora"
    if _leads_demo(db).filter(
        models.Lead.ip_address == ip, models.Lead.created_at >= _hace(24)
    ).scalar() >= _tope("DEMO_MAX_POR_IP_DIA"):
        return "ip_dia"
    if _leads_demo(db).filter(
        models.Lead.email == correo, models.Lead.created_at >= _hace(24)
    ).scalar() >= _tope("DEMO_MAX_POR_CORREO_DIA"):
        return "correo_dia"
    if _leads_demo(db).filter(
        models.Lead.telefono == telefono, models.Lead.created_at >= _hace(24)
    ).scalar() >= _tope("DEMO_MAX_POR_TELEFONO_DIA"):
        return "telefono_dia"
    return None


def turnos_del_mes(db: Session) -> int:
    return int(
        db.query(func.coalesce(func.sum(models.Demo.turnos), 0))
        .filter(models.Demo.created_at >= _inicio_mes_utc())
        .scalar()
        or 0
    )


def _tope_de_demanda(db: Session) -> Optional[str]:
    """Topes que salta la demanda real (global diario, turnos del mes)."""
    demos_dia = (
        db.query(func.count(models.Demo.id))
        .filter(models.Demo.created_at >= _hace(24))
        .scalar()
    )
    if demos_dia >= _tope("DEMO_MAX_GLOBAL_DIA"):
        return "global_dia"
    if turnos_del_mes(db) >= _tope("DEMO_MAX_TURNOS_MES"):
        return "turnos_mes"
    return None


def _demasiadas() -> HTTPException:
    return HTTPException(status_code=429, detail=TEXTO_429)


# ---------------------------------------------------------------------------
# Turnstile (M7, detrás de una bandera)
# ---------------------------------------------------------------------------

def _turnstile_ok(token: Optional[str], ip: str) -> bool:
    secreto = os.getenv("DEMO_TURNSTILE_SECRET") or ""
    if not secreto:
        return True
    if not token:
        return False
    try:
        resp = httpx.post(
            _TURNSTILE_URL,
            data={"secret": secreto, "response": token, "remoteip": ip},
            timeout=5.0,
        )
        return bool(resp.status_code == 200 and resp.json().get("success") is True)
    except Exception:  # noqa: BLE001 — falla cerrada; el detalle no sale
        logger.warning("demo: no se pudo verificar Turnstile (falla cerrada)")
        return False


# ---------------------------------------------------------------------------
# POST /demo/iniciar
# ---------------------------------------------------------------------------

def _respuesta_falsa() -> IniciarOut:
    """El mismo 202 que una demo de verdad, sin crear nada (honeypot)."""
    falso = uuid.uuid4()
    return IniciarOut(demo_id=str(falso), token=emitir_token(falso))


def _guardar_lead(db: Session, payload: IniciarIn, ip: str, ua: str,
                  ahora: datetime) -> models.Lead:
    lead = models.Lead(
        nombre=payload.nombre,
        email=payload.correo,
        telefono=payload.telefono,
        source=LEAD_SOURCE,
        user_agent=ua,
        ip_address=ip,
        estado="pendiente",
        agencia=payload.empresa[:120],
        acepto_privacidad_at=ahora,
    )
    db.add(lead)
    db.flush()
    return lead


@router.post("/iniciar", response_model=IniciarOut, status_code=202)
def iniciar(
    payload: IniciarIn,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    ip = _ip_cliente(request)
    ua = (request.headers.get("user-agent") or "")[:512]

    # M7: honeypot lleno o formulario llenado en menos de 3 s → 202 falso.
    if (payload.sitio_web or "").strip() or (payload.form_ms or 0) < FORM_MS_MINIMO:
        logger.info("demo: iniciar descartado por honeypot/tiempo")
        return _respuesta_falsa()

    if not _turnstile_ok(payload.turnstile_token, ip):
        raise HTTPException(status_code=400, detail="No pudimos verificar el formulario")

    # Techo diario de leads de la demo (#616 M1): con el tope global activo
    # cada intento igual guardaba un lead, y rotando correos y teléfonos se
    # llenaba `/citas`. Por encima, el mismo 429 y no se guarda nada.
    leads_dia = _leads_demo(db).filter(models.Lead.created_at >= _hace(24)).scalar()
    if leads_dia >= _tope("DEMO_MAX_LEADS_DIA"):
        logger.warning("demo: techo diario de leads alcanzado")
        raise _demasiadas()

    # Topes personales: no se crea NADA.
    personal = _tope_personal(db, ip, payload.correo, payload.telefono)
    if personal:
        logger.warning("demo: tope alcanzado tope=%s", personal)
        raise _demasiadas()

    ahora = datetime.utcnow()
    dueno = _dueno_demos(db)
    demanda = _tope_de_demanda(db)
    if dueno is None:
        logger.error("demo: no existe la cuenta dueña de las demos (correr el seed)")
    if demanda or dueno is None:
        # Demanda real (o la cuenta no está): el prospecto igual queda como
        # lead para que ventas lo llame. No se arma bot.
        lead = _guardar_lead(db, payload, ip, ua, ahora)
        db.commit()
        logger.warning(
            "demo: sin demo, solo lead id=%s tope=%s", lead.id, demanda or "sin_cuenta"
        )
        raise _demasiadas()

    lead = _guardar_lead(db, payload, ip, ua, ahora)
    demo = models.Demo(
        public_id=uuid.uuid4(),
        lead_id=lead.id,
        empresa=payload.empresa,
        tipo_empresa=payload.tipo_empresa,
        tipo_otro=payload.tipo_otro,
        acepta_contacto_at=ahora,
        consent_version=CONSENT_VERSION,
        acepta_promociones=payload.acepta_promociones,
        acepta_promociones_at=ahora if payload.acepta_promociones else None,
        estado=models.DEMO_ESTADO_GENERANDO,
        ip_address=ip,
        user_agent=ua,
    )
    db.add(demo)
    db.commit()
    db.refresh(demo)
    logger.info("demo creada id=%s tipo=%s lead=%s", demo.id, demo.tipo_empresa, lead.id)

    background.add_task(generar_en_fondo, demo.id)
    return IniciarOut(demo_id=str(demo.public_id), token=emitir_token(demo.public_id))


# ---------------------------------------------------------------------------
# Generación: bot + 3 productos
# ---------------------------------------------------------------------------

def materializar(db: Session, demo: models.Demo, contenido: demo_bot.ContenidoDemo) -> bool:
    """Crea el bot y sus 3 productos y deja la demo `lista`, en UNA transacción.

    Devuelve `False` sin dejar nada si otra ejecución ya la resolvió (la tarea
    de fondo y el respaldo por vencimiento pueden cruzarse): el cambio de
    estado es un UPDATE condicionado a `estado='generando'`.
    """
    dueno = _dueno_demos(db)
    if dueno is None:
        raise RuntimeError("no existe la cuenta dueña de las demos")
    user_id, team_id = dueno
    ahora = datetime.utcnow()

    bot = models.Bot(
        user_id=user_id,
        team_id=team_id,
        name=f"Demo #{demo.id} — {demo.empresa}"[:120],
        description="Bot de la demo pública de glomacx.com/demo (Sprint 32).",
        status="active",
        channels="demo",
        engine="llm",
        trigger_type=models.BOT_TRIGGER_MANUAL,
        reparto_pct=None,
        reparto_desde=None,
        instrucciones=instrucciones_de(demo, contenido.productos),
        instrucciones_version=1,
        llm_config=llm_config_demo(),
    )
    db.add(bot)
    db.flush()

    hoy = productos.hoy_colombia()
    public_id = demo.public_id if isinstance(demo.public_id, uuid.UUID) else uuid.UUID(str(demo.public_id))
    prefijo = f"demo-{public_id.hex[:12]}"
    for n, producto in enumerate(contenido.productos, start=1):
        spec = demo_bot.catalogo_demo(producto, hoy)
        datos = dict(spec["producto"])
        slug = f"{prefijo}-{n}-{datos.pop('slug')}"[:80]
        fila_producto = models.BotProducto(team_id=team_id, slug=slug, **datos)
        db.add(fila_producto)
        db.flush()
        for variante in spec["variantes"]:
            db.add(models.BotProductoVariante(producto_id=fila_producto.id, **variante))
        for fila in spec["filas"]:
            db.add(models.BotProductoFila(producto_id=fila_producto.id, **fila))
        db.add(models.BotProductoBot(
            bot_id=bot.id, producto_id=fila_producto.id, activo=True, orden=n,
        ))
    db.flush()

    resultado = db.execute(
        text(
            "UPDATE demos SET estado = :lista, bot_id = :bot_id, "
            "origen_productos = :origen, mensaje_sugerido = :mensaje, "
            "lista_at = :ahora, updated_at = :ahora "
            "WHERE id = :id AND estado = :generando"
        ),
        {
            "lista": models.DEMO_ESTADO_LISTA,
            "generando": models.DEMO_ESTADO_GENERANDO,
            "bot_id": bot.id,
            "origen": contenido.origen,
            "mensaje": (contenido.mensaje_sugerido or "")[:500],
            "ahora": ahora,
            "id": demo.id,
        },
    )
    if resultado.rowcount != 1:
        db.rollback()
        return False
    db.commit()
    return True


def _marcar_error(db: Session, demo_id: int) -> None:
    try:
        db.rollback()
        db.execute(
            text(
                "UPDATE demos SET estado = :error, updated_at = :ahora "
                "WHERE id = :id AND estado = :generando"
            ),
            {
                "error": models.DEMO_ESTADO_ERROR,
                "generando": models.DEMO_ESTADO_GENERANDO,
                "ahora": datetime.utcnow(),
                "id": demo_id,
            },
        )
        db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("demo: no se pudo marcar el error id=%s", demo_id)
        db.rollback()


def _resolver(db: Session, demo: models.Demo, contenido: demo_bot.ContenidoDemo,
              t0: float) -> None:
    demo_id, tipo = demo.id, demo.tipo_empresa
    try:
        hecho = materializar(db, demo, contenido)
        estado = models.DEMO_ESTADO_LISTA if hecho else "ya_resuelta"
    except Exception:  # noqa: BLE001 — solo un fallo de BD deja la demo en error
        logger.exception("demo: no se pudo guardar el bot id=%s", demo_id)
        _marcar_error(db, demo_id)
        estado = models.DEMO_ESTADO_ERROR
    logger.info(
        "demo generada id=%s tipo=%s estado=%s origen=%s motivo=%s ms=%d",
        demo_id, tipo, estado, contenido.origen, contenido.motivo or "-",
        int((time.monotonic() - t0) * 1000),
    )


def generar_en_fondo(demo_id: int) -> None:
    """Tarea de fondo de `/iniciar`. Abre y cierra su propia sesión."""
    t0 = time.monotonic()
    db = _nueva_sesion()
    try:
        demo = db.query(models.Demo).filter(models.Demo.id == demo_id).first()
        if demo is None or demo.estado != models.DEMO_ESTADO_GENERANDO:
            return
        empresa, tipo, tipo_otro = demo.empresa, demo.tipo_empresa, demo.tipo_otro
        # #635: la conexión vuelve al pool mientras Bedrock genera (hasta ~30 s
        # con la espera del semáforo). Una ráfaga de 20 demos agotó el pool.
        db.rollback()
        try:
            contenido = demo_bot.generar_contenido(empresa, tipo, tipo_otro)
        except Exception:  # noqa: BLE001 — la demo nunca se cae por la generación
            logger.exception("demo: generar_contenido falló id=%s", demo_id)
            contenido = demo_bot.respaldo(None, tipo, motivo="excepcion")
        demo = db.query(models.Demo).filter(models.Demo.id == demo_id).first()
        if demo is None or demo.estado != models.DEMO_ESTADO_GENERANDO:
            return
        _resolver(db, demo, contenido, t0)
    except Exception:  # noqa: BLE001
        logger.exception("demo: tarea de fondo falló id=%s", demo_id)
        _marcar_error(db, demo_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# GET /demo/{demo_id}/estado
# ---------------------------------------------------------------------------

def _productos_de(db: Session, bot_id: Optional[int]) -> List[ProductoOut]:
    if bot_id is None:
        return []
    filas = (
        db.query(models.BotProducto.nombre, models.BotProducto.resumen)
        .join(models.BotProductoBot, models.BotProductoBot.producto_id == models.BotProducto.id)
        .filter(models.BotProductoBot.bot_id == bot_id)
        .order_by(models.BotProductoBot.orden, models.BotProducto.id)
        .all()
    )
    return [ProductoOut(nombre=n, resumen=r or "") for n, r in filas]


@router.get("/{demo_id}/estado", response_model=EstadoOut)
def estado(
    demo_id: str,
    x_demo_token: Optional[str] = Header(default=None, alias="X-Demo-Token"),
    db: Session = Depends(get_db),
):
    demo = _demo_autorizada(db, demo_id, x_demo_token)

    if (
        demo.estado == models.DEMO_ESTADO_GENERANDO
        and demo.created_at is not None
        and demo.created_at < datetime.utcnow() - timedelta(seconds=GENERANDO_VENCE_SEGUNDOS)
    ):
        # La tarea de fondo no terminó (la task se reinició, o algo peor): se
        # resuelve aquí con el respaldo determinista, sin llamar al modelo.
        contenido = demo_bot.respaldo(demo.empresa, demo.tipo_empresa, motivo="vencida")
        _resolver(db, demo, contenido, time.monotonic())
        db.expire_all()
        demo = db.query(models.Demo).filter(models.Demo.id == demo.id).first()

    out = EstadoOut(estado=demo.estado, empresa=demo.empresa)
    if demo.estado == models.DEMO_ESTADO_LISTA:
        out.productos = _productos_de(db, demo.bot_id)
        out.mensaje_sugerido = demo.mensaje_sugerido
    return out


# ---------------------------------------------------------------------------
# POST /demo/{demo_id}/chat
# ---------------------------------------------------------------------------

_SEM_TURNOS = threading.BoundedSemaphore(_env_int("DEMO_TURNOS_SIMULTANEOS", 4))


def _espera_turno_s() -> float:
    """Cuánto espera un turno por un cupo antes de «muy solicitada» (#635).
    0 = no espera (el comportamiento de siempre). En la ráfaga de 20 chats a la
    vez, sin espera 26 de 60 turnos salían «muy solicitada»."""
    try:
        return max(0.0, min(float(os.getenv("DEMO_TURNO_ESPERA_S", "0") or 0), 20.0))
    except ValueError:
        return 0.0


def _tomar_cupo_de_turno() -> bool:
    espera = _espera_turno_s()
    if espera <= 0:
        return _SEM_TURNOS.acquire(blocking=False)
    return _SEM_TURNOS.acquire(timeout=espera)
_RATE_TURNOS = ratelimit.SlidingWindow(
    por_ip=_env_int("DEMO_TURNOS_IP_HORA", 60),
    global_=_env_int("DEMO_TURNOS_GLOBAL_HORA", 200),
)
#: Demos con un turno en curso: dos turnos simultáneos de la MISMA demo se
#: pisarían el historial. El segundo recibe "muy solicitada" sin gastar turno.
_EN_CURSO: set = set()
_EN_CURSO_LOCK = threading.Lock()


def _solo_texto(texto: str, *, finished: bool = False) -> ChatOut:
    return ChatOut(
        actions=[ChatAction(type="say", text=texto)], session=None,
        finished=finished, handoff=False,
    )


def _telemetria_sin_texto(tel: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """La telemetría del turno sin una palabra del visitante ni del bot.

    `record_decision` guarda `user_input`, `reply_preview` y las entradas y
    resultados de las herramientas (el `resumen` de un escalamiento repite lo
    que dijo el cliente). En la demo la transcripción vive en un solo lugar,
    `demos.transcripcion`; aquí quedan el camino, los nombres de las
    herramientas, latencia, rondas y tokens (el costo)."""
    if not tel:
        return None
    limpia = dict(tel)
    limpia["user_input"] = None
    limpia["reply_preview"] = None
    limpia["bookings"] = []
    limpia["pedidos"] = []
    limpia.pop("intenciones", None)
    limpia["tools"] = [{"tool": str(t.get("tool") or "?")} for t in tel.get("tools") or []]
    return limpia


def _historial(state: Any) -> List[Dict[str, str]]:
    if not isinstance(state, dict):
        return []
    h = state.get("history")
    return [m for m in h if isinstance(m, dict)] if isinstance(h, list) else []


@router.post("/{demo_id}/chat", response_model=ChatOut)
def chat(
    demo_id: str,
    payload: ChatIn,
    request: Request,
    x_demo_token: Optional[str] = Header(default=None, alias="X-Demo-Token"),
    db: Session = Depends(get_db),
):
    demo = _demo_autorizada(db, demo_id, x_demo_token)
    if demo.estado != models.DEMO_ESTADO_LISTA or demo.bot_id is None:
        raise HTTPException(status_code=409, detail="La demo aún se está preparando")
    mensaje = payload.message
    if not mensaje:
        raise HTTPException(status_code=422, detail="Escribe un mensaje")

    if not _RATE_TURNOS.allow(_ip_cliente(request)):
        logger.warning("demo chat: rate-limit de turnos id=%s", demo.id)
        return _solo_texto(TEXTO_MUY_SOLICITADA)
    if turnos_del_mes(db) >= _tope("DEMO_MAX_TURNOS_MES"):
        logger.warning("demo chat: freno mensual de turnos alcanzado")
        return _solo_texto(TEXTO_MUY_SOLICITADA)

    dueno = _dueno_demos(db)
    if dueno is None:
        logger.error("demo chat: no existe la cuenta dueña de las demos")
        return _solo_texto(TEXTO_MUY_SOLICITADA)
    # M6: el bot sale de la fila de la demo y tiene que ser de la cuenta de
    # demos y LLM. El cliente nunca nombra un bot.
    bot = (
        db.query(models.Bot)
        .filter(
            models.Bot.id == demo.bot_id,
            models.Bot.user_id == dueno[0],
            models.Bot.engine == "llm",
        )
        .first()
    )
    if bot is None:
        raise _no_encontrada()

    with _EN_CURSO_LOCK:
        if demo.id in _EN_CURSO:
            return _solo_texto(TEXTO_MUY_SOLICITADA)
        _EN_CURSO.add(demo.id)
    try:
        if not _tomar_cupo_de_turno():
            logger.warning("demo chat: semáforo de turnos lleno id=%s", demo.id)
            return _solo_texto(TEXTO_MUY_SOLICITADA)
        try:
            return _turno(db, demo, bot, mensaje)
        finally:
            _SEM_TURNOS.release()
    finally:
        with _EN_CURSO_LOCK:
            _EN_CURSO.discard(demo.id)


def _turno(db: Session, demo: models.Demo, bot: models.Bot, mensaje: str) -> ChatOut:
    maximo = _tope("DEMO_MAX_TURNOS")
    turnos = db.execute(
        text(
            "UPDATE demos SET turnos = turnos + 1 "
            "WHERE id = :id AND turnos < :max RETURNING turnos"
        ),
        {"id": demo.id, "max": maximo},
    ).scalar()
    db.commit()
    if turnos is None:
        return _solo_texto(TEXTO_FIN_TURNOS, finished=True)

    previo = _historial(demo.chat_state)
    # #635: el turno no retiene una conexión de la base mientras habla con
    # Bedrock (hasta 25 s): el bot queda suelto de la sesión con lo ya cargado y
    # la transacción se cierra. Con 10 turnos a la vez el pool se agotaba.
    demo_id = demo.id
    db.refresh(bot)          # el commit del contador lo dejó expirado
    db.expunge(bot)
    db.rollback()
    result = llm_engine.advance(bot, {"history": previo} if previo else None, mensaje)
    llm_engine.record_decision(
        db, bot, _telemetria_sin_texto(result.get("telemetry")),
        source="demo", chat_ref=f"demo-{demo_id}",
    )

    actions: List[ChatAction] = []
    textos: List[str] = []
    handoff = False
    terminado = False
    for act in result.get("actions") or []:
        kind = act.get("type")
        data = act.get("payload") or {}
        if kind == "say":
            # La narración ya la recortó el motor (`llm_engine._postproceso_demo`),
            # antes de guardar el historial.
            texto = (data.get("text") or "").strip()
            if texto:
                actions.append(ChatAction(type="say", text=texto))
                textos.append(texto)
        elif kind == "handoff":
            # Sin teléfono ni WhatsApp de Gloma: el front muestra la tarjeta
            # «aquí entra tu equipo».
            handoff = True
        elif kind == "end":
            terminado = True
        # `say_media` se descarta: el bot de demo no tiene medios.
    if handoff and not actions:
        actions.append(ChatAction(type="say", text=TEXTO_HANDOFF))
        textos.append(TEXTO_HANDOFF)

    finished = bool(result.get("finished")) or handoff or terminado or turnos >= maximo
    if turnos >= maximo and not (handoff or terminado or result.get("finished")):
        actions.append(ChatAction(type="say", text=TEXTO_CIERRE_DEMO))

    # Historial en la fila (A3). Si el motor cerró la conversación devuelve
    # `next_state=None`; aquí se conserva igual, para que un mensaje más
    # después del traspaso no arranque una conversación de cero.
    nuevo = result.get("next_state")
    historia = _historial(nuevo)
    if not historia:
        historia = (previo + [
            {"role": "user", "content": mensaje},
            {"role": "assistant", "content": "\n\n".join(textos) or "(sin texto)"},
        ])[-llm_engine._MAX_HISTORY_MESSAGES:]
    estado_chat: Dict[str, Any] = dict(nuevo) if isinstance(nuevo, dict) else {}
    estado_chat["history"] = historia

    ahora = datetime.utcnow().isoformat(timespec="seconds")
    transcripcion = list(demo.transcripcion or [])
    transcripcion.append({"rol": "usuario", "texto": mensaje[:MAX_TRANSCRIPCION_TEXTO], "at": ahora})
    transcripcion.append({
        "rol": "bot",
        "texto": ("\n\n".join(textos) or "")[:MAX_TRANSCRIPCION_TEXTO],
        "at": ahora,
    })
    demo.chat_state = estado_chat
    demo.transcripcion = transcripcion[-2 * maximo:]
    if handoff and demo.traspaso_at is None:
        # #627: el primer traspaso a asesor queda en la fila (panel del admin).
        demo.traspaso_at = datetime.utcnow()
    db.commit()

    return ChatOut(
        actions=actions,
        session=None,
        finished=finished,
        handoff=handoff,
    )


# ---------------------------------------------------------------------------
# POST /demo/{demo_id}/evento (#627): clics del CTA para el panel del admin
# ---------------------------------------------------------------------------

EVENTOS_DEMO = ("whatsapp", "llamada_abierta", "llamada_agendada")
TECHO_CONTADOR_EVENTO = 100
#: #629: 30 eventos por IP y 2.000 globales por HORA. Por encima se responde
#: el mismo 204 sin escribir: el navegador no tiene nada que reintentar y un
#: script no aprende dónde está el tope.
_RATE_EVENTOS = ratelimit.SlidingWindow(
    por_ip=_env_int("DEMO_EVENTOS_IP_HORA", 30),
    global_=_env_int("DEMO_EVENTOS_GLOBAL_HORA", 2000),
)


class EventoIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["whatsapp", "llamada_abierta", "llamada_agendada"]


_SQL_EVENTO = {
    "whatsapp": (
        "UPDATE demos SET clics_whatsapp = LEAST(clics_whatsapp + 1, :techo), "
        "primer_clic_whatsapp_at = COALESCE(primer_clic_whatsapp_at, :ahora) "
        "WHERE id = :id"
    ),
    "llamada_abierta": (
        "UPDATE demos SET aperturas_llamada = LEAST(aperturas_llamada + 1, :techo), "
        "primer_apertura_llamada_at = COALESCE(primer_apertura_llamada_at, :ahora) "
        "WHERE id = :id"
    ),
    # Solo si antes abrió el agendador (#629): un «agendada» sin apertura es
    # un evento fabricado. Lo reporta el navegador y no dispara nada de negocio.
    "llamada_agendada": (
        "UPDATE demos SET llamada_agendada_at = COALESCE(llamada_agendada_at, :ahora) "
        "WHERE id = :id AND aperturas_llamada > 0"
    ),
}


def _sql_de(tipo: str, dialecto: str) -> str:
    """`LEAST` es de Postgres; SQLite (la suite) tiene `MIN` con dos
    argumentos, que hace lo mismo."""
    sql = _SQL_EVENTO[tipo]
    return sql.replace("LEAST(", "MIN(") if dialecto == "sqlite" else sql


@router.post("/{demo_id}/evento", status_code=204)
def evento(
    demo_id: str,
    request: Request,
    cuerpo: Any = Body(default=None),
    x_demo_token: Optional[str] = Header(default=None, alias="X-Demo-Token"),
    db: Session = Depends(get_db),
):
    """Un clic del CTA dentro de una demo: abrir WhatsApp, abrir el agendador
    o agendar la llamada. Vale en cualquier estado de la demo (el CTA se ve
    también mientras genera o si falló). Atómico y con techo en la base, sin
    leer y escribir. Siempre 204, también en el techo o el rate-limit."""
    demo = _demo_autorizada(db, demo_id, x_demo_token)
    # El cuerpo se valida aquí y no en la firma (#632): así el 404 uniforme va
    # primero, y un 422 no le devuelve al navegador el detalle de Pydantic con
    # lo que mandó.
    try:
        payload = EventoIn.model_validate(cuerpo)
    except ValidationError:
        raise HTTPException(status_code=422, detail="Solicitud inválida")
    if not _RATE_EVENTOS.allow(_ip_cliente(request)):
        logger.warning("demo evento: rate-limit id=%s tipo=%s", demo.id, payload.tipo)
        return Response(status_code=204)
    db.execute(
        text(_sql_de(payload.tipo, db.get_bind().dialect.name)),
        {"id": demo.id, "techo": TECHO_CONTADOR_EVENTO, "ahora": datetime.utcnow()},
    )
    db.commit()
    logger.info("demo evento id=%s tipo=%s", demo.id, payload.tipo)
    return Response(status_code=204)

