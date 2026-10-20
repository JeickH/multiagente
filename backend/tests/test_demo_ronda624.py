"""Ronda de pulido #624 de la demo pública (QA #622).

Cada test reproduce un caso textual de QA (scratchpad `r622_*.json`) y trae su
contraprueba de que un bot sin `llm_config.demo` no cambia.
"""
from __future__ import annotations

import json
from datetime import date
from unittest.mock import patch

import pytest

from app.routers import demo as router_demo
from app.services import llm_engine

DEMO = {"demo": True}
HOY = date(2026, 10, 17)


class _Bot:
    id = 31
    team_id = None
    instrucciones = "Asesor de prueba."

    def __init__(self, cfg):
        self.llm_config = json.dumps(cfg)


def _t(texto):
    return {"content": [{"type": "text", "text": texto}], "stop_reason": "end_turn",
            "usage": {}}


def _dice(cfg, texto, mensaje="hola", estado=None):
    with patch.object(llm_engine, "_invoke_model", side_effect=[_t(texto), _t(texto)]):
        r = llm_engine.advance(_Bot(cfg), estado, mensaje)
    return [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]


# ---------------------------------------------------------------------------
# 1. La cuenta escrita se evalúa entera a la izquierda del «=»
# ---------------------------------------------------------------------------

TRASLADO = [("Traslado Aeropuerto - Hotel", 85_000, "por trayecto, hasta 4 pasajeros"),
            ("Ruta Cartagena - Santa Marta", 125_000, "por persona, ida")]

QA_340 = ("Serían 2 trayectos de ida ($85.000 × 2) + 2 trayectos de vuelta "
          "($85.000 × 2) = *$340.000 en total*.")


@pytest.mark.parametrize("texto,mal", [
    (QA_340, False),                                                   # el falso positivo de QA
    ("2 trayectos de ida ($85.000 × 2) + 2 de vuelta ($85.000 × 2) = $400.000", True),
    ("Más los traslados del aeropuerto (4 trayectos × $85.000 = *$340.000*), el total "
     "sería *$1.840.000*.", False),
    ("serían 2 trayectos × 6 personas × $125.000 = *$1.500.000*.", False),
    ("*Ruta* (ida y vuelta, 2 trayectos): $125.000 × 9 personas × 2 = *$2.250.000*", False),
    ("Total: $680.000 + $925.000 = $1.605.000", False),
    ("- 2 Cenas Románticas en Terraza: 2 × *$340.000* = *$680.000*", False),
    # Los de la ronda anterior siguen.
    ("$250.000 × 2 noches × 2 habitaciones = $500.000", True),
    ("lo que sería *$500.000* ($250.000 por noche × 2 noches × 2 habitaciones).", True),
])
def test_operacion_completa(texto, mal):
    assert llm_engine.operacion_mal_hecha(texto) is mal


def test_el_caso_de_qa_no_tumba_el_turno():
    assert llm_engine._viola_precio_demo(DEMO, [QA_340], TRASLADO, []) is False
    assert llm_engine._viola_precio_demo({}, [QA_340], TRASLADO, []) is False


# ---------------------------------------------------------------------------
# 2. Disponibilidad: lo que QA vio pasar, y lo que debe seguir pasando
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto,pregunta", [
    ("Claro, disponemos de espacios. ¿Hoy sábado 17 de octubre te vendría bien?",
     "¿Hay algo para hoy mismo?"),
    ("El próximo sábado 24 de octubre es una excelente opción para el *Rafting Río "
     "Claro*. La disponibilidad exacta la confirma el equipo al reservar, pero ese día "
     "generalmente tenemos actividad.", "¿Hay para el próximo fin de semana?"),
    ("Hoy es sábado, y el *Menú Degustación* está disponible de martes a domingo, así "
     "que hoy sí podemos 😊", "¿Y para hoy a las 8 de la noche?"),
])
def test_disponibilidad_de_qa_se_detecta(texto, pregunta):
    assert llm_engine._viola_disponibilidad_demo(DEMO, [texto], pregunta) is True
    assert llm_engine._viola_disponibilidad_demo({}, [texto], pregunta) is False


