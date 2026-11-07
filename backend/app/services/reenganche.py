"""Reenganche: el cliente que vuelve tras un abandono o un cierre por inactividad
(Sprint 36, diseño de seguridad sección 2).

Hasta el Sprint 35 el que volvía quedaba en silencio: `_marcar_abandonada`
asignaba el chat a una asesora y `bot_router` cortaba en seco cuando
`assigned_to != "bot"`. Si la asesora no estaba mirando, el cliente que volvía
con la tarjeta en la mano no recibía nada.

Ahora la conversación lleva un **marcador de un solo uso** por episodio
(`abandono_at` o `cerrada_por_inactividad_at`, con `reclamos_abandono = 0`). El
primer entrante real después del marcador lo **reclama** con un único UPDATE
atómico (2.1) y la conversación vuelve al bot. Reglas:

  * Se llama SOLO desde `bot_router.resolve_bot_for_incoming_message`, antes del
    paso 0 (cubre los dos webhooks, después de firma, aislamiento y dedupe).
    Nunca desde el tick, `process_pending_action` ni `run_turn` (2.1, 2.5).
  * Solo «abandonada» (`pending`) o «cerrada por inactividad» (`closed`); nunca
    una cerrada por otra razón. Cerrar, reabrir o asignar a mano consumen el
    marcador (`consumir_por_humano`, 2.2).
  * Si una persona del equipo escribió en las últimas 2 h, el bot no responde:
    solo queda la nota «🔥 Volvió» y el marcador se consume (2.4c).
  * Gana un solo proceso: la nota la escribe solo quien gana el UPDATE (2.5).
  * Logs sin texto, teléfono ni nombres (2.10).

El resumen de lo que había (fecha, grupo, último total) sale de la sesión
anterior de la conversación (`BotSession.conversation_id`) y de
`bot_llm_decisions.tools_called`, nunca de texto libre: así la nota y el bloque
del motor no pueden llevar un teléfono ni una cédula.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import Session

from .. import crud, models

logger = logging.getLogger(__name__)

#: Si una persona del equipo le escribió al cliente hace menos que esto, el bot
#: no se mete (diseño 2.4).
VENTANA_HUMANO = timedelta(hours=2)

VIA_ABANDONO = "abandono"
VIA_INACTIVIDAD = "inactividad"

#: Encabezado de la nota interna. Los reportes la buscan por este prefijo.
TITULO_VOLVIO = "🔥 *Volvió*"

#: Herramientas de precios (motor viejo y catálogo de productos).
_CONSULTAS = ("consultar_tarifario", "consultar_precios")
#: Cuántas decisiones del bot se leen hacia atrás para armar el resumen.
_MAX_DECISIONES = 60
_MAX_PERSONAS = 30


# ---------------------------------------------------------------------------
# Acciones humanas (2.2)
# ---------------------------------------------------------------------------

def hay_marcador(conv: models.Conversation) -> bool:
    """¿La conversación tiene un marcador de abandono/inactividad sin reclamar?"""
    return int(conv.reclamos_abandono or 0) == 0 and (
        conv.abandono_at is not None or conv.cerrada_por_inactividad_at is not None
    )


def consumir_por_humano(conv: models.Conversation) -> bool:
    """Cerrar, reabrir o asignar a mano consumen el marcador: después de que una
    persona decidió qué hacer con el chat, el cliente que vuelve no se lo
    devuelve al bot. No hace commit (lo hace el endpoint con su cambio).
    Devuelve si había algo que consumir."""
    if not hay_marcador(conv):
        return False
    conv.reclamos_abandono = 1
    conv.marcador_consumido = models.MARCADOR_CONSUMIDO_HUMANO
    return True


# ---------------------------------------------------------------------------
# El reclamo (2.1, 2.4c)
# ---------------------------------------------------------------------------

@dataclass
class Reclamo:
    """Lo que pasó al reclamar. `tomo_el_bot` = el bot atiende este turno."""

    via: str
    tomo_el_bot: bool
    motivo: str = ""                      # "humano_2h" si solo dejó el aviso
    resumen: Dict[str, Any] = field(default_factory=dict)
    marcado_at: Optional[datetime] = None  # cuándo se marcó el episodio


def _condicion_marcador():
    C = models.Conversation
    return or_(
        and_(C.abandono_at.isnot(None), C.status == "pending"),
        and_(C.cerrada_por_inactividad_at.isnot(None), C.status == "closed"),
    )


def _via(conv: models.Conversation) -> str:
    """Por cuál de los dos marcadores entra. Si tiene los dos (se abandonó y
    después el script la cerró), manda el estado actual."""
    if conv.status == "closed" and conv.cerrada_por_inactividad_at is not None:
        return VIA_INACTIVIDAD
    return VIA_ABANDONO


def reclamar(
    db: Session,
    team: models.Team,
    conv: models.Conversation,
    asignado_leido: str,
    *,
    ahora: Optional[datetime] = None,
) -> Optional[Reclamo]:
    """Intenta reclamar el marcador. None = no había nada que reclamar (o lo
    ganó otro proceso, o una persona ya lo consumió).

    Dos UPDATE excluyentes sobre la misma fila, los dos con
    `reclamos_abandono = 0` en el WHERE, así que entre todos los procesos
    concurrentes gana **uno** (diseño 2.1):

      1. Sin humano en las últimas 2 h → la conversación vuelve al bot
         (`assigned_to='bot'`, `status='open'`).
      2. Con humano en las últimas 2 h → solo se consume el marcador; la
         conversación sigue con quien la tenía y vuelve a la bandeja de
         pendientes si estaba cerrada.

    `asignado_leido` es lo que el router leyó en `assigned_to`: si alguien la
    reasignó entre la lectura y el UPDATE, no se toca.
    """
    if not hay_marcador(conv):
        return None
    momento = ahora or datetime.utcnow()
    corte = momento - VENTANA_HUMANO
    via = _via(conv)
    marcado_at = conv.cerrada_por_inactividad_at if via == VIA_INACTIVIDAD else conv.abandono_at
    C = models.Conversation
    base = [
        C.id == conv.id,
        C.team_id == team.id,
        C.reclamos_abandono == 0,
        C.assigned_to == (asignado_leido or "bot"),
        _condicion_marcador(),
    ]
    sin_humano = or_(C.ultimo_mensaje_humano_at.is_(None), C.ultimo_mensaje_humano_at < corte)
    filas = (
        db.query(C)
        .filter(*base, sin_humano)
        .update(
            {
                C.reclamos_abandono: C.reclamos_abandono + 1,
                C.marcador_consumido: models.MARCADOR_CONSUMIDO_VOLVIO,
                C.assigned_to: "bot",
                C.status: "open",
            },
            synchronize_session=False,
        )
    )
    if filas == 1:
        db.commit()
        db.refresh(conv)
        logger.info(
            "reenganche.reclamado conv=%s team=%s via=%s", conv.id, team.id, via
        )
        return Reclamo(
            via=via, tomo_el_bot=True, resumen=resumen_de_lo_que_habia(db, conv),
            marcado_at=marcado_at,
        )

    filas = (
        db.query(C)
        .filter(*base, C.ultimo_mensaje_humano_at >= corte)
        .update(
            {
                C.reclamos_abandono: C.reclamos_abandono + 1,
                C.marcador_consumido: models.MARCADOR_CONSUMIDO_VOLVIO,
                C.status: case((C.status == "closed", "pending"), else_=C.status),
            },
            synchronize_session=False,
        )
    )
    if filas == 1:
        db.commit()
        db.refresh(conv)
        logger.info(
            "reenganche.solo_aviso conv=%s team=%s motivo=humano_2h", conv.id, team.id
        )
        reclamo = Reclamo(
            via=via, tomo_el_bot=False, motivo="humano_2h",
            resumen=resumen_de_lo_que_habia(db, conv), marcado_at=marcado_at,
        )
        nota_volvio(db, conv, reclamo)
        return reclamo

    db.rollback()
    db.refresh(conv)
    return None


# ---------------------------------------------------------------------------
# Qué bot lo atiende (2.3)
# ---------------------------------------------------------------------------

def elegir_bot(
    db: Session,
    conv: models.Conversation,
    bots: List[models.Bot],
) -> Optional[models.Bot]:
    """El bot que atiende al que vuelve, elegido SOLO de `bots`.

    `bots` es la lista que ya arma `resolve_bot_for_incoming_message`: del owner
    del team, activos y sin `llm_config.demo`. Aquí además se exige
    `engine=='llm'` (el camino de regreso es del motor conversacional).

      1. El bot de la cuenta con `es_reenganche`.
      2. Si no hay, el que ya la tenía: la última sesión de ESTA conversación,
         o `conv.bot_asignado_id`.
      3. Si tampoco pasa el filtro, None → reparto normal.

    Nunca `db.query(Bot).get(id)` suelto: un id que no esté en `bots` (de otro
    owner, pausado, demo, `flow`) se ignora.
    """
    candidatos = {b.id: b for b in bots if getattr(b, "engine", "flow") == "llm"}
    for b in bots:
        if b.id in candidatos and bool(getattr(b, "es_reenganche", False)):
            return b
    ultima = (
        db.query(models.BotSession.bot_id)
        .filter(models.BotSession.conversation_id == conv.id)
        .order_by(models.BotSession.started_at.desc(), models.BotSession.id.desc())
        .first()
    )
    for bot_id in ((ultima[0] if ultima else None), conv.bot_asignado_id):
        if bot_id is not None and bot_id in candidatos:
            return candidatos[bot_id]
    return None


def abrir_sesion_de_regreso(
    db: Session, bot: models.Bot, conv: models.Conversation, reclamo: Reclamo
) -> models.BotSession:
    """Sesión nueva con la bandera de regreso en su estado.

    `bot_runner.run_turn` la saca del estado en el primer turno y la pasa al
    motor como `runtime["regreso"]`; después no queda rastro. Va con sesión (y
    no `(bot, None)`) para que el webhook le pase al turno el texto del cliente:
    con sesión nula el primer turno no ve lo que escribió (gotcha del 20-oct).
    """
    estado = {"regreso": contrato_de_regreso(reclamo)}
    sesion = models.BotSession(
        bot_id=bot.id,
        conversation_id=conv.id,
        state=json.dumps(estado, ensure_ascii=False),
        status=models.BOT_SESSION_RUNNING,
    )
    db.add(sesion)
    db.commit()
    db.refresh(sesion)
    return sesion


# ---------------------------------------------------------------------------
# El resumen de lo que había
# ---------------------------------------------------------------------------

_NUMEROS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4,
            "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10}
_FECHA_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: «$1.377.000 total», «total $918.000», «Total del grupo: $918.000».
_TOTAL_RE = re.compile(
    r"\$\s?(\d{1,3}(?:\.\d{3})+|\d{4,9})\s*(?:cop\s*)?(?:en\s+)?total"
    r"|total(?:\s+del\s+grupo)?\s*(?:de|es|:|=)?\s*\$\s?(\d{1,3}(?:\.\d{3})+|\d{4,9})",
    re.IGNORECASE,
)


def _entero(valor: Any) -> Optional[int]:
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    texto = str(valor or "").strip().lower()
    m = re.search(r"\d{1,2}", texto)
    if m:
        return int(m.group(0))
    for palabra, n in _NUMEROS.items():
        if re.search(rf"\b{palabra}\b", texto):
            return n
    return None


def _edades(valor: Any) -> List[int]:
    if isinstance(valor, list):
        crudos = valor
    else:
        crudos = re.findall(r"\d{1,2}", str(valor or ""))
    edades = []
    for c in crudos:
        n = _entero(c)
        if n is not None and 0 <= n <= 17:
            edades.append(n)
    return edades[:_MAX_PERSONAS]


def _ultima_consulta(db: Session, conv: models.Conversation) -> Dict[str, Any]:
    """El input de la última consulta de precios de la conversación (cualquier
    bot): `{mes, fecha, hotel, adultos, ninos}` tal cual lo pasó el modelo."""
    filas = (
        db.query(models.BotLlmDecision.tools_called)
        .filter(
            models.BotLlmDecision.conversation_id == conv.id,
            models.BotLlmDecision.tools_called.isnot(None),
        )
        .order_by(models.BotLlmDecision.created_at.desc(), models.BotLlmDecision.id.desc())
        .limit(_MAX_DECISIONES)
        .all()
    )
    con_grupo: Optional[Dict[str, Any]] = None
    primera: Optional[Dict[str, Any]] = None
    for (crudo,) in filas:
        try:
            llamadas = json.loads(crudo or "[]")
        except (TypeError, ValueError):
            continue
        for llamada in reversed(llamadas if isinstance(llamadas, list) else []):
            if not isinstance(llamada, dict) or llamada.get("tool") not in _CONSULTAS:
                continue
            entrada = llamada.get("input")
            if not isinstance(entrada, dict):
                continue
            if primera is None:
                primera = entrada
            if con_grupo is None and entrada.get("adultos") not in (None, ""):
                con_grupo = entrada
            if primera is not None and con_grupo is not None:
                break
        if primera is not None and con_grupo is not None:
            break
    salida = dict(primera or {})
    # El grupo puede haberse dado en una consulta anterior a la última.
    if con_grupo is not None:
        for clave in ("adultos", "ninos"):
            if salida.get(clave) in (None, ""):
                salida[clave] = con_grupo.get(clave)
    return salida


def _ultimo_total(db: Session, conv: models.Conversation) -> Optional[int]:
    """El último total que el bot le escribió al cliente («… = $918.000 total»).

    Se lee de los mensajes del bot (salientes sin autor, no notas): es lo que
    la persona vio. Solo es una REFERENCIA para la asesora; el motor nunca lo
    recibe como cifra (`contrato_de_regreso` solo dice que hubo un total).
    """
    filas = (
        db.query(models.Message.content)
        .filter(
            models.Message.conversation_id == conv.id,
            models.Message.direction == "outbound",
            models.Message.sent_by_user_id.is_(None),
            models.Message.message_type != "nota_interna",
        )
        .order_by(models.Message.id.desc())
        .limit(40)
        .all()
    )
    for (contenido,) in filas:
        encontrados = list(_TOTAL_RE.finditer(contenido or ""))
        if not encontrados:
            continue
        m = encontrados[-1]
        crudo = (m.group(1) or m.group(2) or "").replace(".", "")
        try:
            valor = int(crudo)
        except ValueError:
            continue
        if 10_000 <= valor <= 500_000_000:
            return valor
    return None


def _fecha(consulta: Dict[str, Any]) -> Optional[date]:
    texto = str(consulta.get("fecha") or "").strip()[:10]
    if not _FECHA_ISO_RE.match(texto):
        return None
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def resumen_de_lo_que_habia(db: Session, conv: models.Conversation) -> Dict[str, Any]:
    """`{fecha, mes, hotel, adultos, edades_ninos, ultimo_total, fecha_paso}`
    (solo las llaves con dato). Solo datos estructurados: ni nombres, ni
    teléfonos, ni cédulas, ni texto del cliente. Ante cualquier error, {}."""
    try:
        from . import tarifario

        consulta = _ultima_consulta(db, conv)
        salida: Dict[str, Any] = {}
        fecha = _fecha(consulta)
        if fecha is not None:
            salida["fecha"] = fecha.isoformat()
            salida["fecha_paso"] = fecha < tarifario.hoy_colombia()
        mes = tarifario.normalizar_mes(str(consulta.get("mes") or "")) if consulta.get("mes") else None
        if mes is None and fecha is not None:
            mes = fecha.month
        if mes:
            salida["mes"] = int(mes)
        clave = tarifario.normalizar_hotel(str(consulta.get("hotel") or consulta.get("variante") or ""))
        if clave:
            salida["hotel"] = tarifario._NOMBRE_HOTEL.get(clave, clave)
        adultos = _entero(consulta.get("adultos"))
        if adultos and 1 <= adultos <= _MAX_PERSONAS:
            salida["adultos"] = adultos
            salida["edades_ninos"] = _edades(consulta.get("ninos"))
        total = _ultimo_total(db, conv)
        if total:
            salida["ultimo_total"] = total
        return salida
    except Exception as exc:  # nunca tumba el turno
        logger.error(
            "reenganche: no se pudo armar el resumen conv=%s (%s)", conv.id, type(exc).__name__
        )
        return {}


def contrato_de_regreso(reclamo: Reclamo) -> Dict[str, Any]:
    """Lo que viaja al motor en `runtime["regreso"]` (contrato para los bots
    1-3 y el futuro D). Sin la cifra del total viejo: el motor solo sabe que
    hubo una cotización y tiene que volver a consultar precios.

        {"via": "abandono"|"inactividad", "fecha": "AAAA-MM-DD"?,
         "fecha_paso": bool?, "mes": 1-12?, "hotel": str?, "adultos": int?,
         "edades_ninos": [int]?, "habia_total": bool,
         "marcado_at": "AAAA-MM-DDTHH:MM:SS" (UTC) | None}
    """
    r = reclamo.resumen or {}
    contrato: Dict[str, Any] = {
        "via": reclamo.via,
        "habia_total": bool(r.get("ultimo_total")),
        "marcado_at": reclamo.marcado_at.isoformat() if reclamo.marcado_at else None,
    }
    for clave in ("fecha", "fecha_paso", "mes", "hotel", "adultos", "edades_ninos"):
        if clave in r:
            contrato[clave] = r[clave]
    return contrato


# ---------------------------------------------------------------------------
# La nota interna (2.5, 2.10)
# ---------------------------------------------------------------------------

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _pesos(valor: int) -> str:
    return f"${int(valor):,}".replace(",", ".")


def describir_grupo(adultos: Optional[int], edades: Optional[List[int]]) -> str:
    if not adultos:
        return ""
    texto = f"{adultos} adulto" + ("s" if adultos != 1 else "")
    edades = list(edades or [])
    if edades:
        partes = ["bebé" if e == 0 else f"niño de {e}" for e in edades]
        texto += " y " + ", ".join(partes)
    return texto


def lineas_de_resumen(resumen: Dict[str, Any]) -> List[str]:
    lineas: List[str] = []
    if resumen.get("fecha"):
        fecha = resumen["fecha"]
        lineas.append(
            f"Salida que miró: {fecha}" + (" (ya pasó)" if resumen.get("fecha_paso") else "")
        )
    elif resumen.get("mes"):
        lineas.append(f"Mes que miró: {_MESES[int(resumen['mes']) - 1]}")
    if resumen.get("hotel"):
        lineas.append(f"Hotel: {resumen['hotel']}")
    grupo = describir_grupo(resumen.get("adultos"), resumen.get("edades_ninos"))
    if grupo:
        lineas.append(f"Grupo: {grupo}")
    if resumen.get("ultimo_total"):
        lineas.append(
            f"Último total cotizado: {_pesos(resumen['ultimo_total'])} (de entonces; "
            "el bot vuelve a consultar precios)"
        )
    return lineas


def nota_volvio(db: Session, conv: models.Conversation, reclamo: Reclamo,
                bot: Optional[models.Bot] = None) -> None:
    """La nota «🔥 Volvió». La escribe solo quien ganó el UPDATE, así que hay
    una por episodio. `sent_by_user_id` NULL y `nota_interna`: no cuenta como
    humano (0.4), ni como entrante, ni como presentación del bot. Al pasar por
    `crud.add_message` sube la conversación en la bandeja (`last_message_at`).
    """
    origen = (
        "después de que la conversación quedó abandonada"
        if reclamo.via == VIA_ABANDONO
        else "después de que la conversación se cerró por inactividad"
    )
    lineas = [TITULO_VOLVIO, f"El cliente volvió a escribir {origen}."]
    lineas.extend(lineas_de_resumen(reclamo.resumen or {}))
    if reclamo.tomo_el_bot and bot is None:
        lineas.append("No hay un bot activo para retomarla: contéstale tú.")
    elif reclamo.tomo_el_bot:
        nombre = (getattr(bot, "name", "") or "").strip()[:60]
        lineas.append(
            f"Lo atiende el bot{(' ' + nombre) if nombre else ''}: retoma la "
            "cotización y le ofrece apartar."
        )
    else:
        lineas.append(
            "Una persona del equipo le escribió hace menos de 2 horas, así que el "
            "bot no responde: contéstale tú."
        )
    try:
        crud.add_message(
            db, conv, direction="outbound", content="\n".join(lineas),
            message_type="nota_interna", status="sent", sent_by_user_id=None,
        )
    except Exception:
        logger.exception("reenganche: no se pudo guardar la nota conv=%s", conv.id)


def cerrar_sesiones_vivas(db: Session, conv: models.Conversation) -> int:
    """Antes de abrir la sesión de regreso: ninguna otra queda viva en la
    conversación (una sola running/waiting, como espera el router) y sus
    acciones pendientes (recordatorios, abandono) se cancelan."""
    ahora = datetime.utcnow()
    vivas = (
        db.query(models.BotSession)
        .filter(
            models.BotSession.conversation_id == conv.id,
            models.BotSession.status.in_(
                (models.BOT_SESSION_RUNNING, models.BOT_SESSION_WAITING)
            ),
        )
        .all()
    )
    for sesion in vivas:
        (
            db.query(models.BotPendingAction)
            .filter(
                models.BotPendingAction.session_id == sesion.id,
                models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING,
            )
            .update(
                {
                    models.BotPendingAction.status: models.BOT_PENDING_STATUS_DONE,
                    models.BotPendingAction.processed_at: ahora,
                },
                synchronize_session=False,
            )
        )
        sesion.status = models.BOT_SESSION_FINISHED
        sesion.finished_at = ahora
        sesion.updated_at = ahora
        db.add(sesion)
    if vivas:
        db.commit()
    return len(vivas)


def cerrar_llamada_de_rescate(db: Session, conv: models.Conversation) -> bool:
    """2.9: si el bot retomó, la llamada de rescate pendiente del abandono ya no
    tiene sentido (el cliente está hablando con el bot). Solo la de origen
    `abandono`; la que agendó el propio bot (`bot_llamada`) se deja."""
    try:
        filas = (
            db.query(models.Agendamiento)
            .filter(
                models.Agendamiento.conversation_id == conv.id,
                models.Agendamiento.team_id == conv.team_id,
                models.Agendamiento.estado == models.AGENDAMIENTO_PENDIENTE,
                or_(
                    models.Agendamiento.origen.is_(None),
                    models.Agendamiento.origen == models.AGENDAMIENTO_ORIGEN_ABANDONO,
                ),
            )
            .update(
                {
                    models.Agendamiento.estado: models.AGENDAMIENTO_CERRADO,
                    models.Agendamiento.cerrado_at: datetime.utcnow(),
                },
                synchronize_session=False,
            )
        )
        db.commit()
        return bool(filas)
    except Exception:
        db.rollback()
        logger.exception("reenganche: no se pudo cerrar la llamada conv=%s", conv.id)
        return False


# ---------------------------------------------------------------------------
# Tope de turnos LLM por conversación (2.6)
# ---------------------------------------------------------------------------

TOPE_POR_HORA = 30
TOPE_POR_DIA = 120
TITULO_TOPE = "⛔ *Tope de turnos del bot*"


def excede_tope(db: Session, conv: models.Conversation, *, ahora: Optional[datetime] = None) -> Optional[str]:
    """`"hora"`/`"dia"` si la conversación ya gastó su tope de turnos del motor
    LLM, o None. Una sola consulta sobre `bot_llm_decisions.conversation_id`
    (índice existente)."""
    momento = ahora or datetime.utcnow()
    hora = momento - timedelta(hours=1)
    dia = momento - timedelta(days=1)
    D = models.BotLlmDecision
    fila = (
        db.query(
            func.count(D.id),
            func.sum(case((D.created_at >= hora, 1), else_=0)),
        )
        .filter(D.conversation_id == conv.id, D.created_at >= dia)
        .one()
    )
    en_el_dia, en_la_hora = int(fila[0] or 0), int(fila[1] or 0)
    if en_la_hora >= TOPE_POR_HORA:
        return "hora"
    if en_el_dia >= TOPE_POR_DIA:
        return "dia"
    return None


def avisar_tope(db: Session, conv: models.Conversation, motivo: str,
                *, ahora: Optional[datetime] = None) -> None:
    """Una sola nota interna por exceso: si ya hay una en las últimas 24 h, no
    se escribe otra. Warning sin texto ni teléfono."""
    momento = ahora or datetime.utcnow()
    logger.warning("bot_router.tope_turnos conv=%s team=%s tope=%s", conv.id, conv.team_id, motivo)
    ya = (
        db.query(models.Message.id)
        .filter(
            models.Message.conversation_id == conv.id,
            models.Message.message_type == "nota_interna",
            models.Message.created_at >= momento - timedelta(days=1),
            models.Message.content.like(TITULO_TOPE + "%"),
        )
        .first()
    )
    if ya is not None:
        return
    tope = f"{TOPE_POR_HORA} por hora" if motivo == "hora" else f"{TOPE_POR_DIA} por día"
    try:
        crud.add_message(
            db, conv, direction="outbound",
            content=(
                f"{TITULO_TOPE}\nEsta conversación llegó al tope de turnos del bot "
                f"({tope}). El bot deja de responder por ahora: revísala y "
                "contéstale tú si hace falta."
            ),
            message_type="nota_interna", status="sent", sent_by_user_id=None,
        )
    except Exception:
        logger.exception("reenganche: no se pudo guardar la nota de tope conv=%s", conv.id)
