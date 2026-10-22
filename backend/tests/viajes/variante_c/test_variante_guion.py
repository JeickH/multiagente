"""El guion del bot 3 (`bot_contexts/demo_viajes_c.md`, «embudo guiado»).

No mide cómo responde el modelo (eso es la corrida contra Bedrock): fija lo
que se verifica leyendo el texto y es fácil de romper al editarlo:

- cabe en el tope (≤ 38.000 caracteres) y el motor lo carga por su clave;
- **ninguna cifra de dinero ni porcentaje escrito a mano** (todo sale de la
  consulta de precios y de los datos del sistema);
- la bienvenida no pide el nombre, no trae itinerario y **no lista meses**
  (el menú lo da el sistema, de los meses que tienen salidas);
- cada bloque de la biblioteca existe, y los que cierran con opciones las
  escriben como el motor las lee: 1️⃣ 2️⃣… al inicio del renglón, en el mismo
  bloque que la pregunta, máximo cinco;
- los bloques sin opciones son justo los que el motor exceptúa (datos de la
  reserva, comprobante, traspaso, despedida);
- el embudo, los protocolos, el protocolo especial y la atención al cliente
  tienen su sección propia.
"""
from __future__ import annotations

import re

import pytest

from app.data.bot_viajes_c import RUTA_MD_C, instrucciones_c
from app.services import llm_engine, recortes_turno

GUION = instrucciones_c()

#: Bloques que cierran con opciones numeradas.
CON_OPCIONES = ("/bienvenida_regreso", "/fechas", "/hotel", "/personas",
                "/cotizacion", "/apartar", "/duda", "/cliente")
#: Bloques que el motor deja cerrar sin opciones (`_SIN_OPCIONES_RE`, traspaso,
#: despedida).
#: /pago va sin opciones desde el 2026-10-21: ahí el bot entrega al asesor.
SIN_OPCIONES = ("/reserva", "/pago", "/asesor", "/despedida")


def _seccion(titulo: str, nivel: str = "##") -> str:
    m = re.search(
        rf"^{nivel} {re.escape(titulo)}\n(.*?)(?=^#{{2,{len(nivel)}}} |\Z)",
        GUION, re.MULTILINE | re.DOTALL,
    )
    assert m, f"falta la sección «{titulo}»"
    return m.group(1)


def _bloque(nombre: str) -> str:
    return _seccion(nombre, "###")


def _plantilla(nombre: str) -> str:
    """Las líneas del bloque que son el mensaje (sin las notas en viñeta)."""
    cuerpo = _bloque(nombre)
    parrafos = [p for p in cuerpo.split("\n\n") if p.strip()]
    # El mensaje es el párrafo que no empieza con viñeta y que tiene emojis
    # de opción o es el más «WhatsApp»: el que no es prosa de instrucciones.
    candidatos = [p for p in parrafos if not p.lstrip().startswith("-")
                  and not p.lstrip().startswith(("Cuando", "Si ", "Para el primer", "Para quien",
                                                 "El protocolo", "**"))
                  and ("1️⃣" in p or "🙌" in p or "✅" in p or "👋" in p or "📅" in p)]
    assert candidatos, f"el bloque {nombre} no tiene mensaje"
    return candidatos[0]


class TestTamañoYCarga:
    def test_cabe_en_el_tope(self):
        assert len(GUION) <= 38_000

    def test_el_motor_lo_carga_por_su_context_key(self):
        assert llm_engine._load_context("demo_viajes_c").strip() == GUION

    def test_la_ruta_es_la_del_paquete(self):
        assert RUTA_MD_C.name == "demo_viajes_c.md"


class TestSinCifras:
    def test_ningun_monto(self):
        assert re.findall(r"\$\s?\d", GUION) == []
        assert re.findall(r"\b\d{1,3}(?:\.\d{3})+\b", GUION) == []
        assert re.findall(r"(?i)\b\d+\s*(?:mil|k|millones?)\b", GUION) == []

    def test_ningun_porcentaje(self):
        assert re.findall(r"\d+\s*%", GUION) == []

    def test_la_promo_inexistente_no_esta(self):
        assert "350" not in GUION
        assert "lunes a jueves" not in _seccion("Protocolo especial: pasar a un asesor")


