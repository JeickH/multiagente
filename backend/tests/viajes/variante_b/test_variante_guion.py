"""El guion del bot 2 (`bot_contexts/demo_viajes_b.md`) cumple lo que se le pidió.

Estas pruebas no miden cómo responde el modelo (eso es la suite de costo, con
≥12 corridas por versión): fijan lo que se puede verificar leyendo el texto, y
que es fácil de romper sin darse cuenta al editarlo después:

- cabe en el tope (≤ 38.000 caracteres, el del guion editable es 40.000);
- **no tiene ninguna cifra de dinero escrita a mano** (lección del Sprint 24:
  un $350.000 constante sobrevivió varias temporadas). El «desde», los niños y
  el anticipo salen del tarifario y de sus extras;
- la apertura es corta, sin itinerario y cierra preguntando el mes;
- el nombre se pide una vez y al reservar, y la frase vieja del saludo no
  aparece citada (citarla la vuelve a meter en el prompt: ver memoria
  `gotcha_dos_bloques_literales_prompt`);
- cada estrategia que vive en el prompt tiene su **sección propia** (una regla
  metida al lado de otra se diluye: `gotcha_reglas_del_prompt_se_diluyen`).
"""
from __future__ import annotations

import re

import pytest

from app.data.bot_viajes_b import RUTA_MD_B, instrucciones_b
from app.services import llm_engine

GUION = instrucciones_b()


def _seccion(titulo: str) -> str:
    """El cuerpo de la sección `## <titulo>` (hasta la siguiente `## `)."""
    m = re.search(
        rf"^## {re.escape(titulo)}\n(.*?)(?=^## |\Z)", GUION, re.MULTILINE | re.DOTALL
    )
    assert m, f"falta la sección «{titulo}»"
    return m.group(1)


def _apertura() -> str:
    """El mensaje de apertura literal: de «¡Hola! 😊 Soy» hasta su pregunta."""
    cuerpo = _seccion("El primer mensaje")
    m = re.search(r"^¡Hola! 😊 Soy .*?\n\n¿Para qué mes lo estás pensando\? 😊", cuerpo,
                  re.MULTILINE | re.DOTALL)
    assert m, "no se encontró el mensaje de apertura literal"
    return m.group(0)


class TestTamañoYCarga:
    def test_cabe_en_el_tope(self):
        assert len(GUION) <= 38_000

    def test_el_motor_lo_carga_por_su_context_key(self):
        """Si `bots.instrucciones` quedara vacía, el motor cae al `.md` por el
        `context_key` de la config: tiene que ser este mismo archivo."""
        assert llm_engine._load_context("demo_viajes_b").strip() == GUION

    def test_la_ruta_es_la_del_paquete(self):
        assert RUTA_MD_B.name == "demo_viajes_b.md"
        assert RUTA_MD_B.parent.name == "bot_contexts"


class TestSinCifrasDeDinero:
    def test_ningun_monto_con_signo_pesos(self):
        assert re.findall(r"\$\s?\d", GUION) == []

    def test_ningun_monto_escrito_en_miles(self):
        assert re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", GUION) == []
        assert re.findall(r"(?i)\b\d+\s*(?:mil|k|millones?)\b", GUION) == []

    def test_la_promo_inexistente_no_esta_escrita(self):
        """El monto de la promo que no existe vive en la config y lo detecta el
        código sobre el texto del CLIENTE. Escribirlo aquí invita al bot a
        citarlo por su cuenta."""
        assert "350" not in GUION

    def test_el_porcentaje_del_anticipo_no_esta_escrito(self):
        """El 30 % viene de los extras del tarifario, no del guion."""
        assert re.findall(r"\d+\s*%", GUION) == []


