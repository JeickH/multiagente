"""Recordatorios con contexto del bot 2 de Arranquemos Pues (estrategia 28).

El 2.º y el 3.º recordatorio de entonces (uno que se disculpaba por una
respuesta pendiente y «Última razón por hoy») no decían nada nuevo y rinden 11,7 % y 7,7 %. El bot sí sabe qué
mes y qué hotel miró la persona, y el tarifario sabe qué salidas de ese mes
quedan: un recordatorio con fechas y un precio concretos es una razón para
volver.

`texto_recordatorio` llena la plantilla de la etapa (`etapa["plantilla"]`) con
lo que la persona consultó por última vez. Si falta **cualquier** dato que la
plantilla use, o ya no quedan salidas de ese mes, devuelve ``None`` y el
llamador (`bot_runner`) manda el texto fijo de hoy (`etapa["texto"]`). Nunca
llama al modelo y nunca inventa: todo sale de `bot_llm_decisions` y del
tarifario.

**Nunca dice «con cupo».** El tarifario no tiene cupos; esto anuncia las
salidas que **quedan** (no han pasado). Si una plantilla afirma cupo, se
descarta (``None`` + warning sin contenido en el log).

Placeholders (``str.format``), todos opcionales — solo se exigen los que la
plantilla usa:

  ``{nombre}``        primer nombre de `conversation.contact_name` (si es un
                      nombre de verdad; «Cliente», «No proporcionado»… no)
  ``{mes}``           «octubre»
  ``{salidas}``       «16 al 19, 23 al 26 y 30 al 2 de noviembre»
  ``{n_salidas}``     «3»
  ``{desde}``         «$459.000» (mínimo en múltiple de esas salidas)
  ``{anticipo_pct}``  «30» (de `tarifario.extras()`)
  ``{hotel}``         «Amor de Dios» (extensión: solo si la consulta lo nombró)

OJO con ``{nombre}``: el bot 2 pide el nombre al reservar, así que casi nadie
lo tiene a esta altura. Una plantilla con ``{nombre}`` cae al texto fijo con
todo el que no lo haya dado; por eso las sugeridas no lo usan.

Plantillas sugeridas (tono del bot: español de Colombia, emojis moderados): ver
`PLANTILLAS_SUGERIDAS` abajo. La config la pone el agente «variante» en
`seguimiento.recordatorios[i].plantilla` (etapa 2 = 5 h, etapa 3 = 23 h); el
`texto` fijo de hoy se queda al lado como respaldo.

  Etapa 2 (5 h)::

      ¡Hola de nuevo! 👋 Te cuento que para {mes} todavía quedan estas
      salidas: {salidas}, desde {desde} por persona 🌴 ¿Te reviso alguna?

  Etapa 3 (23 h)::

      Última razón por hoy 🌴 Si te animas para {mes}, las salidas que quedan
      son {salidas}, desde {desde} por persona, y apartas tu cupo con un
      anticipo del {anticipo_pct}% 🙌 ¿Te ayudo con alguna?

(«apartas tu cupo con un anticipo» es la forma de reservar, no una afirmación
de que haya cupo; eso sí está permitido.)
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from string import Formatter
from typing import Any, Dict, List, Optional, Tuple

from app import models
from app.services import tarifario

logger = logging.getLogger(__name__)

#: Para las etapas 2 (5 h) y 3 (23 h) de `seguimiento.recordatorios`. No usan
#: `{nombre}` (casi nadie lo ha dado a esa altura) ni `{n_salidas}` (con una
#: sola salida se lee «las 1 salidas»). Probadas en
#: `tests/viajes/variante_b/test_precios_recordatorios.py`.
PLANTILLAS_SUGERIDAS = {
    "etapa_2": (
        "¡Hola de nuevo! 👋 Te cuento que para {mes} todavía quedan estas "
        "salidas: {salidas}, desde {desde} por persona 🌴 ¿Te reviso alguna?"
    ),
    "etapa_3": (
        "Última razón por hoy 🌴 Si te animas para {mes}, las salidas que "
        "quedan son {salidas}, desde {desde} por persona, y apartas tu cupo "
        "con un anticipo del {anticipo_pct}% 🙌 ¿Te ayudo con alguna?"
    ),
}

#: Herramientas de precios: la vieja (`tarifario`) y la nueva (`productos`).
_CONSULTAS = ("consultar_tarifario", "consultar_precios")

#: Afirmar disponibilidad está prohibido (el tarifario no tiene cupos).
#: «apartas tu cupo» / «te aparto el cupo» sí se permite: es cómo se reserva.
_AFIRMA_CUPO_RE = re.compile(
    r"\b(?:con|hay|quedan?|tienen?|tenemos|todav[ií]a\s+hay|a[uú]n\s+hay)\s+"
    r"(?:\w+\s+){0,2}cupos?\b"
    r"|\bcupos?\s+disponibles?\b"
    r"|\bdisponibilidad\b",
    re.IGNORECASE,
)

#: Lo que no es un nombre aunque esté en `contact_name`.
_NO_ES_NOMBRE = {
    "cliente", "usuario", "usuaria", "no", "sin", "desconocido", "desconocida",
    "anonimo", "anónimo", "n/a", "na", "null", "none", "prueba", "test",
    "amigo", "amiga", "señor", "señora", "senor", "senora",
}


def _primer_nombre(contact_name: Optional[str]) -> Optional[str]:
    crudo = (contact_name or "").strip()
    if not crudo or any(c.isdigit() for c in crudo) or "@" in crudo:
        return None
    primero = crudo.split()[0].strip(".,;:!¡¿?")
    if len(primero) < 2 or primero.lower() in _NO_ES_NOMBRE:
        return None
    if not all(c.isalpha() or c in "'-" for c in primero):
        return None
    return primero[:1].upper() + primero[1:].lower()


#: Un recordatorio no es el tarifario: en diciembre quedaban 14 salidas y el
#: mensaje se volvía un listado. Se nombran las primeras y se cuenta el resto.
MAX_SALIDAS_EN_RECORDATORIO = 4


def _lista_y(items: List[str]) -> str:
    if len(items) > MAX_SALIDAS_EN_RECORDATORIO:
        resto = len(items) - MAX_SALIDAS_EN_RECORDATORIO
        return (
            ", ".join(items[:MAX_SALIDAS_EN_RECORDATORIO])
            + f" y {resto} más"
        )
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


def _ultima_consulta(db, conversation, bot) -> Optional[Dict[str, str]]:
    """Input de la última llamada a una herramienta de precios en esta
    conversación (de este bot). Los inputs quedan en
    `bot_llm_decisions.tools_called` como JSON ``[{tool, input, resultado}]``
    (`llm_engine`, recortados a 200 caracteres por campo)."""
    q = db.query(models.BotLlmDecision.tools_called).filter(
        models.BotLlmDecision.conversation_id == conversation.id,
        models.BotLlmDecision.tools_called.isnot(None),
    )
    bot_id = getattr(bot, "id", None)
    if bot_id is not None:
        q = q.filter(models.BotLlmDecision.bot_id == bot_id)
    filas = q.order_by(
        models.BotLlmDecision.created_at.desc(), models.BotLlmDecision.id.desc()
    ).limit(50).all()
    for (crudo,) in filas:
        try:
            llamadas = json.loads(crudo or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(llamadas, list):
            continue
        for llamada in reversed(llamadas):
            if not isinstance(llamada, dict) or llamada.get("tool") not in _CONSULTAS:
                continue
            entrada = llamada.get("input")
            if isinstance(entrada, dict):
                return {"tool": llamada["tool"],
                        **{k: str(v) for k, v in entrada.items()}}
    return None


def _mes_anio(consulta: Dict[str, str], hoy: date) -> Optional[Tuple[int, int]]:
    fecha_txt = (consulta.get("fecha") or "").strip()[:10]
    mes = tarifario.normalizar_mes(consulta.get("mes") or "")
    if fecha_txt:
        try:
            pedida = date.fromisoformat(fecha_txt)
        except ValueError:
            pedida = None
        if pedida is not None:
            resuelta = tarifario.resolver_fecha(pedida, mes, hoy)
            if mes is None or resuelta.month == mes:
                return resuelta.month, resuelta.year
    if mes is None:
        return None
    # El próximo mes con ese número: si ya pasó este año, es el del siguiente.
    anio = hoy.year if mes >= hoy.month else hoy.year + 1
    return mes, anio


def _hotel(consulta: Dict[str, str]) -> Tuple[Optional[str], bool]:
    """(texto del hotel, reconocido). `consultar_tarifario` lo trae en
    `hotel`; `consultar_precios` en `variante` (el producto es el plan)."""
    crudo = (consulta.get("hotel") or consulta.get("variante") or "").strip()
    if not crudo:
        return None, True
    clave = tarifario.normalizar_hotel(crudo)
    return clave, clave is not None


def texto_recordatorio(
    db, *, conversation, bot, cfg: dict, etapa: dict, hoy: date
) -> str | None:
    """Texto del recordatorio con contexto, o ``None`` para usar el fijo.

    ``None`` si: el flag `recordatorios_con_contexto` no está, la etapa no
    trae `plantilla`, no hay consulta de precios en la conversación, la
    consulta no dice mes, no quedan salidas de ese mes, falta un dato que la
    plantilla usa, la plantilla está mal formada o afirma cupo. Cualquier
    error de base también da ``None`` (y queda en el log sin contenido).
    """
    if not isinstance(cfg, dict) or not cfg.get("recordatorios_con_contexto"):
        return None
    plantilla = (etapa or {}).get("plantilla") if isinstance(etapa, dict) else None
    if not isinstance(plantilla, str) or not plantilla.strip():
        return None
    try:
        campos = {
            nombre for _, nombre, _, _ in Formatter().parse(plantilla) if nombre
        }
    except ValueError:
        logger.warning("recordatorios_contexto: plantilla mal formada")
        return None

    try:
        consulta = _ultima_consulta(db, conversation, bot)
    except Exception:  # pragma: no cover - defensivo
        logger.exception(
            "recordatorios_contexto: no se pudo leer la bitácora conv=%s",
            getattr(conversation, "id", None),
        )
        return None
    if consulta is None:
        return None

    mes_anio = _mes_anio(consulta, hoy)
    if mes_anio is None:
        return None
    mes, anio = mes_anio
    hotel, reconocido = _hotel(consulta)
    if not reconocido:
        return None

    salidas = tarifario.salidas_restantes(mes, anio, hotel, hoy)
    if not salidas:
        return None

    datos: Dict[str, Any] = {
        "mes": tarifario._NOMBRE_MES[mes].lower(),
        "salidas": _lista_y([s["etiqueta"] for s in salidas]),
        "n_salidas": str(len(salidas)),
        "desde": tarifario._pesos(min(int(s["desde"]) for s in salidas)),
    }
    pct = tarifario.extras().get("anticipo_pct")
    if isinstance(pct, int) and 0 < pct < 100:
        datos["anticipo_pct"] = str(pct)
    nombre = _primer_nombre(getattr(conversation, "contact_name", None))
    if nombre:
        datos["nombre"] = nombre
    if hotel:
        datos["hotel"] = tarifario._NOMBRE_HOTEL[hotel]

    if not campos <= set(datos):
        return None
    try:
        texto = plantilla.format(**datos).strip()
    except (KeyError, IndexError, ValueError):
        logger.warning("recordatorios_contexto: plantilla mal formada")
        return None
    if _AFIRMA_CUPO_RE.search(texto):
        logger.warning(
            "recordatorios_contexto: la plantilla afirma cupo; se usa el texto fijo"
        )
        return None
    return texto or None



# ===========================================================================
# Sprint 36 (punto 4): el recordatorio lee la conversación
# ===========================================================================
#
# Lo que el CEO vio en los chats de los bots 12, 21 y 22: recordatorios que
# volvían a preguntar lo que la persona ya había dicho («¿Cuántas personas
# viajarían?» a quien dijo «somos 2»), que numeraban otras opciones con los
# mismos números del menú anterior (el «2» que antes era Bohíos pasaba a ser
# «Prefiero otro mes») y que se disculpaban por una respuesta que nadie había
# quedado debiendo. `ajustar_a_la_conversacion` corre sobre el texto ya elegido
# (fijo, por etapa, con contexto o de promoción) justo antes de enviarlo. Es
# determinista: nunca llama al modelo y solo puede cambiar el texto por uno de
# los neutros de abajo, que no preguntan nada ni traen números nuevos.

#: «Te quedé debiendo la respuesta», «quedé debiendo», «te debo la respuesta».
_DEUDA_RE = re.compile(
    r"[^.!?\n]*\b(?:te\s+)?qued[eé]\s+debiend\w*\b[^.!?\n]*[.!?]*\s*"
    r"|[^.!?\n]*\bte\s+debo\s+(?:la|una)\s+respuesta\b[^.!?\n]*[.!?]*\s*",
    re.IGNORECASE,
)

#: Neutros por posición en la cadena. Sin preguntas por mes, hotel o personas,
#: sin números, sin cifras y sin la disculpa.
NEUTRO_PRIMERO = "¿Seguimos con tu plan? 😊 Aquí estoy para ayudarte a dejarlo listo 🌴"
NEUTRO_MEDIO = (
    "¡Hola de nuevo! 👋 ¿Seguimos con tu plan? 🌴 Cuando tengas un momento me "
    "cuentas y lo dejamos listo 🙌"
)
NEUTRO_ULTIMO = (
    "Última razón por hoy 🌴 Si más adelante quieres retomar el plan, aquí estoy "
    "y con gusto te ayudo. ¡Que estés muy bien! 😊"
)
#: Encabezados para repetir el menú anterior tal cual (mismos números, mismo
#: significado).
_CON_MENU = {
    "primero": "¿Seguimos? 😊 Te dejo otra vez las opciones 👇",
    "medio": "¡Hola de nuevo! 👋 ¿Seguimos con tu plan? 🌴 Respóndeme con el número 👇",
    "ultimo": "Última razón por hoy 🌴 Si te animas, respóndeme con un número 👇",
}

#: Lo que un recordatorio pregunta (sobre el texto normalizado, sin tildes).
_PREGUNTAS = {
    "personas": re.compile(
        r"cuant[oa]s\s+(?:personas|adultos|viajeros|pasajeros|viajan|viajarian|van|"
        r"irian|serian|son)\b|cuantos\s+son\b"
    ),
    "mes": re.compile(r"\b(?:que|cual)\s+mes\b|\bpara\s+que\s+mes\b|\bque\s+fecha\b"),
    "hotel": re.compile(r"\b(?:que|cual)\s+hotel\b"),
}

_NUM = r"(?:\d{1,2}|un[oa]?|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
#: Lo que dice la persona cuando cuenta cuántos van.
_DIJO_PERSONAS_RE = re.compile(
    rf"\b(?:somos|seriamos|vamos|iriamos|viajamos|viajariamos)\s+{_NUM}\b"
    rf"|\b{_NUM}\s+(?:personas|adultos|pasajeros|viajeros|cupos)\b"
    r"|\b(?:mi\s+(?:espos[oa]|pareja|novi[oa]|marido|mujer|mama|papa|herman[oa]|amig[oa])"
    r"\s+y\s+yo|yo\s+y\s+mi\s+\w+)\b"
    r"|\b(?:yo\s+sol[oa]|viajo\s+sol[oa]|voy\s+sol[oa])\b"
)
_OPCION_RE = re.compile(r"^\s*(?:[*_]*[0-9]️?⃣|[*_]*[1-9][*_]*\s*(?:[.)]|\s-|-\s))")


def sin_deuda(texto: Optional[str]) -> str:
    """Quita la frase de la disculpa por una respuesta pendiente («Te quedé
    debiendo la respuesta por acá»). Vale para recordatorios y para lo que
    redacte el modelo. Devuelve el resto (puede quedar vacío)."""
    if not texto:
        return texto or ""
    if not _DEUDA_RE.search(texto):
        return texto
    limpio = _DEUDA_RE.sub(" ", texto)
    limpio = re.sub(r"[ \t]{2,}", " ", limpio)
    limpio = "\n".join(l.strip() for l in limpio.split("\n"))
    return limpio.strip()


def tiene_deuda(texto: Optional[str]) -> bool:
    return bool(_DEUDA_RE.search(texto or ""))


def preguntas_de(texto: str) -> set:
    """Qué pregunta el recordatorio: subconjunto de {"personas", "mes", "hotel"}."""
    from app.services import senales

    normal = senales.normalizar(texto)
    return {clave for clave, patron in _PREGUNTAS.items() if patron.search(normal)}


def lo_que_ya_dijo(db, conversation, *, limite: int = 80) -> set:
    """Qué ya contó la persona: subconjunto de {"personas", "mes", "hotel"}.

    Tres fuentes, ninguna con texto libre del modelo:
      * La última consulta de precios del bot (`tools_called`): `mes`/`fecha`,
        `hotel`/`variante` y `adultos` (el grupo, Sprint 36).
      * Lo que escribió la persona: un mes con nombre, un hotel, «somos 2».
      * Una respuesta con el número de una opción del menú anterior del bot
        («2» a «1️⃣ 1 persona 2️⃣ 2 personas»).
    """
    from app.services import recortes_turno, senales

    sabido: set = set()
    try:
        consulta = _ultima_consulta(db, conversation, None) or {}
    except Exception:  # pragma: no cover - defensivo
        consulta = {}
    if (consulta.get("mes") or "").strip() or (consulta.get("fecha") or "").strip():
        sabido.add("mes")
    if (consulta.get("hotel") or consulta.get("variante") or "").strip():
        sabido.add("hotel")
    if (consulta.get("adultos") or "").strip():
        sabido.add("personas")

    filas = (
        db.query(models.Message.direction, models.Message.content,
                 models.Message.sent_by_user_id, models.Message.message_type)
        .filter(models.Message.conversation_id == conversation.id)
        .order_by(models.Message.id.desc())
        .limit(limite)
        .all()
    )
    ultimo_menu: Dict[int, str] = {}
    for direccion, contenido, autor, tipo in reversed(filas):
        if tipo == "nota_interna":
            continue
        texto = contenido or ""
        if direccion == "outbound":
            if autor is None:
                ultimo_menu = recortes_turno.opciones_numeradas(texto) or ultimo_menu
            continue
        normal = senales.normalizar(texto)
        if senales.mes_mencionado(texto):
            sabido.add("mes")
        if tarifario.normalizar_hotel(texto):
            sabido.add("hotel")
        if _DIJO_PERSONAS_RE.search(normal):
            sabido.add("personas")
        n = senales.numero_elegido(texto)
        if n is not None and n in ultimo_menu:
            etiqueta = senales.normalizar(ultimo_menu[n])
            if "persona" in etiqueta or "ninos" in etiqueta or "niños" in etiqueta:
                sabido.add("personas")
            if tarifario.normalizar_hotel(etiqueta):
                sabido.add("hotel")
            if senales.mes_mencionado(etiqueta):
                sabido.add("mes")
    return sabido


def _ultimo_del_bot(db, conversation) -> str:
    fila = (
        db.query(models.Message.content)
        .filter(
            models.Message.conversation_id == conversation.id,
            models.Message.direction == "outbound",
            models.Message.sent_by_user_id.is_(None),
            models.Message.message_type.notin_(("nota_interna", "template")),
        )
        .order_by(models.Message.id.desc())
        .first()
    )
    return (fila[0] or "") if fila else ""


def _etiqueta_comparable(texto: str) -> str:
    from app.services import senales

    return re.sub(r"[^a-z0-9ñ ]", "", senales.normalizar(texto)).strip()


def menu_en_conflicto(anterior: str, nuevo: str) -> bool:
    """¿El recordatorio numera opciones con los números del menú anterior pero
    con otro significado? Solo cuenta si los dos traen menú."""
    from app.services import recortes_turno

    viejo = recortes_turno.opciones_numeradas(anterior)
    nuevas = recortes_turno.opciones_numeradas(nuevo)
    if not viejo or not nuevas:
        return False
    return any(
        n in viejo and _etiqueta_comparable(viejo[n]) != _etiqueta_comparable(etiqueta)
        for n, etiqueta in nuevas.items()
    )


def _lineas_de_opciones(texto: str) -> List[str]:
    return [l.rstrip() for l in (texto or "").split("\n") if _OPCION_RE.match(l)]


def _posicion(posicion: int, total: int) -> str:
    if total > 0 and posicion >= total - 1:
        return "ultimo"
    return "primero" if posicion == 0 else "medio"


def _neutro(posicion: int, total: int, menu_anterior: str) -> str:
    """El texto de respaldo. Si el último mensaje del bot traía un menú, lo
    repite tal cual (mismos números, mismo significado); si no, sin opciones."""
    lugar = _posicion(posicion, total)
    opciones = _lineas_de_opciones(menu_anterior)
    if opciones:
        return _CON_MENU[lugar] + "\n" + "\n".join(opciones)
    return {"primero": NEUTRO_PRIMERO, "medio": NEUTRO_MEDIO, "ultimo": NEUTRO_ULTIMO}[lugar]


def ajustar_a_la_conversacion(
    db, *, conversation, texto: str, posicion: int, total: int
) -> Tuple[str, str]:
    """`(texto, motivo)`: el recordatorio listo para enviar.

    `motivo` es "" si el texto salió igual, o el porqué del cambio para el log
    (`deuda`, `repregunta:<campo>`, `menu`). Nunca el contenido.

    1. Sin la disculpa por una respuesta pendiente.
    2. Si pregunta algo que la persona ya contestó → neutro.
    3. Si numera opciones con otro significado que el último menú del bot →
       neutro con ese mismo menú repetido.
    """
    motivo = ""
    anterior = _ultimo_del_bot(db, conversation)
    if tiene_deuda(texto):
        limpio = sin_deuda(texto)
        motivo = "deuda"
        # Si quitarla deja el mensaje en nada (o solo un saludo), va el neutro.
        texto = limpio if len(limpio) >= 25 else _neutro(posicion, total, anterior)
    repetidas = preguntas_de(texto) & lo_que_ya_dijo(db, conversation)
    if repetidas:
        return _neutro(posicion, total, anterior), "repregunta:" + ",".join(sorted(repetidas))
    if menu_en_conflicto(anterior, texto):
        return _neutro(posicion, total, anterior), "menu"
    return texto, motivo
