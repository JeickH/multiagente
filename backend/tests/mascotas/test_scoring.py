"""El cruce: cuánto se parece un reporte a lo que describe la persona.

Estas pruebas fijan las decisiones de diseño del scoring que están escritas en
`MANUAL_RECUPERA_TU_MASCOTA.md` §5 y que costaron trabajo afinar. Cada una
existe porque romperla tiene una consecuencia concreta sobre una familia
buscando a su animal, no por cubrir líneas.

No tocan la base: `_evaluar` solo lee atributos, así que basta con un objeto
`Mascota` sin guardar.
"""
from __future__ import annotations

import pytest

from app import models
from app.services import mascotas as svc


def reporte(**campos) -> models.Mascota:
    """Un `Mascota` en memoria (sin sesión) con lo que el test necesite."""
    base = {
        "codigo": "MC-00001",
        "tipo_registro": "encontrada",
        "especie": "perro",
        "ubicacion": "Cali",
    }
    return models.Mascota(**{**base, **campos})


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

class TestNormalizar:
    @pytest.mark.parametrize("crudo", ["Café", "cafe", "CAFÉ", "  café  ", "Ca-fé"])
    def test_las_variantes_de_escritura_colapsan(self, crudo):
        assert svc.normalizar(crudo).replace(" ", "") == "cafe"

    @pytest.mark.parametrize(
        "dicho,esperado",
        [
            ("perrito", "perro"), ("Canino", "perro"), ("cachorro", "perro"),
            ("gatico", "gato"), ("felino", "gato"), ("michi", "gato"),
            ("conejo", "otra"), ("", ""),
        ],
    )
    def test_especie_se_deduce_de_como_habla_la_gente(self, dicho, esperado):
        assert svc.normalizar_especie(dicho) == esperado

    @pytest.mark.parametrize(
        "dicho,esperado",
        [("macho", "macho"), ("M", "macho"), ("hembra", "hembra"),
         ("H", "hembra"), ("no sé", "desconocido"), (None, None)],
    )
    def test_sexo(self, dicho, esperado):
        assert svc.normalizar_sexo(dicho) == esperado


class TestSinonimos:
    """Palabras distintas para lo mismo. Si esto se rompe, dos reportes de la
    misma mascota dejan de cruzarse por cómo la describió cada persona."""

    @pytest.mark.parametrize(
        "una,otra",
        [
            ("criollo", "mestizo"), ("criollo", "callejero"), ("mestiza", "chandoso"),
            ("café", "marrón"), ("cafe", "chocolate"),
            ("dorado", "amarillo"), ("beige", "crema"),
            ("gris", "plateado"),
            ("atigrado", "rayado"),
            ("pequeño", "chiquito"),
        ],
    )
    def test_palabras_equivalentes_puntuan_igual_que_la_misma(self, una, otra):
        assert svc._score_texto(una, otra, 5) == 5

    def test_sin_raza_es_criollo(self):
        # Expresión de dos palabras: se colapsa antes que las sueltas o nunca
        # coincide (por eso `_canonizar` hace dos pasadas).
        assert svc._score_texto("sin raza", "criollo", 5) == 5

    def test_palabras_de_grupos_distintos_no_se_confunden(self):
        assert svc._score_texto("café", "gris", 5) == 0


# ---------------------------------------------------------------------------
# Puntaje de un campo
# ---------------------------------------------------------------------------

class TestScoreTexto:
    def test_exacto_vale_el_peso_completo(self):
        assert svc._score_texto("labrador", "labrador", 5) == 5

    def test_contenido_vale_uno_menos(self):
        assert svc._score_texto("labrador", "labrador retriever", 5) == 4

    def test_token_compartido_vale_dos_menos(self):
        assert svc._score_texto("labrador negro", "retriever negro", 5) == 3

    def test_nada_en_comun_no_suma(self):
        assert svc._score_texto("labrador", "pastor aleman", 5) == 0

    @pytest.mark.parametrize("faltante", [None, "", "   "])
    def test_dato_ausente_nunca_resta(self, faltante):
        # Regla de diseño: lo que la persona no sabe, no puntúa — ni a favor ni
        # en contra. Quien perdió a su mascota rara vez recuerda todo.
        assert svc._score_texto(faltante, "labrador", 5) == 0
        assert svc._score_texto("labrador", faltante, 5) == 0

    def test_nunca_devuelve_negativo_ni_pasa_del_peso(self):
        for peso in (1, 2, 3, 5):
            valor = svc._score_texto("collar azul", "collar rojo", peso)
            assert 0 <= valor <= peso


