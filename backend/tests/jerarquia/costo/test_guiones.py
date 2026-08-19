"""Los guiones del bot de Jerarquía contra Claude de verdad, en Bedrock.

**Cuesta plata.** Corre con `--con-costo`. Unos 4 centavos de dólar la corrida.

Son las seis conversaciones con las que se validó el bot antes de entregarle la
cuenta al CEO. Cada una es el centinela de algo que se rompió o se pudo romper:

  A. compra completa      → la venta de punta a punta, con link y comprobante.
  B. regateo              → el precio es fijo y NO se escala por regatear.
  C. medio de pago raro   → o escala de verdad, o no menciona al asesor.
  D. datos incompletos    → pide solo lo que falta, sin volver a pedir todo.
  E. fuera de catálogo    → escala y cierra.
  F. una sola camiseta    → escala: el bot vende la promo, no unidades.

Las afirmaciones son sobre **qué herramientas usó y qué guardarraíles
respetó**, nunca sobre la redacción: un LLM no repite la misma frase dos veces
y un test que exija palabras textuales se cae solo sin que nada esté roto.
"""
from __future__ import annotations

import re

import pytest

from app.services import llm_engine

DATOS_COMPLETOS = (
    "Julián Restrepo, CC 1017234567, 3104567890, julian@correo.com, "
    "Cra 45 #12-30 apto 502, Medellín. Dos negras L y una blanca M"
)

# Las únicas cifras de dinero que el contexto autoriza.
CIFRAS_OK = {"160000", "160", "3", "2", "5"}
_MONEDA = re.compile(
    r"\$\s?\d[\d.,]*|\b\d{1,3}(?:[.,]\d{3})+\b|\b\d+\s?(?:mil|millones|millón)\b",
    re.IGNORECASE,
)
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'()\[\]]+", re.IGNORECASE)
_ANDAMIAJE = re.compile(r"</?\s*(?:antml:)?(?:invoke|parameter|function_calls)", re.I)
# Tratos que no van con la voz de la marca (#374: el modelo soltó "hermano").
_APODOS = re.compile(
    r"\b(mi rey|papi|papito|corazón|corazon|amor|hermano|parcero|mijo)\b", re.I
)


def dicho(*salidas) -> str:
    return " ".join(
        a["payload"].get("text", "")
        for s in salidas for a in s["actions"] if a["type"] == "say"
    )


def tools(*salidas) -> set:
    return {t["tool"] for s in salidas for t in s["telemetry"]["tools"]}


