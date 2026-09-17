"""Las dos mitades de la pregunta del nombre: se agrega si falta (#379) y se
quita si sobra (#382).

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

**La otra mitad (#382): a quien ya está identificado no se le pregunta.** El
modelo a veces pega la apertura enlatada completa —termina en "¿Con quién tengo
el gusto? 😊"— aunque el nombre ya esté en la ficha. Medido: ~8% de los turnos,
en las dos ramas (13 corridas en main con 1 fallo, 22 en la de trabajo con 2),
así que no es una regresión: viene de antes. De cara al cliente es feo, te
saluda por tu nombre y en la misma frase te pregunta cómo te llamas.

Se arregla en código por la misma razón que la primera mitad: el prompt ya se lo
pide en `_bloque_continuidad` y el modelo *elige* entre las dos reglas. Cuando
elige —en vez de olvidarse— insistir en el prompt empata con el baseline.

Estos tests no cuestan un centavo: las dos mitades son funciones puras y el
modelo va mockeado con `patch.object(llm_engine, "_invoke_model")`.
"""
from __future__ import annotations

import json
from unittest.mock import patch

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


# ---------------------------------------------------------------------------
# #382 · La otra mitad: a quien ya está identificado no se le pregunta
# ---------------------------------------------------------------------------

def quita(texto: str) -> str:
    return llm_engine._sin_pregunta_por_el_nombre(texto)


#: El mensaje de apertura tal como lo manda el documento, con el nombre puesto:
#: la pregunta va de última, en su propio párrafo. Es la forma exacta en que
#: sale el defecto.
APERTURA = (
    "¡Hola Marcela! 😊 Soy *Luisa*, asesora de la *Agencia de Viajes "
    "Arranquemos Pues*. Te cuento de nuestro *Plan a Tolú & Coveñas* 🌴: "
    "salida el *viernes* y regreso el *lunes*, con hotel, transporte y "
    "alimentación desde el desayuno del sábado.\n"
    "\n"
    "Así es el plan día a día 👇\n"
    "🚌 *Viernes – Viaje*: salida entre 6:00 y 9:00 pm aprox.\n"
    "📍 *Sábado – Caimanera*: tour a la Ciénaga de La Caimanera 🌿\n"
    "📍 *Domingo – Tolú*: tour a Tolú, ideal para compras 🛍️\n"
    "🚌 *Lunes – Regreso*: desayuno y salida entre 9:00 a.m. y 1:00 p.m.\n"
    "\n"
    "¿Con quién tengo el gusto? 😊"
)
#: Lo mismo sin el último párrafo. Todo lo demás tiene que sobrevivir intacto:
#: descartar el turno costaría el itinerario, que es lo que vende el plan.
APERTURA_SIN_LA_PREGUNTA = APERTURA.rsplit("\n\n", 1)[0]


