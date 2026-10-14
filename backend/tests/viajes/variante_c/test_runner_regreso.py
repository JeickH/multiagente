"""Bot 3: contexto de regreso (`contexto_de_regreso_y_hora`).

Quien vuelve en una sesión NUEVA (fuera de la ventana `retomar`) trae de la
sesión anterior, en el runtime: `etapa_previa` (el `state["etapa"]` que dejó el
motor) y `ultimo_mes` / `ultimo_hotel` (la última consulta de precios del bot
en esa conversación). Solo datos del plan; el motor los valida.

Para los bots 1 y 2 el runtime no cambia. Datos inventados (regla #8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app import models
from app.data.bot_viajes import LLM_CONFIG
from app.services import bot_runner, llm_engine

from ..variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    conversacion,
    crear_agencia,
    db,
    mensaje,
    motor,
)

LLAVES_BOT1 = {"bot_id", "source", "conversation_id", "contact_name", "retomada", "desde"}
LLAVES_REGRESO = {"etapa_previa", "ultimo_mes", "ultimo_hotel"}


def cfg_bot3(**extra):
    cfg = json.loads(json.dumps(LLM_CONFIG))
    cfg["contexto_de_regreso_y_hora"] = True
    cfg.update(extra)
    return cfg


def episodio_anterior(db, ag, conv, *, etapa="cotizacion", entrada=None, bot=None, dias=3):
    """Una sesión cerrada hace `dias` días, en la que el bot habló y consultó."""
    bot = bot or ag["bot"]
    antes = datetime.utcnow() - timedelta(days=dias)
    estado = {"history": [{"role": "assistant", "content": "¡Hola! Soy Luisa…"}]}
    if etapa is not None:
        estado["etapa"] = etapa
    s = models.BotSession(bot_id=bot.id, conversation_id=conv.id,
                          status=models.BOT_SESSION_FINISHED, state=json.dumps(estado),
                          started_at=antes, updated_at=antes)
    db.add(s)
    db.commit()
    mensaje(db, conv, "outbound", "¡Hola! Soy Luisa…", antes + timedelta(minutes=1))
    if entrada is not None:
        db.add(models.BotLlmDecision(
            bot_id=bot.id, session_id=s.id, conversation_id=conv.id, source="whatsapp",
            tools_called=json.dumps([{"tool": "consultar_precios", "input": entrada,
                                      "resultado": "..."}]),
            created_at=antes + timedelta(minutes=2),
        ))
        db.commit()
    return s


def sesion_nueva(db, ag, conv, user_input=None):
    """Como el webhook fuera de `retomar`: sesión nueva, sin texto."""
    return bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                               user_input=user_input, meta_account=None)


class TestRegreso:
    def test_trae_etapa_mes_y_hotel_de_la_sesion_anterior(self, db, motor):
        ag = crear_agencia(db, sufijo="RG1", cfg=cfg_bot3())
        conv = conversacion(db, ag["team"])
        episodio_anterior(db, ag, conv, entrada={"mes": "diciembre", "variante": "Piedra Mar"})
        sesion_nueva(db, ag, conv)
        rt = motor.runtimes[-1]
        assert rt["ya_se_presento"] is True
        assert {k: rt[k] for k in LLAVES_REGRESO} == {
            "etapa_previa": "cotizacion", "ultimo_mes": "diciembre", "ultimo_hotel": "Piedra Mar",
        }

    def test_solo_fecha_se_traduce_a_nombre_de_mes(self, db, motor):
        ag = crear_agencia(db, sufijo="RG2", cfg=cfg_bot3())
        conv = conversacion(db, ag["team"])
        episodio_anterior(db, ag, conv, entrada={"fecha": "2026-12-16", "hotel": "Amor de Dios"})
        sesion_nueva(db, ag, conv)
        rt = motor.runtimes[-1]
        assert rt["ultimo_mes"] == "diciembre" and rt["ultimo_hotel"] == "Amor de Dios"

    def test_toma_la_ultima_sesion_y_solo_las_llaves_con_dato(self, db, motor):
        ag = crear_agencia(db, sufijo="RG3", cfg=cfg_bot3())
        conv = conversacion(db, ag["team"])
        episodio_anterior(db, ag, conv, etapa="mes", dias=10)
        episodio_anterior(db, ag, conv, etapa=None, dias=2)      # la última, sin etapa
        sesion_nueva(db, ag, conv)
        rt = motor.runtimes[-1]
        assert rt["ya_se_presento"] is True
        assert LLAVES_REGRESO.isdisjoint(rt)

    def test_la_consulta_de_otro_bot_no_cuenta(self, db, motor):
        ag = crear_agencia(db, sufijo="RG4", cfg=cfg_bot3())
        otro = models.Bot(user_id=ag["duenio"].id, team_id=ag["team"].id, name="Bot A",
                          engine="llm", status="active", llm_config=json.dumps(LLM_CONFIG))
        db.add(otro)
        db.commit()
        conv = conversacion(db, ag["team"])
        episodio_anterior(db, ag, conv, etapa="fecha")
        episodio_anterior(db, ag, conv, etapa="pago", bot=otro,
                          entrada={"mes": "enero", "hotel": "Bohíos"}, dias=1)
        sesion_nueva(db, ag, conv)
        rt = motor.runtimes[-1]
        assert rt["etapa_previa"] == "fecha"
        assert "ultimo_mes" not in rt and "ultimo_hotel" not in rt

    def test_primer_contacto_no_trae_nada(self, db, motor):
        ag = crear_agencia(db, sufijo="RG5", cfg=cfg_bot3())
        conv = conversacion(db, ag["team"])
        sesion_nueva(db, ag, conv)
        rt = motor.runtimes[-1]
        assert rt["ya_se_presento"] is False and LLAVES_REGRESO.isdisjoint(rt)

    def test_dentro_de_la_misma_sesion_no_se_repite(self, db, motor):
        ag = crear_agencia(db, sufijo="RG6", cfg=cfg_bot3())
        conv = conversacion(db, ag["team"])
        episodio_anterior(db, ag, conv, entrada={"mes": "diciembre"})
        s = sesion_nueva(db, ag, conv)
        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=s,
                            user_input="2", meta_account=None)
        assert "ultimo_mes" in motor.runtimes[0]
        assert LLAVES_REGRESO.isdisjoint(motor.runtimes[1])

    def test_un_error_no_tumba_el_turno(self, db, motor, monkeypatch):
        from app.services import recordatorios_contexto

        ag = crear_agencia(db, sufijo="RG7", cfg=cfg_bot3())
        conv = conversacion(db, ag["team"])
        episodio_anterior(db, ag, conv)

        def revienta(*a, **k):
            raise RuntimeError("bd caída")

        monkeypatch.setattr(recordatorios_contexto, "_ultima_consulta", revienta)
        sesion_nueva(db, ag, conv)
        assert LLAVES_REGRESO.isdisjoint(motor.runtimes[-1])


class TestBots1y2NoCambian:
    @pytest.mark.parametrize("extra, llaves", [
        ({}, LLAVES_BOT1),
        ({"presentacion_una_vez": True, "intencion_compra": {"horas_para_interesado": 6}},
         LLAVES_BOT1 | {"ya_se_presento"}),
    ])
    def test_runtime(self, db, motor, extra, llaves):
        cfg = json.loads(json.dumps(LLM_CONFIG))
        cfg.update(extra)
        ag = crear_agencia(db, sufijo="NC" + str(len(extra)), cfg=cfg)
        conv = conversacion(db, ag["team"])
        episodio_anterior(db, ag, conv, entrada={"mes": "diciembre", "hotel": "Piedra Mar"})
        sesion_nueva(db, ag, conv)
        assert set(motor.runtimes[-1]) == llaves


def test_el_motor_lo_pone_en_el_prompt(db, monkeypatch):
    """De punta a punta con el motor real: el bloque «Ya hablaron antes» lleva
    el mes y el hotel que trajo el runner."""
    vistos = []
    monkeypatch.setattr(llm_engine, "_invoke_model", lambda model_id, system, messages, tools: (
        vistos.append(system) or {"content": [{"type": "text", "text": "¡Hola de nuevo! 😊"}],
                                  "stop_reason": "end_turn",
                                  "usage": {"input_tokens": 1, "output_tokens": 1}}))
    ag = crear_agencia(db, sufijo="RG8", cfg=cfg_bot3(presentacion_una_vez=True))
    conv = conversacion(db, ag["team"])
    episodio_anterior(db, ag, conv, entrada={"mes": "diciembre", "variante": "Piedra Mar"})
    sesion_nueva(db, ag, conv)
    sistema = json.dumps(vistos[-1], ensure_ascii=False) if not isinstance(vistos[-1], str) else vistos[-1]
    assert "Ya hablaron antes" in sistema
    assert "diciembre" in sistema
