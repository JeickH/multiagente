"""Promociones de una salida: el «Simulacro decembrino» (pedido del CEO, 2026-10-19).

Arranquemos Pues pauta la salida del 23 al 26 de octubre con el mensaje
precargado «¡Hola! Quiero más información del simulacro decembrino». Lo que la
promoción trae de más vive en `app/data/promociones_covenas.json`; el precio,
en la fila de la salida, como cualquier otro. Estas pruebas vigilan que los dos
archivos digan lo mismo, que la promoción llegue a los tres bots y que se
apague sola cuando la salida pase.

Frases inventadas; ningún dato real (CLAUDE.md #8).
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict
from unittest.mock import patch

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import LLM_CONFIG_B
from app.data.bot_viajes_c import LLM_CONFIG_C
from app.services import guardarrail_precio, llm_engine, tarifario

HOY = date(2026, 10, 19)
PAUTA = "¡Hola! Quiero más información del simulacro decembrino"
TITULO = "## Promoción vigente: Simulacro decembrino"


class Bot:
    id = 99
    engine = "llm"
    status = "active"

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


@pytest.fixture(autouse=True)
def hoy(monkeypatch):
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: HOY)


def _system(cfg, history=None, user_text=None):
    bot = Bot(cfg)
    cfg = {**llm_engine.config_de(bot), "_runtime": {}}
    return llm_engine._system_prompt(bot, cfg, history or [], user_text)


# ---------------------------------------------------------------------------
# Los datos
# ---------------------------------------------------------------------------

def test_la_salida_de_cada_promocion_existe_y_lleva_su_nombre():
    """Si alguien regenera el tarifario desde el Excel, la fila vuelve a
    «Plan estándar» con el precio viejo y el bot anunciaría una promoción con
    la tarifa de otra cosa. Esta prueba es la que lo grita."""
    planes = tarifario._datos()["planes"]
    for promo in tarifario._promos_crudas():
        filas = [p for p in planes if p["inicio"] == promo["inicio"]]
        assert filas, f"{promo['nombre']}: no hay salida el {promo['inicio']}"
        assert {p["plan"] for p in filas} == {promo["nombre"]}
        hoteles = {h for p in filas for h in p["hoteles"]}
        assert hoteles == {"amor_de_dios", "bohios", "piedra_mar"}


def test_el_simulacro_vale_lo_mismo_en_los_tres_hoteles():
    """Múltiple $489.000 en los tres; la doble, +10 % como la cotizan las
    asesoras (CEO, 2026-10-21)."""
    filas = [p for p in tarifario._datos()["planes"] if p["inicio"] == "2026-10-23"]
    assert {(p["multiple"], p["doble"]) for p in filas} == {(489000, 537900)}
    assert {(p["noches"], p["dias"]) for p in filas} == {(2, 3)}


def test_el_archivo_de_promociones_no_trae_precios():
    crudo = tarifario._PROMOS.read_text(encoding="utf-8")
    assert not re.search(r"\$|\d{3}\.\d{3}|\b\d{6}\b", crudo)


# ---------------------------------------------------------------------------
# Detección
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    PAUTA,
    "hola info del SIMULACRO",
    "Simulacro decembrino?",
])
def test_reconoce_la_pauta_y_sus_variantes(texto):
    assert tarifario.promocion_mencionada(texto, HOY)["nombre"] == "Simulacro decembrino"


@pytest.mark.parametrize("texto", ["Hola, quiero más información", "diciembre", "", None])
def test_lo_demas_no_es_la_promocion(texto):
    assert tarifario.promocion_mencionada(texto, HOY) is None


def test_se_apaga_sola_cuando_la_salida_pasa():
    assert tarifario.promociones_vigentes(date(2026, 10, 23))
    assert tarifario.promociones_vigentes(date(2026, 10, 24)) == []
    assert tarifario.promocion_mencionada(PAUTA, date(2026, 10, 24)) is None


# ---------------------------------------------------------------------------
# El prompt de los tres bots
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cfg", [LLM_CONFIG, LLM_CONFIG_B, LLM_CONFIG_C], ids=["bot1", "bot2", "bot3"])
def test_los_tres_bots_reciben_la_promocion(cfg):
    system = _system(cfg)
    assert TITULO in system
    bloque = system[system.index(TITULO):].split("\n\n## ")[0]
    for extra in ("natilla", "buñuelos", "chicharronada", "música en vivo", "DJ", "entre otros"):
        assert extra in bloque
    assert PAUTA in bloque
    assert "fecha=2026-10-23" in bloque
    # Ninguna cifra: el precio sale de la herramienta y lo valida el guardarraíl.
    assert "$" not in bloque


def test_el_bloque_es_estable_para_la_cache():
    """Igual para todas las conversaciones del día: va en el prefijo cacheado."""
    assert _system(LLM_CONFIG_C, user_text=PAUTA).count(TITULO) == 1
    a = _system(LLM_CONFIG)
    b = _system(LLM_CONFIG, user_text=PAUTA)
    assert a == b


def test_pasada_la_salida_desaparece(monkeypatch):
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: date(2026, 10, 24))
    assert "Promoción vigente" not in _system(LLM_CONFIG)


def test_un_bot_sin_tarifario_no_la_recibe():
    cfg = {k: v for k, v in LLM_CONFIG.items() if k != "tarifario"}
    assert "Promoción vigente" not in _system(cfg)


# ---------------------------------------------------------------------------
# Bot 2: quien llega por la pauta no recibe la vitrina genérica ni el flyer
# ---------------------------------------------------------------------------

def test_bot2_por_la_pauta_no_lleva_la_vitrina():
    assert "## Datos para tu primer mensaje" in _system(LLM_CONFIG_B, user_text="Hola, info")
    assert "## Datos para tu primer mensaje" not in _system(LLM_CONFIG_B, user_text=PAUTA)


SALUDO = ("¡Hola! 😊 Te cuento del Simulacro decembrino. ¿Cuál hotel prefieres? 👇\n"
          "1️⃣ Amor de Dios\n2️⃣ Bohíos\n3️⃣ Piedra Mar")
MEDIOS = json.loads(tarifario._PROMOS.read_text(encoding="utf-8"))["promociones"][0]["medios"]
FLYER_URL = MEDIOS["flyer_simulacro_decembrino"]["url"]
VIDEO_URL = MEDIOS["video_simulacro_decembrino"]["url"]


def _turno(cfg, mensaje, *bloques):
    bloques = bloques or ({"type": "text", "text": SALUDO},)
    respuestas = []
    for bloque in bloques:
        if bloque["type"] == "tool_use":
            respuestas.append({"content": [bloque], "stop_reason": "tool_use"})
    respuestas.append({
        "content": [b for b in bloques if b["type"] == "text"] or [{"type": "text", "text": SALUDO}],
        "stop_reason": "end_turn",
    })
    with patch.object(llm_engine, "_invoke_model", side_effect=respuestas):
        return llm_engine.advance(Bot(cfg), None, mensaje, runtime={})


def _urls(salida):
    return [a["payload"]["url"] for a in salida["actions"] if a["type"] == "say_media"]


def test_bot2_por_la_pauta_no_manda_el_flyer_del_mes():
    normal = _urls(_turno(LLM_CONFIG_B, "Hola, info"))
    pauta = _urls(_turno(LLM_CONFIG_B, PAUTA))
    assert normal and FLYER_URL not in normal
    assert pauta == [FLYER_URL, VIDEO_URL]


# ---------------------------------------------------------------------------
# Flyer y video de la promoción
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cfg", [LLM_CONFIG, LLM_CONFIG_B, LLM_CONFIG_C], ids=["bot1", "bot2", "bot3"])
def test_los_medios_estan_en_el_catalogo_de_los_tres_bots(cfg, monkeypatch):
    catalogo = llm_engine._media_catalog(cfg, None)
    assert catalogo["flyer_simulacro_decembrino"]["url"] == FLYER_URL
    assert catalogo["video_simulacro_decembrino"]["media_type"] == "video"
    assert "`flyer_simulacro_decembrino`" in _system(cfg)
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: date(2026, 10, 24))
    assert "flyer_simulacro_decembrino" not in llm_engine._media_catalog(cfg, None)


@pytest.mark.parametrize("cfg", [LLM_CONFIG, LLM_CONFIG_B, LLM_CONFIG_C], ids=["bot1", "bot2", "bot3"])
def test_por_la_pauta_el_primer_mensaje_lleva_flyer_y_video(cfg):
    salida = _turno(cfg, PAUTA)
    assert _urls(salida)[-2:] == [FLYER_URL, VIDEO_URL] or _urls(salida) == [FLYER_URL, VIDEO_URL]
    textos = [a["payload"].get("text") or a["payload"].get("caption") for a in salida["actions"]]
    assert any(SALUDO in (t or "") for t in textos)
    ultimo = salida["next_state"]["history"][-1]["content"]
    assert "flyer_simulacro_decembrino" in ultimo and "video_simulacro_decembrino" in ultimo


@pytest.mark.parametrize("cfg", [LLM_CONFIG, LLM_CONFIG_C], ids=["bot1", "bot3"])
def test_sin_pauta_no_hay_medios_de_la_promocion(cfg):
    urls = _urls(_turno(cfg, "Hola, quiero más información"))
    assert FLYER_URL not in urls and VIDEO_URL not in urls


def test_por_la_pauta_se_quita_el_flyer_del_mes_que_mando_el_modelo():
    envio = {"type": "tool_use", "id": "t1", "name": "enviar_media",
             "input": {"claves": ["tarifario_amordios_ago_nov"]}}
    urls = _urls(_turno(LLM_CONFIG, PAUTA, envio, {"type": "text", "text": SALUDO}))
    assert urls == [FLYER_URL, VIDEO_URL]


def test_no_se_duplican_si_el_modelo_ya_los_mando():
    envio = {"type": "tool_use", "id": "t1", "name": "enviar_media",
             "input": {"claves": ["flyer_simulacro_decembrino", "video_simulacro_decembrino"]}}
    urls = _urls(_turno(LLM_CONFIG, PAUTA, envio, {"type": "text", "text": SALUDO}))
    assert sorted(urls) == sorted([FLYER_URL, VIDEO_URL])


def test_el_segundo_turno_no_los_repite():
    estado = {"history": [{"role": "user", "content": PAUTA},
                          {"role": "assistant", "content": SALUDO}]}
    respuesta = {"content": [{"type": "text", "text": "¿Cuántas personas viajan?"}],
                 "stop_reason": "end_turn"}
    with patch.object(llm_engine, "_invoke_model", side_effect=[respuesta]):
        salida = llm_engine.advance(Bot(LLM_CONFIG), estado, "Piedra Mar", runtime={})
    assert _urls(salida) == []


# ---------------------------------------------------------------------------
# El guardarraíl de precio acepta el valor de la promoción, y solo ese
# ---------------------------------------------------------------------------

def _resultado_octubre():
    return tarifario.consultar(LLM_CONFIG, mes="octubre", fecha="2026-10-23", hoy=HOY)


def test_el_resultado_de_la_herramienta_nombra_la_promocion():
    resultado = _resultado_octubre()
    assert resultado.count("OCTUBRE 23 AL 26 — múltiple $489.000 · doble $537.900") == 2
    assert "Simulacro decembrino" in resultado


@pytest.mark.parametrize("texto,pasa", [
    ("El *Simulacro decembrino* en Piedra Mar vale $489.000 por persona.", True),
    ("Para 2 personas en Amor de Dios serían $1.075.800.", True),
    # Dos personas no van en múltiple (CEO, 2026-10-21): 2 × $489.000 no se vende.
    ("Para 2 personas en Amor de Dios serían $978.000.", False),
    ("Para 3 personas en múltiple serían $1.467.000.", True),
    ("El Simulacro decembrino en Amor de Dios queda en $459.000 por persona.", False),
])
def test_guardarrail_con_la_fila_del_simulacro(texto, pasa):
    viola = guardarrail_precio.viola_precio(
        texto,
        resultados_precios=[_resultado_octubre()],
        desde_validos=set(),
        cifras_cliente=set(),
        extras=tarifario.extras(),
    )
    assert (viola is None) is pasa


def _segundo_turno(primer_mensaje, claves):
    estado = {"history": [{"role": "user", "content": primer_mensaje},
                          {"role": "assistant", "content": SALUDO}]}
    respuestas = [
        {"content": [{"type": "tool_use", "id": "t1", "name": "enviar_media",
                      "input": {"claves": claves}}], "stop_reason": "tool_use"},
        {"content": [{"type": "text", "text": "¿Cuántas personas viajan?"}],
         "stop_reason": "end_turn"},
    ]
    with patch.object(llm_engine, "_invoke_model", side_effect=respuestas):
        return llm_engine.advance(Bot(LLM_CONFIG), estado, "Piedra Mar", runtime={})


def test_en_la_conversacion_de_la_pauta_no_sale_el_tarifario_viejo_del_mes():
    salida = _segundo_turno(PAUTA, ["tarifario_piedramar_jul_oct", "info_piedramar"])
    urls = _urls(salida)
    assert all("tarifario_piedramar2" not in u for u in urls)
    assert any("hotel_piedramar.jpeg" in u for u in urls)
    assert "tarifario_piedramar_jul_oct" not in salida["next_state"]["history"][-1]["content"]


def test_fuera_de_la_pauta_el_tarifario_del_mes_si_sale():
    urls = _urls(_segundo_turno("Hola, info de octubre", ["tarifario_piedramar_jul_oct"]))
    assert any("tarifario_piedramar2" in u for u in urls)


def test_el_tarifario_de_otro_mes_si_sale_en_la_conversacion_de_la_pauta():
    urls = _urls(_segundo_turno(PAUTA, ["tarifario_piedramar_nov_ene"]))
    assert any("tarifario_piedramar1" in u for u in urls)


# ---------------------------------------------------------------------------
# «Mes sin consultar» no tumba un mes que la sesión ya consultó
# ---------------------------------------------------------------------------

def test_mes_ya_consultado_en_la_sesion_no_viola():
    cfg = {"consulta_obligatoria_por_mes": True}
    texto = ["1️⃣ *Múltiple*: $489.000 c/u → *$978.000 total*"]
    pregunta = "En la imagen de octubre dice otro valor, por qué cambia?"
    assert llm_engine._viola_consulta_por_mes(cfg, pregunta, texto, [])
    assert not llm_engine._viola_consulta_por_mes(
        cfg, pregunta, texto, [], [_resultado_octubre()])
    # Un mes que la sesión nunca consultó sigue violando.
    assert llm_engine._viola_consulta_por_mes(
        cfg, "y en noviembre?", texto, [], [_resultado_octubre()])
