"""Sprint 36: lo que los tres bots de Arranquemos Pues hacen igual al vender.

Pedido del CEO del 7-nov-2026 para los bots 12, 21 y 22 (ver
`app/services/venta_grupo.py`):

  1. Pedir la venta después del total («¿Te aparto los N cupos?»).
  2. El total del grupo con la acomodación correcta, calculado por la
     herramienta (1–2 personas en doble, múltiple desde 3, niños por tramos).
  3. «Sale de Medellín» en el primer mensaje, y ninguna salida inventada desde
     otra ciudad.
  5. Fuera «todo incluido» / «incluye todo», y la doble (+10 %) verificada.
  6. Listo para reservar con solo nombre completo y cédula de quien paga.

Modelo falso, sin red ni Bedrock. Nombres, cédulas y teléfonos inventados
(regla #8).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, List

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import LLM_CONFIG_B
from app.data.bot_viajes_c import LLM_CONFIG_C
from app.services import bot_runner, guardarrail_precio, llm_engine, tarifario, venta_grupo

from .variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    conversacion,
    crear_agencia,
    db,
)

HOY = date(2026, 11, 7)
#: La salida del 20 al 23 de noviembre en Amor de Dios: múltiple $459.000,
#: doble $505.000 (tarifario de la temporada).
SALIDA = "NOVIEMBRE 20 AL 23"
FECHA = "2026-11-20"
TRES = [(LLM_CONFIG, "bot1"), (LLM_CONFIG_B, "bot2"), (LLM_CONFIG_C, "bot3")]


class Bot:
    id = 12
    engine = "llm"
    status = "active"

    def __init__(self, cfg: Dict[str, Any]) -> None:
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


def _resp(*bloques):
    con_tool = any(b["type"] == "tool_use" for b in bloques)
    return {"content": list(bloques), "stop_reason": "tool_use" if con_tool else "end_turn"}


def T(texto: str) -> dict:
    return {"type": "text", "text": texto}


def U(nombre: str, entrada: dict, ident: str = "t1") -> dict:
    return {"type": "tool_use", "id": ident, "name": nombre, "input": entrada}


@pytest.fixture
def modelo(monkeypatch):
    """Modelo falso con guion; guarda lo que recibe en cada llamada."""
    guion: List[Dict[str, Any]] = []
    vistos: List[Dict[str, Any]] = []

    def invocar(model_id, system, working, tools, *a, **k):
        vistos.append({"system": system, "working": json.loads(json.dumps(working)),
                       "tools": tools})
        return guion.pop(0) if guion else _resp(T(""))

    monkeypatch.setattr(llm_engine, "_invoke_model", invocar)
    monkeypatch.setattr(llm_engine, "record_booking", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: HOY)
    return guion, vistos


def _historia(*pares):
    h = []
    for u, a in pares:
        h += [{"role": "user", "content": u}, {"role": "assistant", "content": a}]
    return {"history": h}


def _dichos(salida) -> List[str]:
    fuera = []
    for a in salida["actions"]:
        p = a.get("payload") or {}
        if a["type"] == "say":
            fuera.append(p.get("text") or "")
        elif a["type"] == "say_media" and p.get("caption"):
            fuera.append(p["caption"])
    return fuera


def _turno(cfg, estado, mensaje, **runtime):
    return llm_engine.advance(Bot(json.loads(json.dumps(cfg))), estado, mensaje,
                              runtime=dict(runtime))


def _resultado_de(vistos, nombre_tool_use_id="t1") -> str:
    """El `tool_result` que recibió el modelo para la primera herramienta."""
    for v in vistos:
        for m in v["working"]:
            if m.get("role") != "user" or not isinstance(m.get("content"), list):
                continue
            for b in m["content"]:
                if b.get("type") == "tool_result" and b.get("tool_use_id") == nombre_tool_use_id:
                    return b["content"]
    raise AssertionError("no hubo tool_result")




# ---------------------------------------------------------------------------
# Punto 2 — el total del grupo, calculado
# ---------------------------------------------------------------------------

def _consulta(**kw) -> str:
    return tarifario.consultar({"tarifario": "covenas"}, mes="noviembre", hoy=HOY, **kw)


class TestTotalDelGrupo:
    def test_dos_personas_van_en_doble(self):
        texto, totales = venta_grupo.bloque_total(_consulta(fecha=FECHA), {"adultos": "2"}, hoy=HOY)
        assert "DOBLE" in texto and "MÚLTIPLE" not in texto
        amor = [t for t in totales if t.hotel == "Amor de Dios" and t.etiqueta == SALIDA]
        assert [(t.acomodacion, t.total, t.a_pagar) for t in amor] == [("doble", 1_010_000, 303_000)]
        assert "2 × $505.000 (doble) = $1.010.000 total" in texto
        assert "anticipo del 30%: $303.000" in texto

    def test_una_persona_sola_paga_la_doble(self):
        _, totales = venta_grupo.bloque_total(_consulta(fecha=FECHA), {"adultos": 1}, hoy=HOY)
        amor = [t for t in totales if t.hotel == "Amor de Dios" and t.etiqueta == SALIDA]
        assert [(t.acomodacion, t.total) for t in amor] == [("doble", 505_000)]
        assert venta_grupo.frase_pedir_venta(amor[0]).endswith("¿Te aparto tu cupo? 🙌")

    def test_tres_van_en_multiple_y_la_doble_al_lado(self):
        texto, totales = venta_grupo.bloque_total(_consulta(fecha=FECHA), {"adultos": "3"}, hoy=HOY)
        amor = {t.acomodacion: t.total for t in totales if t.hotel == "Amor de Dios" and t.etiqueta == SALIDA}
        assert amor == {"múltiple": 3 * 459_000, "doble": 3 * 505_000}
        assert "MÚLTIPLE" in texto

    def test_los_ninos_pagan_por_tramo(self):
        """Bebé de meses: seguro ($55.000). 3 años: silla más seguro
        ($195.000). 7 años: paga el plan como un adulto."""
        texto, totales = venta_grupo.bloque_total(
            _consulta(fecha=FECHA), {"adultos": "2", "ninos": "8 meses, 3, 7"}, hoy=HOY,
        )
        amor = {t.acomodacion: t for t in totales if t.hotel == "Amor de Dios" and t.etiqueta == SALIDA}
        # 5 personas → múltiple; pagan el plan los 2 adultos y el de 7.
        assert amor["múltiple"].total == 3 * 459_000 + 55_000 + 195_000
        assert amor["múltiple"].personas == 5
        assert "bebé $55.000" in texto and "niño de 3 años $195.000" in texto

    def test_dos_adultos_y_un_nino_son_tres_del_mismo_grupo(self):
        """Misma lectura del guardarraíl de precio: dos adultos en múltiple
        solo con al menos un niño (la habitación queda con 3 o más)."""
        _, totales = venta_grupo.bloque_total(
            _consulta(fecha=FECHA), {"adultos": "2", "ninos": "3"}, hoy=HOY,
        )
        acoms = {t.acomodacion for t in totales if t.hotel == "Amor de Dios" and t.etiqueta == SALIDA}
        assert acoms == {"múltiple", "doble"}

    def test_con_fecha_solo_van_las_salidas_de_ese_dia(self):
        """El 20 de noviembre arrancan dos: la estándar y la de Barú. Las dos
        llevan su total; ninguna otra del mes."""
        _, totales = venta_grupo.bloque_total(_consulta(fecha=FECHA), {"adultos": "2"}, hoy=HOY)
        assert {t.etiqueta for t in totales} == {SALIDA, "NOVIEMBRE 20 AL 24 (Obsequio a Barú)"}

    def test_sin_fecha_van_las_del_mes_con_tope_por_hotel(self):
        _, totales = venta_grupo.bloque_total(_consulta(), {"adultos": "2"}, hoy=HOY)
        por_hotel: Dict[str, int] = {}
        for t in totales:
            por_hotel[t.hotel] = por_hotel.get(t.hotel, 0) + 1
        assert set(por_hotel) == {"Amor de Dios", "Piedra Mar"}
        assert all(n <= 4 for n in por_hotel.values())

    def test_salida_muy_pronto_se_paga_completa(self):
        hoy = date(2026, 11, 10)   # la del 13 al 16 sale en 3 días
        resultado = tarifario.consultar({"tarifario": "covenas"}, mes="noviembre",
                                        fecha="2026-11-13", hoy=hoy)
        texto, totales = venta_grupo.bloque_total(resultado, {"adultos": "2"}, hoy=hoy)
        amor = [t for t in totales if t.hotel == "Amor de Dios"][0]
        assert amor.pago_total and amor.a_pagar == amor.total
        assert "PAGO TOTAL al reservar" in texto
        frase = venta_grupo.frase_pedir_venta(amor)
        assert "Como la salida es muy pronto" in frase and "anticipo" not in frase

    @pytest.mark.parametrize("entrada,aviso", [
        ({"ninos": "3"}, "cuántos adultos"),
        ({"adultos": "2", "ninos": "un niño"}, "edades"),
        ({"adultos": "16"}, "grupo grande"),
    ])
    def test_datos_que_no_alcanzan_piden_lo_que_falta(self, entrada, aviso):
        texto, totales = venta_grupo.bloque_total(_consulta(fecha=FECHA), entrada, hoy=HOY)
        assert aviso in texto and totales == []

    def test_sin_grupo_no_se_agrega_nada(self):
        assert venta_grupo.bloque_total(_consulta(fecha=FECHA), {}, hoy=HOY) == ("", [])

    def test_el_total_y_el_anticipo_pasan_el_guardarrail_de_precio(self):
        """El bot 2 y el 3 validan cada cifra contra la fila: el total del
        sistema no puede tumbarles el turno."""
        resultado = _consulta(fecha=FECHA)
        texto, totales = venta_grupo.bloque_total(
            resultado, {"adultos": "2", "ninos": "3"}, hoy=HOY,
        )
        doble = [t for t in totales if t.hotel == "Amor de Dios" and t.etiqueta == SALIDA
                 and t.acomodacion == "doble"][0]
        mensaje = (
            f"Para los 3 del *{SALIDA}* en Amor de Dios, en doble, con el niño de "
            f"3 años son *${doble.total:,}* en total 🌴 ".replace(",", ".")
            + venta_grupo.frase_pedir_venta(doble)
        )
        assert guardarrail_precio.viola_precio(
            mensaje, resultados_precios=[resultado + "\n" + texto],
            extras=tarifario.extras(), desde_validos=set(), cifras_cliente=set(),
        ) is None


class TestLaHerramientaRecibeElGrupo:
    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_los_tres_bots_declaran_adultos_y_ninos(self, cfg, _id):
        tools = llm_engine._tools_for(dict(cfg), None, "")
        precios = next(t for t in tools if t["name"] == "consultar_tarifario")
        props = precios["input_schema"]["properties"]
        assert {"adultos", "ninos"} <= set(props)

    def test_un_bot_sin_tarifario_no_cambia(self):
        sin = {k: v for k, v in LLM_CONFIG.items() if k != "tarifario"}
        nombres = [t["name"] for t in llm_engine._tools_for(sin, None, "")]
        assert "consultar_tarifario" not in nombres

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_el_resultado_trae_el_total_en_los_tres(self, modelo, cfg, _id):
        guion, vistos = modelo
        guion.extend([
            _resp(U("consultar_tarifario", {"mes": "noviembre", "fecha": FECHA,
                                            "hotel": "Amor de Dios", "adultos": "2"})),
            _resp(T("¡Listo! 🌴")),
        ])
        _turno(cfg, _historia(("hola", "¡Hola! Soy *Luisa*.")),
               "somos 2 para el 20 de noviembre en Amor de Dios")
        resultado = _resultado_de(vistos)
        assert "TOTAL DEL GRUPO" in resultado
        assert "2 × $505.000 (doble) = $1.010.000 total" in resultado


# ---------------------------------------------------------------------------
# Punto 5b — la doble es la múltiple + 10 %, en los tres bots
# ---------------------------------------------------------------------------

class TestLaDoble:
    def test_en_todo_el_tarifario_la_doble_es_la_multiple_mas_10(self):
        """Las 102 filas: la doble es la múltiple + 10 %, redondeada a miles
        (la del Simulacro, $537.900, es exacta)."""
        planes = tarifario._datos()["planes"]
        assert len(planes) >= 100
        for p in planes:
            assert abs(p["doble"] - p["multiple"] * 1.1) <= 1_000, p["fecha"]

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_cada_bot_cotiza_la_doble_de_la_tabla(self, modelo, cfg, _id):
        """Lo que recibe cada bot de su consulta: doble = múltiple + 10 %, y a
        2 personas el total sale en doble."""
        guion, vistos = modelo
        guion.extend([
            _resp(U("consultar_tarifario", {"mes": "noviembre", "adultos": "2"})),
            _resp(T("¡Listo! 🌴")),
        ])
        _turno(cfg, _historia(("hola", "¡Hola! Soy *Luisa*.")), "somos 2, noviembre")
        resultado = _resultado_de(vistos)
        filas = guardarrail_precio.filas_de_resultados([resultado])
        assert filas
        for f in filas:
            assert abs(f.doble - f.multiple * 1.1) <= 1_000, f.etiqueta
        for linea in resultado.splitlines():
            if "(doble) =" in linea or "(múltiple) =" in linea:
                assert "(múltiple)" not in linea, linea


# ---------------------------------------------------------------------------
# Punto 1 — pedir la venta después del total
# ---------------------------------------------------------------------------

def _cotiza(guion, texto, adultos="2"):
    guion.extend([
        _resp(U("consultar_tarifario", {"mes": "noviembre", "fecha": FECHA,
                                        "hotel": "Amor de Dios", "adultos": adultos})),
        _resp(T(texto)),
    ])


ESTADO = _historia(("hola", "¡Hola! 😊 Soy *Luisa*. ¿Para qué mes lo estás pensando?"))


class TestPedirLaVenta:
    @pytest.mark.parametrize("cfg,_id", [TRES[0], TRES[1]], ids=["bot1", "bot2"])
    def test_tras_el_total_se_pide_la_venta(self, modelo, cfg, _id):
        guion, _ = modelo
        _cotiza(guion, "Para los 2 en doble del *20 al 23* son *$1.010.000* en total 🌴 ¿Te sirve?")
        salida = _turno(cfg, ESTADO, "somos 2, la del 20 de noviembre en Amor de Dios")
        texto = "\n".join(_dichos(salida))
        assert "¿Te aparto los 2 cupos? 🙌" in texto
        assert "*anticipo de $303.000*" in texto
        assert "¿Te sirve?" not in texto, "la otra pregunta se reemplaza, no se suma"
        assert texto.rstrip().endswith("¿Te aparto los 2 cupos? 🙌")

    def test_el_bot_3_la_pide_con_sus_opciones(self, modelo):
        guion, _ = modelo
        texto_modelo = "Para los 2 en doble del *20 al 23* son *$1.010.000 total* 🌴"
        _cotiza(guion, texto_modelo)
        # La corrección de opciones cerradas del bot 3 pide reintentar una vez;
        # el modelo repite y ahí pasa.
        guion.append(_resp(T(texto_modelo)))
        salida = _turno(LLM_CONFIG_C, ESTADO, "somos 2, la del 20 de noviembre en Amor de Dios")
        texto = "\n".join(_dichos(salida))
        assert "¿Te aparto los 2 cupos? 🙌 👇\n1️⃣ Sí, quiero reservar ✅" in texto

    def test_si_ya_la_pidio_no_se_toca(self, modelo):
        guion, _ = modelo
        dicho = ("Para los 2 son *$1.010.000* en total 🌴 Se aparta con un anticipo "
                 "de $303.000. ¿Te los aparto?")
        _cotiza(guion, dicho)
        salida = _turno(LLM_CONFIG, ESTADO, "somos 2, la del 20 de noviembre")
        assert _dichos(salida) == [dicho]

    def test_si_no_dijo_el_total_no_se_toca(self, modelo):
        guion, _ = modelo
        dicho = "En Amor de Dios la doble está en $505.000 por persona 🌴 ¿Cuántos viajan?"
        _cotiza(guion, dicho)
        salida = _turno(LLM_CONFIG, ESTADO, "la del 20 de noviembre")
        assert _dichos(salida) == [dicho]

    def test_si_pregunta_la_acomodacion_no_se_toca(self, modelo):
        guion, _ = modelo
        dicho = ("Para los 3: múltiple *$1.377.000 total* o doble *$1.515.000 total* 🌴 "
                 "¿Cuál acomodación prefieren?")
        _cotiza(guion, dicho, adultos="3")
        salida = _turno(LLM_CONFIG, ESTADO, "somos 3")
        assert _dichos(salida) == [dicho]

    def test_si_lo_va_a_pensar_no_se_insiste(self, modelo):
        guion, _ = modelo
        dicho = "¡Claro! Son *$1.010.000* en total para los 2 🌴 Me cuentas cuando lo hables 😊"
        _cotiza(guion, dicho)
        salida = _turno(LLM_CONFIG, ESTADO, "lo voy a consultar con mi esposo, ¿cuánto sería para 2?")
        assert _dichos(salida) == [dicho]


# ---------------------------------------------------------------------------
# Punto 3 — sale de Medellín
# ---------------------------------------------------------------------------

APERTURA = ("¡Hola! 😊 Soy *Luisa*, asesora de la *Agencia de Viajes Arranquemos "
            "Pues*. Te cuento del plan 🌴\n\n¿Para qué mes lo estás pensando? 😊")
#: El bot 3 cierra cada mensaje con opciones (si no, su guardarraíl corrige).
OPCIONES = "\n1️⃣ Noviembre\n2️⃣ Diciembre"


def _con_opciones(cfg, texto: str) -> str:
    return texto + OPCIONES if cfg.get("opciones_cerradas") else texto


class TestSaleDeMedellin:
    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_el_primer_mensaje_lo_dice_en_los_tres(self, modelo, cfg, _id):
        guion, _ = modelo
        guion.append(_resp(T(_con_opciones(cfg, APERTURA))))
        salida = _turno(cfg, None, "Hola, quiero más información")
        texto = "\n".join(_dichos(salida))
        assert "*Medellín*" in texto
        assert texto.index("Medellín") < texto.index("¿Para qué mes")

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_los_guiones_lo_dicen_en_la_apertura(self, cfg, _id):
        guion = llm_engine._instrucciones_de(Bot(dict(cfg)), dict(cfg))
        assert "Medellín" in guion

    def test_si_ya_lo_dijo_no_se_repite(self, modelo):
        guion, _ = modelo
        dicho = APERTURA.replace("Te cuento del plan", "El plan sale de *Medellín*")
        guion.append(_resp(T(dicho)))
        salida = _turno(LLM_CONFIG, None, "Hola")
        assert _dichos(salida) == [dicho]

    def test_no_en_un_turno_que_no_es_el_primero(self, modelo):
        guion, _ = modelo
        guion.append(_resp(T(APERTURA)))
        salida = _turno(LLM_CONFIG, ESTADO, "hola")
        assert "Medellín" not in "\n".join(_dichos(salida))

    @pytest.mark.parametrize("frase", [
        "Sí, también salimos desde Cali 🚌",
        "Te recogemos en Bogotá sin problema",
        "Desde Pereira sale un bus el viernes",
        "La salida de Cali es a las 6 p.m.",
    ])
    def test_inventar_una_salida_desde_otra_ciudad_viola(self, frase):
        assert venta_grupo.afirma_salida_otra_ciudad([frase])

    @pytest.mark.parametrize("frase", [
        "El plan sale solo desde Medellín, no tenemos salida desde Cali 🚌",
        "No hay recogidas en Bogotá: sale de Medellín",
        "¡Qué bien que nos escribas desde Cali! El plan sale de Medellín",
    ])
    def test_decir_la_verdad_no_viola(self, frase):
        assert not venta_grupo.afirma_salida_otra_ciudad([frase])

    def test_el_motor_corrige_la_salida_inventada(self, modelo):
        guion, vistos = modelo
        bueno = "El plan sale solo desde *Medellín* 🚌 ¿Para qué mes lo estás pensando?"
        guion.extend([_resp(T("¡Claro! También salimos desde Cali 🚌")), _resp(T(bueno))])
        salida = _turno(LLM_CONFIG, ESTADO, "vivo en Cali, ¿salen desde allá?")
        assert _dichos(salida) == [bueno]
        assert "SOLO desde Medellín" in json.dumps(vistos[-1]["working"], ensure_ascii=False)
        assert not salida["finished"]


# ---------------------------------------------------------------------------
# Punto 5 — fuera «todo incluido»
# ---------------------------------------------------------------------------

class TestTodoIncluido:
    @pytest.mark.parametrize("antes,despues", [
        ("Es un plan todo incluido 🌴", "Es un plan con hotel, transporte y alimentación 🌴"),
        ("Todo incluido: hotel y bus", "Con hotel, transporte y alimentación: hotel y bus"),
        ("El plan incluye todo 🙌", "El plan incluye hotel, transporte y alimentación 🙌"),
        ("¡Todo está incluido!", "¡Con hotel, transporte y alimentación!"),
    ])
    def test_se_reescribe(self, antes, despues):
        assert venta_grupo.sin_todo_incluido(antes) == despues

    @pytest.mark.parametrize("texto", [
        "No es todo incluido: la alimentación va desde el desayuno del sábado.",
        "El plan incluye todo lo que ves en la imagen 👆",
        "Incluye hotel, transporte y alimentación desde el desayuno del sábado.",
    ])
    def test_lo_que_esta_bien_no_se_toca(self, texto):
        assert venta_grupo.sin_todo_incluido(texto) == texto

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_no_le_llega_al_cliente_en_los_tres(self, modelo, cfg, _id):
        guion, _ = modelo
        guion.append(_resp(T(_con_opciones(cfg, "¡Sí! Es todo incluido 🌴 ¿Para qué mes?"))))
        salida = _turno(cfg, ESTADO, "¿es todo incluido?")
        texto = "\n".join(_dichos(salida)).lower()
        assert "todo incluido" not in texto
        assert "hotel, transporte y alimentación" in texto
        assert "todo incluido" not in salida["next_state"]["history"][-1]["content"].lower()

    @pytest.mark.parametrize("antes,despues", [
        ("¡Sí! 🙌 Incluye hotel, transporte y alimentación.", "Incluye hotel, transporte y alimentación."),
        ("Sí, el plan incluye *hotel* y transporte.", "El plan incluye *hotel* y transporte."),
        ("¡Claro que sí! Incluye hotel.", "Incluye hotel."),
        ("Claro 🙌 Incluye *hotel* y transporte.", "Incluye *hotel* y transporte."),
        ("Siempre salimos de Medellín.", "Siempre salimos de Medellín."),
        ("El plan incluye hotel.", "El plan incluye hotel."),
    ])
    def test_a_la_pregunta_no_se_le_contesta_si(self, antes, despues):
        assert venta_grupo.sin_si_a_todo_incluido(antes) == despues

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_el_motor_quita_el_si_solo_si_preguntaron_por_todo_incluido(self, modelo, cfg, _id):
        guion, _ = modelo
        dicho = _con_opciones(cfg, "¡Sí! 🙌 Incluye hotel, transporte y alimentación desde el sábado. ¿Para qué mes?")
        guion.append(_resp(T(dicho)))
        salida = _turno(cfg, ESTADO, "¿el plan es todo incluido?")
        assert _dichos(salida)[0].startswith("Incluye hotel")
        guion.append(_resp(T(dicho)))
        salida = _turno(cfg, ESTADO, "¿hay salida en noviembre?")
        assert _dichos(salida)[0].startswith("¡Sí! 🙌")

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_los_guiones_no_lo_mencionan(self, cfg, _id):
        guion = llm_engine._instrucciones_de(Bot(dict(cfg)), dict(cfg)).lower()
        assert "todo incluido" not in guion and "incluye todo" not in guion


# ---------------------------------------------------------------------------
# Punto 6 — listo para reservar con nombre completo y cédula
# ---------------------------------------------------------------------------

PIDE_DATOS = _historia((
    "quiero reservar",
    "¡Qué bien! 🙌 Para apartar tu cupo solo necesito el *nombre completo* y la "
    "*cédula* de quien paga 📝",
))
DATOS = "Carlos Gómez Ruiz, 1000000002"
COBRO = ("¡Listo, recibí tus datos! ✅ Para apartar pagas el anticipo. Haz la "
         "transferencia y mándame el comprobante por aquí 📎")


class TestCierreConCedula:
    @pytest.mark.parametrize("texto,esperado", [
        ("Carlos Gómez Ruiz, 1000000002", True),
        ("Carlos Gómez CC 79.456.123", True),
        ("mi cédula es 1000000002", False),          # sin nombre completo
        ("Carlos Gómez, cel 3000000000", False),     # un celular no es cédula
        ("somos 2 para noviembre", False),
    ])
    def test_reconoce_nombre_completo_y_cedula(self, texto, esperado):
        assert venta_grupo.trae_datos_de_quien_paga(texto) is esperado

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_los_guiones_piden_solo_nombre_y_cedula(self, cfg, _id):
        guion = llm_engine._instrucciones_de(Bot(dict(cfg)), dict(cfg))
        assert "fecha de nacimiento" not in guion
        assert "de **cada viajero**" not in guion and "de cada viajero" not in guion
        assert "*nombre completo*" in guion and "*cédula*" in guion
        assert "quien paga" in guion

    def test_las_reglas_de_la_agencia_lo_dicen(self):
        reglas = llm_engine._bloque_reglas_agencia(dict(LLM_CONFIG))
        assert "el nombre completo y la cédula" in reglas
        assert "fecha de nacimiento" not in reglas

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_si_pide_mas_datos_se_corrige_y_cierra(self, modelo, cfg, _id):
        guion, vistos = modelo
        guion.extend([
            _resp(T("¡Gracias! ¿Me pasas también la fecha de nacimiento y el correo?")),
            _resp(T(COBRO), U("listo_para_reservar", {"resumen": "20-23 nov, Amor de Dios, 2 adultos, doble",
                                                     "datos": DATOS})),
            _resp(T("")),
        ])
        salida = _turno(cfg, PIDE_DATOS, DATOS)
        assert salida["finished"]
        handoff = next(a for a in salida["actions"] if a["type"] == "handoff")
        assert handoff["payload"]["etiqueta"] == llm_engine.ETIQUETA_LISTO_PARA_RESERVAR
        assert "demás viajeros" in handoff["payload"]["motivo"]
        assert "fecha de nacimiento" not in "\n".join(_dichos(salida))
        assert "nombre completo y la cédula de quien paga" in json.dumps(
            vistos[1]["working"], ensure_ascii=False)

    def test_sin_haberle_pedido_los_datos_no_se_corrige(self, modelo):
        guion, _ = modelo
        dicho = "¡Hola Carlos! 🌴 ¿Para qué mes lo estás pensando?"
        guion.append(_resp(T(dicho)))
        salida = _turno(LLM_CONFIG, ESTADO, DATOS)
        assert _dichos(salida) == [dicho]

    def test_la_nota_a_la_asesora_dice_que_faltan_los_demas(self, db, modelo):
        """Por el camino de producción (`bot_runner.run_turn`)."""
        guion, _ = modelo
        guion.extend([
            _resp(T(COBRO), U("listo_para_reservar", {"resumen": "20-23 nov, Amor de Dios, 2 adultos",
                                                     "datos": DATOS})),
            _resp(T("")),
        ])
        ag = crear_agencia(db, sufijo="S36", cfg=json.loads(json.dumps(LLM_CONFIG)))
        conv = conversacion(db, ag["team"])
        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                            user_input=DATOS, meta_account=None)
        from app import models
        notas = [m.content for m in db.query(models.Message).filter(
            models.Message.conversation_id == conv.id,
            models.Message.message_type == "nota_interna")]
        assert notas and notas[-1].startswith("🟢 *Listo para reservar*")
        assert "demás viajeros" in notas[-1] and "1000000002" in notas[-1]


# ---------------------------------------------------------------------------
# La fuente de producción: `consultar_precios` sobre el tarifario importado
# ---------------------------------------------------------------------------

class TestPorLaFuenteDeProduccion:
    """Los bots 12, 21 y 22 leen precios de `bot_producto_filas`
    (`fuente_datos=productos`): la herramienta es `consultar_precios`, no
    `consultar_tarifario`. El total y la doble tienen que salir igual."""

    @pytest.fixture
    def cuenta(self, monkeypatch):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.database import Base
        from app.services import productos
        from tests.productos import covenas
        from tests.productos.conftest import crear_cuenta

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                               poolclass=StaticPool)
        Base.metadata.create_all(engine)
        Sesion_ = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        sesion = Sesion_()
        team_id, bot_id = crear_cuenta(sesion, "s36")
        covenas.cargar(sesion, team_id=team_id, bot_id=bot_id)
        sesion.commit()
        monkeypatch.setattr(llm_engine, "_productos_db", Sesion_)
        monkeypatch.setattr(productos, "hoy_colombia", lambda: HOY)
        productos.limpiar_cache()
        yield team_id, bot_id
        productos.limpiar_cache()
        sesion.close()
        engine.dispose()

    @pytest.mark.parametrize("cfg,_id", TRES, ids=[i for _, i in TRES])
    def test_consultar_precios_trae_el_total_en_doble(self, modelo, cuenta, cfg, _id):
        team_id, bot_id = cuenta
        guion, vistos = modelo
        guion.extend([
            _resp(U("consultar_precios", {"mes": "noviembre", "fecha": FECHA,
                                          "variante": "Amor de Dios", "adultos": "2"})),
            _resp(T("Para los 2 en doble son *$1.010.000* en total 🌴")),
        ])
        conf = {**json.loads(json.dumps(cfg)), "fuente_datos": "productos"}
        bot = Bot(conf)
        bot.id, bot.team_id, bot.instrucciones = bot_id, team_id, None
        salida = llm_engine.advance(bot, ESTADO, "somos 2, la del 20 de noviembre")
        precios = next(t for t in vistos[0]["tools"] if t["name"] == "consultar_precios")
        assert {"adultos", "ninos"} <= set(precios["input_schema"]["properties"])
        resultado = _resultado_de(vistos)
        assert "2 × $505.000 (doble) = $1.010.000 total" in resultado
        for f in guardarrail_precio.filas_de_resultados([resultado]):
            assert abs(f.doble - f.multiple * 1.1) <= 1_000, f.etiqueta
        texto = "\n".join(_dichos(salida))
        if not cfg.get("opciones_cerradas"):
            assert "¿Te aparto los 2 cupos? 🙌" in texto
