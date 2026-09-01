"""Una conversación abandonada no se archiva: le queda dueño (Sprint 24, F5).

Pedido del CEO: «a los 15 minutos de no hablar, marcar la conversación como
abandonada con una etiqueta y asignarla a un asesor». La etiqueta ya la ponía
#377; lo que faltaba —y es lo que se prueba acá— es que el chat caiga en manos
de una persona, repartido por el mismo turno rotativo del handoff, y que quede
`pending` en vez de `closed`: cerrada no figura como pendiente en la bandeja y
el asesor nunca la ve, con lo cual asignarla no serviría de nada.

Las dos cosas que este archivo cuida de verdad:

  1. **Que el abandono no se contagie a la despedida.** Cerrar por despedida
     (B1) y cerrar por abandono (B5) salían de la misma función. Si vuelven a
     juntarse, cada cliente que se despide bien termina en la bandeja de un
     asesor como si fuera un cliente perdido. `TestLaDespedidaSigueSiendoUnCierre`
     es esa alarma.
  2. **Que el reparto sea de verdad reparto.** Ya pasó una vez (`606b169`): el
     handle `asesor_1` le ganaba al round-robin y los seis chats de un día real
     cayeron todos en la misma casilla, que además no es de nadie.

Los teléfonos son sintéticos: este repositorio es público (regla #8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.data.bot_viajes import LLM_CONFIG
from app.services import bot_router, bot_runner, llm_engine

ETIQUETA = "conversación abandonada"
ASESORES = ["Camila", "Julián"]


# ---------------------------------------------------------------------------
# Andamiaje: base de verdad, modelo de mentira
# ---------------------------------------------------------------------------

def _texto(t: str) -> dict:
    return {"type": "text", "text": t}


def _tool(nombre: str, entrada: dict | None = None, ident: str = "tu_1") -> dict:
    return {"type": "tool_use", "id": ident, "name": nombre, "input": entrada or {}}


def _respuesta(*bloques, stop: str = "end_turn") -> dict:
    return {
        "content": list(bloques),
        "stop_reason": stop,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


class ModeloFalso:
    """Bedrock reemplazado por un guion fijo. Acá no importa qué redactó el
    modelo, sino en qué estado quedó la conversación."""

    def __init__(self) -> None:
        self.guion: list = []
        self.recibidos: list = []

    def __call__(self, model_id, system, messages, tools):
        self.recibidos.append({"system": system, "messages": [dict(m) for m in messages]})
        if not self.guion:
            return _respuesta(_texto("(el guion se quedó sin respuestas)"))
        return self.guion.pop(0)


@pytest.fixture
def modelo(monkeypatch) -> ModeloFalso:
    falso = ModeloFalso()
    monkeypatch.setattr(llm_engine, "_invoke_model", falso)
    return falso


@pytest.fixture
def db_session():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sesion = Sesion()
    yield sesion
    sesion.close()
    engine.dispose()


def _team_con_bot(db, *, correo: str, documento: str, asesores: list[str] | None):
    owner = crud.create_user(
        db,
        schemas.UserCreate(
            nombre="Agencia", correo=correo, tipo_documento="CC",
            documento=documento, password="Clave-De-Prueba-1",
        ),
    )
    team = models.Team(
        nombre="Arranquemos Pues",
        owner_user_id=owner.id,
        asesores_rotacion=list(asesores or []),
    )
    db.add(team)
    db.flush()
    bot = models.Bot(
        user_id=owner.id, team_id=team.id, name="Maria Camila",
        engine="llm", status="active", trigger_type=models.BOT_TRIGGER_DEFAULT,
        llm_config=json.dumps(LLM_CONFIG, ensure_ascii=False),
    )
    db.add(bot)
    db.commit()
    return team, bot


@pytest.fixture
def agencia(db_session):
    """El team de la agencia con sus asesores configurados, como en producción."""
    return _team_con_bot(
        db_session, correo="agencia_abandono@test.com",
        documento="ABND0001", asesores=ASESORES,
    )


@pytest.fixture
def agencia_sin_asesores(db_session):
    """El otro tenant: nunca dijo quién atiende. No puede reventar por eso."""
    return _team_con_bot(
        db_session, correo="tenant_sin_asesores@test.com",
        documento="ABND0002", asesores=None,
    )


#: Números sintéticos (regla #8). Los reales van enmascarados como 3XXXXXXXXX.
WA_ID = "573000000011"


def entra_mensaje(db, team, texto: str, wa_id: str = WA_ID):
    """Lo mismo que hace el webhook cuando llega un WhatsApp.

    Pasa por `bot_router` a propósito: parte de lo que se prueba acá es que,
    con la conversación ya en manos de un asesor, el router **no** devuelve bot.
    """
    conv = crud.get_or_create_conversation(db, team.id, wa_id, contact_name=None)
    crud.add_message(db, conv, direction="inbound", content=texto, status="received")
    bot, session = bot_router.resolve_bot_for_incoming_message(
        db, team=team, conversation_id=conv.id, message_text=texto,
    )
    if bot is not None:
        bot_runner.run_turn(
            db, bot=bot, conversation=conv, session=session,
            user_input=texto if session is not None else None,
            meta_account=None,
        )
    db.refresh(conv)
    return conv, bot


def salientes(db, conv) -> list:
    return (
        db.query(models.Message)
        .filter(
            models.Message.conversation_id == conv.id,
            models.Message.direction == "outbound",
        )
        .order_by(models.Message.id)
        .all()
    )


def enviados_al_cliente(db, conv) -> list:
    """Sólo lo que sale hacia WhatsApp. La nota interna no cuenta: se guarda en
    la conversación pero nunca pasa por Meta/Twilio."""
    return [m for m in salientes(db, conv) if m.message_type != "nota_interna"]


def notas(db, conv) -> list:
    return [m for m in salientes(db, conv) if m.message_type == "nota_interna"]


def pendientes(db, conv) -> list:
    return (
        db.query(models.BotPendingAction)
        .join(models.BotSession)
        .filter(
            models.BotSession.conversation_id == conv.id,
            models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING,
        )
        .all()
    )


def sesion_de(db, conv) -> models.BotSession:
    return (
        db.query(models.BotSession)
        .filter(models.BotSession.conversation_id == conv.id)
        .order_by(models.BotSession.id.desc())
        .first()
    )


def _vencer(db, pa: models.BotPendingAction) -> None:
    pa.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()


def hasta_el_abandono(db, conv):
    """Consume la cadena de recordatorios y devuelve el `abandono` ya vencido,
    listo para que el test lo procese como quiera (con o sin patch)."""
    for _ in range(10):
        pa = pendientes(db, conv)[0]
        _vencer(db, pa)
        if pa.action_type == models.BOT_PENDING_ACTION_ABANDONO:
            return pa
        bot_runner.process_pending_action(db, pa)
    raise AssertionError("la cadena de recordatorios nunca llegó al abandono")


def abandonar(db, team, modelo, wa_id: str = WA_ID):
    """El ciclo completo: saludo → silencio → recordatorio(s) → abandono.

    Los recordatorios se recorren en bucle en vez de contarlos: desde el
    Sprint 27 el bot de viajes manda tres (15 min, 5 h y 23 h) y este helper lo
    usan cuatro clases de tests que no tratan sobre *cuántos* son, sino sobre
    lo que pasa **después**. Con el bucle, cambiar la cadencia no los rompe.
    """
    modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
    conv, _ = entra_mensaje(db, team, "Hola", wa_id=wa_id)

    # Tope de seguridad: si la cadena no llegara nunca al abandono, es mejor
    # fallar acá que colgar la suite.
    for _ in range(10):
        pa = pendientes(db, conv)[0]
        _vencer(db, pa)
        bot_runner.process_pending_action(db, pa)
        if pa.action_type == models.BOT_PENDING_ACTION_ABANDONO:
            break
    else:  # pragma: no cover - defensivo
        raise AssertionError("la cadena de recordatorios nunca llegó al abandono")

    db.refresh(conv)
    return conv


def despedirse(db, team, modelo, wa_id: str = WA_ID):
    """El otro final: el bot cierra bien, con `finalizar_conversacion`."""
    modelo.guion = [
        _respuesta(_texto("¡Hola! ¿Con quién tengo el gusto?")),
        _respuesta(
            _texto("¡Que tengas un lindo día! 🌴✨"),
            _tool("finalizar_conversacion"),
            stop="tool_use",
        ),
    ]
    conv, _ = entra_mensaje(db, team, "Hola", wa_id=wa_id)
    conv, _ = entra_mensaje(db, team, "listo, muchas gracias, chao", wa_id=wa_id)
    return conv


# ---------------------------------------------------------------------------
# El abandono cae en un asesor
# ---------------------------------------------------------------------------

class TestElChatAbandonadoQuedaConDuenio:
    def test_etiquetada_pendiente_y_asignada_a_una_persona(
        self, db_session, agencia, modelo
    ):
        """Los tres campos del pedido, juntos. `closed` era justo lo que hacía
        inútil la asignación: el asesor no la ve en la bandeja."""
        team, _ = agencia
        conv = abandonar(db_session, team, modelo)

        assert conv.etiqueta == ETIQUETA
        assert conv.status == "pending"
        assert conv.assigned_to != "bot"
        assert conv.assigned_to in ASESORES

    def test_no_le_queda_el_handle_que_no_es_de_nadie(
        self, db_session, agencia, modelo
    ):
        """La regresión de `606b169`: `asesor_1` no es una persona."""
        team, _ = agencia
        conv = abandonar(db_session, team, modelo)
        assert conv.assigned_to != "asesor_1"

    def test_dos_abandonos_seguidos_caen_en_asesores_distintos(
        self, db_session, agencia, modelo
    ):
        """Si no rotara, todos los clientes fríos se le acumularían al mismo."""
        team, _ = agencia
        primera = abandonar(db_session, team, modelo, wa_id="573000000021")
        segunda = abandonar(db_session, team, modelo, wa_id="573000000022")

        assert primera.assigned_to != segunda.assigned_to
        assert {primera.assigned_to, segunda.assigned_to} == set(ASESORES)

    def test_la_sesion_del_bot_queda_cerrada_y_sin_pendientes(
        self, db_session, agencia, modelo
    ):
        """Asignarla a un humano no puede dejar al bot agendado por detrás."""
        team, _ = agencia
        conv = abandonar(db_session, team, modelo)

        assert sesion_de(db_session, conv).status == models.BOT_SESSION_FINISHED
        assert pendientes(db_session, conv) == []


# ---------------------------------------------------------------------------
# El abandono es silencioso, pero deja rastro para el asesor
# ---------------------------------------------------------------------------

class TestElAbandonoNoLeEscribeAlCliente:
    def test_al_contacto_no_le_llega_ni_un_mensaje(self, db_session, agencia, modelo):
        """Se fue: escribirle otra vez es la insistencia que #377 vino a quitar."""
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        abandono = hasta_el_abandono(db_session, conv)
        # Se cuenta DESPUÉS de los recordatorios: esos sí salen, y lo que este
        # test defiende es que el abandono en sí no agregue ni uno más.
        antes = len(enviados_al_cliente(db_session, conv))

        bot_runner.process_pending_action(db_session, abandono)

        assert len(enviados_al_cliente(db_session, conv)) == antes

    def test_nada_sale_por_whatsapp_en_el_abandono(self, db_session, agencia, modelo):
        """El cinturón por el otro lado: `_send_text` es el único camino hacia
        Meta/Twilio, y en este tramo no se toca."""
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        abandono = hasta_el_abandono(db_session, conv)
        with patch.object(bot_runner, "_send_text") as enviar:
            bot_runner.process_pending_action(db_session, abandono)
        enviar.assert_not_called()

    def test_queda_una_nota_interna_para_el_asesor(self, db_session, agencia, modelo):
        """El chat le llega frío: por lo menos que sepa por qué le llegó."""
        team, _ = agencia
        conv = abandonar(db_session, team, modelo)

        internas = notas(db_session, conv)
        assert len(internas) == 1
        nota = internas[0]
        assert nota.message_type == "nota_interna"
        # En minúsculas: el encabezado capitaliza la etiqueta para leerse mejor.
        assert ETIQUETA in nota.content.lower()
        assert "15" in nota.content, "no dice cuánto esperó el bot"

    def test_si_la_nota_falla_el_abandono_igual_queda_marcado(
        self, db_session, agencia, modelo
    ):
        """La nota es un extra; la etiqueta y el dueño no pueden perderse por
        ella. Por eso se escriben antes."""
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        abandono = hasta_el_abandono(db_session, conv)
        with patch.object(crud, "add_message", side_effect=RuntimeError("boom")):
            bot_runner.process_pending_action(db_session, abandono)
        db_session.refresh(conv)

        assert conv.etiqueta == ETIQUETA
        assert conv.status == "pending"
        assert conv.assigned_to in ASESORES


