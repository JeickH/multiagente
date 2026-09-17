"""Regresión: la corrección de un guardarraíl no puede romper el `tool_use`.

Bug de producción. En `_advance_inner`, cuando un guardarraíl
(`_viola_contacto`, `_viola_ficha`, `_viola_link`, `_viola_duracion`,
`_viola_disponibilidad`) rechaza
lo que escribió el modelo, la ronda se reinyecta con el mensaje del asistente
completo más un mensaje del usuario con la corrección. Si en ESA MISMA ronda el
modelo también llamó una herramienta, su bloque `tool_use` viaja dentro de
`content`, y la API de Anthropic exige que el mensaje siguiente **arranque** con
el `tool_result` correspondiente. Mandando solo el texto de la corrección, la
llamada siguiente moría con:

    ValidationException: messages.N: `tool_use` ids were found without
    `tool_result` blocks immediately after: toolu_bdrk_01LH29...

El turno entero se iba al fail-safe y el cliente recibía la disculpa genérica en
vez de su respuesta. Se reprodujo contra Bedrock en
`tests/viajes/costo/test_guiones.py::TestNoInventa` y `::TestBohios`.

Estos tests son gratuitos: el modelo va mockeado con
`patch.object(llm_engine, "_invoke_model")`, igual que `GuardarrailLinkTests` en
`tests/test_venta_jerarquia.py` y los del guardarraíl en
`tests/viajes/test_duracion.py`. No tocan red, ni AWS, ni la base.

Lo que de verdad protege no es el caso puntual sino el invariante:
`assert_tool_use_bien_formado()` recorre TODOS los `messages` que vio el modelo
y exige que cada `tool_use` tenga su `tool_result` pegado detrás. Está pensado
para reusarse en cualquier prueba futura del motor.
"""
from __future__ import annotations

import copy
import json
from datetime import date
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine, tarifario


# --------------------------------------------------------------------------
# El invariante reusable
# --------------------------------------------------------------------------

def _messages_de_la_llamada(llamada) -> List[Dict[str, Any]]:
    """`_invoke_model(model_id, system, messages, tools)`, posicional o no."""
    if len(llamada.args) >= 3:
        return llamada.args[2]
    return llamada.kwargs["messages"]


def snapshots_de(mock) -> List[List[Dict[str, Any]]]:
    """Los `messages` que vio el modelo en cada llamada.

    Ojo con `mock.call_args_list` a secas: el motor **muta la misma lista**
    `working` entre rondas, así que todas las entradas apuntan al mismo objeto y
    todas muestran el estado FINAL. Para el invariante da igual (el par
    malformado sigue ahí al final), pero para mirar "el mensaje que armó la
    ronda 1" hay que haber copiado en el momento. Por eso `_grabador()` guarda
    copias en `mock.snapshots` y aquí se prefieren si existen.
    """
    guardadas = getattr(mock, "snapshots", None)
    if guardadas:
        return guardadas
    return [_messages_de_la_llamada(c) for c in mock.call_args_list]


def _bloques(mensaje: Dict[str, Any]) -> List[Dict[str, Any]]:
    contenido = mensaje.get("content")
    if isinstance(contenido, list):
        return [b for b in contenido if isinstance(b, dict)]
    return []


def assert_tool_use_bien_formado(mock) -> None:
    """Todo `tool_use` va seguido de su `tool_result`, en el mensaje siguiente.

    Es literalmente la regla que la API de Anthropic hace cumplir con un 400.
    Reusable: cualquier test del motor que mockee `_invoke_model` puede llamar
    esto al final y se entera si una ruta nueva rompe la conversación.
    """
    for n, messages in enumerate(snapshots_de(mock)):
        for i, mensaje in enumerate(messages):
            ids = [
                b.get("id") for b in _bloques(mensaje) if b.get("type") == "tool_use"
            ]
            if not ids:
                continue
            assert i + 1 < len(messages), (
                f"llamada {n}: el mensaje {i} tiene tool_use {ids} y es el "
                "último: nadie devolvió el tool_result"
            )
            siguiente = messages[i + 1]
            bloques = _bloques(siguiente)
            assert siguiente.get("role") == "user" and bloques, (
                f"llamada {n}, mensaje {i + 1}: después de un tool_use {ids} "
                f"tiene que ir un mensaje `user` con bloques, y llegó "
                f"{siguiente!r}"
            )
            devueltos = [
                b.get("tool_use_id")
                for b in bloques[: len(ids)]
                if b.get("type") == "tool_result"
            ]
            assert devueltos == ids, (
                f"llamada {n}, mensaje {i + 1}: los tool_result tienen que ir "
                f"de PRIMEROS y con los mismos ids. Se esperaban {ids} y el "
                f"mensaje arranca con {[b.get('type') for b in bloques]}"
            )