class TestApertura:
    def test_es_corta(self):
        """~210 caracteres con el «desde» puesto; el hueco `$<desde>` mide
        parecido a una cifra real."""
        assert len(_apertura()) <= 260

    def test_lleva_el_desde_como_hueco_que_llena_el_sistema(self):
        assert "$<desde>" in _apertura()

    def test_no_lleva_itinerario(self):
        apertura = _apertura()
        for dia in ("Sábado", "Domingo", "Caimanera", "Estación Universidad"):
            assert dia not in apertura

    def test_cierra_con_la_pregunta_del_mes_y_nada_mas(self):
        assert _apertura().rstrip().endswith("¿Para qué mes lo estás pensando? 😊")
        assert _apertura().count("¿") == 1

    def test_no_pide_el_nombre(self):
        assert not llm_engine._PIDE_EL_NOMBRE.search(_apertura())

    def test_el_flyer_lo_pone_el_sistema(self):
        cuerpo = _seccion("El primer mensaje")
        assert "El flyer del mes lo adjunta el sistema" in cuerpo

    def test_el_itinerario_sigue_disponible_por_su_camino(self):
        itinerario = GUION.split("### Itinerario", 1)[1]
        for dia in ("*Viernes – Viaje*", "*Sábado – Caimanera*",
                    "*Domingo – Tolú*", "*Lunes – Regreso*"):
            assert dia in itinerario


class TestNombre:
    def test_la_frase_vieja_del_saludo_no_aparece(self):
        """Ni como mal ejemplo: citarla la vuelve a meter en el prompt."""
        assert not re.search(r"(?i)con qui[eé]n tengo el gusto", GUION)

    def test_se_pide_al_reservar_con_la_frase_de_la_reserva(self):
        assert "«¿A nombre de quién aparto el cupo?»" in _seccion("El nombre")
        reserva = GUION.split("### Reserva", 1)[1]
        assert "¿A nombre de quién aparto el cupo?" in reserva
        assert "nombre completo" in reserva

    def test_el_nombre_nunca_bloquea_una_cotizacion(self):
        assert "El nombre nunca bloquea una cotización" in _seccion("El nombre")


class TestSeccionesPropias:
    @pytest.mark.parametrize(
        "titulo",
        [
            "Una sola pregunta, y al final",              # 5, 10, 17
            "El primer mensaje",                          # 1, 3, 4
            "El nombre",                                  # 2, 12
            "El anticipo y cómo se paga",                 # 16
            "Cuando citan un precio de nuestra publicidad",  # 20, 21
            "Cuándo avisar que hay intención de compra",  # 22
            "Cuando lo tiene que consultar",              # 14
            "Cuándo cerrar",
        ],
    )
    def test_existe(self, titulo):
        assert _seccion(titulo).strip()

    def test_la_decision_aplazada_no_esta_dentro_de_cuando_cerrar(self):
        """Antes eran el caso 2 de la misma sección; ahora cada una tiene la
        suya y «Cuándo cerrar» solo remite."""
        cerrar = _seccion("Cuándo cerrar")
        assert "¿Te escribo mañana" not in cerrar
        assert "Cuando lo tiene que consultar" not in cerrar or "sección siguiente" in cerrar


