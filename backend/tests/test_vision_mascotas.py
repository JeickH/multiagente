"""El desempate visual entre candidatas (#368).

La foto no decide: reordena lo que el texto ya dejó cerca. Estos casos fijan
los límites que hacen que eso siga siendo cierto — cuánto puede sumar, a
cuántas candidatas se aplica, y qué pasa cuando el proveedor falla.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from app.services import vision_mascotas as vm

FOTO = (b"\xff\xd8\xff", "image/jpeg")


def _candidata(codigo, score):
    return {"codigo": codigo, "score": score}


class PuntosPorParecidoTests(unittest.TestCase):
    def test_la_escala_es_modesta_a_proposito(self):
        # El máximo empata con acertar la raza: la foto desempata, no manda.
        self.assertEqual(vm.puntos_por_parecido(10), 5)
        self.assertEqual(vm.puntos_por_parecido(9), 5)
        self.assertEqual(vm.puntos_por_parecido(7), 3)
        self.assertEqual(vm.puntos_por_parecido(6), 1)

    def test_por_debajo_de_seis_no_suma(self):
        """"Podrían ser" no es información: si sumara, un parecido tibio
        encaramaría animales que el texto había separado bien."""
        for flojo in (0, 3, 5):
            self.assertEqual(vm.puntos_por_parecido(flojo), 0)


class ReordenarTests(unittest.TestCase):
    def test_sin_foto_de_la_persona_no_toca_el_orden(self):
        candidatas = [_candidata("MC-1", 10), _candidata("MC-2", 8)]
        self.assertEqual(
            vm.reordenar_candidatas(None, candidatas, lambda c: FOTO), candidatas
        )

    def test_la_foto_puede_adelantar_a_una_candidata(self):
        """El texto la tenía segunda; la foto la sube a primera."""
        candidatas = [_candidata("MC-1", 10), _candidata("MC-2", 8)]
        veredictos = {
            "MC-1": {"parecido": 2, "motivo": "otro color"},
            "MC-2": {"parecido": 9, "motivo": "misma mancha"},
        }
        pendientes = ["MC-1", "MC-2"]   # se comparan en el orden del texto

        with patch.object(
            vm, "comparar",
            side_effect=lambda a, b, model_id=None: veredictos[pendientes.pop(0)],
        ):
            salida = vm.reordenar_candidatas(FOTO, candidatas, lambda c: FOTO)

        self.assertEqual(salida[0]["codigo"], "MC-2")   # 8 + 5 = 13
        self.assertEqual(salida[0]["motivo_foto"], "misma mancha")
        self.assertEqual(salida[1]["codigo"], "MC-1")   # 10 + 0

    def test_no_compara_mas_de_cuatro(self):
        """Cada comparación son dos imágenes al modelo: lo más caro del bot."""
        candidatas = [_candidata(f"MC-{i}", 10 - i) for i in range(8)]
        with patch.object(vm, "comparar",
                          return_value={"parecido": 7, "motivo": "x"}) as mock:
            vm.reordenar_candidatas(FOTO, candidatas, lambda c: FOTO)
        self.assertEqual(mock.call_count, vm.MAX_COMPARACIONES)

    def test_una_candidata_sin_foto_no_se_penaliza(self):
        candidatas = [_candidata("MC-1", 10), _candidata("MC-2", 9)]
        with patch.object(vm, "comparar",
                          return_value={"parecido": 9, "motivo": "igual"}):
            salida = vm.reordenar_candidatas(
                FOTO, candidatas, lambda c: None if c == "MC-1" else FOTO
            )
        # MC-2 gana por la foto, pero MC-1 conserva sus 10 puntos de texto.
        self.assertEqual(salida[0]["codigo"], "MC-2")
        self.assertEqual(salida[1]["score"], 10)
        self.assertNotIn("parecido_foto", salida[1])

    def test_si_el_proveedor_falla_queda_el_orden_del_texto(self):
        """Sin desempate se sigue como antes de que existiera esta función."""
        candidatas = [_candidata("MC-1", 10), _candidata("MC-2", 8)]
        with patch.object(vm, "comparar", return_value=None):
            salida = vm.reordenar_candidatas(FOTO, candidatas, lambda c: FOTO)
        self.assertEqual([c["codigo"] for c in salida], ["MC-1", "MC-2"])

    def test_un_error_leyendo_la_foto_no_tumba_la_busqueda(self):
        candidatas = [_candidata("MC-1", 10)]

        def _explota(_codigo):
            raise RuntimeError("S3 caído")

        with patch.object(vm, "comparar", return_value={"parecido": 9, "motivo": "x"}):
            salida = vm.reordenar_candidatas(FOTO, candidatas, _explota)
        self.assertEqual(salida[0]["score"], 10)


class CompararTests(unittest.TestCase):
    def test_un_fallo_del_proveedor_devuelve_none_y_no_levanta(self):
        with patch("app.services.llm_engine._bedrock_client",
                   side_effect=RuntimeError("sin credenciales")):
            self.assertIsNone(vm.comparar(FOTO, FOTO))


if __name__ == "__main__":
    unittest.main()
