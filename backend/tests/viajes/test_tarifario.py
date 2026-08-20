"""Pruebas de `services/tarifario.py` — los precios del bot de viajes.

Lo que se protege aquí es lo que se paga caro si falla: que el bot no ofrezca
una salida que ya pasó, que no mande el flyer de otro mes, que Bohíos cobre lo
mismo que Amor de Dios y que una fecha sin salida NO termine en un pase al
asesor sin darle opciones al cliente.

La fecha se inyecta (`hoy=`) en vez de usar la del sistema: si no, la suite
empieza a fallar sola cuando pase la última salida del tarifario.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import tarifario

CFG = LLM_CONFIG

# Mitad de la temporada: quedan salidas por delante y ya quedaron unas atrás.
HOY = date(2026, 8, 19)


class TestNormalizacion:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("Amor de Dios", "amor_de_dios"),
            ("el amor de dios", "amor_de_dios"),
            ("Hotel Amor de Dios", "amor_de_dios"),
            ("Bohíos", "bohios"),
            ("bohios", "bohios"),
            ("Piedra Mar", "piedra_mar"),
            ("piedramar", "piedra_mar"),
            ("en el hotel piedra mar por favor", "piedra_mar"),
        ],
    )
    def test_reconoce_los_tres_hoteles(self, texto, esperado):
        assert tarifario.normalizar_hotel(texto) == esperado

    def test_hotel_desconocido_es_none(self):
        assert tarifario.normalizar_hotel("Hotel Decameron") is None

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("septiembre", 9), ("Septiembre", 9), ("setiembre", 9),
            ("diciembre", 12), ("enero", 1),
            ("2026-09-15", 9), ("12", 12),
            ("me sirve en octubre", 10),
        ],
    )
    def test_reconoce_el_mes(self, texto, esperado):
        assert tarifario.normalizar_mes(texto) == esperado


class TestNoVenderElPasado:
    """La regla que más plata cuesta: una salida vencida no se ofrece."""

    def test_las_salidas_de_agosto_ya_corridas_no_aparecen(self):
        planes = tarifario.planes_de("amor_de_dios", 8, hoy=HOY)
        fechas = [p["fecha"] for p in planes]
        assert not any("AGOSTO 06" in f for f in fechas)
        assert not any("AGOSTO 14" in f for f in fechas)
        assert any("AGOSTO 21" in f for f in fechas)
        assert any("AGOSTO 28" in f for f in fechas)

    def test_una_fecha_ya_pasada_se_avisa_pero_no_corta_la_venta(self):
        """Avisa que venció **y** sigue mostrando el mes.

        Antes cortaba en seco y el bot se quedaba preguntando «¿para cuál otra
        fecha?» sin ofrecer nada — el hallazgo 4 de la prueba del 19-ago-2026.
        """
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="agosto", fecha="2026-08-06", hoy=HOY
        )
        assert "ya pasó" in out
        assert "AGOSTO 21 AL 24" in out          # las que sí quedan
        assert "AGOSTO 06" not in out            # la vencida no se lista

    def test_al_final_de_la_temporada_el_mes_queda_vacio(self):
        planes = tarifario.planes_de("piedra_mar", 8, hoy=date(2027, 3, 1))
        assert planes == []


class TestZonaHoraria:
    """El backend corre en UTC; el negocio vende en Colombia.

    Sin esto, entre las 7 pm y la medianoche colombiana el servidor ya cree que
    es mañana y el bot deja de ofrecer una salida que todavía se puede vender.
    Es el mismo error que tumbó el CI el 19-ago-2026 en la suite de mascotas.
    """

    def test_el_hoy_por_defecto_es_el_de_colombia(self):
        from datetime import datetime, timedelta, timezone

        esperado = datetime.now(timezone(timedelta(hours=-5))).date()
        assert tarifario.hoy_colombia() == esperado

    def test_una_salida_de_hoy_todavia_se_ofrece(self):
        """Hoy mismo aún es vendible: el corte es `< hoy`, no `<= hoy`."""
        planes = tarifario.planes_de("piedra_mar", 12, hoy=date(2026, 12, 8))
        assert any("DICIEMBRE 08 AL 11" in p["fecha"] for p in planes)


class TestElAnioQueElModeloNoSabe:
    """Hallazgos de la prueba del 19-ago-2026 (guiones G06 y G12).

    El modelo no sabe en qué año vive: al pedirle una fecha exacta escribía
    `2025-01-15` para «el 15 de enero». La consulta respondía «esa fecha ya
    pasó» a clientes que querían viajar en fechas futuras y vendibles — y le
    pega justo a los de mayor intención, los que ya escogieron día.
    """

    def test_el_18_de_diciembre_no_es_del_ano_pasado(self):
        """El caso exacto que costó una venta en la prueba."""
        out = tarifario.consultar(
            CFG, hotel="Piedra Mar", mes="diciembre", fecha="2025-12-18", hoy=HOY
        )
        assert "ya pasó" not in out
        assert "DICIEMBRE 18 AL 21" in out
        assert "la fecha que pidió" in out

    def test_enero_se_resuelve_al_ano_entrante(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="enero", fecha="2025-01-15", hoy=HOY
        )
        assert "ya pasó" not in out
        assert "ENERO 15 AL 18" in out

    def test_una_fecha_futura_explicita_se_respeta(self):
        """Solo se corrige lo que está demostrablemente mal."""
        f = date(2026, 12, 18)
        assert tarifario.resolver_fecha(f, 12, HOY) == f

    def test_una_fecha_de_verdad_vencida_sigue_marcandose(self):
        """El 6 de agosto sí pasó, y agosto del año entrante no existe en el
        tarifario: no hay reinterpretación válida, así que se avisa."""
        assert tarifario.resolver_fecha(date(2025, 8, 6), 8, HOY) == date(2025, 8, 6)
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="agosto", fecha="2025-08-06", hoy=HOY
        )
        assert "ya pasó" in out

    def test_29_de_febrero_no_revienta(self):
        assert tarifario.resolver_fecha(date(2025, 2, 29 - 1), 2, HOY) is not None


class TestFechaVencidaOfreceAlternativas:
    """Hallazgo 4: cortaba en seco con «¿para cuál otra fecha?» y sin opciones."""

    def test_lista_las_salidas_que_quedan_en_ese_mes(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="agosto", fecha="2025-08-06", hoy=HOY
        )
        assert "AGOSTO 21 AL 24" in out and "AGOSTO 28 AL 31" in out
        assert "$459.000" in out

    def test_le_prohibe_preguntar_sin_dar_opciones(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="agosto", fecha="2025-08-06", hoy=HOY
        )
        assert "NO le preguntes" in out


class TestMesSinSalidas:
    """Hallazgo 3: el bot dedujo que julio «sí tiene» salidas entre semana."""

    def test_no_ofrece_la_promo_de_entre_semana(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="julio", hoy=HOY
        )
        assert "$350.000" not in out
        assert "NO aplica a un mes sin fechas publicadas" in out

    def test_la_promo_si_sale_en_un_mes_publicado(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY
        )
        assert "$350.000" in out

    def test_los_meses_van_del_mas_proximo_al_mas_lejano(self):
        """Hallazgo 5: recorriendo enero→diciembre, «Enero» salía de primero en
        agosto como si fuera lo más cercano, y el bot terminó omitiéndolo."""
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="julio", hoy=HOY)
        linea = [l for l in out.split("\n") if "Meses que SÍ tienen" in l][0]
        assert linea.index("Agosto") < linea.index("Diciembre") < linea.index("Enero")


class TestBohios:
    def test_cobra_exactamente_lo_mismo_que_amor_de_dios(self):
        a = tarifario.planes_de("amor_de_dios", 9, hoy=HOY)
        b = tarifario.planes_de("bohios", 9, hoy=HOY)
        assert [(p["fecha"], p["multiple"], p["doble"]) for p in a] == \
               [(p["fecha"], p["multiple"], p["doble"]) for p in b]

    def test_usa_el_flyer_de_amor_de_dios(self):
        assert tarifario.clave_imagen(CFG, "bohios", 9) == \
               tarifario.clave_imagen(CFG, "amor_de_dios", 9) == \
               "tarifario_amordios_ago_nov"

    def test_avisa_que_la_imagen_sale_a_nombre_de_otro_hotel(self):
        """Sin este aviso el cliente cree que le mandaron el hotel equivocado."""
        out = tarifario.consultar(CFG, hotel="Bohíos", mes="septiembre", hoy=HOY)
        assert "tarifario_amordios_ago_nov" in out
        assert "Amor de Dios" in out and "aplican igual para Bohíos" in out

    def test_mandar_el_flyer_no_es_opcional(self):
        """En la re-corrida el bot listó los precios de Bohíos en texto y no
        mandó la imagen: la instrucción era sugerencia, ahora es obligación."""
        out = tarifario.consultar(CFG, hotel="Bohíos", mes="octubre", hoy=HOY)
        assert "OBLIGATORIO" in out
        assert "No basta con listar los precios en texto" in out


class TestLaImagenCorrespondeAlMes:
    @pytest.mark.parametrize(
        "hotel,mes,clave",
        [
            ("amor_de_dios", 8, "tarifario_amordios_ago_nov"),
            ("amor_de_dios", 11, "tarifario_amordios_ago_nov"),
            ("amor_de_dios", 12, "tarifario_amordios_dic_ene"),
            ("amor_de_dios", 1, "tarifario_amordios_dic_ene"),
            ("piedra_mar", 8, "tarifario_piedramar_jul_oct"),
            ("piedra_mar", 10, "tarifario_piedramar_jul_oct"),
            ("piedra_mar", 11, "tarifario_piedramar_nov_ene"),
            ("piedra_mar", 1, "tarifario_piedramar_nov_ene"),
        ],
    )
    def test_cada_mes_trae_su_flyer(self, hotel, mes, clave):
        assert tarifario.clave_imagen(CFG, hotel, mes) == clave

    def test_un_mes_sin_flyer_no_inventa_uno(self):
        assert tarifario.clave_imagen(CFG, "amor_de_dios", 3) is None

    def test_las_claves_del_catalogo_existen_de_verdad(self):
        """Si alguien renombra una imagen y olvida el catálogo, el bot manda un
        404 por WhatsApp."""
        for hotel in ("amor_de_dios", "piedra_mar"):
            for mes in range(1, 13):
                clave = tarifario.clave_imagen(CFG, hotel, mes)
                if clave is not None:
                    assert clave in CFG["media"], clave


class TestFechaSinSalida:
    """Pedido del CEO: si no hay salida ese día, no se escala — se ofrecen las
    cercanas con su precio."""

    def test_ofrece_las_cercanas_y_prohibe_escalar(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre",
            fecha="2026-09-20", hoy=HOY,
        )
        assert "no hay salida que arranque el 2026-09-20" in out
        assert "NO escales" in out
        assert "SEPTIEMBRE 18 AL 21" in out and "SEPTIEMBRE 25 AL 28" in out

    def test_las_dos_cercanas_son_dos_dias_distintos(self):
        """Varios planes arrancan el mismo día (el estándar y el de Barú): sin
        deduplicar, «las más cercanas» eran el mismo día ofrecido dos veces."""
        out = tarifario.consultar(
            CFG, hotel="Piedra Mar", mes="septiembre",
            fecha="2026-09-20", hoy=HOY,
        )
        linea = [l for l in out.split("\n") if "Las más cercanas" in l][0]
        assert linea.count("SEPTIEMBRE 18") == 1, linea

    def test_una_fecha_exacta_queda_marcada(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre",
            fecha="2026-09-18", hoy=HOY,
        )
        assert "la fecha que pidió" in out
        assert "NO escales" not in out

    def test_un_mes_sin_salidas_en_ese_hotel_ofrece_los_que_si(self):
        """Amor de Dios no publicó julio; Piedra Mar sí."""
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="julio", hoy=date(2026, 6, 1)
        )
        assert "NO hay NADA publicado" in out
        assert "no escales todavía" in out.lower()
        assert "Agosto" in out


class TestRespuestaAlModelo:
    def test_sin_hotel_compara_los_dos_tarifarios(self):
        out = tarifario.consultar(CFG, mes="septiembre", hoy=HOY)
        assert "Amor de Dios —" in out and "Piedra Mar —" in out
        assert "Bohíos cobra exactamente lo mismo" in out

    def test_trae_los_precios_reales_del_excel(self):
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY)
        assert "$459.000" in out and "$505.000" in out

    def test_recuerda_la_promo_de_entre_semana_de_cada_hotel(self):
        amor = tarifario.consultar(CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY)
        piedra = tarifario.consultar(CFG, hotel="Piedra Mar", mes="septiembre", hoy=HOY)
        assert "$350.000" in amor and "$389.000" not in amor
        assert "$389.000" in piedra and "$350.000" not in piedra

    def test_prohibe_mandar_el_excel_en_cada_respuesta(self):
        out = tarifario.consultar(CFG, mes="diciembre", hoy=HOY)
        assert "NUNCA le mandes el Excel" in out

    def test_sin_mes_pide_el_mes_en_vez_de_adivinar(self):
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="", hoy=HOY)
        assert "en qué mes" in out
        assert "$" not in out

    def test_hotel_que_no_existe_no_se_confunde_con_uno_real(self):
        out = tarifario.consultar(CFG, hotel="Hotel Hilton", mes="septiembre", hoy=HOY)
        assert "No reconozco el hotel" in out
        assert "$" not in out
