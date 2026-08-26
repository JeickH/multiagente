"""La dirección de la oficina: el bot la sabe y no la escala (26-ago-2026).

Pedido del CEO: "¿dónde quedan?" es de las preguntas más frecuentes y el bot
sólo contestaba "estamos en Medellín", así que la persona tenía que volver a
preguntar o terminaba donde un asesor por un dato que ya existe.

Dos riesgos reales, los dos de texto y los dos cubiertos aquí:

1. **Que la regla de oro se la siga tragando.** El documento dice "tus temas son
   exactamente estos ocho … si no cae en ninguno, `escalar_a_asesor`". Con la
   dirección fuera de esa lista, la sección nueva y la regla de oro se quedan
   peleando y el bot escala de todos modos — es el gotcha confirmado del
   proyecto (las reglas del prompt se diluyen entre sí).
2. **Que se confunda con el punto de salida del viaje.** La oficina queda al
   frente de la estación *Universidad* del Metro y el bus sale de la *Estación
   Universidad – Calle Carabobo*: dos cosas distintas a dos cuadras, fáciles de
   mezclar. Contestar "el bus sale del Local 1087" deja a alguien parado en un
   centro comercial a las 7 de la noche.

Como el resto de `tests/viajes/`, se afirma sobre el prompt renderizado y sobre
el clasificador, que son deterministas y no cuestan un centavo.
"""
from __future__ import annotations

import re

import pytest

from app.data.bot_viajes import CAMINOS
from app.services import caminos as caminos_svc
from app.services import llm_engine


def _prompt(bot, **runtime) -> str:
    cfg = {**llm_engine.config_de(bot), "_runtime": dict(runtime)}
    return llm_engine._system_prompt(bot, cfg)


def _plano(texto: str) -> str:
    """Colapsa saltos de línea: una frase partida a 79 columnas debe matchear."""
    return re.sub(r"\s+", " ", texto)


def _seccion(texto: str, titulo: str) -> str:
    inicio = texto.index(f"## {titulo}")
    resto = texto[inicio + 3:]
    fin = resto.find("\n## ")
    return _plano(resto if fin == -1 else resto[:fin])


def camino(bot, pregunta, tools=(), media=()):
    return llm_engine._classify_camino(
        bot.cfg,
        pregunta,
        [{"tool": t} for t in tools],
        list(media),
        False,
    )


# ---------------------------------------------------------------------------
# La dirección está escrita, completa y en su propia sección
# ---------------------------------------------------------------------------

class TestElPromptTraeLaDireccion:
    def test_tiene_seccion_propia(self, bot):
        """Sección propia y no un renglón colgado de otra regla: metida dentro
        de las reglas operativas le roba atención a la vecina en vez de
        sumarse."""
        assert "## Dónde queda la agencia" in _prompt(bot)

    @pytest.mark.parametrize("linea", [
        "Centro Comercial Bosque Plaza",
        "Calle 73 N° 51D - 71",
        "Local 1087",
        "Medellín",
    ])
    def test_lleva_cada_parte_de_la_direccion(self, bot, linea):
        assert linea in _seccion(_prompt(bot), "Dónde queda la agencia")

    @pytest.mark.parametrize("referencia", [
        "estación *Universidad* del Metro",
        "Jardín Botánico",
    ])
    def test_lleva_las_dos_referencias(self, bot, referencia):
        """Sin ellas la dirección es correcta y aun así la gente vuelve a
        preguntar: en esa zona nadie se ubica por la nomenclatura."""
        assert referencia in _seccion(_prompt(bot), "Dónde queda la agencia")

    def test_dice_explicitamente_que_no_se_escala(self, bot):
        seccion = _seccion(_prompt(bot), "Dónde queda la agencia")
        assert "no se escala" in seccion

    def test_de_la_oficina_solo_sabe_donde_queda(self, bot):
        """Saber la dirección no lo vuelve experto en la oficina: horarios,
        parqueadero y teléfono siguen siendo de un humano."""
        seccion = _seccion(_prompt(bot), "Dónde queda la agencia")
        assert "horarios de atención" in seccion
        assert "escalar_a_asesor" in seccion

    def test_va_en_prosa_y_no_como_bloque_para_copiar(self, bot):
        """Lo más contraintuitivo de este cambio, y lo que costó media jornada
        de medición: con la dirección puesta como bloque literal precedido de
        "mándala tal cual", el modelo entraba en modo copiar-bloque y arrastraba
        el **otro** bloque literal del documento —el mensaje de apertura—, que
        termina pidiendo el nombre. La regla de no repreguntarlo se fue de 13/16
        a 2/20. En prosa, y con el refuerzo del bloque de continuidad, sube a
        16/16.

        El assert es por la negativa a propósito: lo que no puede volver es la
        orden de reproducir la dirección al pie de la letra.
        """
        seccion = _seccion(_prompt(bot), "Dónde queda la agencia")
        assert "tal cual" not in seccion, (
            "la dirección volvió a pedirse literal: eso hace que el modelo "
            "copie también el mensaje de apertura y repregunte el nombre"
        )
        assert "Centro Comercial Bosque Plaza*, Calle 73" in seccion, (
            "la dirección volvió a partirse en renglones: va corrida"
        )