@pytest.mark.parametrize("texto,fichas", [
    # Copiado de la ficha: pasa.
    ("El traslado está disponible 24/7 desde el aeropuerto.",
     ["Condiciones: Disponible 24/7 desde el aeropuerto. Máximo 4 pasajeros."]),
    ("El *Traslado* está disponible 24/7.", []),
    ("El menú está disponible de martes a domingo.", []),
    ("La disponibilidad exacta la confirma el equipo al reservar.", []),
    ("Contamos con silla para bebé.", []),
])
def test_disponibilidad_que_debe_pasar(texto, fichas):
    assert llm_engine._viola_disponibilidad_demo(DEMO, [texto], "¿hay para hoy?", fichas) is False


def test_una_afirmacion_que_no_esta_en_la_ficha_no_se_salva():
    fichas = ["Condiciones: Disponible 24/7 desde el aeropuerto."]
    assert llm_engine._viola_disponibilidad_demo(
        DEMO, ["Claro, disponemos de espacios para el sábado."], "", fichas
    ) is True


# ---------------------------------------------------------------------------
# 3. «El próximo martes es 22 de octubre»
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("El próximo martes es 22 de octubre, ¿es correcto?",
     "El próximo jueves es 22 de octubre, ¿es correcto?"),
    ("ese viernes sería 23 de octubre", "ese viernes sería 23 de octubre"),
    ("el martes cae el 22 de octubre", "el jueves cae el 22 de octubre"),
])
def test_dia_con_conector(crudo, limpio):
    assert llm_engine.dias_de_semana_corregidos(crudo, HOY) == limpio


def test_otro_bot_no_corrige_el_dia():
    texto = "El próximo martes es 22 de octubre, ¿es correcto?"
    assert _dice({}, texto) == [texto]


# ---------------------------------------------------------------------------
# 4 y 6. Plantilla: contactos no escalan; capacidad con techo
# ---------------------------------------------------------------------------

def test_plantilla_contacto_no_es_traspaso():
    plantilla = router_demo._plantilla()
    assert "**No es motivo de traspaso** que pida un teléfono" in plantilla


def test_plantilla_capacidad():
    plantilla = router_demo._plantilla()
    assert "9 personas en vehículos de 4" in plantilla
    assert "Nunca cotices una opción que" in plantilla


# ---------------------------------------------------------------------------
# 5. Aviso de traspaso armado
# ---------------------------------------------------------------------------

def _aviso(resumen, history=None, precios=None):
    tools = [{"tool": "escalar_a_asesor", "input": {"resumen": resumen}}]
    return llm_engine._traspaso_con_texto_demo(DEMO, tools, [], precios or [], history)


def test_sin_doble_punto_y_recorte_por_frase():
    resumen = ("Carolina Vélez, 4 personas, llega 4 de diciembre y se va 8 de diciembre. "
               "Quiere 3 noches en Suite Premium familiar y 1 noche en Habitación Estándar "
               "doble. Total: $1.560.000 más la estándar")
    texto = _aviso(resumen)
    assert ".." not in texto
    assert "Te confirmo: Carolina Vélez, 4 personas, llega 4 de diciembre y se va 8 de " \
           "diciembre. Quiere 3 noches en Suite Premium familiar y 1 noche en Habitación " \
           "Estándar doble. Le paso" in texto


def test_corte_por_palabra_no_a_mitad():
    resumen = "Ana, 2 personas, 20 de noviembre, " + "palabralarga " * 20
    resumen_en_texto = _aviso(resumen).split("Te confirmo: ", 1)[1].split(". Le paso", 1)[0]
    assert len(resumen_en_texto) <= 160
    assert all(p == "palabralarga" for p in resumen_en_texto.split(", ")[-1].split())


