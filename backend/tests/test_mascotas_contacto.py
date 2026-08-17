"""Quién está escribiendo, cuando todavía no hay reporte registrado.

El panel leía el contacto del hilo desde el reporte. Si la persona se presentaba
en el primer mensaje y la conversación no llegaba a registrar nada, el hilo
quedaba anónimo: no había a quién devolverle la llamada. Estos casos cubren el
rescate de ese dato desde lo que la persona escribió.
"""
import unittest

from app.services.mascotas import contacto_dicho, nombre_dicho, telefono_dicho


class TelefonoDichoTests(unittest.TestCase):
    def test_celular_con_y_sin_indicativo(self):
        self.assertEqual(telefono_dicho("mi tel es 3009998877"), "3009998877")
        self.assertEqual(telefono_dicho("escríbeme al +57 300 999 8877"), "573009998877")

    def test_separadores_habituales(self):
        self.assertEqual(telefono_dicho("300-999-8877 es mi numero"), "3009998877")
        self.assertEqual(telefono_dicho("(602) 555 3311"), "6025553311")

    def test_no_confunde_codigos_ni_fechas(self):
        # Un código de reporte y una fecha no son teléfonos.
        self.assertIsNone(telefono_dicho("mi caso es MC-00012"))
        self.assertIsNone(telefono_dicho("se perdió el 12/08/2026"))

    def test_sin_telefono(self):
        self.assertIsNone(telefono_dicho("se me perdió mi perro en San Fernando"))


class NombreDichoTests(unittest.TestCase):
    def test_formas_de_presentarse(self):
        self.assertEqual(nombre_dicho("hola, soy Carlos"), "Carlos")
        self.assertEqual(nombre_dicho("me llamo ana maria"), "Ana Maria")
        self.assertEqual(nombre_dicho("mi nombre es JUAN"), "Juan")

    def test_no_captura_lo_que_no_es_nombre(self):
        # El motivo de la lista de exclusión: sin ella el panel se llenaba de
        # contactos llamados "De" o "La".
        self.assertIsNone(nombre_dicho("soy de Cali"))
        self.assertIsNone(nombre_dicho("soy la dueña del perro"))
        self.assertIsNone(nombre_dicho("soy el vecino"))

    def test_sin_presentacion(self):
        self.assertIsNone(nombre_dicho("encontré un perro negro"))


class ContactoDichoTests(unittest.TestCase):
    def test_nombre_y_telefono_juntos(self):
        self.assertEqual(
            contacto_dicho("Hola, soy Carlos, mi numero es 3009998877"),
            "Carlos · 3009998877",
        )

    def test_solo_uno_de_los_dos(self):
        self.assertEqual(contacto_dicho("soy Ana"), "Ana")
        self.assertEqual(contacto_dicho("llámame al 3145566778"), "3145566778")

    def test_mensaje_sin_datos_de_contacto(self):
        self.assertIsNone(contacto_dicho("se me perdió mi gato atigrado"))


class AntesalaDelChatTests(unittest.TestCase):
    """La plantilla real que arma `frontend/pages/mascotas.tsx`.

    La antesala pide nombre y teléfono y con eso compone el primer mensaje del
    hilo. Ese era el caso que se estaba perdiendo: si la conversación no llegaba
    a registrar un reporte, el panel mostraba el hilo sin contacto aunque la
    persona lo hubiera dado antes de escribir una sola palabra.
    """

    def test_busca_su_mascota(self):
        self.assertEqual(
            contacto_dicho("Hola, soy Alexander Quintero. Se me perdió mi mascota "
                           "y quiero buscarla. Mi teléfono de contacto es 314 439 3595."),
            "Alexander Quintero · 3144393595",
        )

    def test_reporta_una_encontrada(self):
        self.assertEqual(
            contacto_dicho("Hola, soy Ana. Encontré una mascota y quiero reportarla. "
                           "Mi teléfono de contacto es 3009998877."),
            "Ana · 3009998877",
        )

    def test_listado_no_pide_telefono(self):
        # El Excel no necesita teléfono: nadie tiene que devolverle la llamada.
        self.assertEqual(
            contacto_dicho("Hola, soy Juan Carlos. Quiero descargar el listado de "
                           "mascotas encontradas en Excel."),
            "Juan Carlos",
        )

    def test_nombre_en_minusculas_y_telefono_con_indicativo(self):
        self.assertEqual(
            contacto_dicho("Hola, soy maría josé. Se me perdió mi mascota y quiero "
                           "buscarla. Mi teléfono de contacto es +57 300 123 4567."),
            "María José · 573001234567",
        )


if __name__ == "__main__":
    unittest.main()