# --------------------------------------------------------------------------
# Andamiaje del turno
# --------------------------------------------------------------------------

class BotFake:
    id = 404
    engine = "llm"

    def __init__(self, cfg: Dict[str, Any]):
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


def _resp(content, stop_reason="end_turn"):
    return {"content": content, "stop_reason": stop_reason}


def _texto(t: str) -> Dict[str, Any]:
    return {"type": "text", "text": t}


def _tool_use(name: str, tool_input=None, tid="toolu_bdrk_01LH29"):
    return {"type": "tool_use", "id": tid, "name": name, "input": tool_input or {}}


#: Historial previo sin dígitos: el guardarraíl de contacto da por bueno todo
#: teléfono que la propia persona haya escrito, y aquí no queremos ninguno.
HISTORIA = {
    "history": [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "¡Hola! ¿Con quién tengo el gusto?"},
    ]
}


def _grabador(mock, respuestas: List[Dict[str, Any]]):
    """Encola respuestas del modelo y copia los `messages` de cada llamada."""
    mock.snapshots = []
    cola = list(respuestas)

    def responder(model_id, system, messages, tools):
        mock.snapshots.append(copy.deepcopy(messages))
        return cola.pop(0) if cola else _resp([_texto("Listo 👍")])

    mock.side_effect = responder


def _corre_turno(
    cfg: Dict[str, Any],
    content_malo: List[Dict[str, Any]],
    texto_bueno: str,
    resultado_tool: str,
    user_input: str,
):
    """Un turno donde la ronda 1 viola un guardarraíl y la 2 responde bien."""

    with patch.object(llm_engine, "_invoke_model") as mock, \
            patch.object(llm_engine, "_run_tool") as run_tool:
        run_tool.return_value = (resultado_tool, False)
        _grabador(
            mock,
            [
                _resp(content_malo, stop_reason="tool_use"),
                _resp([_texto(texto_bueno)]),
            ],
        )
        out = llm_engine.advance(BotFake(cfg), copy.deepcopy(HISTORIA), user_input)
    return out, mock


# --------------------------------------------------------------------------
# Un escenario por guardarraíl
# --------------------------------------------------------------------------

HOY = date(2026, 8, 19)

#: Salida REAL de la herramienta (nunca un string fabricado: el criterio ya
#: quemado en `tests/viajes/test_duracion.py`). Septiembre publica las DOS
#: duraciones, que es donde el guardarraíl de duración distingue.
TARIFARIO_SEPTIEMBRE = tarifario.consultar(
    LLM_CONFIG, hotel="Amor de Dios", mes="septiembre", hoy=HOY
)
ESTANDAR = "SEPTIEMBRE 11 AL 14"      # 2 noches / 3 días

CFG_VIAJES = dict(LLM_CONFIG)

CFG_VENTA = {
    "context_key": "jerarquia",
    "assignee": "asesor_1",
    "venta": {
        "producto": "Promo Manada — 3 camisetas tipo polo",
        "valor": "$160.000",
        "prefijo": "JRQ",
        "link_pago": "https://app.glomacx.com/pago-demo?ref={ref}&total=160000",
    },
}

CFG_MASCOTAS = {"context_key": "mascotas_cali", "mascotas": {}}

RESULTADO_VENTA = (
    "Pedido JRQ-0001 registrado. link de pago: "
    "https://app.glomacx.com/pago-demo?ref=JRQ-0001&total=160000 — cópialo EXACTO."
)

