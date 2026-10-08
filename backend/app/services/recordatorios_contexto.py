"""Recordatorios con contexto del bot 2 de Arranquemos Pues (estrategia 28).

El 2.º y el 3.º recordatorio de hoy («Te quedé debiendo la respuesta», «Última
razón por hoy») no dicen nada nuevo y rinden 11,7 % y 7,7 %. El bot sí sabe qué
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