class TestEstrategias:
    def test_14_la_aplazada_deja_una_pregunta_con_momento_y_no_cierra(self):
        cuerpo = _seccion("Cuando lo tiene que consultar")
        assert "pregunta\n   concreta que tenga un momento" in cuerpo
        assert "finalizar_conversacion" in cuerpo and "no_responder" in cuerpo

    def test_14_la_aplazada_es_guia_y_no_frase_para_copiar(self):
        """QA contra Bedrock (7-oct-2026): con la frase escrita entre comillas,
        12 de 12 corridas la copiaron letra por letra. Ninguna pregunta de
        «te escribo» puede quedar literal en el guion."""
        assert not re.search(r"(?i)¿te escribo", GUION)
        assert "Es una decisión para tomar juntos" not in GUION

    def test_16_el_anticipo_trae_saldo_y_medios_de_pago(self):
        cuerpo = _seccion("El anticipo y cómo se paga")
        assert "8 a 10 días hábiles" in cuerpo
        assert "`medios_pago`" in cuerpo
        # El porcentaje lo inyecta el sistema; si no llega, no se adivina.
        assert "te lo da el\n   sistema" in cuerpo
        assert "no\n   adivines uno" in cuerpo

    def test_21_nunca_interroga_y_escala(self):
        cuerpo = _seccion("Cuando citan un precio de nuestra publicidad")
        assert "«Déjame confirmarlo con un compañero para no darte un dato" in cuerpo
        assert "`escalar_a_asesor`" in cuerpo
        assert "¿De dónde" not in GUION

    def test_20_no_cita_la_promo_del_flyer_por_iniciativa_propia(self):
        """Revisión de seguridad: la detección es sobre lo que escribe el
        cliente; el guion no nombra la promo de lunes a jueves."""
        cuerpo = _seccion("Cuando citan un precio de nuestra publicidad")
        assert "lunes a jueves" not in cuerpo

    def test_22_reservar_manda_sobre_fecha_concreta(self):
        """QA: «quiero reservar la del 18» salía como `fecha_concreta` 10/12."""
        cuerpo = _seccion("Cuándo avisar que hay intención de compra")
        assert "aunque en la misma frase nombre una fecha" in cuerpo
        assert '"quiero reservar la del 18" es\n  `reservar`' in cuerpo

    def test_22_registrar_intencion_con_los_cuatro_tipos(self):
        cuerpo = _seccion("Cuándo avisar que hay intención de compra")
        assert "`registrar_intencion`" in cuerpo
        for tipo in ("anticipo", "reservar", "fecha_concreta", "datos"):
            assert f'`tipo: "{tipo}"`' in cuerpo
        assert set(llm_engine.TIPOS_DE_INTENCION) == {
            "anticipo", "reservar", "fecha_concreta", "datos"
        }

    def test_19_los_ninos_salen_del_resultado_de_precios(self):
        ninos = GUION.split("### Niños", 1)[1].split("###", 1)[0]
        assert "línea" in ninos and "consulta de" in ninos

    def test_17_los_adjuntos_van_antes_de_la_pregunta(self):
        cuerpo = _seccion("Una sola pregunta, y al final")
        assert "van **antes** de la pregunta" in cuerpo
        assert "Después de la pregunta no escribes nada más" in cuerpo


class TestDuracionYTono:
    def test_no_cuenta_dias_del_itinerario(self):
        """El plan dura 3 días / 2 noches aunque el itinerario narre 4 bloques
        (memoria `duracion_planes_arranquemos`). Ninguna duración escrita."""
        assert not re.search(r"(?i)\b[2-5]\s*(?:d[ií]as|noches)\b(?!\s*h[aá]biles)", GUION)
        assert "no cuenta como día de plan" in GUION

    def test_sin_frases_prohibidas_dichas_como_propias(self):
        for prohibida in ("todo incluido", "todas las comidas"):
            for m in re.finditer(prohibida, GUION):
                # Solo pueden aparecer para prohibirlas.
                contexto = GUION[max(0, m.start() - 60): m.end() + 60]
                assert "falsas" in contexto

    def test_la_sena_solo_aparece_para_prohibirla(self):
        apariciones = [m.start() for m in re.finditer(r"\bseña\b", GUION)]
        assert len(apariciones) == 1


class TestAjustesDelQA:
    """Hallazgos de la corrida contra Bedrock del 7-oct-2026
    (`entregables/transcripciones_b/2026-10-07/`)."""

    def test_el_mes_obliga_a_consultar_en_ese_turno(self):
        """G03/G06: con «octubre» el bot repetía el desde de la apertura y
        hasta inventaba fechas, sin llamar la consulta."""
        cuerpo = _seccion("Cómo se cotiza")
        assert "Cuando la persona dice el mes, consultas precios en ese mismo turno." in cuerpo

    def test_con_el_mes_va_el_desde_por_hotel_y_no_la_lista(self):
        """G02: 18 turnos de 9-18 líneas listando todas las salidas."""
        cuerpo = _seccion("Cómo se cotiza")
        assert "La lista de salidas con sus precios no va en ese mensaje." in cuerpo
        assert "el \"desde\" de cada hotel en ese mes" in cuerpo

    def test_al_escalar_siempre_se_escribe(self):
        """G10: con los datos de reserva el bot escalaba sin escribir nada."""
        herramientas = _seccion("Qué puedes hacer (herramientas)")
        assert "En ese mismo turno le escribes a la persona" in herramientas
        reserva = GUION.split("### Reserva", 1)[1]
        assert "le escribes en ese mismo turno" in reserva
        assert "confirma el cupo y el pago" in reserva

    def test_no_narra_la_consulta(self):
        assert "Tampoco narres lo que vas a hacer" in _seccion("Tono y estilo")