# ---------------------------------------------------------------------------
# La trampa: despedirse NO es abandonar
# ---------------------------------------------------------------------------

class TestLaDespedidaSigueSiendoUnCierre:
    """B1 (#377) intacta. Cerrar por despedida y cerrar por abandono compartían
    función; si vuelven a compartirla, toda conversación bien terminada aterriza
    en la bandeja de alguien y el reparto se llena de clientes que ya cerraron.
    """

    def test_cierra_sin_asesor_y_sin_etiqueta(self, db_session, agencia, modelo):
        team, _ = agencia
        conv = despedirse(db_session, team, modelo)

        assert conv.status == "closed"
        assert conv.assigned_to == "bot"
        assert conv.etiqueta is None

    def test_no_gasta_el_turno_del_reparto(self, db_session, agencia, modelo):
        """Si la despedida consumiera turno, el reparto se desalinearía sin que
        nadie recibiera nada."""
        team, _ = agencia
        despedirse(db_session, team, modelo)
        db_session.refresh(team)
        assert team.handoff_turno == 0

        # Y el primer abandono real sigue siendo el primero de la rueda.
        conv = abandonar(db_session, team, modelo, wa_id="573000000031")
        assert conv.assigned_to == ASESORES[0]

    def test_no_le_deja_notas_internas_a_nadie(self, db_session, agencia, modelo):
        team, _ = agencia
        conv = despedirse(db_session, team, modelo)
        assert notas(db_session, conv) == []


