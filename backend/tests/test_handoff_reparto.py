"""El chat que el bot entrega cae en un asesor con nombre, y va rotando.

Por qué existe este archivo. `test_rotacion_asesores.py` prueba
`crud.siguiente_asesor` aislado, y pasaba en verde mientras en producción los
chats seguían cayendo todos en `asesor_1`: la rotación estaba bien, pero nunca
se llamaba. El bot traía `assignee` fijo en su `llm_config` y un `assignee`
explícito **gana** sobre el reparto por turnos — para eso existe, para rutas que
deben caer siempre en la misma persona.

Así que acá se prueba la cadena completa (`bot_runner.run_turn` → acción
`handoff` → `conversation.assigned_to`) y, aparte, que la config que se despacha
del bot de viajes **no** traiga `assignee`. Ese es el campo que rompió esto una
vez y el que lo va a volver a romper.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.services import bot_runner

ASESORES = ["Camila", "Julián", "Alexandra"]


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
    """Un team con los tres asesores configurados y su bot LLM."""
    owner = crud.create_user(
        db_session,
        schemas.UserCreate(
            nombre="Agencia", correo="agencia_reparto@test.com",
            tipo_documento="CC", documento="REPARTO01", password="Clave-De-Prueba-1",
        ),
    )
    team = models.Team(
        nombre="Agencia de Viajes", owner_user_id=owner.id,
        asesores_rotacion=list(ASESORES),
    )
    db_session.add(team)
    db_session.flush()
    bot = models.Bot(user_id=owner.id, team_id=team.id, name="Bot Viajes", engine="llm")
    db_session.add(bot)
    db_session.commit()
    return team, bot


def _conversacion(db, team, wa_id: str):
    conv = crud.get_or_create_conversation(db, team.id, wa_id, contact_name=None)
    db.commit()
    return conv


def _correr_handoff(db, bot, conv, *, assignee=None):
    """Un turno cuya única acción es entregarle el chat a un humano.

    Se mockea el motor (no interesa qué dijo el modelo, sino a quién le queda el
    chat) y el envío por WhatsApp (no hay proveedor en un test).
    """
    # Las acciones viajan como {"type": ..., "payload": {...}}: el `assignee`
    # va DENTRO del payload, que es donde lo lee `bot_runner`.
    payload = {"text": "Te conecto con un asesor 💬"}
    if assignee is not None:
        payload["assignee"] = assignee
    resultado = {
        "actions": [{"type": "handoff", "payload": payload}],
        "next_state": None,
        "finished": False,
        "telemetry": None,
    }
    with patch.object(bot_runner.llm_engine, "advance", return_value=resultado), \
         patch.object(bot_runner.llm_engine, "record_decision"), \
         patch.object(bot_runner.llm_engine, "record_booking"), \
         patch.object(bot_runner, "_send_text"):
        bot_runner.run_turn(
            db, bot=bot, conversation=conv, session=None,
            user_input="quiero reservar", meta_account=None,
        )
    db.refresh(conv)
    return conv


class TestElChatCaeEnUnaPersonaConNombre:
    def test_ya_no_dice_asesor_1(self, db_session, agencia):
        """El síntoma que reportó el CEO: la bandeja mostraba `asesor_1`."""
        team, bot = agencia
        conv = _conversacion(db_session, team, "573001110001")
        _correr_handoff(db_session, bot, conv)
        assert conv.assigned_to != "asesor_1"
        assert conv.assigned_to in ASESORES

    def test_y_queda_pendiente_de_atender(self, db_session, agencia):
        team, bot = agencia
        conv = _conversacion(db_session, team, "573001110002")
        _correr_handoff(db_session, bot, conv)
        assert conv.status == "pending"

    def test_los_chats_se_reparten_entre_los_tres(self, db_session, agencia):
        """Cuatro chats seguidos: uno a cada quien y vuelve a empezar."""
        team, bot = agencia
        asignados = []
        for i in range(4):
            conv = _conversacion(db_session, team, f"57300222000{i}")
            _correr_handoff(db_session, bot, conv)
            asignados.append(conv.assigned_to)
        assert asignados == ["Camila", "Julián", "Alexandra", "Camila"]


class TestElAssigneeExplicitoSigueMandando:
    def test_una_ruta_puede_caer_siempre_en_la_misma_persona(self, db_session, agencia):
        """No es un bug, es la razón de ser del campo: sirve para un camino que
        deba ir siempre a la misma persona (ej. reclamos). Lo que estaba mal era
        tenerlo puesto en el bot entero."""
        team, bot = agencia
        conv = _conversacion(db_session, team, "573003330001")
        _correr_handoff(db_session, bot, conv, assignee="Alexandra")
        assert conv.assigned_to == "Alexandra"

    def test_y_no_gasta_el_turno_de_los_demas(self, db_session, agencia):
        team, bot = agencia
        conv = _conversacion(db_session, team, "573003330002")
        _correr_handoff(db_session, bot, conv, assignee="Alexandra")
        # El siguiente chat repartido sigue siendo el primero de la rueda.
        otra = _conversacion(db_session, team, "573003330003")
        _correr_handoff(db_session, bot, otra)
        assert otra.assigned_to == "Camila"


class TestElPlaceholderNoLeGanaAlTurno:
    """`asesor_1` no es una persona: es el handle que quedó del MVP.

    `bot_engine` lo mete por defecto cuando el paso no fija asesor, y los seeds
    viejos lo escriben tal cual. Antes eso le ganaba al reparto (un `assignee`
    explícito manda) y volvía a poner `asesor_1` en la bandeja. Si el team ya
    dijo quiénes atienden, el placeholder entra al turno como si no estuviera.
    """

    def test_un_assignee_asesor_1_entra_al_turno(self, db_session, agencia):
        team, bot = agencia
        conv = _conversacion(db_session, team, "573004440001")
        _correr_handoff(db_session, bot, conv, assignee="asesor_1")
        assert conv.assigned_to == "Camila"

    @pytest.mark.parametrize("handle", ["asesor_2", "ASESOR_1", "asesor-3", " asesor_1 "])
    def test_cualquier_variante_del_handle_tambien(self, db_session, agencia, handle):
        team, bot = agencia
        conv = _conversacion(db_session, team, "573004440002")
        _correr_handoff(db_session, bot, conv, assignee=handle)
        assert conv.assigned_to in ASESORES

    def test_un_team_sin_asesores_configurados_no_cambia(self, db_session):
        """El resto de tenants sigue igual: sin rotación, el placeholder es el
        único destino que hay y se respeta."""
        owner = crud.create_user(
            db_session,
            schemas.UserCreate(
                nombre="Otro", correo="otro_tenant@test.com",
                tipo_documento="CC", documento="OTRO0001", password="Clave-De-Prueba-1",
            ),
        )
        team = models.Team(nombre="Otro tenant", owner_user_id=owner.id)
        db_session.add(team)
        db_session.flush()
        bot = models.Bot(user_id=owner.id, team_id=team.id, name="Bot", engine="llm")
        db_session.add(bot)
        db_session.commit()

        conv = _conversacion(db_session, team, "573005550001")
        _correr_handoff(db_session, bot, conv, assignee="asesor_1")
        assert conv.assigned_to == "asesor_1"


class TestLaConfigQueSeDespacha:
    def test_el_bot_de_viajes_no_fija_assignee(self):
        """La regresión concreta: con `assignee` puesto, los 6 chats reales del
        19-ago-2026 cayeron todos en `asesor_1` y el reparto nunca corrió."""
        from app.data.bot_viajes import LLM_CONFIG

        assert "assignee" not in LLM_CONFIG
