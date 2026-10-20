"""El primer mensaje de la pauta llega al bot (incidente del 2026-10-19).

En una conversación nueva el webhook llama a `run_turn(user_input=None)`: el
modelo recibía «salúdalo» y nunca veía «Quiero más información del simulacro
decembrino». Ninguna de las 51 personas de la pauta recibió la promoción en su
primer mensaje, y la QA no lo vio porque llamaba a `llm_engine.advance`
directo. Estas pruebas pasan por `bot_runner.run_turn`, como el webhook.

Datos inventados (regla #8).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

import pytest

from app import models
from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import LLM_CONFIG_B
from app.data.bot_viajes_c import LLM_CONFIG_C
from app.services import bot_runner, llm_engine, tarifario

from .variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    conversacion,
    crear_agencia,
    db,
)

PAUTA = "¡Hola! Quiero más información del simulacro decembrino"
SALUDO = ("¡Hola! 😊 Te cuento del Simulacro decembrino. ¿Cuál hotel prefieres? 👇\n"
          "1️⃣ Amor de Dios\n2️⃣ Bohíos\n3️⃣ Piedra Mar")


@pytest.fixture
def modelo(monkeypatch):
    """Modelo falso que anota lo que recibe en cada llamada."""
    vistos: List[str] = []

    def invocar(model_id, system, working, tools, *a, **k):
        vistos.append(json.dumps(working, ensure_ascii=False))
        return {"content": [{"type": "text", "text": SALUDO}], "stop_reason": "end_turn"}

    monkeypatch.setattr(llm_engine, "_invoke_model", invocar)
    monkeypatch.setattr(llm_engine, "record_booking", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: date(2026, 10, 20))
    return vistos


def _primer_turno(db, cfg, texto, sufijo):
    ag = crear_agencia(db, sufijo=sufijo, cfg=json.loads(json.dumps(cfg)))
    conv = conversacion(db, ag["team"])
    sesion = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                                 user_input=None, meta_account=None, primer_mensaje=texto)
    estado = json.loads(sesion.state or "{}")
    return estado.get("history") or []


@pytest.mark.parametrize("cfg,sufijo", [(LLM_CONFIG, "PM1"), (LLM_CONFIG_B, "PM2"), (LLM_CONFIG_C, "PM3")],
                         ids=["bot1", "bot2", "bot3"])
def test_la_pauta_llega_al_modelo_y_salen_flyer_y_video(db, modelo, cfg, sufijo):
    historia = _primer_turno(db, cfg, PAUTA, sufijo)
    assert PAUTA in modelo[0]
    assert "acaba de abrir el chat" not in modelo[0]
    assert historia[0] == {"role": "user", "content": PAUTA}
    assert "flyer_simulacro_decembrino" in historia[-1]["content"]
    assert "video_simulacro_decembrino" in historia[-1]["content"]


def test_otro_primer_mensaje_sigue_como_saludo(db, modelo):
    historia = _primer_turno(db, LLM_CONFIG, "Hola, buenas tardes", "PM4")
    assert "acaba de abrir el chat" in modelo[0]
    assert "Hola, buenas tardes" not in modelo[0]
    assert "flyer_simulacro_decembrino" not in historia[-1]["content"]


def test_pasada_la_salida_vuelve_al_saludo(db, modelo, monkeypatch):
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: date(2026, 10, 24))
    _primer_turno(db, LLM_CONFIG, PAUTA, "PM5")
    assert "acaba de abrir el chat" in modelo[0]
