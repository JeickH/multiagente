"""La config del bot 2 (`app/data/bot_viajes_b.py`).

Lo que se fija:

1. Es la del bot 1 más las banderas de la variante, con los nombres exactos
   de la spec (el motor las lee por nombre: si se renombran aquí, se apagan
   sin avisar).
2. El reenganche es el mismo del bot 1 **por construcción** (minutos, cuántos,
   etiqueta de abandono): el A/B tiene que medir el guion, no otro reenganche.
3. Construirla no le escribe encima a la config del bot 1, que es un módulo
   importado una vez por proceso.
4. Las plantillas de recordatorio solo usan las variables del servicio, no
   afirman cupo y no dependen del nombre.
"""
from __future__ import annotations

import copy
import re
from string import Formatter

from app.data import bot_viajes, bot_viajes_b
from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import FLAGS_VARIANTE, LLM_CONFIG_B

#: Las banderas de la spec compartida, con su valor.
ESPERADAS = {
    "variante": "B",
    "apertura_vitrina": True,
    "una_pregunta_por_turno": True,
    "presentacion_una_vez": True,
    "nombre_una_vez": True,
    "filtrar_nombres_genericos": True,
    "no_cerrar_aplazadas": True,
    "guardarrail_precio": True,
    "cargos_ninos": True,
    "recordatorios_con_contexto": True,
    # Ajustes tras la QA contra Bedrock.
    "correcciones_silenciosas": True,
    "anticipo_en_sistema": True,
    "marcas_a_medios": True,
    "duracion_por_plan": True,
    "consulta_obligatoria_por_mes": True,
}

VARIABLES = {"nombre", "mes", "salidas", "n_salidas", "desde", "anticipo_pct"}


class TestBanderas:
    def test_context_key_propio(self):
        assert LLM_CONFIG_B["context_key"] == "demo_viajes_b"

    def test_todas_las_banderas_con_su_valor(self):
        for clave, valor in ESPERADAS.items():
            assert LLM_CONFIG_B[clave] == valor, clave

    def test_promo_inexistente(self):
        promo = LLM_CONFIG_B["promo_inexistente"]
        assert promo["montos"] == [350000]
        assert promo["texto"].startswith("Déjame confirmarlo con un compañero")
        assert promo["motivo"].strip()
        # La nota interna no repite la cifra: sale de `montos`.
        assert "350" not in promo["texto"] + promo["motivo"]

    def test_intencion_compra(self):
        assert LLM_CONFIG_B["intencion_compra"] == {"horas_para_interesado": 6}

    def test_flags_variante_es_lo_que_b_agrega(self):
        assert set(FLAGS_VARIANTE) == set(ESPERADAS) | {
            "promo_inexistente", "intencion_compra", "aviso_en_traspaso"
        }
        for clave in FLAGS_VARIANTE:
            assert clave not in LLM_CONFIG, f"{clave} no puede estar en el bot 1"

    def test_hereda_todo_lo_demas_del_bot_1(self):
        propias = set(FLAGS_VARIANTE) | {"context_key", "seguimiento"}
        for clave, valor in LLM_CONFIG.items():
            if clave not in propias:
                assert LLM_CONFIG_B[clave] == valor, clave
        # El nombre se sigue pidiendo al reservar (#2), como en el bot 1.
        assert LLM_CONFIG_B["nombre_al_reservar"] is True
        assert LLM_CONFIG_B["media"] == LLM_CONFIG["media"]


class TestSeguimiento:
    def test_mismos_minutos_y_etiqueta_que_el_bot_1(self):
        a, b = LLM_CONFIG["seguimiento"], LLM_CONFIG_B["seguimiento"]
        assert b["minutos"] == a["minutos"]
        assert b["etiqueta_abandono"] == a["etiqueta_abandono"]
        assert [r["minutos"] for r in b["recordatorios"]] == [
            r["minutos"] for r in a["recordatorios"]
        ]
        # El texto fijo se conserva: es el respaldo cuando la plantilla no se
        # puede llenar.
        assert [r["texto"] for r in b["recordatorios"]] == [
            r["texto"] for r in a["recordatorios"]
        ]

    def test_plantilla_solo_en_la_segunda_y_la_tercera(self):
        recs = LLM_CONFIG_B["seguimiento"]["recordatorios"]
        assert "plantilla" not in recs[0]
        assert recs[1]["plantilla"] and recs[2]["plantilla"]

    def test_las_plantillas_usan_solo_variables_del_servicio(self):
        for rec in LLM_CONFIG_B["seguimiento"]["recordatorios"][1:]:
            usadas = {c for _, c, _, _ in Formatter().parse(rec["plantilla"]) if c}
            assert usadas <= VARIABLES, usadas
            assert "nombre" not in usadas  # casi nadie lo tiene a esta altura
            assert {"mes", "salidas", "desde"} <= usadas

    def test_las_plantillas_no_hablan_de_cupo_ni_tienen_cifras(self):
        for rec in LLM_CONFIG_B["seguimiento"]["recordatorios"][1:]:
            assert not re.search(r"(?i)cupo|disponib", rec["plantilla"])
            assert not re.search(r"\d", rec["plantilla"])

    def test_las_plantillas_cierran_con_una_pregunta(self):
        for rec in LLM_CONFIG_B["seguimiento"]["recordatorios"][1:]:
            assert rec["plantilla"].rstrip().endswith("?")
            assert rec["plantilla"].count("¿") == 1

    def test_el_servicio_las_acepta(self):
        """El servicio descarta (None) una plantilla que afirme cupo."""
        from app.services import recordatorios_contexto as rc

        patron = getattr(rc, "_AFIRMA_CUPO_RE", None)
        if patron is None:  # el servicio todavía no lo expone
            return
        for rec in LLM_CONFIG_B["seguimiento"]["recordatorios"][1:]:
            assert not patron.search(rec["plantilla"])


class TestNoMutaElBot1:
    def test_construir_la_b_no_toca_la_config_del_bot_1(self):
        antes = copy.deepcopy(bot_viajes.LLM_CONFIG)
        # Se reconstruye como lo haría una segunda importación.
        bot_viajes_b._seguimiento_b()
        assert bot_viajes.LLM_CONFIG == antes
        for rec in bot_viajes.LLM_CONFIG["seguimiento"]["recordatorios"]:
            assert "plantilla" not in rec

    def test_son_objetos_distintos(self):
        assert LLM_CONFIG_B["seguimiento"] is not LLM_CONFIG["seguimiento"]
        assert LLM_CONFIG_B["media"] is not LLM_CONFIG["media"]
