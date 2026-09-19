"""Los reenganches de silencio, ahora configurables por cuenta (fase 3).

La regla que ordena todo lo de aquí: **manda la tabla, el JSON es el
respaldo**. Mientras `bot_recordatorios` esté vacía para un bot, el motor lee
`llm_config.seguimiento` exactamente como el día anterior al despliegue — el
bot de Arranquemos Pues lleva meses reenganchando a los 15 min, a las 5 h y a
las 23 h, y no puede cambiar de comportamiento porque se despliegue un sprint.
Cambia el día que alguien cargue sus filas.

El error fácil que estas pruebas existen para impedir: leer `[15, 300, 1380]`
como offsets. No lo son. Los minutos se cuentan **desde que empezó el
silencio**, así que el segundo recordatorio se agenda a 4 h 45 del primero, no
a 5 h.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest

from app import crud, models
from app.data.bot_viajes import LLM_CONFIG
from app.services import bot_runner, llm_engine

from .conftest import crear_cuenta

#: Número sintético: este repo es público (regla #8).
WA_ID = "573000000009"

#: La política de Arranquemos Pues, tal como está desplegada.
MINUTOS_DE_VIAJES = [15, 5 * 60, 23 * 60]


# ---------------------------------------------------------------------------
# Andamiaje
# ---------------------------------------------------------------------------

def _respuesta(texto: str) -> dict:
    return {
        "content": [{"type": "text", "text": texto}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


@pytest.fixture
def modelo(monkeypatch):
    """Bedrock siempre contesta lo mismo: aquí no se mide qué redactó."""
    monkeypatch.setattr(
        llm_engine, "_invoke_model",
        lambda *a, **k: _respuesta("¿Para qué fecha lo piensas?"),
    )


@pytest.fixture
def agencia(db_session):
    """Una cuenta con el bot de viajes: su `llm_config` real, sin filas."""
    team_id, bot_id = crear_cuenta(db_session, "recordatorios")
    bot = db_session.get(models.Bot, bot_id)
    bot.llm_config = json.dumps(LLM_CONFIG, ensure_ascii=False)
    bot.status = "active"
    db_session.add(bot)
    db_session.commit()
    return db_session.get(models.Team, team_id), bot


def cargar(
    db,
    team_id: int,
    filas: List[Dict[str, Any]],
    *,
    bot_id: int = models.REF_TODAS,
) -> None:
    """Escribe la cadena de recordatorios de una cuenta."""
    for i, fila in enumerate(filas, start=1):
        db.add(
            models.BotRecordatorio(
                team_id=team_id,
                bot_id=fila.get("bot_id", bot_id),
                orden=fila.get("orden", i),
                minutos=fila["minutos"],
                texto=fila["texto"],
                omitir_si=fila.get("omitir_si") or {},
                hora_min=fila.get("hora_min", 0),
                hora_max=fila.get("hora_max", 23),
                activo=fila.get("activo", True),
            )
        )
    db.commit()


def arrancar(db, team, bot) -> models.Conversation:
    """Una conversación viva con su primer turno corrido."""
    conv = crud.get_or_create_conversation(db, team.id, WA_ID, contact_name=None)
    crud.add_message(db, conv, direction="inbound", content="Hola", status="received")
    bot_runner.run_turn(
        db, bot=bot, conversation=conv, session=None, user_input="Hola",
        meta_account=None,
    )
    db.refresh(conv)
    return conv


def pendiente(db, conv) -> Optional[models.BotPendingAction]:
    return (
        db.query(models.BotPendingAction)
        .join(models.BotSession)
        .filter(
            models.BotSession.conversation_id == conv.id,
            models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING,
        )
        .first()
    )


def salientes(db, conv) -> list:
    return (
        db.query(models.Message)
        .filter(
            models.Message.conversation_id == conv.id,
            models.Message.direction == "outbound",
            models.Message.message_type != "nota_interna",
        )
        .order_by(models.Message.id)
        .all()
    )


def _vencer(db, pa) -> None:
    pa.scheduled_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()


def faltan_minutos(pa) -> float:
    return (pa.scheduled_at - datetime.utcnow()).total_seconds() / 60


# ---------------------------------------------------------------------------
# La tabla vacía: nada cambia
# ---------------------------------------------------------------------------

class TestConLaTablaVacia:
    def test_los_recordatorios_salen_del_json(self, db_session, agencia):
        """El respaldo, y el estado de los seis bots que hay en producción."""
        _, bot = agencia
        etapas = llm_engine.recordatorios_de(
            llm_engine.seguimiento_de(bot), db=db_session, bot=bot
        )

        assert [e["minutos"] for e in etapas] == MINUTOS_DE_VIAJES

    def test_la_franja_del_json_no_restringe_nada(self, db_session, agencia):
        """De 0 a 23 = a cualquier hora, que es lo que hace el motor desde
        #377. Si el respaldo trajera una franja, el bot desplegado cambiaría de
        comportamiento el día del deploy — justo lo que no puede pasar."""
        _, bot = agencia
        etapas = llm_engine.recordatorios_de(
            llm_engine.seguimiento_de(bot), db=db_session, bot=bot
        )

        assert all((e["hora_min"], e["hora_max"]) == (0, 23) for e in etapas)
        assert all(e["omitir_si"] == {} for e in etapas)

    def test_viajes_manda_sus_tres_mensajes_igual_que_antes(
        self, db_session, agencia, modelo
    ):
        """La cadena completa, de punta a punta, sin una sola fila cargada."""
        team, bot = agencia
        conv = arrancar(db_session, team, bot)
        antes = len(salientes(db_session, conv))

        for _ in range(3):
            pa = pendiente(db_session, conv)
            _vencer(db_session, pa)
            bot_runner.process_pending_action(db_session, pa)

        nuevos = [m.content for m in salientes(db_session, conv)[antes:]]
        assert len(nuevos) == 3
        assert len(set(nuevos)) == 3, "los tres textos no pueden ser el mismo"

    def test_sin_bot_ni_sesion_sigue_respondiendo(self, db_session, agencia):
        """`recordatorios_de(seg)` a secas tiene que seguir funcionando: lo
        llaman desde sitios que no tienen ni base ni bot a mano."""
        assert llm_engine.recordatorios_de({"minutos": 15})[0]["minutos"] == 15


# ---------------------------------------------------------------------------
# Con filas: mandan las filas
# ---------------------------------------------------------------------------

class TestConFilasCargadas:
    def test_las_filas_le_ganan_al_json(self, db_session, agencia):
        team, bot = agencia
        cargar(db_session, team.id, [
            {"minutos": 20, "texto": "primero"},
            {"minutos": 90, "texto": "segundo"},
        ])

        etapas = llm_engine.recordatorios_de(
            llm_engine.seguimiento_de(bot), db=db_session, bot=bot
        )

        assert [e["minutos"] for e in etapas] == [20, 90]
        assert [e["texto"] for e in etapas] == ["primero", "segundo"]

    def test_el_orden_lo_manda_el_reloj_no_la_columna_orden(
        self, db_session, agencia
    ):
        """Quien configura puede numerarlas al revés; el silencio no se
        negocia. Con la lista ordenada, además, la resta que agenda la
        siguiente nunca es negativa."""
        team, bot = agencia
        cargar(db_session, team.id, [
            {"orden": 1, "minutos": 300, "texto": "el de las cinco horas"},
            {"orden": 2, "minutos": 15, "texto": "el de los quince minutos"},
        ])

        etapas = llm_engine.recordatorios_de(
            llm_engine.seguimiento_de(bot), db=db_session, bot=bot
        )

        assert [e["minutos"] for e in etapas] == [15, 300]

    def test_la_fila_inactiva_no_cuenta(self, db_session, agencia):
        team, bot = agencia
        cargar(db_session, team.id, [
            {"minutos": 20, "texto": "vivo"},
            {"minutos": 90, "texto": "apagado", "activo": False},
        ])

        etapas = llm_engine.recordatorios_de(
            llm_engine.seguimiento_de(bot), db=db_session, bot=bot
        )

        assert [e["texto"] for e in etapas] == ["vivo"]

    def test_las_filas_del_bot_le_ganan_a_las_de_la_cuenta(
        self, db_session, agencia
    ):
        """Configurar "todos mis bots" y después afinar uno tiene que poderse
        sin borrar lo otro."""
        team, bot = agencia
        cargar(db_session, team.id, [{"minutos": 20, "texto": "de la cuenta"}])
        cargar(
            db_session, team.id,
            [{"minutos": 45, "texto": "de este bot"}], bot_id=bot.id,
        )

        etapas = llm_engine.recordatorios_de(
            llm_engine.seguimiento_de(bot), db=db_session, bot=bot
        )

        assert [e["texto"] for e in etapas] == ["de este bot"]

    def test_el_segundo_se_agenda_a_la_diferencia_no_al_total(
        self, db_session, agencia, modelo
    ):
        """**El error fácil.** Con 15 min · 5 h · 23 h, el segundo sale a 4 h 45
        del primero: los minutos se cuentan desde que empezó el silencio, y
        leerlos como offsets le regalaría 15 minutos a cada etapa."""
        team, bot = agencia
        cargar(db_session, team.id, [
            {"minutos": m, "texto": f"recordatorio {i}"}
            for i, m in enumerate(MINUTOS_DE_VIAJES, start=1)
        ])
        conv = arrancar(db_session, team, bot)

        esperados = [15, 5 * 60 - 15, 23 * 60 - 5 * 60]
        for esperado in esperados:
            pa = pendiente(db_session, conv)
            assert abs(faltan_minutos(pa) - esperado) <= 2, (
                esperado, faltan_minutos(pa)
            )
            _vencer(db_session, pa)
            bot_runner.process_pending_action(db_session, pa)

    def test_salen_los_textos_de_la_tabla(self, db_session, agencia, modelo):
        team, bot = agencia
        cargar(db_session, team.id, [
            {"minutos": 15, "texto": "Texto cargado por la cuenta ✨"},
        ])
        conv = arrancar(db_session, team, bot)

        pa = pendiente(db_session, conv)
        _vencer(db_session, pa)
        bot_runner.process_pending_action(db_session, pa)

        assert salientes(db_session, conv)[-1].content == (
            "Texto cargado por la cuenta ✨"
        )


# ---------------------------------------------------------------------------
# La franja horaria
# ---------------------------------------------------------------------------

class TestFranjaHoraria:
    """Nadie quiere un recordatorio comercial a las 4 de la mañana."""

    def test_un_silencio_de_las_11_pm_no_dispara_a_las_4_am(self):
        """El caso del enunciado, con el reloj puesto a mano.

        23:00 en Colombia son las 04:00 UTC del día siguiente; el reenganche de
        5 horas cae a las 04:00 de allá. Con la franja 8–20, sale a las 8.
        """
        # 04:00 del 2 de enero en UTC = 23:00 del 1 de enero en Colombia.
        empezo = datetime(2026, 1, 2, 4, 0)
        a_las_cinco_horas = empezo + timedelta(hours=5)

        corrido = bot_runner._dentro_de_la_franja(a_las_cinco_horas, 8, 20)

        local = corrido - timedelta(hours=5)
        assert (local.hour, local.minute) == (8, 0)
        assert local.date() == datetime(2026, 1, 2).date()

    def test_lo_que_cae_dentro_de_la_franja_no_se_mueve(self):
        """Mover lo que no hace falta sería retrasar un mensaje que llegaba
        bien."""
        # 15:00 en Colombia = 20:00 UTC.
        dentro = datetime(2026, 1, 2, 20, 0)

        assert bot_runner._dentro_de_la_franja(dentro, 8, 20) == dentro

    def test_pasada_la_franja_espera_a_la_manana_siguiente(self):
        """22:00 en Colombia con franja hasta las 20: mañana a las 8."""
        # 03:00 UTC del día 3 = 22:00 del día 2 en Colombia.
        tarde = datetime(2026, 1, 3, 3, 0)

        corrido = bot_runner._dentro_de_la_franja(tarde, 8, 20)

        local = corrido - timedelta(hours=5)
        assert (local.hour, local.minute) == (8, 0)
        assert local.date() == datetime(2026, 1, 3).date()

    def test_la_franja_por_defecto_no_mueve_nada(self):
        """0–23 es la del respaldo: a cualquier hora, como hasta hoy."""
        for hora in range(24):
            cuando = datetime(2026, 1, 2, hora, 37)
            assert bot_runner._dentro_de_la_franja(cuando, 0, 23) == cuando

    def test_lo_agendado_respeta_la_franja_de_la_etapa(
        self, db_session, agencia, modelo
    ):
        """Y llega hasta la tabla: no basta con que la función sepa restar.

        La franja se construye a partir del reloj real para que la prueba diga
        lo mismo a cualquier hora del día: se elige una ventana de una sola
        hora que con seguridad no es la de ahora.
        """
        team, bot = agencia
        hora_permitida = ((datetime.utcnow() - timedelta(hours=5)).hour + 2) % 24
        cargar(db_session, team.id, [
            {
                "minutos": 15,
                "texto": "sólo a su hora",
                "hora_min": hora_permitida,
                "hora_max": hora_permitida,
            },
        ])

        conv = arrancar(db_session, team, bot)

        pa = pendiente(db_session, conv)
        local = pa.scheduled_at - timedelta(hours=5)
        assert (local.hour, local.minute) == (hora_permitida, 0)


# ---------------------------------------------------------------------------
# `omitir_si`
# ---------------------------------------------------------------------------

class TestOmitirSi:
    def _ya_compro(self, db, conv, bot, herramienta: str = "registrar_venta") -> None:
        """La huella que deja el motor cuando el bot cierra una venta."""
        db.add(
            models.BotLlmDecision(
                bot_id=bot.id,
                conversation_id=conv.id,
                source="whatsapp",
                camino="venta",
                tools_called=json.dumps(
                    [{"tool": herramienta, "input": {}, "resultado": "ok"}]
                ),
            )
        )
        db.commit()

    def test_a_quien_ya_compro_no_se_le_insiste(self, db_session, agencia, modelo):
        team, bot = agencia
        cargar(db_session, team.id, [
            {
                "minutos": 15,
                "texto": "¿te quedó alguna duda?",
                "omitir_si": {"tools": ["registrar_venta"]},
            },
        ])
        conv = arrancar(db_session, team, bot)
        self._ya_compro(db_session, conv, bot)
        antes = len(salientes(db_session, conv))

        pa = pendiente(db_session, conv)
        _vencer(db_session, pa)
        bot_runner.process_pending_action(db_session, pa)

        assert len(salientes(db_session, conv)) == antes, (
            "acababa de comprar: ese mensaje no se manda"
        )

    def test_si_no_compro_el_recordatorio_sale(self, db_session, agencia, modelo):
        """El contrapunto: sin él, un `omitir_si` que se cumpliera siempre
        pasaría por un guardarraíl que funciona."""
        team, bot = agencia
        cargar(db_session, team.id, [
            {
                "minutos": 15,
                "texto": "¿te quedó alguna duda?",
                "omitir_si": {"tools": ["registrar_venta"]},
            },
        ])
        conv = arrancar(db_session, team, bot)
        antes = len(salientes(db_session, conv))

        pa = pendiente(db_session, conv)
        _vencer(db_session, pa)
        bot_runner.process_pending_action(db_session, pa)

        assert len(salientes(db_session, conv)) == antes + 1

    def test_otra_herramienta_no_cuenta(self, db_session, agencia, modelo):
        """La condición nombra herramientas concretas. Que el bot haya llamado
        cualquier otra no dice nada de si la persona compró."""
        team, bot = agencia
        cargar(db_session, team.id, [
            {
                "minutos": 15,
                "texto": "¿te quedó alguna duda?",
                "omitir_si": {"tools": ["registrar_venta"]},
            },
        ])
        conv = arrancar(db_session, team, bot)
        self._ya_compro(db_session, conv, bot, herramienta="enviar_media")
        antes = len(salientes(db_session, conv))

        pa = pendiente(db_session, conv)
        _vencer(db_session, pa)
        bot_runner.process_pending_action(db_session, pa)

        assert len(salientes(db_session, conv)) == antes + 1


# ---------------------------------------------------------------------------
# Aislamiento por cuenta
# ---------------------------------------------------------------------------

def test_los_recordatorios_de_una_cuenta_no_los_lee_el_bot_de_otra(
    db_session, agencia
):
    """Mismo criterio que el catálogo: todo filtrado por `team_id`. Que a una
    agencia le salgan los textos de otra es el peor error de este esquema."""
    _, bot = agencia
    otro_team, otro_bot_id = crear_cuenta(db_session, "vecina")
    cargar(db_session, otro_team, [{"minutos": 3, "texto": "de la vecina"}])

    etapas = llm_engine.recordatorios_de(
        llm_engine.seguimiento_de(bot), db=db_session, bot=bot
    )

    assert [e["minutos"] for e in etapas] == MINUTOS_DE_VIAJES
    assert all("vecina" not in e["texto"] for e in etapas)


def test_un_bot_sin_cuenta_cae_en_el_json(db_session, agencia):
    """`bots.team_id` es nullable. Sin cuenta no se puede aislar, así que no se
    consulta: se usa la config, que es de ese bot y de nadie más."""
    team, bot = agencia
    cargar(db_session, team.id, [{"minutos": 3, "texto": "de la cuenta"}])
    bot.team_id = None
    db_session.add(bot)
    db_session.commit()

    etapas = llm_engine.recordatorios_de(
        llm_engine.seguimiento_de(bot), db=db_session, bot=bot
    )

    assert [e["minutos"] for e in etapas] == MINUTOS_DE_VIAJES
