"""Con la `LLM_CONFIG` del bot 1 (`app/data/bot_viajes.py`), ningún enganche del
bot 2 se activa.

Regla de la spec: el bot 1 (id 12 en prod) no cambia de comportamiento. Aquí se
le ponen delante exactamente las situaciones que disparan cada enganche del bot
2 —aplazar, nombrar la promo, dos preguntas, un nombre genérico, el runtime de
«ya se presentó»— y se verifica que el turno sale como hoy. Además, las
funciones nuevas del módulo de precios se reemplazan por dobles que **revientan
si alguien las llama**: con el bot 1, nadie debe llamarlas.

El test golden de QA (`tests/viajes/test_bot1_sin_cambios.py`) compara turnos
completos contra una grabación; este fija el porqué, flag por flag.
"""
from __future__ import annotations

import json
import sys
import types
from unittest.mock import patch

import pytest

import app.services as servicios
from app.data import bot_natulce, bot_viajes
from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine, tarifario

FLAGS_DEL_BOT_2 = (
    "variante", "apertura_vitrina", "una_pregunta_por_turno",
    "presentacion_una_vez", "nombre_una_vez", "filtrar_nombres_genericos",
    "no_cerrar_aplazadas", "guardarrail_precio", "cargos_ninos",
    "promo_inexistente", "intencion_compra",
)


class Bot1:
    id = 12
    engine = "llm"
    status = "active"
    llm_config = json.dumps(LLM_CONFIG, ensure_ascii=False)


def _revienta(*_a, **_k):
    raise AssertionError("el bot 1 no debe llamar esto")


@pytest.fixture(autouse=True)
def nadie_llama_lo_nuevo(monkeypatch):
    for nombre in ("desde_temporada", "flyer_apertura", "linea_ninos",
                   "linea_extras", "extras"):
        monkeypatch.setattr(tarifario, nombre, _revienta, raising=False)
    modulo = types.ModuleType("app.services.guardarrail_precio")
    modulo.viola_precio = _revienta
    monkeypatch.setitem(sys.modules, "app.services.guardarrail_precio", modulo)
    monkeypatch.setattr(servicios, "guardarrail_precio", modulo, raising=False)
    from app.services import senales
    # Las señales de la variante tampoco se consultan sin sus flags.
    monkeypatch.setattr(senales, "es_aplazamiento", _revienta)
    monkeypatch.setattr(senales, "menciona_monto", _revienta)
    monkeypatch.setattr(senales, "es_nombre_generico", _revienta)
    monkeypatch.setattr(senales, "mes_mencionado", _revienta)
    monkeypatch.setattr(senales, "monto_mencionado", _revienta)
    monkeypatch.setattr(senales, "es_presupuesto", _revienta)


def jugar(respuestas, mensaje="Hola, quiero más información", estado=None, **runtime):
    with patch.object(llm_engine, "_invoke_model", side_effect=list(respuestas)):
        return llm_engine.advance(Bot1(), estado, mensaje, runtime=dict(runtime))


def resp(*bloques):
    con_tool = any(b["type"] == "tool_use" for b in bloques)
    return {"content": list(bloques), "stop_reason": "tool_use" if con_tool else "end_turn"}


def texto(t):
    return {"type": "text", "text": t}


def herramienta(nombre, entrada):
    return {"type": "tool_use", "id": "t1", "name": nombre, "input": entrada}


