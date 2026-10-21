"""Ronda de arreglos #619 de la demo pública (QA #615 + auditoría #616).

Todo lo que se prueba aquí corre SOLO con `llm_config.demo`; cada bloque tiene
además su contraprueba de que un bot sin el flag no cambia.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.routers import demo as router_demo
from app.services import calendario_demo, demo_bot, llm_engine, productos, productos_bot
from tests.test_demo_api import (  # noqa: F401  (fixtures)
    ModeloFalso, Sesion, _cuerpo, _demo_de, _demo_lista, _h, _iniciar, _texto, _tool,
    client, cuenta_demos, db, entorno, generacion_modelo,
)
from tests.test_demo_bot import HOY, _a_catalogo

DEMO = {"fuente_datos": "productos", "demo": True}


# ---------------------------------------------------------------------------
# 1. Calendario determinista
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("anio,esperada", [
    (2024, date(2024, 3, 31)), (2025, date(2025, 4, 20)),
    (2026, date(2026, 4, 5)), (2027, date(2027, 3, 28)),
])
def test_pascua(anio, esperada):
    assert calendario_demo.pascua(anio) == esperada


def test_festivos_colombia_2026():
    f = calendario_demo.festivos(2026)
    esperados = {
        date(2026, 1, 1), date(2026, 1, 12), date(2026, 3, 23), date(2026, 4, 2),
        date(2026, 4, 3), date(2026, 5, 1), date(2026, 5, 18), date(2026, 6, 8),
        date(2026, 6, 15), date(2026, 6, 29), date(2026, 7, 20), date(2026, 8, 7),
        date(2026, 8, 17), date(2026, 10, 12), date(2026, 11, 2), date(2026, 11, 16),
        date(2026, 12, 8), date(2026, 12, 25),
    }
    assert set(f) == esperados


@pytest.mark.parametrize("hoy,este,proximo", [
    (date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 24)),   # viernes
    (date(2026, 10, 17), date(2026, 10, 17), date(2026, 10, 24)),   # sábado
    (date(2026, 10, 18), date(2026, 10, 17), date(2026, 10, 24)),   # domingo
    (date(2026, 10, 19), date(2026, 10, 24), date(2026, 10, 31)),   # lunes
])
def test_fines_de_semana(hoy, este, proximo):
    (s1, d1), (s2, d2) = calendario_demo.fines_de_semana(hoy)
    assert (s1, s2) == (este, proximo)
    assert d1 == s1 + timedelta(days=1) and d1.weekday() == 6


def test_bloque_del_calendario():
    texto = calendario_demo.bloque(date(2026, 10, 16))
    assert "Hoy es viernes 16 de oct; mañana es sábado 17 de oct." in texto
    assert "Este fin de semana: sáb 17 oct – dom 18 oct." in texto
    assert "El próximo fin de semana: sáb 24 oct – dom 25 oct." in texto
    assert "vie 16 oct (2026-10-16) [hoy]" in texto
    assert "sáb 17 oct (2026-10-17) [mañana]" in texto
    assert "lun 2 nov (2026-11-02) [festivo: Todos los Santos]" in texto
    assert "dom 18 oct" in texto and "jue 5 nov" in texto      # 21 días
    assert "vie 6 nov" not in texto.split("Festivos")[0]
    assert "lun 16 nov (Independencia de Cartagena)" in texto
    assert "sáb 31 oct – lun 2 nov (Todos los Santos)" in texto      # puente
    assert "sáb 14 nov – lun 16 nov" in texto


class _Bot:
    id = 9
    team_id = None
    instrucciones = "Asesor de prueba."

    def __init__(self, cfg):
        self.llm_config = json.dumps(cfg)


def test_el_calendario_solo_entra_al_prompt_de_la_demo():
    con = llm_engine._system_prompt(_Bot({"demo": True}), {"demo": True})
    sin = llm_engine._system_prompt(_Bot({}), {})
    assert "## Calendario" in con
    assert "## Calendario" not in sin
    assert "## Qué día es hoy" in sin


# ---------------------------------------------------------------------------
# 2 y 3. Herramientas del catálogo en la demo
# ---------------------------------------------------------------------------

@pytest.fixture
def cats():
    c = demo_bot.respaldo("Viajes Prueba", "agencia_viajes")
    return [_a_catalogo(demo_bot.catalogo_demo(p, HOY), i + 1)
            for i, p in enumerate(c.productos)]


def _ctx(cats):
    return productos_bot.Contexto(team_id=7, bot_id=5, catalogos=tuple(cats), hoy=HOY)


def test_sin_fechas_disponibles_y_abrir_sin_disponibilidad(cats):
    tools = llm_engine._tools_for(DEMO, _ctx(cats), "")
    nombres = [t["name"] for t in tools]
    assert "fechas_disponibles" not in nombres
    abrir = next(t for t in tools if t["name"] == "abrir_producto")
    assert "disponibilidad" not in abrir["description"]
    # Contraprueba: un bot sin el flag sigue con las tres.
    otro = {t["name"] for t in llm_engine._tools_for({"fuente_datos": "productos"}, _ctx(cats), "")}
    assert {"abrir_producto", "consultar_precios", "fechas_disponibles"} <= otro


def _ejecutar_demo(cats, nombre, entrada):
    with patch.object(productos, "resolver_producto", return_value=cats[0]):
        return llm_engine._ejecutar_producto_demo(None, _ctx(cats), nombre, entrada)


def test_consultar_precios_sin_fecha_da_el_precio(cats):
    texto = _ejecutar_demo(cats, "consultar_precios", {"producto": cats[0].slug})
    assert "$2.890.000" in texto
    assert texto != productos.PLANTILLA["sin_periodo"]
    assert "mismo precio todos los meses" in texto
    # Contraprueba: la capa sin el ajuste sigue pidiendo la fecha.
    with patch.object(productos, "resolver_producto", return_value=cats[0]):
        crudo = productos_bot.ejecutar(None, _ctx(cats), "consultar_precios",
                                       {"producto": cats[0].slug})
    assert crudo == productos.PLANTILLA["sin_periodo"]


def test_consultar_precios_con_mes_se_respeta(cats):
    texto = _ejecutar_demo(cats, "consultar_precios", {"producto": cats[0].slug, "mes": "diciembre"})
    assert "Diciembre" in texto and "$2.890.000" in texto


def test_abrir_producto_sin_periodos_de_disponibilidad(cats):
    texto = _ejecutar_demo(cats, "abrir_producto", {"producto": cats[0].slug})
    assert "disponibilidad" not in texto.lower()
    assert cats[0].instrucciones in texto


def test_fechas_disponibles_no_devuelve_calendario(cats):
    texto = _ejecutar_demo(cats, "fechas_disponibles", {"producto": cats[0].slug})
    assert "no está disponible" in texto
    assert "Diciembre" not in texto


def test_etiqueta_de_las_filas_es_neutra():
    p = demo_bot.respaldo(None, "hotel").productos[0]
    filas = demo_bot.catalogo_demo(p, HOY)["filas"]
    assert {f["etiqueta"] for f in filas} == {"tarifa del mes"}


# ---------------------------------------------------------------------------
# 4. Fichas en el prefijo
# ---------------------------------------------------------------------------

def test_las_tres_fichas_quedan_en_las_instrucciones(client, db):
    demo_id, _ = _demo_lista(client)
    demo = _demo_de(db, demo_id)
    from app import models

    bot = db.query(models.Bot).get(demo.bot_id)
    texto = bot.instrucciones
    respaldo = demo_bot.respaldo_crudo("hotel")["productos"]
    assert texto.index("## Fichas de los productos") > texto.index("## Datos del negocio")
    for p in respaldo:
        assert f"### {p['nombre']}" in texto
        assert p["ficha"].splitlines()[0] in texto
    assert "NUNCA inventes una condición" in texto


# ---------------------------------------------------------------------------
# 6 y 7. Narración y pregunta repetida, con el historial limpio
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("Necesito revisar las fechas.", ""),
    ("Tengo que consultar el precio de diciembre.", ""),
    ("Un momento 🙏", ""),
    ("Claro, dame un momento.", "Claro"),
    ("Te paso el precio para que veas cuánto queda.", ""),
    # Con cifras no se toca: podría llevarse el precio.
    ("Te paso el precio para que veas: $1.200.000 por persona.",
     "Te paso el precio para que veas: $1.200.000 por persona."),
    ("Déjame consultar: está en $1.200.000.", "Déjame consultar: está en $1.200.000."),
    ("Es un momento especial para parejas.", "Es un momento especial para parejas."),
    ("¡Hola! 😊\n\nDéjame traerte el precio de *Cartagena 3 días / 2 noches* para este mes.",
     "¡Hola! 😊"),
])
def test_narracion_ampliada(crudo, limpio):
    assert llm_engine.sin_narracion_demo(crudo) == limpio


def test_el_historial_guarda_el_texto_limpio(client, db):
    demo_id, token = _demo_lista(client)
    precio = llm_engine._pesos(demo_bot.respaldo_crudo("hotel")["productos"][0]["precio_cop"])
    respuesta = f"La habitación está en {precio} por noche. ¿Para cuántas personas?"
    modelo = ModeloFalso([
        _tool("consultar_precios", {"producto": "x"}, texto="Déjame consultar el precio."),
        _texto(respuesta),
    ])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "precio"})
    assert [a["text"] for a in r.json()["actions"]] == [respuesta]
    demo = _demo_de(db, demo_id)
    guardado = demo.chat_state["history"][-1]["content"]
    assert "Déjame" not in guardado
    assert "Déjame" not in demo.transcripcion[-1]["texto"]


@pytest.mark.parametrize("a,b,igual", [
    ("¿Para qué fecha exacta en diciembre lo estás pensando?",
     "¿para qué fechas exactas en diciembre lo estás pensando?", True),
    ("¿Para cuál día: sábado 19 o domingo 20?",
     "¿Para cuál de los dos días lo estás pensando, sábado 19 o domingo 20?", True),
    ("¿Con quién tengo el gusto?", "¿Para qué fecha?", False),
    ("¿Para cuántas personas sería?", "¿Para qué fecha sería?", False),
])
def test_misma_pregunta(a, b, igual):
    assert llm_engine.misma_pregunta(a, b) is igual


def _turno_demo(cfg, respuestas, historial):
    with patch.object(llm_engine, "_invoke_model", side_effect=respuestas):
        r = llm_engine.advance(_Bot(cfg), {"history": historial}, "¿Incluye seguro?")
    return [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]


_HIST = [
    {"role": "user", "content": "hola"},
    {"role": "assistant", "content": "Está en $1.000.000. ¿Para qué fecha de diciembre lo estás pensando?"},
]
_RESP = {"content": [{"type": "text", "text":
         "Sí, incluye seguro de viaje y traslados. ¿Para qué fechas de diciembre lo estás pensando?"}],
         "stop_reason": "end_turn"}


def test_pregunta_repetida_se_quita_en_la_demo():
    assert _turno_demo({"demo": True}, [_RESP], _HIST) == [
        "Sí, incluye seguro de viaje y traslados."
    ]


def test_pregunta_repetida_no_se_toca_en_otros_bots():
    assert _turno_demo({}, [_RESP], _HIST) == [
        "Sí, incluye seguro de viaje y traslados. ¿Para qué fechas de diciembre lo estás pensando?"
    ]


def test_si_solo_queda_la_pregunta_se_conserva():
    resp = {"content": [{"type": "text", "text": "¿Para qué fecha de diciembre lo estás pensando?"}],
            "stop_reason": "end_turn"}
    assert _turno_demo({"demo": True}, [resp], _HIST) == [
        "¿Para qué fecha de diciembre lo estás pensando?"
    ]


# ---------------------------------------------------------------------------
# 9. Cierre del último turno
# ---------------------------------------------------------------------------

def test_ultimo_turno_lleva_el_cierre_fijo(client, monkeypatch):
    monkeypatch.setenv("DEMO_MAX_TURNOS", "1")
    demo_id, token = _demo_lista(client)
    with patch.object(llm_engine, "_invoke_model", ModeloFalso([_texto("Está en $1. ¿Para cuándo?")])):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "a"})
    out = r.json()
    assert out["finished"] is True
    assert out["actions"][-1]["text"] == router_demo.TEXTO_CIERRE_DEMO


def test_el_cierre_no_se_suma_a_un_traspaso(client, monkeypatch):
    monkeypatch.setenv("DEMO_MAX_TURNOS", "1")
    demo_id, token = _demo_lista(client)
    modelo = ModeloFalso([_tool("escalar_a_asesor", {"motivo": "r"}, texto="Te paso con el equipo.")])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "a"})
    assert router_demo.TEXTO_CIERRE_DEMO not in [a["text"] for a in r.json()["actions"]]


# ---------------------------------------------------------------------------
# 10. Techo diario de leads (#616 M1)
# ---------------------------------------------------------------------------

def test_techo_diario_de_leads_no_guarda_nada(client, db, monkeypatch):
    from app import models

    monkeypatch.setenv("DEMO_MAX_GLOBAL_DIA", "1")
    monkeypatch.setenv("DEMO_MAX_LEADS_DIA", "3")
    for n in range(3):   # 1 demo + 2 leads guardados por el tope global
        _iniciar(client, correo=f"m{n}@example.com", telefono=f"300 111 {n:04d}")
    r = _iniciar(client, correo="m9@example.com", telefono="300 111 0099")
    assert r.status_code == 429
    assert r.json() == {"detail": router_demo.TEXTO_429}
    db.expire_all()
    assert db.query(models.Lead).count() == 3


# ---------------------------------------------------------------------------
# 11. Cliente Bedrock propio en los turnos de demo (#616 M2)
# ---------------------------------------------------------------------------

def test_turno_de_demo_usa_el_cliente_corto():
    vistos = []

    def _modelo(model_id, system, messages, tools):
        vistos.append(llm_engine._TURNO_DEMO.get())
        return {"content": [{"type": "text", "text": "Hola"}], "stop_reason": "end_turn"}

    with patch.object(llm_engine, "_invoke_model", _modelo):
        llm_engine.advance(_Bot({"demo": True}), None, "hola")
        llm_engine.advance(_Bot({}), None, "hola")
    assert vistos == [True, False]
    assert llm_engine._TURNO_DEMO.get() is False


def test_invoke_model_elige_el_cliente_segun_el_turno():
    class _Cliente:
        def __init__(self):
            self.n = 0

        def invoke_model(self, **kw):
            self.n += 1

            class _B:
                def read(self):
                    return b'{"content": [], "usage": {}}'
            return {"body": _B()}

    corto, compartido = _Cliente(), _Cliente()
    with patch.object(llm_engine, "_bedrock_client_demo", return_value=corto), \
            patch.object(llm_engine, "_bedrock_client", return_value=compartido):
        marca = llm_engine._TURNO_DEMO.set(True)
        try:
            llm_engine._invoke_model("m", "s", [], [])
        finally:
            llm_engine._TURNO_DEMO.reset(marca)
        llm_engine._invoke_model("m", "s", [], [])
    assert (corto.n, compartido.n) == (1, 1)


def test_cliente_demo_con_timeouts_cortos():
    llm_engine._bedrock_client_demo.cache_clear()
    try:
        with patch("boto3.client") as mk:
            llm_engine._bedrock_client_demo()
        cfg = mk.call_args.kwargs["config"]
        # #635: sin reintentos de botocore (los hace `_invoke_con_respaldo`,
        # dentro del plazo del turno) y el timeout que quede del plazo.
        assert cfg.connect_timeout == 3 and cfg.read_timeout == 15
        assert cfg.retries["total_max_attempts"] == 1
    finally:
        llm_engine._bedrock_client_demo.cache_clear()


# ---------------------------------------------------------------------------
# 12. Modelo fijo (#616 B3)
# ---------------------------------------------------------------------------

def test_modelo_del_chat_fijo_y_configurable(monkeypatch):
    monkeypatch.delenv("DEMO_CHAT_MODEL_ID", raising=False)
    monkeypatch.setenv("LLM_MODEL_ID", "global.anthropic.claude-sonnet-4-6")
    assert json.loads(router_demo.llm_config_demo())["model_id"] == \
        "global.anthropic.claude-haiku-4-5-20251001-v1:0"
    monkeypatch.setenv("DEMO_CHAT_MODEL_ID", "otro-modelo")
    assert json.loads(router_demo.llm_config_demo())["model_id"] == "otro-modelo"


# ---------------------------------------------------------------------------
# 13. Restricción de origen
# ---------------------------------------------------------------------------

def test_origen_ajeno_da_el_mismo_404(client, db):
    from app import models

    r = client.post("/demo/iniciar", json=_cuerpo(),
                    headers={"Origin": "https://sitio-ajeno.example"})
    assert r.status_code == 404 and r.json() == {"detail": "Demo no encontrada"}
    db.expire_all()
    assert db.query(models.Lead).count() == 0

    demo_id, token = _demo_lista(client)
    for metodo, ruta, extra in (
        ("get", f"/demo/{demo_id}/estado", {}),
        ("post", f"/demo/{demo_id}/chat", {"json": {"message": "hola"}}),
    ):
        r = getattr(client, metodo)(ruta, headers={**_h(token), "Origin": "https://evil.example"}, **extra)
        assert r.status_code == 404 and r.json() == {"detail": "Demo no encontrada"}


def test_origen_de_la_landing_y_sin_origen_pasan(client, monkeypatch):
    for origen in ("https://glomacx.com", "https://www.glomacx.com/"):
        r = client.post("/demo/iniciar", json=_cuerpo(correo=f"o{len(origen)}@example.com",
                                                       telefono=f"300 222 {len(origen):04d}"),
                        headers={"Origin": origen, "x-forwarded-for": f"5.5.5.{len(origen)}"})
        assert r.status_code == 202, origen
    assert _iniciar(client).status_code == 202          # sin Origin
    monkeypatch.setenv("DEMO_ALLOWED_ORIGINS", "http://localhost:3000")
    r = client.post("/demo/iniciar", json=_cuerpo(correo="local@example.com", telefono="300 333 0001"),
                    headers={"Origin": "http://localhost:3000"})
    assert r.status_code == 202


# ---------------------------------------------------------------------------
# Re-prueba real (#619): día de la semana, traspaso mudo y nombre repetido
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("saliendo el viernes 12 de diciembre: $7.400.000",
     "saliendo el sábado 12 de diciembre: $7.400.000"),
    ("El Viernes 20 de noviembre", "El Viernes 20 de noviembre"),          # ya está bien
    ("el lunes 16 de octubre", "el viernes 16 de octubre"),                 # hoy
    ("el lunes 15 de octubre", "el viernes 15 de octubre"),                 # ya pasó → 2027
    ("domingo 14 de marzo de 2027", "domingo 14 de marzo de 2027"),
    ("martes 31 de febrero", "martes 31 de febrero"),                       # no existe
    ("el viernes 23 y el sábado 24", "el viernes 23 y el sábado 24"),       # sin mes
])
def test_dias_de_semana_corregidos(crudo, limpio):
    assert llm_engine.dias_de_semana_corregidos(crudo, date(2026, 10, 16)) == limpio


def _escala_sin_texto(resumen):
    return {"content": [{"type": "tool_use", "id": "t1", "name": "escalar_a_asesor",
                         "input": {"motivo": "reserva", "resumen": resumen}}],
            "stop_reason": "tool_use"}


def test_traspaso_mudo_lleva_la_confirmacion_del_resumen():
    with patch.object(llm_engine, "_invoke_model",
                      side_effect=[_escala_sin_texto("Paula Ríos, 2 personas, del 20 al 23 de noviembre")]):
        r = llm_engine.advance(_Bot({"demo": True}), None, "Lo quiero")
    textos = [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]
    assert textos == [
        "Listo 🙌 Te confirmo: Paula Ríos, 2 personas, del 20 al 23 de noviembre. Le "
        "paso tu reserva a una persona del equipo para que confirme la "
        "disponibilidad y te ayude con el pago."
    ]
    assert [a["type"] for a in r["actions"]] == ["say", "handoff"]


@pytest.mark.parametrize("resumen", ["Pide hablar con una persona", "Llamar al 300 123 4567 el 20"])
def test_traspaso_mudo_sin_resumen_util_lleva_el_aviso_generico(resumen):
    with patch.object(llm_engine, "_invoke_model", side_effect=[_escala_sin_texto(resumen)]):
        r = llm_engine.advance(_Bot({"demo": True}), None, "una persona")
    textos = [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]
    assert textos == [llm_engine._TEXTO_TRASPASO_DEMO]


def test_traspaso_mudo_de_otro_bot_no_cambia():
    with patch.object(llm_engine, "_invoke_model",
                      side_effect=[_escala_sin_texto("Paula, 2 personas, 20 de noviembre")]):
        r = llm_engine.advance(_Bot({}), None, "Lo quiero")
    assert [a["type"] for a in r["actions"]] == ["handoff"]


def test_el_nombre_se_pregunta_una_sola_vez_en_la_demo():
    hist = [{"role": "user", "content": "precio?"},
            {"role": "assistant", "content": "Está en $185.000 por persona. ¿Con quién tengo el gusto?"}]
    resp = {"content": [{"type": "text", "text":
            "Para 10 personas serían $1.850.000. ¿Cómo te llamas?"}], "stop_reason": "end_turn"}
    assert _turno_demo({"demo": True}, [resp], hist) == ["Para 10 personas serían $1.850.000."]
    resp2 = {"content": [{"type": "text", "text":
             "Para 10 personas serían $1.850.000. ¿Cómo te llamas?"}], "stop_reason": "end_turn"}
    assert _turno_demo({}, [resp2], hist) == ["Para 10 personas serían $1.850.000. ¿Cómo te llamas?"]


# ---------------------------------------------------------------------------
# Disponibilidad afirmada (guardarraíl de la demo) y pregunta duplicada
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto,viola", [
    ("Ese fin de semana tenemos disponibilidad para ambos tours.", True),
    ("Sí, hay cupo para el sábado.", True),
    ("Está disponible todo noviembre.", True),
    ("La disponibilidad exacta la confirma el equipo al reservar.", False),
    ("El equipo te confirma si hay disponibilidad.", False),
    ("El equipo te confirma la disponibilidad para el 20.", False),
    ("¿Te sirve si hay cupo el sábado?", False),
])
def test_detecta_disponibilidad_afirmada(texto, viola):
    assert llm_engine._viola_disponibilidad_demo({"demo": True}, [texto]) is viola
    assert llm_engine._viola_disponibilidad_demo({}, [texto]) is False


def test_disponibilidad_una_correccion_y_luego_frase_fija():
    afirma = _texto("Tenemos disponibilidad para el puente. El tour vale $180.000 por persona.")
    limpio = _texto("El tour vale $180.000 por persona. ¿Para cuántos sería?")
    with patch.object(llm_engine, "_invoke_model", side_effect=[afirma, limpio]) as m:
        r = llm_engine.advance(_Bot({"demo": True}), None, "¿hay para el puente?")
    assert [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"] == [
        "El tour vale $180.000 por persona. ¿Para cuántos sería?"
    ]
    assert m.call_count == 2
    with patch.object(llm_engine, "_invoke_model", side_effect=[afirma, afirma]):
        r = llm_engine.advance(_Bot({"demo": True}), None, "¿hay para el puente?")
    textos = [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]
    assert textos == [
        "La disponibilidad te la confirma el equipo al reservar. El tour vale $180.000 por persona."
    ]
    # Otro bot: pasa tal cual.
    with patch.object(llm_engine, "_invoke_model", side_effect=[afirma]):
        r = llm_engine.advance(_Bot({}), None, "¿hay para el puente?")
    assert "Tenemos disponibilidad" in r["actions"][0]["payload"]["text"]


def test_pregunta_duplicada_entre_burbujas_del_turno():
    resp = {"content": [
        {"type": "text", "text": "¡Hola! El próximo fin de semana es sáb 24 – dom 25: ¿cuántas noches te gustaría?"},
        {"type": "text", "text": "La suite está en $450.000 por noche.\n\n¿Cuántas noches es para?"},
    ], "stop_reason": "end_turn"}
    with patch.object(llm_engine, "_invoke_model", side_effect=[resp]):
        r = llm_engine.advance(_Bot({"demo": True}), None, "la suite")
    # #621: lo que quedaba terminando en «:» era el arranque de la pregunta
    # quitada y se va con ella.
    assert [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"] == [
        "¡Hola!",
        "La suite está en $450.000 por noche.\n\n¿Cuántas noches es para?",
    ]
