"""La dirección de la oficina contra Claude de verdad, en Bedrock (26-ago-2026).

**Cuesta plata.** Corre con `--con-costo`. Unos 3 centavos de dólar.

`tests/viajes/test_direccion.py` (gratis) prueba que **el prompt dice** la
dirección. Esto prueba que **el modelo la dice**, que no es lo mismo: el dato
compite con la regla de oro ("si no cae en estos temas, escala"), y el gotcha
confirmado del proyecto es que las reglas del prompt se diluyen entre sí.

Tres cosas que sólo se ven corriendo el modelo:

1. Que conteste la dirección en vez de escalarla, que era el comportamiento
   viejo cuando el dato no existía.
2. Que la mande **completa**. Una dirección a medias ("estamos en el Bosque
   Plaza") obliga a preguntar otra vez, que es justo lo que el CEO quería
   quitar.
3. Que no se la dé a quien pregunta **de dónde sale el bus**. La oficina queda
   al frente de la estación Universidad del Metro y el bus sale de la Estación
   Universidad – Calle Carabobo: dos sitios distintos con casi el mismo nombre.

Se imprime la transcripción completa (`-s` para verla) por la lección del
19-ago-2026: doce guiones pasaron sesenta y tres chequeos verdes y el bot igual
perdía ventas. Los asserts vigilan lo afirmable sin leer; la transcripción está
para que una persona la lea.

Nombres inventados (regla #8: el repo es público).
"""
from __future__ import annotations

import re

import pytest

from app.services import llm_engine

#: Las piezas de la dirección. `_LOCAL` y `_CALLE` toleran cómo el modelo
#: reescribe la nomenclatura ("N°" / "No." / "#", "Local" con o sin coma).
_CENTRO_COMERCIAL = re.compile(r"bosque\s*plaza", re.IGNORECASE)
_CALLE = re.compile(r"(calle\s*)?73\s*(n[°ºo]?\.?|#)?\s*51\s*d\s*[-–]\s*71",
                    re.IGNORECASE)
_LOCAL = re.compile(r"local\s*#?\s*1087", re.IGNORECASE)
_REFERENCIAS = re.compile(r"universidad|jard[ií]n\s*bot[aá]nico", re.IGNORECASE)
#: El punto de salida del viaje, que NO es la oficina.
_CARABOBO = re.compile(r"carabobo", re.IGNORECASE)
#: La pregunta del nombre, en las formas en que el modelo la escribe (gemela de
#: la de `test_guiones_primer_mensaje.py`).
_PIDE_EL_NOMBRE = re.compile(
    r"con qui[eé]n tengo el gusto|c[oó]mo te llamas|cu[aá]l es tu nombre|"
    r"tu nombre\?|me regalas tu nombre",
    re.IGNORECASE,
)


def _dicho(salida) -> str:
    return " ".join(
        a["payload"].get("text", "")
        for a in salida["actions"] if a["type"] == "say"
    )


def _tools(salida) -> set:
    return {t["tool"] for t in salida["telemetry"]["tools"]}


def _transcribir(titulo: str, turnos: list) -> None:
    print(f"\n{'=' * 68}\n{titulo}\n{'=' * 68}")
    for quien, texto, marcas in turnos:
        prefijo = "CLIENTE " if quien == "cliente" else "BOT     "
        cuerpo = texto.strip() or "(no envió nada)"
        for i, linea in enumerate(cuerpo.split("\n")):
            print(f"{prefijo if i == 0 else '        '}| {linea}")
        if marcas:
            print(f"        · [{', '.join(sorted(marcas))}]")
    print("=" * 68)


def _conversar(bot, mensajes, estado=None, runtime=None):
    salidas, turnos = [], []
    for mensaje in mensajes:
        salida = llm_engine.advance(bot, estado, mensaje, runtime=runtime)
        salidas.append(salida)
        turnos.append(("cliente", mensaje or "(abre el chat)", set()))
        turnos.append(("bot", _dicho(salida), _tools(salida)))
        estado = salida.get("next_state")
    return salidas, turnos


@pytest.fixture
def bot_viajes():
    """El bot tal como se despacha, leído de `app/data/bot_viajes.py`."""
    from tests.viajes.conftest import BotViajes

    return BotViajes()


# ---------------------------------------------------------------------------
# La contesta, y completa
# ---------------------------------------------------------------------------

