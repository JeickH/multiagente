"""Panel del admin de Gloma: quiénes usaron la demo pública (Sprint 32, #627).

Solo para el dueño de la cuenta de Gloma y los miembros de su team que tengan
la llave `ver_demos` (`require_gloma_account`, el portero de `/citas`, más
`require_ver_demos`): cualquier otra sesión recibe 403. Revisión #629: teléfono
y correo enmascarados en la lista, `Cache-Control: no-store`, log de auditoría
con el `user_id` y sin PII, y rango de fechas de 366 días como máximo.

- `GET /admin/demos/access`       → {allowed} para el menú.
- `GET /admin/demos`              → resumen + lista paginada con filtros.
- `GET /admin/demos/{public_id}`  → una demo con sus productos, la transcripción
  y el consentimiento.

Demos internas (pruebas de QA y del equipo): las de un lead cuyo correo termina
en un dominio de `DEMO_DOMINIOS_INTERNOS` (default `example.com,glomacx.com,
glomabeauty.com`). La lista y el resumen las ocultan salvo `incluir_internas`.

Contiene PII de prospectos (nombre, correo, teléfono, la transcripción): es lo
que el equipo de ventas necesita para llamar, y por eso solo se sirve detrás del
portero. Lo que es del sistema NO sale nunca: ni el token de la demo, ni
`chat_state`, ni la IP, ni el user agent, ni el id serial de la fila. Los logs
llevan solo ids (regla #1) y los errores al cliente son genéricos (regla #6).

Fechas: las columnas guardan UTC sin zona (como el resto de la app; el front las
formatea con `lib/fechas.ts`). Los filtros `desde`/`hasta` son días de Colombia
(UTC-5): `desde=2026-10-17` arranca a las 05:00 UTC de ese día.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from .. import crud, models
from ..dependencies import GLOMA_EMAIL, get_current_user, get_db, require_gloma_account
from ..services import demo_bot

logger = logging.getLogger(__name__)

#: Llave de permiso para ver el panel siendo miembro (no dueño) del team de
#: Gloma (#629). `crud.member_has_permission` lee cualquier llave guardada en
#: `team_permissions`; para poder otorgarla desde la app falta sumarla a
#: `models.AVAILABLE_PERMISSIONS` (ver el reporte de #627).
PERMISO_VER_DEMOS = "ver_demos"

PAGE_SIZE_DEFAULT = 25
PAGE_SIZE_MAX = 100
RANGO_MAX_DIAS = 366
_TZ_CO = timedelta(hours=5)       # Colombia es UTC-5, sin horario de verano
_SIN_CACHE = {"Cache-Control": "no-store"}


def require_ver_demos(
    user: models.User = Depends(require_gloma_account),
    db: Session = Depends(get_db),
) -> models.User:
    """El dueño de la cuenta de Gloma, o un miembro de su team con `ver_demos`.

    `require_gloma_account` ya dejó pasar solo a la cuenta de Gloma y a su team;
    aquí además el miembro necesita la llave: el panel trae PII de prospectos.
    """
    if (user.correo or "").lower() == GLOMA_EMAIL:
        return user
    owner = db.query(models.User).filter(models.User.correo == GLOMA_EMAIL).first()
    member = None
    if owner is not None:
        member = (
            db.query(models.TeamMember)
            .join(models.Team, models.Team.id == models.TeamMember.team_id)
            .filter(
                models.TeamMember.user_id == user.id,
                models.Team.owner_user_id == owner.id,
            )
            .first()
        )
    if member is not None and (
        member.role == "owner" or crud.member_has_permission(member, PERMISO_VER_DEMOS)
    ):
        return user
    raise HTTPException(status_code=403, detail="No tienes acceso a este módulo")


router = APIRouter(prefix="/admin/demos", tags=["admin-demos"])


# ---------------------------------------------------------------------------
# Demos internas (pruebas de QA y del equipo): por dominio del correo del lead
# ---------------------------------------------------------------------------

_DOMINIOS_INTERNOS_DEFAULT = "example.com,glomacx.com,glomabeauty.com"


def dominios_internos() -> List[str]:
    crudo = os.getenv("DEMO_DOMINIOS_INTERNOS", "").strip() or _DOMINIOS_INTERNOS_DEFAULT
    return [d.strip().lower().lstrip("@") for d in crudo.split(",") if d.strip()]


def _es_interna_sql():
    """Expresión SQL: el correo del lead termina en «@<dominio interno>». Sin
    lead (borrado), no es interna."""
    correo = func.lower(models.Lead.email)
    return or_(*[correo.like(f"%@{d}") for d in dominios_internos()]) \
        if dominios_internos() else False


def es_interna(correo: Optional[str]) -> bool:
    correo = (correo or "").lower()
    return bool(correo) and any(correo.endswith("@" + d) for d in dominios_internos())


# ---------------------------------------------------------------------------
# Schemas de salida (sin nada sensible del sistema)
# ---------------------------------------------------------------------------

class AccesoDemosOut(BaseModel):
    allowed: bool


class PorEstadoOut(BaseModel):
    modelo: int
    respaldo: int
    generando: int
    error: int


class ResumenDemosOut(BaseModel):
    demos: int
    conversaron: int
    traspaso: int
    clic_whatsapp: int
    abrieron_llamada: int
    agendaron_llamada: int
    pidieron_hablar: int = Field(
        description="Demos con al menos un clic a WhatsApp o una apertura del "
                    "agendador (cada demo cuenta una vez)."
    )
    por_estado: PorEstadoOut


class DemoAdminItemOut(BaseModel):
    """Una demo en la lista. Teléfono y correo van ENMASCARADOS (#629):
    completos solo en el detalle."""

    public_id: str
    created_at: datetime
    nombre: Optional[str] = None
    empresa: str
    tipo_empresa: str
    tipo_otro: Optional[str] = None
    tipo_empresa_label: str
    telefono: Optional[str] = None
    correo: Optional[str] = None
    acepta_promociones: bool
    estado: str
    origen_productos: Optional[str] = None
    turnos: int
    traspaso_at: Optional[datetime] = None
    clics_whatsapp: int
    aperturas_llamada: int
    llamada_agendada_at: Optional[datetime] = Field(
        default=None,
        description="Reportada por el navegador (evento del agendador): no es una "
                    "confirmación del calendario.",
    )
    interna: bool
    lead_borrado: bool
    bot_eliminado_at: Optional[datetime] = Field(
        default=None,
        description="Cuándo se borró el bot por inactividad (#638). Los datos del "
                    "prospecto se conservan; los productos salen del snapshot.",
    )


class DemoAdminListaOut(BaseModel):
    resumen: ResumenDemosOut
    total: int
    page: int
    page_size: int
    items: List[DemoAdminItemOut]


class ProductoDemoOut(BaseModel):
    nombre: str
    resumen: Optional[str] = None
    ficha: Optional[str] = None
    precio_cop: Optional[int] = None
    unidad_precio: Optional[str] = None


class MensajeTranscripcionOut(BaseModel):
    rol: str
    texto: str
    at: Optional[str] = None


class UsoModeloOut(BaseModel):
    modelo: Optional[str] = None
    decisiones: int = 0
    rondas: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    sin_tokens: int = 0
    costo_usd_estimado: Optional[float] = None


class UsoResumenOut(BaseModel):
    """Consumo del bot, copiado antes de borrarlo (#638). Solo existe en las
    demos con el bot ya eliminado."""

    turnos: int = 0
    decisiones: int = 0
    rondas: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cache_read: int = 0
    cache_write: int = 0
    sin_tokens: int = 0
    failsafe: int = 0
    escalados: int = 0
    modelos: List[str] = []
    por_modelo: List[UsoModeloOut] = []
    latencia_ms_promedio: Optional[int] = None
    primera_decision_at: Optional[str] = None
    ultima_decision_at: Optional[str] = None
    costo_usd_estimado: Optional[float] = None
    nota_costo: Optional[str] = None


class DemoAdminDetalleOut(DemoAdminItemOut):
    """El detalle, con teléfono y correo completos y el consentimiento."""

    acepto_contacto_at: Optional[datetime] = None
    acepta_promociones_at: Optional[datetime] = None
    consent_version: Optional[str] = None
    lista_at: Optional[datetime] = None
    primer_clic_whatsapp_at: Optional[datetime] = None
    primer_apertura_llamada_at: Optional[datetime] = None
    productos: List[ProductoDemoOut]
    transcripcion: List[MensajeTranscripcionOut]
    uso_resumen: Optional[UsoResumenOut] = None
    # #644: el correo automático de la promoción. Estado `enviado|omitido|error`
    # o null (no se intentó: envío apagado o demo anterior).
    correo_promo_enviado_at: Optional[datetime] = None
    correo_promo_estado: Optional[str] = None


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

ESTADOS_FILTRO = ("generando", "lista", "error", "modelo", "respaldo")
ETAPAS_FILTRO = (
    "conversaron", "traspaso", "whatsapp", "llamada_abierta", "llamada_agendada",
    "pidieron_hablar",
)


def _inicio_dia_co(d: date) -> datetime:
    """00:00 de ese día en Colombia, en UTC sin zona (como `created_at`)."""
    return datetime.combine(d, time.min) + _TZ_CO


def _filtros_rango(desde: Optional[date], hasta: Optional[date],
                   incluir_internas: bool) -> list:
    """Rango de fechas e internas: lo único que filtra el resumen."""
    if desde and hasta and hasta < desde:
        raise HTTPException(status_code=422, detail="El rango de fechas no es válido")
    fin = hasta or (datetime.utcnow() - _TZ_CO).date()
    if desde and (fin - desde).days > RANGO_MAX_DIAS:
        raise HTTPException(status_code=422, detail="El rango de fechas es demasiado largo")
    filtros = []
    if desde:
        filtros.append(models.Demo.created_at >= _inicio_dia_co(desde))
    if hasta:
        filtros.append(models.Demo.created_at < _inicio_dia_co(hasta + timedelta(days=1)))
    if not incluir_internas and dominios_internos():
        filtros.append(or_(models.Lead.id.is_(None), ~_es_interna_sql()))
    return filtros


_PIDIERON_HABLAR = or_(models.Demo.clics_whatsapp > 0, models.Demo.aperturas_llamada > 0)


def _filtro_etapa(etapa: str):
    D = models.Demo
    return {
        "conversaron": D.turnos > 0,
        "traspaso": D.traspaso_at.isnot(None),
        "whatsapp": D.clics_whatsapp > 0,
        "llamada_abierta": D.aperturas_llamada > 0,
        "llamada_agendada": D.llamada_agendada_at.isnot(None),
        "pidieron_hablar": _PIDIERON_HABLAR,
    }[etapa]


def _filtro_estado(estado: str):
    D = models.Demo
    if estado in ("modelo", "respaldo"):
        return (D.estado == models.DEMO_ESTADO_LISTA) & (D.origen_productos == estado)
    return D.estado == estado


def _etiqueta(demo: models.Demo) -> str:
    etiqueta = demo_bot.TIPOS_EMPRESA.get(demo.tipo_empresa, demo.tipo_empresa)
    if demo.tipo_empresa == "otro" and demo.tipo_otro:
        return f"{etiqueta}: {demo.tipo_otro}"
    return etiqueta


def enmascarar_telefono(tel: Optional[str]) -> Optional[str]:
    """`+573001234567` → `+57 300 ••• 4567`."""
    if not tel:
        return None
    digitos = "".join(c for c in tel if c.isdigit())
    if len(digitos) < 7:
        return "•••"
    if tel.startswith("+57") and len(digitos) == 12:
        return f"+57 {digitos[2:5]} ••• {digitos[-4:]}"
    return f"+{digitos[:3]} ••• {digitos[-4:]}"


def enmascarar_correo(correo: Optional[str]) -> Optional[str]:
    """`camila.ruiz@dominio.com` → `ca•••@dominio.com`."""
    if not correo or "@" not in correo:
        return None if not correo else "•••"
    local, dominio = correo.rsplit("@", 1)
    return f"{local[:2]}•••@{dominio}"


def _item(demo: models.Demo, lead: Optional[models.Lead], *, completo: bool) -> Dict[str, Any]:
    telefono = lead.telefono if lead else None
    correo = lead.email if lead else None
    interna = es_interna(correo)
    if not completo:
        telefono, correo = enmascarar_telefono(telefono), enmascarar_correo(correo)
    return {
        "public_id": str(demo.public_id),
        "created_at": demo.created_at,
        "nombre": lead.nombre if lead else None,
        "empresa": demo.empresa,
        "tipo_empresa": demo.tipo_empresa,
        "tipo_otro": demo.tipo_otro,
        "tipo_empresa_label": _etiqueta(demo),
        "telefono": telefono,
        "correo": correo,
        "acepta_promociones": bool(demo.acepta_promociones),
        "estado": demo.estado,
        "origen_productos": demo.origen_productos,
        "turnos": int(demo.turnos or 0),
        "traspaso_at": demo.traspaso_at,
        "clics_whatsapp": int(demo.clics_whatsapp or 0),
        "aperturas_llamada": int(demo.aperturas_llamada or 0),
        "llamada_agendada_at": demo.llamada_agendada_at,
        "interna": interna,
        "lead_borrado": lead is None,
        "bot_eliminado_at": demo.bot_eliminado_at,
    }


def _suma(condicion):
    return func.coalesce(func.sum(case((condicion, 1), else_=0)), 0)


def _resumen(db: Session, filtros: list) -> ResumenDemosOut:
    """Por agregados SQL, en UNA consulta, con el rango y las internas."""
    D = models.Demo
    lista = D.estado == models.DEMO_ESTADO_LISTA
    fila = (
        db.query(
            func.count(D.id),
            _suma(D.turnos > 0),
            _suma(D.traspaso_at.isnot(None)),
            _suma(D.clics_whatsapp > 0),
            _suma(D.aperturas_llamada > 0),
            _suma(D.llamada_agendada_at.isnot(None)),
            _suma(_PIDIERON_HABLAR),
            _suma(lista & (D.origen_productos == models.DEMO_ORIGEN_MODELO)),
            _suma(lista & (D.origen_productos == models.DEMO_ORIGEN_RESPALDO)),
            _suma(D.estado == models.DEMO_ESTADO_GENERANDO),
            _suma(D.estado == models.DEMO_ESTADO_ERROR),
        )
        .select_from(D)
        .outerjoin(models.Lead, models.Lead.id == D.lead_id)
        .filter(*filtros)
        .one()
    )
    n = [int(x or 0) for x in fila]
    return ResumenDemosOut(
        demos=n[0], conversaron=n[1], traspaso=n[2], clic_whatsapp=n[3],
        abrieron_llamada=n[4], agendaron_llamada=n[5], pidieron_hablar=n[6],
        por_estado=PorEstadoOut(modelo=n[7], respaldo=n[8], generando=n[9], error=n[10]),
    )


# ---------------------------------------------------------------------------
# GET /admin/demos/access
# ---------------------------------------------------------------------------

@router.get("/access", response_model=AccesoDemosOut)
def acceso_demos(
    response: Response,
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """¿Esta sesión puede ver el panel? Para el menú. Siempre 200, con la misma
    regla del panel (portero de Gloma + dueño o `ver_demos`)."""
    response.headers.update(_SIN_CACHE)
    try:
        require_ver_demos(user=require_gloma_account(user=user, db=db), db=db)
    except HTTPException:
        return AccesoDemosOut(allowed=False)
    return AccesoDemosOut(allowed=True)


# ---------------------------------------------------------------------------
# GET /admin/demos
# ---------------------------------------------------------------------------

@router.get("", response_model=DemoAdminListaOut)
def listar_demos(
    response: Response,
    desde: Optional[date] = Query(default=None, description="Día de Colombia, AAAA-MM-DD"),
    hasta: Optional[date] = Query(default=None, description="Día de Colombia, incluido"),
    incluir_internas: bool = Query(default=False),
    q: Optional[str] = Query(default=None, max_length=80),
    tipo: Optional[str] = Query(default=None, max_length=40),
    estado: Optional[str] = Query(default=None, max_length=16),
    etapa: Optional[str] = Query(default=None, max_length=24),
    page: int = Query(default=1, ge=1, le=10_000),
    page_size: int = Query(default=PAGE_SIZE_DEFAULT, ge=1, le=PAGE_SIZE_MAX),
    db: Session = Depends(get_db),
    user: models.User = Depends(require_ver_demos),
):
    response.headers.update(_SIN_CACHE)
    if tipo and tipo not in demo_bot.TIPOS_EMPRESA:
        raise HTTPException(status_code=422, detail="Tipo de empresa inválido")
    if estado and estado not in ESTADOS_FILTRO:
        raise HTTPException(status_code=422, detail="Estado inválido")
    if etapa and etapa not in ETAPAS_FILTRO:
        raise HTTPException(status_code=422, detail="Etapa inválida")

    rango = _filtros_rango(desde, hasta, incluir_internas)
    resumen = _resumen(db, rango)

    filtros = list(rango)
    if tipo:
        filtros.append(models.Demo.tipo_empresa == tipo)
    if estado:
        filtros.append(_filtro_estado(estado))
    if etapa:
        filtros.append(_filtro_etapa(etapa))
    texto = (q or "").strip()
    if texto:
        # Server-side y sobre los datos COMPLETOS (la lista los enmascara). Sin
        # comodines del usuario; nunca por teléfono.
        patron = "%" + texto.replace("\\", "").replace("%", "").replace("_", "") + "%"
        filtros.append(or_(
            models.Demo.empresa.ilike(patron),
            models.Lead.nombre.ilike(patron),
            models.Lead.email.ilike(patron),
        ))

    consulta = (
        db.query(models.Demo, models.Lead)
        .outerjoin(models.Lead, models.Lead.id == models.Demo.lead_id)
        .filter(*filtros)
    )
    total = consulta.order_by(None).count()
    filas = (
        consulta.order_by(models.Demo.created_at.desc(), models.Demo.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    logger.info("admin_demos lista user_id=%s pagina=%s", user.id, page)
    return DemoAdminListaOut(
        resumen=resumen,
        total=total,
        page=page,
        page_size=page_size,
        items=[DemoAdminItemOut(**_item(d, l, completo=False)) for d, l in filas],
    )


# ---------------------------------------------------------------------------
# GET /admin/demos/{public_id}
# ---------------------------------------------------------------------------

def _productos(db: Session, bot_id: Optional[int]) -> List[ProductoDemoOut]:
    if bot_id is None:
        return []
    productos = (
        db.query(models.BotProducto)
        .join(models.BotProductoBot, models.BotProductoBot.producto_id == models.BotProducto.id)
        .filter(models.BotProductoBot.bot_id == bot_id)
        .order_by(models.BotProductoBot.orden, models.BotProducto.id)
        .all()
    )
    if not productos:
        return []
    # El precio es plano: la primera fila (orden 0) de cada producto.
    filas = (
        db.query(models.BotProductoFila)
        .filter(models.BotProductoFila.producto_id.in_([p.id for p in productos]))
        .order_by(models.BotProductoFila.producto_id, models.BotProductoFila.orden)
        .all()
    )
    primera: Dict[int, models.BotProductoFila] = {}
    for f in filas:
        primera.setdefault(f.producto_id, f)
    salida = []
    for p in productos:
        valores = (primera[p.id].valores or {}) if p.id in primera else {}
        precio = valores.get("precio")
        salida.append(ProductoDemoOut(
            nombre=p.nombre,
            resumen=p.resumen,
            ficha=p.instrucciones,
            precio_cop=int(precio) if isinstance(precio, (int, float)) and not isinstance(precio, bool) else None,
            unidad_precio=str(valores.get("unidad")) if valores.get("unidad") else None,
        ))
    return salida


def _productos_del_detalle(db: Session, demo: models.Demo) -> List[ProductoDemoOut]:
    """Del bot si todavía existe; si se borró por inactividad (#638), del
    snapshot que se copió antes de borrarlo."""
    if demo.bot_id is not None:
        return _productos(db, demo.bot_id)
    salida = []
    for p in demo.productos_snapshot or []:
        if not isinstance(p, dict):
            continue
        precio = p.get("precio_cop")
        salida.append(ProductoDemoOut(
            nombre=str(p.get("nombre") or ""),
            resumen=p.get("resumen"),
            ficha=p.get("ficha"),
            precio_cop=int(precio) if isinstance(precio, (int, float)) and not isinstance(precio, bool) else None,
            unidad_precio=p.get("unidad_precio"),
        ))
    return salida


def _uso(demo: models.Demo) -> Optional[UsoResumenOut]:
    if not isinstance(demo.uso_resumen, dict):
        return None
    try:
        return UsoResumenOut(**{k: v for k, v in demo.uso_resumen.items()
                                if k in UsoResumenOut.model_fields})
    except Exception:  # noqa: BLE001 — un JSON raro no tumba el detalle
        logger.warning("admin_demos: uso_resumen ilegible demo_id=%s", demo.id)
        return None


def _transcripcion(demo: models.Demo) -> List[MensajeTranscripcionOut]:
    salida = []
    for m in demo.transcripcion or []:
        if not isinstance(m, dict):
            continue
        salida.append(MensajeTranscripcionOut(
            rol=str(m.get("rol") or ""),
            texto=str(m.get("texto") or ""),
            at=str(m.get("at")) if m.get("at") else None,
        ))
    return salida


@router.get("/{public_id}", response_model=DemoAdminDetalleOut)
def detalle_demo(
    public_id: str,
    response: Response,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_ver_demos),
):
    response.headers.update(_SIN_CACHE)
    try:
        pid = uuid.UUID(str(public_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=404, detail="Demo no encontrada")
    fila = (
        db.query(models.Demo, models.Lead)
        .outerjoin(models.Lead, models.Lead.id == models.Demo.lead_id)
        .filter(models.Demo.public_id == pid)
        .first()
    )
    if fila is None:
        raise HTTPException(status_code=404, detail="Demo no encontrada")
    demo, lead = fila
    logger.info("admin_demos detalle user_id=%s demo_id=%s", user.id, demo.id)
    return DemoAdminDetalleOut(
        **_item(demo, lead, completo=True),
        acepto_contacto_at=demo.acepta_contacto_at,
        acepta_promociones_at=demo.acepta_promociones_at,
        consent_version=demo.consent_version,
        lista_at=demo.lista_at,
        primer_clic_whatsapp_at=demo.primer_clic_whatsapp_at,
        primer_apertura_llamada_at=demo.primer_apertura_llamada_at,
        productos=_productos_del_detalle(db, demo),
        transcripcion=_transcripcion(demo),
        uso_resumen=_uso(demo),
        correo_promo_enviado_at=demo.correo_promo_enviado_at,
        correo_promo_estado=demo.correo_promo_estado,
    )
