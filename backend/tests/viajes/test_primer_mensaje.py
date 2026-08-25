"""El primer mensaje va completo: info general + itinerario + el nombre (F3).

Pedido del CEO (Sprint 24): quien abre con "hola" o "quiero más información"
debe recibir **un solo mensaje** con la info general del plan, el itinerario y
la pregunta del nombre al final. Antes el bot mandaba un saludo pelado —"¿Con
quién tengo el gusto?"— y la persona tenía que escribir dos veces para
enterarse de qué le estaban vendiendo.

Lo que se prueba aquí es el **prompt renderizado y el clasificador**, no la
redacción del modelo: ambos son deterministas y no cuestan un centavo. Los dos
riesgos reales de esta tarea son de texto, no de código:

1. Que la regla vieja siguiera viva en el documento. El gotcha confirmado del
   proyecto es que **las reglas del prompt se diluyen entre sí**: ya pasó que
   una regla nueva puesta al lado de la de escalar la debilitó y el bot dejó de
   escalar (ver el comentario de `_system_prompt` sobre las notas de voz). Por
   eso hay tests que verifican que las frases viejas **ya no están**, no sólo
   que las nuevas sí.
2. Que el límite de "~8 líneas por mensaje" quedara peleando contra un mensaje
   de apertura que ahora tiene doce. También se verifica su excepción.

Los guiones contra el modelo real viven en
`costo/test_guiones_primer_mensaje.py` y no corren sin `--con-costo`.
"""
from __future__ import annotations

import re

import pytest

from app.data.bot_viajes import CAMINOS, LLM_CONFIG
from app.services import llm_engine


# ---------------------------------------------------------------------------
# Andamiaje
# ---------------------------------------------------------------------------

def _prompt(bot, **runtime) -> str:
    """El `system` tal como le llega a Bedrock, con el runtime que se le pase.

    Es la misma vía que usa `test_continuidad.py` para afirmar sobre las reglas
    (`assert "registrar_nombre" in system`): se afirma sobre el texto que el
    modelo va a leer, no sobre el archivo .md, para que un cambio en cómo se
    ensambla el prompt también quede cubierto.
    """
    cfg = {**llm_engine.config_de(bot), "_runtime": dict(runtime)}
    return llm_engine._system_prompt(bot, cfg)


def _plano(texto: str) -> str:
    """Colapsa saltos de línea y espacios.

    Sin esto, una frase del prompt partida en dos líneas por el ancho de 79
    columnas no matchea, y el test se cae al reformatear el .md sin que nada
    haya cambiado de verdad.
    """
    return re.sub(r"\s+", " ", texto)


def _seccion(texto: str, titulo: str) -> str:
    """Sólo el cuerpo de una sección `## <titulo>`, ya aplanado.

    Importa acotar: el itinerario aparece **dos veces** en el documento (en el
    mensaje de apertura y en su propia sección de conocimiento). Un `in` contra
    el prompt entero pasaría aunque el bloque del primer mensaje no existiera,
    que es justo la regresión que este archivo tiene que atrapar.
    """
    inicio = texto.index(f"## {titulo}")
    resto = texto[inicio + 3:]
    fin = resto.find("\n## ")
    cuerpo = resto if fin == -1 else resto[:fin]
    return _plano(cuerpo)


def camino(bot, pregunta, tools=(), media=()):
    return llm_engine._classify_camino(
        bot.cfg,
        pregunta,
        [{"tool": t} for t in tools],
        list(media),
        False,
    )


# ---------------------------------------------------------------------------
# F3.1 — la instrucción nueva está en el prompt
# ---------------------------------------------------------------------------

