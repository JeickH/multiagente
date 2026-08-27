"""#379: el primer mensaje sale siempre con la pregunta del nombre.

El documento ya lo ordena y el modelo lo cumple ~4 de cada 5 veces. Falla justo
cuando la persona abre con una pregunta concreta ("¿qué tours incluye?"): el bot
la contesta y gasta su única pregunta —la regla de *una pregunta por mensaje*—
en el mes o en un "¿te ayudo en algo más?", y el nombre se pierde. Sin nombre no
hay `registrar_nombre`, y sin eso vuelve a preguntarlo la semana entrante.

**Por qué es determinista y no otra frase en el prompt.** Se intentó por prompt
dos veces, midiendo contra Bedrock e intercalando las variantes:

    reforzarlo en el bloque de continuidad   12/15  (baseline 12/15)
    nombrarle la pregunta rival en el .md    10/15  (baseline 10/15)

Las dos empataron **exactamente** con el baseline. El modelo no se olvida del
nombre: prefiere la pregunta que sigue al tema, y ninguna insistencia lo movió.
Por eso el nombre se agrega en código.

Estos tests no cuestan un centavo: `_falta_pedir_el_nombre` es una función pura.
"""
from __future__ import annotations

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine


def _cfg(**runtime):
    return {**LLM_CONFIG, "_runtime": dict(runtime)}


def falta(say_texts, *, history=None, tools=(), finished=False, **runtime):
    return llm_engine._falta_pedir_el_nombre(
        _cfg(**runtime),
        list(history or []),
        list(say_texts),
        [{"tool": t} for t in tools],
        finished,
    )


class TestCuandoSeAgrega:
    def test_contesto_la_pregunta_y_no_pidio_el_nombre(self):
        """El caso de #379, tal cual salió en la medición: contesta los tours y
        cierra con un relleno."""
        assert falta(["El plan incluye dos tours 🌴 ¿Te ayudo en algo más? 😊"])

    def test_tampoco_vale_cerrar_con_la_pregunta_del_mes(self):
        """La otra mitad de las fallas. El mes es la pregunta del **segundo**
        mensaje; robársela al primero deja la conversación sin nombre."""
        assert falta(["Los precios cambian según la fecha. "
                      "¿Para qué mes lo estás pensando? 😊"])

    def test_aunque_haya_mandado_material(self):
        """Es justo el turno donde más se pierde: manda el flyer y se le olvida."""
        assert falta(["Te dejo la info de los tours 👆"])


class TestCuandoNoSeToca:
    def test_si_ya_la_hizo_no_se_repite(self):
        assert not falta(["Manejamos tres hoteles 🏨 ¿Con quién tengo el gusto? 😊"])

    @pytest.mark.parametrize("frase", [
        "¿Quién eres? 😊",
        "¿Con quién hablo?",
        "¿Cómo te llamas?",
        "¿Me regalas tu nombre?",
    ])
    def test_ni_cuando_la_escribio_con_otras_palabras(self, frase):
        """Preguntarlo dos veces seguidas con distintas palabras es peor que no
        preguntarlo: es el bot sonando a formulario."""
        assert not falta([f"Claro que sí 🌴 {frase}"])

    def test_no_si_ya_se_sabe_el_nombre(self):
        """Sería el bug #377 otra vez, ahora metido por el guardarraíl."""
        assert not falta(["¡Hola Marcela! Los tours son dos 🌴"],
                         contact_name="Marcela")

    def test_no_en_el_segundo_turno(self):
        """Insistir turno tras turno es la queja que originó #377: "no que
        pereza, por eso no me gusta agregar al guasap porque son muy intensos"."""
        historia = [{"role": "user", "content": "hola"},
                    {"role": "assistant", "content": "¡Hola! ¿Con quién tengo el gusto?"}]
        assert not falta(["Los tours son dos 🌴"], history=historia)

    def test_no_en_una_conversacion_retomada(self):
        """Tiene historial propio aunque llegue vacío por otra vía: no es un
        primer mensaje y saludar de cero es justo lo que #377 arregló."""
        assert not falta(["Seguimos con lo tuyo 🌴"], retomada=True)

    def test_no_cuando_escala_a_un_asesor(self):
        """Quien va a preguntar el nombre es la persona del equipo. Pedirlo
        mientras se hace el traspaso deja al cliente contestándole a nadie."""
        assert not falta(["Te paso con un compañero 💬"], tools=["escalar_a_asesor"])

    def test_no_cuando_acaba_de_registrarlo(self):
        """Se presentó en este mismo turno: repreguntarlo es lo que más delata
        a un bot."""
        assert not falta(["¡Un gusto, Andrés! 🌴"], tools=["registrar_nombre"])

    def test_no_si_la_conversacion_se_cerro(self):
        assert not falta(["¡Que tengas un lindo día! 🌴✨"], finished=True)

    def test_no_si_el_bot_no_escribio_nada(self):
        """`no_responder` deja el turno en silencio a propósito."""
        assert not falta([], tools=["no_responder"])


class TestElAlcanceEsDeEsteBot:
    """`llm_engine` lo comparten mascotas, Gloma, Jerarquía y Talulah."""

    def test_sin_la_clave_del_tenant_no_hace_nada(self):
        cfg = {k: v for k, v in LLM_CONFIG.items() if k != "pregunta_nombre"}
        assert not llm_engine._falta_pedir_el_nombre(
            {**cfg, "_runtime": {}}, [], ["Los tours son dos 🌴"], [], False
        )

    def test_ni_sin_recordar_nombre(self):
        cfg = {k: v for k, v in LLM_CONFIG.items() if k != "recordar_nombre"}
        assert not llm_engine._falta_pedir_el_nombre(
            {**cfg, "_runtime": {}}, [], ["Los tours son dos 🌴"], [], False
        )

    def test_la_frase_es_la_del_tenant(self):
        """Sale de `llm_config` y no del motor: es la voz de la agencia."""
        assert LLM_CONFIG["pregunta_nombre"] == "¿Con quién tengo el gusto? 😊"