class TestContestaLaDireccion:
    @pytest.mark.parametrize("pregunta", [
        "¿dónde quedan ubicados?",
        "buenas, ¿cuál es la dirección de la agencia?",
        "hola, ¿tienen oficina en Medellín? quiero ir personalmente",
        "¿cómo llego hasta donde ustedes?",
    ])
    def test_la_da_sin_escalar(self, bot_viajes, modelo_real, pregunta):
        modelo_real["actual"] = "dirección · pregunta directa"
        salidas, turnos = _conversar(
            bot_viajes, [pregunta], runtime={"contact_name": "Mariana"}
        )
        _transcribir(f"DIRECCIÓN — {pregunta}", turnos)
        texto = _dicho(salidas[0])

        assert "escalar_a_asesor" not in _tools(salidas[0]), (
            "escaló una pregunta cuya respuesta está escrita en el contexto"
        )
        assert _CENTRO_COMERCIAL.search(texto), "no nombró el Centro Comercial"
        assert _CALLE.search(texto), "no dio la nomenclatura de la calle"
        assert _LOCAL.search(texto), "no dio el local"
        assert _REFERENCIAS.search(texto), (
            "dio la dirección sin ninguna referencia: en esa zona la gente se "
            "ubica por el Metro y el Jardín Botánico, y vuelve a preguntar"
        )

    def test_tambien_la_da_en_el_primer_mensaje(self, bot_viajes, modelo_real):
        """Preguntar la dirección de entrada es una de las excepciones del
        mensaje de apertura: se contesta lo que preguntó, no la info general.

        **Lo que este test NO afirma**, a propósito: que además cierre con la
        pregunta del nombre. El documento lo pide ("sea cual sea el primer
        mensaje que mandes, termina con la pregunta del nombre") y el modelo no
        lo cumple — pero eso **ya pasaba antes de este cambio**: se reprodujo
        contra el contexto de producción con "¿qué tours incluye el plan?", que
        falla igual. Es una debilidad vieja de la excepción, no algo que trajo
        la dirección.

        Se intentó cerrarla y salió peor: meter "¿dónde quedan?" en la lista de
        la excepción dejó la regla del nombre en 9/16 (baseline 15/16), y
        repetir la frase del saludo en la sección la hundió a 0/20. Afirmarlo
        aquí sería fijar una expectativa que el bot no cumple; queda anotado
        como pendiente en la BITACORA.
        """
        modelo_real["actual"] = "dirección · en el primer mensaje"
        salidas, turnos = _conversar(bot_viajes, ["Hola, ¿dónde están ubicados?"])
        _transcribir("DIRECCIÓN — primer mensaje", turnos)
        texto = _dicho(salidas[0])

        assert _CENTRO_COMERCIAL.search(texto)
        assert _LOCAL.search(texto)
        assert "escalar_a_asesor" not in _tools(salidas[0])


# ---------------------------------------------------------------------------
# Y no se la da a quien preguntó otra cosa
# ---------------------------------------------------------------------------

class TestNoConfundeLaOficinaConLaSalidaDelBus:
    def test_de_donde_sale_el_bus_es_carabobo(self, bot_viajes, modelo_real):
        modelo_real["actual"] = "salida del bus ≠ oficina"
        salidas, turnos = _conversar(
            bot_viajes,
            ["¿de dónde sale el bus el viernes?"],
            runtime={"contact_name": "Mariana"},
        )
        _transcribir("SALIDA DEL BUS — no es la oficina", turnos)
        texto = _dicho(salidas[0])

        assert _CARABOBO.search(texto), (
            "no dijo el punto de salida real (Estación Universidad – Calle "
            "Carabobo)"
        )
        assert not _LOCAL.search(texto), (
            "mandó a alguien a esperar el bus en el local de la oficina"
        )

    def test_el_horario_de_atencion_sigue_yendo_a_un_asesor(
        self, bot_viajes, modelo_real
    ):
        """Saber dónde queda la oficina no lo vuelve experto en la oficina."""
        modelo_real["actual"] = "horario de la oficina · escala"
        salidas, turnos = _conversar(
            bot_viajes,
            ["¿en qué horario atienden en la oficina? ¿los domingos abren?"],
            runtime={"contact_name": "Mariana"},
        )
        _transcribir("HORARIO DE LA OFICINA — escala", turnos)
        assert "escalar_a_asesor" in _tools(salidas[0]), (
            "inventó un horario de atención en vez de pasar a un compañero"
        )
