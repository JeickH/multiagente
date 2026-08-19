"""Los 10 guiones del bot de viajes contra Claude de verdad, en Bedrock.

**Cuesta plata.** Corre con `--con-costo`. Unos 15 centavos de dólar la corrida.

Son los mismos guiones que se ejecutaron contra producción el 2026-08-18 y que
destaparon cuatro cosas: andamiaje de tool-use filtrado al cliente, un hotel de
"3 estrellas" que nadie mencionó nunca, comidas prometidas de más y el bot
negando medios de pago por su cuenta. Cada guion de acá es el centinela de uno
de esos hallazgos.

Las afirmaciones son sobre **qué herramientas usó y qué guardarraíles
respetó**, nunca sobre la redacción: un LLM no repite la misma frase dos veces
y un test que exija palabras textuales se cae solo sin que nada esté roto. Lo
que sí es determinista —y lo que de verdad importa— es que no invente precios,
no invente características del hotel y no cierre puertas comerciales.
"""
from __future__ import annotations

import re

import pytest

from app.services import llm_engine

# Las únicas cifras de dinero que el contexto autoriza: los opcionales del
# itinerario y el 30% de la reserva. Los precios viven en las imágenes del
# tarifario, así que cualquier otra cifra la inventó el modelo.
CIFRAS_OK = {"25000", "3000", "4000", "30", "15", "10", "8"}
_MONEDA = re.compile(
    r"\$\s?\d[\d.,]*|\b\d{1,3}(?:[.,]\d{3})+\b|\b\d+\s?(?:mil|millones|millón)\b",
    re.IGNORECASE,
)
# El contexto no tiene un solo teléfono: si el bot escribe uno, lo inventó.
_TELEFONO = re.compile(r"(?:\+?\d[\d\s\-().]{6,}\d)")
_ANDAMIAJE = re.compile(r"</?\s*(?:antml:)?(?:invoke|parameter|function_calls)", re.I)


def dicho(*salidas) -> str:
    return " ".join(
        a["payload"].get("text", "")
        for s in salidas for a in s["actions"] if a["type"] == "say"
    )


def medios(*salidas) -> list:
    enviados = []
    for s in salidas:
        for t in s["telemetry"]["tools"]:
            if t["tool"] == "enviar_media":
                enviados += re.findall(r"\w+", t["input"].get("claves", ""))
    return enviados


def tools(*salidas) -> set:
    return {t["tool"] for s in salidas for t in s["telemetry"]["tools"]}


def conversar(bot, mensajes, estado=None):
    """Encadena varios turnos como lo haría una persona en el chat."""
    salidas = []
    for mensaje in mensajes:
        salida = llm_engine.advance(bot, estado, mensaje)
        salidas.append(salida)
        estado = salida.get("next_state")
        if salida.get("finished"):
            break
    return salidas


@pytest.fixture(autouse=True)
def sin_inventos(monkeypatch):
    """Guardarraíles que valen para TODOS los guiones, sin repetirlos uno por
    uno: engancha `advance` y revisa al final todo lo que el bot dijo en el
    test que acaba de correr.

    Se enchufa al motor en vez de pedirle a cada test que le pase sus mensajes:
    olvidar esa línea en un guion nuevo es exactamente el tipo de descuido que
    dejó pasar el `</parameter>` a producción.
    """
    dichos: list = []
    preguntado: list = []
    original = llm_engine.advance

    def _capturando(bot, state, user_input=None, **kwargs):
        salida = original(bot, state, user_input, **kwargs)
        preguntado.append(user_input or "")
        dichos.extend(
            a["payload"].get("text", "")
            for a in salida["actions"] if a["type"] == "say"
        )
        return salida

    monkeypatch.setattr(llm_engine, "advance", _capturando)
    yield dichos

    texto = " ".join(dichos)
    assert not _ANDAMIAJE.search(texto), f"andamiaje de tool-use al cliente: {texto!r}"
    # Los números que la propia persona dio son suyos: confirmarle la cédula
    # que acaba de escribir es correcto, no un dato inventado. Es el mismo
    # criterio que usa el guardarraíl del motor con los teléfonos.
    dio_la_persona = {
        re.sub(r"\D", "", m.group(0))
        for p in preguntado for m in _TELEFONO.finditer(p)
    }
    telefonos = [
        m.group(0) for m in _TELEFONO.finditer(texto)
        if len(re.sub(r"\D", "", m.group(0))) >= 7
        and re.sub(r"\D", "", m.group(0)) not in dio_la_persona
    ]
    assert not telefonos, f"teléfono inventado: {telefonos}"
    # Igual con el dinero: repetirle su "300 mil" para explicarle que el precio
    # no se negocia no es inventar nada.
    permitidas = CIFRAS_OK | {
        re.sub(r"\D", "", m.group(0))
        for p in preguntado for m in _MONEDA.finditer(p)
    }
    inventadas = [
        m.group(0) for m in _MONEDA.finditer(texto)
        if re.sub(r"\D", "", m.group(0)) not in permitidas
    ]
    assert not inventadas, f"cifras que no están en el contexto: {inventadas}"