class TestElRecorteEsQuirurgico:
    """Se va la frase, no el mensaje."""

    def test_la_apertura_entera_pierde_solo_la_ultima_linea(self):
        assert quita(APERTURA) == APERTURA_SIN_LA_PREGUNTA

    def test_al_final_de_un_parrafo_no_deja_el_emoji_huerfano(self):
        """El "😊" era de la pregunta: si se queda, es el rastro de que aquí se
        recortó algo."""
        assert quita("¡Hola Marcela! 🌴 Te cuento del plan. "
                     "¿Con quién tengo el gusto? 😊") == (
            "¡Hola Marcela! 🌴 Te cuento del plan."
        )

    def test_en_su_propia_linea_se_va_la_linea_entera(self):
        assert quita("Manejamos tres hoteles 🏨.\n"
                     "¿Cuál es tu nombre?\n"
                     "Dime para qué mes lo estás pensando.") == (
            "Manejamos tres hoteles 🏨.\nDime para qué mes lo estás pensando."
        )

    def test_en_el_medio_no_deja_doble_espacio(self):
        assert quita("Claro que sí 🌴 ¿Cómo te llamas? "
                     "Te paso el itinerario.") == (
            "Claro que sí 🌴 Te paso el itinerario."
        )

    def test_al_principio_no_deja_el_espacio_de_adelante(self):
        assert quita("¿Cómo te llamas? Mientras tanto te cuento el plan 🌴") == (
            "Mientras tanto te cuento el plan 🌴"
        )

    def test_lo_que_iba_antes_de_la_pregunta_se_queda(self):
        """El "¿" es frontera dura en español: lo de antes no es la pregunta.
        Sin esto, un párrafo mal puntuado se perdería entero."""
        assert quita("Marcela, el plan sale el viernes y regresa el lunes, "
                     "¿con quién tengo el gusto? 😊") == (
            "Marcela, el plan sale el viernes y regresa el lunes"
        )

    def test_el_prefijo_no_queda_pegado_a_la_frase_siguiente(self):
        assert quita("Cuéntame, ¿cómo te llamas? Te paso el itinerario.") == (
            "Cuéntame. Te paso el itinerario."
        )

    def test_aunque_el_modelo_se_coma_el_signo_de_apertura(self):
        assert quita("Hola Marcela, con quién tengo el gusto? 😊") == "Hola Marcela"

    def test_el_parrafo_de_la_pregunta_no_deja_renglon_en_blanco_de_mas(self):
        assert quita("Hola 🌴\n\n¿Con quién tengo el gusto? 😊\n\n"
                     "El plan sale el viernes.") == (
            "Hola 🌴\n\nEl plan sale el viernes."
        )

    @pytest.mark.parametrize("texto", [
        "¿Con quién tengo el gusto? 😊",
        "¿Quién eres?",
    ])
    def test_un_mensaje_que_era_solo_la_pregunta_se_queda_en_nada(self, texto):
        """No se manda un mensaje vacío: el motor descarta esa acción."""
        assert quita(texto) == ""


class TestLoQueNoSeToca:
    @pytest.mark.parametrize("texto", [
        "¡Hola Marcela! 🌴 ¿Para qué mes lo estás pensando? 😊",
        "Listo Marcela 🙌 ¿me confirmas cuántas personas viajan?",
        "El plan incluye dos tours 🌴 ¿Te ayudo en algo más? 😊",
        "Ya tengo tu nombre en la ficha, Marcela 😊",
        "Me dijiste cómo te llamas al principio, Marcela.",
    ])
    def test_el_texto_sale_caracter_por_caracter_igual(self, texto):
        """Si el modelo no preguntó el nombre, el mensaje es suyo y no se toca:
        ni un espacio, ni un emoji."""
        assert quita(texto) == texto

    @pytest.mark.parametrize("texto", [
        "Para reservar necesito tu nombre completo, cédula, número de personas "
        "y fecha de viaje 📝",
        "¿Me regalas tu nombre completo y la cédula para apartar el cupo?",
        "¿Me confirmas tu nombre como aparece en el documento?",
    ])
    def test_los_datos_de_la_reserva_no_son_la_pregunta_del_saludo(self, texto):
        """El *nombre completo* con la cédula es para apartar el cupo, y el bot
        lo necesita aunque ya sepa que la clienta se llama Marcela. Borrarlo
        dejaría al cliente sin el mensaje con el que se cierra la venta."""
        assert quita(texto) == texto


# ---------------------------------------------------------------------------
# El turno completo, con el modelo mockeado (no cuesta un centavo)
# ---------------------------------------------------------------------------

class BotDePrueba:
    """Un bot cualquiera con la `llm_config` que le den."""

    id = 12
    engine = "llm"
    status = "active"

    def __init__(self, cfg: dict) -> None:
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


def turno(texto_del_modelo, *, cfg=None, estado=None,
          mensaje="Hola, quiero mas informacion", **runtime):
    """Un turno entero con el modelo diciendo lo que se le pase."""
    respuesta = {
        "content": [{"type": "text", "text": texto_del_modelo}],
        "stop_reason": "end_turn",
    }
    bot = BotDePrueba(cfg if cfg is not None else dict(LLM_CONFIG))
    with patch.object(llm_engine, "_invoke_model", return_value=respuesta):
        return llm_engine.advance(bot, estado, mensaje, runtime=dict(runtime))


