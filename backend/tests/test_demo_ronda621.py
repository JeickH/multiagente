"""Ronda de arreglos #621 de la demo pública (QA #620).

El bloqueante: el bot de demo INVENTÓ PRECIOS (tres casos reales de QA, abajo
con sus cifras). Todo corre solo con `llm_config.demo`; cada bloque trae su
contraprueba de que un bot sin el flag no cambia.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.routers import demo as router_demo
from app.services import calendario_demo, demo_bot, llm_engine, productos_bot

DEMO = {"demo": True}

#: Las filas reales de las demos de QA #620 (r620_precios.txt).
P_AGENCIA = [  # demo #1, Rumbo Caribe Viajes
    ("Cartagena 3 días / 2 noches todo incluido", 890_000, "por persona en acomodación doble"),
    ("Santa Marta 5 días / 4 noches con trekking incluido", 1_450_000, "por persona"),
    ("Tayrona 2 días / 1 noche naturaleza pura", 650_000, "por persona"),
]
P_APARTAMENTOS = [  # demo #6, Apartamentos Mar Azul
    ("Estudio Frente al Mar", 280_000, "por noche"),
    ("Apartamento 2 Habitaciones Familia", 520_000, "por noche"),
    ("Penthouse Lujo con Vista Panorámica", 1_250_000, "por noche"),
]
P_HOSTAL = [  # E2E y demo #4, Hostal La Mochila
    ("Dormitorio Compartido 4 Camas", 45_000, "por persona por noche"),
    ("Habitación Privada Doble", 120_000, "por noche"),
    ("Combo Mochilero 7 Noches", 280_000, "por persona, 7 noches"),
]


# ---------------------------------------------------------------------------
# 1b. Guardarraíl de precios: los 3 casos reales de QA
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("precios,texto", [
    # #1: «para ese fin de semana está en $1.190.000» (la fila es $890.000),
    # sin haber llamado ninguna herramienta.
    (P_AGENCIA, "El *Cartagena 3 días / 2 noches* para ese fin de semana está en "
                "*$1.190.000 por persona*, así que para 4 personas serían $4.760.000."),
    # #6: «$420.000 por noche» (la fila es $520.000).
    (P_APARTAMENTOS, "Te recomendaría el *Apartamento 2 Habitaciones Familia*. Para 4 "
                     "noches está en *$420.000 por noche* = *$1.680.000* 🏡"),
    # E2E: «por persona, 7 noches» multiplicado otra vez por 7 noches.
    (P_HOSTAL, "El *Combo Mochilero* está en $280.000 por persona × 7 noches = $1.960.000."),
])
def test_casos_reales_de_qa_se_detectan(precios, texto):
    assert llm_engine._viola_precio_demo(DEMO, [texto], precios, []) is True
    assert llm_engine._viola_precio_demo({}, [texto], precios, []) is False


@pytest.mark.parametrize("precios,texto", [
    (P_AGENCIA, "Para 4 personas son *$3.560.000* en total ($890.000 por persona × 4)."),
    (P_AGENCIA, "El *Cartagena 3 días / 2 noches* está en $890.000 por persona."),
    (P_AGENCIA, "Uno de cada: $890.000 + $1.450.000 = $2.340.000."),
    (P_APARTAMENTOS, "*$520.000 por noche × 2 noches = $1.040.000*"),
    (P_APARTAMENTOS, "5 personas, 4 noches: $280.000 × 4 = $1.120.000"),
    (P_HOSTAL, "Para los 3: $280.000 × 3 = $840.000 total."),
    (P_HOSTAL, "Son 3 personas × 2 noches: $45.000 × 6 = $270.000."),
    (P_HOSTAL, "En 2026 el plan de 3 días / 2 noches sale el 12 de diciembre."),
    (P_HOSTAL, "Serían 840.000 para los tres."),
])
def test_cuentas_correctas_pasan(precios, texto):
    assert llm_engine._viola_precio_demo(DEMO, [texto], precios, []) is False


def test_lo_que_dijo_el_visitante_no_cuenta():
    texto = "Con tu presupuesto de $2.000.000 te alcanza para el Cartagena."
    assert llm_engine._viola_precio_demo(DEMO, [texto], P_AGENCIA, ["tengo 2 millones"]) is False
    assert llm_engine._viola_precio_demo(DEMO, [texto], P_AGENCIA, []) is True


def test_montos_no_confunde_dias_noches_ni_anios():
    assert llm_engine.montos_demo("3 días / 2 noches, salida 2026-12-12, año 2027") == []
    assert llm_engine.montos_demo("$1.850.000 × 4 = 7.400.000") == [1_850_000, 7_400_000]


class _Bot:
    id = 21
    team_id = 7
    instrucciones = "Asesor de prueba."

    def __init__(self, cfg):
        self.llm_config = json.dumps(cfg)


def _ctx(precios):
    cats = []
    for i, (nombre, precio, unidad) in enumerate(precios, start=1):
        p = demo_bot.ProductoDemo(f"p{i}x", nombre, "Resumen de prueba largo.",
                                  "x" * 150, precio, unidad)
        from tests.test_demo_bot import HOY, _a_catalogo
        cats.append(_a_catalogo(demo_bot.catalogo_demo(p, HOY), i))
    from tests.test_demo_bot import HOY
    return productos_bot.Contexto(team_id=7, bot_id=21, catalogos=tuple(cats), hoy=HOY)


def _turno(cfg, respuestas, precios, mensaje="¿Y para el próximo fin de semana?"):
    ctx = _ctx(precios)
    with patch.object(llm_engine, "_abrir_productos", return_value=(MagicMock(), ctx, [])), \
            patch.object(llm_engine, "_invoke_model", side_effect=respuestas) as m:
        r = llm_engine.advance(_Bot(cfg), None, mensaje)
    return [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"], m


def _t(texto):
    return {"content": [{"type": "text", "text": texto}], "stop_reason": "end_turn"}


_MAL_1 = _t("El *Cartagena 3 días / 2 noches* para ese fin de semana está en *$1.190.000 por persona*.")
_BIEN_1 = _t("El *Cartagena 3 días / 2 noches* está en *$890.000 por persona*. ¿Para cuántos?")


def test_precio_inventado_una_correccion():
    textos, m = _turno({"fuente_datos": "productos", "demo": True}, [_MAL_1, _BIEN_1], P_AGENCIA)
    assert textos == ["El *Cartagena 3 días / 2 noches* está en *$890.000 por persona*. ¿Para cuántos?"]
    assert m.call_count == 2
    ultimo = json.dumps(m.call_args_list[-1].args[2][-1], ensure_ascii=False)
    assert "usa exactamente los precios" in ultimo.lower()


def test_precio_inventado_dos_veces_sale_el_precio_correcto():
    textos, _ = _turno({"fuente_datos": "productos", "demo": True}, [_MAL_1, _MAL_1], P_AGENCIA)
    assert textos == [
        "*Cartagena 3 días / 2 noches todo incluido*: *$890.000 por persona en "
        "acomodación doble* (el mismo precio todo el año). El total exacto te lo "
        "confirma el equipo al reservar."
    ]


def test_precio_inventado_sin_producto_reconocible_pide_la_cotizacion():
    mal = _t("Ese plan te queda en $1.190.000.")
    textos, _ = _turno({"fuente_datos": "productos", "demo": True}, [mal, mal], P_AGENCIA,
                       mensaje="¿y el otro?")
    assert textos == [llm_engine._TEXTO_PRECIO_DEMO_GENERICO]


def test_otro_bot_con_la_misma_cifra_no_cambia():
    textos, m = _turno({"fuente_datos": "productos"}, [_MAL_1], P_AGENCIA)
    assert "$1.190.000" in textos[0] and m.call_count == 1


# ---------------------------------------------------------------------------
# 1a. El precio va pegado a cada ficha del prefijo
# ---------------------------------------------------------------------------

def test_fichas_con_precio_exacto():
    demo = MagicMock(empresa="Rumbo Caribe Viajes", tipo_empresa="agencia_viajes", tipo_otro=None)
    contenido = demo_bot.respaldo("Rumbo Caribe Viajes", "agencia_viajes")
    texto = router_demo.instrucciones_de(demo, contenido.productos)
    for p in contenido.productos:
        linea = f"Precio: {llm_engine._pesos(p.precio_cop)} {p.unidad_precio} (igual todo el año)"
        assert linea in texto
        assert texto.index(linea) > texto.index(f"### {p.nombre}")
    assert "multiplícalo solo por personas" in texto


def test_la_plantilla_trae_la_regla_de_unidades_compuestas():
    plantilla = router_demo._plantilla()
    assert "ya incluye noches" in plantilla
    assert "nunca por noches" in plantilla


# ---------------------------------------------------------------------------
# 2. Fechas: creerle al cliente, «es un viernes» y rangos sin mes
# ---------------------------------------------------------------------------

HOY = date(2026, 10, 16)


@pytest.mark.parametrize("crudo,limpio", [
    ("el sábado 14 de noviembre es un viernes en realidad",
     "el sábado 14 de noviembre es un sábado en realidad"),
    ("el 20 de noviembre cae un jueves", "el 20 de noviembre cae un viernes"),
    ("el puente es sábado 15 a martes 17 de noviembre",
     "el puente es domingo 15 a martes 17 de noviembre"),
    ("del viernes 23 al domingo 25 de octubre", "del viernes 23 al domingo 25 de octubre"),
    ("lunes 30 y martes 1 de diciembre", "lunes 30 y martes 1 de diciembre"),
    ("martes 30 y miércoles 1 de diciembre", "lunes 30 y martes 1 de diciembre"),
])
def test_dias_de_semana_ampliado(crudo, limpio):
    assert llm_engine.dias_de_semana_corregidos(crudo, HOY) == limpio


def test_calendario_manda_creerle_al_cliente():
    texto = calendario_demo.bloque(HOY)
    assert "créele: no le corrijas el día de la semana" in texto
    assert "Un puente solo existe si está en «Puentes festivos»" in texto
    assert "de sábado a lunes son 2 noches" in texto


# ---------------------------------------------------------------------------
# 3 y 4. Disponibilidad: más frases, sin falsos positivos ni texto roto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto,viola", [
    ("Tenemos ambos tours disponibles para esas fechas.", True),
    ("La suite está disponible para ese fin de semana.", True),
    ("Para el sábado 24 debería funcionar sin problema.", True),
    ("El 20 de noviembre sí se puede.", True),
    # Condiciones de la ficha, no cupos (QA #620 #4).
    ("El combo está disponible de domingo a viernes.", False),
    ("El menú está disponible jueves a domingo.", False),
    ("Disponible todos los días.", False),
    # «sin problema» que no habla de una fecha.
    ("Sin problema, te cuento qué incluye.", False),
    ("El equipo confirma la disponibilidad exacta al reservar.", False),
])
def test_disponibilidad_ampliada(texto, viola):
    assert llm_engine._viola_disponibilidad_demo(DEMO, [texto]) is viola


def test_el_detector_compartido_de_viajes_no_cambia():
    """Las frases nuevas son de la demo; el bot de viajes sigue igual."""
    assert not llm_engine._AFIRMA_DISPONIBILIDAD_RE.search(
        "Tenemos ambos tours disponibles para esas fechas."
    )


def _t2(texto):
    return {"content": [{"type": "text", "text": texto}], "stop_reason": "end_turn",
            "usage": {}}


def test_texto_fijo_de_disponibilidad_no_se_duplica_ni_se_disculpa():
    afirma = _t2("Tenemos disponibilidad para hoy. La disponibilidad exacta la confirma "
                 "el equipo al reservar. ¿Podrían el domingo 18 de octubre?")
    rehecho = _t2("Tienes razón, me disculpo. Aquí va de nuevo:\n\nTenemos disponibilidad "
                  "para hoy. La disponibilidad exacta la confirma el equipo al reservar. "
                  "¿Podrían el domingo 18 de octubre?")
    with patch.object(llm_engine, "_invoke_model", side_effect=[afirma, rehecho]):
        r = llm_engine.advance(_Bot(DEMO), None, "¿hay para hoy?")
    textos = [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]
    assert textos == [
        "La disponibilidad exacta la confirma el equipo al reservar. ¿Podrían el "
        "domingo 18 de octubre?"
    ]


def test_la_condicion_de_la_ficha_pasa_sin_corregir():
    ok = _t2("El combo está disponible de domingo a viernes. La disponibilidad exacta la "
             "confirma el equipo al reservar.")
    with patch.object(llm_engine, "_invoke_model", side_effect=[ok]) as m:
        r = llm_engine.advance(_Bot(DEMO), None, "¿hay para hoy?")
    assert m.call_count == 1
    assert r["actions"][0]["payload"]["text"].startswith("El combo está disponible de domingo")


# ---------------------------------------------------------------------------
# 5. Narración
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("Primero déjame darte el precio.", ""),
    ("¡Hola! 😊 Primero déjame darte el precio. La suite incluye jacuzzi.",
     "¡Hola! 😊 La suite incluye jacuzzi."),
    ("Ahora déjame contarte lo que incluye.", ""),
    ("Déjame pasarte el precio del plan.", ""),
    # Un traspaso no es narración.
    ("Déjame pasarte con una persona del equipo.", "Déjame pasarte con una persona del equipo."),
    # Después de dos puntos viene contenido: no se toca.
    ("Déjame contarte: incluye desayuno y piscina.", "Déjame contarte: incluye desayuno y piscina."),
])
def test_narracion_dar_pasar_contar(crudo, limpio):
    assert llm_engine.sin_narracion_demo(crudo) == limpio


# ---------------------------------------------------------------------------
# 6. Pregunta repetida sin frases colgando
# ---------------------------------------------------------------------------

def _turno_hist(cfg, texto, previa, mensaje="ok"):
    hist = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": previa}]
    with patch.object(llm_engine, "_invoke_model", side_effect=[_t2(texto)]):
        r = llm_engine.advance(_Bot(cfg), {"history": hist}, mensaje)
    return [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]


@pytest.mark.parametrize("texto,limpio", [
    ("Sí, tiene aire acondicionado y silla para bebé. Volvamos a la camioneta: "
     "¿a qué hora llegan el sábado 24?",
     "Sí, tiene aire acondicionado y silla para bebé."),
    ("Sí, incluye seguro y traslados al hotel. Entonces, ¿a qué hora llegan el sábado 24?",
     "Sí, incluye seguro y traslados al hotel."),
])
def test_pregunta_repetida_sin_colgantes(texto, limpio):
    previa = "Está en $1. ¿A qué hora llegan el sábado 24?"
    assert _turno_hist(DEMO, texto, previa) == [limpio]


# ---------------------------------------------------------------------------
# 7. Nombre completo: como máximo uno de cada dos mensajes
# ---------------------------------------------------------------------------

def test_nombre_completo_no_dos_mensajes_seguidos():
    previa = "Perfecto. ¿Me das tu nombre completo para la reserva?"
    texto = ("Sí, el parqueadero es sin costo para los huéspedes. Me das tu nombre completo "
             "y seguimos.")
    assert _turno_hist(DEMO, texto, previa) == [
        "Sí, el parqueadero es sin costo para los huéspedes."
    ]
    # Si el anterior no lo pidió, se queda.
    assert _turno_hist(DEMO, texto, "Está en $1. ¿Para cuándo?") == [texto]
    # Otro bot: igual que siempre.
    assert _turno_hist({}, texto, previa) == [texto]


# ---------------------------------------------------------------------------
# 9. El resumen del traspaso (seguridad B-n1)
# ---------------------------------------------------------------------------

def _escala(resumen):
    return {"content": [{"type": "tool_use", "id": "t1", "name": "escalar_a_asesor",
                         "input": {"motivo": "reserva", "resumen": resumen}}],
            "stop_reason": "tool_use"}


def _aviso(resumen, precios=None):
    tools = [{"tool": "escalar_a_asesor", "input": {"resumen": resumen}}]
    return llm_engine._traspaso_con_texto_demo(DEMO, tools, [], precios or [])


def test_resumen_recortado():
    largo = "Ana Gómez, 2 personas, 20 de noviembre, " + "con muchos detalles extra " * 20
    texto = _aviso(largo)
    resumen = texto.split("Te confirmo: ", 1)[1].split(". Le paso", 1)[0]
    assert len(resumen) <= 160


@pytest.mark.parametrize("resumen", [
    "Ana, 2 personas, 20 de noviembre, tenemos disponibilidad para esa fecha",
    "Ana, 2 personas, 20 de noviembre, viene por la publicidad de Gloma",
])
def test_resumen_sospechoso_da_el_aviso_generico(resumen):
    assert _aviso(resumen) == llm_engine._TEXTO_TRASPASO_DEMO


def test_resumen_con_precio_inventado_da_el_aviso_generico():
    assert _aviso("Ana, 2 personas, 20 de noviembre, total $1.190.000", P_AGENCIA) == \
        llm_engine._TEXTO_TRASPASO_DEMO
    assert _aviso("Ana, 2 personas, 20 de noviembre, total $1.780.000", P_AGENCIA).startswith(
        "Listo 🙌 Te confirmo: Ana"
    )


# ---------------------------------------------------------------------------
# 10. Semáforo de generación: tope de espera (seguridad B-n2)
# ---------------------------------------------------------------------------

def test_espera_por_defecto_12_s(monkeypatch):
    monkeypatch.delenv("DEMO_GENERACION_ESPERA_S", raising=False)
    assert demo_bot._env_espera() == 12.0


def test_maximo_cuatro_generaciones_esperando(monkeypatch):
    # Semáforo sin tope para poder soltar a las 4 que esperan al final (y que
    # la prueba no dependa de que el reloj alcance bajo carga).
    sem = threading.Semaphore(1)
    monkeypatch.setattr(demo_bot, "_SEMAFORO", sem)
    monkeypatch.setattr(demo_bot, "_EN_ESPERA", 0)
    monkeypatch.setattr(demo_bot, "_env_espera", lambda: 30.0)
    assert sem.acquire(blocking=False)
    tomados = []
    hilos = [threading.Thread(target=lambda: tomados.append(demo_bot._tomar_cupo()))
             for _ in range(demo_bot.MAX_EN_ESPERA)]
    for h in hilos:
        h.start()
    for _ in range(1000):
        if demo_bot._EN_ESPERA == demo_bot.MAX_EN_ESPERA:
            break
        time.sleep(0.01)
    assert demo_bot._EN_ESPERA == demo_bot.MAX_EN_ESPERA
    inicio = time.monotonic()
    assert demo_bot._tomar_cupo() is False          # la quinta no espera
    assert time.monotonic() - inicio < 1.0
    for _ in hilos:
        sem.release()
    for h in hilos:
        h.join(timeout=10)
    assert tomados == [True] * demo_bot.MAX_EN_ESPERA
    assert demo_bot._EN_ESPERA == 0


# ---------------------------------------------------------------------------
# Re-prueba real #621: lo que salió en las conversaciones
# ---------------------------------------------------------------------------

def test_si_podemos_a_una_pregunta_por_fecha_es_afirmar():
    texto = "Hoy es viernes, la entrada es desde las 14:00. Sí podemos, depende de las noches."
    assert llm_engine._viola_disponibilidad_demo(DEMO, [texto], "¿Hay algo para hoy mismo?") is True
    assert llm_engine._viola_disponibilidad_demo(DEMO, ["Sí podemos ayudarte con eso."], "¿tienen lockers?") is False


def test_nombre_completo_sin_pregunta_suelta():
    previa = "¿Me das tu nombre completo?"
    texto = ("Prefiero que sigamos con tu plan 😊 El apartamento tiene vista al mar.\n\n"
             "Necesito tu nombre completo para la reserva. ¿Cuál es?")
    assert _turno_hist(DEMO, texto, previa) == [
        "Prefiero que sigamos con tu plan 😊 El apartamento tiene vista al mar."
    ]


@pytest.mark.parametrize("crudo,limpio", [
    ("No tengo esos datos 😊 Pero estoy acá para ayudarte con lo que necesites. ¿Seguimos?",
     "No tengo esos datos 😊 ¿Seguimos?"),
    ("¡Excelente! El plan incluye desayuno.", "El plan incluye desayuno."),
    ("Es una excelente opción para parejas.", "Es una excelente opción para parejas."),
])
def test_frases_prohibidas(crudo, limpio):
    assert llm_engine._sin_frases_prohibidas_demo(crudo) == limpio


@pytest.mark.parametrize("texto,mal", [
    # Re-prueba #621: el total es múltiplo de un precio válido, pero la cuenta
    # escrita no da.
    ("necesitarían 2 habitaciones, lo que sería *$500.000* ($250.000 por noche × 2 noches "
     "× 2 habitaciones).", True),
    ("$250.000 × 2 noches × 2 habitaciones = $500.000", True),
    ("Dos habitaciones por 3 noches: $185.000 × 2 habitaciones × 3 noches = $1.110.000 en total", False),
    # Caso real de la primera re-prueba #621: 45.000 × 7 × 3 son 945.000, no
    # 1.575.000 (múltiplo válido de 45.000, así que solo la cuenta lo delata).
    ("serían $1.575.000 para ustedes 3 ($45.000 × 7 noches × 3 personas).", True),
    ("serían $945.000 para ustedes 3 ($45.000 × 7 noches × 3 personas).", False),
    ("Para 4 personas sería $2.800.000 × 4 = *$11.200.000 en total*.", False),
    ("*$650.000 por noche × 2 noches = $1.300.000*", False),
])
def test_operacion_mal_hecha(texto, mal):
    assert llm_engine.operacion_mal_hecha(texto) is mal
    precios = [("Habitación Estándar", 250_000, "por noche"), ("Hab", 185_000, "por noche"),
               ("Dorm", 45_000, "por noche por persona"), ("San Andrés", 2_800_000, "por persona"),
               ("Apto", 650_000, "por noche")]
    assert llm_engine._viola_precio_demo(DEMO, [texto], precios, []) is mal


@pytest.mark.parametrize("texto,mal", [
    ("Para el puente (sábado 31 de octubre a lunes 2 de noviembre, que son 3 noches): $450.000 × 3", True),
    ("Del 20 al 23 de noviembre (3 noches): $1.350.000", False),
    ("llegando el viernes 23 al domingo 25 de octubre son 2 noches", False),
    ("del 30 de diciembre al 2 de enero, 3 noches", False),
    ("del 30 de diciembre al 2 de enero, 4 noches", True),
])
def test_noches_mal_contadas(texto, mal):
    assert llm_engine.noches_mal_contadas(texto, HOY) is mal


def test_suma_de_dos_productos_con_parciales_de_antes():
    precios = [("Suite", 420_000, "por noche"), ("Estándar", 185_000, "por noche")]
    texto = "Entre la suite y las dos habitaciones llegarían a *$2.370.000*."
    assert llm_engine._viola_precio_demo(DEMO, [texto], precios, []) is False
    assert llm_engine._viola_precio_demo(DEMO, ["Llegarían a $2.371.000."], precios, []) is True


def test_respaldo_sin_temporadas_ni_recargos():
    for tipo in demo_bot.TIPOS_EMPRESA:
        for p in demo_bot.respaldo_crudo(tipo)["productos"]:
            assert "temporada alta" not in p["ficha"].lower(), (tipo, p["slug"])


def test_correccion_de_noches_dice_cuantas_son(monkeypatch):
    monkeypatch.setattr(llm_engine, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: __import__("datetime").datetime(2026, 10, 16, 12))}))
    texto = llm_engine.correccion_precio_demo(
        ["Puente: sábado 31 de octubre a lunes 2 de noviembre, que son 3 noches: $2.550.000"]
    )
    assert "del 31 de octubre al 2 de noviembre son 2 noches" in texto


def test_texto_fijo_toma_el_producto_de_la_conversacion():
    mal = _t("Para el puente serían 3 noches: $2.550.001.")
    ctx = _ctx(P_APARTAMENTOS)
    hist = [{"role": "user", "content": "¿el Apartamento 2 Habitaciones Familia?"},
            {"role": "assistant", "content": "El *Apartamento 2 Habitaciones Familia* está en $520.000."}]
    with patch.object(llm_engine, "_abrir_productos", return_value=(MagicMock(), ctx, [])), \
            patch.object(llm_engine, "_invoke_model", side_effect=[mal, mal]):
        r = llm_engine.advance(_Bot({"fuente_datos": "productos", "demo": True}),
                               {"history": hist}, "¿y para el puente?")
    textos = [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]
    assert textos[0].startswith("*Apartamento 2 Habitaciones Familia*: *$520.000 por noche*")
