"""La config del bot 3 (`app/data/bot_viajes_c.py`).

1. Es la del bot 1 + las banderas reutilizadas del bot 2 (copiadas de allá,
   no reescritas) + las nuevas del embudo, con los nombres exactos de la spec.
2. NO lleva `apertura_vitrina`, `una_pregunta_por_turno` ni
   `recordatorios_con_contexto`.
3. El reenganche tiene los mismos minutos y etiqueta del bot 1.
4. Los recordatorios por etapa: 3 por etapa, cortos, sin montos, con opciones
   que el motor reconoce (salvo los que piden datos o el comprobante).
5. El aviso de ausencia dice las mismas horas que el horario configurado.
6. Construirla no toca las configs de los bots 1 y 2.
"""
from __future__ import annotations

import copy
import re

from app.data import bot_viajes, bot_viajes_b
from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import FLAGS_VARIANTE as FLAGS_B, LLM_CONFIG_B
from app.data.bot_viajes_c import (
    FLAGS_VARIANTE_C,
    LLM_CONFIG_C,
    NO_VAN_EN_C,
    RECORDATORIOS_POR_ETAPA,
    REUTILIZADAS_DE_B,
)
from app.services import llm_engine, recortes_turno

REUTILIZADAS_SPEC = {
    "guardarrail_precio", "cargos_ninos", "anticipo_en_sistema",
    "correcciones_silenciosas", "marcas_a_medios", "consulta_obligatoria_por_mes",
    "duracion_por_plan", "filtrar_nombres_genericos", "nombre_una_vez",
    "presentacion_una_vez", "promo_inexistente", "intencion_compra",
    "no_cerrar_aplazadas",
}
NUEVAS_SPEC = {
    "variante", "menu_meses", "respuesta_por_numero", "opciones_cerradas",
    "etapas_funnel", "horario_asesores", "mensaje_ausencia",
    "comprobante_a_asesor", "recordatorios_por_etapa", "cliente_con_reserva",
    "aviso_en_traspaso", "contexto_de_regreso_y_hora", "bienvenida_regreso",
    # Arreglos de motor tras QA contra Bedrock (2026-10-10).
    "duracion_con_sesion", "escalar_si_promete", "regreso_sin_modelo",
    "recortar_narracion", "consulta_obligatoria_por_salida",
    "system_en_dos_bloques", "unir_opciones", "menu_edades_ninos",
    "turno_nunca_vacio", "media_sin_repetir",
}
ETAPAS_CON_TEXTO = ("bienvenida", "mes", "fecha", "cotizacion", "reserva", "pago", "cliente")


class TestBanderas:
    def test_identidad(self):
        assert LLM_CONFIG_C["context_key"] == "demo_viajes_c"
        assert LLM_CONFIG_C["variante"] == "C"

    def test_reutiliza_las_del_bot_2_con_su_valor(self):
        assert set(REUTILIZADAS_DE_B) == REUTILIZADAS_SPEC
        for clave in REUTILIZADAS_SPEC:
            assert LLM_CONFIG_C[clave] == FLAGS_B[clave], clave

    def test_flags_variante_c_son_exactamente_las_de_la_spec(self):
        assert set(FLAGS_VARIANTE_C) == REUTILIZADAS_SPEC | NUEVAS_SPEC

    def test_las_nuevas_encendidas(self):
        for clave in ("menu_meses", "respuesta_por_numero", "opciones_cerradas",
                      "etapas_funnel", "cliente_con_reserva"):
            assert LLM_CONFIG_C[clave] is True, clave

    def test_no_lleva_las_que_romperian_el_embudo(self):
        assert set(NO_VAN_EN_C) == {"apertura_vitrina", "una_pregunta_por_turno",
                                    "recordatorios_con_contexto"}
        for clave in NO_VAN_EN_C:
            assert not LLM_CONFIG_C.get(clave), clave

    def test_aviso_en_traspaso_propio(self):
        aviso = LLM_CONFIG_C["aviso_en_traspaso"]
        assert aviso and aviso != FLAGS_B["aviso_en_traspaso"]
        assert "datos" not in aviso  # en el bot 3 los datos no traspasan

    def test_comprobante(self):
        conf = LLM_CONFIG_C["comprobante_a_asesor"]
        assert conf["motivo"] == "comprobante de pago"
        assert "{cuando}" in conf["texto"]

    def test_hereda_lo_demas_del_bot_1(self):
        for clave, valor in LLM_CONFIG.items():
            if clave not in FLAGS_VARIANTE_C and clave not in ("context_key", "seguimiento"):
                assert LLM_CONFIG_C[clave] == valor, clave
        assert LLM_CONFIG_C["media"] == LLM_CONFIG["media"]
        assert LLM_CONFIG_C["nombre_al_reservar"] is True