def dichos(salida) -> list:
    return [a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"]


class TestElTurnoConElNombreSabido:
    def test_el_nombre_del_canal_evita_la_pregunta(self):
        """El caso del guion `test_el_nombre_del_canal_tambien_evita_la_pregunta`,
        que fallaba 1 de cada 12 corridas."""
        salida = turno(APERTURA, contact_name="Marcela")

        assert dichos(salida) == [APERTURA_SIN_LA_PREGUNTA]

    def test_y_el_itinerario_sigue_completo(self):
        """Lo que se perdería si el turno se descartara en vez de recortarlo."""
        texto = dichos(turno(APERTURA, contact_name="Marcela"))[0]

        for pieza in ("viernes", "sábado", "domingo", "lunes", "Caimanera",
                      "Tolú", "9:00 pm"):
            assert pieza.lower() in texto.lower(), f"se perdió {pieza!r}"

    def test_la_sesion_retomada_tampoco_repregunta(self):
        """El otro guion intermitente: vuelve al día siguiente y el bot tiene
        el nombre en la ficha."""
        estado = {"history": [
            {"role": "user", "content": "Hola, soy Marcela"},
            {"role": "assistant", "content": "¡Un gusto, Marcela! 🌴"},
        ]}
        salida = turno(
            "¡Hola de nuevo, Marcela! 🌴 Claro, el 18 de septiembre sigue "
            "disponible. ¿Con quién tengo el gusto? 😊",
            estado=estado, mensaje="¿el 18 de septiembre sigue?",
            contact_name="Marcela", retomada=True, desde="ayer",
        )

        assert dichos(salida) == [
            "¡Hola de nuevo, Marcela! 🌴 Claro, el 18 de septiembre sigue "
            "disponible."
        ]

    def test_el_historial_guarda_el_texto_recortado(self):
        """Si el historial se quedara con la pregunta, el modelo se copiaría a
        sí mismo en el turno siguiente."""
        salida = turno(APERTURA, contact_name="Marcela")
        guardado = salida["next_state"]["history"][-1]["content"]

        assert not llm_engine._PIDE_EL_NOMBRE.search(guardado)
        assert "Caimanera" in guardado

    def test_si_el_modelo_no_pregunta_no_se_toca_nada(self):
        """Ni se recorta ni se agrega: el turno sale tal cual lo redactó."""
        texto = "¡Hola Marcela! 🌴 ¿Para qué mes lo estás pensando? 😊"

        assert dichos(turno(texto, contact_name="Marcela")) == [texto]

    def test_un_mensaje_que_era_solo_la_pregunta_no_sale_vacio(self):
        """La acción se cae entera: WhatsApp no recibe un mensaje en blanco."""
        salida = turno("¿Con quién tengo el gusto? 😊", contact_name="Marcela")

        assert dichos(salida) == []

    def test_el_material_adjunto_no_se_pierde(self):
        """La razón de recortar en vez de descartar el turno: descartarlo se
        lleva por delante el flyer que el bot ya mandó."""
        respuestas = [
            {
                "content": [{"type": "tool_use", "id": "t1",
                             "name": "enviar_media",
                             "input": {"claves": ["info_amordios"]}}],
                "stop_reason": "tool_use",
            },
            {
                "content": [{"type": "text", "text": "¡Hola Marcela! 🌴 Ahí te "
                                                     "dejo la info del hotel. "
                                                     "¿Con quién tengo el gusto? 😊"}],
                "stop_reason": "end_turn",
            },
        ]
        bot = BotDePrueba(dict(LLM_CONFIG))
        with patch.object(llm_engine, "_invoke_model", side_effect=respuestas):
            salida = llm_engine.advance(
                bot, None, "¿qué hoteles manejan?",
                runtime={"contact_name": "Marcela"},
            )

        assert [a["type"] for a in salida["actions"]] == ["say_media", "say"]
        assert dichos(salida) == [
            "¡Hola Marcela! 🌴 Ahí te dejo la info del hotel."
        ]


class TestElTurnoSinSaberElNombre:
    def test_la_pregunta_del_modelo_se_respeta(self):
        salida = turno(APERTURA)

        assert dichos(salida) == [APERTURA]

    def test_y_si_no_la_hizo_se_le_agrega(self):
        """La primera mitad (#379) sigue viva: es la que no puede romperse al
        agregar la segunda."""
        salida = turno("El plan incluye dos tours 🌴 ¿Te ayudo en algo más? 😊")

        assert dichos(salida)[-1] == LLM_CONFIG["pregunta_nombre"]

    def test_un_nombre_que_no_sirve_es_no_saber_el_nombre(self):
        """`nombre_saneado` rechaza un teléfono en el campo del nombre; ahí el
        bot sigue sin saber cómo se llama."""
        salida = turno("El plan incluye dos tours 🌴", contact_name="3001112233")

        assert dichos(salida)[-1] == LLM_CONFIG["pregunta_nombre"]


class TestElAlcanceSigueSiendoDeEsteBot:
    """`llm_engine` lo comparten el bot de mascotas, el institucional y
    Natulcé. Un recorte global les movería el comportamiento — que es justo lo
    que pasó con el aviso de "no leo imágenes" (commit 1a7d385)."""

    def test_un_bot_sin_recordar_nombre_no_se_toca(self):
        salida = turno(
            "¡Hola Marcela! Soy Lía 🤍 ¿Con quién tengo el gusto?",
            cfg={"context_key": "gloma"}, contact_name="Marcela",
        )

        assert dichos(salida) == [
            "¡Hola Marcela! Soy Lía 🤍 ¿Con quién tengo el gusto?"
        ]

    def test_ni_el_de_mascotas_con_el_nombre_en_la_ficha(self):
        salida = turno(
            "¡Hola Marcela! 🐾 ¿Con quién tengo el gusto?",
            cfg={"context_key": "mascotas"}, contact_name="Marcela",
        )

        assert dichos(salida) == ["¡Hola Marcela! 🐾 ¿Con quién tengo el gusto?"]


class TestLasDosMitadesNoSePisan:
    """Una agrega la pregunta y la otra la quita: no pueden dispararse en el
    mismo turno. En el motor van en ramas contrarias del mismo `if`, y las dos
    se deciden con `_ya_se_sabe_el_nombre`."""

    @pytest.mark.parametrize("runtime", [
        {},
        {"contact_name": "Marcela"},
        {"contact_name": ""},
        {"contact_name": "   "},
        {"contact_name": "3001112233"},
        {"contact_name": "Marcela", "retomada": True},
        {"retomada": True},
    ])
    @pytest.mark.parametrize("dicho", [
        "Te cuento del plan 🌴",
        "Te cuento del plan 🌴 ¿Con quién tengo el gusto? 😊",
        "",
    ])
    def test_nunca_las_dos_a_la_vez(self, runtime, dicho):
        cfg = _cfg(**runtime)
        se_quita = llm_engine._ya_se_sabe_el_nombre(cfg)
        se_agrega = llm_engine._falta_pedir_el_nombre(
            cfg, [], [dicho] if dicho else [], [], False
        )
        assert not (se_quita and se_agrega)

    def test_la_condicion_es_una_sola(self):
        """Si alguien le pusiera otra determinación a una de las mitades, las
        dos podrían desincronizarse. Con el nombre sabido, la que agrega se
        calla por esta misma función."""
        cfg = _cfg(contact_name="Marcela")

        assert llm_engine._ya_se_sabe_el_nombre(cfg)
        assert not llm_engine._falta_pedir_el_nombre(
            cfg, [], ["Te cuento del plan 🌴"], [], False
        )
