"""El primer mensaje contra Claude de verdad, en Bedrock (Sprint 24 · F3).

**Cuesta plata.** Corre con `--con-costo`. Unos 5 centavos de dólar.

Estos guiones existen por un gotcha confirmado del proyecto: **las reglas del
prompt se diluyen entre sí**. Ya pasó que una regla nueva puesta al lado de la
de escalar la debilitó y el bot pasó de escalar 4 de 4 temas ajenos a 1 de 4.
F3 reescribió tres secciones del contexto —"Cómo saludar", "Una pregunta por
mensaje" y el ejemplo de `"hola"`—, así que hay que medir, no suponer.

`test_primer_mensaje.py` (gratis) prueba que **el prompt dice** lo correcto.
Esto prueba que **el modelo lo hace**, que no es lo mismo.

Cómo se corre para comparar antes/después, que es el uso para el que se
escribió:

    pytest --con-costo tests/viajes/costo/test_guiones_primer_mensaje.py \
        -s --count 12          # si está pytest-repeat; si no, un bucle de shell

Por la dilución, **una corrida no dice nada**: un LLM que acierta 11 de 12 y
otro que acierta 6 de 12 se ven idénticos en una sola pasada. La cifra que
importa es cuántas de 12 pasan, antes y después del cambio.

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

# La pregunta del nombre, en las formas en que el modelo la escribe.
#: Ojo con las formas que faltaban: el modelo también pregunta el nombre con
#: "¿quién eres?" o "¿con quién hablo?". Sin ellas la métrica se equivoca en las
#: dos direcciones — contaba como "no preguntó" un turno donde sí preguntó, y
#: dejaba pasar una repregunta cuando el nombre ya se sabía.
_PIDE_EL_NOMBRE = re.compile(
    r"con qui[eé]n tengo el gusto|c[oó]mo te llamas|cu[aá]l es tu nombre|"
    r"tu nombre\?|me regalas tu nombre|qui[eé]n eres|con qui[eé]n hablo|"
    r"me dices tu nombre|c[oó]mo te digo",
    re.IGNORECASE,
)
#: El resumen del plan que el documento obliga a decir textual. Se acepta
#: cualquiera de sus piezas: el modelo a veces parte la frase en dos líneas.
_RESUMEN_DEL_PLAN = re.compile(
    r"viernes.{0,80}lunes|salida el \*?viernes\*?", re.IGNORECASE | re.DOTALL
)
#: Los cuatro días del itinerario. Es lo que el CEO pidió agregar al mensaje.
_DIAS = ["viernes", "sábado", "domingo", "lunes"]
_HITOS_ITINERARIO = ["caimanera", "tolú"]


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


def _cuenta_lineas(texto: str) -> int:
    return len([l for l in texto.split("\n") if l.strip()])


# ---------------------------------------------------------------------------
# El caso por defecto: un solo mensaje con todo
# ---------------------------------------------------------------------------

class TestAperturaGenerica:
    """El pedido literal del CEO: "Hola, quiero más información" tiene que
    devolver la info general **con el itinerario** y la pregunta del nombre, en
    un solo mensaje."""

    @pytest.mark.parametrize("apertura", [
        "Hola, quiero mas informacion",
        "Hola",
        "buenas, me interesa el plan",
        "info por favor",
    ])
    def test_manda_info_itinerario_y_pregunta_el_nombre_de_una(
        self, bot_viajes, modelo_real, apertura
    ):
        modelo_real["actual"] = "F3-1 apertura genérica"
        salidas, turnos = _conversar(bot_viajes, [apertura])
        _transcribir(f"Apertura genérica: «{apertura}»", turnos)

        texto = _dicho(salidas[0])
        bajo = texto.lower()

        assert _RESUMEN_DEL_PLAN.search(bajo), (
            f"no contó el plan en el primer mensaje: {texto!r}"
        )
        faltan = [d for d in _DIAS if d not in bajo]
        assert not faltan, (
            f"el itinerario salió incompleto, faltan {faltan}: {texto!r}"
        )
        assert all(h in bajo for h in _HITOS_ITINERARIO), (
            f"el itinerario no menciona los tours del sábado y el domingo: {texto!r}"
        )
        assert _PIDE_EL_NOMBRE.search(texto), (
            f"no preguntó el nombre, así que no lo va a poder registrar: {texto!r}"
        )

    def test_es_un_solo_mensaje_no_tres(self, bot_viajes, modelo_real):
        """El pedido dice "que todo quede en un solo mensaje". Partirlo en tres
        burbujas es el mismo problema con otra cara."""
        modelo_real["actual"] = "F3-2 un solo mensaje"
        salidas, turnos = _conversar(bot_viajes, ["Hola, quiero mas informacion"])
        _transcribir("Un solo mensaje", turnos)

        burbujas = [a for a in salidas[0]["actions"] if a["type"] == "say"]
        assert len(burbujas) == 1, (
            f"partió la apertura en {len(burbujas)} mensajes: "
            f"{[b['payload'].get('text') for b in burbujas]!r}"
        )

    def test_no_hace_dos_preguntas(self, bot_viajes, modelo_real):
        """La regla de "una pregunta por mensaje" sigue viva: el primer mensaje
        lleva información + UNA pregunta, la del nombre. Preguntarle además el
        mes es exactamente lo que la regla prohíbe."""
        modelo_real["actual"] = "F3-3 una sola pregunta"
        salidas, turnos = _conversar(bot_viajes, ["Hola, quiero mas informacion"])
        _transcribir("Una sola pregunta", turnos)

        texto = _dicho(salidas[0])
        assert not re.search(r"para qu[eé] mes|qu[eé] mes (?:te|lo|est)", texto, re.I), (
            f"preguntó el nombre y el mes en el mismo mensaje: {texto!r}"
        )

    def test_no_manda_material_ni_precios_en_la_apertura(self, bot_viajes, modelo_real):
        """El itinerario va en texto. Un flyer o un tarifario en el primer
        mensaje —sin saber el mes— es material que nadie pidió."""
        modelo_real["actual"] = "F3-4 sin material en la apertura"
        salidas, turnos = _conversar(bot_viajes, ["Hola"])
        _transcribir("Sin material en la apertura", turnos)

        assert "consultar_tarifario" not in _tools(salidas[0]), (
            "consultó precios sin que nadie le dijera un mes"
        )
        assert not [a for a in salidas[0]["actions"] if a["type"] == "say_media"], (
            "mandó imágenes o video en el primer mensaje"
        )


# ---------------------------------------------------------------------------
# La excepción: si preguntó algo concreto, eso manda
# ---------------------------------------------------------------------------

class TestSiPreguntoAlgoConcretoNoLeSueltaLaInfoGeneral:
    @pytest.mark.parametrize("pregunta,esperado", [
        ("¿qué hoteles manejan?", ["amor de dios", "piedra mar", "boh"]),
        ("¿qué tours incluye el plan?", ["caimanera"]),
        ("¿cómo puedo pagar?", ["bancolombia", "bre-b", "efectivo"]),
    ])
    def test_contesta_la_pregunta_y_pide_el_nombre_al_final(
        self, bot_viajes, modelo_real, pregunta, esperado
    ):
        modelo_real["actual"] = "F3-5 pregunta concreta de entrada"
        salidas, turnos = _conversar(bot_viajes, [pregunta])
        _transcribir(f"Abre preguntando: «{pregunta}»", turnos)

        texto = _dicho(salidas[0])
        bajo = texto.lower()
        assert any(e in bajo for e in esperado), (
            f"no contestó lo que le preguntaron ({esperado}): {texto!r}"
        )
        # Punto 3 del pedido: el primer mensaje, sea cual sea, pide el nombre.
        assert _PIDE_EL_NOMBRE.search(texto), (
            f"contestó pero no pidió el nombre: {texto!r}"
        )

    def test_no_le_encaja_el_itinerario_a_quien_pregunto_por_hoteles(
        self, bot_viajes, modelo_real
    ):
        """El riesgo de sobrecorregir F3: que ahora TODO primer mensaje traiga
        el itinerario aunque no venga al caso."""
        modelo_real["actual"] = "F3-6 sin itinerario de más"
        salidas, turnos = _conversar(bot_viajes, ["¿qué hoteles manejan?"])
        _transcribir("Pregunta por hoteles: sin itinerario de más", turnos)

        bajo = _dicho(salidas[0]).lower()
        assert "caimanera" not in bajo, (
            f"le mandó el itinerario a quien preguntó por los hoteles: {bajo!r}"
        )


# ---------------------------------------------------------------------------
# Lo que F3 no puede romper
# ---------------------------------------------------------------------------

class TestLoQueNoSePuedeRomper:
    def test_a_quien_se_presenta_no_le_pregunta_el_nombre(
        self, bot_viajes, modelo_real
    ):
        """La regla que más fácil se atropella con el cambio: la sección nueva
        dice "termina preguntando el nombre" y esta persona ya lo dio."""
        modelo_real["actual"] = "F3-7 ya se presentó"
        salidas, turnos = _conversar(bot_viajes, ["Hola, soy Andrés, quiero info"])
        _transcribir("Ya se presentó", turnos)

        texto = _dicho(salidas[0])
        assert not _PIDE_EL_NOMBRE.search(texto), (
            f"le preguntó el nombre a quien acaba de darlo: {texto!r}"
        )
        assert re.search(r"andr[eé]s", texto, re.I), (
            f"no lo llamó por su nombre: {texto!r}"
        )
        assert "registrar_nombre" in _tools(salidas[0]), (
            "no guardó el nombre: se pierde cuando se acabe la sesión"
        )

    def test_el_nombre_del_canal_tambien_evita_la_pregunta(
        self, bot_viajes, modelo_real
    ):
        modelo_real["actual"] = "F3-8 nombre del canal"
        salidas, turnos = _conversar(
            bot_viajes, ["Hola, quiero mas informacion"],
            runtime={"contact_name": "Marcela"},
        )
        _transcribir("El canal ya trajo el nombre", turnos)

        texto = _dicho(salidas[0])
        assert not _PIDE_EL_NOMBRE.search(texto), (
            f"preguntó un nombre que ya tenía en la ficha: {texto!r}"
        )
        assert re.search(r"marcela", texto, re.I), f"no la saludó por su nombre: {texto!r}"

    def test_el_itinerario_se_puede_volver_a_pedir(self, bot_viajes, modelo_real):
        """Punto 5 del pedido: mandarlo en la apertura no cierra ese camino.
        "Ya te lo mandé" no es una respuesta."""
        modelo_real["actual"] = "F3-9 el itinerario se repite"
        salidas, turnos = _conversar(bot_viajes, [
            "Hola, quiero mas informacion",
            "Marcela",
            "¿qué se hace cada día?",
        ])
        _transcribir("Vuelve a pedir el itinerario", turnos)

        bajo = _dicho(salidas[-1]).lower()
        assert "caimanera" in bajo and "tolú" in bajo, (
            f"no volvió a dar el itinerario: {_dicho(salidas[-1])!r}"
        )
        assert not re.search(r"ya te lo (mand[eé]|envi[eé]|pas[eé])|como te dec[ií]a "
                             r"arriba", bajo), (
            f"le echó en cara que ya se lo había mandado: {bajo!r}"
        )
        assert salidas[-1]["telemetry"]["camino"] == "itinerario", (
            f"el chip del panel dice {salidas[-1]['telemetry']['camino']!r}, "
            "así el tenant no ve que el itinerario se sigue pidiendo"
        )

    def test_no_se_desborda_de_largo(self, bot_viajes, modelo_real):
        """El límite de ~8 líneas se matizó para el primer mensaje. Matizar no
        es quitarlo: si la apertura se va a treinta líneas, por WhatsApp no la
        lee nadie."""
        modelo_real["actual"] = "F3-10 largo del primer mensaje"
        salidas, turnos = _conversar(bot_viajes, ["Hola, quiero mas informacion"])
        _transcribir("Largo del primer mensaje", turnos)

        lineas = _cuenta_lineas(_dicho(salidas[0]))
        assert lineas <= 20, f"la apertura salió de {lineas} líneas, es un muro"

    def test_sigue_sin_inventar_precios_en_la_apertura(self, bot_viajes, modelo_real):
        """El contexto no autoriza ninguna cifra de dinero fuera del tarifario.
        Si el mensaje nuevo, más largo, arrastra un precio, es un invento."""
        modelo_real["actual"] = "F3-11 sin precios inventados"
        salidas, turnos = _conversar(bot_viajes, ["Hola, quiero mas informacion"])
        _transcribir("Sin precios inventados", turnos)

        texto = _dicho(salidas[0])
        cifras = re.findall(r"\$\s?\d[\d.,]*", texto)
        # Los únicos opcionales que el itinerario menciona con valor.
        permitidas = {"25.000", "25000", "3.000", "3000", "4.000", "4000"}
        coladas = [c for c in cifras if re.sub(r"[^\d.]", "", c) not in permitidas]
        assert not coladas, f"precios sin respaldo en la apertura: {coladas}"
