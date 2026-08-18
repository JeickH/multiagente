"""Importadores de fuentes externas (`backend/scripts/fuentes/base.py`).

La regla que hace que este archivo exista (manual §6.3): **ningún teléfono
puede quedar en `senas` ni en `notas`**. El guardarraíl `_viola_contacto`
descarta el turno completo si el bot escribe un número que no vino de
`entregar_contacto` — o sea que un teléfono escondido en una descripción deja
al bot mudo justo cuando encontró a la mascota.

Protección Animal publica el teléfono dentro del texto de la descripción, así
que este camino se recorre en cada importación real.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Los importadores viven en `scripts/`, fuera del paquete `app`.
RAIZ = Path(__file__).resolve().parents[3] / "backend"
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts.fuentes import base  # noqa: E402


class TestQuitarTelefonos:
    @pytest.mark.parametrize(
        "con_numero",
        [
            "Perrita encontrada en el centro. Teléfono: 3012458967",
            "Se busca. Contacto 301 245 8967",
            "Informes al 3012458967 gracias",
            "Llamar al +57 301 245 8967",
            "Comunicarse 301-245-8967",
            "Fijo 5553311 para más datos",
        ],
    )
    def test_no_queda_ni_un_digito_de_telefono(self, con_numero):
        limpio = base.quitar_telefonos(con_numero) or ""
        assert "3012458967" not in limpio.replace(" ", "").replace("-", "")
        assert "5553311" not in limpio.replace(" ", "")

    def test_el_texto_util_sobrevive(self):
        limpio = base.quitar_telefonos(
            "Perrita café con collar azul, muy asustada. Teléfono: 3012458967"
        )
        assert "collar azul" in limpio
        assert "asustada" in limpio

    def test_no_deja_el_rotulo_colgando(self):
        """Sin esto las señas terminan en "Teléfonos de contacto: /"."""
        for crudo in (
            "Gato negro. Teléfonos de contacto: 3012458967",
            "Gato negro. Celular: 3012458967",
            "Gato negro. Contacto: 3012458967 / 3109998877",
            "Gato negro. WhatsApp 3012458967",
        ):
            limpio = base.quitar_telefonos(crudo)
            assert limpio.rstrip().endswith("negro"), f"quedó basura: {limpio!r}"

    def test_un_texto_sin_telefonos_no_se_toca(self):
        original = "Perro criollo café, cojea de la pata trasera"
        assert base.quitar_telefonos(original) == original

    @pytest.mark.parametrize("vacio", [None, "", "   "])
    def test_vacios(self, vacio):
        assert base.quitar_telefonos(vacio) in (None, vacio)

    def test_si_solo_habia_un_telefono_queda_none(self):
        # `None` y no cadena vacía: es lo que la columna debe guardar.
        assert base.quitar_telefonos("3012458967") is None

    def test_no_se_come_las_fechas_ni_los_codigos(self):
        # Un año o un peso no son teléfonos: quitarlos rompería la descripción.
        limpio = base.quitar_telefonos("Perdido en 2026, pesa 12 kg")
        assert "2026" in limpio
        assert "12 kg" in limpio


class TestTelefonoDeTexto:
    """Rescata el número ANTES de borrarlo, para guardarlo en su columna."""

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("Contacto 3012458967", "301 2458967"),
            ("Llamar al +57 301 245 8967", "301 2458967"),
            ("Informes 301-245-8967", "301 2458967"),
            ("Sin teléfono aquí", None),
        ],
    )
    def test_lo_encuentra_y_lo_normaliza(self, texto, esperado):
        assert base.telefono_de_texto(texto) == esperado

    def test_revisa_varios_textos_en_orden(self):
        assert base.telefono_de_texto(
            "sin nada", "descripción con 3012458967"
        ) == "301 2458967"


class TestTelefonoColombiano:
    @pytest.mark.parametrize(
        "crudo,esperado",
        [
            ("3012458967", "301 2458967"),
            ("+57 301 245 8967", "301 2458967"),
            ("573012458967", "301 2458967"),
            ("301-245-8967", "301 2458967"),
            ("5553311", "5553311"),          # fijo sin indicativo
            ("no tengo", None),
            ("12", None),
            (None, None),
        ],
    )
    def test_normaliza_lo_que_publica_cada_fuente(self, crudo, esperado):
        assert base.telefono_colombiano(crudo) == esperado


class TestValorReal:
    """Los rellenos no se guardan: el cruce puntúa el nombre y la zona, y
    "Anonimo" contra "Anonimo" daría un parecido que no existe."""

    @pytest.mark.parametrize(
        "relleno",
        ["Anónimo", "sin nombre", "Desconocido", "N/A", "-", "?", "no se sabe",
         "Rescatado", "Encontrada", "sin datos"],
    )
    def test_los_rellenos_se_descartan(self, relleno):
        assert base.valor_real(relleno, 80) is None

    @pytest.mark.parametrize("real", ["Lucas", "Pelusa", "Firulais"])
    def test_un_nombre_de_verdad_se_conserva(self, real):
        assert base.valor_real(real, 80) == real

    def test_recorta_al_limite(self):
        assert len(base.valor_real("x" * 200, 80)) == 80


class TestNormalizadores:
    @pytest.mark.parametrize(
        "crudo,esperado",
        [("Perro", "perro"), ("PERRA", "perro"), ("Gato", "gato"),
         ("Gata", "gato"), ("Canino", "perro"), ("Felino", "gato")],
    )
    def test_especie(self, crudo, esperado):
        assert base.normalizar_especie(crudo) == esperado

    def test_el_sexo_se_deduce_del_texto(self):
        assert base.sexo_desde_texto("la perrita estaba asustada") == "hembra"
        assert base.sexo_desde_texto("el perro es muy juguetón") == "macho"
        assert base.sexo_desde_texto("encontrado en la calle") == "desconocido"

    def test_el_color_sale_del_texto_libre(self):
        # Es una lectura, no una adivinanza: junta las palabras de color que
        # están escritas, sin tildes, y por eso el HTML de revisión lo marca
        # como derivado para que el humano lo corrija ("manchas" no es color).
        assert base.color_desde_texto("perro cafe") == "cafe"
        assert base.color_desde_texto("perro café con manchas") == "cafe con manchas"
        assert base.color_desde_texto("no dice nada del color") is None

    def test_el_vocabulario_de_color_habla_el_idioma_del_cruce(self):
        """Si aquí se guardara "marrón" y el matcher canoniza a "cafe", los dos
        reportes de la misma mascota no se encontrarían."""
        from app.services import mascotas as svc

        assert svc._score_texto(
            base.color_desde_texto("perro marron"), "café", 5
        ) == 5

    def test_el_tamaño_sale_del_texto_libre(self):
        assert base.tamano_desde_texto("perro grande, muy fuerte") == "grande"

    def test_la_edad_sale_del_texto_libre(self):
        assert base.edad_desde_texto("es un cachorro de meses") == "cachorro"


class TestReglaDeOro:
    """La comprobación de punta a punta de la regla §6.3, sobre el caso real de
    Protección Animal: teléfono dentro de la descripción."""

    def test_un_registro_importado_no_lleva_telefonos_en_el_texto(self):
        descripcion = (
            "Perrita criolla café, collar azul, muy asustada. "
            "Teléfonos de contacto: 3012458967 / 3109998877"
        )

        telefono = base.telefono_de_texto(descripcion)
        senas = base.quitar_telefonos(descripcion)

        # El número se rescata para su columna...
        assert telefono == "301 2458967"
        # ...y desaparece del texto que va a leer el bot.
        solo_digitos = "".join(c for c in senas if c.isdigit())
        assert len(solo_digitos) < 7, f"quedó un teléfono en las señas: {senas!r}"
        assert "collar azul" in senas