# ---------------------------------------------------------------------------
# El tenant que nunca configuró asesores
# ---------------------------------------------------------------------------

class TestUnTeamSinAsesoresNoRevienta:
    def test_el_abandono_se_procesa_igual(self, db_session, agencia_sin_asesores, modelo):
        """`crud.asesores_del_team` cae al `asesor_1` histórico cuando no hay ni
        rotación ni miembros `agent`: el mismo destino que ya usa el handoff en
        ese tenant. Lo que no puede pasar es que el abandono se caiga."""
        team, _ = agencia_sin_asesores
        conv = abandonar(db_session, team, modelo, wa_id="573000000041")

        assert conv.etiqueta == ETIQUETA
        assert conv.assigned_to != "bot"
        assert conv.status == "pending"

    def test_la_accion_queda_atendida(self, db_session, agencia_sin_asesores, modelo):
        """Si reventara, la acción quedaría `failed` y el scheduler la
        reintentaría cada minuto contra el mismo chat."""
        team, _ = agencia_sin_asesores
        conv = abandonar(db_session, team, modelo, wa_id="573000000042")

        procesadas = (
            db_session.query(models.BotPendingAction)
            .join(models.BotSession)
            .filter(models.BotSession.conversation_id == conv.id)
            .all()
        )
        assert procesadas, "no se agendó nada"
        assert all(
            pa.status == models.BOT_PENDING_STATUS_DONE for pa in procesadas
        ), [pa.last_error for pa in procesadas]

    def test_si_no_hay_a_quien_repartir_se_cierra_etiquetada(
        self, db_session, agencia_sin_asesores, modelo
    ):
        """El caso degenerado: repartir falla de verdad. Antes que dejarla
        `pending` a nombre del bot —que en la bandeja significa "alguien la está
        atendiendo" y sería mentira— se conserva el cierre etiquetado de #377."""
        team, _ = agencia_sin_asesores
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db_session, team, "Hola", wa_id="573000000043")
        abandono = hasta_el_abandono(db_session, conv)
        with patch.object(bot_runner, "_asesor_para_el_abandono", return_value=None):
            bot_runner.process_pending_action(db_session, abandono)
        db_session.refresh(conv)

        assert conv.etiqueta == ETIQUETA
        assert conv.status == "closed"
        assert conv.assigned_to == "bot"


