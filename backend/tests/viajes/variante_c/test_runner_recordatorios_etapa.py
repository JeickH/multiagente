"""Bot 3 (variante C): recordatorios por etapa del embudo (`recordatorios_por_etapa`).

Lo que se cuida:

  1. **El texto sale de la etapa** que el motor dejó en `session.state["etapa"]`
     y de la posición en la cadena (15 min / 5 h / 23 h).
  2. **Los tiempos, la cadena y el abandono son los del bot 1**: misma
     programación minuto a minuto, mismo traspaso a la asesora al final, y al
     cliente no se le escribe nada en el abandono.
  3. **Respaldo al texto fijo** cuando no hay etapa, la etapa no tiene textos,
     falta la posición, el texto está vacío o la etapa es de traspaso
     (`comprobante`, `asesor`).
  4. **El bot 2 no cambia**: `recordatorios_con_contexto` sigue igual y una
     etapa en el estado no le cambia nada a un bot sin el flag.

El modelo no se invoca (motor guionado del andamiaje de Interesados). Textos
inventados; ningún dato real (regla #8).
"""
from __future__ import annotations

import json

import pytest

from app import models
from app.data.bot_viajes import LLM_CONFIG
from app.services import bot_runner

from ..variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    conversacion,
    crear_agencia,
    db,
    motor,
)

FIJOS = [r["texto"] for r in LLM_CONFIG["seguimiento"]["recordatorios"]]

POR_ETAPA = {
    "bienvenida": ["B1 ¿qué mes te sirve? 1️⃣ 2️⃣", "B2 te muestro los meses", "B3 última"],
    "fecha": ["F1 ¿cuál salida? 1️⃣ 2️⃣", "F2 quedan pocas salidas", "F3 aquí sigo"],
    "pago": ["P1 ¿pudiste hacer el anticipo?"],          # solo el primero
    "cotizacion": ["", "C2 ¿reservamos?", None],           # vacío y None → fijo
    "comprobante": ["NO", "NO", "NO"],
    "asesor": ["NO", "NO", "NO"],
}


def cfg_bot3(**extra):
    cfg = json.loads(json.dumps(LLM_CONFIG))
    cfg["recordatorios_por_etapa"] = json.loads(json.dumps(POR_ETAPA))
    cfg.update(extra)
    return cfg


def enviados(db, conv):
    return [
        m.content for m in db.query(models.Message)
        .filter(models.Message.conversation_id == conv.id,
                models.Message.direction == "outbound",
                models.Message.message_type != "nota_interna")
        .order_by(models.Message.id)
    ]


def _pendiente(db, session):
    return (
        db.query(models.BotPendingAction)
        .filter(models.BotPendingAction.session_id == session.id,
                models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING)
        .one()
    )


def cadena(db, motor, *, sufijo, cfg, etapa=None, wa="573000000600"):
    """Un turno que deja la sesión en `etapa`, y la cadena completa de
    silencio: los recordatorios enviados y los minutos de cada acción."""
    ag = crear_agencia(db, sufijo=sufijo, cfg=cfg)
    conv = conversacion(db, ag["team"], wa_id=wa)
    motor.turno("¡Hola! Te cuento del plan 🌴")
    if etapa is not None:
        motor.guion[-1]["next_state"]["etapa"] = etapa
    s = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                            user_input="Hola, quiero más información", meta_account=None)
    respuesta = len(enviados(db, conv))
    tiempos = []
    for _ in FIJOS:
        pa = _pendiente(db, s)
        tiempos.append((pa.action_type, round((pa.scheduled_at - pa.created_at).total_seconds() / 60)))
        bot_runner.process_pending_action(db, pa)
    pa = _pendiente(db, s)
    tiempos.append((pa.action_type, round((pa.scheduled_at - pa.created_at).total_seconds() / 60)))
    return ag, conv, s, enviados(db, conv)[respuesta:], tiempos, pa


