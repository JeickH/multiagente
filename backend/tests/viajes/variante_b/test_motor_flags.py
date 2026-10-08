"""Enganches del bot 2 en `llm_engine`, uno por flag, con el modelo falso.

El modelo va parcheado (`llm_engine._invoke_model`) y las funciones del módulo
de precios (`tarifario.desde_temporada`, `flyer_apertura`, `linea_ninos`,
`extras` y `guardarrail_precio.viola_precio`) se reemplazan por dobles: este
archivo prueba el **motor**, no los precios. Cada flag se prueba encendido y
apagado: apagado, el turno tiene que salir igual que hoy.

Frases inventadas; ningún dato real (CLAUDE.md #8).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

import app.services as servicios
from app.data.bot_viajes import LLM_CONFIG, MEDIA
from app.services import llm_engine, tarifario

FLYER = "tarifario_amordios_ago_nov"
DESDE = 459000
LINEA_NINOS = "Niños: de 0 a 2 años pagan el valor A; de 3 a 4 años, el valor B."
LINEA_EXTRAS = LINEA_NINOS + " Anticipo: 30% para apartar; saldo antes del viaje."
FLYER_DIC = "tarifario_amordios_dic_ene"
#: Las funciones reales del módulo de precios, guardadas antes de los dobles.
_FLYER_REAL = getattr(tarifario, "flyer_apertura", None)


class Bot:
    id = 99
    engine = "llm"
    status = "active"

    def __init__(self, **flags: Any) -> None:
        cfg: Dict[str, Any] = dict(LLM_CONFIG)
        cfg.update(flags)
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


def texto(t: str) -> Dict[str, Any]:
    return {"type": "text", "text": t}


def herramienta(nombre: str, entrada: Dict[str, Any], id_: str = "t1") -> Dict[str, Any]:
    return {"type": "tool_use", "id": id_, "name": nombre, "input": entrada}


def resp(*bloques: Dict[str, Any]) -> Dict[str, Any]:
    con_tool = any(b["type"] == "tool_use" for b in bloques)
    return {"content": list(bloques), "stop_reason": "tool_use" if con_tool else "end_turn"}


def jugar(bot, respuestas: List[Dict[str, Any]], mensaje="Hola, quiero más información",
          estado=None, **runtime):
    with patch.object(llm_engine, "_invoke_model", side_effect=list(respuestas)) as mock:
        salida = llm_engine.advance(bot, estado, mensaje, runtime=dict(runtime))
    return salida, mock


def dichos(salida) -> List[str]:
    return [a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"]


def tipos(salida) -> List[str]:
    return [a["type"] for a in salida["actions"]]


def herramientas(salida) -> List[str]:
    return [t["tool"] for t in salida["telemetry"]["tools"]]


def con_historia(*pares) -> Dict[str, Any]:
    history = []
    for usuario, bot in pares:
        history += [{"role": "user", "content": usuario},
                    {"role": "assistant", "content": bot}]
    return {"history": history}


@pytest.fixture(autouse=True)
def precios_dobles(monkeypatch):
    """Dobles de lo que escribe el agente de precios (puede no existir aún)."""
    monkeypatch.setattr(tarifario, "desde_temporada", lambda hoy: DESDE, raising=False)
    monkeypatch.setattr(tarifario, "flyer_apertura", lambda hoy, cfg=None: FLYER, raising=False)
    monkeypatch.setattr(tarifario, "linea_ninos", lambda: LINEA_NINOS, raising=False)
    monkeypatch.setattr(tarifario, "linea_extras", lambda: LINEA_EXTRAS, raising=False)
    monkeypatch.setattr(tarifario, "extras", lambda: {"anticipo_pct": 30}, raising=False)


@pytest.fixture
def guardarrail(monkeypatch):
    """Un `guardarrail_precio` falso que anota cada llamada y rechaza $549.000."""
    llamadas: List[Dict[str, Any]] = []

    def viola_precio(texto_bot, *, resultados_precios, desde_validos,
                     cifras_cliente, extras):
        llamadas.append({
            "texto": texto_bot, "resultados": list(resultados_precios),
            "desde": set(desde_validos), "cifras": set(cifras_cliente),
            "extras": extras,
        })
        if "$549.000" in texto_bot:
            return "esa fila cuesta otro valor en doble"
        return None

    modulo = types.ModuleType("app.services.guardarrail_precio")
    modulo.viola_precio = viola_precio
    monkeypatch.setitem(sys.modules, "app.services.guardarrail_precio", modulo)
    monkeypatch.setattr(servicios, "guardarrail_precio", modulo, raising=False)
    return llamadas


# ---------------------------------------------------------------------------
# apertura_vitrina (#1 #3 #4 #5)
# ---------------------------------------------------------------------------

class TestAperturaVitrina:
    def _system(self, bot, history=None, **runtime):
        cfg = {**llm_engine.config_de(bot), "_runtime": dict(runtime)}
        return llm_engine._system_prompt(bot, cfg, history or [])

    def test_el_bloque_va_solo_en_el_primer_turno(self):
        bot = Bot(apertura_vitrina=True)
        primero = self._system(bot)
        assert "## Datos para tu primer mensaje" in primero
        assert "$459.000" in primero
        historia = con_historia(("hola", "¡Hola!"))["history"]
        assert "Datos para tu primer mensaje" not in self._system(bot, historia)
        assert "Datos para tu primer mensaje" not in self._system(bot, retomada=True)
        assert "Datos para tu primer mensaje" not in self._system(bot, ya_se_presento=True)

    def test_sin_flag_no_hay_bloque(self):
        assert "Datos para tu primer mensaje" not in self._system(Bot())

    def test_un_solo_texto_corto_sale_como_pie_del_flyer(self):
        saludo = "¡Hola! 😊 Soy *Luisa*. Plan Coveñas desde $459.000. ¿Para qué mes lo estás pensando?"
        salida, _ = jugar(Bot(apertura_vitrina=True), [resp(texto(saludo))])
        assert tipos(salida) == ["say_media"]
        payload = salida["actions"][0]["payload"]
        assert payload["caption"] == saludo
        assert payload["url"] == MEDIA[FLYER]["url"]
        historial = salida["next_state"]["history"][-1]["content"]
        assert saludo in historial and f"[enviaste: {FLYER}]" in historial

    def test_con_dos_textos_el_flyer_va_antes_de_la_pregunta(self):
        salida, _ = jugar(Bot(apertura_vitrina=True), [resp(
            texto("¡Hola! 😊 Soy *Luisa*, de Arranquemos Pues."),
            texto("¿Para qué mes lo estás pensando?"),
        )])
        assert tipos(salida) == ["say", "say_media", "say"]

    def test_si_el_modelo_ya_lo_mando_no_se_duplica(self):
        salida, _ = jugar(Bot(apertura_vitrina=True), [
            resp(herramienta("enviar_media", {"claves": [FLYER]})),
            resp(texto("¿Para qué mes lo estás pensando?")),
        ])
        urls = [a["payload"]["url"] for a in salida["actions"] if a["type"] == "say_media"]
        assert urls == [MEDIA[FLYER]["url"]]

    def test_el_segundo_turno_no_lleva_flyer(self):
        salida, _ = jugar(
            Bot(apertura_vitrina=True), [resp(texto("¿Para cuántas personas?"))],
            mensaje="octubre", estado=con_historia(("hola", "¡Hola! ¿Qué mes?")),
        )
        assert tipos(salida) == ["say"]

    def test_un_flyer_que_no_esta_en_el_catalogo_no_rompe_el_turno(self, monkeypatch):
        monkeypatch.setattr(tarifario, "flyer_apertura", lambda hoy, cfg=None: "no_existe", raising=False)
        salida, _ = jugar(Bot(apertura_vitrina=True), [resp(texto("¿Qué mes?"))])
        assert tipos(salida) == ["say"]
        assert not salida["telemetry"]["failsafe"]

    def test_si_el_tarifario_no_tiene_las_funciones_se_apaga_solo(self, monkeypatch):
        monkeypatch.delattr(tarifario, "flyer_apertura", raising=False)
        monkeypatch.delattr(tarifario, "desde_temporada", raising=False)
        salida, _ = jugar(Bot(apertura_vitrina=True), [resp(texto("¿Qué mes?"))])
        assert tipos(salida) == ["say"]
        assert not salida["telemetry"]["failsafe"]

    def test_sin_flag_no_hay_flyer(self):
        salida, _ = jugar(Bot(), [resp(texto("¿Para qué mes?"))])
        assert tipos(salida) == ["say"]

    # -- Si el primer mensaje nombra un mes, va el flyer de ESE mes ----------

    @staticmethod
    def _por_mes(monkeypatch, vistos):
        """Doble de `flyer_apertura` que responde según el mes de `hoy`."""
        def flyer(hoy, cfg=None):
            vistos.append(hoy)
            if hoy.month in (12, 1):
                return FLYER_DIC
            if hoy.month in (8, 9, 10, 11):
                return FLYER
            return FLYER          # meses sin flyer propio: salta a otro
        monkeypatch.setattr(tarifario, "flyer_apertura", flyer, raising=False)

    def _url_del_flyer(self, mensaje):
        salida, _ = jugar(Bot(apertura_vitrina=True),
                          [resp(texto("¡Hola! 😊 ¿Te cuento las salidas?"))], mensaje=mensaje)
        (url,) = [a["payload"]["url"] for a in salida["actions"] if a["type"] == "say_media"]
        return url

    def test_mes_nombrado_trae_el_flyer_de_ese_mes(self, monkeypatch):
        vistos = []
        self._por_mes(monkeypatch, vistos)
        assert self._url_del_flyer("¿cuánto vale en diciembre?") == MEDIA[FLYER_DIC]["url"]
        assert any(d.month == 12 and d.day == 1 for d in vistos)

    def test_sin_mes_va_el_del_mes_en_curso(self, monkeypatch):
        self._por_mes(monkeypatch, [])
        monkeypatch.setattr(tarifario, "hoy_colombia", lambda: llm_engine.date(2026, 10, 7))
        assert self._url_del_flyer("Hola, quiero más información") == MEDIA[FLYER]["url"]
        assert self._url_del_flyer("soy mayor de edad, ¿puedo ir sola?") == MEDIA[FLYER]["url"]

    def test_mes_sin_flyer_propio_cae_al_del_mes_en_curso(self, monkeypatch):
        vistos = []
        self._por_mes(monkeypatch, vistos)
        monkeypatch.setattr(tarifario, "hoy_colombia", lambda: llm_engine.date(2026, 10, 7))
        # Junio: el doble devuelve un flyer que no cubre junio → no es «el de
        # ese mes», y se usa el del mes en curso.
        assert self._url_del_flyer("¿hay algo en junio?") == MEDIA[FLYER]["url"]
        assert vistos[-1] == llm_engine.date(2026, 10, 7)

    @pytest.mark.skipif(_FLYER_REAL is None, reason="tarifario.flyer_apertura aún no existe")
    def test_con_el_tarifario_real_diciembre_trae_un_flyer_de_diciembre(self, monkeypatch):
        monkeypatch.setattr(tarifario, "flyer_apertura", _FLYER_REAL)
        monkeypatch.setattr(tarifario, "hoy_colombia", lambda: llm_engine.date(2026, 10, 7))
        url = self._url_del_flyer("¿cuánto vale en diciembre?")
        (clave,) = [k for k, v in MEDIA.items() if v["url"] == url]
        assert 12 in MEDIA[clave]["meses"]


# ---------------------------------------------------------------------------
# una_pregunta_por_turno (#10 #17)
# ---------------------------------------------------------------------------

class TestUnaPreguntaPorTurno:
    CASO_543 = [resp(
        texto("¿Cuál de las dos te funciona mejor? Y me dices si prefieres múltiple o doble 🏨"),
        texto("Perfecto 🌴 Mira las opciones para septiembre 👇"),
    )]

    def test_el_bot_no_se_responde_solo(self):
        salida, _ = jugar(Bot(una_pregunta_por_turno=True), self.CASO_543, mensaje="ok")
        assert dichos(salida) == [
            "¿Cuál de las dos te funciona mejor? Y me dices si prefieres múltiple o doble 🏨"
        ]
        assert "Mira las opciones" not in salida["next_state"]["history"][-1]["content"]

    def test_el_adjunto_posterior_sube_antes_de_la_pregunta(self):
        salida, _ = jugar(Bot(una_pregunta_por_turno=True), [
            resp(texto("¿Te cuento de los tours?"), herramienta("enviar_media", {"claves": ["tours"]})),
            resp(texto("Ahí te van 👆")),
        ], mensaje="ok")
        assert tipos(salida) == ["say_media", "say"]
        assert dichos(salida) == ["¿Te cuento de los tours?"]

    def test_dos_preguntas_al_final_queda_la_primera(self):
        salida, _ = jugar(Bot(una_pregunta_por_turno=True), [
            resp(texto("Perfecto 🌴 ¿Para qué mes? ¿Y cuántas personas viajan?")),
        ], mensaje="ok")
        assert dichos(salida) == ["Perfecto 🌴 ¿Para qué mes?"]

    def test_sin_flag_salen_los_dos(self):
        salida, _ = jugar(Bot(), self.CASO_543, mensaje="ok")
        assert len(dichos(salida)) == 2


# ---------------------------------------------------------------------------
# presentacion_una_vez (#11)
# ---------------------------------------------------------------------------

class TestPresentacionUnaVez:
    SALUDO = ("¡Hola de nuevo! 😊 Soy *Luisa*, asesora de la *Agencia de Viajes "
              "Arranquemos Pues*. ¿Para qué mes lo estás pensando?")

    def test_si_ya_se_presento_no_se_vuelve_a_presentar(self):
        salida, _ = jugar(Bot(presentacion_una_vez=True), [resp(texto(self.SALUDO))],
                          ya_se_presento=True)
        (dicho,) = dichos(salida)
        assert "Soy *Luisa*" not in dicho
        assert dicho.startswith("¡Hola de nuevo!")
        assert dicho.endswith("¿Para qué mes lo estás pensando?")

    def test_la_primera_vez_se_presenta(self):
        salida, _ = jugar(Bot(presentacion_una_vez=True), [resp(texto(self.SALUDO))],
                          ya_se_presento=False)
        assert dichos(salida) == [self.SALUDO]

    def test_sin_flag_el_runtime_no_importa(self):
        salida, _ = jugar(Bot(), [resp(texto(self.SALUDO))], ya_se_presento=True)
        assert dichos(salida) == [self.SALUDO]


# ---------------------------------------------------------------------------
# nombre_una_vez (#8)
# ---------------------------------------------------------------------------

class TestNombreUnaVez:
    YA_PREGUNTO = con_historia(("quiero reservar", "¡Genial! ¿A nombre de quién aparto el cupo?"))

    def test_no_se_vuelve_a_preguntar(self):
        salida, _ = jugar(Bot(nombre_una_vez=True), [
            resp(texto("Listo 🙌 Octubre 16 al 19 en doble. ¿A nombre de quién aparto el cupo?")),
        ], mensaje="en doble", estado=self.YA_PREGUNTO)
        assert dichos(salida) == ["Listo 🙌 Octubre 16 al 19 en doble."]

    def test_la_primera_vez_si_se_pregunta(self):
        pregunta = "¡Genial! ¿A nombre de quién aparto el cupo?"
        salida, _ = jugar(Bot(nombre_una_vez=True), [resp(texto(pregunta))],
                          mensaje="quiero reservar", estado=con_historia(("hola", "¡Hola!")))
        assert dichos(salida) == [pregunta]

    def test_con_el_nombre_en_la_ficha_no_se_pregunta(self):
        salida, _ = jugar(Bot(nombre_una_vez=True), [
            resp(texto("¡De una, Marcela! ¿A nombre de quién aparto el cupo?")),
        ], mensaje="quiero reservar", estado=con_historia(("hola", "¡Hola!")),
            contact_name="Marcela")
        assert dichos(salida) == ["¡De una, Marcela!"]

    def test_el_formulario_de_la_reserva_se_queda(self):
        formulario = "Para apartarlo, ¿me regalas tu nombre completo y tu cédula?"
        salida, _ = jugar(Bot(nombre_una_vez=True), [resp(texto(formulario))],
                          mensaje="listo", estado=self.YA_PREGUNTO)
        assert dichos(salida) == [formulario]

    def test_dos_veces_en_el_mismo_turno_queda_la_primera(self):
        salida, _ = jugar(Bot(nombre_una_vez=True), [resp(
            texto("¡Genial! ¿A nombre de quién aparto el cupo?"),
            texto("¿A nombre de quién lo reservo?"),
        )], mensaje="quiero reservar", estado=con_historia(("hola", "¡Hola!")))
        assert dichos(salida) == ["¡Genial! ¿A nombre de quién aparto el cupo?"]
        assert "lo reservo" not in salida["next_state"]["history"][-1]["content"]

    def test_sin_flag_la_repregunta_sale(self):
        repregunta = "Listo 🙌 ¿A nombre de quién aparto el cupo?"
        salida, _ = jugar(Bot(), [resp(texto(repregunta))],
                          mensaje="en doble", estado=self.YA_PREGUNTO)
        assert dichos(salida) == [repregunta]


# ---------------------------------------------------------------------------
# filtrar_nombres_genericos (#9)
# ---------------------------------------------------------------------------

class TestNombresGenericos:
    def _registrar(self, bot, nombre):
        return jugar(bot, [
            resp(herramienta("registrar_nombre", {"nombre": nombre})),
            resp(texto("¡Con gusto! ¿Para qué mes?")),
        ], mensaje="hola", estado=con_historia(("hola", "¡Hola!")))

    @pytest.mark.parametrize("nombre", ["Cliente", "No proporcionado", "Casa"])
    def test_no_se_guarda_un_generico(self, nombre):
        salida, mock = self._registrar(Bot(filtrar_nombres_genericos=True), nombre)
        assert "perfil" not in tipos(salida)
        resultado = mock.call_args_list[1].args[2][-1]["content"][0]["content"]
        assert "no guardé nada" in resultado

    def test_un_nombre_de_verdad_si(self):
        salida, _ = self._registrar(Bot(filtrar_nombres_genericos=True), "Marcela")
        assert {"type": "perfil", "payload": {"nombre": "Marcela"}} in salida["actions"]

    def test_sin_flag_se_guarda_como_hoy(self):
        salida, _ = self._registrar(Bot(), "Cliente")
        assert {"type": "perfil", "payload": {"nombre": "Cliente"}} in salida["actions"]

    def test_un_perfil_generico_cuenta_como_nombre_desconocido(self):
        con = {**llm_engine.config_de(Bot(filtrar_nombres_genericos=True)),
               "_runtime": {"contact_name": "Casa"}}
        sin = {**llm_engine.config_de(Bot()), "_runtime": {"contact_name": "Casa"}}
        assert not llm_engine._ya_se_sabe_el_nombre(con)
        assert "Todavía no sabes cómo se llama" in llm_engine._bloque_continuidad(con)
        assert llm_engine._ya_se_sabe_el_nombre(sin)
        assert "**Casa**" in llm_engine._bloque_continuidad(sin)


# ---------------------------------------------------------------------------
# no_cerrar_aplazadas (#14) — incluida la trampa de `no_responder`
# ---------------------------------------------------------------------------

class TestNoCerrarAplazadas:
    APLAZA = "Mil gracias, lo voy a consultar con mi esposo"
    ESTADO = con_historia(("¿cuánto vale octubre?", "Desde $459.000 por persona 🌴"))

    def test_finalizar_se_anula_y_el_bot_responde(self):
        salida, mock = jugar(Bot(no_cerrar_aplazadas=True), [
            resp(texto("¡Con gusto! Que estés muy bien 😊"),
                 herramienta("finalizar_conversacion", {})),
            resp(texto("¡Claro que sí! Quedo pendiente de lo que decidan 🌴")),
        ], mensaje=self.APLAZA, estado=self.ESTADO)
        assert salida["finished"] is False
        assert "end" not in tipos(salida)
        assert dichos(salida) == ["¡Claro que sí! Quedo pendiente de lo que decidan 🌴"]
        assert "finalizar_conversacion:anulada" in herramientas(salida)
        # La API exige el tool_result del tool_use corregido antes del texto.
        ultimo = mock.call_args_list[1].args[2][-1]["content"]
        assert ultimo[0]["type"] == "tool_result" and ultimo[0]["tool_use_id"] == "t1"
        assert "dejó la decisión para después" in ultimo[-1]["text"]
        assert salida["telemetry"]["camino"] != "fin"

    def test_la_trampa_no_responder_no_vacia_el_turno_corregido(self):
        salida, _ = jugar(Bot(no_cerrar_aplazadas=True), [
            resp(herramienta("no_responder", {})),
            resp(texto("¡Dale! Aquí quedo atenta 😊")),
        ], mensaje=self.APLAZA, estado=self.ESTADO)
        assert salida["finished"] is False
        assert dichos(salida) == ["¡Dale! Aquí quedo atenta 😊"]
        assert "no_responder:anulada" in herramientas(salida)

    def test_una_despedida_de_verdad_si_cierra(self):
        salida, _ = jugar(Bot(no_cerrar_aplazadas=True), [
            resp(texto("¡Que estés muy bien! 😊"), herramienta("finalizar_conversacion", {})),
        ], mensaje="gracias, chao", estado=self.ESTADO)
        assert salida["finished"] is True
        assert "end" in tipos(salida)

    def test_sin_flag_se_cierra_como_hoy(self):
        salida, _ = jugar(Bot(), [
            resp(texto("¡Con gusto! 😊"), herramienta("finalizar_conversacion", {})),
        ], mensaje=self.APLAZA, estado=self.ESTADO)
        assert salida["finished"] is True


# ---------------------------------------------------------------------------
# guardarrail_precio (#18)
# ---------------------------------------------------------------------------

class TestGuardarrailPrecio:
    def test_precio_de_otra_fila_se_corrige(self, guardarrail):
        salida, mock = jugar(Bot(guardarrail_precio=True), [
            resp(texto("En doble te queda en $549.000 por persona 🌴")),
            resp(texto("En doble te queda en $505.000 por persona 🌴")),
        ], mensaje="Amor de Dios 16 al 19 en doble")
        assert dichos(salida) == ["En doble te queda en $505.000 por persona 🌴"]
        correccion = mock.call_args_list[1].args[2][-1]["content"]
        assert "esa fila cuesta otro valor en doble" in correccion
        assert "NO se le envió" in correccion

    def test_le_llegan_los_datos_que_pide_la_firma(self, guardarrail):
        jugar(Bot(guardarrail_precio=True), [
            resp(herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto("Desde $459.000 en múltiple 🌴")),
        ], mensaje="tengo 450 mil, ¿qué hay en octubre?")
        (llamada,) = guardarrail
        assert llamada["resultados"] and "Tarifario de Coveñas" in llamada["resultados"][0]
        assert DESDE in llamada["desde"]
        assert 450000 in llamada["cifras"]
        assert llamada["extras"] == {"anticipo_pct": 30}

    def test_los_precios_consultados_viajan_al_turno_siguiente(self, guardarrail):
        salida, _ = jugar(Bot(guardarrail_precio=True), [
            resp(herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto("Desde $459.000 en múltiple 🌴 ¿Cuántos viajan?")),
        ], mensaje="¿qué hay en octubre?")
        guardados = salida["next_state"]["precios_consultados"]
        assert len(guardados) == 1 and "Tarifario de Coveñas" in guardados[0]

        guardarrail.clear()
        jugar(Bot(guardarrail_precio=True), [resp(texto("Serían $918.000 para los dos"))],
              mensaje="somos 2", estado=salida["next_state"])
        assert guardarrail[0]["resultados"] == guardados

    def test_la_trampa_un_cierre_en_la_ronda_corregida_se_anula(self, guardarrail):
        salida, _ = jugar(Bot(guardarrail_precio=True), [
            resp(texto("Son $549.000 por persona, ¡feliz día!"),
                 herramienta("no_responder", {})),
            resp(texto("Son $505.000 por persona en doble 🌴")),
        ], mensaje="¿y en doble?")
        assert salida["finished"] is False
        assert dichos(salida) == ["Son $505.000 por persona en doble 🌴"]

    def test_las_cifras_del_cliente_las_extrae_el_guardarrail(self, guardarrail, monkeypatch):
        modulo = sys.modules["app.services.guardarrail_precio"]
        monkeypatch.setattr(modulo, "extraer_montos", lambda texto: [123000], raising=False)
        jugar(Bot(guardarrail_precio=True), [resp(texto("Desde $459.000"))],
              mensaje="tengo 450 mil")
        assert guardarrail[0]["cifras"] == {123000}

    # -- Auditoría de seguridad ------------------------------------------------

    def test_h1_sin_montos_del_bot_no_se_lee_al_cliente(self, guardarrail, monkeypatch):
        leidos = []
        modulo = sys.modules["app.services.guardarrail_precio"]
        monkeypatch.setattr(modulo, "extraer_montos",
                            lambda t: (leidos.append(t), [])[1], raising=False)
        jugar(Bot(guardarrail_precio=True), [resp(texto("¿Para qué mes lo estás pensando?"))],
              mensaje="tengo 450 mil", estado=con_historia(*[("1" * 20000, "ok")] * 3))
        assert leidos == ["¿Para qué mes lo estás pensando?"]
        assert guardarrail == []

    def test_h1_del_cliente_se_leen_10_mensajes_recortados(self, guardarrail, monkeypatch):
        leidos = []
        modulo = sys.modules["app.services.guardarrail_precio"]
        monkeypatch.setattr(modulo, "extraer_montos",
                            lambda t: (leidos.append(t), [459000])[1], raising=False)
        jugar(Bot(guardarrail_precio=True), [resp(texto("Desde $459.000"))],
              mensaje="ok", estado=con_historia(*[("9" * 20000, "ok")] * 14))
        del_cliente = leidos[1:]
        assert len(del_cliente) == 10
        assert max(len(t) for t in del_cliente) <= 1000

    @pytest.mark.skipif(importlib.util.find_spec("app.services.guardarrail_precio") is None,
                        reason="guardarrail_precio aún no existe")
    def test_h1_un_historial_de_20000_digitos_no_vuelve_lento_el_guardarrail(self):
        import time
        historia = ["1" * 20000, "3" * 20000 + " mil", "$" + "4" * 20000] * 4
        cfg = llm_engine.config_de(Bot(guardarrail_precio=True))
        t0 = time.perf_counter()
        llm_engine._viola_precio(cfg, ["En doble te queda en $505.000 por persona"],
                                 [], historia)
        assert time.perf_counter() - t0 < 0.1

    def test_m2_agotadas_las_correcciones_el_precio_no_sale(self, guardarrail):
        malo = resp(texto("En doble te queda en $549.000 por persona 🌴"))
        salida, mock = jugar(Bot(guardarrail_precio=True), [malo, malo, malo],
                             mensaje="Amor de Dios del 16 al 19 en doble")
        assert mock.call_count == 3
        assert "549" not in json.dumps(salida["actions"], ensure_ascii=False)
        assert tipos(salida) == ["say", "handoff"]
        assert dichos(salida) == [llm_engine._TEXTO_PRECIO_A_ASESOR]
        handoff = salida["actions"][1]["payload"]
        assert handoff["assignee"] == "" and handoff["motivo"]
        assert salida["finished"] is True
        assert salida["telemetry"]["escalated_to"] == "(por turno)"
        assert "549" not in salida["next_state"]["history"][-1]["content"]

    def test_m2_sin_flag_no_aplica(self, guardarrail):
        malo = resp(texto("Son $549.000"))
        salida, _ = jugar(Bot(), [malo])
        assert dichos(salida) == ["Son $549.000"]

    def test_b4_la_intencion_de_la_ronda_corregida_se_descarta(self, guardarrail):
        salida, _ = jugar(Bot(guardarrail_precio=True, intencion_compra=INTENCION), [
            resp(herramienta("registrar_intencion", {"tipo": "reservar", "resumen": "x"}),
                 texto("Son $549.000 por persona")),
            resp(texto("Son $505.000 por persona")),
        ], mensaje="quiero reservar en doble")
        assert salida["telemetry"]["intenciones"] == []
        assert dichos(salida) == ["Son $505.000 por persona"]

    def test_sin_el_modulo_no_bloquea(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "app.services.guardarrail_precio", None)
        monkeypatch.delattr(servicios, "guardarrail_precio", raising=False)
        salida, _ = jugar(Bot(guardarrail_precio=True), [resp(texto("Son $549.000"))])
        assert dichos(salida) == ["Son $549.000"]
        assert not salida["telemetry"]["failsafe"]

    def test_sin_flag_no_se_consulta(self, guardarrail):
        salida, _ = jugar(Bot(), [resp(texto("Son $549.000"))])
        assert guardarrail == []
        assert "precios_consultados" not in salida["next_state"]


# ---------------------------------------------------------------------------
# cargos_ninos (#19)
# ---------------------------------------------------------------------------

class TestCargosNinos:
    def _resultado_que_vio_el_modelo(self, bot):
        _, mock = jugar(bot, [
            resp(herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto("Te cuento 🌴")),
        ], mensaje="¿octubre?")
        return mock.call_args_list[1].args[2][-1]["content"][0]["content"]

    def test_la_linea_de_extras_va_al_final_del_resultado(self):
        """Niños + anticipo: de ahí saca el bot 2 el 30 % (#16)."""
        resultado = self._resultado_que_vio_el_modelo(Bot(cargos_ninos=True))
        assert resultado.rstrip().endswith(LINEA_EXTRAS)

    def test_sin_linea_extras_cae_a_la_de_ninos(self, monkeypatch):
        monkeypatch.delattr(tarifario, "linea_extras", raising=False)
        resultado = self._resultado_que_vio_el_modelo(Bot(cargos_ninos=True))
        assert resultado.rstrip().endswith(LINEA_NINOS)
        assert "Anticipo" not in resultado

    def test_tambien_en_consultar_precios(self, monkeypatch):
        """La fuente nueva (`consultar_precios`) recibe la misma línea."""
        from app.services import productos_bot
        monkeypatch.setattr(llm_engine, "_fallback_de_producto",
                            lambda cfg, name, entrada: "Tarifario de prueba")
        _, mock = jugar(Bot(cargos_ninos=True), [
            resp(herramienta(productos_bot.PRECIOS, {"mes": "octubre"})),
            resp(texto("Te cuento 🌴")),
        ], mensaje="¿octubre?")
        resultado = mock.call_args_list[1].args[2][-1]["content"][0]["content"]
        assert resultado == f"Tarifario de prueba\n{LINEA_EXTRAS}"

    def test_sin_flag_no(self):
        resultado = self._resultado_que_vio_el_modelo(Bot())
        assert LINEA_NINOS not in resultado and LINEA_EXTRAS not in resultado


# ---------------------------------------------------------------------------
# promo_inexistente (#20 #21)
# ---------------------------------------------------------------------------

PROMO = {
    "montos": [350000],
    "texto": "Déjame confirmarlo con un compañero para no darte un dato equivocado 🙏",
    "motivo": "precio de promoción que no está en el tarifario",
}


class TestPromoInexistente:
    def test_mencionar_el_monto_pasa_a_un_asesor(self):
        salida, _ = jugar(Bot(promo_inexistente=PROMO), [
            resp(texto("Para lunes a jueves no tengo ese valor 🤔 ¿De dónde sacaste esa cifra?")),
        ], mensaje="vi que de lunes a jueves está desde 350 mil")
        assert tipos(salida) == ["say", "handoff"]
        assert dichos(salida) == [PROMO["texto"]]
        handoff = salida["actions"][1]["payload"]
        # Igual que `escalar_a_asesor`: assignee vacío → rotación del team.
        assert handoff["assignee"] == ""
        assert handoff["motivo"] == PROMO["motivo"]
        assert handoff["resumen"]
        assert salida["finished"] is True
        assert salida["telemetry"]["escalated_to"] == "(por turno)"
        assert salida["telemetry"]["camino"] == "escalar_a_asesor"

    def test_es_la_misma_accion_que_escalar_a_asesor(self):
        promo, _ = jugar(Bot(promo_inexistente=PROMO), [resp(texto("Mmm"))],
                         mensaje="la promo de $350.000")
        escalo, _ = jugar(Bot(), [resp(texto("Te paso"),
                                       herramienta("escalar_a_asesor", {"motivo": "x"}))])
        a = next(x for x in promo["actions"] if x["type"] == "handoff")["payload"]
        b = next(x for x in escalo["actions"] if x["type"] == "handoff")["payload"]
        assert set(a) == set(b) and a["assignee"] == b["assignee"] and a["text"] == b["text"]

    def test_se_decide_sin_llamar_al_modelo(self):
        """QA #5: depende sólo del mensaje del cliente → cero rondas, y nunca
        un handoff duplicado."""
        salida, mock = jugar(Bot(promo_inexistente=PROMO), [
            resp(texto("Te paso con un compañero 🙏"),
                 herramienta("escalar_a_asesor", {"motivo": "promo"})),
        ], mensaje="vi la promo de 350k")
        assert mock.call_count == 0
        assert salida["telemetry"]["rounds"] == 0
        assert tipos(salida).count("handoff") == 1
        assert dichos(salida) == [PROMO["texto"]]

    def test_un_monto_que_lo_contiene_no_cuenta(self):
        salida, _ = jugar(Bot(promo_inexistente=PROMO), [resp(texto("¡Claro! 🌴"))],
                          mensaje="mi presupuesto es 1.350.000 para los dos")
        assert "handoff" not in tipos(salida)

    def test_el_monto_dicho_por_el_bot_no_dispara(self):
        salida, _ = jugar(Bot(promo_inexistente=PROMO), [
            resp(texto("Hay salidas desde $350.000"))], mensaje="hola")
        assert "handoff" not in tipos(salida)

    def test_nunca_le_pregunta_de_donde_saco_el_precio(self):
        salida, _ = jugar(Bot(promo_inexistente=PROMO), [
            resp(texto("Ese valor no me aparece 🤔 ¿De dónde sacaste ese precio?")),
        ], mensaje="me dijeron que era más barato")
        assert dichos(salida) == ["Ese valor no me aparece 🤔"]

    def test_sin_flag_el_modelo_decide(self):
        salida, _ = jugar(Bot(), [resp(texto("No tengo ese valor 🤔"))],
                          mensaje="vi la promo de 350 mil")
        assert "handoff" not in tipos(salida)
        assert salida["finished"] is False


# ---------------------------------------------------------------------------
# intencion_compra (#22)
# ---------------------------------------------------------------------------

INTENCION = {"horas_para_interesado": 6}


class TestIntencionCompra:
    def _nombres(self, bot):
        cfg = llm_engine.config_de(bot)
        return [t["name"] for t in llm_engine._tools_for(cfg)]

    def test_la_herramienta_solo_existe_con_el_flag(self):
        assert "registrar_intencion" in self._nombres(Bot(intencion_compra=INTENCION))
        assert "registrar_intencion" not in self._nombres(Bot())

    def test_la_descripcion_dice_cuando_usarla(self):
        cfg = llm_engine.config_de(Bot(intencion_compra=INTENCION))
        (tool,) = [t for t in llm_engine._tools_for(cfg) if t["name"] == "registrar_intencion"]
        for palabra in ("anticipo", "reservar", "fecha", "datos"):
            assert palabra in tool["description"]
        assert tool["input_schema"]["properties"]["tipo"]["enum"] == [
            "anticipo", "reservar", "fecha_concreta", "datos"]

    def test_anota_en_la_telemetria_sin_escribirle_al_cliente(self):
        salida, _ = jugar(Bot(intencion_compra=INTENCION), [
            resp(herramienta("registrar_intencion",
                             {"tipo": "anticipo", "resumen": "Pregunta\x07 cuánto se abona\npara octubre"}),
                 texto("Se aparta con el 30% 🌴")),
            resp(texto("¿Para cuántas personas sería?")),
        ], mensaje="¿con cuánto se separa?")
        assert salida["telemetry"]["intenciones"] == [
            {"tipo": "anticipo", "resumen": "Pregunta cuánto se abona para octubre"}]
        assert set(tipos(salida)) == {"say"}

    def test_tipo_fuera_de_la_lista_no_se_anota(self):
        salida, mock = jugar(Bot(intencion_compra=INTENCION), [
            resp(herramienta("registrar_intencion", {"tipo": "vip", "resumen": "x"})),
            resp(texto("¡Listo!")),
        ], mensaje="quiero ir")
        assert salida["telemetry"]["intenciones"] == []
        resultado = mock.call_args_list[1].args[2][-1]["content"][0]["content"]
        assert "anticipo" in resultado and "no anoté nada" in resultado

    def test_b3_sin_invisibles_ni_numeros_largos(self):
        salida, _ = jugar(Bot(intencion_compra=INTENCION), [
            resp(herramienta("registrar_intencion", {
                "tipo": "datos",
                "resumen": "Ana\u200b\u202e da cel 300 123 4567 y cc 1.234.567.890, viajan 2",
            })),
            resp(texto("¡Listo!")),
        ], mensaje="mis datos")
        resumen = salida["telemetry"]["intenciones"][0]["resumen"]
        assert resumen == "Ana da cel [número] y cc [número], viajan 2"

    def test_el_resumen_se_recorta(self):
        salida, _ = jugar(Bot(intencion_compra=INTENCION), [
            resp(herramienta("registrar_intencion", {"tipo": "reservar", "resumen": "a" * 900})),
            resp(texto("¡Listo!")),
        ], mensaje="quiero reservar")
        assert len(salida["telemetry"]["intenciones"][0]["resumen"]) == 300

    def test_sin_flag_no_hay_clave_en_la_telemetria(self):
        salida, _ = jugar(Bot(), [resp(texto("Hola"))])
        assert "intenciones" not in salida["telemetry"]
