"""Defectos del motor del bot 2 que encontró QA contra Bedrock real (2026-10-07).

Transcripciones en `entregables/transcripciones_b/2026-10-07/`. Cada clase es un
punto del reporte de QA, reproducido con el modelo falso y con el mismo patrón
de bloques que mandó el modelo de verdad. Todo va detrás de flags del bot 2:
cada punto se prueba también sin su flag.
"""
from __future__ import annotations

import json

import pytest

from app.data.bot_viajes import LLM_CONFIG, MEDIA
from app.services import llm_engine
from tests.viajes.variante_b.test_motor_flags import (  # noqa: F401  (fixtures)
    FLYER, FLYER_DIC, PROMO, Bot, con_historia, dichos, guardarrail, herramienta,
    herramientas, jugar, precios_dobles, resp, texto, tipos,
)


def _con_texto(salida):
    return [a for a in salida["actions"] if a["type"] == "say"]


# ---------------------------------------------------------------------------
# QA #1 (CRÍTICO) — traspaso mudo: `aviso_en_traspaso`
# ---------------------------------------------------------------------------

AVISO = "¡Listo, Laura! 🙌 Ya le paso tus datos a una compañera para confirmar tu cupo 💬"
RESERVA = [resp(
    herramienta("registrar_nombre", {"nombre": "Laura"}),
    herramienta("registrar_intencion", {"tipo": "datos", "resumen": "2 personas, 18 dic"}),
    herramienta("escalar_a_asesor", {"motivo": "Reserva con datos", "resumen": "2 personas"}),
)]


class TestAvisoEnTraspaso:
    def test_el_traspaso_sin_texto_lleva_el_aviso_antes_del_handoff(self):
        salida, _ = jugar(Bot(aviso_en_traspaso=AVISO, intencion_compra={"h": 6}),
                          RESERVA, mensaje="Laura, 2 personas, salida del 18",
                          estado=con_historia(("quiero reservar", "¿A nombre de quién?")))
        assert tipos(salida) == ["perfil", "say", "handoff"]
        assert dichos(salida) == [AVISO]
        assert AVISO in salida["next_state"]["history"][-1]["content"]

    def test_con_true_usa_el_aviso_por_defecto(self):
        salida, _ = jugar(Bot(aviso_en_traspaso=True), RESERVA, mensaje="mis datos",
                          estado=con_historia(("hola", "¡Hola!")))
        assert dichos(salida) == [llm_engine._AVISO_TRASPASO_DEFAULT]

    def test_si_el_modelo_escribio_algo_no_se_agrega(self):
        salida, _ = jugar(Bot(aviso_en_traspaso=AVISO), [resp(
            texto("¡Gracias! Te paso con una compañera 🙌"),
            herramienta("escalar_a_asesor", {"motivo": "x"}),
        )], mensaje="mis datos", estado=con_historia(("hola", "¡Hola!")))
        assert dichos(salida) == ["¡Gracias! Te paso con una compañera 🙌"]

    def test_sin_flag_el_traspaso_sale_mudo_como_hoy(self):
        """Lo mismo le pasa hoy al bot 1: el motor no garantiza texto en el
        traspaso (la herramienta sólo se lo pide al modelo en la descripción)."""
        salida, _ = jugar(Bot(), RESERVA, mensaje="mis datos",
                          estado=con_historia(("hola", "¡Hola!")))
        assert "say" not in tipos(salida)
        assert "handoff" in tipos(salida)


# ---------------------------------------------------------------------------
# QA #2 (ALTO) — disculpas al sistema: `correcciones_silenciosas`
# ---------------------------------------------------------------------------