class TestZonasGenericas:
    """"Cali" lo dice casi todo reporte de la base: compartirlo no acerca nada.
    Con umbral 6 esto llegó a producir 5.284 coincidencias inservibles."""

    @pytest.mark.parametrize("generica", ["Cali", "Valle", "Colombia", "Palmira"])
    def test_una_ciudad_compartida_no_suma(self, generica):
        assert svc._score_texto(
            generica, generica, 2, vacios=svc._ZONAS_GENERICAS
        ) == 0

    def test_el_barrio_si_suma(self):
        assert svc._score_texto(
            "San Fernando", "San Fernando", 2, vacios=svc._ZONAS_GENERICAS
        ) == 2

    def test_barrio_igual_suma_aunque_ambos_digan_cali(self):
        assert svc._score_texto(
            "San Fernando, Cali", "San Fernando, Cali", 2,
            vacios=svc._ZONAS_GENERICAS,
        ) > 0


# ---------------------------------------------------------------------------
# El puntaje completo
# ---------------------------------------------------------------------------

class TestEvaluar:
    def test_la_especie_es_el_unico_filtro_duro(self):
        # Un perro nunca es un gato, por muy parecido que sea todo lo demás.
        score, detalle = svc._evaluar(
            {"especie": "gato", "color": "negro"},
            reporte(especie="perro", color="negro"),
        )
        assert score == -1
        assert detalle == {}

    def test_ningun_otro_campo_descarta(self):
        # Zona, color y raza distintos: baja el puntaje, pero el par sigue vivo.
        score, _ = svc._evaluar(
            {"especie": "perro", "color": "negro", "zona": "Meléndez"},
            reporte(especie="perro", color="blanco", ubicacion="Guadalupe"),
        )
        assert score >= 0

    def test_el_peso_esta_en_lo_fisico_no_en_el_nombre(self):
        """Quien encuentra un animal en la calle no sabe cómo se llama.

        El nombre vale 1 (desempate); raza y color valen 5. Si esto se
        invirtiera, el bot cruzaría por coincidencia de nombres comunes.
        """
        solo_nombre, _ = svc._evaluar(
            {"especie": "perro", "nombre": "Lucas"},
            reporte(nombre="Lucas", raza="pastor", color="negro"),
        )
        solo_fisico, _ = svc._evaluar(
            {"especie": "perro", "raza": "pastor", "color": "negro"},
            reporte(nombre="Lucas", raza="pastor", color="negro"),
        )
        assert solo_fisico > solo_nombre

    def test_la_zona_suma_pero_no_es_obligatoria(self):
        """El animal camina: se pierde en San Fernando y aparece en Meléndez.
        Quien lo encuentra reporta dónde ESTÁ, no dónde se perdió."""
        criterios = {"especie": "perro", "raza": "labrador", "color": "dorado"}
        lejos, _ = svc._evaluar(
            {**criterios, "zona": "Meléndez"},
            reporte(raza="labrador", color="dorado", barrio="Guadalupe"),
        )
        cerca, _ = svc._evaluar(
            {**criterios, "zona": "Guadalupe"},
            reporte(raza="labrador", color="dorado", barrio="Guadalupe"),
        )
        assert cerca > lejos
        assert lejos > 0, "una zona distinta no puede anular raza y color"

    def test_sexo_desconocido_no_puntua(self):
        """Es el valor por defecto de las plataformas de origen: que dos
        reportes lo compartan no dice nada."""
        _, detalle = svc._evaluar(
            {"especie": "perro", "sexo": "desconocido"},
            reporte(sexo="desconocido"),
        )
        assert "sexo" not in detalle

    def test_sexo_conocido_si_puntua(self):
        _, detalle = svc._evaluar(
            {"especie": "perro", "sexo": "hembra"}, reporte(sexo="hembra")
        )
        assert detalle["sexo"] == 2

    def test_las_senas_se_buscan_en_todo_el_texto_del_reporte(self):
        # "collar azul" puede estar en `senas`, en `notas` o en la descripción
        # libre: la persona no sabe en qué campo lo guardamos nosotros.
        _, detalle = svc._evaluar(
            {"especie": "perro", "descripcion": "tiene collar azul y cojea"},
            reporte(senas="collar azul", notas="llegó cojeando"),
        )
        assert detalle["senas"] >= 2

    def test_las_senas_estan_topadas_en_cinco(self):
        muchas = "collar azul mancha blanca cojea oreja rota cola corta pelo largo"
        _, detalle = svc._evaluar(
            {"especie": "perro", "descripcion": muchas}, reporte(senas=muchas)
        )
        assert detalle["senas"] == 5

    def test_el_desglose_explica_el_puntaje(self):
        """El panel le muestra al equipo POR QUÉ cruzaron dos casos antes de
        que llamen a una familia. La suma del desglose es el puntaje."""
        score, detalle = svc._evaluar(
            {"especie": "perro", "raza": "labrador", "color": "dorado",
             "sexo": "macho", "zona": "San Fernando"},
            reporte(raza="labrador", color="dorado", sexo="macho",
                    barrio="San Fernando"),
        )
        assert score == sum(detalle.values())
        assert set(detalle) == {"especie", "raza", "color", "sexo", "zona"}

    def test_criterios_vacios_no_inventan_parecido(self):
        score, detalle = svc._evaluar({}, reporte(raza="labrador"))
        assert score == 0
        assert detalle == {}
