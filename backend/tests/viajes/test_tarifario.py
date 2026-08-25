"""Pruebas de `services/tarifario.py` — los precios del bot de viajes.

Lo que se protege aquí es lo que se paga caro si falla: que el bot no ofrezca
una salida que ya pasó, que no mande el flyer de otro mes, que Bohíos cobre lo
mismo que Amor de Dios y que una fecha sin salida NO termine en un pase al
asesor sin darle opciones al cliente.

La fecha se inyecta (`hoy=`) en vez de usar la del sistema: si no, la suite
empieza a fallar sola cuando pase la última salida del tarifario.
"""
from __future__ import annotations

import re
from datetime import date

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import tarifario

CFG = LLM_CONFIG

# Mitad de la temporada: quedan salidas por delante y ya quedaron unas atrás.
HOY = date(2026, 8, 19)

# Meses que la temporada publica, de agosto a enero.
MESES_PUBLICADOS = (8, 9, 10, 11, 12, 1)


def pesos(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def minimo_crudo(hotel: str, mes=None, hoy: date = HOY):
    """El mínimo en múltiple leído del JSON, sin pasar por el código que se prueba.

    A propósito no se usa `tarifario.planes_vigentes`: si el filtro por `hoy` o
    la selección del mínimo se rompieran, un test que reusara esas funciones se
    rompería igual y no habría manera de notarlo. Y a propósito tampoco se
    escriben las cifras a mano: es el mismo error que se está arreglando.
    """
    valores = [
        p["multiple"]
        for p in tarifario._datos()["planes"]
        if hotel in p["hoteles"]
        and (mes is None or p["mes"] == mes)
        and date.fromisoformat(p["inicio"]) >= hoy
    ]
    return min(valores) if valores else None


def precios_publicados() -> set:
    """Todo valor en pesos que el tarifario puede honrar (múltiple y doble)."""
    return {
        v
        for p in tarifario._datos()["planes"]
        for v in (p["multiple"], p["doble"])
    }


def cifras_de(texto: str) -> set:
    """Los montos en pesos que aparecen en una respuesta de la herramienta."""
    return {int(c.replace(".", "")) for c in re.findall(r"\$([\d.]+)", texto)}


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
        assert "NO aplica a un mes sin fechas publicadas" in out
        # Julio no tiene NADA en este hotel: la respuesta no puede traer ni una
        # sola cifra, venga de donde venga. Antes traía «desde $350.000».
        assert "$" not in out

    def test_la_promo_si_sale_en_un_mes_publicado(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY
        )
        assert "«desde» de Septiembre" in out
        assert pesos(minimo_crudo("amor_de_dios", 9)) in out

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

    def test_el_desde_de_cada_hotel_es_el_suyo_y_no_el_del_otro(self):
        amor = tarifario.consultar(CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY)
        piedra = tarifario.consultar(CFG, hotel="Piedra Mar", mes="septiembre", hoy=HOY)
        min_amor = pesos(minimo_crudo("amor_de_dios", 9))
        min_piedra = pesos(minimo_crudo("piedra_mar", 9))
        assert min_amor in amor and min_piedra not in amor
        assert min_piedra in piedra and min_amor not in piedra

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


class TestElDesdeEsDelMesQuePidioElCliente:
    """Bug del CEO (Sprint 24, F7).

    Un cliente dijo que le interesaba **septiembre**, preguntó precios, y el bot
    le contestó un «desde» que era el mínimo de TODOS los meses. No lo inventó:
    la herramienta le pegaba al final de la respuesta dos líneas con `$350.000`
    y `$389.000` escritos a mano, y el modelo las leía como el «desde» del mes
    que tenía delante. En septiembre eso son $109.000 de diferencia contra el
    precio real — una cotización que revienta cuando el cliente va a pagar.
    """

    @pytest.mark.parametrize("hotel,clave", [
        ("Amor de Dios", "amor_de_dios"),
        ("Piedra Mar", "piedra_mar"),
        ("Bohíos", "bohios"),
    ])
    @pytest.mark.parametrize("mes,num", [
        ("septiembre", 9), ("octubre", 10), ("noviembre", 11),
        ("diciembre", 12), ("enero", 1),
    ])
    def test_el_desde_coincide_con_el_minimo_real_del_mes(self, hotel, clave, mes, num):
        out = tarifario.consultar(CFG, hotel=hotel, mes=mes, hoy=HOY)
        esperado = minimo_crudo(clave, num)
        linea = [l for l in out.split("\n") if "«desde» de" in l][0]
        assert pesos(esperado) in linea, linea

    def test_septiembre_no_devuelve_el_desde_de_diciembre(self):
        """El test que reproduce el reporte, con dos meses de mínimo distinto.

        Septiembre arranca en $459.000 y diciembre en $369.000: si la respuesta
        de septiembre trae la cifra de diciembre, es el bug otra vez.
        """
        min_sep = minimo_crudo("amor_de_dios", 9)
        min_dic = minimo_crudo("amor_de_dios", 12)
        assert min_sep != min_dic, "sin mínimos distintos este test no prueba nada"

        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY)
        assert pesos(min_sep) in out
        assert pesos(min_dic) not in out

    def test_diciembre_no_devuelve_el_desde_de_septiembre(self):
        """El mismo cruce en el otro sentido: no es que se citara siempre el
        más barato, es que se citaba uno fijo pasara lo que pasara."""
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="diciembre", hoy=HOY)
        linea = [l for l in out.split("\n") if "«desde» de" in l][0]
        assert pesos(minimo_crudo("amor_de_dios", 12)) in linea
        assert pesos(minimo_crudo("amor_de_dios", 9)) not in linea

    def test_un_mes_sin_salidas_entre_semana_no_trae_un_desde_falso(self):
        """Septiembre solo publica salidas de viernes.

        La línea de la promo de «lunes con jueves» tiene que quedar SIN cifra:
        el «desde» de entre semana de otro mes en la respuesta de septiembre es
        exactamente por donde entró el bug la primera vez.
        """
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY)
        linea = [l for l in out.split("\n") if "Entre semana" in l][0]
        assert "no hay ninguna publicada" in linea
        assert "$" not in linea, linea

    def test_un_mes_con_salidas_entre_semana_da_el_minimo_de_esas(self):
        """Diciembre sí publica salidas de lunes a jueves."""
        out = tarifario.consultar(CFG, hotel="Piedra Mar", mes="diciembre", hoy=HOY)
        linea = [l for l in out.split("\n") if "Entre semana" in l][0]
        entre_semana = [
            p["multiple"]
            for p in tarifario._datos()["planes"]
            if "piedra_mar" in p["hoteles"] and p["mes"] == 12
            and date.fromisoformat(p["inicio"]).weekday() <= 3
        ]
        assert pesos(min(entre_semana)) in linea, linea
        assert "No aplica para lunes festivos" in linea

    def test_un_mes_sin_salidas_publicadas_no_reintroduce_lo_de_julio(self):
        """Amor de Dios no publicó julio.

        El comentario de la función lo advierte: la promo de entre semana se
        agregaba siempre y el bot la usó para concluir que julio «sí tiene
        salidas». Calcular el «desde» no puede resucitar ese error: sin filas
        no hay línea de «desde», ni de entre semana, ni cifra alguna.
        """
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="julio", hoy=HOY)
        assert "«desde» de" not in out
        assert "Entre semana" not in out
        assert cifras_de(out) == set()

    def test_solo_el_hotel_que_si_publica_el_mes_recibe_su_desde(self):
        """Consultando los dos hoteles en julio, Piedra Mar sí publica y Amor de
        Dios no: la línea de Amor de Dios no puede aparecer."""
        out = tarifario.consultar(CFG, mes="julio", hoy=date(2026, 6, 1))
        assert "Piedra Mar — «desde» de Julio" in out
        assert "Amor de Dios y Bohíos — «desde»" not in out

    def test_el_minimo_no_cuenta_salidas_que_ya_pasaron(self):
        """Las dos salidas de $369.000 de diciembre son el 08 y el 14.

        Consultando el 16 de diciembre ya pasaron las dos, y el «desde» tiene
        que subir solo. Un mínimo calculado sobre una fecha vencida es la misma
        promesa incumplible, nada más que por otra puerta.
        """
        tarde = date(2026, 12, 16)
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes="diciembre", hoy=tarde)
        linea = [l for l in out.split("\n") if "«desde» de" in l][0]
        assert pesos(minimo_crudo("amor_de_dios", 12, hoy=tarde)) in linea
        assert pesos(minimo_crudo("amor_de_dios", 12, hoy=HOY)) not in linea


