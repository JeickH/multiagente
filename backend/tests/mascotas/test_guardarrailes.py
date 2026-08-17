"""Los guardarraíles del bot Huella.

Son la regla 2 del manual: **el teléfono de contacto no se inventa jamás**, y
el bot no describe una mascota que no consultó. Un modelo pequeño "recuerda"
un número plausible en vez de pedirlo, y aquí eso significa mandar a una
familia angustiada a marcar un número equivocado.

Si algo de este archivo se pone en rojo, no se debilita el test: se arregla el
motor.
"""
from __future__ import annotations

import pytest

from app.services import llm_engine

# Config de un bot de mascotas (los guardarraíles solo aplican si `mascotas`
# está presente en la config: los demás bots de la plataforma no los llevan).
CFG = {"context_key": "mascotas_cali", "mascotas": {}}
CFG_OTRO_BOT = {"context_key": "talulah"}


class TestTelefonoInventado:
    @pytest.mark.parametrize(
        "inventado",
        [
            "Llama al 3012458967",
            "El número es 301 245 8967",
            "Comunícate al (602) 555-3311",
            "Escríbele al +57 315 802 4471",
            "Su teléfono: 315-802-4471",
        ],
    )
    def test_un_numero_sin_tool_descarta_el_turno(self, inventado):
        assert llm_engine._viola_contacto(CFG, [inventado], []) is True

    @pytest.mark.parametrize(
        "inocente",
        [
            "Tu reporte quedó con el código MC-00012",
            "Hay 3 coincidencias",
            "Te respondo en 20 minutos",
            "Llevamos 1.200 mascotas reunidas",
        ],
    )
    def test_los_numeros_que_no_son_telefonos_no_estorban(self, inocente):
        # Menos de 7 dígitos: horas, códigos de reporte y cantidades.
        # Si esto diera falso positivo, el bot se quedaría mudo al dar un código.
        assert llm_engine._viola_contacto(CFG, [inocente], []) is False

    def test_una_fecha_iso_no_parece_un_telefono(self):
        assert llm_engine._viola_contacto(
            CFG, ["Tu reporte quedó registrado hoy, 2026-08-13"], []
        ) is False

    def test_entregar_contacto_habilita_el_numero_QUE_DEVOLVIO(self):
        # Antes bastaba con que la tool apareciera en la ronda para dar por
        # bueno cualquier número. Ahora se compara contra lo que devolvió: es
        # la única forma de distinguir el teléfono de la base del inventado.
        entrega = [{
            "tool": "entregar_contacto",
            "resultado": '{"contacto_telefono": "3012458967"}',
        }]
        assert llm_engine._viola_contacto(
            CFG, ["Llama al 3012458967"], entrega
        ) is False

    def test_el_indicativo_no_cambia_el_numero(self):
        # La tool devuelve `+57 315 802 4471` y el bot escribe `3158024471`:
        # es el mismo teléfono y no puede descartar el turno.
        entrega = [{
            "tool": "entregar_contacto",
            "resultado": '{"contacto_telefono": "+57 315 802 4471"}',
        }]
        assert llm_engine._viola_contacto(
            CFG, ["Su teléfono es 3158024471"], entrega
        ) is False

    def test_el_telefono_que_dio_la_persona_se_puede_repetir(self):
        # Confirmarle su propio número ("registré tu caso con el 3009998877")
        # es legítimo: lo escribió ella misma, no lo inventó el bot.
        assert llm_engine._viola_contacto(
            CFG, ["Registré tu caso con el 3009998877"], [], ["3009998877"]
        ) is False

    def test_otra_tool_no_habilita_dar_telefonos(self):
        for otra in ("buscar_mascota", "ver_ficha", "registrar_reporte"):
            assert llm_engine._viola_contacto(
                CFG, ["Llama al 3012458967"], [{"tool": otra}]
            ) is True, f"{otra} no puede autorizar un teléfono"

    def test_el_guardarrail_es_solo_del_bot_de_mascotas(self):
        # Talulah sí puede dar el teléfono de la tienda.
        assert llm_engine._viola_contacto(
            CFG_OTRO_BOT, ["Llámanos al 3012458967"], []
        ) is False

    def test_sin_texto_no_hay_violacion(self):
        assert llm_engine._viola_contacto(CFG, [], []) is False
        assert llm_engine._viola_contacto(CFG, [""], []) is False

    def test_revisa_todos_los_textos_de_la_ronda(self):
        # El modelo puede partir la respuesta en varios bloques de texto; basta
        # que el número esté en uno.
        assert llm_engine._viola_contacto(
            CFG, ["Encontré a tu perrito 🐾", "Llama al 3012458967"], []
        ) is True

    def test_numero_inventado_en_la_misma_ronda_que_la_tool(self):
        """La brecha del benchmark 2026-08-17, ya cerrada.

        La herramienta devolvió 3009998877, pero el modelo escribió otro número
        antes de leer el resultado y llamó la tool en la misma ronda, así que el
        guardarraíl se daba por satisfecho y el número falso llegaba al usuario.
        Sonnet lo disparó una vez en 77 turnos.
        """
        assert llm_engine._viola_contacto(
            CFG,
            ["Ya la encontramos, llama al 315 234 5678"],
            [{"tool": "entregar_contacto", "resultado": '{"contacto_telefono": "3009998877"}'}],
        ) is True