class TestBienvenida:
    def test_no_pide_el_nombre_ni_trae_itinerario(self):
        bienvenida = _plantilla("/bienvenida")
        assert not llm_engine._PIDE_EL_NOMBRE.search(bienvenida)
        assert not re.search(r"(?i)nombre", bienvenida)
        for dia in ("Sábado", "Domingo", "Caimanera", "Carabobo"):
            assert dia not in bienvenida

    def test_saludo_de_la_franja_del_sistema(self):
        """Análisis: 357 de 1.056 saludos del bot 1 decían «buen día» de noche.
        QA 10-oct: el saludo sale de «Momento del día», no «¡Hola!» a secas."""
        assert not re.search(r"(?i)buen(?:os)? d[ií]as?|buenas (?:tardes|noches)",
                             _plantilla("/bienvenida"))
        assert "<saludo del momento del día>" in _plantilla("/bienvenida")
        assert "*Momento del día*" in _seccion("Cómo escribes")
        assert '"¡Hola!" a secas' not in GUION

    def test_la_bienvenida_dice_de_donde_sale(self):
        assert "*Estación Universidad*" in _plantilla("/bienvenida")

    def test_el_menu_de_meses_lo_da_el_sistema(self):
        cuerpo = _bloque("/bienvenida")
        assert "Meses con salidas (datos del sistema)" in cuerpo
        assert "La persona ya dijo el" in cuerpo
        meses = r"(?i)\b(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\b"
        assert not re.search(meses, cuerpo)

    def test_la_frase_vieja_del_nombre_no_aparece(self):
        assert not re.search(r"(?i)con qui[eé]n tengo el gusto", GUION)


class TestBiblioteca:
    @pytest.mark.parametrize("nombre", CON_OPCIONES + SIN_OPCIONES + ("/bienvenida", "/lo_consulto"))
    def test_el_bloque_existe(self, nombre):
        assert _bloque(nombre).strip()

    @pytest.mark.parametrize("nombre", CON_OPCIONES)
    def test_cierra_con_opciones_que_el_motor_reconoce(self, nombre):
        mensaje = _plantilla(nombre)
        opciones = recortes_turno.opciones_numeradas(mensaje)
        assert 2 <= len(opciones) <= 5, (nombre, opciones)
        assert recortes_turno.cierra_con_opciones(mensaje), nombre
        # Cada opción en su propio renglón.
        for linea in mensaje.splitlines():
            assert len(re.findall(r"\d️⃣", linea)) <= 1, linea

    @pytest.mark.parametrize("nombre", ("/reserva", "/pago"))
    def test_los_que_van_sin_opciones_caen_en_la_excepcion_del_motor(self, nombre):
        assert llm_engine._SIN_OPCIONES_RE.search(_plantilla(nombre)), nombre

    def test_la_cotizacion_dice_total(self):
        assert llm_engine._TOTAL_RE.search(_plantilla("/cotizacion"))

    def test_el_menu_de_cliente_activa_la_etapa_cliente(self):
        assert llm_engine._es_menu_cliente(_plantilla("/cliente"))

    def test_la_reserva_es_el_unico_lugar_donde_se_pide_el_nombre(self):
        assert "nombre completo" in _plantilla("/reserva")
        assert "registrar_intencion" in _bloque("/reserva")
        for nombre in ("/bienvenida", "/fechas", "/hotel", "/personas", "/cotizacion", "/apartar"):
            assert not re.search(r"(?i)nombre", _plantilla(nombre)), nombre

    def test_el_pago_entrega_al_asesor(self):
        """CEO, 2026-10-21: el bot llega hasta los datos y las formas de pago;
        el comprobante y la confirmación son del asesor."""
        cuerpo = _bloque("/pago")
        assert "`listo_para_reservar`" in cuerpo and "Ahí termina tu parte" in cuerpo
        assert '`tipo: "datos"`' in cuerpo
        assert "/transferencia" not in GUION and "/pago_seguimiento" not in GUION

    def test_el_anticipo_sale_del_sistema(self):
        cuerpo = _bloque("/apartar")
        assert "Anticipo y saldo (datos del sistema)" in cuerpo
        assert "no lo adivines" in cuerpo