class TestLaReglaDeOroYaLaIncluye:
    """El riesgo 1: la lista cerrada de temas manda sobre la sección nueva."""

    def test_la_direccion_es_uno_de_los_temas_que_sabe(self, bot):
        texto = _plano(_prompt(bot))
        assert "*dónde queda la agencia*" in texto, (
            "la dirección no está en la lista de temas de la regla de oro: el "
            "bot va a escalar la pregunta aunque tenga el dato escrito"
        )

    def test_la_lista_vieja_de_ocho_ya_no_esta(self, bot):
        """Si quedaran las dos redacciones, el modelo lee una lista cerrada de
        ocho temas que no incluye la dirección y otra de nueve que sí."""
        texto = _plano(_prompt(bot))
        assert "estos ocho" not in texto
        assert "ninguno de esos ocho" not in texto
        assert "estos nueve" in texto

    def test_no_se_agrego_un_ejemplo_a_como_se_ve_bien_hecho(self, bot):
        """Contraintuitivo, y por eso está fijado: el ejemplo resuelto —que es
        lo que uno agregaría por costumbre— fue la segunda edición más dañina
        de las cuatro que se probaron (5/16 contra 15/16 del baseline). La
        sección sola contesta la dirección 20/20 sin él, así que no se pone.
        """
        texto = _plano(_prompt(bot))
        assert '"¿dónde quedan ustedes?"' not in texto


class TestNoSeConfundeConLaSalidaDelBus:
    """El riesgo 2: la oficina y el punto de salida no son lo mismo."""

    def test_la_seccion_lo_advierte(self, bot):
        seccion = _seccion(_prompt(bot), "Dónde queda la agencia")
        assert "no el punto de salida del viaje" in seccion
        assert "Estación Universidad – Calle Carabobo" in seccion

    def test_el_itinerario_conserva_su_punto_de_salida(self, bot):
        """La dirección nueva no puede haber desplazado el dato del bus."""
        seccion = _seccion(_prompt(bot), "Conocimiento del plan Tolú & Coveñas")
        assert "Estación Universidad – Calle Carabobo" in seccion


class TestElBloqueDeContinuidadAguantaLaSeccionNueva:
    """El otro medio arreglo, y el que más pesó (13/16 → 16/16).

    Decirle "no preguntes el nombre" no alcanzaba cuando el documento le da,
    a la vez, un mensaje de apertura redactado palabra por palabra que termina
    pidiéndolo: el modelo copiaba el bloque entero. Hay que decirle qué hacer
    con esa última línea.
    """

    def test_le_dice_que_quite_la_ultima_linea_de_la_apertura(self, bot):
        bloque = llm_engine._bloque_continuidad(
            {**llm_engine.config_de(bot), "_runtime": {"contact_name": "Marcela"}}
        )
        assert "sin su última línea" in bloque
        assert "para qué mes lo está pensando" in bloque

    def test_no_repite_la_frase_literal_que_pide_el_nombre(self, bot):
        """Citarla la vuelve a meter en el prompt y el efecto se invierte: una
        versión que la citaba se fue de 16/20 a 0/20."""
        bloque = llm_engine._bloque_continuidad(
            {**llm_engine.config_de(bot), "_runtime": {"contact_name": "Marcela"}}
        )
        assert "tengo el gusto" not in bloque.lower()

    def test_la_frase_de_cierre_es_del_tenant_no_del_motor(self, bot):
        """`llm_engine` lo comparten mascotas, Gloma y Jerarquía: "para qué mes"
        no significa nada allá. Sin la clave, el motor sólo dice que la quite."""
        cfg = {k: v for k, v in llm_engine.config_de(bot).items()
               if k != "cierre_sin_nombre"}
        bloque = llm_engine._bloque_continuidad(
            {**cfg, "_runtime": {"contact_name": "Marcela"}}
        )
        assert "sin su última línea" in bloque
        assert "mes" not in bloque

    def test_sin_nombre_conocido_el_bloque_no_cambia(self, bot):
        """Quien todavía no se presentó tiene que seguir recibiendo la pregunta
        del nombre: es la mayoría de los chats."""
        bloque = llm_engine._bloque_continuidad(
            {**llm_engine.config_de(bot), "_runtime": {}}
        )
        assert "registrar_nombre" in bloque
        assert "última línea" not in bloque


