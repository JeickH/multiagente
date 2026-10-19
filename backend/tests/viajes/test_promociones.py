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


def test_el_simulacro_vale_lo_mismo_en_los_tres_hoteles_y_las_dos_acomodaciones():
    filas = [p for p in tarifario._datos()["planes"] if p["inicio"] == "2026-10-23"]
    assert {(p["multiple"], p["doble"]) for p in filas} == {(489000, 489000)}
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


def _turno(cfg, mensaje):
    respuesta = {
        "content": [{"type": "text", "text": "¡Hola! 😊 Te cuento del Simulacro decembrino."}],
        "stop_reason": "end_turn",
    }
    with patch.object(llm_engine, "_invoke_model", side_effect=[respuesta]):
        return llm_engine.advance(Bot(cfg), None, mensaje, runtime={})


def test_bot2_por_la_pauta_no_manda_el_flyer_del_mes():
    tipos_normal = [a["type"] for a in _turno(LLM_CONFIG_B, "Hola, info")["actions"]]
    tipos_pauta = [a["type"] for a in _turno(LLM_CONFIG_B, PAUTA)["actions"]]
    assert "say_media" in tipos_normal
    assert tipos_pauta == ["say"]


# ---------------------------------------------------------------------------
# El guardarraíl de precio acepta el valor de la promoción, y solo ese
# ---------------------------------------------------------------------------

def _resultado_octubre():
    return tarifario.consultar(LLM_CONFIG, mes="octubre", fecha="2026-10-23", hoy=HOY)


def test_el_resultado_de_la_herramienta_nombra_la_promocion():
    resultado = _resultado_octubre()
    assert resultado.count("OCTUBRE 23 AL 26 — múltiple $489.000 · doble $489.000") == 2
    assert "Simulacro decembrino" in resultado


@pytest.mark.parametrize("texto,pasa", [
    ("El *Simulacro decembrino* en Piedra Mar vale $489.000 por persona.", True),
    ("Para 2 personas en Amor de Dios serían $978.000.", True),
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