class TestSecciones:
    @pytest.mark.parametrize("titulo", [
        "Respuestas cerradas", "El embudo", "Biblioteca de bloques", "Protocolos",
        "Protocolo especial: pasar a un asesor", "El comprobante", "Atención al cliente",
        "Cuándo avisar que hay intención de compra", "Cómo se cotiza",
    ])
    def test_existe(self, titulo):
        assert _seccion(titulo).strip()

    def test_el_comprobante_fuera_de_pago_escala_con_su_motivo(self):
        cuerpo = _seccion("El comprobante")
        assert 'motivo: "comprobante de pago"' in cuerpo

    def test_atencion_al_cliente_usa_los_temas_del_motor(self):
        cuerpo = _seccion("Atención al cliente")
        for tema in llm_engine._TEMAS_CLIENTE:
            assert f"`{tema}`" in cuerpo

    def test_el_horario_no_esta_escrito_en_el_guion(self):
        """El horario lo da el sistema (y el aviso de ausencia la config): el
        guion no calcula horarios ni los repite."""
        assert "Horario de los asesores (datos del sistema)" in GUION
        assert not re.search(r"(?i)lunes a viernes", GUION)
        assert not re.search(r"\b(?:18|13):00\b", GUION)

    def test_las_opciones_van_en_el_mismo_mensaje_que_la_pregunta(self):
        cuerpo = _seccion("Respuestas cerradas")
        assert "en el mismo mensaje que la pregunta" in cuerpo
        assert "1️⃣ 2️⃣ 3️⃣ 4️⃣ 5️⃣" in cuerpo


class TestTono:
    def test_whatsapp_no_tiene_subrayado(self):
        assert "WhatsApp no tiene subrayado" in _seccion("Cómo escribes")

    def test_la_sena_solo_aparece_para_prohibirla(self):
        assert len(re.findall(r"\bseña\b", GUION)) == 1

    def test_duracion_no_escrita(self):
        assert not re.search(r"(?i)\b[2-5]\s*(?:d[ií]as|noches)\b(?!\s*h[aá]biles)", GUION)


class TestOrdenDelMensaje:
    @pytest.mark.parametrize("nombre", CON_OPCIONES)
    def test_la_ultima_linea_es_una_opcion(self, nombre):
        """La pregunta arriba, las opciones debajo y nada después: lo que
        queda abajo es lo que la persona ve al abrir el chat."""
        ultima = _plantilla(nombre).rstrip().splitlines()[-1]
        assert re.match(r"\d️⃣", ultima), (nombre, ultima)