def dichos(salida):
    return [a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"]


ESTADO = {"history": [
    {"role": "user", "content": "¿cuánto vale octubre?"},
    {"role": "assistant", "content": "Desde $459.000 por persona 🌴 ¿A nombre de quién aparto el cupo?"},
]}


@pytest.mark.parametrize("config", [bot_viajes.LLM_CONFIG, bot_natulce.LLM_CONFIG])
def test_las_configs_versionadas_no_traen_flags_del_bot_2(config):
    assert not set(config) & set(FLAGS_DEL_BOT_2)


def test_las_herramientas_son_las_de_siempre():
    nombres = [t["name"] for t in llm_engine._tools_for(llm_engine.config_de(Bot1()))]
    assert "registrar_intencion" not in nombres


def test_el_prompt_del_primer_turno_no_trae_el_bloque_de_apertura():
    cfg = {**llm_engine.config_de(Bot1()), "_runtime": {}}
    assert "Datos para tu primer mensaje" not in llm_engine._system_prompt(Bot1(), cfg, [])


def test_el_primer_turno_no_lleva_flyer():
    salida = jugar([resp(texto("¡Hola! 😊 ¿Para qué mes lo estás pensando?"))])
    assert [a["type"] for a in salida["actions"]] == ["say"]


def test_una_decision_aplazada_se_cierra_como_hoy():
    salida = jugar([resp(texto("¡Con gusto! 😊"), herramienta("finalizar_conversacion", {}))],
                   mensaje="lo voy a consultar con mi esposo", estado=ESTADO)
    assert salida["finished"] is True
    assert "end" in [a["type"] for a in salida["actions"]]


def test_la_promo_no_dispara_traspaso():
    salida = jugar([resp(texto("No tengo ese valor 🤔 ¿De dónde sacaste esa cifra?"))],
                   mensaje="vi la promo de 350 mil")
    assert "handoff" not in [a["type"] for a in salida["actions"]]
    assert dichos(salida) == ["No tengo ese valor 🤔 ¿De dónde sacaste esa cifra?"]


def test_dos_mensajes_seguidos_salen_los_dos():
    salida = jugar([resp(texto("¿Cuál te funciona mejor? 🏨"), texto("Mira las opciones 👇"))],
                   mensaje="ok", estado=ESTADO)
    assert len(dichos(salida)) == 2


def test_la_repregunta_a_nombre_de_quien_no_se_toca():
    pregunta = "Listo 🙌 ¿A nombre de quién aparto el cupo?"
    salida = jugar([resp(texto(pregunta))], mensaje="en doble", estado=ESTADO)
    assert dichos(salida) == [pregunta]


def test_un_nombre_generico_se_guarda_como_hoy():
    salida = jugar([resp(herramienta("registrar_nombre", {"nombre": "Cliente"})),
                    resp(texto("¡Listo!"))], mensaje="hola", estado=ESTADO)
    assert {"type": "perfil", "payload": {"nombre": "Cliente"}} in salida["actions"]


def test_ya_se_presento_en_el_runtime_no_cambia_nada():
    saludo = "¡Hola! 😊 Soy *Luisa*, asesora de Arranquemos Pues. ¿Para qué mes?"
    salida = jugar([resp(texto(saludo))], ya_se_presento=True)
    assert dichos(salida) == [saludo]


def test_consultar_tarifario_no_agrega_la_linea_de_ninos_ni_guarda_precios():
    with patch.object(llm_engine, "_invoke_model", side_effect=[
        resp(herramienta("consultar_tarifario", {"mes": "octubre"})),
        resp(texto("Son $549.000 en doble")),
    ]) as mock:
        salida = llm_engine.advance(Bot1(), None, "¿octubre?", runtime={})
    resultado = mock.call_args_list[1].args[2][-1]["content"][0]["content"]
    assert resultado == tarifario.consultar(LLM_CONFIG, hotel="", mes="octubre",
                                            fecha="", presupuesto="")
    assert set(salida["next_state"]) == {"history"}
    assert dichos(salida) == ["Son $549.000 en doble"]


def test_la_telemetria_tiene_las_claves_de_siempre():
    salida = jugar([resp(texto("Hola"))])
    assert set(salida["telemetry"]) == {
        "user_input", "bookings", "pedidos", "camino", "tools", "reply_preview",
        "model_id", "rounds", "latency_ms", "finished", "escalated_to",
        "failsafe", "fuente_datos", "tokens_in", "tokens_out", "cache_read",
        "cache_write",
    }
