"""Guardarraíl `_viola_contacto_demo` del motor (Sprint 32, #608 M4).

El bot de la demo pública no tiene ninguna herramienta que le entregue un
contacto: todo teléfono, correo, @usuario, URL o dominio que escriba y que el
visitante no haya escrito es inventado. Una corrección y, si se repite, texto
fijo. Para cualquier otro bot el comportamiento no cambia.

Modelo mockeado (`llm_engine._invoke_model`): sin red ni costo.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.services import llm_engine

DEMO = {"demo": True}


class FakeBot:
    id = 501
    engine = "llm"
    status = "active"
    team_id = None
    instrucciones = "Eres el asesor de un hotel de prueba."

    def __init__(self, cfg):
        self.llm_config = json.dumps(cfg)


def _texto(t):
    return {"content": [{"type": "text", "text": t}], "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5}}


def _turno(cfg, respuestas, mensaje="Hola, ¿cuánto vale?", state=None):
    with patch.object(llm_engine, "_invoke_model", side_effect=respuestas) as m:
        r = llm_engine.advance(FakeBot(cfg), state, mensaje)
    textos = [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]
    return r, textos, m


# ---------------------------------------------------------------------------
# El detector
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Escríbenos al 300 123 4567",
    "Llámanos al +57 (604) 444 5566",
    "Nuestro correo es reservas@hotelprueba.co",
    "Síguenos en @hotelprueba",
    "Mira las fotos en https://hotelprueba.example/fotos",
    "Entra a www.hotelprueba.com",
    "Todo está en hotelprueba.com",
])
def test_detecta_contactos_inventados(texto):
    assert llm_engine._viola_contacto_demo(DEMO, [texto], ["hola"]) is True


@pytest.mark.parametrize("texto", [
    "El plan está en *$1.250.000* por persona.",
    "Son 2 × $480.000 = $960.000 por las dos noches.",
    "Queda en 1.250.000 COP por persona, del 20 al 23 de diciembre.",
    "Check-in 3:00 p. m. y check-out 12:00 m.",
    "Para 2026-12-20 te confirmo con el equipo.",
    "Incluye desayuno, wifi y piscina. ¿Para cuántas personas?",
])
def test_no_confunde_precios_ni_fechas(texto):
    assert llm_engine._viola_contacto_demo(DEMO, [texto], ["hola"]) is False


def test_lo_que_escribio_el_visitante_si_se_puede_repetir():
    visitante = ["Soy Ana, mi correo es Ana@Example.com y mi cel 300 765 4321, "
                 "mi página es anaviajes.co"]
    for texto in (
        "Listo, te escribimos a ana@example.com",
        "Te llamamos al +57 300 765 4321",
        "Vi tu página anaviajes.co",
    ):
        assert llm_engine._viola_contacto_demo(DEMO, [texto], visitante) is False
    assert llm_engine._viola_contacto_demo(DEMO, ["O al 301 111 2222"], visitante) is True


def test_sin_el_flag_no_hace_nada():
    assert llm_engine._viola_contacto_demo({}, ["Escríbenos al 300 123 4567"], []) is False


# ---------------------------------------------------------------------------
# En el turno
# ---------------------------------------------------------------------------

def test_una_correccion_y_sale_la_respuesta_limpia():
    r, textos, m = _turno(DEMO, [
        _texto("Escríbenos al 300 123 4567 y te reservamos 😊"),
        _texto("Una persona del equipo sigue contigo al confirmar 😊"),
    ])
    assert textos == ["Una persona del equipo sigue contigo al confirmar 😊"]
    assert m.call_count == 2
    # La corrección le llegó al modelo.
    ultimo = m.call_args_list[-1].args[2][-1]
    assert "ALTO" in json.dumps(ultimo, ensure_ascii=False)
    assert r["telemetry"]["rounds"] == 2


def test_si_se_repite_sale_el_texto_fijo():
    _, textos, m = _turno(DEMO, [
        _texto("Escríbenos al 300 123 4567"),
        _texto("Nuestro correo es reservas@hotelprueba.co"),
    ])
    assert textos == [llm_engine._TEXTO_CONTACTO_DEMO]
    assert m.call_count == 2
    assert all("300 123" not in t and "@" not in t for t in textos)


def test_la_correccion_deshace_el_cierre_de_la_ronda():
    escala_con_telefono = {
        "content": [
            {"type": "text", "text": "Te paso con el equipo: 300 123 4567"},
            {"type": "tool_use", "id": "t1", "name": "escalar_a_asesor",
             "input": {"motivo": "reserva"}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    escala_limpio = {
        "content": [
            {"type": "text", "text": "Te paso con una persona del equipo 🙌"},
            {"type": "tool_use", "id": "t2", "name": "escalar_a_asesor",
             "input": {"motivo": "reserva"}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    r, textos, _ = _turno(DEMO, [escala_con_telefono, escala_limpio])
    assert textos == ["Te paso con una persona del equipo 🙌"]
    assert [a["type"] for a in r["actions"]].count("handoff") == 1
    assert r["finished"] is True
    nombres = [t["tool"] for t in r["telemetry"]["tools"]]
    assert nombres == ["escalar_a_asesor:anulada", "escalar_a_asesor"]


def test_otros_bots_no_cambian():
    """Sin `demo` el teléfono pasa como siempre (los otros guardarraíles
    miran sus propios flags): ningún bot existente cambia de comportamiento."""
    _, textos, m = _turno({"context_key": "x"}, [_texto("Escríbenos al 300 123 4567")])
    assert textos == ["Escríbenos al 300 123 4567"]
    assert m.call_count == 1


def test_repite_el_telefono_que_dio_el_visitante():
    _, textos, m = _turno(
        DEMO, [_texto("Anotado tu número 300 765 4321 ✅")],
        mensaje="Mi número es 3007654321",
    )
    assert textos == ["Anotado tu número 300 765 4321 ✅"]
    assert m.call_count == 1