class TestAjustesDelAnalisis:
    """Hallazgos de las 1.124 conversaciones reales del bot 1 (10-oct-2026)."""

    def test_el_orden_es_mes_salidas_hotel(self):
        """El 74 % contesta «¿cuál hotel?» pero solo el 17 % elige uno: el
        hotel va después del precio, con fotos y videos como opción."""
        embudo = _seccion("El embudo")
        assert embudo.index("*/fechas*") < embudo.index("*/hotel*") < embudo.index("*/personas*")
        assert "Ver fotos y videos 🎥" in _plantilla("/hotel")
        assert "desde *<precio>*" in _plantilla("/fechas")

    def test_el_precio_llega_en_el_primer_mensaje_tras_el_mes(self):
        assert "En tu primer mensaje después de que elige el\nmes ya van las salidas con su precio." in _seccion("El embudo")
        assert "Nunca respondas \"depende del mes\" sin dar un precio" in _seccion("Preguntas frecuentes")

    def test_el_que_vuelve_no_recibe_la_bienvenida_larga(self):
        regreso = _plantilla("/bienvenida_regreso")
        assert regreso.startswith("¡Hola de nuevo!")
        assert "Soy *Luisa*" not in regreso
        assert "La última vez miraste" in regreso

    def test_lo_consulto_es_guia_y_no_frase(self):
        """QA del bot 2: la frase escrita se copió 12 de 12 veces."""
        cuerpo = _bloque("/lo_consulto")
        assert "no es una frase para copiar" in cuerpo
        # QA 10-oct: el ejemplo literal se copió 6 de 6; ya no hay ejemplo.
        assert "Por ejemplo" not in cuerpo and "Lo hablan con calma" not in GUION
        assert "¿Te escribo mañana para ver qué decidieron?" not in GUION
        assert "`finalizar_conversacion`" in cuerpo and "`no_responder`" in cuerpo
        assert '"gracias" u "ok"' in cuerpo  # tras el precio no es despedida

    def test_siempre_hay_cupo(self):
        """Decisión del CEO (10-oct): las salidas de la consulta tienen cupo."""
        assert "tienen cupo" in _bloque("/apartar")
        assert not re.search(r"(?i)sujeto a disponibilidad|el cupo lo confirma|confirma el cupo", GUION)
        assert "Si hay cupo en una salida concreta" not in GUION

    def test_la_oficina_como_senal_de_confianza_en_el_pago(self):
        pago = _plantilla("/pago")
        assert "Bosque Plaza" in pago
        assert "Oficina y confianza" in _seccion("Preguntas frecuentes")

    def test_la_llamada_se_ofrece_sin_discutir(self):
        assert 'motivo: "pide llamada"' in _seccion("Preguntas frecuentes")
        assert "o que lo llamen (sin discutir, de una)" in _seccion("Protocolo especial: pasar a un asesor")

    def test_fuera_de_horario_sigue_vendiendo(self):
        assert "**Fuera del horario de los asesores**" in _seccion("Protocolos")

    def test_no_se_disculpa_sin_motivo_ni_deja_huecos(self):
        assert "No te disculpas si no te equivocaste" in _seccion("Cómo escribes")
        assert "ningún `<…>` llega al cliente" in _seccion("Biblioteca de bloques")

    def test_entre_semana_sin_contradecirse(self):
        assert "No cambias de respuesta sin una consulta nueva" in GUION


class TestAjustesQABedrock:
    """QA del bot 3 contra Bedrock (10-oct-2026)."""

    def test_pregunta_desconocida_escala_en_el_mismo_turno(self):
        duda = _bloque("/duda")
        assert "no la contestas ni la adivinas" in duda
        assert "`escalar_a_asesor` en ese mismo turno" in duda
        assert "**Prometer una confirmación es escalar**" in _seccion("Protocolo especial: pasar a un asesor")

    def test_cliente_con_pregunta_concreta_va_directo(self):
        cuerpo = _seccion("Atención al cliente")
        assert "**Si ya dijo qué necesita, se lo respondes directo**" in cuerpo
        assert "siempre en el mismo mensaje, nunca en dos" in cuerpo
        assert "no dijo qué necesita" in _bloque("/cliente")

    def test_confianza_con_las_dos_referencias_y_sin_adjetivos(self):
        faq = _seccion("Preguntas frecuentes")
        assert "**sus dos\n  referencias**" in faq
        assert "*Jardín Botánico*" in faq and "*Universidad*" in faq
        assert "No afirmes nada que no esté en este documento" in faq

    def test_el_pago_manda_medios_en_el_mismo_bloque(self):
        cuerpo = _bloque("/pago")
        assert "El sistema le envía la imagen de formas de pago" in " ".join(cuerpo.split())
        assert "en este mismo turno" in " ".join(cuerpo.split())
        assert "**Lo que ya te dio no se vuelve a pedir ni a confirmar**" in cuerpo

    def test_cotizacion_segun_cuantos_viajan(self):
        """La múltiple es para 3 o más del mismo grupo (CEO, 2026-10-21)."""
        cotizacion = _bloque("/cotizacion")
        assert "**3 o más personas** (las dos acomodaciones)" in cotizacion
        assert "**1 o 2 personas** (solo doble)" in cotizacion

    def test_ninos_solo_de_la_consulta_y_con_opciones(self):
        personas = _bloque("/personas")
        assert "¿Me escribes los adultos" not in GUION
        assert "1️⃣ 1\n  adulto" in personas
        # R3: el menú de edades sale del bloque del sistema, copiado tal cual,
        # y no se repregunta lo que ya dijo.
        assert "*Edades de niños (datos del sistema)*" in personas
        assert "no le preguntas nada de eso otra vez" in personas
        assert "**Lo que pagan los niños sale solo de la línea de niños" in personas
        assert "ningún valor de\nniño sale de tu memoria" in GUION