# ---------------------------------------------------------------------------
# Y si la persona vuelve, el chat ya no es del bot
# ---------------------------------------------------------------------------

class TestCuandoLaPersonaVuelveAEscribir:
    """La decisión de este sprint: una vez que el chat tiene dueño humano, el
    bot no se lo quita. `bot_router.resolve_bot_for_incoming_message` ya corta
    cuando `assigned_to != "bot"` (desde el handoff del Sprint 19), así que la
    conversación abandonada y asignada queda para el asesor — con su etiqueta,
    que es lo que le explica por qué le llegó así.
    """

    def test_el_bot_no_vuelve_a_contestar(self, db_session, agencia, modelo):
        team, _ = agencia
        conv = abandonar(db_session, team, modelo)
        antes = len(enviados_al_cliente(db_session, conv))

        conv, bot = entra_mensaje(db_session, team, "hola, ¿me confirmas precios?")

        assert bot is None, "el bot le quitó el chat al asesor"
        assert len(enviados_al_cliente(db_session, conv)) == antes

    def test_el_asesor_conserva_el_chat_con_su_etiqueta(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        conv = abandonar(db_session, team, modelo)
        asesor = conv.assigned_to

        conv, _ = entra_mensaje(db_session, team, "hola, ¿me confirmas precios?")

        assert conv.assigned_to == asesor
        assert conv.status == "pending"
        assert conv.etiqueta == ETIQUETA

    def test_reabrir_no_le_quita_el_chat_a_una_persona(self, db_session, agencia):
        """La guarda, directo. En el flujo real ni se llega hasta acá porque el
        router corta antes; está por si alguien invoca `run_turn` por otro
        camino, donde el costo de olvidarlo es quitarle un cliente a un asesor.
        """
        team, _ = agencia
        conv = crud.get_or_create_conversation(
            db_session, team.id, "573000000051", contact_name=None
        )
        conv.status = "pending"
        conv.assigned_to = "Camila"
        conv.etiqueta = ETIQUETA
        db_session.commit()

        bot_runner._reabrir_conversacion(db_session, conv)

        assert conv.assigned_to == "Camila"
        assert conv.status == "pending"
        assert conv.etiqueta == ETIQUETA

    def test_pero_la_que_sigue_siendo_del_bot_si_se_reabre(self, db_session, agencia):
        """El camino de siempre no se toca: una conversación que el bot cerró al
        despedirse vuelve a la bandeja cuando la persona escribe."""
        team, _ = agencia
        conv = crud.get_or_create_conversation(
            db_session, team.id, "573000000052", contact_name=None
        )
        conv.status = "closed"
        conv.etiqueta = ETIQUETA
        db_session.commit()

        bot_runner._reabrir_conversacion(db_session, conv)

        assert conv.status == "open"
        assert conv.etiqueta is None
