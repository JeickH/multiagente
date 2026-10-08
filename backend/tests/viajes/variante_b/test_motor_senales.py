"""Señales del cliente (`services/senales.py`): pruebas puras, sin modelo.

Las frases son inventadas o parafraseadas de los casos del informe de
estrategias (10-sep-2026); ningún nombre ni teléfono real (CLAUDE.md #8).
"""
from __future__ import annotations

import pytest

from app.services import senales


class TestAplazamiento:
    @pytest.mark.parametrize("frase", [
        "Voy a validar con mi pareja y le comento",
        "Mil gracias, lo voy a consultar con mi esposo",
        "Déjame cuadro unas cosas y te confirmo más tarde",
        "No estoy cotizando porque somos 2 y debo hablar primero con mi pareja",
        "Sí tengo que programar con la familia para ver qué día vamos a viajar",
        "Ok muchas gracias. Voy a hablar con mi madre y te estaré avisando",
        "lo pienso y te aviso",
        "luego te escribo para reservar",
        "todavía no sé qué fecha",
        "dame unos días y te confirmo",
    ])
    def test_decisiones_aplazadas(self, frase):
        assert senales.es_aplazamiento(frase)

    @pytest.mark.parametrize("frase", [
        "gracias", "ok listo", "chao, que estés bien", "👍",
        "te confirmo que somos 4", "¿cuánto vale diciembre?",
        "quiero reservar para octubre", "no me interesa, gracias",
    ])
    def test_no_son_aplazamientos(self, frase):
        assert not senales.es_aplazamiento(frase)


class TestMencionaMonto:
    @pytest.mark.parametrize("frase", [
        "vi la promo de $350.000", "desde 350 mil", "350k", "$350k",
        "350.000 lunes a jueves", "$350", "350,000 pesos", "$350 mil",
        "tengo trescientos cincuenta mil", "350000", "350 000",
        "¿y la de 350mil?",
    ])
    def test_cualquier_forma_del_monto(self, frase):
        assert senales.menciona_monto(frase, [350000])

    @pytest.mark.parametrize("frase", [
        "1.350.000", "3.500.000", "3500000", "desde 350", "somos 350 personas",
        "$459.000", "", "350 metros", "mi cel es 350 000 1234",
        "mi cel es 315 350 000",
    ])
    def test_otros_numeros_no_cuentan(self, frase):
        assert not senales.menciona_monto(frase, [350000])

    def test_los_montos_vienen_de_la_config(self):
        assert senales.menciona_monto("lo vi en 400 mil", [350000, 400000])
        assert not senales.menciona_monto("lo vi en 400 mil", [350000])
        assert not senales.menciona_monto("350 mil", [])
        assert not senales.menciona_monto("350 mil", ["no-es-numero", None])


class TestCifras:
    def test_extrae_las_cifras_en_pesos(self):
        assert senales.cifras("tengo 450 mil o $400.000") == {450000, 400000}

    def test_un_numero_corto_se_lee_en_miles(self):
        assert 450000 in senales.cifras("tengo 450")

    def test_millones(self):
        assert 1_500_000 in senales.cifras("1,5 millones")

    def test_sin_cifras(self):
        assert senales.cifras("hola, quiero información") == set()


class TestNombreGenerico:
    @pytest.mark.parametrize("valor", [
        "Cliente", "No proporcionado", "no proporcionada", "Casa", "Usuario",
        "Mecánica JR", "Señora", "Distribuidora del Norte SAS", "🌴", "",
        "Sin nombre", "Desconocido",
    ])
    def test_genericos(self, valor):
        assert senales.es_nombre_generico(valor)

    @pytest.mark.parametrize("valor", [
        "Marcela", "Ana María", "José", "Doña Rosa", "Andrés Felipe", "Luz",
    ])
    def test_nombres_de_persona(self, valor):
        assert not senales.es_nombre_generico(valor)


class TestMesMencionado:
    @pytest.mark.parametrize("frase,mes", [
        ("¿cuánto vale en diciembre?", 12), ("info del plan de enero porfa", 1),
        ("para Septiembre", 9), ("setiembre", 9), ("quiero ir en dic", 12),
        ("en octubre o noviembre", 10),
    ])
    def test_meses(self, frase, mes):
        assert senales.mes_mencionado(frase) == mes

    @pytest.mark.parametrize("frase", [
        "Hola, quiero más información", "soy mayor de edad", "somos 4",
        "2026-09-15", "", "diciembrito",
    ])
    def test_sin_mes(self, frase):
        assert senales.mes_mencionado(frase) is None