# ---------------------------------------------------------------------------
# El chip del panel
# ---------------------------------------------------------------------------

class TestElClasificadorReconoceLaPregunta:
    @pytest.mark.parametrize("pregunta", [
        "¿dónde quedan?",
        "hola, ¿cuál es la dirección?",
        "¿donde estan ubicados?",
        "¿tienen oficina en Medellín?",
        "¿cómo llego hasta allá?",
        "¿dónde los ubico?",
        "quiero ir a visitarlos",
        "¿en qué parte del Bosque Plaza es?",
    ])
    def test_cae_en_ubicacion(self, bot, pregunta):
        assert camino(bot, pregunta) == "ubicacion", pregunta

    def test_tiene_etiqueta_en_el_panel(self):
        """Un camino sin etiqueta se muestra como "Ubicacion", en crudo."""
        assert caminos_svc.etiqueta(
            "ubicacion", "arranquemospues.marketing@gmail.com"
        ) == "📍 Preguntó la dirección"


class TestNoSeRobaTurnosDeOtroCamino:
    """`ubicacion` entra penúltimo, justo antes de `info_general`. Todo lo que
    matchea antes tiene que seguir matcheando antes."""

    @pytest.mark.parametrize("pregunta,esperado", [
        ("¿dónde queda el hotel?", "hotel"),
        ("¿dónde queda el hotel Piedra Mar?", "hotel"),
        ("¿a qué hora sale el bus?", "itinerario"),
        ("¿cómo es la agenda del viaje?", "itinerario"),
        ("¿cuánto vale y cómo llego a pagar?", "precios_condiciones"),
        ("¿puedo pagar en efectivo en la oficina?", "pagos"),
        ("quiero hablar con un asesor sobre la dirección", "asesor"),
        ("Hola, quiero más información", "info_general"),
        ("¿tienen planes a Cartagena?", "otros_destinos"),
    ])
    def test_gana_el_camino_de_siempre(self, bot, pregunta, esperado):
        assert camino(bot, pregunta) == esperado, pregunta

    def test_info_general_sigue_siendo_el_ultimo_recurso(self):
        """Su lugar al final de la tabla es lo que hace que "¿cuánto vale el
        plan?" sea precios y no info_general. `ubicacion` va justo antes."""
        assert list(CAMINOS)[-1] == "info_general"
        assert list(CAMINOS)[-2] == "ubicacion"

    def test_ninguna_keyword_nueva_contiene_una_de_un_camino_anterior(self):
        """Se matchea por substring y en orden de escritura: si una keyword de
        `ubicacion` contuviera una de un camino de más arriba, ese turno nunca
        llegaría hasta acá — el chip saldría mal y nada fallaría."""
        anteriores = list(CAMINOS)[:list(CAMINOS).index("ubicacion")]
        arriba = {kw for label in anteriores for kw in CAMINOS[label]}
        for kw in CAMINOS["ubicacion"]:
            colisiones = [otra for otra in arriba if otra in kw]
            assert not colisiones, (
                f"la keyword {kw!r} de `ubicacion` contiene {colisiones!r}, "
                f"que se matchea antes"
            )