class TestPrimerContacto:
    def test_se_presenta_y_pide_el_nombre(self, bot, modelo_real):
        modelo_real["actual"] = "C1 saludo"
        s = conversar(bot, [None, "Buenas tardes"])
        texto = dicho(*s).lower()
        assert "maria camila" in texto
        assert "arranquemos" in texto

    def test_no_pregunta_el_nombre_a_quien_acaba_de_darlo(self, bot, modelo_real):
        """El saludo del prompt termina en "¿con quién tengo el gusto?" y el
        modelo lo pegaba literal aunque la persona ya se hubiera presentado."""
        modelo_real["actual"] = "C3 nombre"
        s = conversar(bot, ["Hola, soy Andrés"])
        texto = dicho(*s).lower()
        assert "andrés" in texto or "andres" in texto
        assert "con quién tengo el gusto" not in texto
        assert "cuál es tu nombre" not in texto

    def test_toda_imagen_va_anunciada_en_el_texto(self, bot, modelo_real):
        """Una imagen suelta, sin una línea que diga qué es, se lee como spam."""
        modelo_real["actual"] = "C2 publicidad"
        s = conversar(
            bot, ["Hola, soy Camilo, vi la publicidad del viaje a Coveñas, cuéntame más"]
        )
        assert "info_general" in medios(*s)
        assert dicho(*s).strip(), "mandó medios sin una sola línea de texto"


class TestNoInventa:
    def test_no_cita_precios_de_memoria(self, bot, modelo_real):
        """El guardarraíl de cifras del fixture es el que juzga; acá se fija
        además que la respuesta correcta sea mandar los tarifarios."""
        modelo_real["actual"] = "C3 precios"
        s = conversar(bot, ["Hola, soy Andrés", "¿Cuánto cuesta el plan por persona?"])
        assert "tarifario1" in medios(*s)

    def test_del_hotel_solo_dice_el_nombre(self, bot, modelo_real):
        """En la corrida del 2026-08-18 se inventó "hotel 3 estrellas". El
        contexto solo autoriza el nombre y el video."""
        modelo_real["actual"] = "C10 hotel"
        s = conversar(bot, ["Hola, soy Luis", "¿y el hotel cómo es? ¿cuántas estrellas?"])
        texto = dicho(*s).lower()
        # Lo prohibido es AFIRMAR una categoría. Decir "sobre las estrellas te
        # paso con un asesor" es justo la respuesta que se busca, así que el
        # test no puede prohibir la palabra: prohíbe la cifra pegada a ella.
        categoria = re.search(
            r"(\d|una|dos|tres|cuatro|cinco)\s*(y media\s*)?estrella", texto
        )
        assert not categoria, f"le puso categoría a un hotel que no la declara: {texto!r}"
        assert "hotel_video" in medios(*s) or "escalar_a_asesor" in tools(*s)

    @pytest.mark.parametrize("guion", [
        # El "¿qué incluye?" explícito...
        ["Hola, soy Luis", "¿Qué incluye el plan?"],
        # ...y el resumen de una línea del primer mensaje, que es por donde se
        # coló en la corrida del 2026-08-18: tres turnos dijeron "todo
        # incluido" aunque la sección del plan ya lo prohibía.
        ["Hola, soy Luis"],
        ["Hola, quiero reservar para ir con mi esposa"],
    ])
    def test_no_promete_comidas_de_mas(self, bot, modelo_real, guion):
        """La alimentación va del desayuno del sábado al desayuno del lunes:
        el viernes se sale de noche y el lunes solo hay desayuno."""
        modelo_real["actual"] = "comidas"
        s = conversar(bot, guion)
        texto = dicho(*s).lower()
        for frase in ("todos los días", "todo incluido", "todas las comidas"):
            assert frase not in texto, f"prometió de más ({frase!r}): {texto!r}"

    def test_no_niega_un_medio_de_pago_por_su_cuenta(self, bot, modelo_real):
        """Negar también es inventar: decir "no recibimos X" sin que conste
        cierra una venta con información que el bot no tiene."""
        modelo_real["actual"] = "C6 pagos"
        s = conversar(bot, [
            "Hola, soy Jorge",
            "¿Cómo puedo pagar?",
            "¿y puedo pagar con Nequi o contraentrega?",
        ])
        texto = dicho(*s).lower()
        assert "medios_pago" in medios(*s)
        assert not re.search(r"no (recibimos|aceptamos|manejamos|tenemos)", texto), (
            f"descartó un medio de pago de plano: {texto!r}"
        )

    def test_no_negocia_el_precio(self, bot, modelo_real):
        """Quien juzga es el guardarraíl de cifras: lo que no puede pasar es
        que salga con un precio propio para cerrar la venta. Sí puede repetir
        el número que dijo la persona para explicarle que no aplica."""
        modelo_real["actual"] = "C9 descuento"
        s = conversar(bot, [
            "Hola, soy Sara",
            "¿me dejas el plan en 300 mil por persona si pago hoy?",
        ])
        assert "tarifario1" in medios(*s) or "escalar_a_asesor" in tools(*s)