class TestCorreccionesSilenciosas:
    MALO = resp(texto("En doble te queda en $549.000 por persona 🌴"))
    DISCULPA = resp(texto("Tienes razón, disculpa. Vuelvo a responder bien:\n\n"
                          "En doble te queda en $505.000 por persona 🌴"))

    def test_la_disculpa_no_llega_y_la_correccion_lo_pide(self, guardarrail):
        salida, mock = jugar(Bot(guardarrail_precio=True, correcciones_silenciosas=True),
                             [self.MALO, self.DISCULPA], mensaje="16 al 19 en doble")
        assert dichos(salida) == ["En doble te queda en $505.000 por persona 🌴"]
        correccion = mock.call_args_list[1].args[2][-1]["content"]
        assert correccion.endswith(llm_engine._SIN_DISCULPAS)

    @pytest.mark.parametrize("disculpa", [
        "Tienes toda la razón. Disculpa, no había consultado.",
        "Tienes razón, me disculpo. Vuelvo a intentar:",
        "Perdón.",
    ])
    def test_varias_formas(self, guardarrail, disculpa):
        salida, _ = jugar(Bot(guardarrail_precio=True, correcciones_silenciosas=True), [
            self.MALO, resp(texto(f"{disculpa}\n\nSon $505.000 en doble"))],
            mensaje="en doble")
        assert dichos(salida) == ["Son $505.000 en doble"]

    def test_sin_correccion_previa_no_se_toca(self):
        salida, _ = jugar(Bot(correcciones_silenciosas=True),
                          [resp(texto("Disculpa la demora 🙏 ¿Para qué mes?"))])
        assert dichos(salida) == ["Disculpa la demora 🙏 ¿Para qué mes?"]

    def test_sin_flag_la_correccion_y_la_disculpa_quedan_como_hoy(self, guardarrail):
        salida, mock = jugar(Bot(guardarrail_precio=True), [self.MALO, self.DISCULPA],
                             mensaje="16 al 19 en doble")
        assert dichos(salida)[0].startswith("Tienes razón, disculpa.")
        correccion = mock.call_args_list[1].args[2][-1]["content"]
        assert llm_engine._SIN_DISCULPAS not in correccion


# ---------------------------------------------------------------------------
# QA #3 (ALTO) — anticipo como dato del system: `anticipo_en_sistema`
# ---------------------------------------------------------------------------

class TestAnticipoEnSistema:
    def _system(self, bot, history):
        cfg = {**llm_engine.config_de(bot), "_runtime": {}}
        return llm_engine._system_prompt(bot, cfg, history)

    def test_esta_en_todos_los_turnos_y_en_la_parte_estable(self, monkeypatch):
        from app.services import tarifario
        monkeypatch.setattr(tarifario, "extras", lambda: {
            "anticipo_pct": 30, "saldo_texto": "el saldo se paga de 8 a 10 días hábiles antes"})
        bot = Bot(anticipo_en_sistema=True)
        for historia in ([], con_historia(("hola", "¡Hola!"))["history"]):
            system = self._system(bot, historia)
            assert "## Anticipo y saldo (datos del sistema)" in system
            assert "**30 %**" in system
            assert "El saldo se paga de 8 a 10 días hábiles antes." in system
            assert system.index("## Anticipo y saldo") < system.index("## Qué día es hoy")

    def test_sin_dato_no_hay_bloque(self, monkeypatch):
        from app.services import tarifario
        monkeypatch.setattr(tarifario, "extras", lambda: {})
        assert "Anticipo y saldo" not in self._system(Bot(anticipo_en_sistema=True), [])

    def test_sin_flag_no_hay_bloque(self):
        assert "Anticipo y saldo" not in self._system(Bot(), [])


# ---------------------------------------------------------------------------
# QA #4 (ALTO) — `[enviaste: …]` filtrado al cliente: `marcas_a_medios`
# ---------------------------------------------------------------------------