class TestHorario:
    def test_horario_del_ceo(self):
        h = LLM_CONFIG_C["horario_asesores"]
        assert h["tz"] == "America/Bogota"
        for dia in ("lun", "mar", "mie", "jue", "vie"):
            assert h["dias"][dia] == ["08:00", "18:00"]
        assert h["dias"]["sab"] == ["08:00", "13:00"]
        assert "dom" not in h["dias"]

    def test_el_aviso_de_ausencia_dice_las_mismas_horas(self):
        texto = LLM_CONFIG_C["mensaje_ausencia"]
        assert "{cuando}" in texto
        assert "lunes a viernes de 8:00 a.m. a 6:00 p.m." in texto
        assert "sábados de 8:00 a.m. a 1:00 p.m." in texto

    def test_el_servicio_de_horario_lo_acepta(self):
        from datetime import datetime, timezone

        from app.services import horario

        h = LLM_CONFIG_C["horario_asesores"]
        # Miércoles 10:00 a.m. y domingo 10:00 a.m. en Bogotá.
        assert horario.en_horario(datetime(2026, 10, 7, 15, 0, tzinfo=timezone.utc), h)
        assert not horario.en_horario(datetime(2026, 10, 11, 15, 0, tzinfo=timezone.utc), h)


class TestSeguimiento:
    def test_mismos_minutos_y_etiqueta_que_el_bot_1(self):
        assert LLM_CONFIG_C["seguimiento"] == LLM_CONFIG["seguimiento"]


class TestRecordatoriosPorEtapa:
    def test_tres_por_etapa(self):
        assert set(RECORDATORIOS_POR_ETAPA) == set(ETAPAS_CON_TEXTO)
        for etapa, textos in RECORDATORIOS_POR_ETAPA.items():
            assert len(textos) == 3, etapa
            assert all(isinstance(t, str) and t.strip() for t in textos), etapa

    def test_las_etapas_existen_en_el_motor(self):
        validas = set(llm_engine.ETAPAS_FUNNEL) | {llm_engine.ETAPA_CLIENTE}
        assert set(RECORDATORIOS_POR_ETAPA) <= validas

    def test_sin_montos_ni_porcentajes(self):
        for textos in RECORDATORIOS_POR_ETAPA.values():
            for t in textos:
                assert not re.search(r"\$|\d+\s*%|\d{3}\.\d{3}", t), t

    def test_cortos(self):
        for textos in RECORDATORIOS_POR_ETAPA.values():
            for t in textos:
                assert len(t.splitlines()) <= 6 and len(t) <= 260, t

    def test_cierran_con_opciones_salvo_datos_comprobante_o_despedida(self):
        for etapa, textos in RECORDATORIOS_POR_ETAPA.items():
            for i, t in enumerate(textos):
                if recortes_turno.cierra_con_opciones(t):
                    continue
                excepcion = llm_engine._SIN_OPCIONES_RE.search(t) or (
                    etapa == "cliente" and i == 2
                )
                assert excepcion, (etapa, i, t)

    def test_el_de_pago_es_el_seguimiento_del_pago(self):
        primero = RECORDATORIOS_POR_ETAPA["pago"][0]
        assert "¿Pudiste hacer el pago?" in primero
        assert recortes_turno.opciones_numeradas(primero) == {
            1: "Ya pagué ✅", 2: "Tuve un problema 😕", 3: "Lo hago más tarde",
        } or len(recortes_turno.opciones_numeradas(primero)) == 3

    def test_no_afirman_cupo(self):
        for textos in RECORDATORIOS_POR_ETAPA.values():
            for t in textos:
                assert not re.search(r"(?i)\b(?:hay|quedan?|con)\s+cupos?\b|disponibilidad", t), t


class TestNoMutaLosOtrosBots:
    def test_no_toca_bot_1_ni_bot_2(self):
        antes_1 = copy.deepcopy(bot_viajes.LLM_CONFIG)
        antes_2 = copy.deepcopy(bot_viajes_b.LLM_CONFIG_B)
        import importlib

        from app.data import bot_viajes_c
        importlib.reload(bot_viajes_c)
        assert bot_viajes.LLM_CONFIG == antes_1
        assert bot_viajes_b.LLM_CONFIG_B == antes_2
        assert LLM_CONFIG_B["variante"] == "B"

    def test_son_objetos_distintos(self):
        assert LLM_CONFIG_C["media"] is not LLM_CONFIG["media"]
        assert LLM_CONFIG_C["promo_inexistente"] is not FLAGS_B["promo_inexistente"]


class TestBienvenidaRegreso:
    def test_dos_textos_con_opciones(self):
        from app.data.bot_viajes_c import BIENVENIDA_REGRESO

        reg = LLM_CONFIG_C["bienvenida_regreso"]
        assert reg == BIENVENIDA_REGRESO
        assert set(reg) == {"con_contexto", "sin_contexto"}
        assert "{mes_hotel}" in reg["con_contexto"]
        assert "{" not in reg["sin_contexto"]
        lleno = reg["con_contexto"].format(mes_hotel="*diciembre* en *Amor de Dios*")
        for texto in (lleno, reg["sin_contexto"]):
            assert texto.startswith("¡Hola de nuevo!")
            assert recortes_turno.cierra_con_opciones(texto)
            assert len(recortes_turno.opciones_numeradas(texto)) == 3

    def test_el_contexto_de_regreso_y_hora_solo_en_c(self):
        assert LLM_CONFIG_C["contexto_de_regreso_y_hora"] is True
        assert "contexto_de_regreso_y_hora" not in LLM_CONFIG
        assert "contexto_de_regreso_y_hora" not in LLM_CONFIG_B
