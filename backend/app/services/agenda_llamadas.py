"""Agenda de llamadas del bot D (Sprint 36, puerta 2; diseño de seguridad §3).

La persona que ya vio el total de su grupo y prefiere hablarlo elige una de las
5 franjas que arma el servidor (`services/horario.py`), y queda en la lista de
llamadas de Agendamientos con su franja y su cotización. Aquí vive todo lo que
toca la base:

  * `ocupacion`: cuántas llamadas pendientes tiene cada franja del team.
  * `reservar`: la inserción con cupo (3.3). Un puesto (1..cupo) por llamada, y
    el índice único parcial `uq_agendamientos_franja_puesto` hace cumplir el
    cupo aunque dos clientes elijan la misma franja a la vez: cada intento va
    en un `begin_nested()`; un `IntegrityError` pasa al siguiente puesto, y sin
    puestos la franja está llena. Si la conversación ya tenía una llamada
    pendiente (la del abandono, o una franja anterior), se **actualiza esa
    fila** — `uq_agendamientos_conv_pendiente` no deja tener dos — y el puesto
    viejo se libera solo.
  * `avisos_del_tick`: al empezar la franja, un aviso; si se acaba sin
    resultado, una alerta (3.5). Idempotentes: cada uno sale solo si el UPDATE
    que pone su sello (`WHERE ... IS NULL`) toca una fila. Los dos son notas
    internas en la conversación: **no salen de la plataforma** (mandarle un
    WhatsApp al celular de la asesora requiere su propia revisión).

Nada de lo que se loggea lleva teléfono, nombre, texto del cliente ni la
cotización (3.6): solo ids, la franja y el puesto.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models
from . import horario

logger = logging.getLogger(__name__)

_TZ_CO = timezone(timedelta(hours=-5))

LLENA = "llena"
MISMA = "misma"

TITULO_AVISO = "📞 *Llamada agendada por el bot*"
TITULO_ALERTA = "⚠️ *Llamada sin resultado*"


def _naive_utc(valor: datetime) -> datetime:
    if valor.tzinfo is None:
        return valor
    return valor.astimezone(timezone.utc).replace(tzinfo=None)


def ocupacion(
    db: Session,
    team_id: int,
    *,
    desde: datetime,
    excluir_conversation_id: Optional[int] = None,
) -> Dict[datetime, int]:
    """inicio de franja (UTC sin zona) → llamadas pendientes del team.

    La propia conversación no cuenta: quien cambia de franja no se quita a sí
    mismo un cupo que va a liberar."""
    q = (
        db.query(models.Agendamiento.franja_inicio, func.count(models.Agendamiento.id))
        .filter(
            models.Agendamiento.team_id == team_id,
            models.Agendamiento.estado == models.AGENDAMIENTO_PENDIENTE,
            models.Agendamiento.franja_inicio.isnot(None),
            models.Agendamiento.franja_inicio >= _naive_utc(desde),
        )
    )
    if excluir_conversation_id is not None:
        q = q.filter(models.Agendamiento.conversation_id != excluir_conversation_id)
    return {inicio: int(n) for inicio, n in q.group_by(models.Agendamiento.franja_inicio).all()}


def franjas_para(
    db: Session,
    conversation: models.Conversation,
    cfg_horario: dict,
    *,
    ahora_utc: datetime,
    cupo: int,
) -> List[horario.Franja]:
    """Las 5 franjas que se le ofrecen a esta conversación ahora."""
    ocupadas = ocupacion(
        db, conversation.team_id, desde=ahora_utc,
        excluir_conversation_id=conversation.id,
    )
    return horario.proximas_franjas_llamada(
        ahora_utc, cfg_horario, ocupacion=ocupadas, cupo=cupo,
    )


def fecha_local(instante_utc: datetime) -> date:
    """El día del calendario de la asesora (Colombia) de un instante UTC."""
    return _naive_utc(instante_utc).replace(tzinfo=timezone.utc).astimezone(_TZ_CO).date()


def _pendiente(db: Session, conversation_id: int) -> Optional[models.Agendamiento]:
    return (
        db.query(models.Agendamiento)
        .filter(
            models.Agendamiento.conversation_id == conversation_id,
            models.Agendamiento.estado == models.AGENDAMIENTO_PENDIENTE,
        )
        .first()
    )


def _poner_franja(
    fila: models.Agendamiento,
    franja: horario.Franja,
    puesto: int,
    cotizacion: Optional[str],
) -> None:
    fila.franja_inicio = _naive_utc(franja.inicio)
    fila.franja_fin = _naive_utc(franja.fin)
    fila.puesto = puesto
    fila.origen = models.AGENDAMIENTO_ORIGEN_BOT_LLAMADA
    fila.fecha_llamada = fecha_local(franja.inicio)
    fila.cotizacion = (cotizacion or None) and cotizacion[: models.AGENDAMIENTO_COTIZACION_MAX]
    # Franja nueva = avisos y resultado nuevos.
    fila.aviso_inicio_at = None
    fila.alerta_fin_at = None
    fila.resultado = None
    fila.resultado_por_user_id = None
    fila.resultado_at = None


def reservar(
    db: Session,
    conversation: models.Conversation,
    franja: horario.Franja,
    *,
    cupo: int,
    cotizacion: Optional[str],
) -> Tuple[Optional[models.Agendamiento], str]:
    """Agenda (o mueve) la llamada de la conversación en `franja`.

    Devuelve `(fila, "")` si quedó, `(fila, "misma")` si ya estaba en esa
    franja, o `(None, "llena")` si no quedan puestos. Hace commit.
    """
    cupo = max(1, int(cupo or 1))
    inicio = _naive_utc(franja.inicio)
    existente = _pendiente(db, conversation.id)
    if existente is not None and existente.franja_inicio == inicio and existente.puesto:
        if cotizacion and existente.cotizacion != cotizacion[: models.AGENDAMIENTO_COTIZACION_MAX]:
            existente.cotizacion = cotizacion[: models.AGENDAMIENTO_COTIZACION_MAX]
            db.commit()
        return existente, MISMA

    puesto = 1
    # Un intento de más por si, en medio, aparece la pendiente del abandono
    # (otro tick la creó): ese choque no gasta un puesto.
    intentos = cupo + 2
    while puesto <= cupo and intentos > 0:
        intentos -= 1
        try:
            with db.begin_nested():
                if existente is None:
                    fila = models.Agendamiento(
                        team_id=conversation.team_id,
                        conversation_id=conversation.id,
                        nivel_interes=models.AGENDAMIENTO_NIVEL_CON_INFORMACION,
                        estado=models.AGENDAMIENTO_PENDIENTE,
                        fecha_llamada=fecha_local(franja.inicio),
                    )
                    _poner_franja(fila, franja, puesto, cotizacion)
                    db.add(fila)
                else:
                    fila = existente
                    _poner_franja(fila, franja, puesto, cotizacion)
                db.flush()
            db.commit()
            db.refresh(fila)
            logger.info(
                "agenda.llamada conv=%s team=%s franja=%s puesto=%s",
                conversation.id, conversation.team_id,
                fila.franja_inicio.isoformat(), fila.puesto,
            )
            return fila, ""
        except IntegrityError:
            if existente is None:
                otra = _pendiente(db, conversation.id)
                if otra is not None:
                    # Era `uq_agendamientos_conv_pendiente`: la conversación ya
                    # tiene su fila; se actualiza esa, con el mismo puesto.
                    existente = otra
                    continue
            else:
                db.refresh(existente)
            puesto += 1
    db.rollback()
    logger.info(
        "agenda.llena conv=%s team=%s franja=%s cupo=%s",
        conversation.id, conversation.team_id, inicio.isoformat(), cupo,
    )
    return None, LLENA


# ---------------------------------------------------------------------------
# Avisos del tick (3.5)
# ---------------------------------------------------------------------------


@dataclass
class ResultadoTick:
    avisos: int = 0
    alertas: int = 0


def _rango(fila: models.Agendamiento) -> str:
    return horario.rango_de_la_franja(
        horario.Franja(inicio=fila.franja_inicio, fin=fila.franja_fin), {}
    )


def _sellar(db: Session, fila_id: int, columna, ahora: datetime) -> bool:
    """El UPDATE que pone el sello. True solo para quien lo puso."""
    n = (
        db.query(models.Agendamiento)
        .filter(models.Agendamiento.id == fila_id, columna.is_(None))
        .update({columna: ahora}, synchronize_session=False)
    )
    db.commit()
    return n == 1


def _nota(db: Session, fila: models.Agendamiento, texto: str) -> None:
    conv = (
        db.query(models.Conversation)
        .filter(
            models.Conversation.id == fila.conversation_id,
            models.Conversation.team_id == fila.team_id,
        )
        .first()
    )
    if conv is None:
        return
    # `nota_interna`, sin autor: no viaja a WhatsApp, no cuenta como humano ni
    # como entrante, y sube la conversación en la bandeja (`last_message_at`).
    crud.add_message(
        db, conv, direction="outbound", content=texto,
        message_type="nota_interna", status="sent", sent_by_user_id=None,
    )


def avisos_del_tick(db: Session, ahora: Optional[datetime] = None) -> ResultadoTick:
    """Aviso al empezar la franja y alerta si se acabó sin resultado.

    Solo llamadas que agendó el bot (`origen = bot_llamada`), pendientes. Un
    aviso de una franja que ya terminó no sale (llega la alerta en su lugar).
    """
    ahora = _naive_utc(ahora or datetime.utcnow())
    res = ResultadoTick()
    A = models.Agendamiento
    base = db.query(A.id).filter(
        A.origen == models.AGENDAMIENTO_ORIGEN_BOT_LLAMADA,
        A.estado == models.AGENDAMIENTO_PENDIENTE,
        A.franja_inicio.isnot(None),
        A.franja_fin.isnot(None),
    )
    por_avisar = [
        i for (i,) in base.filter(
            A.aviso_inicio_at.is_(None), A.franja_inicio <= ahora, A.franja_fin > ahora,
        ).order_by(A.franja_inicio, A.id).limit(200)
    ]
    for fila_id in por_avisar:
        if not _sellar(db, fila_id, A.aviso_inicio_at, ahora):
            continue
        fila = db.get(A, fila_id)
        lineas = [TITULO_AVISO, f"Empieza la franja: {_rango(fila)}. Llámalo ahora."]
        if fila.cotizacion:
            lineas.append(f"Cotización: {fila.cotizacion}")
        lineas.append("Cuando termines, marca el resultado en Agendamientos.")
        _nota(db, fila, "\n".join(lineas))
        res.avisos += 1
        logger.info("agenda.aviso id=%s conv=%s team=%s", fila.id, fila.conversation_id, fila.team_id)

    por_alertar = [
        i for (i,) in base.filter(
            A.alerta_fin_at.is_(None), A.resultado.is_(None), A.franja_fin <= ahora,
        ).order_by(A.franja_fin, A.id).limit(200)
    ]
    for fila_id in por_alertar:
        if not _sellar(db, fila_id, A.alerta_fin_at, ahora):
            continue
        fila = db.get(A, fila_id)
        _nota(db, fila, "\n".join([
            TITULO_ALERTA,
            f"Se acabó la franja ({_rango(fila)}) y la llamada no tiene resultado.",
            "Si ya llamaste, márcalo en Agendamientos; si no, llámalo apenas puedas.",
        ]))
        res.alertas += 1
        logger.info("agenda.alerta id=%s conv=%s team=%s", fila.id, fila.conversation_id, fila.team_id)
    return res
