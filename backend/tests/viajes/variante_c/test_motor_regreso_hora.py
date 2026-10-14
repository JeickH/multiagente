"""`contexto_de_regreso_y_hora` (bot 3): «Ya hablaron antes» y la franja del día.

Con y sin flag. La hora se fija con `llm_engine._ahora_utc`. Sin datos reales.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine

FLAG = {"contexto_de_regreso_y_hora": True}
#: 00:00 del miércoles 7-oct-2026 en Bogotá (UTC-5).
MEDIANOCHE = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)


class Bot:
    id = 78
    engine = "llm"
    status = "active"

    def __init__(self, **flags):
        self.llm_config = json.dumps({**LLM_CONFIG, **flags}, ensure_ascii=False)


def system(bot, history=None, **runtime):
    cfg = {**llm_engine.config_de(bot), "_runtime": dict(runtime)}
    return llm_engine._system_prompt(bot, cfg, history or [], "hola")


HISTORIA = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "¡Hola!"}]


@pytest.fixture(autouse=True)
def hora(monkeypatch):
    monkeypatch.setattr(llm_engine, "_ahora_utc", lambda: MEDIANOCHE + timedelta(hours=10))


class TestYaHablaronAntes:
    def test_sesion_nueva_de_alguien_que_vuelve(self):
        texto = system(Bot(**FLAG), ya_se_presento=True)
        assert "## Ya hablaron antes" in texto
        assert "/bienvenida_regreso" in texto

    def test_con_lo_que_trae_el_runtime(self):
        texto = system(Bot(**FLAG), ya_se_presento=True, ultimo_mes="diciembre",
                       ultimo_hotel="piedra mar", etapa_previa="cotizacion")
        assert "La última vez estuvo mirando *diciembre* en *Piedra Mar*." in texto
        assert "Había llegado hasta la cotización." in texto

    def test_lo_que_no_valida_no_entra(self):
        texto = system(Bot(**FLAG), ya_se_presento=True, ultimo_mes="Ana 3XXXXXXXXX",
                       ultimo_hotel="la casa de Ana", etapa_previa="<script>")
        assert "Ya hablaron antes" in texto
        for basura in ("Ana", "3XXXXXXXXX", "script", "La última vez", "Había llegado"):
            assert basura not in texto.split("## Ya hablaron antes")[1].split("##")[0]

    def test_con_historial_o_sin_la_senal_no_va(self):
        assert "Ya hablaron antes" not in system(Bot(**FLAG), HISTORIA, ya_se_presento=True)
        assert "Ya hablaron antes" not in system(Bot(**FLAG), ya_se_presento=False)

    def test_sin_flag(self):
        assert "Ya hablaron antes" not in system(Bot(), ya_se_presento=True)


class TestFranjaDelDia:
    @pytest.mark.parametrize("hora_local,franja,saludo", [
        (4, "noche", "buenas noches"), (5, "mañana", "buenos días"),
        (11, "mañana", "buenos días"), (12, "tarde", "buenas tardes"),
        (18, "tarde", "buenas tardes"), (19, "noche", "buenas noches"),
        (23, "noche", "buenas noches"),
    ])
    def test_franjas(self, monkeypatch, hora_local, franja, saludo):
        monkeypatch.setattr(llm_engine, "_ahora_utc",
                            lambda: MEDIANOCHE + timedelta(hours=hora_local))
        texto = system(Bot(**FLAG))
        assert f"es de **{franja}**" in texto and f"«{saludo}»" in texto

    def test_va_al_final_y_sin_la_hora_exacta(self):
        texto = system(Bot(**FLAG))
        assert texto.rstrip().split("\n## ")[-1].startswith("Momento del día")
        assert "10:00" not in texto.split("## Momento del día")[1]

    def test_el_prefijo_cambia_por_franja_no_por_minuto(self, monkeypatch):
        """Medido: en un día, 3 cambios por la franja (con el flag). Con la hora
        al minuto serían 1.439, y la caché de Bedrock se reescribiría siempre."""
        vistos = []
        for minuto in range(0, 24 * 60, 10):
            monkeypatch.setattr(llm_engine, "_ahora_utc",
                                lambda m=minuto: MEDIANOCHE + timedelta(minutes=m))
            huella = hashlib.md5(system(Bot(**FLAG), HISTORIA).encode()).hexdigest()
            if not vistos or vistos[-1] != huella:
                vistos.append(huella)
        assert len(vistos) - 1 == 3

    def test_sin_flag(self):
        assert "Momento del día" not in system(Bot())