class TestMarcasAMedios:
    CASO = ("Apartas tu cupo con un anticipo 🙌 Te dejo los medios de pago 💳\n"
            "[enviaste: medios_pago]\n\n¿Te aparto el cupo?")

    def test_la_marca_se_vuelve_el_adjunto_real(self):
        salida, _ = jugar(Bot(marcas_a_medios=True), [resp(texto(self.CASO))],
                          mensaje="¿con cuánto se separa?", estado=con_historia(("hola", "¡Hola!")))
        assert tipos(salida) == ["say", "say_media", "say"]
        assert salida["actions"][1]["payload"]["url"] == MEDIA["medios_pago"]["url"]
        assert "[enviaste" not in json.dumps(salida["actions"], ensure_ascii=False)
        assert dichos(salida)[-1] == "¿Te aparto el cupo?"

    def test_formulario_que_no_salia(self):
        salida, _ = jugar(Bot(marcas_a_medios=True), [resp(texto(
            "Te dejo el formulario 👇\n[enviaste: formulario_reserva]"))],
            mensaje="quiero reservar", estado=con_historia(("hola", "¡Hola!")))
        urls = [a["payload"]["url"] for a in salida["actions"] if a["type"] == "say_media"]
        assert urls == [MEDIA["formulario_reserva"]["url"]]

    def test_clave_inexistente_o_repetida_no_se_manda(self):
        salida, _ = jugar(Bot(marcas_a_medios=True), [
            resp(herramienta("enviar_media", {"claves": ["tours"]})),
            resp(texto("Mira 👆 [enviaste: tours] [enviaste: no_existe] [guardaste que se llama Ana]")),
        ], mensaje="tours", estado=con_historia(("hola", "¡Hola!")))
        assert [a["type"] for a in salida["actions"]] == ["say_media", "say"]
        assert dichos(salida) == ["Mira 👆"]

    def test_sin_flag_la_marca_sale_como_hoy(self):
        salida, _ = jugar(Bot(), [resp(texto(self.CASO))], mensaje="¿con cuánto?",
                          estado=con_historia(("hola", "¡Hola!")))
        assert dichos(salida) == [self.CASO]


# ---------------------------------------------------------------------------
# QA #5 (ALTO) — promo vs presupuesto, decidido antes del modelo
# ---------------------------------------------------------------------------

class TestPromoAntesDelModelo:
    def test_promo_del_flyer(self):
        salida, mock = jugar(Bot(promo_inexistente={"montos": [350000]}), [], mensaje=(
            "En el flyer dice que de lunes a jueves hay salidas desde $350.000, ¿para cuándo es eso?"))
        assert mock.call_count == 0
        handoff = salida["actions"][-1]["payload"]
        assert handoff["motivo"] == "cliente pregunta por la promo de lunes a jueves"
        assert dichos(salida) == [llm_engine._TEXTO_PROMO_DEFAULT]

    def test_presupuesto(self):
        salida, mock = jugar(Bot(promo_inexistente={"montos": [350000]}), [],
                             mensaje="tengo 350 mil por persona, ¿qué me alcanza?")
        assert mock.call_count == 0
        assert salida["actions"][-1]["payload"]["motivo"] == "cliente con presupuesto de $350.000"
        (dicho,) = dichos(salida)
        assert "promo" not in dicho.lower()
        assert salida["finished"] is True

    def test_textos_y_motivos_de_la_config(self):
        cfg = {"montos": [350000], "texto_presupuesto": "Ya te ayudo 🙌",
               "motivo_presupuesto": "presupuesto ajustado"}
        salida, _ = jugar(Bot(promo_inexistente=cfg), [], mensaje="cuento con 350k")
        assert dichos(salida) == ["Ya te ayudo 🙌"]
        assert salida["actions"][-1]["payload"]["motivo"] == "presupuesto ajustado"

    def test_sin_monto_el_modelo_responde(self):
        salida, mock = jugar(Bot(promo_inexistente=PROMO), [resp(texto("¡Hola! ¿Qué mes?"))])
        assert mock.call_count == 1 and "handoff" not in tipos(salida)


# ---------------------------------------------------------------------------
# QA #6 (MEDIO) — narración de una ronda que sólo consultaba
# ---------------------------------------------------------------------------

