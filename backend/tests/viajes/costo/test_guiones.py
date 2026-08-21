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

import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.data.bot_viajes import MEDIA
from app.services import llm_engine
from app.services.messaging.base import MARCADOR_IMAGEN, MARCADOR_NOTA_DE_VOZ

# Las claves salen del catálogo, no escritas a mano. Cuando el bot pasó de dos
# hoteles a tres, `info_general`, `tarifario1` y `hotel_video` dejaron de
# existir y cuatro guiones se quedaron pidiendo material fantasma: verdes en
# apariencia hasta que alguien los corrió. Derivándolas, un rename las arrastra.
CLAVES_MEDIA = set(MEDIA)
CLAVES_TARIFARIO = {k for k, v in MEDIA.items() if v.get("meses")}
CLAVES_VIDEO_HOTEL = {
    k for k, v in MEDIA.items()
    if v.get("camino") == "hotel" and v.get("media_type") == "video"
}
CLAVES_INFO_HOTEL = {
    k for k, v in MEDIA.items()
    if v.get("camino") == "hotel" and v.get("media_type") == "image"
}


def _precios_del_tarifario() -> set:
    """Todas las cifras que el tarifario autoriza a decir, sacadas del JSON que
    genera el Excel — la misma fuente que lee `consultar_tarifario`.

    Se leen del archivo y no se escriben acá para que subir un tarifario nuevo
    no deje este guardarraíl marcando precios legítimos como inventados.
    """
    ruta = Path(__file__).resolve().parents[3] / "app" / "data" / "tarifario_covenas.json"
    numeros = set(re.findall(r"\d[\d.,]*", ruta.read_text(encoding="utf-8")))
    return {re.sub(r"\D", "", n) for n in numeros if re.sub(r"\D", "", n)}


PRECIOS_DEL_TARIFARIO = _precios_del_tarifario()

