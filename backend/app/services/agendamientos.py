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

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models

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