#: (id, cfg, bloque de texto que viola, tool que llamó en la MISMA ronda,
#:  resultado de esa tool, texto limpio del reintento, lo que escribió la persona)
ESCENARIOS = [
    pytest.param(
        CFG_VIAJES,
        f"La del *{ESTANDAR}* es de 4 días y 3 noches 🌴",
        _tool_use("consultar_tarifario", {"mes": "septiembre"}),
        TARIFARIO_SEPTIEMBRE,
        "Con gusto, ¿para cuántas personas sería? 🌴",
        "¿cuánto dura el plan de septiembre?",
        id="duracion",
    ),
    pytest.param(
        CFG_VIAJES,
        "¡Sí! El 18 de septiembre sigue disponible 🌴",
        # A propósito NO `consultar_tarifario`: si la hubiera llamado, el dato
        # vendría del tarifario y el guardarraíl —con razón— no dispara.
        _tool_use("registrar_nombre", {"nombre": "Marcela"}),
        "Nombre registrado.",
        "Déjame reviso esa fecha y te confirmo 😊",
        "¿el 18 de septiembre sigue?",
        id="disponibilidad",
    ),
    pytest.param(
        CFG_VENTA,
        "Paga aquí: https://jerarquia.com/pagos/123",
        _tool_use("registrar_venta", {"nombre": "cliente"}),
        RESULTADO_VENTA,
        "Ya te confirmo el link en un momento 👊",
        "quiero pagar",
        id="link",
    ),
    pytest.param(
        CFG_MASCOTAS,
        "Llama al 3005556677 y pregunta por la perrita.",
        # A propósito una tool que NO trae datos de contacto: si fuera
        # `entregar_contacto`, el número saldría del resultado y sería legítimo.
        _tool_use("buscar_mascota", {"texto": "perrita café"}),
        "No hay coincidencias todavía.",
        "Cuéntame cómo es tu mascota y dónde se perdió 🐶",
        "se me perdió una perrita café",
        id="contacto",
    ),
    pytest.param(
        CFG_MASCOTAS,
        "Mira esta otra: es una salchicha café, la encontraron cerca 🐶",
        # Tampoco puede ser `ver_ficha`/`buscar_mascota`: esas SÍ traen la
        # ficha y el guardarraíl —con razón— no dispara.
        _tool_use("registrar_reporte", {"tipo": "perdida"}),
        "Reporte MC-00012 registrado.",
        "¿Tienes una foto de tu mascota? 🐶",
        "busco a mi perro",
        id="ficha",
    ),
]


@pytest.mark.parametrize(
    "cfg, texto_malo, tool, resultado_tool, texto_bueno, user_input", ESCENARIOS
)
class TestCorreccionEnUnaRondaConHerramienta:
    """Los CINCO guardarrailes, cada uno disparando en una ronda que además
    llamó una herramienta. Es la combinación que reventaba."""

    def test_la_correccion_arranca_con_el_tool_result(
        self, cfg, texto_malo, tool, resultado_tool, texto_bueno, user_input
    ):
        """EL CASO DEL BUG. El mensaje `user` que el motor arma después de
        tumbar la ronda tiene que empezar por el `tool_result` del `tool_use`
        que viajó en esa misma ronda, con su mismo id.

        Se lee del argumento `messages` de la SEGUNDA llamada a
        `_invoke_model`, no de variables internas del motor.
        """
        out, mock = _corre_turno(
            cfg, [_texto(texto_malo), tool], texto_bueno, resultado_tool, user_input
        )
        assert mock.call_count == 2, (
            "el guardarraíl no disparó: sin corrección este test no prueba nada"
        )
        messages = snapshots_de(mock)[1]
        ultimo = messages[-1]
        assert ultimo["role"] == "user"
        assert isinstance(ultimo["content"], list), (
            "con un tool_use en la ronda, la corrección NO puede ir como string "
            f"pelado: la API la rechaza. Llegó {ultimo['content']!r}"
        )
        primero = ultimo["content"][0]
        assert primero["type"] == "tool_result"
        assert primero["tool_use_id"] == tool["id"]
        # Y la corrección sigue llegando: el modelo tiene que enterarse.
        textos = [b for b in ultimo["content"] if b.get("type") == "text"]
        assert textos and textos[-1]["text"].startswith("ALTO:")

    def test_ningun_tool_use_queda_sin_su_tool_result(
        self, cfg, texto_malo, tool, resultado_tool, texto_bueno, user_input
    ):
        """El invariante general, que es lo que de verdad protege."""
        _, mock = _corre_turno(
            cfg, [_texto(texto_malo), tool], texto_bueno, resultado_tool, user_input
        )
        assert_tool_use_bien_formado(mock)

    def test_el_turno_no_cae_al_failsafe(
        self, cfg, texto_malo, tool, resultado_tool, texto_bueno, user_input
    ):
        """La consecuencia visible del bug: el cliente recibía la disculpa
        genérica en vez de su respuesta."""
        out, _ = _corre_turno(
            cfg, [_texto(texto_malo), tool], texto_bueno, resultado_tool, user_input
        )
        textos = [a["payload"]["text"] for a in out["actions"] if a["type"] == "say"]
        assert llm_engine._FAILSAFE_TEXT not in textos
        assert out["telemetry"]["camino"] != "failsafe"
        assert out["telemetry"].get("failsafe") is False
        # Lo que sí le llega es el reintento; lo que el guardarraíl tumbó, no.
        assert texto_bueno in textos
        assert texto_malo not in textos


