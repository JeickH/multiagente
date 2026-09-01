"""Bot runner: orquesta motor + sesión persistida + envío a Meta.

Es la capa entre `bot_engine.advance()` (puro) y el mundo real:
carga la sesión de DB, corre el motor, envía cada acción por WhatsApp
Cloud API, persiste sesiones y programa delays.

Invocado desde:
  - meta_webhook.py     cuando entra un mensaje y hay bot que responder.
  - scheduler tick      cuando vence un BotPendingAction de delay.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .. import crud, models
from . import bot_engine, llm_engine, messaging, meta_whatsapp

logger = logging.getLogger(__name__)


def _load_state(session: Optional[models.BotSession]) -> Optional[dict]:
    if session is None or not session.state:
        return None
    try:
        return json.loads(session.state)
    except (ValueError, TypeError):
        return None


def _persist_state(
    db: Session,
    session: models.BotSession,
    next_state: Optional[dict],
    finished: bool,
    waiting: bool,
) -> None:
    session.state = json.dumps(next_state) if next_state else None
    if finished:
        session.status = models.BOT_SESSION_FINISHED
        session.finished_at = datetime.utcnow()
    elif waiting:
        session.status = models.BOT_SESSION_WAITING
    else:
        session.status = models.BOT_SESSION_RUNNING
    session.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(session)


def _create_session(
    db: Session, bot: models.Bot, conversation_id: int
) -> models.BotSession:
    s = models.BotSession(
        bot_id=bot.id,
        conversation_id=conversation_id,
        state=None,
        status=models.BOT_SESSION_RUNNING,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _schedule_delay(
    db: Session, session: models.BotSession, seconds: int
) -> None:
    pa = models.BotPendingAction(
        session_id=session.id,
        scheduled_at=datetime.utcnow() + timedelta(seconds=max(seconds, 1)),
        action_type=models.BOT_PENDING_ACTION_RESUME,
        status=models.BOT_PENDING_STATUS_PENDING,
    )
    db.add(pa)
    db.commit()


# ---------------------------------------------------------------------------
# Seguimiento y abandono (#377): las dos acciones programadas del bot LLM
# ---------------------------------------------------------------------------

#: Los dos tipos que NO pueden pasar por `run_turn`. Está escrito aquí y no
#: suelto en cada `if` porque olvidarlo es el error caro: `run_turn` con
#: `user_input=None` le manda `_FIRST_TURN_PROMPT` al modelo, que es un saludo
#: — y saludaríamos a quien se fue, que es justo el bug que esto arregla.
_ACCIONES_DE_SILENCIO = (
    models.BOT_PENDING_ACTION_SEGUIMIENTO,
    models.BOT_PENDING_ACTION_ABANDONO,
)


def _cancelar_pendientes(db: Session, session: models.BotSession) -> int:
    """Da por cerradas las acciones de seguimiento/abandono de esta sesión.

    Se llama en cada turno: si la persona escribió, el silencio se rompió y el
    recordatorio que estaba agendado ya no tiene sentido. Sin esto se acumulan
    y la persona recibe dos o tres "¿te quedó alguna duda?" seguidos.
    """
    pendientes = (
        db.query(models.BotPendingAction)
        .filter(
            models.BotPendingAction.session_id == session.id,
            models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING,
            models.BotPendingAction.action_type.in_(_ACCIONES_DE_SILENCIO),
        )
        .all()
    )
    ahora = datetime.utcnow()
    for pa in pendientes:
        pa.status = models.BOT_PENDING_STATUS_DONE
        pa.processed_at = ahora
        pa.last_error = None
    if pendientes:
        db.commit()
    return len(pendientes)


def _programar(
    db: Session,
    session: models.BotSession,
    action_type: str,
    minutos: int,
    etapa: int = 0,
) -> models.BotPendingAction:
    """Agenda una acción de silencio, reemplazando la que hubiera.

    `etapa` es cuál de los recordatorios de `llm_engine.recordatorios_de` va a
    salir cuando venza. Viaja en la columna `payload` (que ya existía y estaba
    sin usar) y no en una columna nueva: es la única forma de encadenar tres
    reenganches sin migrar la tabla. Derivarla contando las acciones ya
    procesadas no sirve — `_cancelar_pendientes` marca `done` también las que
    cancela, así que un cliente que contesta y vuelve a callarse arrancaría en
    la etapa 2 y se saltaría el primer recordatorio.
    """
    _cancelar_pendientes(db, session)
    pa = models.BotPendingAction(
        session_id=session.id,
        scheduled_at=datetime.utcnow() + timedelta(minutes=max(1, minutos)),
        action_type=action_type,
        payload=json.dumps({"etapa": max(0, int(etapa))}),
        status=models.BOT_PENDING_STATUS_PENDING,
    )
    db.add(pa)
    db.commit()
    db.refresh(pa)
    return pa


def _etapa_de(pa: models.BotPendingAction) -> int:
    """Qué recordatorio toca. Cero ante cualquier duda: repetir el primero es
    molesto, saltarse al último es perder el reenganche entero."""
    try:
        return max(0, int((json.loads(pa.payload or "{}") or {}).get("etapa") or 0))
    except (ValueError, TypeError, AttributeError):
        return 0


def _cerrar_conversacion(db: Session, conversation: models.Conversation) -> None:
    """El bot **se despidió** (B1): la conversación se cierra y ya.

    Antes, cuando el bot se despedía, la conversación quedaba `open` para
    siempre: la del 20-ago-2026 sigue abierta en la bandeja aunque la clienta
    se despidió cuatro veces.

    Ojo con lo que esta función **no** hace, y a propósito: no etiqueta y no
    asigna asesor. Una despedida es un cierre limpio — el cliente ya recibió lo
    que pedía y nadie tiene que hacerle seguimiento. El abandono es lo
    contrario, y por eso vive aparte en `_marcar_abandonada`: si los dos
    caminos volvieran a compartir función, cada conversación bien cerrada
    caería en la bandeja de un asesor como si fuera un cliente perdido.
    """
    conversation.status = "closed"
    db.add(conversation)
    db.commit()


def _asesor_para_el_abandono(
    db: Session, conversation: models.Conversation
) -> Optional[str]:
    """A quién le toca el chat abandonado: el mismo turno que reparte el handoff.

    Se llama `resolver_asesor` **sin** `assignee` a propósito. Pasarle un
    `asesor_1` de respaldo sería repetir el bug de `606b169`: un handle
    explícito le gana al reparto por turnos y todos los chats terminan en la
    misma casilla, que además no es de nadie.

    Un team sin `asesores_rotacion` ni miembros `agent` no se queda sin
    destino: `crud.asesores_del_team` cae al `asesor_1` histórico, igual que
    hoy hace el handoff en ese mismo tenant. Devuelve None sólo si repartir
    falló de verdad; el caller decide qué hacer con eso.
    """
    try:
        team = db.query(models.Team).get(conversation.team_id)
        asesor = (crud.resolver_asesor(db, team) or "").strip()
    except Exception:  # pragma: no cover - defensivo
        logger.exception(
            "bot_runner: no se pudo repartir el abandono conv=%s", conversation.id
        )
        return None
    return asesor or None


def _describir_reenganches(etapas: list) -> str:
    """"a los 15 min, a las 5 h y a las 23 h" — para la nota que lee el asesor.

    Lo que necesita saber quien recibe el chat frío no es cuántos mensajes le
    salieron sino **hace cuánto** fue el último: si el bot le escribió por
    última vez hace 23 horas, la persona ya tuvo todo el día para contestar y
    no lo hizo, que es una conversación muy distinta a un silencio de media
    hora.
    """
    def _humano(minutos: int) -> str:
        if minutos < 60:
            return f"a los {minutos} min"
        horas = minutos / 60
        # Sin decimales cuando son horas exactas: "a las 5 h", no "a las 5.0 h".
        texto = f"{horas:.0f}" if abs(horas - round(horas)) < 0.05 else f"{horas:.1f}"
        return f"a las {texto} h"

    partes = [_humano(int(e["minutos"])) for e in etapas]
    if len(partes) == 1:
        return partes[0]
    return f"{', '.join(partes[:-1])} y {partes[-1]}"


def _marcar_abandonada(
    db: Session,
    conversation: models.Conversation,
    *,
    etiqueta: str,
    minutos: int,
    etapas: Optional[list] = None,
) -> Optional[str]:
    """La persona dejó de contestar: se etiqueta y pasa a manos de un humano.

    Pedido del CEO (Sprint 24): además de la etiqueta que ya ponía #377, la
    conversación se **asigna** al siguiente asesor del turno y queda `pending`,
    no `closed`. El motivo es práctico: cerrada no aparece como pendiente en la
    bandeja, y entonces asignarla no sirve de nada — el asesor nunca la ve.

    El orden importa: primero se resuelve el asesor y después se escribe todo
    junto. Si repartir fallara, la conversación igual queda etiquetada (que es
    el comportamiento ya desplegado de #377) en vez de perderse el rastro del
    abandono por culpa de la parte nueva.
    """
    asesor = _asesor_para_el_abandono(db, conversation)

    conversation.etiqueta = etiqueta
    if asesor:
        conversation.status = "pending"
        conversation.assigned_to = asesor
    else:
        # Sin nadie a quien entregársela, dejarla `pending` sería mentirle a la
        # bandeja: figuraría por atender y seguiría siendo del bot. Se cierra
        # etiquetada, como antes de este cambio.
        conversation.status = "closed"
    db.add(conversation)
    db.commit()

    if asesor:
        etapas = etapas or [{"minutos": minutos}]
        veces = (
            "una vez" if len(etapas) == 1 else f"{len(etapas)} veces"
        )
        _nota_de_handoff(
            db,
            conversation,
            {
                "motivo": (
                    f"la persona dejó de responder; el bot la reenganchó {veces} "
                    f"({_describir_reenganches(etapas)}) y esperó {minutos} "
                    "minutos más sin respuesta. No se le volverá a escribir "
                    "automáticamente"
                ),
            },
            # La etiqueta va en minúscula en la bandeja; como encabezado se ve
            # mejor con la inicial en mayúscula, sin tocar el resto (una
            # etiqueta futura podría traer siglas).
            titulo=f"🕒 *{etiqueta[:1].upper()}{etiqueta[1:]}*",
        )
    return asesor


def _reabrir_conversacion(db: Session, conversation: models.Conversation) -> None:
    """La persona volvió a escribir: la conversación vuelve a la bandeja y
    pierde la etiqueta de abandono, que ya no describe lo que está pasando.

    Excepción (Sprint 24): si el chat ya está en manos de una persona, aquí no
    se toca nada. Desde que el abandono asigna asesor, "volver a escribir"
    puede llegar a un chat que ya tiene dueño humano, y devolverlo a `open` con
    la etiqueta borrada le quitaría al asesor las dos señales con las que lo
    encuentra: el filtro de pendientes y la marca de por qué le llegó frío.

    Que el bot no se vuelva a meter no lo decide esta función, lo decide
    `bot_router.resolve_bot_for_incoming_message`, que corta en seco cuando
    `assigned_to != "bot"` (misma regla desde el handoff del Sprint 19). Con esa
    puerta cerrada, en el flujo real del webhook `run_turn` ni siquiera llega
    hasta acá; la guarda está igual porque el día que alguien llame a `run_turn`
    por otro camino, el costo de olvidarla es quitarle un cliente a un asesor.
    """
    if (conversation.assigned_to or "bot") != "bot":
        return

    cambio = False
    if conversation.status == "closed":
        conversation.status = "open"
        cambio = True
    if getattr(conversation, "etiqueta", None):
        conversation.etiqueta = None
        cambio = True
    if cambio:
        db.add(conversation)
        db.commit()


def _guardar_nombre(
    db: Session, conversation: models.Conversation, valor: str
) -> None:
    """Escribe el nombre en la ficha del contacto, **sólo si está vacío**.

    El nombre que venga del canal (el perfil de WhatsApp) manda sobre el que
    dedujo el modelo. Se vuelve a sanear aquí aunque el motor ya lo hizo: es un
    dato que sale de un LLM y termina a la vista del asesor en la bandeja.
    """
    nombre = llm_engine.nombre_saneado(valor)
    if not nombre:
        return

    if not (conversation.contact_name or "").strip():
        conversation.contact_name = nombre
        db.add(conversation)
        db.commit()
        # Sin el nombre en el log (regla #1): es un dato personal.
        logger.info("bot_runner: nombre de contacto registrado conv=%s", conversation.id)

    # Y en la agenda del team, junto al teléfono (pedido del CEO). Va aparte de
    # la ficha de la conversación a propósito: aunque el nombre de la burbuja ya
    # estuviera puesto, el contacto puede no existir todavía en Contactos.
    crud.registrar_contacto_desde_bot(
        db, conversation.team_id, conversation.contact_wa_id, nombre
    )


def _apuntar_en_el_historial(
    db: Session, session: models.BotSession, texto: str
) -> None:
    """Deja en el historial de la sesión lo que el bot mandó por su cuenta.

    Sin esto, el mensaje de seguimiento no existe para el modelo: si la persona
    contesta "sí, tengo una duda", el bot no sabe a qué le está contestando.
    """
    estado = _load_state(session) or {}
    historial = estado.get("history")
    if not isinstance(historial, list):
        historial = []
    historial.append({"role": "assistant", "content": texto})
    estado["history"] = historial[-llm_engine._MAX_HISTORY_MESSAGES:]
    session.state = json.dumps(estado)
    session.updated_at = datetime.utcnow()
    db.add(session)
    db.commit()


def run_turn(
    db: Session,
    *,
    bot: models.Bot,
    conversation: models.Conversation,
    session: Optional[models.BotSession],
    user_input: Optional[str],
    meta_account: Optional[models.MetaAccount],
) -> models.BotSession:
    """Ejecuta un turno del bot para la conversación dada.

    - Si `session` es None, crea una nueva (inicio del flujo).
    - Si hay `user_input`, se pasa al motor.
    - Por cada acción retornada:
        * `say` / `say_media` / `end` → se envían como mensaje a Meta.
        * `pause` → se programa como BotPendingAction y se corta el turno.
        * `ask` → no se envía nada extra; la acción anterior (say) ya fue enviada.
                  Lo realmente importante es que la sesión queda en status=waiting.

    Idempotencia: el caller debe haber deduplicado por meta_message_id.
    """
    # Sprint 19: cada bot declara su motor. 'llm' = conversacional (Bedrock);
    # 'flow' = pasos clásicos. Mismo contrato de actions/next_state/finished.
    is_llm = getattr(bot, "engine", "flow") == "llm"
    cfg = llm_engine.config_de(bot) if is_llm else {}
    seguimiento = llm_engine.seguimiento_de(cfg) if is_llm else None

    # #377: `bot_router` puede devolver una sesión ya cerrada para **retomarla**
    # (dentro de la ventana `retomar.horas`). Se revive conservando su `state`,
    # que es el historial: con el historial cargado el modelo ya no saluda de
    # cero ni vuelve a preguntar el nombre.
    retomada = session is not None and session.status in (
        models.BOT_SESSION_FINISHED,
        models.BOT_SESSION_CANCELLED,
    )
    cerrada_desde = session.updated_at if retomada else None
    if session is None:
        session = _create_session(db, bot, conversation.id)
    elif retomada:
        session.status = models.BOT_SESSION_RUNNING
        session.finished_at = None
        db.add(session)
        db.commit()

    if user_input:
        # La persona escribió: el chat vuelve a la bandeja y deja de estar
        # marcado como abandonado.
        _reabrir_conversacion(db, conversation)

    state = _load_state(session)
    if is_llm:
        result = llm_engine.advance(
            bot,
            state,
            user_input,
            runtime={
                "bot_id": getattr(bot, "id", None),
                "source": "whatsapp",
                "conversation_id": conversation.id,
                # Lo que hace que el nombre sobreviva a que se acabe la sesión.
                "contact_name": (conversation.contact_name or "").strip() or None,
                "retomada": retomada,
                "desde": llm_engine.hace_cuanto(cerrada_desde) if retomada else None,
            },
        )
        # #255: registrar la decisión del turno (camino, tools, latencia) en
        # bot_llm_decisions. Nunca rompe el turno (record_decision es defensivo).
        llm_engine.record_decision(
            db,
            bot,
            result.get("telemetry"),
            source="whatsapp",
            conversation_id=conversation.id,
            session_id=session.id,
        )
        # Sprint 21 #276: demos agendadas por WhatsApp → `demo_bookings`.
        llm_engine.record_booking(
            db, bot, result.get("telemetry"), source="whatsapp"
        )
    else:
        result = bot_engine.advance(bot, state, user_input)

    actions = result["actions"]
    next_state = result["next_state"]
    finished = bool(result["finished"])
    # Un bot LLM sin finalizar siempre espera el próximo mensaje del usuario.
    waiting = any(a.get("type") == "ask" for a in actions) or (is_llm and not finished)

    # Procesamos las acciones en orden. Si encontramos un `pause`, cortamos
    # el turno y programamos un delay; el resto queda para cuando vuelva.
    for i, action in enumerate(actions):
        atype = action.get("type")
        payload = action.get("payload") or {}

        if atype == "say":
            _send_text(db, conversation, bot, meta_account, payload.get("text", ""))
        elif atype == "say_media":
            _send_media(
                db,
                conversation,
                bot,
                meta_account,
                url=payload.get("url", ""),
                caption=payload.get("caption", ""),
                media_type=payload.get("media_type", "image"),
            )
        elif atype == "say_catalog":
            # Sprint 19 #264: catálogo de WhatsApp. Si hay Content Template
            # (twilio/catalog) y la cuenta es Twilio, va como mensaje nativo;
            # si no, fallback al texto que redactó la IA.
            content_sid = payload.get("content_sid") or ""
            cuerpo = payload.get("cuerpo", "")
            sent = False
            if (
                content_sid
                and meta_account is not None
                and crud.is_meta_account_usable(meta_account)
                and messaging.provider_of(meta_account) == "twilio"
            ):
                try:
                    meta_id, _ = messaging.send_template(
                        meta_account, conversation.contact_wa_id, content_sid
                    )
                    crud.add_message(
                        db, conversation, direction="outbound",
                        content=cuerpo or "[catálogo]", message_type="catalog",
                        meta_message_id=meta_id, sent_by_user_id=None,
                        status="sent",
                    )
                    sent = True
                except Exception:
                    logger.exception("bot_runner: envío de catálogo falló bot=%s", bot.id)
            if not sent:
                _send_text(db, conversation, bot, meta_account, cuerpo or "🛍️ Catálogo")
        elif atype == "perfil":
            # #377 (B2): el modelo registró el nombre de la persona.
            _guardar_nombre(db, conversation, payload.get("nombre", ""))
        elif atype == "ask":
            # El `ask` en sí no viaja al contacto: el prompt ya se envió como
            # `say` inmediatamente antes. Solo marca que el motor espera input.
            pass
        elif atype == "end":
            _send_text(db, conversation, bot, meta_account, payload.get("text", ""))
            # #377 (B1): el bot se despidió → la conversación se cierra. Detrás
            # del flag `seguimiento` porque el bot de mascotas y el
            # institucional también emiten `end` y su bandeja no funciona así.
            if seguimiento is not None:
                _cerrar_conversacion(db, conversation)
        elif atype == "handoff":
            # El bot entrega el chat a un humano: marcamos la conversación como
            # pendiente y la reasignamos del "bot" al asesor indicado. La UI de
            # mensajes mostrará el nuevo responsable.
            #
            # Si el paso no fija un asesor concreto, se reparte por turnos entre
            # los asesores del team (`teams.asesores_rotacion`): primero uno,
            # después el otro. Un `assignee` explícito en el paso manda sobre el
            # turno — sirve para rutas que deben caer siempre en la misma
            # persona (ej. un camino de reclamos). La única excepción es el
            # placeholder `asesor_N`, que en un team con asesores configurados
            # entra al turno igual: ver `crud.resolver_asesor`.
            team = db.query(models.Team).get(conversation.team_id)
            assignee = crud.resolver_asesor(db, team, payload.get("assignee"))
            conversation.status = "pending"
            conversation.assigned_to = assignee
            db.add(conversation)
            db.commit()
            _nota_de_handoff(db, conversation, payload)
            text = payload.get("text", "")
            if text and text.strip():
                _send_text(db, conversation, bot, meta_account, text)
        elif atype == "pause":
            seconds = int(payload.get("seconds") or 0)
            if seconds > 0:
                _schedule_delay(db, session, seconds)
                # Guardamos un estado "intermedio" para que el scheduler tick
                # retome desde el próximo step cuando venza.
                _persist_state(db, session, next_state, finished=False, waiting=False)
                return session
        else:
            logger.warning("bot_runner: acción desconocida %s", atype)

    _persist_state(db, session, next_state, finished, waiting)

    # #377 (B4): el silencio también es una respuesta. Si el turno deja la
    # sesión esperando, se agenda el reenganche; si el bot cerró, NO se agenda
    # nada — sería contradictorio con B1 y es justo lo que el CEO no quiere.
    if seguimiento is not None:
        _cancelar_pendientes(db, session)
        if not finished:
            _programar(
                db,
                session,
                models.BOT_PENDING_ACTION_SEGUIMIENTO,
                llm_engine.recordatorios_de(seguimiento)[0]["minutos"],
                etapa=0,
            )
    return session


#: Encabezado por defecto de la nota interna. El abandono manda el suyo.
_TITULO_NOTA = "📋 *Resumen del bot para el asesor*"


def _nota_de_handoff(
    db: Session,
    conversation: models.Conversation,
    payload: dict,
    *,
    titulo: str = _TITULO_NOTA,
) -> None:
    """Deja en el chat lo que el bot ya averiguó, para el asesor que lo recibe.

    Se guarda como `message_type='nota_interna'`: queda en la conversación y se
    ve en la bandeja, pero **no viaja al cliente** — a propósito no pasa por
    `_send_text`, que es el único camino hacia Meta/Twilio.

    Motivo (pedido del CEO, 19-ago-2026): antes el asesor heredaba el chat sin
    contexto y le volvía a preguntar el nombre y la fecha a alguien que ya los
    había dado dos veces. El `resumen` lo redacta el propio bot con lo que el
    cliente dijo.

    `titulo` existe para que el abandono (Sprint 24) reutilice esta nota sin
    encabezarla como un "resumen del bot": ahí no hubo pase, hubo silencio.
    """
    resumen = (payload.get("resumen") or "").strip()
    motivo = (payload.get("motivo") or "").strip()
    if not resumen and not motivo:
        return

    lineas = [titulo]
    nombre = (conversation.contact_name or "").strip()
    if nombre:
        lineas.append(f"Contacto: {nombre}")
    if resumen:
        lineas.append(resumen)
    if motivo:
        lineas.append(f"Motivo del pase: {motivo}")

    try:
        crud.add_message(
            db,
            conversation,
            direction="outbound",
            content="\n".join(lineas),
            message_type="nota_interna",
            status="sent",
            sent_by_user_id=None,
        )
    except Exception:
        # Una nota que falle no puede tumbar el handoff: el chat ya cambió de
        # dueño y eso es lo que no se puede perder.
        logger.exception(
            "bot_runner: no se pudo guardar la nota de handoff conv=%s",
            conversation.id,
        )


def _send_text(
    db: Session,
    conversation: models.Conversation,
    bot: models.Bot,
    account: Optional[models.MetaAccount],
    text: str,
) -> None:
    """Envía texto por Meta + persiste el mensaje saliente en la conversación."""
    if not text.strip():
        return

    if account is None or not crud.is_meta_account_usable(account):
        crud.add_message(
            db,
            conversation,
            direction="outbound",
            content=text,
            message_type="text",
            sent_by_user_id=None,
            status="failed",
            error_detail="MetaAccount no usable",
        )
        return

    try:
        # Sprint 18: envía por el proveedor de la cuenta (Meta o Twilio) vía el
        # puerto de mensajería. La firma (message_id, payload) es idéntica.
        meta_id, _ = messaging.send_text(
            account, conversation.contact_wa_id, text
        )
        crud.add_message(
            db,
            conversation,
            direction="outbound",
            content=text,
            message_type="text",
            meta_message_id=meta_id,
            sent_by_user_id=None,
            status="sent",
        )
    except Exception as exc:  # MetaWhatsAppError, CryptoError, red, etc.
        logger.exception("Error enviando mensaje del bot %s", bot.id)
        crud.add_message(
            db,
            conversation,
            direction="outbound",
            content=text,
            message_type="text",
            sent_by_user_id=None,
            status="failed",
            error_detail=str(exc)[:500],
        )


def _send_media(
    db: Session,
    conversation: models.Conversation,
    bot: models.Bot,
    account: Optional[models.MetaAccount],
    *,
    url: str,
    caption: str = "",
    media_type: str = "image",
) -> None:
    """Envía un archivo (imagen/video/documento) + persiste el mensaje saliente.

    Ambos proveedores envían por **link público**, así que no hay upload previo.
    Si el envío del archivo falla, hacemos *fallback a texto* con el caption y
    la URL: es preferible que el contacto reciba el enlace a que el turno del
    bot se quede mudo. El mensaje persistido guarda la URL en `content` para
    que quede trazable en el módulo de Mensajes.
    """
    url = (url or "").strip()
    if not url:
        # Sin URL no hay nada que enviar; si venía un caption, va como texto.
        if caption.strip():
            _send_text(db, conversation, bot, account, caption)
        return

    contenido = f"{caption}\n{url}".strip() if caption.strip() else url

    if account is None or not crud.is_meta_account_usable(account):
        crud.add_message(
            db, conversation, direction="outbound", content=contenido,
            message_type=media_type, sent_by_user_id=None, status="failed",
            error_detail="MetaAccount no usable",
        )
        return

    try:
        meta_id, _ = messaging.send_media(
            account,
            conversation.contact_wa_id,
            url,
            caption=caption or None,
            media_type=media_type,
        )
        crud.add_message(
            db, conversation, direction="outbound", content=contenido,
            message_type=media_type, meta_message_id=meta_id,
            sent_by_user_id=None, status="sent",
        )
    except Exception as exc:
        # No loggeamos el payload del proveedor completo (regla #6): sólo tipo y bot.
        logger.exception(
            "bot_runner: envío de media falló bot=%s tipo=%s", bot.id, media_type
        )
        crud.add_message(
            db, conversation, direction="outbound", content=contenido,
            message_type=media_type, sent_by_user_id=None, status="failed",
            error_detail=str(exc)[:500],
        )
        # Fallback: que al menos le llegue el enlace.
        _send_text(db, conversation, bot, account, contenido)


def process_pending_action(
    db: Session, pa: models.BotPendingAction
) -> None:
    """Procesa una BotPendingAction vencida: resume la sesión sin user_input.

    Marca la acción como done/failed según resultado.

    ⚠️ `seguimiento` y `abandono` (#377) **no pasan por `run_turn`**: para un bot
    LLM, `run_turn(user_input=None)` le manda `_FIRST_TURN_PROMPT` al modelo, que
    es literalmente "saluda al cliente". Mandarlas por ahí haría que el bot
    saludara a alguien que se fue — el bug que este sprint arregla. Se atienden
    antes, en `_procesar_silencio`.
    """
    pa.attempts += 1
    if (pa.action_type or models.BOT_PENDING_ACTION_RESUME) in _ACCIONES_DE_SILENCIO:
        _procesar_silencio(db, pa)
        return

    session = pa.session
    if session is None or session.status in (
        models.BOT_SESSION_FINISHED,
        models.BOT_SESSION_CANCELLED,
    ):
        pa.status = models.BOT_PENDING_STATUS_DONE
        pa.processed_at = datetime.utcnow()
        db.commit()
        return

    conversation = session.conversation
    bot = session.bot
    if conversation is None or bot is None:
        pa.status = models.BOT_PENDING_STATUS_FAILED
        pa.last_error = "session sin conversation/bot"
        pa.processed_at = datetime.utcnow()
        db.commit()
        return

    # Buscar la MetaAccount del team de la conversación.
    account = crud.get_meta_account_for_team(db, conversation.team_id)

    try:
        run_turn(
            db,
            bot=bot,
            conversation=conversation,
            session=session,
            user_input=None,
            meta_account=account,
        )
        pa.status = models.BOT_PENDING_STATUS_DONE
    except Exception as exc:  # pragma: no cover - defensivo
        logger.exception("process_pending_action falló")
        pa.status = models.BOT_PENDING_STATUS_FAILED
        pa.last_error = str(exc)[:500]
    pa.processed_at = datetime.utcnow()
    db.commit()


def _cerrar_accion(
    db: Session, pa: models.BotPendingAction, motivo: str
) -> None:
    """Da la acción por atendida sin hacer nada más. `motivo` va al log, nunca
    al cliente."""
    pa.status = models.BOT_PENDING_STATUS_DONE
    pa.processed_at = datetime.utcnow()
    db.commit()
    logger.info("bot_runner: acción %s sin efecto (%s)", pa.action_type, motivo)


def _procesar_silencio(db: Session, pa: models.BotPendingAction) -> None:
    """Atiende un `seguimiento` o un `abandono` vencido. NUNCA llama al modelo.

    - `seguimiento`: si la persona no volvió a escribir, se le manda el texto
      fijo de la etapa que toca y se agenda la siguiente; después del último
      recordatorio, el `abandono`.
    - `abandono`: si tampoco contestó a eso, la conversación se cierra y queda
      etiquetada. **No se le envía nada.**

    Cualquier señal de que la conversación siguió viva (mensaje entrante nuevo,
    sesión ya finalizada, chat en manos de un asesor) cancela la acción.
    """
    session = pa.session
    conversation = session.conversation if session is not None else None
    bot = session.bot if session is not None else None
    if session is None or conversation is None or bot is None:
        pa.status = models.BOT_PENDING_STATUS_FAILED
        pa.last_error = "session sin conversation/bot"
        pa.processed_at = datetime.utcnow()
        db.commit()
        return

    seguimiento = llm_engine.seguimiento_de(bot)
    if seguimiento is None:
        return _cerrar_accion(db, pa, "el bot ya no tiene política de seguimiento")
    if session.status in (models.BOT_SESSION_FINISHED, models.BOT_SESSION_CANCELLED):
        # El bot cerró después de programarlo: B1 manda sobre B4.
        return _cerrar_accion(db, pa, "la sesión ya está cerrada")
    if (conversation.assigned_to or "bot") != "bot":
        return _cerrar_accion(db, pa, "el chat lo tomó una persona")
    if crud.hay_entrante_despues(db, conversation.id, pa.created_at):
        return _cerrar_accion(db, pa, "la persona ya escribió")

    if pa.action_type == models.BOT_PENDING_ACTION_SEGUIMIENTO:
        # Cadena de reenganches (Sprint 27). Con un solo recordatorio
        # configurado esto se comporta igual que antes; con tres, cada uno
        # agenda el siguiente y sólo el último le abre paso al abandono.
        etapas = llm_engine.recordatorios_de(seguimiento)
        etapa = min(_etapa_de(pa), len(etapas) - 1)
        texto = etapas[etapa]["texto"]
        account = crud.get_meta_account_for_team(db, conversation.team_id)
        _send_text(db, conversation, bot, account, texto)
        _apuntar_en_el_historial(db, session, texto)

        siguiente = etapa + 1
        if siguiente < len(etapas):
            # Los minutos de cada etapa se cuentan desde que empezó el
            # silencio, así que lo que falta es la diferencia con la actual.
            _programar(
                db,
                session,
                models.BOT_PENDING_ACTION_SEGUIMIENTO,
                etapas[siguiente]["minutos"] - etapas[etapa]["minutos"],
                etapa=siguiente,
            )
        else:
            _programar(
                db,
                session,
                models.BOT_PENDING_ACTION_ABANDONO,
                llm_engine.minutos_de_seguimiento(seguimiento),
            )
        # `_programar` canceló las pendientes de la sesión, incluida ésta.
        pa.status = models.BOT_PENDING_STATUS_DONE
        pa.processed_at = datetime.utcnow()
        db.commit()
        logger.info(
            "bot_runner: seguimiento %s/%s enviado conv=%s bot=%s",
            etapa + 1, len(etapas), conversation.id, bot.id,
        )
        return

    # Abandono: se etiqueta y se le entrega a un asesor, en silencio. Al
    # contacto **no se le escribe nada** — la única huella nueva en el chat es
    # una nota interna, que no viaja a WhatsApp.
    asesor = _marcar_abandonada(
        db,
        conversation,
        etiqueta=llm_engine.etiqueta_de_abandono(seguimiento),
        minutos=llm_engine.minutos_de_seguimiento(seguimiento),
        etapas=llm_engine.recordatorios_de(seguimiento),
    )
    session.status = models.BOT_SESSION_FINISHED
    session.finished_at = datetime.utcnow()
    session.updated_at = datetime.utcnow()
    db.add(session)
    pa.status = models.BOT_PENDING_STATUS_DONE
    pa.processed_at = datetime.utcnow()
    db.commit()
    # Sin el nombre del asesor en el log (regla #1): basta saber si se repartió.
    logger.info(
        "bot_runner: conversación marcada como abandonada conv=%s bot=%s asignada=%s",
        conversation.id, bot.id, bool(asesor),
    )
