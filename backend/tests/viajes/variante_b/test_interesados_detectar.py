"""`services/intencion_compra`: la mitad determinista de Interesados (#22).

Frases inventadas, con la forma de lo que escribe un cliente de una agencia de
viajes por WhatsApp (sin tildes, con tildes, en minúscula, con emojis). Nada
copiado de conversaciones reales (regla #8).
"""
from __future__ import annotations

import pytest

from app.services import intencion_compra as ic


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("¿Cuánto es el anticipo para separar?", ["anticipo"]),
        ("y como les pago, por nequi?", ["anticipo"]),
        ("cuanto hay que abonar para el cupo", ["anticipo"]),
        # QA con Bedrock: la pregunta de compra más común no casaba.
        ("¿con cuánto se separa?", ["anticipo"]),
        ("y cuánto se abona?", ["anticipo"]),
        ("me pasas el número de cuenta para consignar", ["anticipo"]),
        ("Listo, quiero reservar 🙌", ["reservar"]),
        ("hagamos la reserva entonces", ["reservar"]),
        ("me lo llevo!", ["reservar"]),
        ("¿El 20 de diciembre todavía hay?", ["fecha_concreta"]),
        ("la salida del 16 al 19", ["fecha_concreta"]),
        ("para el 28/12", ["fecha_concreta"]),
        ("el viernes 14 salimos", ["fecha_concreta"]),
        ("Somos 2 adultos y un niño de 6 años", ["datos"]),
        ("somos cuatro", ["datos"]),
        ("mi nombre completo es Ana Pérez", ["datos"]),
        ("reservame para el viernes 16, somos 3", ["reservar", "fecha_concreta", "datos"]),
    ],
)
def test_detecta_las_cuatro_senales(texto, esperado):
    assert ic.detectar(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "hola",
        "Buenas tardes, información por favor",
        "¿cuánto cuesta en diciembre?",          # un mes suelto no es fecha concreta
        "no quiero reservar todavía",            # negación justo antes
        "todavía no vamos a separar nada",
        "habitaciones separadas?",               # "separadas" no es separar un cupo
        "",
        None,
    ],
)
def test_lo_que_no_es_senal_no_se_inventa(texto):
    assert ic.detectar(texto) == []


def test_un_rango_de_personas_no_se_lee_como_fecha():
    # "de 3 a 4" es cuántos son, no un rango de días.
    assert "fecha_concreta" not in ic.detectar("seríamos de 3 a 4")


def test_el_orden_es_siempre_el_de_los_tipos():
    assert ic.detectar("somos 2 y quiero reservar, cuánto es el anticipo") == [
        "anticipo", "reservar", "datos",
    ]
    assert ic.TIPOS == ("anticipo", "reservar", "fecha_concreta", "datos")


class TestTextoSeguro:
    def test_quita_telefonos_correos_y_enlaces(self):
        t = ic.fragmento_seguro(
            "escríbeme al 300 000 0000 o a ana@example.com, mira https://ejemplo.co/x"
        )
        assert "300" not in t and "@" not in t and "https" not in t
        assert "[número]" in t and "[correo]" in t and "[enlace]" in t

    def test_los_precios_con_puntos_no_se_tapan(self):
        assert "$1.200.000" in ic.fragmento_seguro("¿el de $1.200.000 incluye todo?")

    def test_quita_caracteres_de_control_y_de_formato(self):
        t = ic.texto_seguro("hola​‮ mundo\x07\n\nfin", 160)
        assert t == "hola mundo fin"

    def test_corta_con_puntos_suspensivos(self):
        t = ic.fragmento_seguro("a" * 400)
        assert len(t) == ic.MAX_FRAGMENTO and t.endswith("…")
        assert len(ic.texto_seguro("b" * 400, ic.MAX_RESUMEN)) == 300

    def test_vacio_o_no_texto_es_none(self):
        assert ic.fragmento_seguro("   \n ") is None
        assert ic.texto_seguro(None, 10) is None
        assert ic.texto_seguro(123, 10) is None


def test_tipos_validos_es_lista_blanca():
    assert ic.tipos_validos(["datos", "x", "anticipo", "anticipo", 3, None]) == [
        "anticipo", "datos",
    ]