# --------------------------------------------------------------------------
# El camino de siempre, el que NO hay que romper al arreglar el otro
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "cfg, texto_malo, user_input",
    [
        pytest.param(
            CFG_VIAJES,
            f"La del *{ESTANDAR}* es de 4 días y 3 noches 🌴",
            "¿cuánto dura?",
            id="duracion",
        ),
        pytest.param(
            CFG_VENTA,
            "Paga aquí: https://jerarquia.com/pagos/123",
            "quiero pagar",
            id="link",
        ),
        pytest.param(
            CFG_MASCOTAS,
            "Llama al 3005556677 y pregunta por la perrita.",
            "se me perdió una perrita",
            id="contacto",
        ),
        pytest.param(
            CFG_MASCOTAS,
            "Mira esta otra: es una salchicha café, la encontraron cerca 🐶",
            "busco a mi perro",
            id="ficha",
        ),
    ],
)
def test_sin_herramienta_la_correccion_sigue_siendo_el_texto_pelado(
    cfg, texto_malo, user_input
):
    """Ronda de SOLO texto: no hay `tool_result` que devolver, así que el
    mensaje del usuario sigue siendo el string de la corrección, como antes.
    Envolverlo siempre en bloques sería un cambio de forma gratuito."""

    with patch.object(llm_engine, "_invoke_model") as mock:
        # Sin tool en la ronda no hace falta mockear `_run_tool`: nadie la llama.
        _grabador(
            mock,
            [
                _resp([_texto(texto_malo)]),
                _resp([_texto("Dame un segundo y te confirmo 👍")]),
            ],
        )
        out = llm_engine.advance(BotFake(cfg), copy.deepcopy(HISTORIA), user_input)

    assert mock.call_count == 2, "el guardarraíl no disparó"
    ultimo = snapshots_de(mock)[1][-1]
    assert ultimo["role"] == "user"
    assert isinstance(ultimo["content"], str)
    assert ultimo["content"].startswith("ALTO:")
    assert out["telemetry"]["camino"] != "failsafe"
    assert_tool_use_bien_formado(mock)


# --------------------------------------------------------------------------
# Que los escenarios sigan siendo los que se creen
# --------------------------------------------------------------------------

def test_el_tarifario_de_ejemplo_publica_dos_duraciones():
    """Si el Excel cambia y septiembre deja de publicar las dos duraciones, el
    escenario de `duracion` se vuelve decorativo sin avisar."""
    assert ESTANDAR in TARIFARIO_SEPTIEMBRE
    assert llm_engine._viola_duracion(
        CFG_VIAJES,
        [f"La del *{ESTANDAR}* es de 4 días y 3 noches 🌴"],
        [TARIFARIO_SEPTIEMBRE],
    )