_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _proxima_salida() -> str:
    """Una fecha de viaje futura y real, en el habla del cliente ("7 de
    septiembre"), sacada de las salidas del tarifario.

    Estaba escrita a mano como "7 de agosto" y el guion se pudrió con el
    calendario: pasado el 7 de agosto el bot dejó de escalar, y con razón —
    ofrece las salidas que quedan en vez de mandar a un asesor una fecha que ya
    no se vende. El test medía el almanaque, no al bot.

    Se piden **10 días de margen** y no "la próxima": la próxima puede ser
    mañana, y ahí el bot pregunta si de verdad es para mañana antes de escalar
    — que también es lo correcto, pero convierte el guion en una moneda al aire.
    """
    ruta = Path(__file__).resolve().parents[3] / "app" / "data" / "tarifario_covenas.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    limite = date.today() + timedelta(days=10)
    futuras = sorted(
        date.fromisoformat(p["inicio"])
        for p in datos.get("planes", [])
        if p.get("inicio") and date.fromisoformat(p["inicio"]) >= limite
    )
    if not futuras:
        pytest.skip("el tarifario cargado no tiene salidas futuras: hay que regenerarlo")
    d = futuras[0]
    return f"{d.day} de {_MESES_ES[d.month - 1]}"

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
    # no se negocia no es inventar nada. Y **los precios del tarifario tampoco**:
    # desde que existe `consultar_tarifario`, decir "$459.000" es exactamente lo
    # que se le pide al bot. Antes este guardarraíl daba por inventada cualquier
    # cifra que no estuviera en el contexto, porque los precios vivían solo en
    # las imágenes; con la herramienta esa premisa dejó de ser cierta.
    permitidas = CIFRAS_OK | PRECIOS_DEL_TARIFARIO | {
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
        """Una imagen suelta, sin una línea que diga qué es, se lee como spam.

        El guion llega hasta el hotel a propósito: es donde el bot manda
        material de verdad. Antes preguntaba solo "cuéntame más" y esperaba un
        `info_general` que ya no existe — con tres hoteles, el primer mensaje
        pregunta el nombre y el mes, no manda flyers."""
        modelo_real["actual"] = "C2 publicidad"
        s = conversar(bot, [
            "Hola, soy Camilo, vi la publicidad del viaje a Coveñas, cuéntame más",
            "para septiembre",
            "en Piedra Mar",
        ])
        enviados = medios(*s)
        assert enviados, "no mandó nada de material en toda la conversación"
        assert set(enviados) <= CLAVES_MEDIA, (
            f"inventó una clave de media que no está en el catálogo: "
            f"{set(enviados) - CLAVES_MEDIA}"
        )
        assert dicho(*s).strip(), "mandó medios sin una sola línea de texto"


class TestNoInventa:
    def test_no_cita_precios_de_memoria(self, bot, modelo_real):
        """El guardarraíl de cifras del fixture es el que juzga; acá se fija
        además que la respuesta correcta sea consultar el tarifario y mandar el
        flyer del mes. El mes va en el guion porque sin mes no hay precio: si no
        se lo dan, la respuesta correcta es preguntarlo, no mandar una imagen."""
        modelo_real["actual"] = "C3 precios"
        s = conversar(bot, [
            "Hola, soy Andrés",
            "¿Cuánto cuesta el plan por persona?",
            "para septiembre",
        ])
        assert "consultar_tarifario" in tools(*s), "citó precios sin consultar"
        enviados = set(medios(*s))
        assert enviados & CLAVES_TARIFARIO, (
            f"no mandó el flyer del mes; mandó {enviados or 'nada'}"
        )

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
        enviados = set(medios(*s))
        assert (
            enviados & (CLAVES_VIDEO_HOTEL | CLAVES_INFO_HOTEL)
            or "escalar_a_asesor" in tools(*s)
        ), f"ni mostró material del hotel ni pasó al asesor: {enviados or 'nada'}"

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
        texto = dicho(*s).lower()
        # Sin mes no hay flyer que mandar, así que la respuesta correcta es
        # sostener el precio (y ofrecer el asesor si insiste), no una imagen.
        sostiene = "no" in texto and ("descuento" in texto or "precio" in texto)
        assert (
            sostiene
            or set(medios(*s)) & CLAVES_TARIFARIO
            or "escalar_a_asesor" in tools(*s)
        ), f"ni sostuvo el precio ni ofreció salida: {texto!r}"


class TestBohios:
    """Bohíos comparte flyer con Amor de Dios (mismo plan, mismo precio) y solo
    tiene video propio. Lo que no puede pasar es que el bot se quede sin nada
    que mostrar, o que mande la imagen sin avisar que dice otro nombre."""

    def test_muestra_material_y_avisa_del_nombre(self, bot, modelo_real):
        modelo_real["actual"] = "C14 bohios"
        s = conversar(bot, [
            "Hola, soy Camilo",
            "para septiembre, en Bohíos",
            "¿y cómo es el hotel? mándame la info",
        ])
        enviados = set(medios(*s))
        assert enviados, "no le mostró nada de Bohíos"
        assert set(enviados) <= CLAVES_MEDIA, (
            f"clave fuera del catálogo: {enviados - CLAVES_MEDIA}"
        )
        texto = dicho(*s).lower()
        if enviados & {"info_amordios"} or enviados & CLAVES_TARIFARIO:
            assert "amor de dios" in texto, (
                f"mandó el flyer de Amor de Dios sin avisar por qué: {texto!r}"
            )


class TestReconoceSuPropioPlan:
    """El plan se llama *Tolú & Coveñas*, pero la gente nombra uno solo de los
    dos. En producción alguien preguntó por Coveñas y el bot la mandó a un
    asesor: leyó "otro destino" donde estaba el único plan que vende."""

    @pytest.mark.parametrize("pregunta", [
        "Buenas, tienen planes para Coveñas?",
        "hola, info del viaje a tolu para 2 personas",
        "quiero saber del plan a Tolú",
    ])
    def test_no_escala_a_quien_pregunta_por_un_solo_nombre(self, bot, modelo_real, pregunta):
        """Dos turnos, no uno: sin saber el nombre el bot puede contestar solo
        con el saludo (regla de "una pregunta por mensaje"), y eso está bien.
        Lo que se vigila es que la conversación termine hablando de SU plan y
        no en manos de un asesor."""
        modelo_real["actual"] = "C11 destino"
        s = conversar(bot, [pregunta, "soy Andrés"])
        assert "escalar_a_asesor" not in tools(*s), (
            f"mandó a un asesor una pregunta por su propio plan: {dicho(*s)!r}"
        )
        texto = dicho(*s).lower()
        assert "tolú" in texto or "coveñas" in texto, (
            f"no reconoció el plan por el que le preguntaron: {texto!r}"
        )


class TestNotasDeVoz:
    """No sabemos transcribir audio todavía. El mensaje entra como
    `[nota de voz]` y el bot tiene que pedir que se lo escriban — ni adivinar
    qué decía, ni seguir como si no hubiera llegado nada, ni escalar."""

    @pytest.mark.parametrize("guion", [
        # De entrada, sin saber siquiera cómo se llama.
        [MARCADOR_NOTA_DE_VOZ],
        # A mitad de conversación.
        ["Hola, soy Andrés", MARCADOR_NOTA_DE_VOZ],
        # Y con el marcador viejo, que es lo que hay guardado en los chats
        # que ya existían cuando se hizo este cambio.
        ["Hola, soy Sara", "[audio]"],
    ])
    def test_pide_que_le_escriban(self, bot, modelo_real, guion):
        modelo_real["actual"] = "C12 nota de voz"
        s = conversar(bot, guion)
        texto = dicho(*s).lower()
        assert "escrib" in texto, f"no le pidió que le escribiera: {texto!r}"
        assert "escalar_a_asesor" not in tools(*s), "escaló por una nota de voz"
        assert not s[-1]["finished"], "cerró la conversación en vez de esperar el texto"

    def test_no_se_inventa_lo_que_decia_el_audio(self, bot, modelo_real):
        """El riesgo feo: que conteste el audio "de oído" y prometa algo."""
        modelo_real["actual"] = "C12 nota de voz"
        s = conversar(bot, ["Hola, soy Andrés", MARCADOR_NOTA_DE_VOZ])
        # El guardarraíl de cifras del fixture ya vigila los precios; acá basta
        # con que no arranque a mandar material como si le hubieran pedido algo.
        assert not medios(*s), f"mandó material sin saber qué le pidieron: {medios(*s)}"


class TestFotos:
    """Tampoco ve imágenes. La diferencia con las notas de voz: un soporte de
    pago sí tiene destino, y es un asesor humano."""

    @pytest.mark.parametrize("guion", [
        [MARCADOR_IMAGEN],
        ["Hola, soy Andrés", MARCADOR_IMAGEN],
        ["Hola, soy Sara", "[image]"],   # el marcador de los chats viejos
    ])
    def test_avisa_que_no_puede_leer_la_imagen(self, bot, modelo_real, guion):
        modelo_real["actual"] = "C13 foto"
        s = conversar(bot, guion)
        texto = dicho(*s).lower()
        assert "imágenes" in texto or "imagen" in texto or "foto" in texto
        assert "escrib" in texto or "cuentas" in texto, (
            f"no le pidió que le escribiera: {texto!r}"
        )

    def test_anunciar_una_foto_no_dispara_el_aviso(self, bot, modelo_real):
        """El aviso es para cuando la foto LLEGA. Con la primera versión de la
        regla, a "les mando el comprobante" —texto puro— el bot ya contestaba
        "no puedo ver imágenes", que es contestar algo que nadie mandó."""
        modelo_real["actual"] = "C13 foto"
        s = conversar(bot, ["Hola, soy Luis", "ya te mando una foto"])
        ultimo = " ".join(
            a["payload"].get("text", "")
            for a in s[-1]["actions"] if a["type"] == "say"
        ).lower()
        assert "no puedo ver" not in ultimo, f"se adelantó al adjunto: {ultimo!r}"

    def test_un_comprobante_de_pago_va_a_un_asesor(self, bot, modelo_real):
        """Un soporte de consignación no se contesta con "escríbemelo": lo
        tiene que revisar una persona."""
        modelo_real["actual"] = "C13 foto"
        s = conversar(bot, ["Hola, soy Luis", "les mando el comprobante", MARCADOR_IMAGEN])
        assert "escalar_a_asesor" in tools(*s)


class TestSabeCuandoSoltar:
    def test_los_datos_de_reserva_van_a_un_humano(self, bot, modelo_real):
        modelo_real["actual"] = "C7 reserva"
        # El tercer turno solo corre si el bot no escaló ya (`conversar` corta
        # cuando la conversación se cierra): cubre el caso en que pide confirmar
        # la fecha antes de soltar el chat, que es correcto y pasaba a veces.
        s = conversar(bot, [
            "Hola, quiero reservar para ir con mi esposa",
            f"Carlos Gómez, CC 79456123, 2 personas, {_proxima_salida()}",
            "sí, esa fecha, conéctame con el asesor por favor",
        ])
        assert "escalar_a_asesor" in tools(*s), (
            f"se quedó con la reserva en vez de pasarla: {dicho(*s)!r}"
        )
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
        los ocho caminos, no se improvisa — se pasa a un asesor.

        El "sí, por favor" del final no es relleno: el bot a veces ofrece
        primero ("¿te conecto con un asesor?") y escala al turno siguiente, que
        es tan correcto como escalar de una. Exigiendo la herramienta en un
        turno exacto, este guion salía rojo 1 de cada 3 corridas sin que nada
        estuviera roto — el mismo patrón que ya usaba
        `test_otro_destino_va_a_un_humano`."""
        modelo_real["actual"] = "catch-all"
        s = conversar(bot, [
            "Hola",
            "¿ustedes tramitan la visa americana o venden seguros de viaje?",
            "sí, por favor, pásame con un asesor",
        ])
        assert "escalar_a_asesor" in tools(*s), (
            f"nunca llegó a un humano: {dicho(*s)!r}"
        )

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
