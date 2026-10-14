"""Re-verificación contra Bedrock del bot 3 (2026-10-14): C05b r02 y C10.

Transcripciones en `entregables/transcripciones_c/2026-10-14/reverificacion/`.
Con y sin flag; modelo falso. Sin datos reales.
"""
from __future__ import annotations

import json

from app.data.bot_viajes import MEDIA
from app.services import llm_engine
from tests.viajes.variante_c.test_motor_embudo import (  # noqa: F401 (fixture)
    AUSENCIA, CUANDO_FUERA, FUERA, HORARIO, Bot, dichos, dobles, estado, herramienta,
    jugar, resp, texto, tipos,
)

DIC = (
    "Amor de Dios — Diciembre (2 salidas):\n"
    "  · DICIEMBRE 04 AL 07 — múltiple $459.000 · doble $505.000 (2 noches / 3 días, Plan estándar)\n"
    "  · DICIEMBRE 04 AL 08 — múltiple $559.000 · doble $615.000 (3 noches / 4 días, Fin de semana festivo)\n"
)


class Test1aRangoConA:
    CFG = {"tarifario": "covenas", "duracion_con_sesion": True}

    def test_n_a_m_de_mes_es_una_salida(self):
        assert not llm_engine._viola_duracion_por_plan(
            self.CFG, ["1️⃣ *4 a 7 de diciembre* (2 noches/3 días): desde *$459.000*"], [DIC])

    def test_sigue_atrapando_la_duracion_equivocada(self):
        assert llm_engine._viola_duracion_por_plan(
            self.CFG, ["1️⃣ *4 a 7 de diciembre* (3 noches/4 días)"], [DIC])

    def test_a_sin_mes_no_es_salida(self):
        assert not llm_engine._viola_duracion_por_plan(
            self.CFG, ["El saldo se paga de 8 a 10 días hábiles antes del viaje"], [DIC])


PROMESA = resp(texto("Eso lo confirmo con un compañero para darte el dato exacto 🙌"))


def _cuatro_rondas_de_herramienta():
    return [resp(herramienta("enviar_media", {"claves": ["tours"]}, id_=f"t{i}"))
            for i in range(4)]


class Test1bTurnoNuncaVacio:
    def test_la_correccion_en_la_ultima_ronda_cae_a_la_salida_segura(self):
        salida, mock = jugar(Bot(escalar_si_promete=True, turno_nunca_vacio=True),
                             _cuatro_rondas_de_herramienta() + [PROMESA],
                             mensaje="¿el bus tiene baño?", estado=estado(("hola", "¡Hola!")))
        assert mock.call_count == llm_engine._MAX_TOOL_ROUNDS
        assert tipos(salida)[-2:] == ["say", "handoff"]
        assert dichos(salida)[-1] == llm_engine._TEXTO_TURNO_INCOMPLETO
        assert salida["actions"][-1]["payload"]["motivo"] == "el bot no completó la respuesta"
        assert salida["finished"] is True

    def test_sin_flag_el_turno_queda_a_medias_como_hoy(self):
        salida, _ = jugar(Bot(escalar_si_promete=True),
                          _cuatro_rondas_de_herramienta() + [PROMESA],
                          mensaje="¿el bus tiene baño?", estado=estado(("hola", "¡Hola!")))
        assert "handoff" not in tipos(salida) and dichos(salida) == []

    def test_sin_correccion_pendiente_no_hace_nada(self):
        salida, _ = jugar(Bot(turno_nunca_vacio=True),
                          [resp(texto("¿Para qué mes? 1️⃣ Octubre 2️⃣ Noviembre"))])
        assert tipos(salida) == ["say"]


class Test1cMediaSinRepetir:
    DOS_VECES = [
        resp(herramienta("enviar_media", {"claves": ["tarifario_amordios_dic_ene",
                                                     "tarifario_piedramar_nov_ene"]})),
        resp(herramienta("enviar_media", {"claves": ["tarifario_amordios_dic_ene",
                                                     "tarifario_piedramar_nov_ene"]}, id_="t2")),
        resp(texto("¿Cuál te sirve? 1️⃣ 4 al 7 2️⃣ 11 al 14")),
    ]

    def _urls(self, salida):
        return [a["payload"]["url"] for a in salida["actions"] if a["type"] == "say_media"]

    def test_no_se_repite(self):
        salida, _ = jugar(Bot(media_sin_repetir=True), self.DOS_VECES, mensaje="diciembre",
                          estado=estado(("hola", "¡Hola!")))
        assert self._urls(salida) == [MEDIA["tarifario_amordios_dic_ene"]["url"],
                                      MEDIA["tarifario_piedramar_nov_ene"]["url"]]

    def test_sin_flag_salen_duplicados_como_hoy(self):
        salida, _ = jugar(Bot(), self.DOS_VECES, mensaje="diciembre",
                          estado=estado(("hola", "¡Hola!")))
        assert len(self._urls(salida)) == 4


class Test2CuandoUnaSolaVez:
    FLAGS = {"horario_asesores": HORARIO, "mensaje_ausencia": AUSENCIA}

    def _traspaso(self, monkeypatch, texto_modelo):
        monkeypatch.setattr(llm_engine, "_ahora_utc", lambda: FUERA)
        return jugar(Bot(**self.FLAGS), [resp(
            texto(texto_modelo), herramienta("escalar_a_asesor", {"motivo": "pide llamada"}))],
            mensaje="¿me pueden llamar?", estado=estado(("hola", "¡Hola!")))[0]

    def test_en_un_momento_del_modelo_se_va(self, monkeypatch):
        salida = self._traspaso(monkeypatch, "¡Claro! Te paso con un compañero del equipo "
                                             "para que te ayude con eso 🙌 Te escribe por aquí en un momento.")
        ausencia = llm_engine._poner_cuando(AUSENCIA, CUANDO_FUERA)
        assert dichos(salida) == [
            "¡Claro! Te paso con un compañero del equipo para que te ayude con eso 🙌", ausencia]
        assert "en un momento" not in json.dumps(salida["actions"], ensure_ascii=False)

    def test_el_cuando_del_modelo_tampoco_se_repite(self, monkeypatch):
        salida = self._traspaso(monkeypatch, "¡Claro! Te paso con un compañero 🙌 Te escribe "
                                             f"por aquí {CUANDO_FUERA}.")
        assert sum(d.count(CUANDO_FUERA) for d in dichos(salida)) == 1

    def test_en_horario_no_se_toca(self, monkeypatch):
        salida, _ = jugar(Bot(**self.FLAGS), [resp(
            texto("Te paso con un compañero 🙌 Te escribe por aquí en un momento."),
            herramienta("escalar_a_asesor", {"motivo": "x"}))], estado=estado(("hola", "¡Hola!")))
        assert dichos(salida) == ["Te paso con un compañero 🙌 Te escribe por aquí en un momento."]