class TestTextoPorEtapa:
    @pytest.mark.parametrize("etapa", ["bienvenida", "fecha"])
    def test_los_tres_salen_de_la_etapa(self, db, motor, etapa):
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo="E" + etapa[:3], cfg=cfg_bot3(), etapa=etapa)
        assert salieron == POR_ETAPA[etapa]

    def test_falta_la_posicion_sale_el_fijo(self, db, motor):
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo="EP", cfg=cfg_bot3(), etapa="pago")
        assert salieron == [POR_ETAPA["pago"][0], FIJOS[1], FIJOS[2]]

    def test_texto_vacio_o_nulo_sale_el_fijo(self, db, motor):
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo="EC", cfg=cfg_bot3(), etapa="cotizacion")
        assert salieron == [FIJOS[0], "C2 ¿reservamos?", FIJOS[2]]

    @pytest.mark.parametrize("etapa", [None, "reserva", "inventada", 7, ""])
    def test_sin_etapa_o_sin_textos_sale_el_fijo(self, db, motor, etapa):
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo=f"EN{etapa!s:.3}", cfg=cfg_bot3(), etapa=etapa)
        assert salieron == FIJOS

    @pytest.mark.parametrize("etapa", ["comprobante", "asesor"])
    def test_en_etapas_de_traspaso_no_aplica(self, db, motor, etapa):
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo="ET" + etapa[:3], cfg=cfg_bot3(), etapa=etapa)
        assert salieron == FIJOS

    @pytest.mark.parametrize("valor", [True, ["fecha"], "fecha"])
    def test_flag_mal_formado_sale_el_fijo(self, db, motor, valor):
        cfg = cfg_bot3()
        cfg["recordatorios_por_etapa"] = valor
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo=f"EM{type(valor).__name__[:3]}",
                                         cfg=cfg, etapa="fecha")
        assert salieron == FIJOS


class TestMismosTiemposYAbandono:
    def test_misma_cadena_que_el_bot_1(self, db, motor):
        *_, tiempos_bot1, _ = cadena(db, motor, sufijo="T1",
                                     cfg=json.loads(json.dumps(LLM_CONFIG)), wa="573000000601")
        *_, tiempos_bot3, _ = cadena(db, motor, sufijo="T3", cfg=cfg_bot3(),
                                     etapa="fecha", wa="573000000603")
        assert tiempos_bot3 == tiempos_bot1
        assert [t[0] for t in tiempos_bot3] == (
            [models.BOT_PENDING_ACTION_SEGUIMIENTO] * len(FIJOS) + [models.BOT_PENDING_ACTION_ABANDONO]
        )

    def test_el_abandono_traspasa_a_la_asesora_sin_escribirle_al_cliente(self, db, motor):
        ag, conv, s, salieron, _, abandono = cadena(db, motor, sufijo="AB", cfg=cfg_bot3(), etapa="fecha")
        antes = enviados(db, conv)
        bot_runner.process_pending_action(db, abandono)
        db.refresh(conv)
        db.refresh(s)
        assert conv.assigned_to in ("Camila", "Julián") and conv.status == "pending"
        assert s.status == models.BOT_SESSION_FINISHED
        assert enviados(db, conv) == antes
        notas = db.query(models.Message).filter(
            models.Message.conversation_id == conv.id,
            models.Message.message_type == "nota_interna").all()
        assert len(notas) == 1

    def test_si_la_persona_contesta_no_sale_el_recordatorio(self, db, motor):
        from app import crud

        ag = crear_agencia(db, sufijo="RC", cfg=cfg_bot3())
        conv = conversacion(db, ag["team"], wa_id="573000000604")
        motor.turno("¿Qué mes te sirve? 1️⃣ Octubre 2️⃣ Noviembre")
        motor.guion[-1]["next_state"]["etapa"] = "bienvenida"
        s = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                                user_input="Hola", meta_account=None)
        pa = _pendiente(db, s)
        crud.add_message(db, conv, direction="inbound", content="2", status="received")
        antes = enviados(db, conv)
        bot_runner.process_pending_action(db, pa)
        assert enviados(db, conv) == antes


class TestBot2Intacto:
    def test_con_contexto_sigue_igual_y_no_lee_la_etapa(self, db, motor, monkeypatch):
        from app.services import recordatorios_contexto

        cfg = json.loads(json.dumps(LLM_CONFIG))
        cfg["recordatorios_con_contexto"] = True
        for i, r in enumerate(cfg["seguimiento"]["recordatorios"]):
            r["plantilla"] = f"Plantilla {i}"
        monkeypatch.setattr(recordatorios_contexto, "texto_recordatorio",
                            lambda *a, **k: "con contexto")
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo="B2", cfg=cfg, etapa="fecha")
        assert salieron == ["con contexto"] * len(FIJOS)

    def test_sin_el_flag_la_etapa_en_el_estado_no_cambia_nada(self, db, motor):
        _, _, _, salieron, _, _ = cadena(db, motor, sufijo="B1",
                                         cfg=json.loads(json.dumps(LLM_CONFIG)), etapa="fecha")
        assert salieron == FIJOS


def test_helper_puro():
    s = models.BotSession(state=json.dumps({"etapa": "fecha", "history": []}))
    cfg = {"recordatorios_por_etapa": POR_ETAPA}
    assert [bot_runner._texto_por_etapa(cfg, s, i) for i in range(4)] == POR_ETAPA["fecha"] + [None]
    assert bot_runner._texto_por_etapa(cfg, s, -1) is None
    assert bot_runner._texto_por_etapa(cfg, models.BotSession(state=None), 0) is None
    assert bot_runner._texto_por_etapa(cfg, models.BotSession(state="{roto"), 0) is None
