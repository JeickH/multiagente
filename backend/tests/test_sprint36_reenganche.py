"""Sprint 36 — reenganche y camino de regreso (diseño de seguridad, sección 2).

Cubre los «Tests exigidos» de la sección 2:

  * abandonada → `bot`, `reclamos=1`, una nota, un turno (Bedrock simulado), y
    un segundo entrante sin otra nota;
  * la cerrada por inactividad se reclama;
  * NO se reclaman: la cerrada por asesora, la cerrada por despedida del bot,
    la reabierta y la reasignada por el owner;
  * humano hace 1 h 59 → solo nota (una vez); 2 h 01 → el bot toma;
  * `llm_engine.advance` parcheado que inserta un humano a mitad de turno → no
    se envía nada;
  * bot de reenganche de otro owner forzado en la BD se ignora (y el pausado,
    el demo y el `flow`);
  * espía: el tick y las acciones pendientes nunca llaman `reclamar`;
  * el turno 31 de la hora no llama a Bedrock;
  * `add_message` sella solo el humano saliente que no es nota;
  * `caplog` sin texto ni teléfono.

Más el camino de regreso (el bloque que recibe el motor, sin la cifra vieja) y
el sello previo de 2.4b. Las sesiones concurrentes en Postgres están en
`test_sprint36_reenganche_postgres.py`. Teléfonos y cédulas inventados
(regla #8).
"""
from __future__ import annotations

import json
import logging
import runpy
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.data.bot_viajes import LLM_CONFIG
from app.routers import mensajes
from app.services import bot_router, bot_runner, llm_engine, reenganche

WA = "573000000731"
ASESORES = ["Camila", "Julián"]


# ---------------------------------------------------------------------------
# Andamiaje
# ---------------------------------------------------------------------------

def _texto(t: str) -> dict:
    return {"type": "text", "text": t}


def _respuesta(*bloques, stop: str = "end_turn") -> dict:
    return {"content": list(bloques), "stop_reason": stop,
            "usage": {"input_tokens": 10, "output_tokens": 5}}


class ModeloFalso:
    def __init__(self) -> None:
        self.guion: list = []
        self.recibidos: list = []

    def __call__(self, model_id, system, messages, tools):
        self.recibidos.append({"system": system, "messages": [dict(m) for m in messages]})
        if not self.guion:
            return _respuesta(_texto("¡Hola de nuevo! 😊 ¿Te aparto los cupos? 🙌"))
        return self.guion.pop(0)


@pytest.fixture
def modelo(monkeypatch) -> ModeloFalso:
    falso = ModeloFalso()
    monkeypatch.setattr(llm_engine, "_invoke_model", falso)
    return falso


@pytest.fixture
def db():
    from app.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


def _owner(db, sufijo: str):
    return crud.create_user(db, schemas.UserCreate(
        nombre="Agencia", correo=f"s36_{sufijo}@test.com", tipo_documento="CC",
        documento=f"S36{sufijo}", password="Clave-De-Prueba-1",
    ))