class TestNarracionDeConsulta:
    def _turno(self, bot, segunda):
        return jugar(bot, [
            resp(texto("¡Perfecto! 🙌 Te consulto los precios de diciembre..."),
                 herramienta("consultar_tarifario", {"mes": "diciembre"})),
            segunda,
        ], mensaje="diciembre", estado=con_historia(("hola", "¡Hola! ¿Qué mes?")))

    def test_la_narracion_sobra_si_llega_el_mensaje(self):
        salida, _ = self._turno(Bot(una_pregunta_por_turno=True),
                                resp(texto("En diciembre hay desde $369.000 🌴 ¿Cuántos viajan?")))
        assert dichos(salida) == ["En diciembre hay desde $369.000 🌴 ¿Cuántos viajan?"]
        assert "Te consulto" not in salida["next_state"]["history"][-1]["content"]

    def test_si_no_llega_otro_mensaje_la_narracion_se_queda(self):
        salida, _ = self._turno(Bot(una_pregunta_por_turno=True), resp())
        assert dichos(salida) == ["¡Perfecto! 🙌 Te consulto los precios de diciembre..."]

    def test_un_texto_que_acompana_un_envio_no_es_narracion(self):
        salida, _ = jugar(Bot(una_pregunta_por_turno=True), [
            resp(texto("Te dejo el tarifario 👇"), herramienta("enviar_media", {"claves": [FLYER]})),
            resp(texto("¿Cuál fecha te sirve?")),
        ], mensaje="octubre", estado=con_historia(("hola", "¡Hola!")))
        assert dichos(salida) == ["Te dejo el tarifario 👇", "¿Cuál fecha te sirve?"]

    def test_sin_flag_salen_las_dos(self):
        salida, _ = self._turno(Bot(), resp(texto("Desde $369.000 🌴 ¿Cuántos viajan?")))
        assert len(dichos(salida)) == 2


# ---------------------------------------------------------------------------
# QA #7 (MEDIO) — falso positivo de `_viola_duracion`: `duracion_por_plan`
# ---------------------------------------------------------------------------

RESULTADO = (
    "Amor de Dios — Octubre (2 salidas):\n"
    "  · OCTUBRE 16 AL 19 — múltiple $459.000 · doble $505.000 (2 noches / 3 días, Plan estándar)\n"
    "  · OCTUBRE 16 AL 20 (Obsequio a Barú) — múltiple $550.000 · doble $605.000 "
    "(3 noches / 4 días, Obsequio a Barú)\n"
)
RESULTADO_DIC = (
    "Amor de Dios — Diciembre (2 salidas):\n"
    "  · DICIEMBRE 08 AL 11 — múltiple $369.000 · doble $406.000 (2 noches / 3 días, Obsequio a Rincón del Mar)\n"
    "  · DICIEMBRE 11 AL 15 (Obsequio a Barú) — múltiple $550.000 · doble $605.000 "
    "(3 noches / 4 días, Obsequio a Barú)\n"
)
#: Texto real de la corrida (G07 r07), correcto y bloqueado por la versión del bot 1.
POR_PLAN = (
    "Perfecto, para el 16 al 19 en doble hay dos opciones 🌴:\n\n"
    "**Plan Estándar** (2 noches / 3 días):\n- *Amor de Dios*: $505.000 por persona\n\n"
    "O si quieres algo más completo, está el **Obsequio a Barú** (3 noches / 4 días):\n"
    "- *Amor de Dios*: $605.000 por persona"
)


class TestDuracionPorPlan:
    CFG = llm_engine.config_de(Bot(duracion_por_plan=True))

    def test_el_caso_real_pasa(self):
        assert not llm_engine._viola_duracion_por_plan(self.CFG, [POR_PLAN], [RESULTADO])

    def test_la_version_del_bot_1_lo_bloquea(self):
        """El caso queda reportado para decidir después sobre el bot 1."""
        assert llm_engine._viola_duracion(self.CFG, [POR_PLAN], [RESULTADO])

    def test_salida_con_guion(self):
        assert not llm_engine._viola_duracion_por_plan(
            self.CFG, ["- 8-11 dic: $369.000 x adulto (2 noches)"], [RESULTADO_DIC])

    def test_sigue_atrapando_la_duracion_equivocada(self):
        for malo in ("**Plan Estándar** (3 noches / 4 días)",
                     "La del *16 al 19* son 3 noches",
                     "El plan es de 3 noches"):
            assert llm_engine._viola_duracion_por_plan(self.CFG, [malo], [RESULTADO]), malo

    def test_en_el_turno_con_flag_no_hay_correccion(self):
        salida, mock = jugar(Bot(duracion_por_plan=True), [
            resp(herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto(POR_PLAN)),
        ], mensaje="16 al 19 en doble", estado=con_historia(("hola", "¡Hola!")))
        assert mock.call_count == 2


