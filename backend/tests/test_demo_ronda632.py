"""Ronda corta #632 de la demo pública (QA #631).

Reproduce los dos defectos y los dos cosméticos de QA, cada uno con su
contraprueba de que un bot sin `llm_config.demo` no cambia.
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.services import demo_bot, llm_engine
from tests.test_demo_api import (  # noqa: F401  (fixtures)
    Sesion, _demo_de, _demo_lista, _h, client, cuenta_demos, db, entorno, generacion_modelo,
)
from tests.test_demo_ronda621 import _ctx

HOY = date(2026, 10, 17)
DEMO = {"fuente_datos": "productos", "demo": True}
OTRO = {"fuente_datos": "productos"}
P_AGENCIA = [("Cartagena 4 días / 3 noches romance", 1_850_000, "por persona")]
P_TRASLADO = [("Traslado Aeropuerto - Hotel ida y vuelta", 180_000, "por persona")]


class _Bot:
    id = 41
    team_id = 7
    instrucciones = "Asesor de prueba."

    def __init__(self, cfg):
        self.llm_config = json.dumps(cfg)


def _t(texto):
    return {"content": [{"type": "text", "text": texto}], "stop_reason": "end_turn", "usage": {}}


def _con_tool(texto, nombre="consultar_precios"):
    return {"content": [{"type": "text", "text": texto},
                        {"type": "tool_use", "id": "t1", "name": nombre,
                         "input": {"producto": "p1x"}}],
            "stop_reason": "tool_use", "usage": {}}


def _turno(cfg, respuestas, precios, mensaje, estado=None):
    ctx = _ctx(precios)
    with patch.object(llm_engine, "_abrir_productos", return_value=(MagicMock(), ctx, [])), \
            patch.object(llm_engine, "_run_tool", return_value=("Precio: $180.000 por persona", False)), \
            patch.object(llm_engine, "_invoke_model", side_effect=respuestas):
        return llm_engine.advance(_Bot(cfg), estado, mensaje)


def _dichos(r):
    return [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]


# ---------------------------------------------------------------------------
# 1. Nombres de acompañantes y reserva completa
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("Perfecto, Mariana 🙌 Necesito los nombres completos de los otros 3 adultos para "
     "completar la reserva.", "Perfecto, Mariana 🙌"),
    ("¿Vamos con la reserva? Solo necesito los nombres completos de las dos parejas.",
     "¿Vamos con la reserva?"),
    ("Necesito los nombres completos de ustedes y confirmo que serían 4 adultos.", ""),
    # El nombre de quien escribe sí se puede pedir.
    ("Me das tu nombre completo y seguimos.", "Me das tu nombre completo y seguimos."),
])
def test_sin_nombres_de_acompanantes(crudo, limpio):
    assert llm_engine._sin_nombres_de_acompanantes(crudo) == limpio


@pytest.mark.parametrize("mensaje,esperado", [
    ("Listo, lo quiero reservar. Soy Mariana Restrepo Ochoa, somos 4 y salimos el 12 de diciembre",
     {"nombre": "Mariana Restrepo Ochoa", "personas": "4", "fecha": "12 de diciembre"}),
    ("Lo quiero. Soy Paula Andrea Ríos, somos 2, llegamos el 20 de noviembre y nos vamos el 23",
     {"nombre": "Paula Andrea Ríos", "personas": "2", "fecha": "20 de noviembre y nos vamos el 23"}),
    ("Listo, resérvalo. Soy Felipe Arango, somos 8, el 5 de diciembre a las 6 a.m.",
     {"nombre": "Felipe Arango", "personas": "8", "fecha": "5 de diciembre"}),
    ("Soy Ana Gómez, ¿cuánto vale para 4 el 12 de diciembre?", None),      # sin intención
    ("Listo, quiero reservar. Soy Tomás Ibarra", None),                  # sin fecha ni personas
    ("Lo quiero, somos 4 y salimos el 12 de diciembre", None),           # sin nombre completo
])
def test_reserva_completa(mensaje, esperado):
    assert llm_engine.reserva_completa_demo(mensaje) == esperado


MENSAJE_QA = ("Listo, lo quiero reservar. Soy Mariana Restrepo Ochoa, somos 4 y salimos "
              "el 12 de diciembre")
PIDE_NOMBRES = _t("Perfecto, Mariana 🙌 Necesito los nombres completos de los otros 3 "
                  "adultos para completar la reserva.")
HIST = {"history": [
    {"role": "user", "content": "Somos 4 adultos. ¿Cuánto nos sale en total?"},
    {"role": "assistant", "content": "$1.850.000 por persona × 4 = *$7.400.000 en total*."},
]}


def test_reserva_completa_escala_con_la_confirmacion():
    r = _turno(DEMO, [PIDE_NOMBRES], P_AGENCIA, MENSAJE_QA, HIST)
    assert _dichos(r) == [
        "Listo, Mariana 🙌 Te confirmo: Mariana Restrepo Ochoa, 4 personas, 12 de "
        "diciembre. Total: *$7.400.000*. Le paso tu reserva a una persona del equipo "
        "para que confirme la disponibilidad y te ayude con el pago."
    ]
    assert [a["type"] for a in r["actions"]] == ["say", "handoff"]
    assert r["finished"] is True
    assert r["telemetry"]["escalated_to"]


def test_si_el_modelo_ya_escalo_no_se_duplica():
    escala = {"content": [{"type": "text", "text": "Listo, Mariana 🙌 Le paso tu reserva."},
                          {"type": "tool_use", "id": "t1", "name": "escalar_a_asesor",
                           "input": {"motivo": "reserva"}}],
              "stop_reason": "tool_use", "usage": {}}
    with patch.object(llm_engine, "_invoke_model", side_effect=[escala]):
        r = llm_engine.advance(_Bot({"demo": True}), None, MENSAJE_QA)
    assert _dichos(r) == ["Listo, Mariana 🙌 Le paso tu reserva."]
    assert [a["type"] for a in r["actions"]].count("handoff") == 1


def test_otro_bot_sigue_pidiendo_lo_que_pida():
    with patch.object(llm_engine, "_invoke_model", side_effect=[PIDE_NOMBRES]):
        r = llm_engine.advance(_Bot({}), None, MENSAJE_QA)
    assert "otros 3 adultos" in _dichos(r)[0]
    assert "handoff" not in [a["type"] for a in r["actions"]]


@pytest.mark.parametrize("ficha,unidad,queda", [
    ("Qué es: escapada romántica. Válido para dos personas. Incluye: vuelos y hotel.",
     "por persona", "Qué es: escapada romántica. Incluye: vuelos y hotel."),
    ("Condiciones: el paquete es para 2 personas.\nIncluye: cena.", "por persona en acomodación doble",
     "Incluye: cena."),
    # Si el precio es por pareja, hablar de dos personas es coherente.
    ("Válido para dos personas. Incluye: cena.", "por pareja", "Válido para dos personas. Incluye: cena."),
])
def test_generador_sin_paquete_para_n(ficha, unidad, queda):
    assert demo_bot.sin_paquete_para_n(ficha, unidad) == queda


def test_respaldo_no_contradice_la_unidad():
    for tipo in demo_bot.TIPOS_EMPRESA:
        for p in demo_bot.respaldo_crudo(tipo)["productos"]:
            if "por persona" in p["unidad_precio"].lower():
                assert not demo_bot._PAQUETE_PARA_N_RE.search(p["ficha"]), (tipo, p["slug"])


# ---------------------------------------------------------------------------
# 2. Burbuja repetida tras una corrección (precio, disponibilidad, contacto)
# ---------------------------------------------------------------------------

SALUDO = ("¡Hola! 😊 Tenemos el servicio perfecto para ti: el *Traslado Aeropuerto - Hotel "
          "ida y vuelta*, con conductor profesional.")
LIMPIO = "Para ustedes 3 sería *$180.000 por persona × 3 = $540.000* ida y vuelta."


@pytest.mark.parametrize("mala", [
    # Disponibilidad (el caso de QA).
    LIMPIO + " Disponible 24 horas, así que no hay problema con la tarde de mañana 🚗",
    # Precio inventado.
    "Para ustedes 3 sería *$600.000* ida y vuelta.",
    # Contacto inventado.
    LIMPIO + " Escríbenos al 300 123 4567.",
])
def test_rehecho_tras_correccion_sin_burbuja_duplicada(mala):
    respuestas = [_con_tool(SALUDO), _t(mala), _t(SALUDO + "\n\n" + LIMPIO)]
    r = _turno(DEMO, respuestas, P_TRASLADO, "Somos 3 para mañana en la tarde")
    assert _dichos(r) == [SALUDO + "\n\n" + LIMPIO]


def test_sin_flag_las_dos_burbujas_quedan():
    """Contraprueba: el bot sin `demo` no tiene el guardarraíl ni el recorte."""
    respuestas = [_con_tool(SALUDO), _t(SALUDO + "\n\n" + LIMPIO)]
    r = _turno(OTRO, respuestas, P_TRASLADO, "Somos 3")
    assert _dichos(r) == [SALUDO, SALUDO + "\n\n" + LIMPIO]


def test_burbujas_distintas_se_quedan():
    actions = [{"type": "say", "payload": {"text": "¡Hola! 😊"}},
               {"type": "say", "payload": {"text": "El plan está en $1.850.000."}}]
    assert llm_engine._sin_burbujas_repetidas(actions) is False and len(actions) == 2


# ---------------------------------------------------------------------------
# 3. «mañana» junto a una fecha que no es mañana
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("Necesito la hora exacta a la que llegan mañana en la madrugada del 24.",
     "Necesito la hora exacta a la que llegan en la madrugada del 24."),
    ("Llegan mañana 18 en la tarde.", "Llegan mañana 18 en la tarde."),            # sí es mañana
    ("A las 6 de la mañana del 24.", "A las 6 de la mañana del 24."),              # la franja
    ("Para mañana en la tarde, perfecto.", "Para mañana en la tarde, perfecto."),  # sin fecha
    ("Mañana 24 de octubre salen.", "24 de octubre salen."),
])
def test_sin_manana_equivocado(crudo, limpio):
    assert llm_engine.sin_manana_equivocado(crudo, HOY) == limpio


def test_manana_solo_en_la_demo():
    texto = "Necesito la hora a la que llegan mañana en la madrugada del 24."
    for cfg, esperado in (({"demo": True}, "Necesito la hora a la que llegan en la madrugada del 24."),
                          ({}, texto)):
        with patch.object(llm_engine, "datetime") as dt:
            dt.now.return_value = __import__("datetime").datetime(2026, 10, 17, 12)
            dt.utcnow.side_effect = __import__("datetime").datetime.utcnow
            with patch.object(llm_engine, "_invoke_model", side_effect=[_t(texto)]):
                r = llm_engine.advance(_Bot(cfg), None, "hola")
        assert _dichos(r) == [esperado], cfg


# ---------------------------------------------------------------------------
# 4. 422 del evento sin el detalle de Pydantic
# ---------------------------------------------------------------------------

def test_evento_422_con_mensaje_fijo(client):
    demo_id, token = _demo_lista(client)
    for cuerpo in ({"tipo": "<script>"}, {"tipo": "whatsapp", "extra": "x"}, {}, [1, 2], "texto"):
        r = client.post(f"/demo/{demo_id}/evento", headers=_h(token), json=cuerpo)
        assert r.status_code == 422 and r.json() == {"detail": "Solicitud inválida"}, cuerpo
        assert "<script>" not in r.text
    r = client.post(f"/demo/{demo_id}/evento", headers=_h(token))
    assert r.status_code == 422 and r.json() == {"detail": "Solicitud inválida"}


def test_evento_404_va_antes_que_el_422(client):
    demo_id, _ = _demo_lista(client)
    r = client.post(f"/demo/{demo_id}/evento", headers=_h("ajeno"), json={"tipo": "x"})
    assert r.status_code == 404 and r.json() == {"detail": "Demo no encontrada"}


def test_otros_endpoints_conservan_el_422_de_siempre(client):
    r = client.post("/demo/iniciar", json={"nombre": "x"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], list)


@pytest.mark.parametrize("texto,viola", [
    ("Perfecto, el próximo sábado 24 de octubre en la madrugada funciona con nosotros 🙌", True),
    ("Claro, marzo de 2027 también funciona.", True),
    ("El 24 de octubre lo cubrimos.", True),
    ("¿Te funciona el sábado 24 de octubre?", False),
    ("Así funciona el traslado: te recogemos en la terminal.", False),
])
def test_funciona_con_una_fecha_es_afirmar(texto, viola):
    assert llm_engine._viola_disponibilidad_demo({"demo": True}, [texto]) is viola
    assert llm_engine._viola_disponibilidad_demo({}, [texto]) is False
