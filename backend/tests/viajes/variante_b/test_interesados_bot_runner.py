"""Los enganches de Interesados en `bot_runner` (bot 2, estrategias #11, #22, #28).

Lo que se cuida, en orden de importancia:

  1. **Sin flags, nada cambia.** El bot 1 no lleva `intencion_compra`,
     `presentacion_una_vez` ni `recordatorios_con_contexto`: su runtime es el
     de siempre, no se escribe nada en `intenciones_compra` y los recordatorios
     salen con el texto fijo y a la misma hora (`TestSinFlags`; el golden
     `tests/viajes/test_bot1_sin_cambios.py` lo vigila además carácter a
     carácter).
  2. **El registro del episodio** une regex y herramienta en UNA fila por
     sesión, con lista blanca de tipos y textos saneados, y nunca tumba el
     turno (`TestRegistro`).
  3. **`ya_se_presento`** mira cualquier sesión anterior del mismo chat, no
     solo la ventana `retomar` (`TestYaSePresento`).
  4. **Si una persona toma el chat mientras el modelo piensa**, lo que el bot
     redactó no sale (`TestCambioDeDueno`).
  5. **Recordatorio con contexto** con su respaldo al texto fijo
     (`TestRecordatorioConContexto`).

El modelo no se invoca: `llm_engine.advance` está reemplazado por un motor
guionado (ver `test_interesados_andamiaje.MotorFalso`).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import pytest

from app import crud, models
from app.data.bot_viajes import LLM_CONFIG
from app.services import agendamientos, bot_runner

from .test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    MotorFalso,
    Sesion,
    config_bot2,
    conversacion,
    crear_agencia,
    db,
    mensaje,
    motor,
    sesion_bot,
)

#: Las llaves del runtime que `bot_runner` le pasa hoy al motor (commit
#: 7835c65). Sin flags no puede aparecer ninguna otra.
LLAVES_RUNTIME_BOT1 = {
    "bot_id", "source", "conversation_id", "contact_name", "retomada", "desde",
}


def turno(db, ag, conv, texto, session=None):
    return bot_runner.run_turn(
        db, bot=ag["bot"], conversation=conv, session=session,
        user_input=texto, meta_account=None,
    )


def filas(db):
    return db.query(models.IntencionCompra).order_by(models.IntencionCompra.id).all()


def enviados(db, conv):
    return [
        m.content for m in db.query(models.Message)
        .filter(models.Message.conversation_id == conv.id,
                models.Message.direction == "outbound",
                models.Message.message_type != "nota_interna")
        .order_by(models.Message.id)
    ]


# ---------------------------------------------------------------------------
# 1. Sin flags
# ---------------------------------------------------------------------------

class TestSinFlags:
    def test_el_bot_1_no_registra_ni_cambia_el_runtime(self, db, motor):
        ag = crear_agencia(db, sufijo="SF1", cfg=json.loads(json.dumps(LLM_CONFIG)))
        conv = conversacion(db, ag["team"])
        motor.turno(intenciones=[{"tipo": "reservar", "resumen": "quiere reservar"}])
        motor.turno()
        s = turno(db, ag, conv, "Hola, quiero reservar, ¿cuánto es el anticipo?")
        turno(db, ag, conv, "somos 2 adultos, el 16 de diciembre", session=s)

        assert filas(db) == []
        for rt in motor.runtimes:
            assert set(rt) == LLAVES_RUNTIME_BOT1

    def test_sin_flag_no_se_consulta_la_tabla(self, db, motor, monkeypatch):
        ag = crear_agencia(db, sufijo="SF2", cfg=json.loads(json.dumps(LLM_CONFIG)))
        conv = conversacion(db, ag["team"])

        def prohibido(*a, **k):  # pragma: no cover - si se llama, falla
            raise AssertionError("registrar_intencion no debe correr sin flag")

        monkeypatch.setattr(agendamientos, "registrar_intencion", prohibido)
        turno(db, ag, conv, "quiero reservar")

    def test_sin_flag_el_recordatorio_es_el_fijo(self, db, motor, monkeypatch):
        cfg = json.loads(json.dumps(LLM_CONFIG))
        cfg["seguimiento"]["recordatorios"][0]["plantilla"] = "Hola {nombre}"
        ag = crear_agencia(db, sufijo="SF3", cfg=cfg)
        conv = conversacion(db, ag["team"])
        from app.services import recordatorios_contexto

        llamado = []
        monkeypatch.setattr(
            recordatorios_contexto, "texto_recordatorio",
            lambda *a, **k: llamado.append(1) or "NO DEBE SALIR",
        )
        s = turno(db, ag, conv, "hola")
        pa = _pendiente(db, s)
        bot_runner.process_pending_action(db, pa)
        assert llamado == []
        assert enviados(db, conv)[-1] == LLM_CONFIG["seguimiento"]["recordatorios"][0]["texto"]


# ---------------------------------------------------------------------------
# 2. Registro del episodio
# ---------------------------------------------------------------------------

class TestRegistro:
    def test_la_regex_crea_la_fila_del_episodio(self, db, motor):
        ag = crear_agencia(db, sufijo="R1")
        conv = conversacion(db, ag["team"])
        s = turno(db, ag, conv, "¿Cuánto es el anticipo para separar? mi cel 300 000 0000")

        [f] = filas(db)
        assert f.session_id == s.id and f.conversation_id == conv.id
        assert f.team_id == ag["team"].id and f.bot_id == ag["bot"].id
        assert f.tipos == ["anticipo"]
        assert f.origen == models.INTENCION_ORIGEN_REGEX
        assert f.estado == models.INTENCION_POR_CONTACTAR
        assert "300" not in f.fragmento and "[número]" in f.fragmento
        assert f.visible_desde == s.started_at + timedelta(hours=6)

    def test_la_herramienta_y_la_regex_se_unen_en_una_sola_fila(self, db, motor):
        ag = crear_agencia(db, sufijo="R2")
        conv = conversacion(db, ag["team"])
        motor.turno(intenciones=[])
        motor.turno(intenciones=[{"tipo": "reservar",
                                  "resumen": "Quiere reservar dic; correo x@example.com"}])
        motor.turno(intenciones=[])
        s = turno(db, ag, conv, "el 16 de diciembre")
        turno(db, ag, conv, "ok perfecto", session=s)
        turno(db, ag, conv, "somos 3 adultos", session=s)

        [f] = filas(db)
        assert f.tipos == ["reservar", "fecha_concreta", "datos"]
        assert f.origen == models.INTENCION_ORIGEN_AMBOS
        # La primera frase que la delató es la que se queda.
        assert f.fragmento == "el 16 de diciembre"
        assert f.resumen == "Quiere reservar dic; correo [correo]"

    def test_lista_blanca_y_tope_de_tipos(self, db, motor):
        ag = crear_agencia(db, sufijo="R3")
        conv = conversacion(db, ag["team"])
        motor.turno(intenciones=[
            {"tipo": "comprar_ya"}, {"tipo": "datos_entregados"}, "reservar",
            {"tipo": "datos", "resumen": "x" * 900}, {"tipo": None},
        ])
        turno(db, ag, conv, "ok")
        [f] = filas(db)
        assert f.tipos == ["datos"]
        assert f.origen == models.INTENCION_ORIGEN_HERRAMIENTA
        assert len(f.resumen) == 300 and f.fragmento is None

    def test_telemetria_rara_no_rompe_nada(self, db, motor):
        ag = crear_agencia(db, sufijo="R4")
        conv = conversacion(db, ag["team"])
        motor.turno(intenciones="reservar")       # no es lista
        turno(db, ag, conv, "hola")
        assert filas(db) == []

    def test_un_fallo_al_guardar_no_tumba_el_turno_ni_filtra_datos(
        self, db, motor, monkeypatch, caplog
    ):
        ag = crear_agencia(db, sufijo="R5")
        conv = conversacion(db, ag["team"])

        def revienta(_db):
            raise RuntimeError("valores: quiero reservar el 16 de diciembre")

        monkeypatch.setattr(agendamientos, "_insert_de", revienta)
        motor.turno("¡Claro! Te cuento 🌴")
        with caplog.at_level(logging.INFO):
            turno(db, ag, conv, "quiero reservar el 16 de diciembre")

        assert filas(db) == []
        assert enviados(db, conv) == ["¡Claro! Te cuento 🌴"]
        assert "diciembre" not in caplog.text and "reservar el" not in caplog.text
        assert "RuntimeError" in caplog.text

    def test_episodio_nuevo_es_fila_nueva(self, db, motor):
        ag = crear_agencia(db, sufijo="R6")
        conv = conversacion(db, ag["team"])
        s1 = turno(db, ag, conv, "quiero reservar")
        s1.status = models.BOT_SESSION_FINISHED
        db.commit()
        s2 = turno(db, ag, conv, "quiero reservar otra vez")
        assert s2.id != s1.id
        assert [f.session_id for f in filas(db)] == [s1.id, s2.id]

    @pytest.mark.parametrize(
        "valor, horas",
        [(2, 2.0), (0, 0.0), (72, 72.0), (100, 6.0), (-1, 6.0), ("abc", 6.0),
         (float("nan"), 6.0), (None, 6.0)],
    )
    def test_el_umbral_se_acota(self, valor, horas):
        cfg = {"intencion_compra": {"horas_para_interesado": valor}}
        assert agendamientos.horas_para_interesado(cfg) == horas

    def test_flag_en_true_usa_el_umbral_por_defecto(self):
        assert agendamientos.config_intencion({"intencion_compra": True}) == {}
        assert agendamientos.horas_para_interesado({"intencion_compra": True}) == 6.0
        assert agendamientos.config_intencion({"intencion_compra": False}) is None
        assert agendamientos.config_intencion({}) is None


# ---------------------------------------------------------------------------
# 3. ya_se_presento
# ---------------------------------------------------------------------------

class TestYaSePresento:
    def test_primer_contacto_no_se_ha_presentado(self, db, motor):
        ag = crear_agencia(db, sufijo="P1")
        conv = conversacion(db, ag["team"])
        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                            user_input=None, meta_account=None)
        assert motor.runtimes[-1]["ya_se_presento"] is False

    def test_sesion_anterior_fuera_de_la_ventana_retomar_cuenta(self, db, motor):
        ag = crear_agencia(db, sufijo="P2")
        conv = conversacion(db, ag["team"])
        hace_un_mes = datetime.utcnow() - timedelta(days=30)
        sesion_bot(db, ag["bot"], conv, hace_un_mes, status=models.BOT_SESSION_FINISHED)
        mensaje(db, conv, "outbound", "¡Hola! Soy Luisa…", hace_un_mes + timedelta(minutes=1))

        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                            user_input=None, meta_account=None)
        assert motor.runtimes[-1]["ya_se_presento"] is True

    @pytest.mark.parametrize(
        "kw",
        [
            {"status": "failed"},                 # nunca le llegó
            {"tipo": "nota_interna"},             # no viaja al cliente
            {"tipo": "template"},                 # una campaña no es el bot
            {"por": "ASESORA"},                   # lo escribió una persona
        ],
    )
    def test_lo_que_no_es_el_bot_hablando_no_cuenta(self, db, motor, kw):
        ag = crear_agencia(db, sufijo="P3")
        conv = conversacion(db, ag["team"])
        antes = datetime.utcnow() - timedelta(days=3)
        sesion_bot(db, ag["bot"], conv, antes, status=models.BOT_SESSION_FINISHED)
        if kw.get("por") == "ASESORA":
            kw = {"por": ag["asesora"].id}
        mensaje(db, conv, "outbound", "algo", antes + timedelta(minutes=1), **kw)

        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                            user_input=None, meta_account=None)
        assert motor.runtimes[-1]["ya_se_presento"] is False

    def test_la_sesion_de_otro_bot_no_cuenta(self, db, motor):
        ag = crear_agencia(db, sufijo="P4")
        otro = models.Bot(user_id=ag["duenio"].id, team_id=ag["team"].id, name="Bot A",
                          engine="llm", status="active", llm_config=json.dumps(LLM_CONFIG))
        db.add(otro)
        db.commit()
        conv = conversacion(db, ag["team"])
        antes = datetime.utcnow() - timedelta(days=3)
        sesion_bot(db, otro, conv, antes, status=models.BOT_SESSION_FINISHED)
        mensaje(db, conv, "outbound", "Soy otra asesora", antes + timedelta(minutes=1))

        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                            user_input=None, meta_account=None)
        assert motor.runtimes[-1]["ya_se_presento"] is False

    @pytest.mark.parametrize("flags, tiene_llave", [
        ({"presentacion_una_vez": True}, True),
        ({"apertura_vitrina": True}, True),
        ({}, False),
    ])
    def test_solo_con_sus_flags_va_la_llave(self, db, motor, flags, tiene_llave):
        cfg = json.loads(json.dumps(LLM_CONFIG))
        cfg.update(flags)
        ag = crear_agencia(db, sufijo="P6" + "".join(sorted(flags))[:6], cfg=cfg)
        conv = conversacion(db, ag["team"])
        turno(db, ag, conv, "hola")
        assert ("ya_se_presento" in motor.runtimes[-1]) is tiene_llave

    def test_dentro_de_la_misma_sesion_ya_se_presento(self, db, motor):
        ag = crear_agencia(db, sufijo="P5")
        conv = conversacion(db, ag["team"])
        s = turno(db, ag, conv, "hola")
        turno(db, ag, conv, "y cuánto vale", session=s)
        assert [rt["ya_se_presento"] for rt in motor.runtimes] == [False, True]


# ---------------------------------------------------------------------------
# 4. Una persona toma el chat mientras el modelo piensa
# ---------------------------------------------------------------------------

class TestCambioDeDueno:
    def test_lo_que_redacto_el_bot_no_sale(self, db, Sesion, motor):
        ag = crear_agencia(db, sufijo="C1")
        conv = conversacion(db, ag["team"])
        s = turno(db, ag, conv, "hola")
        antes = enviados(db, conv)

        def toma_otra_persona():
            otra = Sesion()   # otra conexión, como el request de la asesora
            assert crud.asignar_si_sigue(
                otra, conversation_id=conv.id, team_id=ag["team"].id,
                esperado="bot", destino="Sofía",
            )
            otra.commit()
            otra.close()

        motor.durante = toma_otra_persona
        motor.turno("Esto ya no debe salir",
                    extra_actions=[{"type": "handoff", "payload": {"text": "te paso"}}])
        turno(db, ag, conv, "quiero reservar", session=s)

        db.refresh(conv)
        assert conv.assigned_to == "Sofía"
        assert enviados(db, conv) == antes
        # El historial sí se guarda.
        db.refresh(s)
        assert "Esto ya no debe salir" in (s.state or "")

    def test_el_handoff_normal_sigue_igual(self, db, motor):
        ag = crear_agencia(db, sufijo="C2")
        conv = conversacion(db, ag["team"])
        motor.turno("Te paso con un asesor", finished=True, extra_actions=[
            {"type": "handoff", "payload": {"text": "", "resumen": "Quiere reservar"}},
        ])
        turno(db, ag, conv, "quiero hablar con alguien")
        db.refresh(conv)
        assert conv.assigned_to == "Camila" and conv.status == "pending"
        notas = db.query(models.Message).filter(
            models.Message.conversation_id == conv.id,
            models.Message.message_type == "nota_interna").all()
        assert len(notas) == 1 and notas[0].sent_by_user_id is None

    def test_compara_y_asigna(self, db):
        ag = crear_agencia(db, sufijo="C3")
        conv = conversacion(db, ag["team"])
        assert crud.asignar_si_sigue(db, conversation_id=conv.id, team_id=ag["team"].id,
                                     esperado="bot", destino="Sofía")
        db.commit()
        assert not crud.asignar_si_sigue(db, conversation_id=conv.id, team_id=ag["team"].id,
                                         esperado="bot", destino="Julián")
        # Otro team no puede, aunque adivine el id.
        otra = crear_agencia(db, sufijo="C3b")
        assert not crud.asignar_si_sigue(db, conversation_id=conv.id, team_id=otra["team"].id,
                                         esperado="Sofía", destino="X")
        db.refresh(conv)
        assert conv.assigned_to == "Sofía" and conv.status == "pending"


# ---------------------------------------------------------------------------
# 5. Recordatorio con contexto (#28)
# ---------------------------------------------------------------------------

def _pendiente(db, session):
    return (
        db.query(models.BotPendingAction)
        .filter(models.BotPendingAction.session_id == session.id,
                models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING)
        .one()
    )


def _cfg_con_plantillas():
    cfg = config_bot2(recordatorios_con_contexto=True)
    for i, etapa in enumerate(cfg["seguimiento"]["recordatorios"]):
        etapa["plantilla"] = f"Plantilla {i + 1} para {{nombre}}"
    return cfg


class TestRecordatorioConContexto:
    def test_usa_el_texto_con_contexto(self, db, motor, monkeypatch):
        from app.services import recordatorios_contexto

        ag = crear_agencia(db, sufijo="T1", cfg=_cfg_con_plantillas())
        conv = conversacion(db, ag["team"])
        recibido = {}

        def falso(db_, *, conversation, bot, cfg, etapa, hoy):
            recibido.update(conv=conversation.id, bot=bot.id, etapa=dict(etapa), hoy=hoy,
                            flag=cfg.get("recordatorios_con_contexto"))
            return "Valentina, quedan 2 salidas en diciembre 🌴"

        monkeypatch.setattr(recordatorios_contexto, "texto_recordatorio", falso)
        s = turno(db, ag, conv, "hola")
        bot_runner.process_pending_action(db, _pendiente(db, s))

        assert enviados(db, conv)[-1] == "Valentina, quedan 2 salidas en diciembre 🌴"
        assert recibido["etapa"]["plantilla"] == "Plantilla 1 para {nombre}"
        assert recibido["conv"] == conv.id and recibido["flag"] is True
        # Queda en el historial, como el fijo.
        db.refresh(s)
        assert "quedan 2 salidas" in s.state

    @pytest.mark.parametrize("comportamiento", ["none", "vacio", "error"])
    def test_sin_datos_o_con_error_sale_el_fijo(self, db, motor, monkeypatch, comportamiento):
        from app.services import recordatorios_contexto

        ag = crear_agencia(db, sufijo="T2" + comportamiento, cfg=_cfg_con_plantillas())
        conv = conversacion(db, ag["team"])

        def falso(*a, **k):
            if comportamiento == "error":
                raise RuntimeError("se cayó")
            return None if comportamiento == "none" else "   "

        monkeypatch.setattr(recordatorios_contexto, "texto_recordatorio", falso)
        s = turno(db, ag, conv, "hola")
        bot_runner.process_pending_action(db, _pendiente(db, s))
        assert enviados(db, conv)[-1] == LLM_CONFIG["seguimiento"]["recordatorios"][0]["texto"]

    def test_los_tiempos_no_cambian(self, db, motor, monkeypatch):
        """Mismos minutos de la cadena con y sin el flag (solo cambia el texto)."""
        from app.services import recordatorios_contexto

        monkeypatch.setattr(recordatorios_contexto, "texto_recordatorio",
                            lambda *a, **k: "texto con contexto")

        def cadena(sufijo, cfg):
            ag = crear_agencia(db, sufijo=sufijo, cfg=cfg)
            conv = conversacion(db, ag["team"], wa_id="5730000003" + sufijo[-2:])
            s = turno(db, ag, conv, "hola")
            difs = []
            for _ in range(len(LLM_CONFIG["seguimiento"]["recordatorios"])):
                pa = _pendiente(db, s)
                difs.append(round((pa.scheduled_at - pa.created_at).total_seconds() / 60))
                bot_runner.process_pending_action(db, pa)
            pa = _pendiente(db, s)
            difs.append((pa.action_type, round((pa.scheduled_at - pa.created_at).total_seconds() / 60)))
            return difs

        sin = cadena("TA01", json.loads(json.dumps(LLM_CONFIG)))
        con = cadena("TB02", _cfg_con_plantillas())
        assert sin == con

    def test_la_plantilla_solo_se_hereda_del_json_si_la_etapa_es_del_json(self):
        seg = {"recordatorios": [{"minutos": 15, "texto": "fijo", "plantilla": "P {nombre}"}]}
        assert bot_runner._plantilla_de(seg, {"minutos": 15, "texto": "fijo"}) == "P {nombre}"
        # Etapa que vino de `bot_recordatorios` (otro texto): no hereda.
        assert bot_runner._plantilla_de(seg, {"minutos": 15, "texto": "de la tabla"}) is None
        # Si el motor algún día la pasa en la etapa, manda esa.
        assert bot_runner._plantilla_de(seg, {"minutos": 15, "texto": "x", "plantilla": "Q"}) == "Q"


def test_el_abandono_no_le_quita_el_chat_a_quien_lo_tomo_en_ese_instante(db, Sesion, motor, monkeypatch):
    """Auditoría de seguridad (M1): `_asesor_para_el_abandono` puede hacer
    commit (reparto con 2+ asesores) y, con expire_on_commit, el compara-y-asigna
    leía como "esperado" el dueño ACTUAL — si una asesora tomaba el chat desde
    Interesados en ese instante, el abandono se lo quitaba."""
    ag = crear_agencia(db, sufijo="M1")
    conv = conversacion(db, ag["team"])
    s = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                            user_input="hola", meta_account=None)
    bot_runner._programar(db, s, models.BOT_PENDING_ACTION_ABANDONO, 1)
    db.commit()
    pa = (
        db.query(models.BotPendingAction)
        .filter_by(session_id=s.id, action_type=models.BOT_PENDING_ACTION_ABANDONO)
        .first()
    )
    assert pa is not None

    original = crud.siguiente_asesor

    def con_toma_concurrente(db_, team):
        otra = Sesion()  # la asesora toma el chat justo ahora
        assert crud.asignar_si_sigue(otra, conversation_id=conv.id, team_id=ag["team"].id,
                                     esperado="bot", destino="Sofía")
        otra.commit()
        otra.close()
        return original(db_, team)

    monkeypatch.setattr(crud, "siguiente_asesor", con_toma_concurrente)
    bot_runner._procesar_silencio(db, pa)
    db.refresh(conv)
    assert conv.assigned_to == "Sofía"