class TestElPromptPideElMensajeUnificado:
    def test_existe_una_seccion_propia_para_el_primer_mensaje(self, bot):
        """Sección propia y no un párrafo colgado de otra regla: metida dentro
        de las reglas operativas, una instrucción le roba atención a la vecina
        en vez de sumarse (es lo que pasó con el aviso de notas de voz)."""
        assert "## El primer mensaje" in _prompt(bot)

    def test_dice_que_la_info_general_va_de_una_sin_esperar_el_nombre(self, bot):
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "Por defecto vas derecho a la info general" in seccion
        assert "con el itinerario incluido" in seccion

    def test_el_itinerario_viaja_dentro_de_ese_mismo_mensaje(self, bot):
        """El día por día tiene que estar redactado **en la sección**, no sólo
        referenciado: si el modelo tiene que ir a buscarlo abajo, lo resume mal
        o lo deja para el mensaje siguiente."""
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "Así es el plan día a día" in seccion
        for dia in ("*Viernes – Viaje*", "*Sábado – Caimanera*",
                    "*Domingo – Tolú*", "*Lunes – Regreso*"):
            assert dia in seccion, f"falta {dia} en el mensaje de apertura"

    def test_lleva_el_resumen_textual_del_plan(self, bot):
        """La frase que el documento obliga a decir "exactamente" — con ella se
        cuidan de un tirón las dos prohibiciones: "todo incluido" y "todas las
        comidas", que son falsas y generan reclamos en el destino."""
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert (
            "salida el *viernes* y regreso el *lunes*, con hotel, transporte y "
            "alimentación desde el desayuno del sábado"
        ) in seccion
        assert "todo incluido" not in seccion.lower()

    def test_y_termina_preguntando_el_nombre(self, bot):
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "¿Con quién tengo el gusto? 😊" in seccion
        assert "termina con la pregunta del nombre" in seccion

    def test_la_regla_vale_para_cualquier_primer_mensaje_no_solo_para_hola(self, bot):
        """Punto 3 del pedido: sea cual sea el primer mensaje que el bot elija
        mandar, cierra pidiendo el nombre — también el de la excepción."""
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "Sea cual sea el primer mensaje que mandes" in seccion

    def test_la_excepcion_esta_escrita_y_es_reconocible(self, bot):
        """Punto 2: si en el primer mensaje preguntó algo concreto, eso manda
        sobre la info general."""
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "si en ese primer mensaje te preguntó algo concreto" in seccion
        assert "no le sueltes la info general" in seccion

    def test_sigue_recordandole_que_registre_el_nombre(self, bot):
        """El mensaje nuevo no sirve de nada si el nombre no queda guardado:
        `registrar_nombre` es lo que evita repreguntarlo la semana entrante."""
        assert "registrar_nombre" in _prompt(bot, contact_name=None)


# ---------------------------------------------------------------------------
# F3.2 — la instrucción vieja ya no compite
# ---------------------------------------------------------------------------

class TestLaReglaViejaYaNoEstaViva:
    """Reescrita, no tapada con un párrafo encima.

    Si la vieja se hubiera dejado en pie, las dos se quedan peleando y el
    comportamiento sale aleatorio: unas veces el saludo pelado, otras el
    mensaje completo. Cada assert de aquí apunta a una frase textual que
    ordenaba lo contrario.
    """

    @pytest.mark.parametrize("frase_vieja", [
        # `## Una pregunta por mensaje`, la que mandaba justo lo contrario:
        "tu primer mensaje es *solo* el saludo",
        "Nada más: ni el resumen del plan, ni el mes, ni los hoteles",
        # `## Cómo saludar`, el saludo pelado que se copiaba literal:
        "Espero que se encuentre muy bien el día de hoy",
        # `### Cómo se ve bien hecho`, el ejemplo que reforzaba a las dos:
        'solo el saludo con "¿Con quién tengo el gusto?". El plan y el mes van '
        'en el mensaje siguiente',
    ])
    def test_ya_no_aparece(self, bot, frase_vieja):
        assert frase_vieja not in _plano(_prompt(bot)), (
            f"la instrucción vieja sigue en el prompt y compite con la nueva: "
            f"{frase_vieja!r}"
        )

    def test_el_ejemplo_de_hola_ahora_manda_el_mensaje_completo(self, bot):
        texto = _plano(_prompt(bot))
        assert 'Cliente: "hola" (sin nombre) → el mensaje completo' in texto

    def test_el_limite_de_ocho_lineas_no_pelea_con_el_mensaje_nuevo(self, bot):
        """El mensaje de apertura tiene doce líneas. Con el "máximo ~8 líneas"
        sin matizar, el modelo queda entre dos órdenes y recorta el itinerario
        justo cuando se le acaba de pedir que lo mande."""
        texto = _plano(_prompt(bot))
        assert "Máximo ~8 líneas por mensaje" in texto, (
            "la regla de longitud desapareció: sin ella el bot escribe párrafos"
        )
        assert "el límite de 8 líneas no aplica" in texto

    def test_una_pregunta_por_mensaje_sobrevive_como_regla(self, bot):
        """Su razón de ser no cambió (por WhatsApp se contesta una sola). Lo que
        cambia es que el primer mensaje lleva información + UNA pregunta, así
        que hay que decirlo explícito o se lee como una contradicción."""
        seccion = _seccion(_prompt(bot), "Una pregunta por mensaje")
        assert "Nunca hagas dos preguntas en el mismo mensaje" in seccion
        assert "Esto es sobre **preguntas**, no sobre información" in seccion


