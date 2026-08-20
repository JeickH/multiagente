"""Ventana de supervisión: las conversaciones de otras cuentas, en modo lectura.

Por qué existe: `gloma@glomabeauty.com` opera la plataforma y necesita ver cómo
les está yendo a los bots de los clientes — si contestan bien, si alguien quedó
esperando, si el motor falló — sin tener que entrar con la contraseña de cada
cuenta. La bandeja normal (`/mensajes`) sigue siendo la de la cuenta propia y no
cambia: ahí Gloma ve las conversaciones de SU bot, y nada más.

Qué se ve aquí:
  - `GET /supervision/access`                    ¿esta sesión ve el módulo? (menú)
  - `GET /supervision/cuentas`                   qué cuentas puede mirar y cuánto hay
  - `GET /supervision/conversaciones?cuenta=..`  un renglón por hilo
  - `GET /supervision/conversaciones/{hilo_id}`  los mensajes de un hilo

Qué NO se puede hacer: escribir. Todos los endpoints son GET a propósito. Esta
ventana es para mirar; responderle a un contacto se hace desde la cuenta dueña
de la conversación, que es la que tiene el WhatsApp conectado.

Quién entra: solo la cuenta de Gloma y los miembros de su team
(`require_gloma_account`, el mismo portero de `/citas` e `/instagram`).
Cualquier otra sesión recibe 403 — incluida la cuenta dueña de las
conversaciones, que para sus propios chats tiene su propio panel.

Qué cuentas se supervisan: las de `SUPERVISION_CUENTAS` (correos separados por
coma). Por defecto, mascotas y Arranquemos Pues. Es una lista blanca explícita,
no "todas las cuentas": mirar los chats de un cliente es algo que se habilita a
propósito, cuenta por cuenta.

De dónde salen las conversaciones. Hay dos registros distintos y ninguno cubre
al otro, así que se leen los dos:
  - `conversations` + `messages` → los chats de WhatsApp. Es el registro
    completo: incluye lo que escribió un asesor humano después del handoff, que
    la bitácora del bot no ve.
  - `bot_llm_decisions` → los chats web (el bot de mascotas es anónimo y no
    tiene `conversation_id`), y las pruebas del simulador. Ahí el texto del bot
    viene recortado a 300 caracteres, y la respuesta lo marca como tal en vez
    de aparentar que ese era el mensaje completo.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from .. import models
from ..dependencies import get_current_user, get_db, require_gloma_account
from ..services import caminos as svc_caminos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supervision", tags=["supervision"])


# ---------------------------------------------------------------------------
# Qué cuentas se pueden mirar
# ---------------------------------------------------------------------------

_CUENTAS_DEFAULT = "recuperatumascota@gmail.com,arranquemospues.marketing@gmail.com"


def cuentas_supervisadas() -> List[str]:
    """Correos habilitados, en el orden en que se muestran en la ventana."""
    # Un `SUPERVISION_CUENTAS=""` (que es lo que deja un passthrough de
    # docker-compose cuando la variable no está definida) cae en la lista por
    # defecto en vez de dejar la ventana vacía sin explicación.
    crudo = os.getenv("SUPERVISION_CUENTAS", "").strip() or _CUENTAS_DEFAULT
    vistos: List[str] = []
    for parte in crudo.split(","):
        correo = parte.strip().lower()
        if correo and correo not in vistos:
            vistos.append(correo)
    return vistos


def _slug(correo: str) -> str:
    """Identificador corto y estable de una cuenta, para la URL y las pestañas.

    Sale del correo (`recuperatumascota@gmail.com` → `recuperatumascota`) y no
    del nombre del team, que el dueño puede cambiar cuando quiera.
    """
    return re.sub(r"[^a-z0-9]+", "-", correo.split("@")[0].lower()).strip("-")


class _Cuenta:
    """Una cuenta supervisada ya resuelta contra la base: su dueño, su team y
    sus bots. Se arma una vez por request y se reusa en todo el endpoint."""

    def __init__(self, correo: str, user: models.User, team: Optional[models.Team],
                 bots: List[models.Bot]):
        self.correo = correo
        self.slug = _slug(correo)
        self.user = user
        self.team = team
        self.bots = bots
        self.nombre = (team.nombre if team else None) or user.nombre or correo

    @property
    def bot_ids(self) -> List[int]:
        return [b.id for b in self.bots]

    def bot_nombre(self, bot_id: Optional[int]) -> Optional[str]:
        for b in self.bots:
            if b.id == bot_id:
                return b.name
        return None


def _resolver_cuentas(db: Session) -> List[_Cuenta]:
    """Traduce la lista blanca de correos a cuentas reales.

    Un correo configurado que no existe en la base no rompe la ventana: se
    omite con un warning. Pasa en local, donde no están todas las cuentas de
    producción, y no es motivo para dejar al CEO sin las que sí están.
    """
    resueltas: List[_Cuenta] = []
    for correo in cuentas_supervisadas():
        user = db.query(models.User).filter(models.User.correo == correo).first()
        if user is None:
            logger.warning("supervision: cuenta configurada inexistente (%s)", correo)
            continue
        team = (
            db.query(models.Team)
            .filter(models.Team.owner_user_id == user.id)
            .order_by(models.Team.id)
            .first()
        )
        bots = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == user.id)
            .order_by(models.Bot.id)
            .all()
        )
        resueltas.append(_Cuenta(correo, user, team, bots))
    return resueltas


def _cuenta_o_404(db: Session, slug: str) -> _Cuenta:
    for cuenta in _resolver_cuentas(db):
        if cuenta.slug == slug:
            return cuenta
    raise HTTPException(status_code=404, detail="Cuenta no supervisada")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

CANAL_LABEL = {
    "whatsapp": "💬 WhatsApp",
    "web": "🌐 Chat web",
    "mascotas": "🌐 Chat web",
    "landing": "🌐 Chat de la landing",
    "simulador": "🧪 Pruebas del simulador",
    "instagram": "📸 Instagram",
    "messenger": "📨 Messenger",
}


class AccesoOut(BaseModel):
    allowed: bool


class CuentaOut(BaseModel):
    slug: str
    nombre: str
    correo: str
    bots: List[str] = []
    hilos: int = 0


class CuentasOut(BaseModel):
    cuentas: List[CuentaOut]


class HiloOut(BaseModel):
    """Un renglón de la lista: de qué se trata el hilo sin abrirlo."""

    hilo_id: str
    cuenta: str
    bot: Optional[str] = None
    contacto: Optional[str] = None
    canal: str
    canal_label: str
    inicio: datetime
    fin: datetime
    turnos: int
    caminos: List[str] = []
    atendido_por: str = "bot"
    preview: Optional[str] = None


class HilosOut(BaseModel):
    conversaciones: List[HiloOut]
    # Cuántos hilos hay en total en la cuenta, no cuántos vienen en esta página:
    # es lo que le deja decir al frontend "21-40 de 900" y saber si hay
    # siguiente. Se calcula con COUNT en la base, sin traer los hilos.
    total: int
    pagina: int = 1
    por_pagina: int = 0


class TurnoOut(BaseModel):
    """Un mensaje del hilo. `truncado` avisa que el texto viene recortado."""

    fecha: datetime
    quien: str                       # persona | bot | asesor | sistema
    autor: Optional[str] = None      # nombre del asesor, si lo hubo
    texto: str
    camino_label: Optional[str] = None
    herramientas: List[str] = []
    truncado: bool = False
    error: Optional[str] = None


class HiloDetalleOut(BaseModel):
    hilo_id: str
    cuenta: str
    contacto: Optional[str] = None
    canal: str
    canal_label: str
    turnos: List[TurnoOut]
    # El registro de WhatsApp guarda los mensajes completos; el del chat web
    # solo un adelanto de lo que respondió el bot. La ventana lo dice en vez de
    # dejar creer que el bot contestó tres líneas.
    completo: bool = True


# ---------------------------------------------------------------------------
# Armado de los hilos
#
# La lista se arma en dos tiempos, y ahí está la diferencia entre una ventana
# que aguanta 20.000 conversaciones y una que no:
#
#   1. RESUMEN — una consulta agregada por fuente que devuelve, como mucho,
#      `pagina × por_pagina` renglones: el id del hilo y su fecha, nada más.
#      El agrupado lo hace la base, no Python.
#   2. HIDRATACIÓN — el preview, los caminos y el contacto se buscan solo para
#      los hilos que de verdad se van a pintar.
#
# Para quedarse con la página N de la fusión de dos listas YA ordenadas basta
# con los primeros `offset + límite` elementos de cada una: lo que no entra en
# ese prefijo no puede aparecer en esa página. Por eso el paso 1 puede pedir tan
# poquito y aun así dar el orden correcto.
#
# Antes esto se hacía al revés: se traían 5.000 filas de la bitácora, TODAS las
# conversaciones del team y TODOS sus mensajes a memoria de Python, se armaban
# todos los hilos y recién ahí se recortaba a 200. Se pagaba el historial
# completo para pintar 20 renglones.
# ---------------------------------------------------------------------------

_D = models.BotLlmDecision
_C = models.Conversation
_M = models.Message

# Techo de página. Más que esto vuelve a ser el problema que se está
# arreglando, solo que del lado del navegador.
MAX_POR_PAGINA = 200


@dataclass
class _Renglon:
    """Un hilo sin hidratar: lo justo para ordenarlo y paginarlo."""

    hilo_id: str
    fin: datetime


def _canal(source: str) -> str:
    return "web" if source == "mascotas" else source


def _herramientas(tools_called: Optional[str]) -> List[str]:
    try:
        return [t.get("tool", "") for t in json.loads(tools_called or "[]") if t.get("tool")]
    except (ValueError, TypeError, AttributeError):
        return []


def _dia_texto(valor: Any) -> str:
    """`date(created_at)` devuelve un `date` en Postgres y un texto en SQLite."""
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y%m%d")
    return str(valor)[:10].replace("-", "")


def _exprs_agrupacion() -> Tuple[Any, Any, Any, Any]:
    """Por qué columnas se agrupan los turnos que no cuelgan de una conversación.

    Es `_clave_sin_conversacion` escrita en SQL, y tiene que dar exactamente los
    mismos grupos: con `chat_ref` se agrupa SOLO por él (un chat web puede
    cruzar la medianoche y sigue siendo la misma conversación); sin él se cae a
    bot + canal + día.

    El truco de los `CASE` es lo que permite las dos reglas en un solo GROUP BY:
    cuando hay `chat_ref` las otras tres columnas valen NULL y no separan nada.
    Se evita `to_char`, que no existe en SQLite y la suite corre ahí.
    """
    sin_ref = _D.chat_ref.is_(None)
    return (
        _D.chat_ref,
        case((sin_ref, _D.bot_id), else_=None),
        case((sin_ref, _D.source), else_=None),
        case((sin_ref, func.date(_D.created_at)), else_=None),
    )


def _consulta_bitacora(db: Session, cuenta: _Cuenta):
    """Un renglón por hilo del chat web / simulador, agrupado en la base.

    El `HAVING` deja fuera las visitas donde la persona nunca escribió: abrieron
    el chat, recibieron el saludo automático y se fueron. Filtrarlas acá y no en
    Python es lo que hace que el conteo total sea una sola consulta.
    """
    g_ref, g_bot, g_source, g_dia = _exprs_agrupacion()
    hablo = func.max(
        case((func.coalesce(func.trim(_D.user_input), "") != "", 1), else_=0)
    )
    return (
        db.query(
            g_ref.label("chat_ref"),
            g_dia.label("dia"),
            func.min(_D.bot_id).label("bot_id"),
            func.min(_D.source).label("source"),
            func.max(_D.created_at).label("fin"),
        )
        .filter(_D.bot_id.in_(cuenta.bot_ids), _D.conversation_id.is_(None))
        .group_by(g_ref, g_bot, g_source, g_dia)
        .having(hablo == 1)
    )


def _clave_de_fila(fila: Any) -> str:
    """El mismo `hilo_id` que produce `_clave_sin_conversacion`, desde el agregado."""
    if fila.chat_ref:
        return f"chat-{fila.chat_ref}"
    return f"dia-{fila.bot_id}-{fila.source}-{_dia_texto(fila.dia)}"


def _renglones_bitacora(db: Session, cuenta: _Cuenta, tope: int) -> List[_Renglon]:
    if not cuenta.bot_ids:
        return []
    filas = _consulta_bitacora(db, cuenta).order_by(func.max(_D.created_at).desc()).limit(tope).all()
    return [_Renglon(hilo_id=_clave_de_fila(f), fin=f.fin) for f in filas]


def _renglones_conversaciones(db: Session, cuenta: _Cuenta, tope: int) -> List[_Renglon]:
    """Los hilos de WhatsApp, ordenados por el índice `(team_id, last_message_at)`.

    Se ordena por `last_message_at` y no por la fecha del último mensaje (que es
    lo que termina mostrándose) porque es la columna indexada. Las dos las
    mantiene la app en el mismo momento, así que coinciden; si alguna vez se
    separaran, el costo sería un renglón fuera de orden, no un dato falso.
    """
    if cuenta.team is None:
        return []
    filas = (
        db.query(_C.id, _C.last_message_at)
        .filter(_C.team_id == cuenta.team.id)
        .order_by(_C.last_message_at.desc())
        .limit(tope)
        .all()
    )
    return [_Renglon(hilo_id=f"conv-{f.id}", fin=f.last_message_at) for f in filas]


def _total_hilos(db: Session, cuenta: _Cuenta) -> int:
    """Cuántos hilos tiene la cuenta, contando en la base y sin armar ninguno."""
    total = 0
    if cuenta.bot_ids:
        sub = _consulta_bitacora(db, cuenta).subquery()
        total += db.query(func.count()).select_from(sub).scalar() or 0
    if cuenta.team is not None:
        total += (
            db.query(func.count(_C.id))
            .filter(_C.team_id == cuenta.team.id)
            .scalar() or 0
        )
    return total


def _pagina_de_hilos(
    db: Session, cuenta: _Cuenta, pagina: int, por_pagina: int
) -> List[HiloOut]:
    """Los hilos de una página, ya ordenados e hidratados."""
    offset = (pagina - 1) * por_pagina
    tope = offset + por_pagina

    renglones = _renglones_bitacora(db, cuenta, tope) + _renglones_conversaciones(db, cuenta, tope)
    renglones.sort(key=lambda r: r.fin, reverse=True)
    visibles = renglones[offset:tope]
    if not visibles:
        return []

    claves = [r.hilo_id for r in visibles]
    conv_ids = [int(c[len("conv-"):]) for c in claves if c.startswith("conv-")]
    otras = [c for c in claves if not c.startswith("conv-")]

    hilos: List[HiloOut] = []
    if otras:
        hilos += _hilos_de_decisiones(cuenta, _turnos_de_hilos(db, cuenta, otras))
    if conv_ids:
        hilos += _hilos_de_conversaciones(db, cuenta, conv_ids)

    # Se respeta el orden que ya se calculó por fecha, en vez de reordenar por
    # un `fin` que la hidratación pudo mover unos segundos.
    posicion = {clave: i for i, clave in enumerate(claves)}
    hilos.sort(key=lambda h: posicion.get(h.hilo_id, len(posicion)))
    return hilos


def _turnos_de_hilos(
    db: Session, cuenta: _Cuenta, claves: Iterable[str]
) -> List[models.BotLlmDecision]:
    """Los turnos crudos de un puñado de hilos ya elegidos, y de nadie más.

    Se traduce cada clave a su condición indexada en vez de recomponer la clave
    en SQL: `chat_ref` tiene índice y los hilos `dia-` caen en el rango de
    `ix_llm_decisions_bot_created`.
    """
    refs = [c[len("chat-"):] for c in claves if c.startswith("chat-")]
    condiciones: List[Any] = []
    if refs:
        condiciones.append(_D.chat_ref.in_(refs))
    for clave in claves:
        if not clave.startswith("dia-"):
            continue
        try:
            _, bot_id, source, dia = clave.split("-", 3)
            inicio = datetime.strptime(dia, "%Y%m%d")
        except ValueError:
            continue
        condiciones.append(and_(
            _D.bot_id == int(bot_id),
            _D.source == source,
            _D.chat_ref.is_(None),
            _D.created_at >= inicio,
            _D.created_at < inicio + timedelta(days=1),
        ))
    if not condiciones:
        return []
    return (
        db.query(_D)
        .filter(
            _D.bot_id.in_(cuenta.bot_ids),
            _D.conversation_id.is_(None),
            or_(*condiciones),
        )
        .order_by(_D.created_at.desc())
        .all()
    )


def _clave_sin_conversacion(fila: models.BotLlmDecision) -> str:
    """Con qué se agrupan los turnos que no cuelgan de una `conversation`.

    `chat_ref` es la sesión del chat web: es la agrupación buena. Cuando falta
    (turnos viejos, y las pruebas del simulador, que no la traen) se agrupa por
    bot + canal + día: no es una conversación de verdad, pero es una caja
    honesta y ordenada por fecha, mejor que un solo montón con todo adentro.
    """
    if fila.chat_ref:
        return f"chat-{fila.chat_ref}"
    dia = fila.created_at.strftime("%Y%m%d")
    return f"dia-{fila.bot_id}-{fila.source}-{dia}"


def _hilos_de_decisiones(cuenta: _Cuenta, filas: List[models.BotLlmDecision]) -> List[HiloOut]:
    """Hilos del chat web y del simulador: los que no tienen `conversation_id`."""
    acumulado: Dict[str, Dict[str, Any]] = {}
    for fila in filas:
        if fila.conversation_id is not None:
            continue  # ese hilo se arma desde `conversations`, con más detalle
        clave = _clave_sin_conversacion(fila)
        hilo = acumulado.setdefault(clave, {
            "hilo_id": clave,
            "cuenta": cuenta.slug,
            "bot": cuenta.bot_nombre(fila.bot_id),
            "contacto": None,
            "canal": _canal(fila.source),
            "inicio": fila.created_at,
            "fin": fila.created_at,
            "turnos": 0,
            "caminos": [],
            "atendido_por": "bot",
            "preview": None,
            # Los hilos donde la persona nunca escribió son visitas que abrieron
            # el chat, recibieron el saludo automático y se fueron. No aportan
            # nada al registro y esconden las reales.
            "_hablo": False,
        })
        hilo["turnos"] += 1
        if (fila.user_input or "").strip():
            hilo["_hablo"] = True
        hilo["inicio"] = min(hilo["inicio"], fila.created_at)
        if fila.created_at >= hilo["fin"]:
            hilo["fin"] = fila.created_at
            hilo["preview"] = fila.reply_preview or fila.user_input
        if fila.chat_contacto and not hilo["contacto"]:
            hilo["contacto"] = fila.chat_contacto
        if fila.escalated_to:
            hilo["atendido_por"] = fila.escalated_to
        if not svc_caminos.es_relleno(fila.camino):
            etiqueta = svc_caminos.etiqueta(fila.camino, cuenta.correo)
            if etiqueta not in hilo["caminos"]:
                hilo["caminos"].append(etiqueta)

    hilos = []
    for datos in acumulado.values():
        if not datos.pop("_hablo"):
            continue
        canal = datos["canal"]
        hilos.append(HiloOut(canal_label=CANAL_LABEL.get(canal, canal), **datos))
    return hilos


def _hilos_de_conversaciones(db: Session, cuenta: _Cuenta,
                             conv_ids: List[int]) -> List[HiloOut]:
    """Hilos de WhatsApp: uno por `conversation`, solo las de la página.

    Se listan todas, tengan o no bitácora del bot: una conversación que atendió
    un humano de punta a punta también es una conversación de la cuenta.

    El filtro por `team_id` no es decorativo aunque los ids vengan de una
    consulta ya filtrada: es el que garantiza que un id de otro tenant no pueda
    colarse nunca por acá.
    """
    if cuenta.team is None or not conv_ids:
        return []

    convs = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id.in_(conv_ids),
            models.Conversation.team_id == cuenta.team.id,
        )
        .order_by(models.Conversation.last_message_at.desc())
        .all()
    )
    if not convs:
        return []

    por_conv: Dict[int, List[models.BotLlmDecision]] = defaultdict(list)
    decisiones = (
        db.query(models.BotLlmDecision)
        .filter(models.BotLlmDecision.conversation_id.in_([c.id for c in convs]))
        .order_by(models.BotLlmDecision.created_at)
        .all()
    )
    for fila in decisiones:
        por_conv[fila.conversation_id].append(fila)

    # Un solo golpe a `messages` para el adelanto y el conteo de todas las
    # conversaciones, en vez de una consulta por renglón.
    resumen = _resumen_mensajes(db, [c.id for c in convs])

    hilos = []
    for conv in convs:
        decisiones = por_conv.get(conv.id, [])
        etiquetas: List[str] = []
        for fila in decisiones:
            if svc_caminos.es_relleno(fila.camino):
                continue
            etiqueta = svc_caminos.etiqueta(fila.camino, cuenta.correo)
            if etiqueta not in etiquetas:
                etiquetas.append(etiqueta)
        total, preview, ultimo = resumen.get(conv.id, (0, None, conv.last_message_at))
        bot = cuenta.bot_nombre(decisiones[0].bot_id) if decisiones else None
        hilos.append(HiloOut(
            hilo_id=f"conv-{conv.id}",
            cuenta=cuenta.slug,
            bot=bot,
            contacto=conv.contact_name or conv.contact_wa_id,
            canal="whatsapp",
            canal_label=CANAL_LABEL["whatsapp"],
            inicio=conv.created_at,
            fin=ultimo or conv.last_message_at,
            turnos=total,
            caminos=etiquetas,
            atendido_por=getattr(conv, "assigned_to", "bot") or "bot",
            preview=preview,
        ))
    return hilos


def _resumen_mensajes(
    db: Session, conv_ids: List[int]
) -> Dict[int, Tuple[int, Optional[str], Optional[datetime]]]:
    """Cuántos mensajes tiene cada conversación y cuál fue el último.

    Lo resuelve la base con funciones de ventana y devuelve UN renglón por
    conversación. Antes se traían todos los mensajes de todas las
    conversaciones a Python para contarlos con un `for`: con 600 conversaciones
    de 20 mensajes eran 12.000 filas por cada vista de la lista.

    `row_number` y `count` se evalúan antes que el `WHERE rn = 1` de afuera, así
    que el conteo es el de la conversación entera y no el del renglón que
    sobrevive. Ambas funcionan igual en Postgres y en SQLite (donde corre la
    suite), a diferencia de `DISTINCT ON`, que es solo de Postgres.
    """
    if not conv_ids:
        return {}
    orden = (models.Message.created_at.desc(), models.Message.id.desc())
    sub = (
        db.query(
            models.Message.conversation_id.label("conv_id"),
            models.Message.content.label("content"),
            models.Message.created_at.label("created_at"),
            func.count().over(
                partition_by=models.Message.conversation_id
            ).label("total"),
            func.row_number().over(
                partition_by=models.Message.conversation_id, order_by=orden
            ).label("rn"),
        )
        .filter(models.Message.conversation_id.in_(conv_ids))
        .subquery()
    )
    filas = db.query(
        sub.c.conv_id, sub.c.content, sub.c.created_at, sub.c.total
    ).filter(sub.c.rn == 1).all()
    return {
        conv_id: (total, (contenido or "")[:160], creado)
        for conv_id, contenido, creado, total in filas
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/access", response_model=AccesoOut)
def check_access(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccesoOut:
    """¿Esta sesión ve el módulo? Lo consulta el menú del frontend. Responde 200
    siempre: solo dice sí o no, no filtra nada."""
    try:
        require_gloma_account(user=user, db=db)
    except HTTPException:
        return AccesoOut(allowed=False)
    return AccesoOut(allowed=True)


@router.get("/cuentas", response_model=CuentasOut)
def listar_cuentas(
    _: models.User = Depends(require_gloma_account),
    db: Session = Depends(get_db),
) -> CuentasOut:
    """Las cuentas que esta ventana puede mirar, con cuánto hay en cada una.

    El número de la pestaña sale de dos COUNT. Antes se armaban TODOS los hilos
    de TODAS las cuentas supervisadas —con sus mensajes— nada más para poder
    hacerles `len()`, y eso corría al abrir la página.
    """
    salida = []
    for cuenta in _resolver_cuentas(db):
        salida.append(CuentaOut(
            slug=cuenta.slug,
            nombre=cuenta.nombre,
            correo=cuenta.correo,
            bots=[b.name for b in cuenta.bots],
            hilos=_total_hilos(db, cuenta),
        ))
    return CuentasOut(cuentas=salida)


@router.get("/conversaciones", response_model=HilosOut)
def listar_conversaciones(
    cuenta: str = Query(..., description="slug de la cuenta a mirar"),
    limite: int = Query(20, ge=1, le=MAX_POR_PAGINA,
                        description="cuántos hilos por página"),
    pagina: int = Query(1, ge=1, description="página, empezando en 1"),
    _: models.User = Depends(require_gloma_account),
    db: Session = Depends(get_db),
) -> HilosOut:
    """Una página de hilos, del más reciente al más viejo.

    La paginación es del servidor a propósito: si se recortara en el navegador,
    "20 por página" seguiría costando el historial completo en la base, que es
    justo lo que se quiere evitar.
    """
    resuelta = _cuenta_o_404(db, cuenta)
    return HilosOut(
        conversaciones=_pagina_de_hilos(db, resuelta, pagina, limite),
        total=_total_hilos(db, resuelta),
        pagina=pagina,
        por_pagina=limite,
    )


@router.get("/conversaciones/{hilo_id}", response_model=HiloDetalleOut)
def detalle_conversacion(
    hilo_id: str,
    cuenta: str = Query(..., description="slug de la cuenta dueña del hilo"),
    _: models.User = Depends(require_gloma_account),
    db: Session = Depends(get_db),
) -> HiloDetalleOut:
    """Los mensajes de un hilo. Se pide al desplegarlo, no al listar.

    El `hilo_id` se valida contra la cuenta: un id de otra cuenta responde 404
    aunque exista. Sin eso, `conv-1` serviría para pasear por las
    conversaciones de cualquier tenant de la plataforma.
    """
    resuelta = _cuenta_o_404(db, cuenta)
    if hilo_id.startswith("conv-"):
        return _detalle_whatsapp(db, resuelta, hilo_id)
    return _detalle_bitacora(db, resuelta, hilo_id)


def _detalle_whatsapp(db: Session, cuenta: _Cuenta, hilo_id: str) -> HiloDetalleOut:
    """Transcripción de un chat de WhatsApp, tomada de `messages`.

    Es el registro completo: lo del contacto, lo del bot y lo que escribió un
    asesor después del handoff. Encima se le pega la etiqueta del camino que
    tomó el bot en cada turno, cruzando por el texto que escribió la persona
    (`user_input` de la bitácora es exactamente el mensaje entrante). Si no
    cruza, el mensaje va sin etiqueta: preferimos ninguna a una equivocada.
    """
    try:
        conv_id = int(hilo_id.split("-", 1)[1])
    except (IndexError, ValueError):
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    conv = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == conv_id,
            models.Conversation.team_id == (cuenta.team.id if cuenta.team else -1),
        )
        .first()
    )
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    mensajes = (
        db.query(models.Message)
        .filter(models.Message.conversation_id == conv.id)
        .order_by(models.Message.created_at, models.Message.id)
        .all()
    )
    decisiones = (
        db.query(models.BotLlmDecision)
        .filter(models.BotLlmDecision.conversation_id == conv.id)
        .order_by(models.BotLlmDecision.created_at)
        .all()
    )
    por_texto: Dict[str, List[models.BotLlmDecision]] = defaultdict(list)
    for fila in decisiones:
        if fila.user_input:
            por_texto[fila.user_input.strip()].append(fila)

    asesores = _nombres_de_asesores(db, mensajes)

    turnos = []
    for msg in mensajes:
        if msg.direction == "inbound":
            quien, autor = "persona", None
        elif msg.sent_by_user_id:
            quien, autor = "asesor", asesores.get(msg.sent_by_user_id)
        else:
            quien, autor = "bot", None

        etiqueta = None
        herramientas: List[str] = []
        if quien == "persona":
            pendientes = por_texto.get((msg.content or "").strip())
            if pendientes:
                fila = pendientes.pop(0)
                etiqueta = svc_caminos.etiqueta(fila.camino, cuenta.correo)
                herramientas = _herramientas(fila.tools_called)

        turnos.append(TurnoOut(
            fecha=msg.created_at,
            quien=quien,
            autor=autor,
            texto=msg.content,
            camino_label=etiqueta,
            herramientas=herramientas,
            # `error_detail` explica por qué un envío quedó en 'failed'. Es
            # justamente lo que se viene a buscar cuando algo salió mal.
            error=msg.error_detail if msg.status == "failed" else None,
        ))

    return HiloDetalleOut(
        hilo_id=hilo_id,
        cuenta=cuenta.slug,
        contacto=conv.contact_name or conv.contact_wa_id,
        canal="whatsapp",
        canal_label=CANAL_LABEL["whatsapp"],
        turnos=turnos,
        completo=True,
    )


def _nombres_de_asesores(
    db: Session, mensajes: List[models.Message]
) -> Dict[int, str]:
    """Nombre de cada usuario que respondió a mano en el hilo."""
    ids = {m.sent_by_user_id for m in mensajes if m.sent_by_user_id}
    if not ids:
        return {}
    filas = db.query(models.User.id, models.User.nombre).filter(models.User.id.in_(ids)).all()
    return {uid: nombre for uid, nombre in filas}


def _detalle_bitacora(db: Session, cuenta: _Cuenta, hilo_id: str) -> HiloDetalleOut:
    """Transcripción de un chat web o del simulador, desde `bot_llm_decisions`.

    Aquí el bot no dejó mensajes en `messages` (el chat web es anónimo), así que
    el único registro es la bitácora del motor: el texto de la persona completo
    y el del bot recortado a 300 caracteres. Por eso `completo=False`.
    """
    if not cuenta.bot_ids:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    consulta = db.query(models.BotLlmDecision).filter(
        models.BotLlmDecision.bot_id.in_(cuenta.bot_ids),
        models.BotLlmDecision.conversation_id.is_(None),
    )
    if hilo_id.startswith("chat-"):
        consulta = consulta.filter(models.BotLlmDecision.chat_ref == hilo_id[len("chat-"):])
    elif hilo_id.startswith("dia-"):
        try:
            _, bot_id, source, dia = hilo_id.split("-", 3)
            inicio = datetime.strptime(dia, "%Y%m%d")
        except ValueError:
            raise HTTPException(status_code=404, detail="Conversación no encontrada")
        consulta = consulta.filter(
            models.BotLlmDecision.bot_id == int(bot_id),
            models.BotLlmDecision.source == source,
            models.BotLlmDecision.chat_ref.is_(None),
            models.BotLlmDecision.created_at >= inicio,
            models.BotLlmDecision.created_at < inicio + timedelta(days=1),
        )
    else:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    filas = consulta.order_by(models.BotLlmDecision.created_at).limit(400).all()
    if not filas:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    contacto = next((f.chat_contacto for f in filas if f.chat_contacto), None)
    canal = _canal(filas[0].source)

    turnos: List[TurnoOut] = []
    for fila in filas:
        etiqueta = svc_caminos.etiqueta(fila.camino, cuenta.correo)
        if fila.user_input:
            turnos.append(TurnoOut(
                fecha=fila.created_at,
                quien="persona",
                texto=fila.user_input,
                camino_label=etiqueta,
                herramientas=_herramientas(fila.tools_called),
            ))
        if fila.reply_preview:
            turnos.append(TurnoOut(
                fecha=fila.created_at,
                quien="bot",
                texto=fila.reply_preview,
                # 300 es el largo del campo: si llegó justo, casi seguro venía
                # más texto y se cortó.
                truncado=len(fila.reply_preview) >= 300,
                error="El motor respondió con el mensaje de respaldo" if fila.failsafe else None,
            ))
        if fila.escalated_to:
            turnos.append(TurnoOut(
                fecha=fila.created_at,
                quien="sistema",
                texto=f"La conversación pasó a {fila.escalated_to}",
            ))

    return HiloDetalleOut(
        hilo_id=hilo_id,
        cuenta=cuenta.slug,
        contacto=contacto,
        canal=canal,
        canal_label=CANAL_LABEL.get(canal, canal),
        turnos=turnos,
        completo=False,
    )
