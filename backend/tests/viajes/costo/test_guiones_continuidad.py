"""Los guiones de continuidad contra Claude de verdad, en Bedrock (#377).

**Cuesta plata.** Corre con `--con-costo`. Unos 6 centavos de dólar.

Estos guiones reproducen el chat real del 20-ago-2026 que originó el sprint:
una clienta se despidió, escribió "muchas gracias por todo" y el bot la saludó
desde cero **cuatro veces**, contestando cada "gracias". Ella cerró con *"no
que pereza, por eso no me gusta agregar al guasap porque son muy intensos"*.

Se imprime la transcripción completa de cada guion (`-s` para verla) porque la
lección del proyecto es **probar bots leyendo, no sólo asertando**: en la
prueba del 19-ago-2026 doce guiones pasaron sesenta y tres chequeos verdes y el
bot igual perdía ventas. Los asserts vigilan lo que se puede afirmar sin leer
—que no salude de nuevo, que no pregunte el nombre, que no escriba nada— y la
transcripción está para que una persona la lea.

Teléfonos y nombres son inventados (regla #8: el repo es público).
"""
from __future__ import annotations

import re

import pytest

from app.services import llm_engine

# La misma frase de apertura que salió cuatro veces seguidas en el chat real.
_SALUDO_DE_APERTURA = re.compile(
    r"con qui[eé]n tengo el gusto|c[oó]mo te llamas|cu[aá]l es tu nombre",
    re.IGNORECASE,
)
_SE_PRESENTA = re.compile(
    r"mi nombre es\s*\*?maria camila|soy\s*\*?maria camila", re.IGNORECASE
)


def _dicho(salida) -> str:
    return " ".join(
        a["payload"].get("text", "")
        for a in salida["actions"] if a["type"] == "say"
    )


def _tools(salida) -> set:
    return {t["tool"] for t in salida["telemetry"]["tools"]}


def _transcribir(titulo: str, turnos: list) -> None:
    """Imprime el chat como se vería en la bandeja. Es el entregable de estos
    tests tanto como los asserts."""
    print(f"\n{'=' * 68}\n{titulo}\n{'=' * 68}")
    for quien, texto, marcas in turnos:
        prefijo = "CLIENTA " if quien == "cliente" else "BOT     "
        cuerpo = texto.strip() or "(no envió nada)"
        for i, linea in enumerate(cuerpo.split("\n")):
            print(f"{prefijo if i == 0 else '        '}| {linea}")
        if marcas:
            print(f"        · [{', '.join(sorted(marcas))}]")
    print("=" * 68)


def _conversar(bot, mensajes, estado=None, runtime=None):
    """Encadena turnos y devuelve (salidas, turnos_para_transcribir).

    A diferencia del `conversar` de `test_guiones.py`, éste **no corta** cuando
    la conversación se cierra: lo que se está probando es justamente lo que
    pasa DESPUÉS del cierre.
    """
    salidas, turnos = [], []
    for mensaje in mensajes:
        salida = llm_engine.advance(bot, estado, mensaje, runtime=runtime)
        salidas.append(salida)
        turnos.append(("cliente", mensaje or "(abre el chat)", set()))
        turnos.append(("bot", _dicho(salida), _tools(salida)))
        estado = salida.get("next_state")
    return salidas, turnos


@pytest.fixture
def bot_con_flags():
    """El bot tal como se despacha: con `seguimiento`, `recordar_nombre` y
    `retomar` encendidos. Sale del conftest, que lee `app/data/bot_viajes.py`."""
    from tests.viajes.conftest import BotViajes

    return BotViajes()


class TestSeDespideYVuelveAEscribirGracias:
    """El guion que reproduce el bug tal cual pasó."""

    def test_no_saluda_de_nuevo_ni_insiste(self, bot_con_flags, modelo_real):
        modelo_real["actual"] = "K1 gracias tras el cierre"
        salidas, turnos = _conversar(bot_con_flags, [
            "Hola, soy Marcela",
            "Bueno mañana te respondo, debo consultar con mi esposo",
            "Ok listo mañana te hablo muchas gracias por todo",
            "Gracias",
            "Gracias lo mismo para ti",
        ])
        _transcribir("Se despide y vuelve a escribir «gracias»", turnos)

        # 1. En ningún turno posterior al primero vuelve a presentarse ni a
        #    preguntar el nombre. Esto es lo que se veía cuatro veces.
        for i, salida in enumerate(salidas[1:], start=1):
            texto = _dicho(salida)
            assert not _SALUDO_DE_APERTURA.search(texto), (
                f"turno {i + 1}: volvió a pedir el nombre — {texto!r}"
            )
            assert not _SE_PRESENTA.search(texto), (
                f"turno {i + 1}: se presentó de nuevo — {texto!r}"
            )

        # 2. "Mañana te respondo" es una venta en pausa, no una despedida: no
        #    puede cerrar ahí, o el seguimiento de los 15 minutos nunca corre.
        assert "finalizar_conversacion" not in _tools(salidas[1]), (
            "cerró en un «mañana te respondo»: eso apaga el seguimiento"
        )

        # 3. En algún momento de los tres «gracias» deja de contestar. Da igual
        #    en cuál: lo que no puede es contestar los tres.
        cierres = [
            i for i, s in enumerate(salidas[2:], start=2)
            if _tools(s) & {"no_responder", "finalizar_conversacion"}
        ]
        assert cierres, (
            "contestó los tres agradecimientos sin cerrar nunca: "
            f"{[_dicho(s) for s in salidas[2:]]!r}"
        )

        # 4. Y donde usó `no_responder`, no salió ni una letra.
        for salida in salidas:
            if "no_responder" in _tools(salida):
                assert not _dicho(salida).strip(), (
                    f"dijo `no_responder` y escribió igual: {_dicho(salida)!r}"
                )
                assert not salida["actions"] or all(
                    a["type"] == "end" for a in salida["actions"]
                )

    def test_el_atajo_determinista_atrapa_los_gracias_del_chat_real(self):
        """Los que ni siquiera llegan a Bedrock. Esta parte no cuesta nada:
        son los mensajes textuales del chat, con el número enmascarado."""
        del_chat_real = [
            "Gracias", "Gracias lo mismo para ti", "Ya  me atendistes",
        ]
        for mensaje in del_chat_real:
            assert llm_engine.es_cortesia(mensaje), mensaje
        # Y los que sí merecen respuesta, del mismo chat.
        for mensaje in ["Cuántos días es lo que anuncian", "El sábado te confirmo",
                        "Eso es cada ocho dias"]:
            assert not llm_engine.es_cortesia(mensaje), mensaje