class TestSabeCuandoSoltar:
    def test_los_datos_de_reserva_van_a_un_humano(self, bot, modelo_real):
        modelo_real["actual"] = "C7 reserva"
        s = conversar(bot, [
            "Hola, quiero reservar para ir con mi esposa",
            "Carlos Gómez, CC 79456123, 2 personas, 7 de agosto",
        ])
        assert "escalar_a_asesor" in tools(*s)
        assert s[-1]["finished"]

    def test_pedir_un_humano_escala_de_una(self, bot, modelo_real):
        modelo_real["actual"] = "C8 humano"
        s = conversar(bot, ["Hola", "prefiero hablar con una persona por favor"])
        assert "escalar_a_asesor" in tools(*s)

    def test_otro_destino_va_a_un_humano(self, bot, modelo_real):
        """El CEO confirmó que sí hay otros destinos, pero no los maneja el
        bot: cualquier consulta por uno tiene que terminar en un asesor."""
        modelo_real["actual"] = "C9 otro destino"
        s = conversar(bot, [
            "Hola, soy Sara",
            "¿Tienen plan a San Andrés para diciembre?",
            "sí, me interesa ese",
        ])
        assert "escalar_a_asesor" in tools(*s)

    def test_un_tema_ajeno_al_bot_va_a_un_humano(self, bot, modelo_real):
        """El catch-all que pidió el CEO: si el mensaje no cae en ninguno de
        los ocho caminos, no se improvisa — se pasa a un asesor."""
        modelo_real["actual"] = "catch-all"
        s = conversar(bot, [
            "Hola",
            "¿ustedes tramitan la visa americana o venden seguros de viaje?",
        ])
        assert "escalar_a_asesor" in tools(*s)

    def test_la_despedida_cierra_la_conversacion(self, bot, modelo_real):
        modelo_real["actual"] = "C10 despedida"
        s = conversar(bot, [
            "Hola, soy Luis",
            "¿Qué tours incluye?",
            "Listo, gracias! luego te escribo para reservar",
        ])
        assert "finalizar_conversacion" in tools(*s)
        assert s[-1]["finished"]


class TestItinerario:
    def test_da_los_cuatro_dias(self, bot, modelo_real):
        modelo_real["actual"] = "C4 itinerario"
        s = conversar(bot, [
            "Hola, soy Paula",
            "¿Cómo es el itinerario del viaje? ¿qué hacemos cada día?",
        ])
        texto = dicho(*s).lower()
        for dia in ("viernes", "sábado", "domingo", "lunes"):
            assert dia in texto, f"el itinerario no menciona el {dia}"
        assert "caimanera" in texto

    def test_el_caching_del_prefijo_esta_vivo(self, bot, modelo_real, medidor):
        """#363: el prefijo (tools + contexto) se cachea en Bedrock. Con el
        contexto viejo, de ~1.7k tokens, quedaba por debajo del mínimo de 2048
        de Haiku y NO se cacheaba nada — en la corrida del 2026-08-18 el bot
        pagó entrada completa en los 25 turnos. Si esto vuelve a cero, el costo
        se triplica en silencio.
        """
        modelo_real["actual"] = "caching"
        conversar(bot, ["Hola, soy Paula", "¿Qué tours incluye?", "¿y el hotel?"])
        leido = sum(c["cache_lectura"] for c in medidor.llamadas)
        escrito = sum(c["cache_escritura"] for c in medidor.llamadas)
        assert leido + escrito > 0, (
            "Bedrock no cacheó nada: el prefijo del bot volvió a quedar por "
            "debajo del mínimo del modelo"
        )
