"""El chat que recibe el asesor llega con contexto, no en blanco.

Pedido del CEO (19-ago-2026): "que llegue al asesor con más o menos la fecha
que ya se tiene y el nombre". Antes el asesor heredaba la conversación sin nada
y le volvía a preguntar el nombre y la fecha a alguien que ya los había dado.

Lo que se fija aquí:
  - el motor propaga el `resumen` que redacta el bot hasta el `bot_runner`;
  - el runner lo deja como `nota_interna` en la conversación;
  - esa nota **no se le envía al cliente** (no pasa por Meta/Twilio);
  - sin `assignee` en la config, el chat entra al reparto por turnos.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.services import bot_runner, llm_engine


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
def conversacion(db_session):
    owner = crud.create_user(
        db_session,
        schemas.UserCreate(
            nombre="Arranquemos Pues", correo="ap_owner@test.com",
            tipo_documento="CC", documento="APH001",
            password="Clave-De-Prueba-1",
        ),
    )
    team = crud.create_team(db_session, "Arranquemos Pues", owner)
    team.asesores_rotacion = ["Camila", "Julián", "Alexandra"]
    db_session.add(team)
    db_session.commit()
    conv = crud.get_or_create_conversation(
        db_session, team.id, "573001112233", contact_name="Andrés Ruiz"
    )
    return conv


class TestElMotorPropagaElResumen:
    def test_el_resumen_viaja_en_la_accion_de_handoff(self, bot):
        actions = []
        llm_engine._run_tool(
            "escalar_a_asesor",
            {
                "motivo": "envió datos de reserva",
                "resumen": "Andrés Ruiz, 2 personas, 18 al 21 de septiembre, "
                           "hotel Amor de Dios",
            },
            bot.cfg, actions, [], [], [],
        )
        payload = actions[-1]["payload"]
        assert payload["resumen"].startswith("Andrés Ruiz, 2 personas")
        assert payload["motivo"] == "envió datos de reserva"

    def test_sin_assignee_el_chat_entra_al_reparto_por_turnos(self, bot):
        """Un `assignee` no vacío aquí anularía el round-robin del team."""
        actions = []
        llm_engine._run_tool(
            "escalar_a_asesor", {"motivo": "pidió humano"},
            bot.cfg, actions, [], [], [],
        )
        assert actions[-1]["payload"]["assignee"] == ""

    def test_el_resumen_se_recorta_y_no_revienta_la_nota(self, bot):
        actions = []
        llm_engine._run_tool(
            "escalar_a_asesor",
            {"motivo": "x", "resumen": "a" * 900},
            bot.cfg, actions, [], [], [],
        )
        assert len(actions[-1]["payload"]["resumen"]) == 500


class TestElPromptDiceQueDiaEsHoy:
    """Hallazgo 1, el caro: sin la fecha en el prompt el modelo adivinaba el año
    (escribía 2025) y le decía a un cliente que el 18 de diciembre «ya pasó»."""

    def test_el_system_trae_la_fecha_de_colombia(self, bot):
        from datetime import datetime

        from app.services import tarifario

        system = llm_engine._system_prompt(bot, bot.cfg)
        hoy = datetime.now(llm_engine._TZ_CO).date()
        assert hoy.isoformat() in system
        assert hoy == tarifario.hoy_colombia()

    def test_le_dice_explicitamente_que_no_suponga_anos_viejos(self, bot):
        system = llm_engine._system_prompt(bot, bot.cfg)
        assert "Nunca supongas un año anterior al de hoy" in system


class TestEnviarMediaTolerante:
    """Hallazgo 2 de la prueba del 19-ago-2026: el bot prometía una imagen que
    nunca salía.

    El modelo a veces serializa el arreglo: manda `"['formulario_reserva']"` en
    vez de `["formulario_reserva"]`. Recorrer ese texto daba letras sueltas,
    ninguna coincidía con una clave y no se enviaba nada — en silencio, con el
    bot diciendo «te dejo el tarifario 👇».
    """

    def _envia(self, bot, claves):
        actions = []
        llm_engine._run_tool(
            "enviar_media", {"claves": claves}, bot.cfg, actions, [], [], [],
        )
        return [a["payload"]["url"].rsplit("/", 1)[-1]
                for a in actions if a["type"] == "say_media"]

    def test_una_lista_normal_sigue_funcionando(self, bot):
        assert self._envia(bot, ["formulario_reserva"]) == ["fomulario_reserva.jpeg"]

    def test_el_arreglo_serializado_tambien_envia(self, bot):
        assert self._envia(bot, "['formulario_reserva']") == ["fomulario_reserva.jpeg"]

    def test_con_comillas_dobles_igual(self, bot):
        assert self._envia(bot, '["tours", "tour_video"]') == \
            ["tours.jpeg", "tour.mp4"]

    def test_una_sola_clave_suelta_como_texto(self, bot):
        assert self._envia(bot, "medios_pago") == ["medios_pago.jpeg"]

    def test_una_clave_que_no_existe_no_envia_nada(self, bot):
        """La tolerancia no puede convertirse en inventar medios."""
        assert self._envia(bot, "['no_existe']") == []

    def test_letra_por_letra_nunca_mas(self, bot):
        """La regresión concreta: ni una sola letra suelta cuenta como clave."""
        assert llm_engine._lista_de_claves("['formulario_reserva']") == \
            ["formulario_reserva"]


class TestLaNotaQuedaEnElChat:
    def test_la_nota_trae_el_nombre_y_la_fecha(self, db_session, conversacion):
        bot_runner._nota_de_handoff(
            db_session, conversacion,
            {
                "resumen": "Andrés Ruiz, 2 personas, 18 al 21 de septiembre",
                "motivo": "envió datos de reserva",
            },
        )
        nota = conversacion.messages[-1]
        assert nota.message_type == "nota_interna"
        assert "Andrés Ruiz" in nota.content
        assert "18 al 21 de septiembre" in nota.content
        assert "envió datos de reserva" in nota.content

    def test_sin_resumen_ni_motivo_no_ensucia_el_chat(self, db_session, conversacion):
        bot_runner._nota_de_handoff(db_session, conversacion, {})
        assert conversacion.messages == []

    def test_la_nota_no_se_le_manda_al_cliente(self, db_session, conversacion):
        """La nota es interna: si saliera por WhatsApp, el cliente leería el
        resumen que el bot escribió para el asesor."""
        with patch.object(bot_runner, "_send_text") as enviar:
            bot_runner._nota_de_handoff(
                db_session, conversacion, {"resumen": "Andrés, septiembre"}
            )
        enviar.assert_not_called()

    def test_un_fallo_guardando_la_nota_no_tumba_el_handoff(
        self, db_session, conversacion
    ):
        with patch.object(crud, "add_message", side_effect=RuntimeError("boom")):
            bot_runner._nota_de_handoff(
                db_session, conversacion, {"resumen": "Andrés"}
            )   # no debe propagar
