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

    def test_una_fecha_ya_pasada_se_rechaza_de_frente(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="agosto", fecha="2026-08-06", hoy=HOY
        )
        assert "ya pasó" in out
        assert "459" not in out

    def test_al_final_de_la_temporada_el_mes_queda_vacio(self):
        planes = tarifario.planes_de("piedra_mar", 8, hoy=date(2027, 3, 1))
        assert planes == []


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
        assert "NO hay salidas publicadas" in out
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
