"""La búsqueda manda las candidatas juntas, no de a una (#367).

Antes el bot mostraba una ficha con `ver_ficha`, esperaba un "no es esa" y
pasaba a la siguiente: cuatro turnos —y cuatro llamadas al modelo— para
descartar cuatro perros. Quien busca a su mascota la reconoce de un vistazo.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services import llm_engine


class _Foto:
    def __init__(self, id_):
        self.id = id_


class _Mascota:
    def __init__(self, codigo, fotos=1):
        self.codigo = codigo
        self.fotos = [_Foto(i + 1) for i in range(fotos)]


class _DB:
    """El motor abre y cierra su propia sesión en cada tool."""

    def close(self):
        pass


CFG = {"mascotas": {"ciudad": "Cali"}, "_runtime": {}}

CANDIDATAS = [
    {"codigo": "MC-00002", "especie": "perro", "color": "café", "zona": "San Fernando"},
    {"codigo": "MC-00006", "especie": "perro", "color": "negro", "zona": "Meléndez"},
    {"codigo": "MC-00009", "especie": "perro", "color": "blanco", "zona": "Granada"},
]


def _correr(candidatas, fotos_por_mascota=1):
    acciones = []
    encontradas = {c["codigo"]: _Mascota(c["codigo"], fotos_por_mascota)
                   for c in candidatas}
    with patch.object(llm_engine, "_mascotas_db", return_value=_DB()), \
         patch("app.services.mascotas.buscar", return_value=candidatas), \
         patch("app.services.mascotas.obtener",
               side_effect=lambda db, c: encontradas.get(c)):
        texto, _ = llm_engine._run_tool_mascotas(
            "buscar_mascota", {"especie": "perro"}, CFG, acciones, []
        )
    return json.loads(texto), acciones


class BusquedaAgrupadaTests(unittest.TestCase):
    def test_manda_una_foto_por_candidata_de_una_sola_vez(self):
        datos, acciones = _correr(CANDIDATAS)
        medios = [a for a in acciones if a["type"] == "say_media"]
        self.assertEqual(len(medios), 3)
        self.assertEqual(datos["fotos_enviadas"], 3)

    def test_cada_foto_lleva_su_codigo_en_el_pie(self):
        """Sin el código, tres fotos seguidas son indistinguibles y la persona
        no puede decir cuál de todas es la suya."""
        _, acciones = _correr(CANDIDATAS)
        pies = [a["payload"]["caption"] for a in acciones if a["type"] == "say_media"]
        self.assertEqual(pies, ["MC-00002", "MC-00006", "MC-00009"])

    def test_le_prohibe_volver_a_mostrarlas_de_a_una(self):
        datos, _ = _correr(CANDIDATAS)
        self.assertIn("NO uses `ver_ficha`", datos["instruccion"])
        self.assertIn("UN solo mensaje", datos["instruccion"])

    def test_las_candidatas_sin_foto_no_rompen_el_turno(self):
        """Los reportes importados a veces no traen imagen: van en el resumen
        de texto igual, solo que sin foto."""
        datos, acciones = _correr(CANDIDATAS, fotos_por_mascota=0)
        self.assertEqual(datos["fotos_enviadas"], 0)
        self.assertEqual([a for a in acciones if a["type"] == "say_media"], [])
        self.assertEqual(len(datos["coincidencias"]), 3)

    def test_sin_coincidencias_pide_registrar_el_caso(self):
        datos, acciones = _correr([])
        self.assertEqual(datos["coincidencias"], [])
        self.assertEqual(acciones, [])
        self.assertIn("registrar_reporte", datos["instruccion"])

    def test_el_resumen_de_cada_ficha_viaja_para_que_el_modelo_lo_use(self):
        datos, _ = _correr(CANDIDATAS)
        for ficha in datos["coincidencias"]:
            self.assertIn("resumen", ficha)
            self.assertIn(ficha["codigo"], ficha["resumen"])


if __name__ == "__main__":
    unittest.main()