class TestNingunaCifraSeInventa:
    """El arreglo que cubre la clase entera de bug, no solo el $350.000.

    Cualquier precio que salga de esta herramienta tiene que existir como fila
    del tarifario. Si mañana alguien vuelve a pegar una cifra a mano en un
    `f"..."` —da igual cuál— este test la caza.
    """

    @pytest.mark.parametrize("hotel", ["", "Amor de Dios", "Piedra Mar", "Bohíos"])
    @pytest.mark.parametrize("mes", [
        "julio", "agosto", "septiembre", "octubre",
        "noviembre", "diciembre", "enero",
    ])
    def test_toda_cifra_de_la_respuesta_existe_en_el_tarifario(self, hotel, mes):
        out = tarifario.consultar(CFG, hotel=hotel, mes=mes, hoy=HOY)
        inventadas = cifras_de(out) - precios_publicados()
        assert not inventadas, f"{hotel or 'ambos'}/{mes}: {sorted(inventadas)}"

    def test_el_350000_que_nunca_existio_ya_no_aparece(self):
        """El CEO lo reportó aparte: «el precio mínimo no es 350mil sino 369mil».

        $350.000 no era el mínimo de ningún mes ni de la temporada — no estaba
        en ninguna fila del Excel. Era una cifra de una temporada vieja.
        """
        assert 350_000 not in precios_publicados()
        for mes in ("agosto", "septiembre", "octubre", "noviembre", "diciembre",
                    "enero"):
            for hotel in ("", "Amor de Dios", "Piedra Mar", "Bohíos"):
                out = tarifario.consultar(CFG, hotel=hotel, mes=mes, hoy=HOY)
                assert "$350.000" not in out, f"{hotel}/{mes}"

    def test_el_minimo_de_la_temporada_sale_de_los_datos(self):
        """$369.000 en Amor de Dios y Bohíos, $389.000 en Piedra Mar.

        Se derivan del JSON: si el CEO manda un Excel nuevo, el test sigue
        valiendo. Lo que se fija aquí es la relación, no las cifras — Piedra Mar
        es más caro que Amor de Dios, y Bohíos cobra igual que Amor de Dios.
        """
        inicio = date(2026, 7, 1)
        amor = minimo_crudo("amor_de_dios", hoy=inicio)
        bohios = minimo_crudo("bohios", hoy=inicio)
        piedra = minimo_crudo("piedra_mar", hoy=inicio)
        assert amor == bohios
        assert amor < piedra
        # Y el JSON que lee el bot declara esos mismos mínimos en sus notas.
        notas = " ".join(tarifario._datos()["notas"])
        assert pesos(amor) in notas and pesos(piedra) in notas
        assert "350.000" not in notas


