"""Arreglos del motor del bot 3 tras QA contra Bedrock (2026-10-10).

Transcripciones en `entregables/transcripciones_c/2026-10-10/`. Un bloque por
punto del reporte de QA, con y sin su flag. Modelo falso; para M3, un cliente
de Bedrock simulado que captura el cuerpo de la llamada.
"""
from __future__ import annotations

import io
import json
from typing import Any, Dict, List
from unittest.mock import patch

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine, tarifario

RESULTADO = (
    "Amor de Dios — Octubre (2 salidas):\n"
    "  · OCTUBRE 16 AL 19 — múltiple $459.000 · doble $505.000 (2 noches / 3 días, Plan estándar)\n"
    "  · OCTUBRE 16 AL 20 (Obsequio a Barú) — múltiple $550.000 · doble $605.000 "
    "(3 noches / 4 días, Obsequio a Barú)\n"
)
MENU_COTIZACION = (
    "Para 2 personas del 18 al 21 en Amor de Dios 🌴 ¿Cuál prefieres? 👇\n"
    "1️⃣ Múltiple → $918.000 total\n2️⃣ Doble → $1.010.000 total"
)


class Bot:
    id = 79
    engine = "llm"
    status = "active"

    def __init__(self, **flags):
        self.llm_config = json.dumps({**LLM_CONFIG, **flags}, ensure_ascii=False)


def texto(t):
    return {"type": "text", "text": t}


def herramienta(nombre, entrada, id_="t1"):
    return {"type": "tool_use", "id": id_, "name": nombre, "input": entrada}


def resp(*bloques):
    con_tool = any(b["type"] == "tool_use" for b in bloques)
    return {"content": list(bloques), "stop_reason": "tool_use" if con_tool else "end_turn"}


def jugar(bot, respuestas, mensaje="ok", estado=None, **runtime):
    with patch.object(llm_engine, "_invoke_model", side_effect=list(respuestas)) as mock:
        salida = llm_engine.advance(bot, estado, mensaje, runtime=dict(runtime))
    return salida, mock