# ---------------------------------------------------------------------------
# QA #8 (BAJO) — apertura con mes: un solo flyer y sin narración
# ---------------------------------------------------------------------------

class TestAperturaConMes:
    def test_un_solo_flyer_el_del_mes_y_sin_narracion(self, monkeypatch):
        from app.services import tarifario
        monkeypatch.setattr(tarifario, "flyer_apertura",
                            lambda hoy, cfg=None: FLYER_DIC if hoy.month in (12, 1) else FLYER,
                            raising=False)
        salida, _ = jugar(Bot(apertura_vitrina=True, una_pregunta_por_turno=True), [
            resp(texto("¡Hola! 😊 Soy *Luisa*. Déjame consultar los precios de diciembre."),
                 herramienta("consultar_tarifario", {"mes": "diciembre"})),
            resp(texto("Mira el tarifario 📦"),
                 herramienta("enviar_media", {"claves": ["tarifario_amordios_dic_ene",
                                                         "tarifario_piedramar_nov_ene"]})),
            resp(texto("Desde $369.000 🌴 ¿Cuál hotel te llama más?")),
        ], mensaje="¿cuánto vale en diciembre?")
        urls = [a["payload"]["url"] for a in salida["actions"] if a["type"] == "say_media"]
        assert urls == [MEDIA[FLYER_DIC]["url"]]
        assert not any("Déjame consultar" in d for d in dichos(salida))
        historial = salida["next_state"]["history"][-1]["content"]
        assert "tarifario_piedramar_nov_ene" not in historial


# ---------------------------------------------------------------------------
# QA #9 (CRÍTICO) — nombró un mes y no consultó: `consulta_obligatoria_por_mes`
# ---------------------------------------------------------------------------

class TestConsultaObligatoriaPorMes:
    INVENTADO = resp(texto("En octubre tenemos el *16 al 19* desde $369.000 🌴"))

    def test_sin_consultar_se_corrige(self):
        salida, mock = jugar(Bot(consulta_obligatoria_por_mes=True), [
            self.INVENTADO,
            resp(herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto("En octubre la del *16 al 19* va desde $459.000 🌴")),
        ], mensaje="¿cuánto vale en octubre?", estado=con_historia(("hola", "¡Hola!")))
        assert dichos(salida) == ["En octubre la del *16 al 19* va desde $459.000 🌴"]
        enviados = json.dumps(mock.call_args_list[-1].args[2], ensure_ascii=False)
        assert "Consulta los precios de ese mes" in enviados

    def test_agotadas_las_correcciones_pasa_a_asesor(self):
        salida, mock = jugar(Bot(consulta_obligatoria_por_mes=True),
                             [self.INVENTADO] * 3, mensaje="¿y en octubre?",
                             estado=con_historia(("hola", "¡Hola!")))
        assert mock.call_count == 3
        assert tipos(salida) == ["say", "handoff"]
        assert dichos(salida) == [llm_engine._TEXTO_PRECIO_A_ASESOR]
        assert salida["finished"] is True

    def test_sin_mes_o_sin_cifras_no_aplica(self):
        for mensaje, respuesta in (("hola", "Desde $369.000 🌴 ¿Qué mes?"),
                                   ("octubre", "¡Qué buena época! ¿Cuántos viajan?")):
            salida, mock = jugar(Bot(consulta_obligatoria_por_mes=True),
                                 [resp(texto(respuesta))], mensaje=mensaje,
                                 estado=con_historia(("hola", "¡Hola!")))
            assert mock.call_count == 1, mensaje

    def test_sin_flag_no_aplica(self):
        salida, mock = jugar(Bot(), [self.INVENTADO], mensaje="¿cuánto vale en octubre?",
                             estado=con_historia(("hola", "¡Hola!")))
        assert mock.call_count == 1
