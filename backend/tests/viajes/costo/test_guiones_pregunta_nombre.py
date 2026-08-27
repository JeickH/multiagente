"""#379 contra Claude de verdad: el nombre entra siempre en el primer mensaje.

**Cuesta plata.** Corre con `--con-costo`. Unos 3 centavos de dólar.

`tests/viajes/test_pregunta_nombre.py` (gratis) prueba **cuándo** dispara el
guardarraíl. Esto prueba lo que no se puede afirmar sin el modelo: que el
mensaje resultante se lee como una conversación y no como un remiendo, y que el
guardarraíl no le quita nada al turno — el material adjunto sigue saliendo.

Se imprime la transcripción (`-s` para verla) por la lección del 19-ago-2026:
doce guiones pasaron sesenta y tres chequeos verdes y el bot igual perdía
ventas. Los asserts vigilan lo afirmable; la transcripción está para leerla.

Nombres inventados (regla #8: el repo es público).
"""
from __future__ import annotations

import re

import pytest

from app.services import llm_engine

_PIDE_EL_NOMBRE = re.compile(
    r"con qui[eé]n tengo el gusto|c[oó]mo te llamas|cu[aá]l es tu nombre|"
    r"tu nombre|me regalas tu nombre|qui[eé]n eres|con qui[eé]n hablo",
    re.IGNORECASE,
)


def _dicho(salida) -> str:
    return " ".join(
        a["payload"].get("text", "")
        for a in salida["actions"] if a["type"] == "say"
    )


def _tools(salida) -> set:
    return {t["tool"] for t in salida["telemetry"]["tools"]}


def _medios(salida) -> list:
    return [a for a in salida["actions"] if a["type"] == "say_media"]


def _transcribir(titulo: str, salida) -> None:
    print(f"\n{'=' * 68}\n{titulo}\n{'=' * 68}")
    for a in salida["actions"]:
        if a["type"] == "say":
            for i, linea in enumerate((a["payload"].get("text") or "").split("\n")):
                print(f"{'BOT  | ' if i == 0 else '     | '}{linea}")
            print("     ·")
        elif a["type"] == "media":
            print(f"     [media: {a['payload'].get('key') or a['payload']}]")
    print("=" * 68)


@pytest.fixture
def bot_viajes():
    from tests.viajes.conftest import BotViajes

    return BotViajes()


class TestElNombreEntraSiempre:
    @pytest.mark.parametrize("apertura", [
        "¿qué tours incluye el plan?",
        "Hola, ¿cuánto vale el plan?",
        "¿qué hoteles manejan?",
        "Hola, ¿dónde están ubicados?",
    ])
    def test_el_primer_mensaje_pide_el_nombre(self, bot_viajes, modelo_real, apertura):
        """Las cuatro aperturas concretas con las que se midió el 80% de acierto
        del modelo solo. Con el guardarraíl tienen que ser 4 de 4."""
        modelo_real["actual"] = "#379 primer mensaje"
        salida = llm_engine.advance(bot_viajes, None, apertura, runtime={})
        _transcribir(f"#379 — {apertura}", salida)

        assert _PIDE_EL_NOMBRE.search(_dicho(salida)), (
            f"el primer mensaje salió sin pedir el nombre: {_dicho(salida)!r}"
        )

    def test_no_lo_pide_dos_veces(self, bot_viajes, modelo_real):
        """Si el modelo ya preguntó, el guardarraíl no puede agregar otra: dos
        veces seguidas suena a formulario, no a asesora."""
        modelo_real["actual"] = "#379 sin duplicar"
        salida = llm_engine.advance(bot_viajes, None, "hola", runtime={})
        _transcribir("#379 — apertura genérica, sin duplicar", salida)

        veces = len(_PIDE_EL_NOMBRE.findall(_dicho(salida)))
        assert veces == 1, f"la pregunta del nombre aparece {veces} veces"

    def test_el_material_adjunto_no_se_pierde(self, bot_viajes, modelo_real):
        """La razón de agregar un mensaje en vez de descartar el turno y pedirle
        al modelo que lo rehaga: rehacerlo se lleva por delante el flyer."""
        modelo_real["actual"] = "#379 conserva el material"
        salida = llm_engine.advance(
            bot_viajes, None, "¿qué tours incluye el plan?", runtime={}
        )
        _transcribir("#379 — el material sigue saliendo", salida)

        assert _medios(salida), "el turno se quedó sin el material de los tours"
        assert _PIDE_EL_NOMBRE.search(_dicho(salida))


class TestNoSeMeteDondeNoDebe:
    def test_con_el_nombre_sabido_no_pregunta(self, bot_viajes, modelo_real):
        """El guardarraíl no puede reintroducir #377 por la puerta de atrás."""
        modelo_real["actual"] = "#379 no rompe #377"
        salida = llm_engine.advance(
            bot_viajes, None, "¿qué tours incluye el plan?",
            runtime={"contact_name": "Marcela"},
        )
        _transcribir("#379 — con el nombre ya sabido", salida)

        assert not _PIDE_EL_NOMBRE.search(_dicho(salida))

    def test_en_el_segundo_turno_el_guardarrail_no_agrega_nada(
        self, bot_viajes, modelo_real
    ):
        """El guardarraíl es sólo del primer turno; que a partir del segundo la
        conversación siga siendo del modelo lo fija `test_pregunta_nombre.py`
        de forma determinista. Acá se cuida lo único que hace falta medir con el
        modelo: que **no salga dos veces** en el mismo turno.

        Nota de lo observado: el modelo sí vuelve a preguntar el nombre en el
        segundo turno cuando la persona no se presentó — es comportamiento suyo,
        anterior a este cambio (el guardarraíl no puede disparar con historial),
        así que no se afirma que no lo haga.
        """
        modelo_real["actual"] = "#379 no insiste"
        primera = llm_engine.advance(bot_viajes, None, "hola", runtime={})
        segunda = llm_engine.advance(
            bot_viajes, primera.get("next_state"),
            "¿y qué tours incluye?", runtime={},
        )
        _transcribir("#379 — segundo turno", segunda)

        veces = len(_PIDE_EL_NOMBRE.findall(_dicho(segunda)))
        assert veces <= 1, f"la pregunta del nombre aparece {veces} veces"