def dichos(salida) -> List[str]:
    return [a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"]


def tipos(salida) -> List[str]:
    return [a["type"] for a in salida["actions"]]


def estado(*pares, **extra) -> Dict[str, Any]:
    history = []
    for usuario, bot in pares:
        history += [{"role": "user", "content": usuario},
                    {"role": "assistant", "content": bot}]
    return {"history": history, **extra}


def enviados(mock) -> str:
    return json.dumps(mock.call_args_list[-1].args[2], ensure_ascii=False)


# ---------------------------------------------------------------------------
# A1 — «gracias» tras el precio no cierra
# ---------------------------------------------------------------------------

class TestA1NoCerrarTrasElMenu:
    FLAGS = {"opciones_cerradas": True}
    ESTADO = estado(("diciembre, 18 al 21, somos 2", MENU_COTIZACION), etapa="cotizacion")
    SIGUE = resp(texto("¡Con gusto! 😊 ¿Cómo sigue? 👇\n1️⃣ Quiero reservar ✅\n2️⃣ Lo voy a consultar 💬"))

    @pytest.mark.parametrize("cierre", ["no_responder", "finalizar_conversacion"])
    def test_gracias_no_cierra(self, cierre):
        salida, mock = jugar(Bot(**self.FLAGS), [resp(herramienta(cierre, {})), self.SIGUE],
                             mensaje="gracias", estado=self.ESTADO)
        assert salida["finished"] is False
        assert dichos(salida) == [self.SIGUE["content"][0]["text"]]
        assert "sólo agradeció" in enviados(mock)

    def test_despedida_explicita_si_cierra(self):
        salida, mock = jugar(Bot(**self.FLAGS), [resp(herramienta("no_responder", {}))],
                             mensaje="gracias, ya no me interesa", estado=self.ESTADO)
        assert salida["finished"] is True and mock.call_count == 1

    def test_antes_del_embudo_no_aplica(self):
        salida, _ = jugar(Bot(**self.FLAGS), [resp(herramienta("no_responder", {}))],
                          mensaje="gracias", estado=estado(("hola", MENU_COTIZACION), etapa="bienvenida"))
        assert salida["finished"] is True

    def test_sin_flag(self):
        salida, _ = jugar(Bot(), [resp(herramienta("no_responder", {}))],
                          mensaje="gracias", estado=self.ESTADO)
        assert salida["finished"] is True


# ---------------------------------------------------------------------------
# A2 — duración contra lo consultado en la sesión
# ---------------------------------------------------------------------------

class TestA2DuracionConSesion:
    TEXTO = resp(texto("¿Cuál te sirve? 👇\n1️⃣ *Octubre 16 al 19* (2 noches / 3 días)\n"
                       "2️⃣ *Octubre 16 al 20 Obsequio a Barú* (3 noches / 4 días)"))
    ESTADO = estado(("octubre", "Te dejo las salidas"), precios_consultados=[RESULTADO])

    def test_lo_consultado_antes_cuenta(self):
        _, mock = jugar(Bot(duracion_por_plan=True, guardarrail_precio=True,
                            duracion_con_sesion=True),
                        [self.TEXTO, self.TEXTO], mensaje="¿el bus tiene baño?", estado=self.ESTADO)
        assert mock.call_count == 1

    def test_sin_flag_es_el_falso_positivo_de_c15b(self):
        _, mock = jugar(Bot(duracion_por_plan=True, guardarrail_precio=True),
                        [self.TEXTO] * 3, mensaje="¿el bus tiene baño?", estado=self.ESTADO)
        assert mock.call_count > 1               # hubo corrección


# ---------------------------------------------------------------------------
# A3 — promete un compañero sin escalar
# ---------------------------------------------------------------------------

PROMESA = resp(texto("¡Buena pregunta! 🚌 Eso lo confirmo con un compañero para darte el dato exacto 🙌"))


class TestA3Promesa:
    def test_primero_se_corrige(self):
        salida, mock = jugar(Bot(escalar_si_promete=True), [
            PROMESA,
            resp(texto("Te paso con un compañero que te confirma 🙌"),
                 herramienta("escalar_a_asesor", {"motivo": "baño del bus"})),
        ], mensaje="¿el bus tiene baño?", estado=estado(("hola", "¡Hola!")))
        assert "escalar_a_asesor" in enviados(mock)
        assert tipos(salida) == ["say", "handoff"]

    def test_si_persiste_se_cumple_la_promesa(self):
        salida, mock = jugar(Bot(escalar_si_promete=True), [PROMESA, PROMESA],
                             mensaje="¿el bus tiene baño?", estado=estado(("hola", "¡Hola!")))
        assert mock.call_count == 2
        assert tipos(salida) == ["say", "handoff"]
        handoff = salida["actions"][-1]["payload"]
        assert handoff["motivo"] == "pregunta sin respuesta" and handoff["assignee"] == ""
        assert salida["finished"] is True
        assert salida["telemetry"]["escalated_to"] == "(por turno)"

    def test_si_escala_en_el_mismo_turno_no_hay_correccion(self):
        _, mock = jugar(Bot(escalar_si_promete=True), [resp(
            texto("Eso lo confirma un compañero 🙌"), herramienta("escalar_a_asesor", {"motivo": "x"}))],
            mensaje="¿el bus tiene baño?", estado=estado(("hola", "¡Hola!")))
        assert mock.call_count == 1

    def test_sin_flag(self):
        salida, mock = jugar(Bot(), [PROMESA], mensaje="¿el bus tiene baño?",
                             estado=estado(("hola", "¡Hola!")))
        assert mock.call_count == 1 and "handoff" not in tipos(salida)


# ---------------------------------------------------------------------------
# M0 — /bienvenida_regreso sin modelo
# ---------------------------------------------------------------------------

REGRESO = {
    "con_contexto": "¡Hola de nuevo! 😊 La última vez miraste {mes_hotel}. ¿Seguimos? 👇\n"
                    "1️⃣ Seguir con esa cotización\n2️⃣ Ver otras fechas 📅\n3️⃣ Tengo una pregunta 🤔",
    "sin_contexto": "¡Hola de nuevo! 😊 ¿Seguimos con tu plan a Coveñas? 👇\n"
                    "1️⃣ Ver salidas y precios 📅\n2️⃣ Seguir donde íbamos\n3️⃣ Tengo una pregunta 🤔",
}


class TestM0Regreso:
    FLAGS = {"regreso_sin_modelo": True, "bienvenida_regreso": REGRESO, "etapas_funnel": True}

    def test_con_contexto(self):
        salida, mock = jugar(Bot(**self.FLAGS), [], mensaje="¡Hola! Quiero más información",
                             ya_se_presento=True, ultimo_mes="diciembre",
                             ultimo_hotel="piedra mar", etapa_previa="cotizacion")
        assert mock.call_count == 0
        (dicho,) = dichos(salida)
        assert dicho.startswith("¡Hola de nuevo! 😊 La última vez miraste *diciembre* en *Piedra Mar*.")
        assert "1️⃣ Seguir con esa cotización" in dicho
        assert salida["next_state"]["etapa"] == "cotizacion"
        assert salida["finished"] is False

    def test_sin_contexto_valido(self):
        salida, _ = jugar(Bot(**self.FLAGS), [], mensaje="hola", ya_se_presento=True,
                          ultimo_mes="Ana {x}", etapa_previa="nada")
        assert dichos(salida) == [REGRESO["sin_contexto"]]
        assert salida["next_state"]["etapa"] == "bienvenida"

    def test_sin_la_llave_usa_el_default(self):
        salida, _ = jugar(Bot(regreso_sin_modelo=True), [], mensaje="info", ya_se_presento=True)
        assert dichos(salida)[0].startswith("¡Hola de nuevo! 😊")

    @pytest.mark.parametrize("mensaje,runtime", [
        ("hola, ¿cuánto vale diciembre?", {"ya_se_presento": True}),
        ("¡Hola! Quiero más información", {"ya_se_presento": False}),
    ])
    def test_con_contenido_o_sin_la_senal_responde_el_modelo(self, mensaje, runtime):
        _, mock = jugar(Bot(**self.FLAGS), [resp(texto("¡Hola! 1️⃣ Sí 2️⃣ No"))],
                        mensaje=mensaje, **runtime)
        assert mock.call_count == 1

    def test_con_historial_responde_el_modelo(self):
        _, mock = jugar(Bot(**self.FLAGS), [resp(texto("¡Hola! 1️⃣ Sí 2️⃣ No"))], mensaje="hola",
                        estado=estado(("hola", "¡Hola!")), ya_se_presento=True)
        assert mock.call_count == 1

    def test_sin_flag(self):
        _, mock = jugar(Bot(), [resp(texto("¡Hola!"))], mensaje="hola", ya_se_presento=True)
        assert mock.call_count == 1


# ---------------------------------------------------------------------------
# M1 — narración y meta-texto
# ---------------------------------------------------------------------------

class TestM1Narracion:
    def test_bordes_de_una_ronda_que_consulta_y_de_la_siguiente(self):
        salida, _ = jugar(Bot(recortar_narracion=True), [
            resp(texto("Déjame consultar los precios de octubre primero."),
                 herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto("Ahora sí. Mira, en *octubre* tenemos salidas 🌴\n\n¿Cuál te sirve? 👇\n1️⃣ 16 al 19\n2️⃣ 23 al 26")),
        ], mensaje="octubre", estado=estado(("hola", "¡Hola!")))
        assert dichos(salida) == ["Mira, en *octubre* tenemos salidas 🌴\n\n¿Cuál te sirve? 👇\n1️⃣ 16 al 19\n2️⃣ 23 al 26"]

    def test_despues_de_una_correccion_toda_la_narracion(self):
        salida, _ = jugar(Bot(recortar_narracion=True, opciones_cerradas=True), [
            resp(texto("¿Para qué mes lo estás pensando?")),
            resp(texto("Tienes razón. Necesito consultar los valores de niños. Un momento\n\n"
                       "¿Para qué mes? 👇\n1️⃣ Octubre\n2️⃣ Noviembre")),
        ], mensaje="tengo un niño de 3", estado=estado(("hola", "¡Hola!")))
        assert dichos(salida) == ["¿Para qué mes? 👇\n1️⃣ Octubre\n2️⃣ Noviembre"]

    def test_sin_flag(self):
        salida, _ = jugar(Bot(), [
            resp(texto("Déjame consultar los precios de octubre primero."),
                 herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto("Ahora sí. Mira 🌴")),
        ], mensaje="octubre", estado=estado(("hola", "¡Hola!")))
        assert dichos(salida) == ["Déjame consultar los precios de octubre primero.", "Ahora sí. Mira 🌴"]


# ---------------------------------------------------------------------------
# M2 — al elegir salida u hotel, se consulta otra vez; y la etapa `fecha`
# ---------------------------------------------------------------------------

MENU_SALIDAS = "¿Cuál te sirve? 👇\n1️⃣ 16 al 19 de oct\n2️⃣ 23 al 26 de oct"


class TestM2ConsultaPorSalida:
    FLAGS = {"consulta_obligatoria_por_salida": True, "respuesta_por_numero": True}
    SIN_CONSULTA = resp(texto("En doble queda en $505.000 por persona 🌴 ¿Cuántos viajan? 1️⃣ 1 2️⃣ 2"))

    def test_eligio_una_salida_por_numero_y_no_consulto(self):
        salida, mock = jugar(Bot(**self.FLAGS), [
            self.SIN_CONSULTA,
            resp(herramienta("consultar_tarifario", {"mes": "octubre", "fecha": "2026-10-16"})),
            resp(texto("En doble queda en $505.000 por persona 🌴 ¿Cuántos viajan? 1️⃣ 1 2️⃣ 2")),
        ], mensaje="1", estado=estado(("octubre", MENU_SALIDAS)))
        assert "consultar esa salida" in json.dumps(mock.call_args_list[1].args[2], ensure_ascii=False)
        assert mock.call_count == 3

    def test_nombro_el_hotel(self):
        _, mock = jugar(Bot(**self.FLAGS), [self.SIN_CONSULTA, self.SIN_CONSULTA, self.SIN_CONSULTA],
                        mensaje="en Piedra Mar", estado=estado(("octubre", "¿Qué hotel?")))
        assert mock.call_count == 3          # 2 correcciones y la salida de M2

    def test_consulta_solo_con_mes_no_alcanza(self):
        salida, mock = jugar(Bot(**self.FLAGS), [
            resp(herramienta("consultar_tarifario", {"mes": "octubre"})),
            self.SIN_CONSULTA, self.SIN_CONSULTA, self.SIN_CONSULTA,
        ], mensaje="1", estado=estado(("octubre", MENU_SALIDAS)))
        assert mock.call_count == 4              # consulta + 2 correcciones + salida
        assert dichos(salida) == [llm_engine._TEXTO_PRECIO_A_ASESOR]
        assert "handoff" in tipos(salida)

    def test_sin_flag(self):
        _, mock = jugar(Bot(respuesta_por_numero=True), [self.SIN_CONSULTA], mensaje="1",
                        estado=estado(("octubre", MENU_SALIDAS)))
        assert mock.call_count == 1

    def test_m2b_hoteles_con_precio_para_una_salida_es_fecha(self):
        salida, _ = jugar(Bot(etapas_funnel=True), [resp(texto(
            "Para el *16 al 19 de oct*: Amor de Dios $459.000 · Piedra Mar $469.000 👇\n1️⃣ Amor de Dios 2️⃣ Piedra Mar"))],
            mensaje="la del 16", estado=estado(("octubre", MENU_SALIDAS), etapa="mes"))
        assert salida["next_state"]["etapa"] == "fecha"


# ---------------------------------------------------------------------------
# M3 — `system` en dos bloques
# ---------------------------------------------------------------------------

class _BedrockFalso:
    def __init__(self):
        self.cuerpos: List[Dict[str, Any]] = []

    def invoke_model(self, modelId, body):
        self.cuerpos.append(json.loads(body))
        respuesta = {"content": [{"type": "text", "text": "¡Bien! 1️⃣ Sí 2️⃣ No"}],
                     "stop_reason": "end_turn", "usage": {}}
        return {"body": io.BytesIO(json.dumps(respuesta).encode())}


class TestM3SystemEnDosBloques:
    MENU = "¿Cuál hotel? 👇\n1️⃣ Amor de Dios\n2️⃣ Piedra Mar"

    def _cuerpos(self, monkeypatch, bot):
        falso = _BedrockFalso()
        monkeypatch.setattr(llm_engine, "_bedrock_client", lambda: falso)
        for mensaje in ("1", "2"):
            llm_engine.advance(bot, estado(("octubre", self.MENU)), mensaje, runtime={})
        return falso.cuerpos

    def test_el_prefijo_cacheado_no_cambia_entre_turnos(self, monkeypatch):
        """Medido con modelo simulado: entre «1» y «2» sólo cambia la cola."""
        bot = Bot(system_en_dos_bloques=True, respuesta_por_numero=True)
        uno, dos = self._cuerpos(monkeypatch, bot)
        assert len(uno["system"]) == 2
        assert uno["system"][0]["cache_control"] == {"type": "ephemeral"}
        assert "cache_control" not in uno["system"][1]
        assert uno["system"][0] == dos["system"][0]
        assert uno["system"][1] != dos["system"][1]
        assert "Opción elegida" in uno["system"][1]["text"]
        assert len(uno["system"][0]["text"]) > 10 * len(uno["system"][1]["text"])

    def test_sin_flag_un_solo_bloque_y_cambia_el_prefijo(self, monkeypatch):
        bot = Bot(respuesta_por_numero=True)
        uno, dos = self._cuerpos(monkeypatch, bot)
        assert len(uno["system"]) == 1
        assert uno["system"][0]["text"] != dos["system"][0]["text"]

    def test_bot_1_el_cuerpo_de_siempre(self, monkeypatch):
        uno, _ = self._cuerpos(monkeypatch, Bot())
        assert uno["system"] == [{"type": "text", "text": uno["system"][0]["text"],
                                  "cache_control": {"type": "ephemeral"}}]
        assert llm_engine._COLA_SIN_CACHE not in uno["system"][0]["text"]


# ---------------------------------------------------------------------------
# M4 — opciones en su propia burbuja
# ---------------------------------------------------------------------------

class TestM4UnirOpciones:
    PARTIDO = [resp(texto("¡Hola de nuevo! 😊 ¿En qué te ayudo con tu viaje? 👇"),
                    texto("1️⃣ Hora y punto de salida 🚌\n2️⃣ Qué llevar 🎒\n3️⃣ Otra cosa"))]

    def test_se_unen(self):
        salida, _ = jugar(Bot(unir_opciones=True), self.PARTIDO, mensaje="ya tengo reserva")
        assert dichos(salida) == [
            "¡Hola de nuevo! 😊 ¿En qué te ayudo con tu viaje? 👇\n"
            "1️⃣ Hora y punto de salida 🚌\n2️⃣ Qué llevar 🎒\n3️⃣ Otra cosa"]
        assert salida["next_state"]["history"][-1]["content"] == dichos(salida)[0]

    def test_sin_flag(self):
        salida, _ = jugar(Bot(), self.PARTIDO, mensaje="ya tengo reserva")
        assert len(dichos(salida)) == 2


# ---------------------------------------------------------------------------
# M5 — resumen del traspaso del comprobante
# ---------------------------------------------------------------------------

class TestM5ResumenComprobante:
    FLAGS = {"comprobante_a_asesor": {"motivo": "comprobante de pago"}, "intencion_compra": {"h": 6},
             "etapas_funnel": True}

    def test_reusa_el_resumen_de_los_datos(self):
        datos, _ = jugar(Bot(**self.FLAGS), [
            resp(herramienta("registrar_intencion", {"tipo": "datos",
                 "resumen": "2 personas, 18 al 21 dic, Amor de Dios, cc 1234567890"}),
                 herramienta("enviar_media", {"claves": ["medios_pago"]}, id_="t2")),
            resp(texto("El anticipo es el 30 % 👇 1️⃣ Transferencia 2️⃣ Tarjeta")),
        ], mensaje="Ana, cc ..., 2 personas", estado=estado(("quiero reservar", "Tus datos"), etapa="reserva"))
        assert datos["next_state"]["etapa"] == "pago"
        assert "[número]" in datos["next_state"]["resumen_reserva"]
        salida, mock = jugar(Bot(**self.FLAGS), [], mensaje="[imagen]", estado=datos["next_state"])
        assert mock.call_count == 0
        resumen = salida["actions"][-1]["payload"]["resumen"]
        # D2: delimitado, rotulado como no verificado y la instrucción al final.
        assert "Datos que dio el cliente (sin verificar): «2 personas, 18 al 21 dic, Amor de Dios" in resumen
        assert resumen.endswith("Verifica el pago en el banco antes de confirmar la reserva.")
        assert "1234567890" not in resumen

    def test_sin_datos_usa_la_ultima_consulta(self):
        previo = estado(("x", "y"), etapa="pago",
                        ultima_consulta={"mes": "diciembre", "hotel": "Piedra Mar", "fecha": "2026-12-18"})
        salida, _ = jugar(Bot(**self.FLAGS), [], mensaje="[imagen]", estado=previo)
        assert "Lo último que consultó: diciembre, Piedra Mar, 2026-12-18." in \
            salida["actions"][-1]["payload"]["resumen"]

    def test_la_consulta_se_guarda_validada(self):
        salida, _ = jugar(Bot(**self.FLAGS), [
            resp(herramienta("consultar_tarifario",
                             {"mes": "diciembre", "hotel": "la casa de Ana", "fecha": "mañana"})),
            resp(texto("Te cuento 1️⃣ Sí 2️⃣ No")),
        ], mensaje="diciembre", estado=estado(("hola", "¡Hola!")))
        assert salida["next_state"]["ultima_consulta"] == {"mes": "diciembre", "hotel": "", "fecha": ""}

    def test_sin_flag_no_se_guarda(self):
        salida, _ = jugar(Bot(intencion_compra={"h": 6}), [
            resp(herramienta("registrar_intencion", {"tipo": "datos", "resumen": "2 personas"})),
            resp(texto("Listo"))], mensaje="mis datos", estado=estado(("hola", "¡Hola!")))
        assert "resumen_reserva" not in salida["next_state"]


# ---------------------------------------------------------------------------
# B2 — «a.m..»
# ---------------------------------------------------------------------------

class TestB2DoblePunto:
    @pytest.mark.parametrize("cuando,esperado", [
        ("el lunes a partir de las 8:00 a.m.", "Te escriben el lunes a partir de las 8:00 a.m."),
        ("mañana a partir de las 1:00 p.m.", "Te escriben mañana a partir de las 1:00 p.m."),
        ("hoy a partir de las 12:00 m.", "Te escriben hoy a partir de las 12:00 m."),
        ("en un momento", "Te escriben en un momento."),
    ])
    def test_sin_doble_punto(self, cuando, esperado):
        assert llm_engine._poner_cuando("Te escriben {cuando}.", cuando) == esperado


class TestA2CasosDeLaCorrida:
    """Los otros disparos de duración de QA (C03 r04, C07 r02): eran correctos."""
    CFG = {"tarifario": "covenas", "duracion_con_sesion": True}
    DIC = (
        "Amor de Dios — Diciembre (3 salidas):\n"
        "  · DICIEMBRE 18 AL 21 — múltiple $459.000 · doble $505.000 (2 noches / 3 días, Plan estándar)\n"
        "  · DICIEMBRE 18 AL 22 (Obsequio a Barú) — múltiple $550.000 · doble $605.000 (3 noches / 4 días, Obsequio a Barú)\n"
        "  · DICIEMBRE 29 AL 02 DE ENERO (Fin de Año) — múltiple $799.000 · doble $879.000 (3 noches / 4 días, Fin de semana festivo)\n"
    )

    def test_c03_el_mes_entre_los_dias(self):
        texto = "1️⃣ *18 al 21 dic* (2 noches): desde *$459.000*\n2️⃣ *29 dic al 02 ene* - Fin de Año (3 noches): desde *$799.000*"
        assert not llm_engine._viola_duracion_por_plan(self.CFG, [texto], [self.DIC])

    def test_c07_la_salida_en_otra_burbuja(self):
        textos = ["¡Perfecto! 🌴 Para 2 personas del *18 al 21 en Amor de Dios*:",
                  "1️⃣ *Múltiple*: $459.000 c/u\n_(2 noches / 3 días, por persona)_"]
        assert not llm_engine._viola_duracion_por_plan(self.CFG, textos, [self.DIC])

    def test_sigue_atrapando_el_error(self):
        assert llm_engine._viola_duracion_por_plan(
            self.CFG, ["1️⃣ *29 dic al 02 ene* (2 noches)"], [self.DIC])
        assert llm_engine._viola_duracion_por_plan(
            self.CFG, ["Para el *18 al 21*:", "_(3 noches / 4 días)_"], [self.DIC])
