"""El bot no vuelve a saludar desde cero, ni contesta cada "gracias" (#377).

Esto sale de un chat real del 20-ago-2026. Una señora preguntó por el plan, se
presentó, pidió los precios y dijo que lo consultaría con su esposo. El bot
cerró la conversación. Ella escribió "Ok listo mañana te hablo muchas gracias
por todo" y —como ya no había sesión activa— el bot arrancó una **sesión nueva
con el historial en blanco** y le soltó *"Hola, ¡Buen día! … ¿Con quién tengo
el gusto? 😊"*. Cuatro veces, en cuatro minutos. Ella cerró con: *"no que
pereza, por eso no me gusta agregar al guasap porque son muy intensos"*.

Se prueba la **cadena completa** (`bot_router` → `bot_runner` → `llm_engine`)
contra una base SQLite de verdad, con el modelo reemplazado por un guion fijo:
lo que aquí importa no es qué redactó Claude, sino qué quedó guardado, qué se
le envió a la persona y qué se agendó. Los guiones contra el modelo real viven
en `costo/test_guiones_continuidad.py`.

Los teléfonos son sintéticos y los nombres inventados: este repo es público
(regla #8), y el número del chat que originó todo esto va enmascarado como
`3XXXXXXXXX` en cualquier comentario.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.data.bot_viajes import LLM_CONFIG
from app.services import bot_router, bot_runner, llm_engine


# ---------------------------------------------------------------------------
# Andamiaje: una base de verdad y un modelo de mentira
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
    """Reemplaza a Bedrock con un guion fijo y guarda lo que se le pidió.

    `recibidos` es la parte interesante: guarda el `system` y los `messages` de
    cada llamada, que es como se comprueba que el historial llegó y que el
    prompt trae (o no) el bloque de continuidad.
    """

    def __init__(self) -> None:
        self.guion: list = []
        self.recibidos: list = []

    def __call__(self, model_id, system, messages, tools):
        self.recibidos.append({
            "system": system,
            "messages": [dict(m) for m in messages],
            "tools": [t["name"] for t in tools],
        })
        if not self.guion:
            # Nunca debería pasar: `advance` se traga las excepciones y responde
            # con el fail-safe, así que el test lo detecta por `agotado`.
            return _respuesta(_texto("(el guion se quedó sin respuestas)"))
        return self.guion.pop(0)

    @property
    def agotado(self) -> bool:
        return not self.guion

    def dijo(self, i: int = -1) -> str:
        return self.recibidos[i]["system"]

    def historial(self, i: int = -1) -> list:
        return self.recibidos[i]["messages"]


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


@pytest.fixture
def agencia(db_session):
    """El team de la agencia con su bot LLM, tal como se despacha a producción."""
    owner = crud.create_user(
        db_session,
        schemas.UserCreate(
            nombre="Agencia", correo="agencia_continuidad@test.com",
            tipo_documento="CC", documento="CONT0001", password="Clave-De-Prueba-1",
        ),
    )
    team = models.Team(nombre="Arranquemos Pues", owner_user_id=owner.id)
    db_session.add(team)
    db_session.flush()
    bot = models.Bot(
        user_id=owner.id, team_id=team.id, name="Maria Camila",
        engine="llm", status="active", trigger_type=models.BOT_TRIGGER_DEFAULT,
        llm_config=json.dumps(LLM_CONFIG, ensure_ascii=False),
    )
    db_session.add(bot)
    db_session.commit()
    return team, bot


#: Número sintético. El del chat real va enmascarado (`3XXXXXXXXX`) por la #8.
WA_ID = "573000000001"


def entra_mensaje(db, team, texto: str, wa_id: str = WA_ID):
    """Lo mismo que hace el webhook cuando llega un WhatsApp.

    Se replica aquí —y no se llama a `run_turn` a pelo— porque el bug vivía
    justo en la costura: `resolve_bot_for_incoming_message` devolvía `None` de
    sesión y el webhook, con `session is None`, mandaba `user_input=None`, que
    para un bot LLM significa "saluda". Un test que llame `run_turn` directo se
    salta exactamente el punto que se está arreglando.
    """
    conv = crud.get_or_create_conversation(db, team.id, wa_id, contact_name=None)
    crud.add_message(db, conv, direction="inbound", content=texto, status="received")
    bot, session = bot_router.resolve_bot_for_incoming_message(
        db, team=team, conversation_id=conv.id, message_text=texto,
    )
    if bot is None:
        return conv, None
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
    """Adelanta el reloj de una acción programada para poder procesarla ya."""
    pa.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()


# ---------------------------------------------------------------------------
# B1 — si la persona cierra, el bot no vuelve a escribir
# ---------------------------------------------------------------------------

class TestCuandoSeCierraElBotSeCalla:
    def test_despedirse_cierra_la_conversacion_en_la_bandeja(
        self, db_session, agencia, modelo
    ):
        """Antes la conversación quedaba `open` para siempre: la del chat real
        sigue abierta en la bandeja aunque la clienta se despidió cuatro veces."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Hola! Soy Maria Camila 😊 ¿Con quién tengo el gusto?")),
            _respuesta(
                _texto("¡Que tengas un lindo día! 🌴✨"),
                _tool("finalizar_conversacion"),
                stop="tool_use",
            ),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        conv, _ = entra_mensaje(db_session, team, "listo, muchas gracias, chao")

        assert conv.status == "closed"
        assert sesion_de(db_session, conv).status == models.BOT_SESSION_FINISHED

    def test_un_gracias_despues_del_cierre_no_genera_ni_un_mensaje(
        self, db_session, agencia, modelo
    ):
        """El corazón del bug. Sin esto, aquí salía el saludo de apertura."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Hola! ¿Con quién tengo el gusto?")),
            _respuesta(_texto("¡Hasta pronto! 🌴"), _tool("finalizar_conversacion"),
                       stop="tool_use"),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        entra_mensaje(db_session, team, "chao, gracias")
        antes = len(salientes(db_session, conv))

        conv, bot = entra_mensaje(db_session, team, "Gracias")

        assert bot is None, "se corrió el bot para contestar un 'gracias' de cierre"
        assert len(salientes(db_session, conv)) == antes, "le escribió igual"
        # Y no se gastó un turno de Bedrock en decidirlo.
        assert modelo.agotado

    @pytest.mark.parametrize("cortesia", [
        "Gracias", "gracias!", "Muchas gracias", "ok", "Ok listo",
        "Gracias lo mismo para ti", "muchas gracias por todo", "chao",
        "Igualmente", "👍", "🙏🙏", "listo, bueno", "ya me atendieron",
    ])
    def test_todas_estas_despedidas_se_dejan_pasar(self, cortesia):
        assert llm_engine.es_cortesia(cortesia), cortesia

    @pytest.mark.parametrize("pregunta", [
        "gracias, ¿y para octubre cuánto vale?",
        "ok pero cuánto vale el plan",
        "listo, mándame el tarifario",
        "no, quiero reservar",
        "¿tienen salidas entre semana?",
        "bueno y el hotel Bohíos cómo es",
        "",
    ])
    def test_pero_una_pregunta_nunca_es_cortesia(self, pregunta):
        assert not llm_engine.es_cortesia(pregunta), pregunta

    def test_con_la_conversacion_viva_un_gracias_si_se_contesta(
        self, db_session, agencia, modelo
    ):
        """El atajo es sólo para conversaciones cerradas. En mitad de una venta,
        "gracias" se responde como siempre."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Hola! ¿Con quién tengo el gusto?")),
            _respuesta(_texto("¡Con gusto! ¿Para qué mes lo piensas? 😊")),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        antes = len(salientes(db_session, conv))
        conv, bot = entra_mensaje(db_session, team, "Gracias")

        assert bot is not None
        assert len(salientes(db_session, conv)) > antes

    def test_no_responder_no_envia_absolutamente_nada(
        self, db_session, agencia, modelo
    ):
        """El modelo a veces llama la herramienta **y además** escribe un "¡con
        gusto! 🤗". Ese texto es justo el que no se quería mandar."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Hola! ¿Con quién tengo el gusto?")),
            _respuesta(
                _texto("¡Con gusto, que estés muy bien! 🤗"),
                _tool("no_responder"),
                stop="tool_use",
            ),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        antes = len(salientes(db_session, conv))

        conv, _ = entra_mensaje(db_session, team, "No gracias ya te dije que yo les escribo")

        assert len(salientes(db_session, conv)) == antes, "escribió pese a `no_responder`"
        assert conv.status == "closed"
        assert sesion_de(db_session, conv).status == models.BOT_SESSION_FINISHED

    def test_los_otros_bots_no_reciben_estas_herramientas(self):
        """`llm_engine` lo comparten el bot de mascotas y el institucional. Una
        herramienta global les cambiaría el comportamiento — ya pasó (1a7d385)."""
        con_flags = {t["name"] for t in llm_engine._tools_for(LLM_CONFIG)}
        assert {"no_responder", "registrar_nombre"} <= con_flags

        for otro in ({"context_key": "gloma"}, {"mascotas": {}},
                     {"context_key": "talulah"}):
            sin = {t["name"] for t in llm_engine._tools_for(otro)}
            assert "no_responder" not in sin
            assert "registrar_nombre" not in sin


# ---------------------------------------------------------------------------
# B2 — el nombre se registra una vez y no se vuelve a preguntar
# ---------------------------------------------------------------------------

class TestElNombreSeGuardaUnaSolaVez:
    def test_registrar_nombre_lo_escribe_en_la_ficha(self, db_session, agencia, modelo):
        """En el chat que originó esto la persona se presentó por su nombre y
        `contact_name` quedó vacío igual: el nombre sólo vivía en el historial
        de la sesión, que después se borró."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Hola! ¿Con quién tengo el gusto?")),
            _respuesta(
                _texto("¡Un gusto, Marcela! 🌴 ¿Para qué mes lo piensas?"),
                _tool("registrar_nombre", {"nombre": "Marcela"}),
                stop="tool_use",
            ),
            _respuesta(_texto("¡Perfecto! Déjame consultarte los precios 😊")),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        conv, _ = entra_mensaje(db_session, team, "Marcela")

        assert conv.contact_name == "Marcela"

    def test_el_nombre_del_canal_manda_sobre_el_del_modelo(
        self, db_session, agencia, modelo
    ):
        """Si WhatsApp ya trajo el nombre del perfil, ese es el bueno."""
        team, _ = agencia
        conv = crud.get_or_create_conversation(
            db_session, team.id, WA_ID, contact_name="Marcela Ríos"
        )
        modelo.guion = [
            _respuesta(_texto("Hola"), _tool("registrar_nombre", {"nombre": "Mar"}),
                       stop="tool_use"),
            _respuesta(_texto("¡Listo!")),
        ]
        entra_mensaje(db_session, team, "hola, soy Mar")
        db_session.refresh(conv)
        assert conv.contact_name == "Marcela Ríos"

    @pytest.mark.parametrize("basura", [
        "", "   ", "573000000002", "Marcela 3000000003", "x", None,
        "correo@ejemplo.com",
    ])
    def test_un_telefono_o_un_correo_no_son_un_nombre(self, basura):
        """La bandeja acabaría mostrando un número como si fuera la persona."""
        assert llm_engine.nombre_saneado(basura) == ""

    def test_se_recorta_y_se_deja_en_una_linea(self):
        assert llm_engine.nombre_saneado("  Ana\nMaría  ") == "Ana María"
        assert len(llm_engine.nombre_saneado("Ana " * 40)) <= 60

    def test_el_prompt_le_dice_el_nombre_y_que_no_lo_pregunte(self, agencia, db_session):
        _, bot = agencia
        cfg = {**llm_engine.config_de(bot), "_runtime": {"contact_name": "Marcela"}}
        system = llm_engine._system_prompt(bot, cfg)
        assert "Marcela" in system
        assert "NO le preguntes cómo se llama" in system

    def test_y_sin_nombre_le_recuerda_que_lo_registre(self, agencia):
        _, bot = agencia
        cfg = {**llm_engine.config_de(bot), "_runtime": {"contact_name": None}}
        system = llm_engine._system_prompt(bot, cfg)
        assert "registrar_nombre" in system

    def test_el_nombre_llega_al_modelo_en_el_turno(self, db_session, agencia, modelo):
        """El eslabón que faltaba: `run_turn` llamaba a `advance` **sin
        `runtime`**, así que el motor nunca se enteraba de `contact_name`."""
        team, _ = agencia
        crud.get_or_create_conversation(
            db_session, team.id, WA_ID, contact_name="Marcela"
        )
        modelo.guion = [_respuesta(_texto("¡Hola Marcela! 🌴"))]
        entra_mensaje(db_session, team, "hola")
        assert "Marcela" in modelo.dijo()

    def test_el_nombre_sobrevive_a_que_se_acabe_la_sesion(
        self, db_session, agencia, modelo
    ):
        """Pasada la ventana de `retomar` sí se arranca de cero — pero el nombre
        sigue en la ficha, así que tampoco ahí lo repregunta."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("Hola"), _tool("registrar_nombre", {"nombre": "Marcela"}),
                       stop="tool_use"),
            _respuesta(_texto("¡Un gusto, Marcela!")),
            _respuesta(_texto("¡Hasta pronto!"), _tool("finalizar_conversacion"),
                       stop="tool_use"),
            _respuesta(_texto("¡Hola de nuevo, Marcela!")),
        ]
        conv, _ = entra_mensaje(db_session, team, "hola, soy Marcela")
        entra_mensaje(db_session, team, "chao")

        # Tres días después: fuera de la ventana de 24 h.
        sesion = sesion_de(db_session, conv)
        sesion.updated_at = datetime.utcnow() - timedelta(days=3)
        db_session.commit()

        entra_mensaje(db_session, team, "hola, ¿todavía hay cupo para diciembre?")
        assert "Marcela" in modelo.dijo()
        assert "NO le preguntes cómo se llama" in modelo.dijo()


# ---------------------------------------------------------------------------
# B3 — no arrancar de cero: retomar donde quedó
# ---------------------------------------------------------------------------

class TestRetomarDondeQuedaron:
    def _cerrar_una_conversacion(self, db, team, modelo):
        modelo.guion = [
            _respuesta(_texto("¡Hola! ¿Con quién tengo el gusto?")),
            _respuesta(_texto("En septiembre tenemos varias salidas 🌴")),
            _respuesta(_texto("¡Que tengas un lindo día!"),
                       _tool("finalizar_conversacion"), stop="tool_use"),
        ]
        conv, _ = entra_mensaje(db, team, "Hola")
        entra_mensaje(db, team, "para septiembre")
        conv, _ = entra_mensaje(db, team, "chao")
        return conv

    def test_se_reusa_la_sesion_con_su_historial(self, db_session, agencia, modelo):
        """Lo que evita las cuatro repeticiones: con el historial cargado, el
        modelo ya no tiene por qué presentarse."""
        team, _ = agencia
        conv = self._cerrar_una_conversacion(db_session, team, modelo)
        sesion_vieja = sesion_de(db_session, conv)

        modelo.guion = [_respuesta(_texto("¡Claro! Te confirmo 🌴"))]
        conv, _ = entra_mensaje(db_session, team, "¿el cupo del 18 de septiembre sigue?")

        assert sesion_de(db_session, conv).id == sesion_vieja.id, "arrancó sesión nueva"
        contenidos = " ".join(str(m["content"]) for m in modelo.historial())
        assert "septiembre" in contenidos, "el historial no llegó al modelo"
        assert "¿Con quién tengo el gusto?" in contenidos

    def test_el_prompt_le_pide_que_no_salude_de_nuevo(self, db_session, agencia, modelo):
        team, _ = agencia
        self._cerrar_una_conversacion(db_session, team, modelo)
        modelo.guion = [_respuesta(_texto("¡Claro!"))]
        entra_mensaje(db_session, team, "¿y para diciembre?")

        system = modelo.dijo()
        assert "ya se había cerrado" in system
        assert "No la saludes como si fuera la primera vez" in system

    def test_la_conversacion_vuelve_a_la_bandeja(self, db_session, agencia, modelo):
        team, _ = agencia
        conv = self._cerrar_una_conversacion(db_session, team, modelo)
        assert conv.status == "closed"

        modelo.guion = [_respuesta(_texto("¡Claro!"))]
        conv, _ = entra_mensaje(db_session, team, "¿y para diciembre?")
        assert conv.status == "open"

    def test_pasada_la_ventana_si_arranca_una_sesion_nueva(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        conv = self._cerrar_una_conversacion(db_session, team, modelo)
        vieja = sesion_de(db_session, conv)
        vieja.updated_at = datetime.utcnow() - timedelta(hours=48)
        db_session.commit()

        modelo.guion = [_respuesta(_texto("¡Hola de nuevo!"))]
        conv, _ = entra_mensaje(db_session, team, "hola, ¿me recuerdas los precios?")
        assert sesion_de(db_session, conv).id != vieja.id

    def test_si_ya_lo_tomo_una_persona_el_bot_no_vuelve(
        self, db_session, agencia, modelo
    ):
        """La regla de siempre sigue mandando: con el chat en manos de un
        asesor, el bot no interviene ni para retomar."""
        team, _ = agencia
        conv = self._cerrar_una_conversacion(db_session, team, modelo)
        conv.assigned_to = "Camila"
        db_session.commit()

        conv, bot = entra_mensaje(db_session, team, "¿me confirmas el cupo?")
        assert bot is None

    def test_los_otros_bots_siguen_borrando_el_estado_al_cerrar(self):
        """Sin el flag `retomar`, cerrar sigue dejando `next_state=None`."""
        class BotSinFlags:
            id = 99
            engine = "llm"
            llm_config = json.dumps({"context_key": "gloma"})

        import unittest.mock as mock

        with mock.patch.object(
            llm_engine, "_invoke_model",
            return_value=_respuesta(_texto("chao"), _tool("finalizar_conversacion"),
                                    stop="tool_use"),
        ):
            salida = llm_engine.advance(BotSinFlags(), {"history": []}, "chao")
        assert salida["finished"]
        assert salida["next_state"] is None


# ---------------------------------------------------------------------------
# B4 — seguimiento a los 15 minutos de silencio
# ---------------------------------------------------------------------------

class TestSeguimientoALos15Minutos:
    def test_se_agenda_cuando_el_turno_queda_esperando(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas? 😊"))]
        conv, _ = entra_mensaje(db_session, team, "Hola, quiero info")

        pend = pendientes(db_session, conv)
        assert len(pend) == 1
        assert pend[0].action_type == models.BOT_PENDING_ACTION_SEGUIMIENTO
        minutos = (pend[0].scheduled_at - datetime.utcnow()).total_seconds() / 60
        assert 13 <= minutos <= 16, minutos

    def test_si_el_bot_cerro_no_se_agenda_nada(self, db_session, agencia, modelo):
        """B1 manda sobre B4: sería contradictorio despedirse y volver a los 15
        minutos con un '¿te quedó alguna duda?'."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("Hola")),
            _respuesta(_texto("¡Hasta pronto!"), _tool("finalizar_conversacion"),
                       stop="tool_use"),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        conv, _ = entra_mensaje(db_session, team, "chao")
        assert pendientes(db_session, conv) == []

    def test_cada_mensaje_reemplaza_el_anterior_no_se_acumulan(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("Hola")) for _ in range(3)]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        entra_mensaje(db_session, team, "¿y el hotel?")
        conv, _ = entra_mensaje(db_session, team, "¿y los tours?")
        assert len(pendientes(db_session, conv)) == 1

    def test_al_vencer_manda_el_texto_y_agenda_el_abandono(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        pa = pendientes(db_session, conv)[0]
        _vencer(db_session, pa)

        bot_runner.process_pending_action(db_session, pa)

        ultimo = salientes(db_session, conv)[-1]
        assert "otra pregunta" in ultimo.content
        assert pa.status == models.BOT_PENDING_STATUS_DONE
        siguiente = pendientes(db_session, conv)
        assert len(siguiente) == 1
        assert siguiente[0].action_type == models.BOT_PENDING_ACTION_ABANDONO

    def test_si_contesta_el_recordatorio_y_se_vuelve_a_ir_se_le_recuerda_otra_vez(
        self, db_session, agencia, modelo
    ):
        """Decisión del CEO (21-ago-2026): el recordatorio **no** es uno por
        persona, es uno por silencio.

        Quien contesta reabrió la conversación, y si después se vuelve a quedar
        callado ese silencio nuevo merece su propio reenganche. Lo que nunca
        puede pasar es que se acumulen dos sin que haya contestado en medio —
        eso lo cuida `test_cada_mensaje_reemplaza_el_anterior_no_se_acumulan`.
        """
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¿Para qué mes lo piensas?")),
            _respuesta(_texto("¡Claro! En septiembre hay salidas todos los viernes.")),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola")

        # Primer silencio → primer recordatorio.
        primero = pendientes(db_session, conv)[0]
        _vencer(db_session, primero)
        bot_runner.process_pending_action(db_session, primero)
        assert "otra pregunta" in salientes(db_session, conv)[-1].content
        # Detrás quedó agendado el abandono.
        assert (
            pendientes(db_session, conv)[0].action_type
            == models.BOT_PENDING_ACTION_ABANDONO
        )

        # Contesta: el abandono se cae y vuelve a quedar agendado un seguimiento.
        conv, _ = entra_mensaje(db_session, team, "sí, ¿qué tal septiembre?")
        pend = pendientes(db_session, conv)
        assert len(pend) == 1, "no se puede acumular más de una acción viva"
        assert pend[0].action_type == models.BOT_PENDING_ACTION_SEGUIMIENTO
        assert conv.etiqueta is None, "contestó: no está abandonada"

        # Segundo silencio → segundo recordatorio. Este es el punto del test.
        segundo = pend[0]
        _vencer(db_session, segundo)
        bot_runner.process_pending_action(db_session, segundo)

        recordatorios = [
            m for m in salientes(db_session, conv) if "otra pregunta" in m.content
        ]
        assert len(recordatorios) == 2, "el segundo silencio también se reengancha"

    def test_pero_sin_contestar_no_se_le_insiste_una_segunda_vez(
        self, db_session, agencia, modelo
    ):
        """El otro lado de la misma moneda: si no contestó, lo que sigue es la
        etiqueta y el silencio, nunca un segundo '¿te quedó alguna duda?'."""
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")

        pa = pendientes(db_session, conv)[0]
        _vencer(db_session, pa)
        bot_runner.process_pending_action(db_session, pa)
        antes = len(salientes(db_session, conv))

        abandono = pendientes(db_session, conv)[0]
        _vencer(db_session, abandono)
        bot_runner.process_pending_action(db_session, abandono)

        assert len(salientes(db_session, conv)) == antes, "le volvió a escribir"
        db_session.refresh(conv)
        assert conv.etiqueta == "conversación abandonada"

    def test_el_seguimiento_no_llama_al_modelo(self, db_session, agencia, modelo):
        """La trampa del sprint. `process_pending_action` llamaba
        `run_turn(user_input=None)`, y para un bot LLM eso es
        `_FIRST_TURN_PROMPT`: **un saludo**. Habríamos saludado a quien se fue.
        """
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        pa = pendientes(db_session, conv)[0]
        _vencer(db_session, pa)
        llamadas_antes = len(modelo.recibidos)

        bot_runner.process_pending_action(db_session, pa)

        assert len(modelo.recibidos) == llamadas_antes, "gastó un turno de Bedrock"
        texto = " ".join(m.content for m in salientes(db_session, conv))
        assert "¿Con quién tengo el gusto?" not in texto, "saludó a quien se fue"

    def test_si_la_persona_ya_escribio_no_se_le_manda_nada(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes?")), _respuesta(_texto("¡Listo!"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        pa = pendientes(db_session, conv)[0]
        # Contesta antes de que venza: el nuevo turno cancela el agendado, así
        # que se procesa a la fuerza para probar también el segundo cinturón.
        entra_mensaje(db_session, team, "para septiembre")
        antes = len(salientes(db_session, conv))
        pa.status = models.BOT_PENDING_STATUS_PENDING
        db_session.commit()
        _vencer(db_session, pa)

        bot_runner.process_pending_action(db_session, pa)

        assert len(salientes(db_session, conv)) == antes
        assert pa.status == models.BOT_PENDING_STATUS_DONE

    def test_el_recordatorio_queda_en_el_historial(self, db_session, agencia, modelo):
        """Si contesta "sí, tengo una duda", el bot tiene que saber a qué le
        está contestando."""
        team, _ = agencia
        modelo.guion = [_respuesta(_texto("¿Para qué mes?")), _respuesta(_texto("¡Claro!"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        pa = pendientes(db_session, conv)[0]
        _vencer(db_session, pa)
        bot_runner.process_pending_action(db_session, pa)

        entra_mensaje(db_session, team, "sí, una duda")
        contenidos = " ".join(str(m["content"]) for m in modelo.historial())
        assert "otra pregunta" in contenidos

    def test_los_otros_bots_no_agendan_seguimientos(self, db_session, agencia, modelo):
        """El bot institucional y el de mascotas no tienen esta política."""
        team, bot = agencia
        bot.llm_config = json.dumps({"context_key": "gloma"})
        db_session.commit()
        modelo.guion = [_respuesta(_texto("Hola"))]
        conv, _ = entra_mensaje(db_session, team, "Hola")
        assert pendientes(db_session, conv) == []


# ---------------------------------------------------------------------------
# B5 — etiqueta "conversación abandonada"
# ---------------------------------------------------------------------------

class TestConversacionAbandonada:
    def _hasta_el_abandono(self, db, team, modelo):
        modelo.guion = [_respuesta(_texto("¿Para qué mes lo piensas?"))]
        conv, _ = entra_mensaje(db, team, "Hola")
        seguimiento = pendientes(db, conv)[0]
        _vencer(db, seguimiento)
        bot_runner.process_pending_action(db, seguimiento)
        abandono = pendientes(db, conv)[0]
        _vencer(db, abandono)
        return conv, abandono

    def test_etiqueta_cierra_y_no_le_escribe_nada(self, db_session, agencia, modelo):
        team, _ = agencia
        conv, abandono = self._hasta_el_abandono(db_session, team, modelo)
        antes = len(salientes(db_session, conv))

        bot_runner.process_pending_action(db_session, abandono)
        db_session.refresh(conv)

        assert conv.etiqueta == "conversación abandonada"
        assert conv.status == "closed"
        assert sesion_de(db_session, conv).status == models.BOT_SESSION_FINISHED
        assert len(salientes(db_session, conv)) == antes, "le escribió al despedirse"
        assert pendientes(db_session, conv) == []

    def test_si_contesto_al_recordatorio_no_se_etiqueta(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        conv, abandono = self._hasta_el_abandono(db_session, team, modelo)
        modelo.guion = [_respuesta(_texto("¡Claro que sí! 🌴"))]
        entra_mensaje(db_session, team, "sí, ¿para diciembre cuánto vale?")
        abandono.status = models.BOT_PENDING_STATUS_PENDING
        db_session.commit()
        _vencer(db_session, abandono)

        bot_runner.process_pending_action(db_session, abandono)
        db_session.refresh(conv)

        assert conv.etiqueta is None
        assert conv.status == "open"

    def test_si_vuelve_a_escribir_la_etiqueta_se_cae(self, db_session, agencia, modelo):
        """La etiqueta describe lo que está pasando ahora, no lo que pasó."""
        team, _ = agencia
        conv, abandono = self._hasta_el_abandono(db_session, team, modelo)
        bot_runner.process_pending_action(db_session, abandono)
        db_session.refresh(conv)
        assert conv.etiqueta == "conversación abandonada"

        modelo.guion = [_respuesta(_texto("¡Claro! 🌴"))]
        conv, _ = entra_mensaje(db_session, team, "hola, ¿me confirmas los precios?")
        assert conv.etiqueta is None
        assert conv.status == "open"


# ---------------------------------------------------------------------------
# Lo que no se puede romper de camino
# ---------------------------------------------------------------------------

class TestLosGuardarrailesDeSiempre:
    def test_el_bot_de_mascotas_sigue_sin_poder_inventar_telefonos(self):
        """`_viola_contacto` es el guardarraíl que impide mandar a una familia a
        marcar el número de un desconocido. Nada de este sprint lo toca."""
        cfg = {"mascotas": {}}
        assert llm_engine._viola_contacto(
            cfg, ["llama al 3001234567 que allá la tienen"], [], []
        )
        # Y el que sí salió de la herramienta pasa.
        assert not llm_engine._viola_contacto(
            cfg,
            ["llama al 3001234567 que allá la tienen"],
            [{"tool": "entregar_contacto", "resultado": "tel 3001234567"}],
            [],
        )

    def test_la_config_que_se_despacha_trae_los_tres_flags(self):
        assert LLM_CONFIG["recordar_nombre"] is True
        assert LLM_CONFIG["seguimiento"]["minutos"] == 15
        assert LLM_CONFIG["seguimiento"]["etiqueta_abandono"] == "conversación abandonada"
        assert LLM_CONFIG["retomar"]["horas"] == 24
        # La regresión que ya costó una vez (ver test_handoff_reparto.py).
        assert "assignee" not in LLM_CONFIG

    def test_el_texto_del_seguimiento_no_promete_nada(self):
        texto = llm_engine.texto_de_seguimiento(LLM_CONFIG["seguimiento"])
        assert "$" not in texto
        assert "cuando quieras" in texto.lower()
