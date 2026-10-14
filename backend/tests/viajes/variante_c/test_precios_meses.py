"""`tarifario.meses_disponibles`: el menú de meses de la bienvenida del bot 3.

Se compara contra el JSON del tarifario, nunca contra cifras escritas aquí.
"""
from __future__ import annotations

import inspect
import re
from datetime import date

import pytest

from app.services import tarifario


def _esperado(hoy: date):
    por_mes = {}
    for p in tarifario._datos()["planes"]:
        inicio = date.fromisoformat(p["inicio"])
        if inicio >= hoy:
            clave = (inicio.year, inicio.month)
            por_mes[clave] = min(p["multiple"], por_mes.get(clave, p["multiple"]))
    return sorted(por_mes.items())


@pytest.mark.parametrize("hoy", [
    date(2026, 7, 1), date(2026, 10, 7), date(2026, 10, 10), date(2026, 10, 31),
    date(2026, 12, 30), date(2027, 1, 15),
])
def test_meses_en_orden_con_su_desde(hoy):
    meses = tarifario.meses_disponibles(hoy)
    esperado = _esperado(hoy)[:4]
    assert [(m["anio"], m["mes"]) for m in meses] == [k for k, _ in esperado]
    assert [m["desde"] for m in meses] == [v for _, v in esperado]
    for m in meses:
        assert m["nombre"] == tarifario._NOMBRE_MES[m["mes"]].lower()
        assert set(m) == {"mes", "anio", "nombre", "desde"}


def test_hoy_octubre_10():
    meses = tarifario.meses_disponibles(date(2026, 10, 10))
    assert [m["nombre"] for m in meses] == ["octubre", "noviembre", "diciembre", "enero"]
    assert [m["anio"] for m in meses] == [2026, 2026, 2026, 2027]


def test_el_desde_es_el_del_mes_en_consultar():
    """Mismo criterio que el «desde» del mes que ve el bot en la consulta."""
    hoy = date(2026, 10, 10)
    for m in tarifario.meses_disponibles(hoy):
        minimo = min(
            p["multiple"] for h in ("amor_de_dios", "piedra_mar")
            for p in tarifario.planes_vigentes(h, hoy, m["mes"])
            if date.fromisoformat(p["inicio"]).year == m["anio"]
        )
        assert m["desde"] == minimo


def test_un_mes_sin_salidas_restantes_no_entra():
    """El 31 de octubre ya salió la del 30: octubre no se ofrece."""
    meses = tarifario.meses_disponibles(date(2026, 10, 31))
    assert meses[0]["nombre"] == "noviembre"


@pytest.mark.parametrize("maximo,n", [(1, 1), (2, 2), (4, 4), (10, 4), (0, 0), (-1, 0)])
def test_maximo(maximo, n):
    hoy = date(2026, 10, 10)
    assert len(tarifario.meses_disponibles(hoy, maximo)) == min(n, len(_esperado(hoy)))


def test_maximo_por_defecto_es_4():
    assert len(tarifario.meses_disponibles(date(2026, 7, 1))) == 4


def test_sin_temporada():
    assert tarifario.meses_disponibles(date(2027, 6, 1)) == []


def test_no_tiene_cifras_a_mano():
    assert not re.search(r"\d{2,3}[.,]?000", inspect.getsource(tarifario.meses_disponibles))