# ---------------------------------------------------------------------------
# F3.3 — quien ya se presentó no vuelve a oír la pregunta
# ---------------------------------------------------------------------------

class TestSiYaSeSabeElNombreNoSeRepregunta:
    def test_el_bloque_de_continuidad_sigue_prohibiendo_la_pregunta(self, bot):
        """Esto ya funcionaba y es lo que más fácil se rompía con el cambio: la
        sección nueva dice "termina preguntando el nombre" y podría atropellar
        al runtime que dice que ya lo sabe."""
        texto = _prompt(bot, contact_name="Marcela")
        assert "Marcela" in texto
        assert "NO le preguntes cómo se llama" in texto

    def test_y_la_seccion_nueva_declara_la_salvedad(self, bot):
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "Si ya sabes cómo se llama" in seccion
        assert "NO la incluyas" in seccion
        # Con el nombre en mano, la pregunta que cierra es la del mes.
        assert "¿Para qué mes lo estás pensando? 😊" in seccion

    def test_una_conversacion_retomada_no_es_un_primer_mensaje(self, bot):
        """Sin esta salvedad, quien vuelve al día siguiente recibiría otra vez
        el itinerario completo y la pregunta del nombre — el bug #377 otra vez,
        ahora con doce líneas en vez de dos."""
        completo = _plano(_prompt(bot, contact_name="Marcela", retomada=True,
                                  desde="ayer"))
        seccion = _seccion(_prompt(bot), "El primer mensaje")
        assert "no es un primer mensaje. Retoma donde quedaron" in seccion
        assert "No la saludes como si fuera la primera vez" in completo


# ---------------------------------------------------------------------------
# F3.4 — el clasificador de caminos
# ---------------------------------------------------------------------------

class TestPedirInformacionEsInfoGeneral:
    @pytest.mark.parametrize("apertura", [
        "Hola, quiero mas informacion",
        "Hola, quiero más información",
        "info por favor",
        "buenas, me interesa el plan",
        "Hola, vi la promo de Coveñas",
        "cuéntame del plan a Tolú",
    ])
    def test_cae_en_info_general(self, bot, apertura):
        assert camino(bot, apertura) == "info_general", apertura

    def test_no_se_lo_lleva_otro_camino_por_una_palabra_suelta(self, bot):
        """`info_general` va de últimas en la tabla, así que cualquier keyword
        de arriba se lo roba. El caso que ya costó una vez: "plan" hacía que
        "¿tienen plan a San Andrés?" cayera aquí en vez de en `otros_destinos`."""
        assert camino(bot, "¿Tienen plan a San Andrés?") == "otros_destinos"


