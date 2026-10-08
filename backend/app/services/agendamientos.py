"""Agendamientos: la llamada de rescate de una conversación abandonada.

Qué resuelve. Cuando alguien deja de contestarle al bot, `bot_runner` ya
etiqueta la conversación y se la asigna a un asesor. Eso la deja *visible*,
pero no *accionable*: la bandeja se ordena por actividad y un chat frío se
hunde debajo de los que sí están hablando. Este módulo saca a esa persona de la
bandeja y la pone en una lista de llamadas por hacer, con fecha.

La regla del nivel de interés — que es de lo que depende todo lo demás — está
en `nivel_de_interes()` y se escribió mirando las conversaciones reales de
Arranquemos Pues (159 abandonos entre el 21-ago y el 4-sep-2026: 62 habían
recibido información, 97 sólo el saludo). Los dos casos se ven separados con
nitidez en la base, y su forma es siempre ésta (ejemplos reescritos — los
mensajes de los clientes no se copian a un repo público, regla 8):

    sólo bienvenida → 1 entrante ("hola, información")
                      saludo de la asesora virtual
                      3 recordatorios, sin respuesta
                      → nunca recibió nada más que el saludo

    con información → 1 entrante, saludo,
                      y de ahí en adelante ida y vuelta: dice su nombre, el bot
                      lo saluda por el nombre, pregunta por fechas o precios y
                      el bot le responde con el plan
                      → recibió información y aun así se fue

Por eso el corte es **si la persona volvió a escribir después del saludo**: si
lo hizo, el bot le contestó (el motor siempre responde a un entrante), y eso es
justamente "recibió información". Contar mensajes salientes no sirve — los tres
recordatorios de silencio también son salientes, y los manda el bot solo,
cuando ya no hay nadie del otro lado.

Sólo los `con_informacion` generan agendamiento. Es lo que pidió el CEO: la
lista es de conversaciones "abandonadas después de al menos enviar alguna
información". El nivel se guarda igual en la fila, para poder mirarlos aparte
más adelante sin volver a clasificar nada.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from . import intencion_compra as _ic

logger = logging.getLogger(__name__)

#: Colombia no tiene horario de verano, así que el offset es -05:00 todo el
#: año. Se usa para que la fecha de la llamada sea la del calendario del
#: asesor: un abandono procesado a las 02:00 UTC son las 21:00 del día
#: anterior en Medellín, y sumarle 3 días sobre la fecha UTC le correría la
#: llamada un día entero.
_TZ_CO = timezone(timedelta(hours=-5))

#: Los `nota_interna` son mensajes salientes que **no viajan a WhatsApp**: son
#: el resumen que el bot le deja al asesor. No cuentan como "el bot saludó".
_TIPO_NOTA_INTERNA = "nota_interna"


def hoy_en_colombia(ahora_utc: Optional[datetime] = None) -> date:
    """La fecha de hoy como la ve el equipo que hace las llamadas."""
    momento = ahora_utc or datetime.utcnow()
    return momento.replace(tzinfo=timezone.utc).astimezone(_TZ_CO).date()


def fecha_tentativa(ahora_utc: Optional[datetime] = None) -> date:
    """Cuándo llamar: 3 días después de marcar la conversación como abandonada."""
    return hoy_en_colombia(ahora_utc) + timedelta(
        days=models.AGENDAMIENTO_DIAS_PARA_LLAMAR
    )


def nivel_de_interes(db: Session, conversation: models.Conversation) -> str:
    """¿Alcanzó a recibir información, o sólo el saludo?

    Devuelve `con_informacion` si la persona escribió **después** del primer
    mensaje del bot. Ver el encabezado del módulo para el porqué de este corte.
    """
    primer_saludo = (
        db.query(func.min(models.Message.created_at))
        .filter(
            models.Message.conversation_id == conversation.id,
            models.Message.direction == "outbound",
            models.Message.message_type != _TIPO_NOTA_INTERNA,
        )
        .scalar()
    )
    if primer_saludo is None:
        # El bot nunca escribió: no hubo ni saludo, así que menos información.
        return models.AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA

    respondio = (
        db.query(models.Message.id)
        .filter(
            models.Message.conversation_id == conversation.id,
            models.Message.direction == "inbound",
            models.Message.created_at > primer_saludo,
        )
        .first()
    )
    return (
        models.AGENDAMIENTO_NIVEL_CON_INFORMACION
        if respondio is not None
        else models.AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA
    )


def pendiente_de(
    db: Session, conversation_id: int
) -> Optional[models.Agendamiento]:
    """El agendamiento sin cerrar de esta conversación, si ya existe."""
    return (
        db.query(models.Agendamiento)
        .filter(
            models.Agendamiento.conversation_id == conversation_id,
            models.Agendamiento.estado == models.AGENDAMIENTO_PENDIENTE,
        )
        .first()
    )


def registrar_por_abandono(
    db: Session,
    conversation: models.Conversation,
    *,
    asesor: Optional[str] = None,
    fecha: Optional[date] = None,
    ahora_utc: Optional[datetime] = None,
) -> Optional[models.Agendamiento]:
    """Agenda la llamada de un chat que el bot acaba de dar por abandonado.

    Devuelve `None` —sin escribir nada— cuando la conversación no llegó a
    recibir información: ésa es la mitad del pedido que separa a un cliente
    potencial de alguien que escribió una vez y nunca volvió.

    Es idempotente: si ese chat ya tiene una llamada pendiente, se devuelve la
    que hay en vez de crear otra. El índice único parcial de la tabla lo
    sostiene aunque dos ticks entren a la vez.
    """
    nivel = nivel_de_interes(db, conversation)
    if nivel != models.AGENDAMIENTO_NIVEL_CON_INFORMACION:
        logger.info(
            "agendamientos: sin llamada para conv=%s (nivel=%s)",
            conversation.id, nivel,
        )
        return None

    existente = pendiente_de(db, conversation.id)
    if existente is not None:
        return existente

    agendamiento = models.Agendamiento(
        team_id=conversation.team_id,
        conversation_id=conversation.id,
        nivel_interes=nivel,
        fecha_llamada=fecha or fecha_tentativa(ahora_utc),
        estado=models.AGENDAMIENTO_PENDIENTE,
        # El nombre del turno al momento del abandono. Si no se pudo repartir,
        # queda vacío y la pantalla lo muestra como "sin asignar" — es
        # preferible a inventar un `asesor_1` que no es nadie.
        asesor=(asesor or conversation.assigned_to or "").strip()[:64] or None,
    )
    db.add(agendamiento)
    try:
        db.commit()
    except IntegrityError:
        # Otro tick ganó la carrera. La lista del asesor no puede mostrar dos
        # renglones de la misma persona, así que se devuelve el que quedó.
        db.rollback()
        logger.info(
            "agendamientos: conv=%s ya tenía llamada pendiente (carrera)",
            conversation.id,
        )
        return pendiente_de(db, conversation.id)

    db.refresh(agendamiento)
    # Sin teléfono ni nombre en el log (regla 1/8): son datos de un tercero.
    logger.info(
        "agendamientos: llamada agendada conv=%s fecha=%s",
        conversation.id, agendamiento.fecha_llamada,
    )
    return agendamiento


# ===========================================================================
# Interesados (estrategia #22): intención de compra mientras el bot atiende
# ===========================================================================
#
# El otro lado de la ventana /agendamientos. Las llamadas de arriba son para
# quien ya se fue; los interesados son quienes **siguen hablando con el bot** y
# dieron una señal de compra (anticipo, reservar, una fecha concreta, sus
# datos). Entran a la lista `horas_para_interesado` (6) después del primer
# mensaje del episodio y salen solos si el bot cierra, si hay handoff o si la
# conversación se abandona: la consulta lo exige en cada lectura, no hay que
# acordarse de "sacarlos".
#
# Nada de lo que escribió el cliente (fragmento) ni de lo que redactó el bot
# (resumen) va a los logs: solo ids y estados (reglas 1, 6 y 8).


#: Ventana de servicio de WhatsApp: texto libre solo hasta 24 h después del
#: último mensaje del cliente.
VENTANA_WHATSAPP = timedelta(hours=24)
#: "Urgente" = a la ventana le quedan menos de 3 h.
UMBRAL_URGENTE = timedelta(hours=3)
#: Tope del umbral configurable. Fuera de [0, 72] se usa el default: un 7000
#: tecleado por error no puede esconder la lista para siempre.
HORAS_MAX_INTERESADO = 72.0
#: Señales distintas que se aceptan por turno (son 4 tipos; más es basura).
MAX_TIPOS_POR_TURNO = 4

_SESION_VIVA = (models.BOT_SESSION_RUNNING, models.BOT_SESSION_WAITING)
#: Herramientas cuyo input dice qué plan miró el cliente. Mismo texto de
#: resultado, dos nombres (motor viejo y catálogo de productos).
_HERRAMIENTAS_DE_PRECIO = ("consultar_tarifario", "consultar_precios")
_MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


class InteresadoNoEncontrado(Exception):
    """No existe o es de otro team: el router responde 404 idéntico."""


class InteresadoYaTomado(Exception):
    """La conversación ya no la atiende el bot (409)."""


class InteresadoVencido(Exception):
    """Ya no es interesado: cerrada, abandonada, gestionada… (410)."""


def config_intencion(cfg: Optional[dict]) -> Optional[dict]:
    """El bloque `llm_config.intencion_compra`, o None si el bot no lo tiene.

    `true` a secas también lo enciende (con el umbral por defecto).
    """
    valor = (cfg or {}).get("intencion_compra")
    if valor is True:
        return {}
    if isinstance(valor, dict):
        return valor
    return None


def horas_para_interesado(cfg: Optional[dict]) -> float:
    """El umbral en horas, acotado a [0, 72]; fuera de rango → 6."""
    conf = config_intencion(cfg) or {}
    try:
        horas = float(conf.get("horas_para_interesado", models.INTENCION_HORAS_DEFAULT))
    except (TypeError, ValueError):
        return float(models.INTENCION_HORAS_DEFAULT)
    if not (0.0 <= horas <= HORAS_MAX_INTERESADO):  # también descarta NaN
        return float(models.INTENCION_HORAS_DEFAULT)
    return horas


def _intenciones_de_la_herramienta(telemetry: Optional[dict]):
    """`(tipos, resumen)` de lo que el modelo registró con `registrar_intencion`.

    Lista blanca de tipos; el resumen se sanea igual que el texto del cliente
    (lo redacta un LLM a partir de lo que el cliente dijo).
    """
    crudos = (telemetry or {}).get("intenciones")
    if not isinstance(crudos, list):
        return [], None
    tipos: list = []
    resumen = None
    for item in crudos[:20]:
        if not isinstance(item, dict):
            continue
        tipo = item.get("tipo")
        if tipo not in models.INTENCION_TIPOS:
            continue
        tipos.append(tipo)
        texto = _ic.texto_seguro(item.get("resumen"), _ic.MAX_RESUMEN)
        if texto:
            resumen = texto
    return _ic.tipos_validos(tipos)[:MAX_TIPOS_POR_TURNO], resumen


def _origen(regex: bool, herramienta: bool) -> str:
    if regex and herramienta:
        return models.INTENCION_ORIGEN_AMBOS
    return models.INTENCION_ORIGEN_REGEX if regex else models.INTENCION_ORIGEN_HERRAMIENTA


def _insert_de(db: Session):
    """El `insert` con ON CONFLICT del motor en uso (Postgres en prod, SQLite
    en los tests)."""
    if db.get_bind().dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        from sqlalchemy.dialects.postgresql import insert
    return insert


def registrar_intencion(
    db: Session,
    *,
    cfg: Optional[dict],
    bot: models.Bot,
    conversation: models.Conversation,
    session: models.BotSession,
    user_input: Optional[str],
    telemetry: Optional[dict],
    ahora: Optional[datetime] = None,
) -> Optional[models.IntencionCompra]:
    """Upsert del interesado del episodio tras un turno del bot.

    Une lo que detecta la regex en el mensaje del cliente con lo que el modelo
    registró por herramienta. Sin el flag `intencion_compra` en la config del
    bot no hace NADA (ni siquiera mira la telemetría). Nunca rompe el turno:
    cualquier error queda en el log sin datos y devuelve None.
    """
    if config_intencion(cfg) is None:
        return None
    try:
        de_regex = _ic.detectar(user_input) if user_input else []
        de_herramienta, resumen = _intenciones_de_la_herramienta(telemetry)
        nuevos = _ic.tipos_validos(de_regex + de_herramienta)[:MAX_TIPOS_POR_TURNO]
        if not nuevos:
            return None

        momento = ahora or datetime.utcnow()
        fragmento = _ic.fragmento_seguro(user_input) if de_regex else None
        existente = (
            db.query(models.IntencionCompra)
            .filter(models.IntencionCompra.session_id == session.id)
            .first()
        )
        if existente is not None:
            tipos = _ic.tipos_validos(list(existente.tipos or []) + nuevos)
            viejo = existente.origen
            origen = _origen(
                bool(de_regex) or viejo in (models.INTENCION_ORIGEN_REGEX, models.INTENCION_ORIGEN_AMBOS),
                bool(de_herramienta) or viejo in (
                    models.INTENCION_ORIGEN_HERRAMIENTA, models.INTENCION_ORIGEN_AMBOS
                ),
            )
            # La primera frase que la delató es la que sirve para escribirle;
            # del resumen, el más reciente (el bot sabe más a cada turno).
            fragmento = existente.fragmento or fragmento
            resumen = resumen or existente.resumen
        else:
            tipos = nuevos
            origen = _origen(bool(de_regex), bool(de_herramienta))

        inicio = session.started_at or momento
        insert = _insert_de(db)
        stmt = insert(models.IntencionCompra.__table__).values(
            team_id=conversation.team_id,
            conversation_id=conversation.id,
            session_id=session.id,
            bot_id=bot.id,
            tipos=tipos,
            origen=origen,
            fragmento=fragmento,
            resumen=resumen,
            primera_at=momento,
            ultima_at=momento,
            visible_desde=inicio + timedelta(hours=horas_para_interesado(cfg)),
            estado=models.INTENCION_POR_CONTACTAR,
            created_at=momento,
            updated_at=momento,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["session_id"],
            set_={
                "tipos": tipos,
                "origen": origen,
                "fragmento": fragmento,
                "resumen": resumen,
                "ultima_at": momento,
                "updated_at": momento,
            },
        )
        with db.begin_nested():
            db.execute(stmt)
        db.commit()
    except Exception as exc:  # nunca tumba el turno del bot
        try:
            db.rollback()
        except Exception:  # pragma: no cover - defensivo
            pass
        # Sin traceback ni mensaje de la excepción: el de la BD podría traer
        # los valores del INSERT (fragmento del cliente).
        logger.error(
            "interesados: no se pudo registrar la intención conv=%s session=%s (%s)",
            getattr(conversation, "id", None), getattr(session, "id", None),
            type(exc).__name__,
        )
        return None

    fila = (
        db.query(models.IntencionCompra)
        .filter(models.IntencionCompra.session_id == session.id)
        .first()
    )
    logger.info(
        "interesados.registrar id=%s conv=%s team=%s session=%s tipos=%s origen=%s",
        getattr(fila, "id", None), conversation.id, conversation.team_id,
        session.id, ",".join(tipos), origen,
    )
    return fila


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

def _ultimo_entrante():
    """Subconsulta correlacionada: último mensaje del cliente en la conversación.

    Usa `ix_messages_conversation_created`. Se evalúa solo para las filas del
    team que pasaron los demás filtros, que son pocas.
    """
    return (
        select(func.max(models.Message.created_at))
        .where(
            models.Message.conversation_id == models.IntencionCompra.conversation_id,
            models.Message.direction == "inbound",
        )
        .correlate(models.IntencionCompra)
        .scalar_subquery()
    )


def _base(db: Session, team_id: int):
    """Interesados del team con su conversación, su sesión y su bot.

    El `team_id` va en el JOIN de la conversación también: una fila cuyo
    `conversation_id` apuntara a otra cuenta no sale nunca.
    """
    return (
        db.query(
            models.IntencionCompra,
            models.Conversation,
            models.BotSession,
            models.Bot,
        )
        .join(
            models.Conversation,
            (models.Conversation.id == models.IntencionCompra.conversation_id)
            & (models.Conversation.team_id == team_id),
        )
        .join(models.BotSession, models.BotSession.id == models.IntencionCompra.session_id)
        .join(models.Bot, models.Bot.id == models.IntencionCompra.bot_id)
        .filter(models.IntencionCompra.team_id == team_id)
    )


def _filtro_por_contactar(consulta, ahora: datetime):
    """La definición de interesado vigente, entera, en el WHERE.

    "Abierta" = **la sesión del episodio sigue viva** (running/waiting) **y el
    chat lo atiende el bot**. A propósito NO se mira `conversations.status`:
    cuando el cliente vuelve fuera de la ventana `retomar`, el webhook arranca
    una sesión nueva sin pasar por `_reabrir_conversacion` y la conversación
    sigue `closed` mientras el bot le contesta (comportamiento del bot 1 que no
    se toca); y cerrar a mano desde /mensajes tampoco detiene al bot. La sesión
    sí refleja la verdad: termina cuando el bot se despide, cuando se abandona
    y cuando hay handoff (este último además cambia `assigned_to`).
    """
    return consulta.filter(
        models.IntencionCompra.estado == models.INTENCION_POR_CONTACTAR,
        models.IntencionCompra.visible_desde <= ahora,
        models.BotSession.conversation_id == models.IntencionCompra.conversation_id,
        models.BotSession.status.in_(_SESION_VIVA),
        func.coalesce(models.Conversation.assigned_to, "bot") == "bot",
    )


def sigue_siendo_interesado(
    fila: models.IntencionCompra,
    conv: models.Conversation,
    sesion: Optional[models.BotSession],
    ahora: Optional[datetime] = None,
) -> bool:
    """La misma regla que `_filtro_por_contactar`, para una fila ya cargada."""
    momento = ahora or datetime.utcnow()
    return (
        fila.estado == models.INTENCION_POR_CONTACTAR
        and fila.visible_desde <= momento
        and sesion is not None
        and sesion.conversation_id == conv.id
        and sesion.status in _SESION_VIVA
        and (conv.assigned_to or "bot") == "bot"
    )


def inicio_del_dia_colombia_utc(ahora_utc: Optional[datetime] = None) -> datetime:
    """Medianoche de hoy en Colombia, expresada en UTC sin marcar."""
    dia = hoy_en_colombia(ahora_utc)
    return datetime(dia.year, dia.month, dia.day) + timedelta(hours=5)


def listar_interesados(
    db: Session,
    *,
    team_id: int,
    estado: str,
    pagina: int,
    limite: int,
    ahora: Optional[datetime] = None,
):
    """`(filas, total, resumen)` de una página. Sin N+1: número fijo de
    consultas sea cual sea el tamaño de la página.

    `filas` = lista de `(intencion, conversacion, sesion, bot, ultimo_entrante)`.
    Orden en `por_contactar` (contrato): ventana abierta primero, la que se
    cierra antes arriba; después las de ventana cerrada, la más reciente
    primero. En `contactado`/`descartado`: lo último gestionado arriba.
    """
    momento = ahora or datetime.utcnow()
    ultimo = _ultimo_entrante()
    corte = momento - VENTANA_WHATSAPP

    base = _base(db, team_id)
    if estado == models.INTENCION_POR_CONTACTAR:
        consulta = _filtro_por_contactar(base, momento)
        abierta = ultimo > corte
        orden = (
            case((abierta, 0), else_=1).asc(),
            case((abierta, ultimo), else_=None).asc(),
            func.coalesce(ultimo, datetime(1970, 1, 1)).desc(),
            models.IntencionCompra.id.asc(),
        )
    else:
        consulta = base.filter(models.IntencionCompra.estado == estado)
        orden = (
            func.coalesce(
                models.IntencionCompra.gestionado_at, models.IntencionCompra.ultima_at
            ).desc(),
            models.IntencionCompra.id.desc(),
        )

    total = consulta.count()
    filas = (
        consulta.add_columns(ultimo.label("ultimo_entrante"))
        .order_by(*orden)
        .offset((pagina - 1) * limite)
        .limit(limite)
        .all()
    )

    # El resumen es SIEMPRE del team entero (como el de las llamadas): es el
    # marcador de "cuánto me falta", no depende del filtro.
    vigentes = _filtro_por_contactar(_base(db, team_id), momento)
    urgente = (ultimo > corte) & (ultimo < corte + UMBRAL_URGENTE)
    cerrada = (ultimo.is_(None)) | (ultimo <= corte)
    por_contactar, urgentes, ventana_cerrada = (
        vigentes.with_entities(
            func.count(models.IntencionCompra.id),
            func.coalesce(func.sum(case((urgente, 1), else_=0)), 0),
            func.coalesce(func.sum(case((cerrada, 1), else_=0)), 0),
        ).one()
    )
    contactados_hoy = (
        _base(db, team_id)
        .filter(
            models.IntencionCompra.estado == models.INTENCION_CONTACTADO,
            models.IntencionCompra.gestionado_at >= inicio_del_dia_colombia_utc(momento),
        )
        .count()
    )
    resumen = {
        "por_contactar": int(por_contactar or 0),
        "urgentes": int(urgentes or 0),
        "ventana_cerrada": int(ventana_cerrada or 0),
        "contactados_hoy": int(contactados_hoy or 0),
    }
    return filas, total, resumen


def _mes_iso(valor: Optional[str], fecha: Optional[str], hoy: date) -> Optional[str]:
    """"diciembre" / "2026-12" / fecha "2026-12-16" → "2026-12"."""
    fecha = (fecha or "").strip()
    if len(fecha) >= 7 and fecha[:4].isdigit() and fecha[4] == "-" and fecha[5:7].isdigit():
        if 1 <= int(fecha[5:7]) <= 12:
            return fecha[:7]
    texto = _ic._normalizar(valor or "")
    if len(texto) >= 7 and texto[:4].isdigit() and texto[4] == "-" and texto[5:7].isdigit():
        if 1 <= int(texto[5:7]) <= 12:
            return texto[:7]
    for nombre, numero in _MESES_ES.items():
        if nombre in texto.split() or texto.startswith(nombre):
            # Un mes que ya pasó este año es el del año que viene.
            anio = hoy.year if numero >= hoy.month else hoy.year + 1
            return f"{anio:04d}-{numero:02d}"
    return None


def interes_por_sesion(
    db: Session, session_ids: list, hoy: Optional[date] = None
) -> dict:
    """`{session_id: {"mes": "2026-12"|None, "hotel": str|None}}` según la
    última consulta de precios del episodio. Una sola consulta para la página.
    """
    if not session_ids:
        return {}
    dia = hoy or hoy_en_colombia()
    filas = (
        db.query(models.BotLlmDecision.session_id, models.BotLlmDecision.tools_called)
        .filter(
            models.BotLlmDecision.session_id.in_(list(session_ids)),
            models.BotLlmDecision.tools_called.isnot(None),
        )
        .order_by(models.BotLlmDecision.id.desc())
        .all()
    )
    salida: dict = {}
    for session_id, crudo in filas:
        if session_id in salida:
            continue  # ya se tomó la más reciente
        try:
            llamadas = json.loads(crudo or "[]")
        except (ValueError, TypeError):
            continue
        for llamada in reversed(llamadas if isinstance(llamadas, list) else []):
            if not isinstance(llamada, dict) or llamada.get("tool") not in _HERRAMIENTAS_DE_PRECIO:
                continue
            entrada = llamada.get("input") if isinstance(llamada.get("input"), dict) else {}
            mes = _mes_iso(entrada.get("mes"), entrada.get("fecha"), dia)
            hotel = _ic.texto_seguro(entrada.get("hotel") or entrada.get("variante"), 60)
            if mes or hotel:
                salida[session_id] = {"mes": mes, "hotel": hotel}
                break
    return salida


def team_tiene_interesados(db: Session, team_id: int) -> bool:
    """`habilitado`: algún bot activo del team tiene `intencion_compra`."""
    from . import llm_engine

    team = db.query(models.Team).get(team_id)
    if team is None:
        return False
    bots = (
        db.query(models.Bot)
        .filter(
            models.Bot.status == "active",
            models.Bot.engine == "llm",
            (models.Bot.team_id == team_id) | (models.Bot.user_id == team.owner_user_id),
        )
        .all()
    )
    for bot in bots:
        try:
            if config_intencion(llm_engine.config_de(bot)) is not None:
                return True
        except Exception:  # pragma: no cover - config ilegible
            continue
    return False


# ---------------------------------------------------------------------------
# Acciones de la asesora
# ---------------------------------------------------------------------------

def fila_del_team(
    db: Session, intencion_id: int, team_id: int, *, para_actualizar: bool = False
):
    """`(intencion, conversacion, sesion, bot)` o InteresadoNoEncontrado.

    Ajena e inexistente dan lo mismo (404 idéntico): el `team_id` va en el
    WHERE de la intención y en el JOIN de la conversación.
    """
    consulta = _base(db, team_id).filter(models.IntencionCompra.id == intencion_id)
    if para_actualizar:
        # También la conversación: en una toma simultánea, quien pierde espera
        # el lock y relee `assigned_to` ya cambiado → 409 (no 410 por la fila
        # ya `contactado`). populate_existing: no confiar en la foto del
        # identity map.
        consulta = consulta.with_for_update(
            of=[models.IntencionCompra, models.Conversation]
        ).populate_existing()
    fila = consulta.first()
    if fila is None:
        raise InteresadoNoEncontrado()
    return fila


def cambiar_estado_interesado(
    db: Session,
    *,
    intencion_id: int,
    team_id: int,
    user_id: int,
    estado: str,
    motivo: Optional[str] = None,
    ahora: Optional[datetime] = None,
):
    """Ya lo contacté / Descartar (con motivo de la lista cerrada) / Deshacer."""
    fila, conv, sesion, bot = fila_del_team(db, intencion_id, team_id, para_actualizar=True)
    antes = fila.estado
    momento = ahora or datetime.utcnow()
    if estado == models.INTENCION_POR_CONTACTAR:
        fila.estado = estado
        fila.gestionado_por_user_id = None
        fila.gestionado_at = None
        fila.motivo_descarte = None
    else:
        fila.estado = estado
        fila.gestionado_por_user_id = user_id
        fila.gestionado_at = momento
        fila.motivo_descarte = motivo if estado == models.INTENCION_DESCARTADO else None
    db.add(fila)
    db.commit()
    db.refresh(fila)
    logger.info(
        "interesados.estado id=%s conv=%s team=%s por_user_id=%s de=%s a=%s",
        fila.id, conv.id, team_id, user_id, antes, fila.estado,
    )
    return fila, conv, sesion, bot


_ETIQUETA_TIPO = {
    "anticipo": "preguntó por el anticipo",
    "reservar": "pidió reservar",
    "fecha_concreta": "preguntó por una fecha concreta",
    "datos": "dejó sus datos",
}


def tomar_interesado(
    db: Session,
    *,
    intencion_id: int,
    team_id: int,
    user: models.User,
    ahora: Optional[datetime] = None,
):
    """La asesora se queda con el chat: mismo efecto que el handoff del bot.

    - 404 (InteresadoNoEncontrado) si no existe o es de otro team.
    - 409 (InteresadoYaTomado) si la conversación ya no la atiende el bot —
      también si otra asesora gana la carrera: la asignación es un
      compara-y-asigna (`crud.asignar_si_sigue`), no un `if` seguido de un
      UPDATE.
    - 410 (InteresadoVencido) si dejó de ser interesado (el bot cerró, se
      abandonó, sesión terminada, ya gestionada, o aún no cumplía el umbral).

    El destino sale del servidor: el nombre del usuario que hace la petición.
    En la misma transacción queda quién la tomó (`tomado_por_user_id`).
    Después: se cancelan las acciones pendientes del bot (recordatorios,
    abandono), la sesión del bot termina y queda una nota interna — que nunca
    viaja al cliente.
    """
    from . import bot_runner  # perezoso: bot_runner importa este módulo

    momento = ahora or datetime.utcnow()
    fila, conv, sesion, bot = fila_del_team(db, intencion_id, team_id, para_actualizar=True)
    if (conv.assigned_to or "bot") != "bot":
        db.rollback()
        raise InteresadoYaTomado()
    if not sigue_siendo_interesado(fila, conv, sesion, momento):
        db.rollback()
        raise InteresadoVencido()

    destino = (user.nombre or "").strip()[:64] or "asesor"
    # Un miembro llamado "bot" dejaría el chat… con el bot.
    if destino.lower() == "bot":
        destino = "asesor"
    if not crud_asignar(db, conv, destino):
        db.rollback()
        raise InteresadoYaTomado()

    antes = fila.estado
    fila.tomado_por_user_id = user.id
    fila.tomado_at = momento
    fila.estado = models.INTENCION_CONTACTADO
    fila.gestionado_por_user_id = user.id
    fila.gestionado_at = momento
    db.add(fila)
    db.commit()

    try:
        bot_runner.soltar_conversacion(db, conv)
    except Exception:  # pragma: no cover - defensivo
        # El chat ya cambió de dueño (eso es lo que no se puede perder). Si
        # cancelar lo pendiente falla, `_procesar_silencio` igual corta porque
        # `assigned_to != "bot"`.
        logger.exception("interesados: no se pudo soltar la sesión conv=%s", conv.id)

    db.refresh(conv)
    db.refresh(fila)
    tipos = [_ETIQUETA_TIPO.get(t, t) for t in (fila.tipos or [])]
    bot_runner._nota_de_handoff(
        db,
        conv,
        {
            "resumen": fila.resumen or "",
            "motivo": (
                "intención de compra detectada por el bot"
                + (f" ({', '.join(tipos)})" if tipos else "")
            ),
        },
        titulo=f"🙋 *Tomada por {destino} desde Interesados*",
        sent_by_user_id=user.id,
    )
    logger.info(
        "interesados.tomar id=%s conv=%s team=%s por_user_id=%s de=%s a=%s",
        fila.id, conv.id, team_id, user.id, antes, fila.estado,
    )
    sesion_actual = db.query(models.BotSession).get(fila.session_id)
    return fila, conv, sesion_actual, bot


def crud_asignar(db: Session, conv: models.Conversation, destino: str) -> bool:
    from .. import crud

    return crud.asignar_si_sigue(
        db,
        conversation_id=conv.id,
        team_id=conv.team_id,
        esperado="bot",
        destino=destino,
    )