class TestDescribirSinFicha:
    """Pasó en producción: alguien buscaba un salchicha café perdido en Valle
    del Lili y el bot le presentó un mestizo hallado en Guadalupe como
    "salchicha café encontrado en Valle del Lili" — le devolvió su propia
    descripción y pudo mandarla a buscar un animal que no era el suyo."""

    @pytest.mark.parametrize(
        "presenta",
        [
            "¿Es este tu perro?",
            "Mira esta otra que encontramos",
            "Esta otra apareció ayer",
            "Lo encontraron cerca del parque",
            "Fue encontrada en Guadalupe",
            "La hallaron el martes",
        ],
    )
    def test_presentar_una_mascota_sin_consultarla_descarta_el_turno(self, presenta):
        assert llm_engine._viola_ficha(CFG, [presenta], []) is True

    @pytest.mark.parametrize(
        "tool", ["ver_ficha", "buscar_mascota", "entregar_contacto"]
    )
    def test_con_datos_de_la_base_puede_describir(self, tool):
        assert llm_engine._viola_ficha(
            CFG, ["¿Es este tu perro?"], [{"tool": tool}]
        ) is False

    def test_una_tool_sin_datos_no_habilita_describir(self):
        assert llm_engine._viola_ficha(
            CFG, ["¿Es este tu perro?"], [{"tool": "registrar_reporte"}]
        ) is True

    def test_hablar_normal_no_dispara_nada(self):
        for normal in (
            "¿Me cuentas de qué color es?",
            "Tu reporte quedó guardado 🐾",
            "¿En qué barrio se perdió?",
        ):
            assert llm_engine._viola_ficha(CFG, [normal], []) is False


class TestUbicacionDeRelleno:
    """La ubicación es obligatoria y es lo único que dice dónde ir a buscar.
    Cuando el modelo se siente presionado a registrar sin tenerla, rellena el
    campo con una muletilla y el reporte nace inservible."""

    @pytest.mark.parametrize(
        "muletilla",
        ["pendiente", "por confirmar", "no sé", "N/A", "-", "?", "desconocida",
         "sin especificar", "TBD", "  Pendiente  ", "PENDIENTE."],
    )
    def test_las_muletillas_se_rechazan(self, muletilla):
        assert llm_engine._ubicacion_de_relleno(muletilla) is not None

    @pytest.mark.parametrize(
        "con_prefijo",
        ["ubicación: pendiente", "lugar por confirmar", "barrio: no sé",
         "dirección - pendiente", "zona: desconocida"],
    )
    def test_la_muletilla_con_una_etiqueta_delante_sigue_siendo_muletilla(
        self, con_prefijo
    ):
        assert llm_engine._ubicacion_de_relleno(con_prefijo) is not None

    @pytest.mark.parametrize(
        "real",
        [
            "Barrio San Fernando",
            "Calle 5 con carrera 39",
            "Cerca del parque de Meléndez",
            "Unicentro, Cali",
            "Vereda La Buitrera",
        ],
    )
    def test_un_lugar_de_verdad_pasa(self, real):
        assert llm_engine._ubicacion_de_relleno(real) is None

    @pytest.mark.parametrize("vacio", [None, "", "   "])
    def test_vacio_lo_resuelve_la_validacion_del_servicio(self, vacio):
        # `_ubicacion_de_relleno` solo juzga muletillas; que el campo sea
        # obligatorio lo hace cumplir `crear_reporte`.
        assert llm_engine._ubicacion_de_relleno(vacio) is None