class TestLaPreguntaConcretaConservaSuCamino:
    """La excepción del pedido: si el primer mensaje trae una pregunta
    específica, se contesta esa — y el chip del panel tiene que decirlo."""

    @pytest.mark.parametrize("apertura,esperado", [
        ("¿qué hoteles manejan?", "hotel"),
        ("Hola, ¿cuánto vale el plan?", "precios_condiciones"),
        ("buenas, ¿qué tours incluye?", "tours"),
        ("hola, ¿cómo puedo pagar?", "pagos"),
        ("Hola, quiero reservar", "reserva"),
        ("hola, quiero hablar con un asesor", "asesor"),
    ])
    def test_no_cae_en_info_general(self, bot, apertura, esperado):
        assert camino(bot, apertura) == esperado, apertura

    def test_ni_siquiera_cuando_la_pregunta_trae_la_palabra_informacion(self, bot):
        """«Quiero información de los hoteles» es una pregunta por los hoteles.
        `hotel` va antes que `info_general` en la tabla, y así debe seguir."""
        assert camino(bot, "quiero información de los hoteles") == "hotel"


class TestElItinerarioSigueTeniendoSuCamino:
    """El punto 5 del pedido: mandarlo en la apertura no cierra el camino.

    Es el riesgo silencioso del cambio — si el itinerario ya salió en el primer
    mensaje, quien lo vuelve a pedir casi nunca dice la palabra "itinerario":
    dice "¿qué se hace cada día?". Ese turno quedaba marcado `respuesta_libre`.
    """

    @pytest.mark.parametrize("pregunta", [
        "el itinerario",
        "¿me mandas el itinerario?",
        "¿qué se hace cada día?",
        "¿que se hace cada dia?",
        "¿cómo es la agenda del viaje?",
        "¿a qué hora sale el bus?",
        "¿qué actividades hay?",
    ])
    def test_se_reconoce_como_itinerario(self, bot, pregunta):
        assert camino(bot, pregunta) == "itinerario", pregunta

    def test_la_pregunta_le_gana_al_adjunto(self, bot):
        """Regresión del 2026-08-18 que cuida `test_caminos.py`: se repite acá
        porque las frases nuevas entran por ese mismo camino."""
        assert camino(
            bot, "¿qué se hace cada día?", media=["tours", "tour_video"]
        ) == "itinerario"

    def test_y_el_prompt_le_dice_que_lo_vuelva_a_mandar(self, bot):
        """El clasificador sólo pinta el chip del panel; que el bot de verdad
        lo conteste otra vez depende de esta línea del prompt."""
        assert "sin decirles que ya se los" in _plano(_prompt(bot))


class TestLaTablaDeCaminosSigueSana:
    def test_las_frases_nuevas_no_pisan_keywords_de_otro_camino(self):
        """Las keywords se matchean por substring y en orden de escritura: una
        frase nueva demasiado genérica en `itinerario` (que va cuarto) se
        tragaría turnos de precios, tours o pagos sin que nada falle."""
        propias = set(CAMINOS["itinerario"])
        for label, keywords in CAMINOS.items():
            if label == "itinerario":
                continue
            for kw in keywords:
                assert not any(p in kw for p in propias), (
                    f"la keyword {kw!r} de `{label}` contiene una de "
                    f"`itinerario`, que se matchea antes"
                )

    def test_info_general_sigue_siendo_el_ultimo_recurso(self):
        """Su lugar al final de la tabla es la razón de que "¿cuánto vale el
        plan?" sea `precios_condiciones` y no `info_general`."""
        assert list(CAMINOS)[-1] == "info_general"

    def test_la_config_que_se_despacha_no_cambio_de_flags(self):
        """Tocar `CAMINOS` es tocar el `llm_config` que se escribe en
        producción: los flags de continuidad viajan en el mismo dict."""
        assert LLM_CONFIG["caminos"] is CAMINOS
        assert LLM_CONFIG["recordar_nombre"] is True
        assert LLM_CONFIG["retomar"]["horas"] == 24