def _bot(db, owner, team, *, nombre="Maria Camila", engine="llm", status="active",
         trigger=models.BOT_TRIGGER_DEFAULT, reenganche_=False, cfg=None):
    bot = models.Bot(
        user_id=owner.id, team_id=team.id, name=nombre, engine=engine, status=status,
        trigger_type=trigger, es_reenganche=reenganche_,
        llm_config=json.dumps(cfg if cfg is not None else LLM_CONFIG, ensure_ascii=False),
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


@pytest.fixture
def agencia(db):
    owner = _owner(db, "A")
    team = crud.create_team(db, "Agencia Reenganche", owner)
    team.asesores_rotacion = list(ASESORES)
    db.add(team)
    db.commit()
    bot = _bot(db, owner, team)
    return {"owner": owner, "team": team, "bot": bot,
            "member": crud.get_membership_for_user(db, owner)}


def _con_historia(db, team, bot, *, wa=WA, fecha="2026-12-04"):
    """Una conversación con lo que el bot ya había cotizado: sesión cerrada,
    una consulta de precios con el grupo y un total que el bot le escribió."""
    conv = crud.get_or_create_conversation(db, team.id, wa, contact_name=None)
    crud.add_message(db, conv, direction="inbound", content="hola, info del plan",
                     status="received")
    sesion = models.BotSession(bot_id=bot.id, conversation_id=conv.id,
                               status=models.BOT_SESSION_FINISHED,
                               state=json.dumps({"history": []}))
    db.add(sesion)
    db.commit()
    db.add(models.BotLlmDecision(
        bot_id=bot.id, session_id=sesion.id, conversation_id=conv.id, source="whatsapp",
        camino="precios", tools_called=json.dumps([{
            "tool": "consultar_tarifario",
            "input": {"mes": "diciembre", "fecha": fecha, "hotel": "Piedra Mar",
                      "adultos": "2", "ninos": "5"},
            "resultado": "…",
        }]),
        created_at=datetime.utcnow() - timedelta(days=2),
    ))
    db.commit()
    crud.add_message(
        db, conv, direction="outbound", status="sent",
        content="Para 2 adultos y un niño de 5: 2 × $459.000 + niño = $1.377.000 total 🌴",
    )
    conv.bot_asignado_id = bot.id
    conv.bot_asignado_at = datetime.utcnow() - timedelta(days=2)
    db.commit()
    return conv


def _abandonada(db, team, bot, **kw):
    conv = _con_historia(db, team, bot, **kw)
    conv.status = "pending"
    conv.assigned_to = "Camila"
    conv.etiqueta = "conversación abandonada"
    conv.abandono_at = datetime.utcnow() - timedelta(days=1)
    conv.abandono_asesor = "Camila"
    conv.reclamos_abandono = 0
    db.commit()
    return conv


def _inactiva(db, team, bot, **kw):
    conv = _abandonada(db, team, bot, **kw)
    conv.status = "closed"
    conv.cerrada_por_inactividad_at = datetime.utcnow() - timedelta(hours=3)
    db.commit()
    return conv


def entra(db, team, texto: str, wa: str = WA, account=None):
    """Lo mismo que hacen los webhooks (Twilio y Meta)."""
    conv = crud.get_or_create_conversation(db, team.id, wa, contact_name=None)
    crud.add_message(db, conv, direction="inbound", content=texto, status="received")
    bot, session = bot_router.resolve_bot_for_incoming_message(
        db, team=team, conversation_id=conv.id, message_text=texto)
    if bot is not None:
        bot_runner.run_turn(
            db, bot=bot, conversation=conv, session=session,
            user_input=texto if session is not None else None,
            primer_mensaje=texto if session is None else None,
            meta_account=account,
        )
    db.refresh(conv)
    return conv, bot


def _mensajes(db, conv, *, notas: bool):
    q = db.query(models.Message).filter(
        models.Message.conversation_id == conv.id,
        models.Message.direction == "outbound",
    )
    q = q.filter(models.Message.message_type == "nota_interna") if notas else \
        q.filter(models.Message.message_type != "nota_interna")
    return q.order_by(models.Message.id).all()


def notas_volvio(db, conv):
    return [m for m in _mensajes(db, conv, notas=True)
            if m.content.startswith(reenganche.TITULO_VOLVIO)]


def enviados(db, conv):
    return _mensajes(db, conv, notas=False)


# ---------------------------------------------------------------------------
# 2.1 / 2.5: el reclamo
# ---------------------------------------------------------------------------

class TestAbandonadaSeReclama:
    def test_vuelve_al_bot_con_una_nota_y_un_turno(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        antes = len(enviados(db, conv))

        conv, bot = entra(db, agencia["team"], "hola, ¿todavía está el plan?")

        assert bot is not None and bot.id == agencia["bot"].id
        assert conv.assigned_to == "bot"
        assert conv.status == "open"
        assert conv.reclamos_abandono == 1
        assert conv.marcador_consumido == models.MARCADOR_CONSUMIDO_VOLVIO
        assert len(notas_volvio(db, conv)) == 1
        assert len(modelo.recibidos) == 1, "un solo turno de Bedrock"
        assert len(enviados(db, conv)) == antes + 1

    def test_el_segundo_entrante_no_deja_otra_nota(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        entra(db, agencia["team"], "hola, ¿todavía está el plan?")
        conv, bot = entra(db, agencia["team"], "y ¿qué incluye?")

        assert bot is not None
        assert conv.reclamos_abandono == 1
        assert len(notas_volvio(db, conv)) == 1
        assert len(modelo.recibidos) == 2

    def test_la_nota_resume_sin_telefono_ni_cedula(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv, _ = entra(db, agencia["team"], "Hola, mi cédula es 1012345678")
        nota = notas_volvio(db, conv)[0].content
        assert "2026-12-04" in nota and "Piedra Mar" in nota
        assert "2 adultos y niño de 5" in nota
        assert "$1.377.000" in nota
        assert WA not in nota and "1012345678" not in nota

    def test_la_bandeja_la_sube(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv.last_message_at = datetime.utcnow() - timedelta(days=1)
        db.commit()
        antes = conv.last_message_at
        conv, _ = entra(db, agencia["team"], "hola de nuevo")
        assert conv.last_message_at > antes
        assert conv.etiqueta == bot_runner.ETIQUETA_VOLVIO

    def test_no_pisa_la_atribucion_del_ab(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        asignado = (conv.bot_asignado_id, conv.bot_asignado_at)
        conv, _ = entra(db, agencia["team"], "hola de nuevo")
        assert (conv.bot_asignado_id, conv.bot_asignado_at) == asignado

    def test_cierra_la_llamada_de_rescate(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        db.add(models.Agendamiento(
            team_id=conv.team_id, conversation_id=conv.id,
            nivel_interes=models.AGENDAMIENTO_NIVEL_CON_INFORMACION,
            fecha_llamada=datetime.utcnow().date(), estado=models.AGENDAMIENTO_PENDIENTE,
            origen=models.AGENDAMIENTO_ORIGEN_ABANDONO,
        ))
        db.commit()
        entra(db, agencia["team"], "hola de nuevo")
        llamada = db.query(models.Agendamiento).filter_by(conversation_id=conv.id).one()
        assert llamada.estado == models.AGENDAMIENTO_CERRADO

    def test_una_pura_cortesia_no_gasta_el_marcador(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv, bot = entra(db, agencia["team"], "gracias")
        assert bot is None
        assert conv.reclamos_abandono == 0 and conv.assigned_to == "Camila"
        assert modelo.recibidos == [] and notas_volvio(db, conv) == []


def test_la_cerrada_por_inactividad_se_reclama(db, agencia, modelo):
    conv = _inactiva(db, agencia["team"], agencia["bot"])
    conv, bot = entra(db, agencia["team"], "hola, ¿siguen con el plan?")
    assert bot is not None
    assert conv.assigned_to == "bot" and conv.status == "open"
    assert conv.reclamos_abandono == 1
    nota = notas_volvio(db, conv)[0].content
    assert "inactividad" in nota


class TestNoSeReclaman:
    def _sin_reclamo(self, db, conv, modelo):
        db.refresh(conv)
        assert notas_volvio(db, conv) == []
        assert modelo.recibidos == []

    def test_la_cerrada_por_la_asesora(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        mensajes.close_conversation(conv.id, db=db, member=agencia["member"])
        db.refresh(conv)
        assert conv.reclamos_abandono == 1
        assert conv.marcador_consumido == models.MARCADOR_CONSUMIDO_HUMANO
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot is None and conv.assigned_to == "Camila"
        self._sin_reclamo(db, conv, modelo)

    def test_la_cerrada_por_despedida_del_bot(self, db, agencia, modelo):
        conv = _con_historia(db, agencia["team"], agencia["bot"])
        conv.status = "closed"
        db.commit()
        entra(db, agencia["team"], "hola otra vez, ¿cuánto vale enero?")
        db.refresh(conv)
        assert conv.reclamos_abandono == 0 and conv.marcador_consumido is None
        assert notas_volvio(db, conv) == []

    def test_la_reabierta(self, db, agencia, modelo):
        conv = _inactiva(db, agencia["team"], agencia["bot"])
        mensajes.reopen_conversation(conv.id, db=db, member=agencia["member"])
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot is None and conv.assigned_to == "Camila"
        assert conv.marcador_consumido == models.MARCADOR_CONSUMIDO_HUMANO
        self._sin_reclamo(db, conv, modelo)

    def test_la_reasignada_por_el_owner(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        mensajes.assign_conversation(
            conv.id, schemas.ConversationAsignarIn(assigned_to="Julián"),
            db=db, member=agencia["member"],
        )
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot is None and conv.assigned_to == "Julián"
        self._sin_reclamo(db, conv, modelo)

    def test_otro_team_no_puede_reclamar(self, db, agencia):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        otro = crud.create_team(db, "Ajena", _owner(db, "Z"))
        assert reenganche.reclamar(db, otro, conv, "Camila") is None
        db.refresh(conv)
        assert conv.reclamos_abandono == 0

    def test_si_la_reasignaron_entre_la_lectura_y_el_update(self, db, agencia):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        assert reenganche.reclamar(db, agencia["team"], conv, "Julián") is None
        db.refresh(conv)
        assert conv.reclamos_abandono == 0 and conv.assigned_to == "Camila"


# ---------------------------------------------------------------------------
# 2.4: la regla de las 2 h
# ---------------------------------------------------------------------------

class TestReglaDeLasDosHoras:
    def test_humano_hace_1h59_solo_nota_una_vez(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv.ultimo_mensaje_humano_at = datetime.utcnow() - timedelta(hours=1, minutes=59)
        db.commit()
        antes = len(enviados(db, conv))

        conv, bot = entra(db, agencia["team"], "hola, ¿me confirmas?")
        assert bot is None
        assert conv.assigned_to == "Camila" and conv.status == "pending"
        assert conv.reclamos_abandono == 1
        assert len(notas_volvio(db, conv)) == 1
        assert "menos de 2 horas" in notas_volvio(db, conv)[0].content

        entra(db, agencia["team"], "¿hola?")
        assert len(notas_volvio(db, conv)) == 1
        assert modelo.recibidos == []
        assert len(enviados(db, conv)) == antes

    def test_la_inactiva_con_humano_reciente_vuelve_a_pendientes(self, db, agencia, modelo):
        conv = _inactiva(db, agencia["team"], agencia["bot"])
        conv.ultimo_mensaje_humano_at = datetime.utcnow() - timedelta(minutes=10)
        db.commit()
        conv, bot = entra(db, agencia["team"], "hola, ¿me confirmas?")
        assert bot is None and conv.status == "pending" and conv.assigned_to == "Camila"

    def test_humano_hace_2h01_el_bot_toma(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv.ultimo_mensaje_humano_at = datetime.utcnow() - timedelta(hours=2, minutes=1)
        db.commit()
        conv, bot = entra(db, agencia["team"], "hola, ¿me confirmas?")
        assert bot is not None and conv.assigned_to == "bot"
        assert len(modelo.recibidos) == 1

    def test_tomada_no_basta_sin_mensaje(self, db, agencia, modelo):
        """Una nota interna con autor (Interesados) no es «una persona escribió»."""
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        crud.add_message(db, conv, direction="outbound", content="📌 tomada",
                         message_type="nota_interna", sent_by_user_id=agencia["owner"].id)
        conv, bot = entra(db, agencia["team"], "hola, ¿me confirmas?")
        assert bot is not None

    def test_humano_a_mitad_de_turno_no_se_envia(self, db, agencia, monkeypatch):
        """2.4d: el sello cambia mientras «piensa» el modelo → se descarta."""
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        antes = len(enviados(db, conv))
        original = llm_engine.advance

        def advance_con_humano(bot, state, user_input, runtime=None):
            c = db.query(models.Conversation).filter_by(id=conv.id).one()
            crud.add_message(db, c, direction="outbound", content="te escribo yo",
                             sent_by_user_id=agencia["owner"].id)
            return {"actions": [{"type": "say", "payload": {"text": "¡Hola de nuevo!"}}],
                    "next_state": {"history": []}, "finished": False, "telemetry": None}

        monkeypatch.setattr(llm_engine, "advance", advance_con_humano)
        entra(db, agencia["team"], "hola, ¿siguen?")
        monkeypatch.setattr(llm_engine, "advance", original)
        bot_msgs = [m for m in enviados(db, conv) if m.sent_by_user_id is None]
        assert len(bot_msgs) == antes, "el bot envió aunque una persona escribió"

    def test_humano_a_mitad_de_turno_en_un_chat_normal(self, db, agencia, monkeypatch):
        """Mismo control para cualquier turno, no solo el de regreso."""
        conv = crud.get_or_create_conversation(db, agencia["team"].id, "573000000799",
                                               contact_name=None)

        def advance_con_humano(bot, state, user_input, runtime=None):
            c = db.query(models.Conversation).filter_by(id=conv.id).one()
            crud.add_message(db, c, direction="outbound", content="yo te atiendo",
                             sent_by_user_id=agencia["owner"].id)
            return {"actions": [{"type": "say", "payload": {"text": "¡Hola!"}}],
                    "next_state": {"history": []}, "finished": False, "telemetry": None}

        monkeypatch.setattr(llm_engine, "advance", advance_con_humano)
        entra(db, agencia["team"], "hola", wa="573000000799")
        assert [m.content for m in enviados(db, conv)] == ["yo te atiendo"]


# ---------------------------------------------------------------------------
# 2.3: qué bot lo atiende
# ---------------------------------------------------------------------------

class TestQueBotLoAtiende:
    def test_gana_el_bot_de_reenganche(self, db, agencia, modelo):
        r = _bot(db, agencia["owner"], agencia["team"], nombre="Reenganche",
                 trigger=models.BOT_TRIGGER_MANUAL if hasattr(models, "BOT_TRIGGER_MANUAL") else "manual",
                 reenganche_=True)
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot.id == r.id
        sesion = db.query(models.BotSession).filter_by(conversation_id=conv.id,
                                                       bot_id=r.id).one()
        assert sesion.status == models.BOT_SESSION_WAITING
        assert conv.bot_asignado_id == agencia["bot"].id, "la atribución A/B no cambia"

    def test_el_de_otro_owner_forzado_en_la_bd_se_ignora(self, db, agencia, modelo):
        ajeno_owner = _owner(db, "X")
        ajeno_team = crud.create_team(db, "Ajena", ajeno_owner)
        ajeno = _bot(db, ajeno_owner, ajeno_team, nombre="Ajeno", reenganche_=True)
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv.bot_asignado_id = ajeno.id          # forzado
        db.commit()
        db.query(models.BotSession).filter_by(conversation_id=conv.id).update(
            {models.BotSession.bot_id: ajeno.id})
        db.commit()
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot is not None and bot.id == agencia["bot"].id

    @pytest.mark.parametrize("variante", ["pausado", "demo", "flow"])
    def test_el_de_reenganche_que_no_pasa_el_filtro_se_ignora(
        self, db, agencia, modelo, variante
    ):
        kw = {"reenganche_": True, "nombre": "R", "trigger": "manual"}
        if variante == "pausado":
            kw["status"] = "paused"
        elif variante == "demo":
            kw["cfg"] = {**LLM_CONFIG, "demo": True}
        else:
            kw["engine"] = "flow"
        r = _bot(db, agencia["owner"], agencia["team"], **kw)
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot is not None and bot.id != r.id
        assert bot.id == agencia["bot"].id

    def test_sin_bot_de_reenganche_ni_el_anterior_va_el_reparto(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        agencia["bot"].status = "paused"
        nuevo = _bot(db, agencia["owner"], agencia["team"], nombre="Nuevo")
        db.commit()
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot.id == nuevo.id

    def test_sin_ningun_bot_vuelve_a_la_asesora_con_la_nota(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        agencia["bot"].status = "paused"
        db.commit()
        conv, bot = entra(db, agencia["team"], "hola, ¿siguen?")
        assert bot is None and modelo.recibidos == []
        assert conv.assigned_to == "Camila" and conv.status == "pending"
        assert conv.reclamos_abandono == 1
        notas = notas_volvio(db, conv)
        assert len(notas) == 1 and "contéstale tú" in notas[0].content
        # El siguiente entrante no deja otra nota ni lo toma un bot.
        conv, bot = entra(db, agencia["team"], "¿hola?")
        assert bot is None and len(notas_volvio(db, conv)) == 1

    def test_un_solo_bot_de_reenganche_por_owner(self, db, agencia):
        from sqlalchemy.exc import IntegrityError

        _bot(db, agencia["owner"], agencia["team"], nombre="R1", reenganche_=True)
        with pytest.raises(IntegrityError):
            _bot(db, agencia["owner"], agencia["team"], nombre="R2", reenganche_=True)
        db.rollback()


# ---------------------------------------------------------------------------
# El camino de regreso: lo que recibe el motor
# ---------------------------------------------------------------------------

class TestCaminoDeRegreso:
    def test_el_motor_sabe_que_es_un_regreso_sin_la_cifra_vieja(self, db, agencia, modelo):
        _abandonada(db, agencia["team"], agencia["bot"])
        entra(db, agencia["team"], "hola, ¿todavía está?")
        system = modelo.recibidos[0]["system"]
        assert "## Vuelve tras un silencio" in system
        assert "2026-12-04" in system and "Piedra Mar" in system
        assert "2 adultos y un niño de 5" in system
        assert "¿Te aparto los 3 cupos?" in system
        assert "vuelve a consultar" in system
        assert "1.377.000" not in system, "el total viejo no puede llegar al modelo"
        # El texto del cliente sí llega (no el saludo de primer turno).
        assert modelo.recibidos[0]["messages"][-1]["content"] == "hola, ¿todavía está?"

    def test_si_la_fecha_ya_paso_lo_dice(self, db, agencia, modelo):
        _abandonada(db, agencia["team"], agencia["bot"], fecha="2026-01-10")
        entra(db, agencia["team"], "hola")
        assert "ya pasó" in modelo.recibidos[0]["system"]

    def test_la_bandera_no_queda_en_el_estado(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        entra(db, agencia["team"], "hola, ¿todavía está?")
        entra(db, agencia["team"], "¿y qué incluye?")
        assert "## Vuelve tras un silencio" not in modelo.recibidos[1]["system"]
        for s in db.query(models.BotSession).filter_by(conversation_id=conv.id):
            assert "regreso" not in json.loads(s.state or "{}")

    def test_contrato_para_el_bot_d(self, db, agencia):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        reclamo = reenganche.reclamar(db, agencia["team"], conv, "Camila")
        contrato = reenganche.contrato_de_regreso(reclamo)
        assert contrato["via"] == "abandono"
        assert contrato["adultos"] == 2 and contrato["edades_ninos"] == [5]
        assert contrato["fecha"] == "2026-12-04" and contrato["fecha_paso"] is False
        assert contrato["habia_total"] is True and "ultimo_total" not in contrato
        json.dumps(contrato)    # serializable: viaja en el estado de la sesión

    def test_bloque_valida_contra_listas_cerradas(self):
        cfg = {"tarifario": True, "_runtime": {"regreso": {
            "via": "abandono", "fecha": "llámame al 3001234567", "hotel": "<script>",
            "adultos": "2; DROP", "edades_ninos": ["x", 99, 4], "mes": 13,
        }}}
        bloque = llm_engine._bloque_vuelve(cfg)
        assert "3001234567" not in bloque and "script" not in bloque and "DROP" not in bloque
        assert "La última vez estaba mirando" not in bloque


# ---------------------------------------------------------------------------
# 2.5: solo un entrante real reclama
# ---------------------------------------------------------------------------

def test_el_tick_y_las_acciones_nunca_llaman_reclamar(db, agencia, modelo, monkeypatch):
    llamadas = []
    monkeypatch.setattr(reenganche, "reclamar", lambda *a, **k: llamadas.append(a))
    conv = _abandonada(db, agencia["team"], agencia["bot"])
    sesion = models.BotSession(bot_id=agencia["bot"].id, conversation_id=conv.id,
                               status=models.BOT_SESSION_WAITING, state=None)
    db.add(sesion)
    db.commit()
    for tipo in (models.BOT_PENDING_ACTION_SEGUIMIENTO, models.BOT_PENDING_ACTION_ABANDONO,
                 models.BOT_PENDING_ACTION_RESUME):
        pa = models.BotPendingAction(
            session_id=sesion.id, scheduled_at=datetime.utcnow() - timedelta(minutes=1),
            action_type=tipo, status=models.BOT_PENDING_STATUS_PENDING,
            payload=json.dumps({"etapa": 0}),
        )
        db.add(pa)
        db.commit()
        bot_runner.process_pending_action(db, pa)
    # El endpoint del tick (EventBridge → Lambda → /internal/bot-scheduler/tick)
    # con acciones vencidas de verdad.
    from fastapi import BackgroundTasks

    from app.routers import internal

    otra = models.BotSession(bot_id=agencia["bot"].id, conversation_id=conv.id,
                             status=models.BOT_SESSION_WAITING, state=None)
    db.add(otra)
    db.commit()
    for tipo in (models.BOT_PENDING_ACTION_SEGUIMIENTO, models.BOT_PENDING_ACTION_ABANDONO):
        db.add(models.BotPendingAction(
            session_id=otra.id, scheduled_at=datetime.utcnow() - timedelta(minutes=1),
            action_type=tipo, status=models.BOT_PENDING_STATUS_PENDING,
            payload=json.dumps({"etapa": 0}),
        ))
    db.commit()
    respuesta = internal.bot_scheduler_tick(BackgroundTasks(), db=db, _=None, limit=50)
    assert respuesta["processed"] >= 1
    bot_runner.run_turn(db, bot=agencia["bot"], conversation=conv, session=None,
                        user_input="hola", meta_account=None)
    assert llamadas == []
    # Y el marcador sigue intacto para el próximo entrante real.
    db.refresh(conv)
    assert conv.reclamos_abandono == 0


# ---------------------------------------------------------------------------
# 2.6: tope de turnos
# ---------------------------------------------------------------------------

class TestTopeDeTurnos:
    def _turnos(self, db, bot, conv, n, hace):
        for _ in range(n):
            db.add(models.BotLlmDecision(bot_id=bot.id, conversation_id=conv.id,
                                         source="whatsapp", camino="x",
                                         created_at=datetime.utcnow() - hace))
        db.commit()

    def test_el_turno_31_de_la_hora_no_llama_bedrock(self, db, agencia, modelo, caplog):
        conv = crud.get_or_create_conversation(db, agencia["team"].id, WA, contact_name=None)
        self._turnos(db, agencia["bot"], conv, 30, timedelta(minutes=20))
        caplog.set_level(logging.INFO)
        conv, bot = entra(db, agencia["team"], "hola otra vez")
        assert bot is None and modelo.recibidos == []
        entra(db, agencia["team"], "¿hola?")
        notas = [m for m in _mensajes(db, conv, notas=True)
                 if m.content.startswith(reenganche.TITULO_TOPE)]
        assert len(notas) == 1
        assert WA not in caplog.text and "hola otra vez" not in caplog.text

    def test_120_en_el_dia(self, db, agencia, modelo):
        conv = crud.get_or_create_conversation(db, agencia["team"].id, WA, contact_name=None)
        self._turnos(db, agencia["bot"], conv, 120, timedelta(hours=5))
        conv, bot = entra(db, agencia["team"], "hola otra vez")
        assert bot is None and modelo.recibidos == []

    def test_29_pasa(self, db, agencia, modelo):
        conv = crud.get_or_create_conversation(db, agencia["team"].id, WA, contact_name=None)
        self._turnos(db, agencia["bot"], conv, 29, timedelta(minutes=20))
        _, bot = entra(db, agencia["team"], "hola otra vez")
        assert bot is not None and len(modelo.recibidos) == 1

    def test_el_tope_no_gasta_el_marcador(self, db, agencia, modelo):
        conv = _abandonada(db, agencia["team"], agencia["bot"])
        self._turnos(db, agencia["bot"], conv, 30, timedelta(minutes=5))
        conv, bot = entra(db, agencia["team"], "hola")
        assert bot is None and conv.reclamos_abandono == 0


# ---------------------------------------------------------------------------
# 0.4 / 2.4b: el sello humano
# ---------------------------------------------------------------------------

class TestSelloHumano:
    def test_add_message_sella_solo_humano_saliente_no_nota(self, db, agencia):
        conv = crud.get_or_create_conversation(db, agencia["team"].id, WA, contact_name=None)
        uid = agencia["owner"].id
        crud.add_message(db, conv, direction="inbound", content="hola", status="received")
        crud.add_message(db, conv, direction="outbound", content="bot", sent_by_user_id=None)
        crud.add_message(db, conv, direction="outbound", content="nota",
                         message_type="nota_interna", sent_by_user_id=uid)
        db.refresh(conv)
        assert conv.ultimo_mensaje_humano_at is None
        crud.add_message(db, conv, direction="outbound", content="asesora",
                         sent_by_user_id=uid)
        db.refresh(conv)
        assert conv.ultimo_mensaje_humano_at is not None

    def test_el_envio_sella_antes_del_proveedor(self, db, agencia, monkeypatch):
        conv = crud.get_or_create_conversation(db, agencia["team"].id, WA, contact_name=None)
        vistos = []

        def send_text(account, wa, texto):
            fila = db.execute(
                models.Conversation.__table__.select().where(models.Conversation.id == conv.id)
            ).mappings().one()
            vistos.append(fila["ultimo_mensaje_humano_at"])
            return "wamid.prueba", {}

        monkeypatch.setattr(mensajes.messaging, "send_text", send_text)
        monkeypatch.setattr(mensajes.crud, "get_meta_account_for_team", lambda *a: object())
        monkeypatch.setattr(mensajes.crud, "is_meta_account_usable", lambda *a: True)
        monkeypatch.setattr(mensajes.pausa, "exigir_servicio_activo", lambda *a: None)
        mensajes.send_message_in_conversation(
            conv.id, schemas.MessageSendIn(content="hola, soy Camila"),
            db=db, member=agencia["member"],
        )
        assert vistos and vistos[0] is not None


# ---------------------------------------------------------------------------
# 0.3: los marcadores se escriben con reset por episodio
# ---------------------------------------------------------------------------

def test_marcar_abandonada_escribe_el_marcador_y_resetea(db, agencia):
    conv = crud.get_or_create_conversation(db, agencia["team"].id, WA, contact_name=None)
    conv.reclamos_abandono = 1
    conv.marcador_consumido = models.MARCADOR_CONSUMIDO_VOLVIO
    db.commit()
    asesor = bot_runner._marcar_abandonada(db, conv, etiqueta="conversación abandonada",
                                           minutos=30)
    db.refresh(conv)
    assert asesor in ASESORES
    assert conv.abandono_at is not None and conv.abandono_asesor == asesor
    assert conv.reclamos_abandono == 0 and conv.marcador_consumido is None


def test_el_script_de_inactividad_escribe_el_marcador(db, agencia, monkeypatch):
    conv = _abandonada(db, agencia["team"], agencia["bot"])
    conv.reclamos_abandono = 1
    conv.last_message_at = datetime.utcnow() - timedelta(days=10)
    db.commit()
    import app.database as database

    monkeypatch.setattr(database, "SessionLocal", lambda: db)
    monkeypatch.setenv("APLICAR", "1")
    monkeypatch.setenv("TEAM", str(agencia["team"].id))
    ruta = Path(__file__).resolve().parents[1] / "scripts" / "cerrar_inactivas_arranquemos.py"
    runpy.run_path(str(ruta), run_name="__main__")
    db.expire_all()
    conv = db.query(models.Conversation).filter_by(id=conv.id).one()
    assert conv.status == "closed"
    assert conv.cerrada_por_inactividad_at is not None
    assert conv.reclamos_abandono == 0


# ---------------------------------------------------------------------------
# 2.10: logs
# ---------------------------------------------------------------------------

def test_logs_sin_texto_ni_telefono(db, agencia, modelo, caplog):
    caplog.set_level(logging.DEBUG)
    _abandonada(db, agencia["team"], agencia["bot"])
    entra(db, agencia["team"], "Hola soy Marcela, mi cédula 1012345678")
    texto = caplog.text
    assert "reenganche.reclamado" in texto
    assert WA not in texto
    assert "1012345678" not in texto and "Marcela" not in texto
    assert "Camila" not in texto     # el nombre de la asesora tampoco