class TestBusquedaPorPresupuesto:
    """F8: del precio a las fechas, que es como pregunta media clientela.

    «Tengo 450 mil, ¿qué me alcanza?», «¿hay algo más económico?», «¿qué tienes
    por 300?». Casi ninguna es un precio exacto: son techos y presupuestos, así
    que se busca por `multiple <= tope` y no por igualdad.
    """

    @pytest.mark.parametrize("texto,esperado", [
        ("450 mil", 450_000),
        ("450000", 450_000),
        ("$450.000", 450_000),
        ("tengo 450", 450_000),
        ("menos de 400", 400_000),
        ("400k", 400_000),
        ("1.200.000", 1_200_000),
        ("algo barato", None),
        ("", None),
    ])
    def test_entiende_como_habla_la_gente_de_plata(self, texto, esperado):
        assert tarifario.normalizar_presupuesto(texto) == esperado

    def test_un_presupuesto_que_alcanza_trae_fecha_hotel_y_precio(self):
        out = tarifario.consultar(CFG, presupuesto="450 mil", hoy=HOY)
        bloque = out.split("PRESUPUESTO")[1]
        assert "Sí le alcanza" in bloque
        # La más barata de la temporada cabe en 450 mil y tiene que estar.
        assert pesos(minimo_crudo("amor_de_dios")) in bloque
        assert "DICIEMBRE 08 AL 11" in bloque
        assert "Amor de Dios" in bloque and "múltiple" in bloque
        # Ninguna de las que lista puede pasarse del presupuesto en múltiple.
        for linea in bloque.split("\n"):
            if linea.strip().startswith("· "):
                mult = int(re.search(r"múltiple \$([\d.]+)", linea)
                           .group(1).replace(".", ""))
                assert mult <= 450_000, linea

    def test_un_presupuesto_que_no_alcanza_ofrece_lo_mas_barato_que_existe(self):
        """Nunca dejar al cliente sin una opción: es la misma filosofía que la
        fecha sin salida, que devuelve las cercanas en vez de escalar."""
        out = tarifario.consultar(CFG, presupuesto="300 mil", hoy=HOY)
        bloque = out.split("PRESUPUESTO")[1]
        assert "NO alcanza" in bloque
        assert "NO le digas «no hay nada» ni escales" in bloque
        assert "Lo más económico" in bloque
        assert pesos(minimo_crudo("amor_de_dios")) in bloque

    def test_el_presupuesto_respeta_el_mes_que_el_cliente_ya_dijo(self):
        """El mismo error de F7 en otra forma: si ya dijo septiembre, no se le
        pueden colar las fechas de diciembre dentro del bloque del presupuesto."""
        out = tarifario.consultar(
            CFG, mes="septiembre", presupuesto="500 mil", hoy=HOY
        )
        bloque = out.split("PRESUPUESTO")[1].split("«desde»")[0]
        assert "sobre Septiembre" in bloque
        for mes in ("DICIEMBRE", "ENERO", "OCTUBRE", "AGOSTO"):
            assert mes not in bloque, bloque

    def test_si_no_alcanza_en_ese_mes_propone_mover_el_viaje(self):
        """$450.000 no alcanza en septiembre pero sí en diciembre. En vez de
        cerrar la venta, se le ofrece el cambio de mes — diciendo cuál es."""
        out = tarifario.consultar(
            CFG, mes="septiembre", presupuesto="450 mil", hoy=HOY
        )
        bloque = out.split("PRESUPUESTO")[1].split("«desde»")[0]
        assert "en otros meses sí le alcanza" in bloque
        assert "Diciembre" in bloque
        # Y los meses van del más próximo al más lejano, no de enero a diciembre.
        assert bloque.index("Diciembre") < bloque.index("Enero")

    def test_no_se_cuelan_salidas_ya_pasadas(self):
        """Consultando el 16 de diciembre, las dos salidas baratas del 08 y el
        14 ya pasaron: no pueden aparecer como opción de presupuesto."""
        out = tarifario.consultar(
            CFG, mes="diciembre", presupuesto="400 mil", hoy=date(2026, 12, 16)
        )
        assert "DICIEMBRE 08 AL 11" not in out
        assert "DICIEMBRE 14 AL 17" not in out

    def test_un_precio_exacto_de_la_tabla(self):
        """«¿Cuándo está en $459.000?» — el valor de un plan estándar de Amor de
        Dios. Tiene que salir con sus fechas, no con un «no entendí»."""
        exacto = minimo_crudo("amor_de_dios", 9)
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", presupuesto=pesos(exacto), hoy=HOY
        )
        bloque = out.split("PRESUPUESTO")[1]
        assert "Sí le alcanza" in bloque
        assert pesos(exacto) in bloque
        assert "SEPTIEMBRE 04 AL 07" in bloque

    def test_sin_mes_el_desde_dice_a_las_claras_que_es_global(self):
        """Un mínimo de toda la temporada es legítimo cuando no hay mes — lo que
        no puede es quedar donde el modelo lo lea como el de un mes."""
        out = tarifario.consultar(CFG, presupuesto="450 mil", hoy=HOY)
        linea = [l for l in out.split("\n") if "«desde» de" in l][0]
        assert "TODOS los meses publicados" in linea
        assert "NO es de un mes en particular" in linea
        assert "vuelve a consultar con ese mes" in linea

    def test_sin_mes_cada_fecha_dice_de_que_mes_es(self):
        out = tarifario.consultar(CFG, presupuesto="450 mil", hoy=HOY)
        bloque = out.split("PRESUPUESTO")[1]
        for linea in bloque.split("\n"):
            if linea.strip().startswith("· "):
                assert re.search(r"— [A-ZÁÉÍÓÚ]+ \d", linea), linea

    def test_toda_cifra_del_bloque_existe_o_es_el_presupuesto(self):
        for texto, tope in [("450 mil", 450_000), ("300 mil", 300_000),
                            ("900 mil", 900_000)]:
            out = tarifario.consultar(CFG, presupuesto=texto, hoy=HOY)
            inventadas = cifras_de(out) - precios_publicados() - {tope}
            assert not inventadas, f"{texto}: {sorted(inventadas)}"

    def test_un_presupuesto_ilegible_no_rompe_la_consulta_del_mes(self):
        """Si el modelo manda basura en `presupuesto`, la consulta normal del mes
        sigue funcionando: se ignora el presupuesto, no se pierde la respuesta."""
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre",
            presupuesto="algo económico", hoy=HOY,
        )
        assert "PRESUPUESTO" not in out
        assert "Amor de Dios — Septiembre" in out
