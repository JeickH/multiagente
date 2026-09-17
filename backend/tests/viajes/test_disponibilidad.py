"""El bot no confirma una fecha que no consultó (#383).

La clienta pregunta «¿el 18 de septiembre sigue?» y el bot a veces contesta que
sí **sin haber llamado `consultar_tarifario`**. Se veía como un test inestable
—`test_guiones_continuidad.py::TestRetomaAlDiaSiguiente` fallaba ~6% de las
veces en el `assert "consultar_tarifario" in tools`— pero el defecto es peor que
eso: es el bot confirmándole a un cliente una salida que no revisó, que puede
estar llena o no existir. La disponibilidad no está en su memoria: vive en el
tarifario y cambia con los cupos.

`_viola_disponibilidad` es el quinto hermano de `_viola_contacto`,
`_viola_ficha`, `_viola_link` y `_viola_duracion`.

**Lo que más se prueba acá son los falsos positivos**, uno por uno. Un
guardarraíl que le tumba turnos a un bot que estaba respondiendo bien termina
apagado, y entonces no protege nada. Por eso exige las DOS condiciones juntas:
una fecha o salida concreta Y una afirmación de disponibilidad.

Los tests no cuestan un centavo: la función es pura y el turno completo va con
el modelo mockeado, como en `test_duracion.py`.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine

CFG = LLM_CONFIG


def viola(texto, *, tools=()):
    return llm_engine._viola_disponibilidad(
        CFG, [texto], [{"tool": t} for t in tools]
    )


# ---------------------------------------------------------------------------
# Lo que SÍ es afirmar disponibilidad sin haber mirado
# ---------------------------------------------------------------------------

class TestElCasoDelBug:
    def test_le_confirma_la_fecha_que_le_preguntaron(self):
        """El turno exacto del guion: la clienta vuelve al día siguiente y
        pregunta por el 18 de septiembre."""
        assert viola("¡Sí, el 18 de septiembre sigue disponible! 🌴 "
                     "¿Para cuántas personas sería?")

    @pytest.mark.parametrize("texto", [
        "Claro que sí, para el *11 al 14* todavía hay cupo 🌴",
        "Para el 11 al 14 quedan 3 cupos.",
        "Sí hay cupos para septiembre, ¿cuántas personas viajan?",
        "En octubre tenemos disponibilidad para el plan 🌴",
        "El 18 sí sale, es la salida de ese fin de semana.",
        "La salida del 11 al 14 está disponible todavía.",
    ])
    def test_afirmar_cupo_sobre_una_fecha_concreta(self, texto):
        assert viola(texto)

    @pytest.mark.parametrize("texto", [
        "La salida del 18 de septiembre ya no tiene cupos, se agotó 😔",
        "Para el 11 al 14 ya no hay cupos, se llenó esa semana.",
        "Septiembre está agotado, te ofrezco octubre.",
    ])
    def test_negarla_tambien_dispara(self, texto):
        """Decirle que NO hay cupo sin mirar es igual de grave: le tumba el
        viaje a alguien por una salida que a lo mejor sí tiene puestos."""
        assert viola(texto)

    def test_una_frase_afirmativa_en_medio_de_preguntas_no_se_salva(self):
        """El `¿` marca dónde empieza la pregunta. Descartar la frase entera
        por tener un `?` al final dejaría pasar justo este caso."""
        assert viola("Sí hay cupos para septiembre, ¿cuántas personas viajan?")


class TestCuandoSiConsulto:
    def test_despues_de_llamar_la_herramienta_pasa(self):
        """El caso bueno: el dato salió del tarifario en este mismo turno."""
        assert not viola(
            "¡Sí, el 18 de septiembre sigue disponible! 🌴",
            tools=["consultar_tarifario"],
        )

    def test_otra_herramienta_no_lo_habilita(self):
        assert viola(
            "¡Sí, el 18 de septiembre sigue disponible! 🌴",
            tools=["enviar_media", "registrar_nombre"],
        )


# ---------------------------------------------------------------------------
# Los falsos positivos — lo que decide si el guardarraíl sirve o estorba
# ---------------------------------------------------------------------------

class TestLoQueNoPuedeDisparar:
    @pytest.mark.parametrize("texto", [
        "Déjame consultar si el 18 de septiembre sigue disponible y te confirmo 😊",
        "Permíteme reviso la disponibilidad del 11 al 14 y ya te digo.",
        "Dame un momento, voy a revisar si en septiembre quedan cupos 🌴",
        "Ya te confirmo si el 18 sigue disponible 🌴",
        "Estoy revisando la disponibilidad del 11 al 14, un momento 😊",
    ])
    def test_anunciar_que_va_a_consultar_es_lo_correcto(self, texto):
        """Es exactamente lo que se quiere que haga. Casi siempre la frase de
        disponibilidad viene dentro («déjame confirmar si el 18 sigue»), así
        que sin esta excepción el guardarraíl castigaría el buen comportamiento."""
        assert not viola(texto)

    @pytest.mark.parametrize("texto", [
        "¿Para qué mes lo estás pensando? 😊",
        "¿Tienes una fecha en mente para el viaje? 🌴",
    ])
    def test_todavia_no_hay_fecha(self, texto):
        assert not viola(texto)

    def test_la_verdad_general_del_catalogo(self):
        """El documento lo autoriza sin consultar: hay salidas entre semana."""
        assert not viola("Tenemos salidas entre semana también, de lunes a "
                         "jueves 🌴")

    @pytest.mark.parametrize("texto", [
        "El plan a Tolú sale el viernes y regresa el lunes, con hotel, "
        "transporte y alimentación 🌴",
        "Manejamos tres hoteles: Amor de Dios, Piedra Mar y Bohíos 🏨",
        "🚌 *Viernes – Viaje*: salida entre 6:00 y 9:00 pm desde la Estación "
        "Universidad.",
        "Se aparta el cupo con el 30% y el saldo 8 días antes del viaje 🤗",
        "Recibimos Bancolombia, Davivienda, Bre-B y tarjetas 💳",
        "Los precios de septiembre arrancan en $460.000 por persona.",
        "SEPTIEMBRE 11 AL 14 — $460.000 por persona, 2 noches / 3 días",
        "Para el 11 al 14 son 2 noches y 3 días 🌴",
    ])
    def test_hablar_del_plan_de_los_pagos_o_de_los_precios(self, texto):
        """Nada de esto afirma cupo, aunque nombre fechas y salidas."""
        assert not viola(texto)

    def test_la_oficina_queda_en_un_lugar_no_queda_un_cupo(self):
        """«Queda» a secas no es disponibilidad, y por eso no está en la lista:
        la oficina *queda* en el Bosque Plaza."""
        assert not viola("La oficina queda en el Bosque Plaza, Local 1087, "
                         "en septiembre atendemos de 9 a 6 📍")

    def test_preguntar_por_la_fecha_no_es_afirmarla(self):
        assert not viola("¿El 18 de septiembre te sirve, o prefieres el 11 al 14?")

    def test_el_porcentaje_del_anticipo_no_es_una_fecha(self):
        """«el 30%» no es el día 30. Sin esta exclusión, un mensaje de pagos con
        un «quedan cupos» al final dispararía sin haber nombrado fecha alguna."""
        assert not viola("Se aparta con el 30% y quedan cupos, ¿te cuento?")

    def test_sin_tarifario_no_aplica(self):
        """Está acotado al bot que tiene tarifario: mascotas, el institucional
        y Natulcé no se mueven."""
        assert not llm_engine._viola_disponibilidad(
            {"context_key": "gloma"},
            ["¡Sí, el 18 de septiembre sigue disponible! 🌴"], [],
        )

    def test_sin_texto_no_aplica(self):
        assert not viola("")


# ---------------------------------------------------------------------------
# El turno completo: el guardarraíl tumba la ronda y el modelo la rehace
# ---------------------------------------------------------------------------

class BotViajesFake:
    id = 12
    engine = "llm"

    def __init__(self, cfg=None):
        self.llm_config = json.dumps(cfg or dict(LLM_CONFIG), ensure_ascii=False)


def _resp(texto, stop="end_turn"):
    return {"content": [{"type": "text", "text": texto}], "stop_reason": stop}


#: Con historial: preguntar por una fecha nunca es el primer mensaje, y así el
#: turno no arrastra la pregunta del nombre que el motor agrega en el primero
#: (#379), que acá sería ruido.
HISTORIA = {"history": [
    {"role": "user", "content": "Hola, soy Marcela"},
    {"role": "assistant", "content": "¡Un gusto, Marcela! 🌴"},
]}


def _corre(textos_del_modelo):
    cola = list(textos_del_modelo)

    def responder(model_id, system, messages, tools):
        return _resp(cola.pop(0))

    with patch.object(llm_engine, "_invoke_model") as mock:
        mock.side_effect = responder
        salida = llm_engine.advance(
            BotViajesFake(), dict(HISTORIA), "¿el 18 de septiembre sigue?",
            runtime={"contact_name": "Marcela"},
        )
    dichos = [a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"]
    return dichos, mock


class TestElTurnoCompleto:
    def test_lo_que_afirmo_sin_consultar_no_le_llega_al_cliente(self):
        dichos, mock = _corre([
            "¡Sí! El 18 de septiembre sigue disponible 🌴",
            "Déjame reviso esa fecha y te confirmo en un momento 😊",
        ])

        assert mock.call_count == 2, "el guardarraíl no disparó"
        assert dichos == ["Déjame reviso esa fecha y te confirmo en un momento 😊"]

    def test_la_correccion_le_dice_que_llame_la_herramienta(self):
        _, mock = _corre([
            "¡Sí! El 18 de septiembre sigue disponible 🌴",
            "Déjame reviso esa fecha y te confirmo 😊",
        ])
        segunda = mock.call_args_list[1]
        mensajes = segunda.args[2] if len(segunda.args) >= 3 else segunda.kwargs["messages"]
        correccion = mensajes[-1]["content"]

        assert isinstance(correccion, str) and correccion.startswith("ALTO:")
        assert "consultar_tarifario" in correccion

    def test_un_turno_limpio_no_se_toca(self):
        dichos, mock = _corre(["Con gusto 🌴 ¿Para cuántas personas sería?"])

        assert mock.call_count == 1
        assert dichos == ["Con gusto 🌴 ¿Para cuántas personas sería?"]