HIST = [
    {"role": "user", "content": "somos 2, ¿cuánto queda?"},
    {"role": "assistant", "content": "$185.000 × 2 noches = *$370.000 en total*. ¿Lo reservo?"},
]
P_HOTEL = [("Habitación Estándar", 185_000, "por noche")]


def test_incluye_el_total_cotizado():
    texto = _aviso("Ana Prueba, 2 personas, del 20 al 22 de noviembre.", HIST, P_HOTEL)
    assert texto.startswith(
        "Listo 🙌 Te confirmo: Ana Prueba, 2 personas, del 20 al 22 de noviembre. "
        "Total: *$370.000*. Le paso tu reserva"
    )


def test_total_invalido_no_se_incluye():
    hist = [{"role": "assistant", "content": "Total: *$371.000*."}]
    texto = _aviso("Ana Prueba, 2 personas, del 20 al 22 de noviembre", hist, P_HOTEL)
    assert "Total" not in texto and "Ana Prueba" in texto


def test_si_el_resumen_ya_trae_plata_no_se_repite():
    texto = _aviso("Ana, 2 personas, 20 de noviembre, $370.000", HIST, P_HOTEL)
    assert texto.count("$370.000") == 1


def test_total_cotizado():
    assert llm_engine.total_cotizado(HIST) == 370_000
    assert llm_engine.total_cotizado([{"role": "assistant", "content": "*Total: $2.590.000*"}]) == 2_590_000
    assert llm_engine.total_cotizado([{"role": "user", "content": "total $1.000.000"}]) is None


# ---------------------------------------------------------------------------
# 7. Cosméticos
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("¿Cuál de los dos productos os llama más: el *Avistamiento*?",
     "¿Cuál de los dos productos les llama más: el *Avistamiento*?"),
    ("Cuéntame: ¿cuál producto preferís, el de avistamiento o el de fotografía?",
     "Cuéntame: ¿cuál producto prefieres, el de avistamiento o el de fotografía?"),
    ("¿Vamos armando la reserva? Decime: ¿el Avistamiento?",
     "¿Vamos armando la reserva? Dime: ¿el Avistamiento?"),
    ("Si querés, podés venir con vos y tenés descuento.",
     "Si quieres, puedes venir contigo y tienes descuento."),
    ("¿Os parece si queréis ver vuestro plan?", "¿Les parece si quieren ver su plan?"),
    ("Los osos del bosque y nos vemos.", "Los osos del bosque y nos vemos."),
])
def test_sin_voseo(crudo, limpio):
    assert llm_engine.sin_voseo_demo(crudo) == limpio


@pytest.mark.parametrize("crudo,limpio", [
    ("De momento estoy aquí para ayudarte. ¿Vamos entonces? Necesito tu nombre.",
     "¿Vamos entonces? Necesito tu nombre."),
    ("Te cuento que la disponibilidad exacta la confirma el equipo al reservar. Pero "
     "primero, déjame darte el precio: el *Avistamiento Chocó* está en *$1.890.000*.",
     "Te cuento que la disponibilidad exacta la confirma el equipo al reservar. El "
     "*Avistamiento Chocó* está en *$1.890.000*."),
    ("Según la ficha, en fines de semana hay diferencia de valor.",
     "En fines de semana hay diferencia de valor."),
    ("El plan incluye desayuno, según la ficha.", "El plan incluye desayuno."),
])
def test_cosmeticos(crudo, limpio):
    assert llm_engine._sin_frases_prohibidas_demo(crudo) == limpio


def test_en_el_turno_de_demo_y_no_en_otro_bot():
    texto = "Según la ficha, ¿cuál preferís? Decime."
    assert _dice(DEMO, texto) == ["¿Cuál prefieres? Dime."]
    assert _dice({}, texto) == [texto]