def resultado_de(salidas, herramienta) -> str:
    for s in salidas:
        for t in s["telemetry"]["tools"]:
            if t["tool"] == herramienta:
                return t["resultado"]
    return ""


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
    uno: engancha `advance` y revisa al final todo lo que el bot dijo.

    El que más importa es el del link: una URL que el bot se invente es una
    dirección a la que un cliente le va a mandar plata.
    """
    dichos: list = []
    preguntado: list = []
    entregados: list = []
    original = llm_engine.advance

    def _capturando(bot, state, user_input=None, **kwargs):
        salida = original(bot, state, user_input, **kwargs)
        preguntado.append(user_input or "")
        dichos.extend(
            a["payload"].get("text", "")
            for a in salida["actions"] if a["type"] == "say"
        )
        for t in salida["telemetry"]["tools"]:
            if t["tool"] == "registrar_venta":
                entregados.extend(_URL.findall(t["resultado"]))
        return salida

    monkeypatch.setattr(llm_engine, "advance", _capturando)
    yield dichos

    texto = " ".join(dichos)
    assert not _ANDAMIAJE.search(texto), f"andamiaje de tool-use al cliente: {texto!r}"
    assert not _APODOS.search(texto), f"trato fuera de la voz de la marca: {texto!r}"
    inventadas = [
        u for u in _URL.findall(texto)
        if u.rstrip(".,;:!?") not in {e.rstrip(".,;:!?") for e in entregados}
    ]
    assert not inventadas, f"links que no entregó la herramienta: {inventadas}"
    # Repetirle a la persona el número que ella escribió no es inventar.
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
    def test_se_presenta_con_la_marca(self, bot, modelo_real):
        modelo_real["actual"] = "A1 saludo"
        s = conversar(bot, [None])
        texto = dicho(*s).lower()
        assert "samuel" in texto and "jerarquía" in texto

    def test_no_pregunta_el_nombre_a_quien_acaba_de_darlo(self, bot, modelo_real):
        """El saludo del contexto termina en "¿con quién tengo el gusto?" y el
        modelo lo pega literal si no se le insiste (lección de #372)."""
        modelo_real["actual"] = "A2 nombre"
        s = conversar(bot, ["Buenas, soy Julián"])
        texto = dicho(*s).lower()
        assert "julián" in texto or "julian" in texto
        assert "con quién tengo el gusto" not in texto

    def test_presenta_la_promo_sin_que_se_la_pidan(self, bot, modelo_real):
        """Vende un solo producto: si no lo nombra, la conversación no arranca."""
        modelo_real["actual"] = "A3 promo"
        s = conversar(bot, ["Buenas, soy Julián"])
        assert "160.000" in dicho(*s)


class TestLaVenta:
    def test_con_los_cinco_datos_registra_y_entrega_el_link(self, bot, modelo_real):
        modelo_real["actual"] = "A4 venta"
        s = conversar(bot, ["Hola, las quiero", DATOS_COMPLETOS])
        assert "registrar_venta" in tools(*s)
        resultado = resultado_de(s, "registrar_venta")
        assert "/pago-demo?ref=JRQ-" in resultado
        # El pedido llega al cliente: número y link, en el texto del bot.
        texto = dicho(*s)
        ref = re.search(r"JRQ-[A-Z0-9]{6}", resultado).group(0)
        assert ref in texto, f"registró el pedido pero no le dio el número: {texto!r}"
        assert "/pago-demo?ref=" in texto
        assert not s[-1]["finished"], "la venta no cierra el chat"

    def test_pide_lo_que_falta_sin_hacer_repetir(self, bot, modelo_real):
        modelo_real["actual"] = "D datos incompletos"
        s = conversar(bot, ["quiero comprar", "Julián Restrepo, 3104567890"])
        texto = dicho(*s).lower()
        assert "registrar_venta" not in tools(*s), "registró con datos incompletos"
        assert "cédula" in texto or "cedula" in texto
        assert "correo" in texto and "direcci" in texto

    def test_no_da_un_link_antes_de_registrar(self, bot, modelo_real):
        """El guardarraíl `_viola_link` del motor lo respalda, pero el contexto
        tiene que llevar al modelo a pedir los datos primero."""
        modelo_real["actual"] = "D link temprano"
        s = conversar(bot, ["hola, mándame el link de pago de una"])
        assert "registrar_venta" not in tools(*s)
        assert "/pago-demo" not in dicho(*s)


class TestSostieneElPrecio:
    def test_el_regateo_no_baja_el_precio_ni_escala(self, bot, modelo_real):
        """Escalar cierra la conversación: hacerlo ante un regateo mata la
        venta que el bot sí sabía cerrar."""
        modelo_real["actual"] = "B regateo"
        s = conversar(bot, ["hola, vi la promo, me las dejas en 130?"])
        assert "escalar_a_asesor" not in tools(*s)
        assert "160.000" in dicho(*s)


class TestSabeCuandoSoltar:
    @pytest.mark.parametrize("mensaje", [
        "hola, tienen chaquetas o solo camisetas?",
        "hola, cuánto vale una sola camiseta?",
        "y si no me sirve la talla me la cambian?",
        "quiero hablar con una persona por favor",
    ])
    def test_lo_que_no_maneja_termina_en_un_humano(self, bot, modelo_real, mensaje):
        modelo_real["actual"] = "E/F fuera de alcance"
        s = conversar(bot, [mensaje])
        assert "escalar_a_asesor" in tools(*s), f"no escaló: {dicho(*s)!r}"
        assert s[-1]["finished"]

    def test_no_promete_un_asesor_sin_escalar(self, bot, modelo_real):
        """El defecto de la primera corrida (#374): decía "te conecto con un
        asesor" y no llamaba la herramienta, así que nadie iba a escribirle."""
        modelo_real["actual"] = "C contra entrega"
        s = conversar(bot, ["hola, puedo pagar contra entrega?"])
        texto = dicho(*s).lower()
        anuncia = re.search(r"(te (conecto|paso)|paso con|conecto con)", texto)
        if anuncia:
            assert "escalar_a_asesor" in tools(*s), (
                f"anunció un asesor y no escaló: {texto!r}"
            )
