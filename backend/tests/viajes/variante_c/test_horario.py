"""Horario de asesores del bot 3: `en_horario` y `cuando_atienden`.

Todas las horas se escriben en hora de Colombia y se pasan en UTC (+5 h), como
llegan del backend. Semana de referencia: lunes 12 a domingo 18 de octubre de
2026.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services import horario
from app.services.horario import cuando_atienden, en_horario

CFG = {
    "tz": "America/Bogota",
    "dias": {
        "lun": ["08:00", "18:00"], "mar": ["08:00", "18:00"], "mie": ["08:00", "18:00"],
        "jue": ["08:00", "18:00"], "vie": ["08:00", "18:00"], "sab": ["08:00", "13:00"],
    },
}
DIA = {"lun": 12, "mar": 13, "mie": 14, "jue": 15, "vie": 16, "sab": 17, "dom": 18}


def co(dia: str, hhmm: str, *, naive: bool = True) -> datetime:
    """Hora de Colombia → instante UTC (naive, como guarda el backend)."""
    h, m = map(int, hhmm.split(":"))
    utc = datetime(2026, 10, DIA[dia], h, m) + timedelta(hours=5)
    return utc if naive else utc.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fronteras
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("dia,hora,esperado", [
    ("lun", "07:59", False), ("lun", "08:00", True), ("lun", "17:59", True),
    ("lun", "18:00", False), ("mie", "12:00", True), ("vie", "17:59", True),
    ("vie", "18:00", False), ("sab", "07:59", False), ("sab", "08:00", True),
    ("sab", "12:59", True), ("sab", "13:00", False), ("dom", "10:00", False),
    ("dom", "08:00", False), ("lun", "00:00", False), ("vie", "23:59", False),
])
def test_en_horario_fronteras(dia, hora, esperado):
    assert en_horario(co(dia, hora), CFG) is esperado
    assert en_horario(co(dia, hora, naive=False), CFG) is esperado


@pytest.mark.parametrize("dia,hora,esperado", [
    ("lun", "08:00", "en un momento"),
    ("lun", "17:59", "en un momento"),
    ("sab", "12:59", "en un momento"),
    ("lun", "07:59", "hoy a partir de las 8:00 a.m."),
    ("lun", "00:30", "hoy a partir de las 8:00 a.m."),
    ("sab", "06:00", "hoy a partir de las 8:00 a.m."),
    ("lun", "18:00", "mañana a partir de las 8:00 a.m."),
    ("jue", "22:00", "mañana a partir de las 8:00 a.m."),
    ("vie", "18:30", "mañana a partir de las 8:00 a.m."),   # mañana = sábado
    ("sab", "13:00", "el lunes a partir de las 8:00 a.m."),
    ("sab", "14:00", "el lunes a partir de las 8:00 a.m."),
    ("dom", "10:00", "mañana a partir de las 8:00 a.m."),   # mañana = lunes
    ("dom", "23:59", "mañana a partir de las 8:00 a.m."),
])
def test_cuando_atienden(dia, hora, esperado):
    assert cuando_atienden(co(dia, hora), CFG) == esperado


def test_viernes_en_la_noche_el_manana_es_el_sabado():
    """«mañana» cae en sábado, que abre a las 8:00 aunque cierre a la 1:00 p.m."""
    ahora = co("vie", "18:30")
    assert cuando_atienden(ahora, CFG).startswith("mañana")
    assert en_horario(co("sab", "08:00"), CFG)


def test_la_medianoche_utc_no_cambia_el_dia_de_colombia():
    """El lunes 19:30 de Colombia ya es martes 00:30 en UTC: sigue siendo
    lunes para el horario (cerrado, abren «mañana», que es martes)."""
    ahora = co("lun", "19:30")
    assert ahora.day == 13 and ahora.hour == 0
    assert cuando_atienden(ahora, CFG) == "mañana a partir de las 8:00 a.m."


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_dia_sin_entrada_esta_cerrado_y_se_nombra_en_espanol():
    cfg = {"tz": "America/Bogota", "dias": {"mie": ["09:30", "12:00"]}}
    assert cuando_atienden(co("lun", "10:00"), cfg) == "el miércoles a partir de las 9:30 a.m."
    assert cuando_atienden(co("mar", "10:00"), cfg) == "mañana a partir de las 9:30 a.m."
    assert en_horario(co("mie", "11:59"), cfg) and not en_horario(co("mie", "12:00"), cfg)


def test_nombres_largos_y_con_tilde():
    cfg = {"dias": {"sábado": ["08:00", "13:00"], "Miércoles": ["14:00", "15:00"]}}
    assert en_horario(co("sab", "09:00"), cfg)
    assert cuando_atienden(co("mie", "10:00"), cfg) == "hoy a partir de las 2:00 p.m."


@pytest.mark.parametrize("rango", [["18:00", "08:00"], ["8", "18:00"], ["25:00", "26:00"], "08:00-18:00"])
def test_rango_mal_escrito_cuenta_como_cerrado(rango):
    cfg = {"dias": {"lun": rango, "mar": ["08:00", "18:00"]}}
    assert not en_horario(co("lun", "10:00"), cfg)
    assert cuando_atienden(co("lun", "10:00"), cfg) == "mañana a partir de las 8:00 a.m."


@pytest.mark.parametrize("cfg", [{}, {"dias": {}}, {"dias": None}, None])
def test_sin_horario(cfg):
    assert not en_horario(co("lun", "10:00"), cfg)
    assert cuando_atienden(co("lun", "10:00"), cfg) == "en el próximo horario de atención"


def test_sin_tz_usa_colombia():
    cfg = {"dias": CFG["dias"]}
    assert en_horario(co("lun", "08:00"), cfg) and not en_horario(co("lun", "07:59"), cfg)


def test_sin_base_de_zonas_cae_a_utc_menos_5(monkeypatch):
    """La imagen `python:3.11-slim` puede no traer `tzdata`: Colombia sin
    horario de verano es UTC−5 fijo, así que el resultado no cambia."""
    monkeypatch.setattr(horario, "ZoneInfo", None)
    assert en_horario(co("lun", "08:00"), CFG) and not en_horario(co("lun", "07:59"), CFG)
    assert cuando_atienden(co("sab", "14:00"), CFG) == "el lunes a partir de las 8:00 a.m."


def test_zona_desconocida_cae_a_utc_menos_5():
    cfg = dict(CFG, tz="Zona/Inventada")
    assert en_horario(co("lun", "08:00"), cfg) and not en_horario(co("lun", "18:00"), cfg)


@pytest.mark.parametrize("hhmm,texto", [
    ("08:00", "8:00 a.m."), ("13:00", "1:00 p.m."), ("12:00", "12:00 m."),
    ("00:30", "12:30 a.m."), ("09:30", "9:30 a.m."),
])
def test_formato_de_hora(hhmm, texto):
    cfg = {"dias": {"mar": [hhmm, "23:59"]}}
    assert cuando_atienden(co("lun", "23:00"), cfg) == f"mañana a partir de las {texto}"