class TestRetomaAlDiaSiguiente:
    """La persona vuelve al día siguiente. El bot tiene el historial y el
    nombre: no puede empezar de cero."""

    def test_sigue_donde_quedaron(self, bot_con_flags, modelo_real):
        modelo_real["actual"] = "K2 retoma al día siguiente"
        primeras, turnos = _conversar(bot_con_flags, [
            "Hola, soy Marcela",
            "para septiembre",
            "listo, muchas gracias, chao",
        ])
        estado = primeras[-1].get("next_state")
        assert estado is not None, (
            "el historial se perdió al cerrar: sin él no hay nada que retomar"
        )

        # Al día siguiente: misma sesión, con el aviso de que se retoma y el
        # nombre ya guardado en la ficha del contacto.
        runtime = {"contact_name": "Marcela", "retomada": True, "desde": "ayer"}
        segundas, turnos_2 = _conversar(
            bot_con_flags, ["Hola, ya hablé con mi esposo, ¿el 18 de septiembre sigue?"],
            estado=estado, runtime=runtime,
        )
        _transcribir("Retoma al día siguiente", turnos + turnos_2)

        texto = _dicho(segundas[0])
        assert not _SALUDO_DE_APERTURA.search(texto), (
            f"le preguntó el nombre a quien ya se lo dijo ayer: {texto!r}"
        )
        assert not _SE_PRESENTA.search(texto), (
            f"se presentó de nuevo como si fuera la primera vez: {texto!r}"
        )
        assert "consultar_tarifario" in _tools(segundas[0]), (
            f"no fue a buscar la fecha que le preguntaron: {texto!r}"
        )

    def test_registra_el_nombre_en_el_turno_en_que_se_presenta(
        self, bot_con_flags, modelo_real
    ):
        """Sin esto el nombre sólo vive en el historial de la sesión, y se
        pierde cuando la sesión se acaba — que es justo lo que pasó en el chat
        que originó este arreglo."""
        modelo_real["actual"] = "K3 registrar nombre"
        salidas, turnos = _conversar(bot_con_flags, [
            "Hola, quiero información del plan",
            "Marcela",
        ])
        _transcribir("Se presenta: el nombre queda en la ficha", turnos)

        llamadas = [
            t for s in salidas for t in s["telemetry"]["tools"]
            if t["tool"] == "registrar_nombre"
        ]
        assert llamadas, "no guardó el nombre: se perderá al cerrar la sesión"
        assert "Marcela" in str(llamadas[0]["input"].get("nombre", ""))
        perfiles = [
            a for s in salidas for a in s["actions"] if a["type"] == "perfil"
        ]
        assert perfiles and perfiles[0]["payload"]["nombre"] == "Marcela"


class TestLaVentaEnPausaNoSeCierra:
    """Si el bot cierra en un «lo pienso», el seguimiento de los 15 minutos no
    corre nunca — y ese seguimiento es la mitad del pedido del CEO."""

    @pytest.mark.parametrize("pausa", [
        "Bueno mañana te respondo, debo consultar con mi esposo",
        "listo, gracias! luego te escribo para reservar",
        "lo voy a pensar y te confirmo",
        "El sábado te confirmo",
    ])
    def test_no_llama_a_finalizar(self, bot_con_flags, modelo_real, pausa):
        modelo_real["actual"] = "K4 venta en pausa"
        salidas, turnos = _conversar(bot_con_flags, ["Hola, soy Marcela", pausa])
        _transcribir(f"Venta en pausa: «{pausa}»", turnos)

        assert "finalizar_conversacion" not in _tools(salidas[-1]), (
            f"cerró una venta en pausa: {_dicho(salidas[-1])!r}"
        )
        assert not salidas[-1]["finished"]
        # Y contesta corto: no es momento de mandarle más material.
        assert not [a for a in salidas[-1]["actions"] if a["type"] == "say_media"], (
            "le mandó material a alguien que dijo que lo iba a pensar"
        )
