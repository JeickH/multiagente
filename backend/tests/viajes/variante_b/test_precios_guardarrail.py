"""Guardarraíl de precio del bot 2 (estrategia 18): `viola_precio`.

El caso que manda es la conversación 636: Amor de Dios, 16 al 19 de octubre,
en doble. El bot cotizó $549.000; el tarifario dice $505.000 — y $549.000 SÍ
existe en el tarifario (doble de Amor de Dios, 15 al 18 de enero). Se verifica
abajo contra el JSON real, no contra cifras copiadas aquí.

La otra mitad de esta suite es la que más importa en producción: **cero falsos
positivos** sobre mensajes como los que el bot 1 manda todos los días. Esos se
generan con las filas reales del tarifario (`test_no_salta_en_mensajes_del_bot_1`).

Ninguna frase de aquí es de un cliente real (repo público, regla #8).
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import tarifario
from app.services.guardarrail_precio import (
    extraer_montos,
    filas_de_resultados,
    viola_precio,
)

HOY = date(2026, 10, 7)
P = tarifario._pesos


def _consulta(**kw) -> str:
    return tarifario.consultar(LLM_CONFIG, hoy=HOY, **kw)


def _fila(hotel: str, inicio: str, etiqueta_prefijo: str) -> Dict:
    for p in tarifario._datos()["planes"]:
        if hotel in p["hoteles"] and p["inicio"] == inicio and p["fecha"].startswith(etiqueta_prefijo):
            return p
    raise AssertionError(f"no está la fila {hotel} {inicio} en el tarifario")


OCT = _consulta(mes="octubre")
OCT_BOHIOS = _consulta(mes="octubre", hotel="Bohíos")
ENE_AMOR = _consulta(mes="enero", hotel="Amor de Dios")
PRESUPUESTO = _consulta(presupuesto="450 mil")
EXTRAS = tarifario.extras()
NINO_3A4 = next(n["valor"] for n in EXTRAS["ninos"] if n["edad_min"] == 3)
NINO_0A2 = next(n["valor"] for n in EXTRAS["ninos"] if n["edad_min"] == 0)
PCT = EXTRAS["anticipo_pct"]

AMOR_16 = _fila("amor_de_dios", "2026-10-16", "OCTUBRE 16 AL 19")
AMOR_16_BARU = _fila("amor_de_dios", "2026-10-16", "OCTUBRE 16 AL 20")
PIEDRA_16 = _fila("piedra_mar", "2026-10-16", "OCTUBRE 16 AL 19")
AMOR_ENE_15 = _fila("amor_de_dios", "2027-01-15", "ENERO 15 AL 18")


def v(texto: str, resultados: Optional[List[str]] = None, *,
      desde: Optional[set] = None, cliente: Optional[set] = None) -> Optional[str]:
    return viola_precio(
        texto,
        resultados_precios=[OCT] if resultados is None else resultados,
        desde_validos={tarifario.desde_temporada(HOY)} if desde is None else desde,
        cifras_cliente=cliente or set(),
        extras=EXTRAS,
    )


# ---------------------------------------------------------------------------
# El caso real: conversación 636
# ---------------------------------------------------------------------------

class TestCaso636:
    def test_las_cifras_son_las_del_tarifario_real(self):
        assert AMOR_16["doble"] == 505_000
        assert AMOR_ENE_15["doble"] == 549_000   # existe, pero es otra fila

    def test_atrapa_la_fila_equivocada(self):
        msg = (f"¡Listo! 🌴 Para *Amor de Dios* del *16 al 19 de octubre* en "
               f"doble queda en {P(AMOR_ENE_15['doble'])} por persona.")
        error = v(msg)
        assert error is not None
        assert P(AMOR_16["doble"]) in error        # le dice el valor correcto

    def test_atrapa_aunque_la_cifra_este_en_los_resultados(self):
        """Lo que hace difícil el caso: $549.000 aparece en lo consultado
        (consultó enero en el mismo turno). Un «¿existe?» lo dejaría pasar."""
        assert P(AMOR_ENE_15["doble"]) in ENE_AMOR
        msg = (f"Para Amor de Dios del 16 al 19 de octubre en doble queda en "
               f"{P(AMOR_ENE_15['doble'])} por persona 🌴")
        assert v(msg, [OCT, ENE_AMOR]) is not None

    def test_atrapa_con_la_salida_en_la_frase_anterior(self):
        msg = (f"Te cuento de Amor de Dios del 16 al 19 de octubre 🌴\n"
               f"En doble queda en {P(AMOR_ENE_15['doble'])} por persona.")
        assert v(msg, [OCT, ENE_AMOR]) is not None

    def test_el_valor_correcto_pasa(self):
        msg = (f"Para Amor de Dios del 16 al 19 de octubre en doble queda en "
               f"{P(AMOR_16['doble'])} por persona 🌴")
        assert v(msg, [OCT, ENE_AMOR]) is None

    def test_la_multiple_cuando_dijo_doble_no_pasa(self):
        msg = (f"Amor de Dios, 16 al 19 de octubre, en doble: "
               f"{P(AMOR_16['multiple'])} por persona.")
        assert v(msg) is not None

    def test_el_plan_de_baru_no_se_confunde_con_el_estandar(self):
        bien = f"El del 16 al 20 de octubre (Obsequio a Barú) en Amor de Dios queda en {P(AMOR_16_BARU['multiple'])} en múltiple."
        mal = f"El del 16 al 19 de octubre en Amor de Dios queda en {P(AMOR_16_BARU['multiple'])} en múltiple."
        assert v(bien) is None
        assert v(mal) is not None

    def test_precio_mas_un_nino_sin_hablar_de_ninos_no_pasa(self):
        """«precio + $55.000» coincide a menudo con otra fila: sin niños en la
        frase, no se acepta como derivado."""
        msg = (f"Amor de Dios del 16 al 19 de octubre en doble: "
               f"{P(AMOR_16['doble'] + NINO_0A2)} por persona.")
        assert v(msg) is not None

    def test_el_precio_del_otro_hotel_no_pasa(self):
        msg = f"En Amor de Dios del 16 al 19 de octubre la múltiple es {P(PIEDRA_16['multiple'])}."
        assert v(msg) is not None


# ---------------------------------------------------------------------------
# Bohíos usa la tabla de Amor de Dios
# ---------------------------------------------------------------------------

class TestBohios:
    def test_bohios_con_el_precio_de_amor_de_dios_pasa(self):
        msg = f"En Bohíos del 16 al 19 de octubre en doble queda en {P(AMOR_16['doble'])} 🌴"
        assert v(msg, [OCT_BOHIOS]) is None
        assert v(msg, [OCT]) is None

    def test_bohios_con_el_precio_de_piedra_mar_no_pasa(self):
        msg = f"En Bohíos del 16 al 19 de octubre en doble queda en {P(PIEDRA_16['doble'])} 🌴"
        assert v(msg, [OCT]) is not None

    def test_las_filas_de_bohios_se_leen_como_amor_de_dios(self):
        filas = filas_de_resultados([OCT_BOHIOS])
        assert filas and {f.hotel for f in filas} == {"amor_de_dios"}


# ---------------------------------------------------------------------------
# Derivados: personas, niños, anticipo, saldo
# ---------------------------------------------------------------------------

class TestDerivados:
    @pytest.mark.parametrize("n", [2, 3, 4, 6, 10, 15])
    def test_total_n_personas(self, n):
        msg = (f"Para {n} personas en doble, del 16 al 19 de octubre en Amor de "
               f"Dios, serían {P(n * AMOR_16['doble'])} en total.")
        assert v(msg) is None

    def test_total_equivocado(self):
        msg = (f"Para 2 personas en doble, del 16 al 19 de octubre en Amor de "
               f"Dios, serían {P(2 * AMOR_16['doble'] + 40_000)} en total.")
        assert v(msg) is not None

    def test_ninos_sueltos(self):
        msg = (f"Los niños de 3 a 4 años pagan silla más seguro, {P(NINO_3A4)}, y los "
               f"menores de 2 años solo el seguro, {P(NINO_0A2)}.")
        assert v(msg) is None
        assert v(msg, []) is None       # sin consulta también: son extras

    def test_familia_con_ninos(self):
        total = 2 * AMOR_16["multiple"] + NINO_3A4 + NINO_0A2
        msg = (f"Para 2 adultos en múltiple del 16 al 19 de octubre en Amor de "
               f"Dios, con un niño de 3 años y un bebé de 1, el total es {P(total)} 🌴")
        assert v(msg) is None

    def test_familia_con_ninos_mal_sumada(self):
        total = 2 * AMOR_16["multiple"] + NINO_3A4 + NINO_0A2 + 30_000
        msg = (f"Para 2 adultos en múltiple del 16 al 19 de octubre en Amor de "
               f"Dios, con un niño de 3 años y un bebé de 1, el total es {P(total)} 🌴")
        assert v(msg) is not None

    def test_anticipo_por_persona_y_redondeado(self):
        exacto = AMOR_16["doble"] * PCT // 100
        redondo = round(exacto, -3)
        for valor in (exacto, redondo):
            msg = (f"Amor de Dios, 16 al 19 de octubre en doble: apartas con un "
                   f"anticipo del {PCT}%, es decir {P(valor)} por persona 🙌")
            assert v(msg) is None, valor

    def test_anticipo_y_saldo_del_total(self):
        total = 2 * AMOR_16["doble"]
        anticipo = total * PCT // 100
        saldo = total - anticipo
        msg = (f"Para 2 personas en doble del 16 al 19 de octubre en Amor de Dios "
               f"el total es {P(total)}. El anticipo del {PCT}% son {P(anticipo)} y "
               f"el saldo, {P(saldo)}, se paga de 8 a 10 días hábiles antes del viaje.")
        assert v(msg) is None

    def test_anticipo_inventado(self):
        msg = (f"Amor de Dios, 16 al 19 de octubre en doble: el anticipo es "
               f"{P(AMOR_16['doble'] * PCT // 100 + 25_000)}.")
        assert v(msg) is not None

    def test_diferencia_doble_menos_multiple(self):
        dif = AMOR_16["doble"] - AMOR_16["multiple"]
        msg = f"Del 16 al 19 de octubre en Amor de Dios, la doble cuesta {P(dif)} más por persona."
        assert v(msg) is None


# ---------------------------------------------------------------------------
# «desde»
# ---------------------------------------------------------------------------

class TestDesde:
    def test_desde_de_la_temporada_sin_consulta(self):
        msg = f"¡Hola! 🌴 Tenemos plan a Coveñas desde {P(tarifario.desde_temporada(HOY))} por persona."
        assert v(msg, []) is None

    def test_desde_del_mes_consultado(self):
        minimo = min(p["multiple"] for p in tarifario.planes_vigentes("amor_de_dios", HOY, 10))
        assert v(f"Para octubre está desde {P(minimo)} por persona en múltiple 🌴") is None

    def test_desde_por_encima_del_minimo_consultado_pasa(self):
        assert v(f"En Piedra Mar arranca en {P(PIEDRA_16['multiple'])} por persona.") is None

    def test_desde_inventado_sin_consulta(self):
        error = v("Tenemos salidas de lunes a jueves desde $350.000 por persona.", [])
        assert error is not None and "desde" in error

    def test_desde_por_debajo_de_lo_consultado(self):
        assert v("Para octubre está desde $300.000 por persona.") is not None


# ---------------------------------------------------------------------------
# Cifras del cliente
# ---------------------------------------------------------------------------

class TestCliente:
    def test_repite_el_presupuesto(self):
        msg = (f"Con tus $450.000 por persona te alcanza para el 16 al 19 de "
               f"octubre en Amor de Dios, que queda en {P(AMOR_16['multiple'])} en múltiple 🌴")
        assert v(msg, [OCT, PRESUPUESTO], cliente={450_000}) is None

    def test_presupuesto_en_mil(self):
        assert v("Con tus 450 mil sí te alcanza 🙌", [PRESUPUESTO], cliente={450_000}) is None
        # «Con» pegado al monto también presenta la cifra como presupuesto (QA
        # 2026-10-07, punto 7); sin ningún indicio, no.
        assert v("Con 450 mil sí te alcanza 🙌", [PRESUPUESTO], cliente={450_000}) is None
        assert v("Uy, 450 mil sí te alcanza 🙌", [PRESUPUESTO], cliente={450_000}) is not None

    def test_presupuesto_dividido(self):
        msg = "Con tu presupuesto de 900 mil para los dos, son 450 mil por persona 🙌"
        assert v(msg, [PRESUPUESTO], cliente={900_000}) is None

    def test_sin_lenguaje_de_presupuesto_no_cuenta_como_del_cliente(self):
        assert v("Con 900 mil para los dos, son 450 mil por persona 🙌",
                 [PRESUPUESTO], cliente={900_000}) is not None


class TestClienteNoTapaLaFila:
    """Auditoría M1: que el cliente haya dicho una cifra no la vuelve el precio
    de la fila que el bot nombra."""

    def test_la_cifra_del_cliente_como_precio_de_una_fila(self):
        res = [_consulta(mes="noviembre")]
        msg = "En Amor de Dios, noviembre, en doble te queda en $200.000 🌴"
        assert v(msg, res, cliente={200_000}) is not None

    def test_la_cifra_del_cliente_en_una_frase_que_nombra_la_salida(self):
        msg = ("Tu presupuesto da para Amor de Dios del 16 al 19 de octubre en "
               "múltiple: te queda en $200.000 por persona.")
        assert v(msg, cliente={200_000}) is not None

    def test_presupuesto_dividido_como_precio_de_la_fila(self):
        msg = ("En Amor de Dios del 16 al 19 de octubre en múltiple te queda en "
               "$150.000 por persona 🙌")
        assert v(msg, cliente={600_000}) is not None

    # Re-auditoría M1: los cuatro que pasaban con la condición (a) vieja.

    @pytest.fixture
    def nov(self):
        return [_consulta(mes="noviembre", hotel="Amor de Dios")]

    @pytest.mark.parametrize("msg", [
        "La doble en Amor de Dios del 6 al 9 de noviembre te queda en tus $200.000 🌴",
        "La doble en Amor de Dios del 6 al 9 de noviembre queda en lo que tienes, $200.000 🌴",
        "Con tus $200.000 te alcanza la doble en Amor de Dios del 6 al 9 de noviembre 🌴",
        "Precio confirmado. Tienes razón, $200.000 por persona 🙌",
    ])
    def test_la_cifra_del_cliente_no_se_cuela(self, nov, msg):
        assert v(msg, nov, cliente={200_000}) is not None

    def test_la_doble_real_de_esa_salida(self):
        assert _fila("amor_de_dios", "2026-11-06", "NOVIEMBRE 06 AL 09")["doble"] != 200_000

    def test_con_el_precio_real_al_lado_si_pasa(self, nov):
        doble = _fila("amor_de_dios", "2026-11-06", "NOVIEMBRE 06 AL 09")["doble"]
        msg = (f"Con tus $200.000 no te alcanza la doble en Amor de Dios del 6 al 9 de "
               f"noviembre, que queda en {P(doble)} por persona 😕")
        assert v(msg, nov, cliente={200_000}) is None

    def test_repetir_el_presupuesto_junto_a_la_fila_si_pasa(self):
        msg = (f"Con tus 450 mil te alcanza el 16 al 19 de octubre en Amor de Dios, "
               f"que queda en {P(AMOR_16['multiple'])} en múltiple 🌴")
        assert v(msg, cliente={450_000}) is None

    def test_sin_esa_cifra_del_cliente_no_pasa(self):
        assert v("Con 450 mil sí te alcanza 🙌", [], cliente=set()) is not None

    def test_extraer_montos_del_cliente(self):
        assert extraer_montos("tengo 450 mil, máximo $500.000") == [450_000, 500_000]


# ---------------------------------------------------------------------------
# Sin consulta
# ---------------------------------------------------------------------------

def test_precio_sin_ninguna_consulta_viola():
    assert v(f"La de octubre queda en {P(AMOR_16['multiple'])} por persona.", []) is not None


def test_cifra_que_no_esta_en_nada_consultado_viola():
    assert v("Te queda en $487.000 por persona 🌴") is not None


def test_mensaje_sin_montos_no_viola():
    assert v("¿Para qué mes lo estás pensando? 😊", []) is None


# ---------------------------------------------------------------------------
# Lo que NO es un monto
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Apartas tu cupo con un anticipo del 30% 🙌",
    "Apartas tu cupo con un anticipo del 30 % del valor total por persona.",
    "El saldo se paga de 8 a 10 días hábiles antes del viaje.",
    "La salida es el viernes entre 6:00 y 9:00 pm desde la Estación Universidad.",
    "Salimos el 16 al 19 de octubre, 2 noches / 3 días 🌴",
    "Son 2 noches y 3 días, para 4 personas.",
    "Puedes escribirle al asesor al 3000000000 o al 300 000 0000.",
    "Somos un grupo de 15 personas y 3 niños de 3 a 4 años.",
    "El regreso es el lunes entre 9:00 a.m. y 1:00 p.m.",
    "Tenemos salidas el 2, 16 y 23 de octubre 🌴",
    "La reserva vence en 24 horas y el 70% restante se paga después.",
    "Del 30 de octubre al 2 de noviembre es puente festivo.",
])
def test_no_salta_con_cosas_que_no_son_precio(texto):
    assert v(texto, []) is None


@pytest.mark.parametrize("texto,esperado", [
    ("$459.000", [459_000]),
    ("$ 459.000", [459_000]),
    ("$459000", [459_000]),
    ("$1.010.000", [1_010_000]),
    ("$1'010.000", [1_010_000]),
    ("459 mil", [459_000]),
    ("$459 mil", [459_000]),
    ("459k", [459_000]),
    ("1,5 millones", [1_500_000]),
    ("2 millones", [2_000_000]),
    ("459.000 pesos", [459_000]),
    ("30%", []),
    ("16 al 19", []),
    ("3000000000", []),
    ("8:00 pm", []),
    ("$3.000", []),               # debajo del mínimo: propina del itinerario
])
def test_extraer_montos(texto, esperado):
    assert extraer_montos(texto) == esperado


# ---------------------------------------------------------------------------
# Formato de `consultar_precios` (capa de productos)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def consultar_precios():
    """El resultado de `consultar_precios` con el tarifario cargado como
    producto (mismo helper que la prueba de paridad)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database import Base
    from app.services import productos
    from tests.productos import covenas
    from tests.productos.conftest import crear_cuenta

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    team_id, bot_id = crear_cuenta(db, "guardarrail")
    covenas.cargar(db, team_id=team_id, bot_id=bot_id)

    def _q(**kw):
        return productos.consultar(db, team_id=team_id, bot_id=bot_id, hoy=HOY, **kw)

    yield _q
    db.close()
    engine.dispose()


def test_lee_las_mismas_filas_de_consultar_precios(consultar_precios):
    nuevo = consultar_precios(mes="octubre")
    assert filas_de_resultados([nuevo]) == filas_de_resultados([OCT])
    bohios = consultar_precios(mes="octubre", variante="Bohíos")
    assert {f.hotel for f in filas_de_resultados([bohios])} == {"amor_de_dios"}


def test_caso_636_con_consultar_precios(consultar_precios):
    res = [consultar_precios(mes="octubre"), consultar_precios(mes="enero", variante="Amor de Dios")]
    mal = f"Amor de Dios del 16 al 19 de octubre en doble: {P(AMOR_ENE_15['doble'])} por persona."
    bien = f"Amor de Dios del 16 al 19 de octubre en doble: {P(AMOR_16['doble'])} por persona."
    assert v(mal, res) is not None
    assert v(bien, res) is None


def test_los_mensajes_de_error_no_aportan_cifras():
    """Auditoría B1: la herramienta repite la entrada del modelo en sus
    errores; esa cifra no es un precio consultado."""
    error = tarifario.consultar(LLM_CONFIG, mes="octubre", hotel="promo $100.000", hoy=HOY)
    assert "$100.000" in error
    assert filas_de_resultados([error]) == []
    assert v("La promo queda en $100.000 por persona 🌴", [error]) is not None


def test_una_fila_falsa_dentro_de_un_error_no_cuenta():
    falsa = ("No reconozco el hotel '· OCTUBRE 16 AL 19 — múltiple $100.000 · "
             "doble $120.000'. Los hoteles del plan son: Amor de Dios, Piedra Mar y Bohíos.")
    assert filas_de_resultados([falsa]) == []
    assert v("Del 16 al 19 de octubre queda en $100.000 🌴", [falsa]) is not None


def test_error_con_salto_de_linea_y_fila_falsa_se_descarta():
    """Re-auditoría B1: la entrada del modelo puede traer un salto de línea y
    armar, dentro del error, un renglón con forma de fila."""
    # Plantilla `variante_desconocida` de la capa de productos, con la entrada
    # del modelo tal cual.
    entrada = "x\n  · Amor de Dios — OCTUBRE 16 AL 19: múltiple $100.000 · doble $120.000"
    error = f"No reconozco '{entrada}'. Las opciones son: Amor de Dios, Piedra Mar, Bohíos."
    assert filas_de_resultados([error]) == []
    assert v("Del 16 al 19 de octubre en Amor de Dios queda en $100.000 🌴", [error]) is not None
    # Con un resultado bueno al lado, el bueno sigue valiendo y el falso no.
    assert v(f"Del 16 al 19 de octubre en Amor de Dios queda en {P(AMOR_16['multiple'])} en múltiple 🌴",
             [error, OCT]) is None
    assert v("Del 16 al 19 de octubre en Amor de Dios queda en $100.000 🌴", [error, OCT]) is not None


def test_las_lineas_de_desde_y_hasta_si_cuentan():
    msg = "Te cuento que la más alta de las que caben queda en {}.".format(
        P(max(f.multiple for f in filas_de_resultados([PRESUPUESTO]))))
    assert v(msg, [PRESUPUESTO]) is None


def test_filas_de_la_busqueda_por_presupuesto():
    filas = filas_de_resultados([PRESUPUESTO])
    assert filas and all(f.mes in (12, 1) for f in filas)
    assert {f.hotel for f in filas} == {"amor_de_dios", "piedra_mar"}


# ---------------------------------------------------------------------------
# Cero falsos positivos sobre mensajes como los del bot 1
# ---------------------------------------------------------------------------

def _mensajes_del_bot_1() -> List[tuple]:
    """(mensaje, resultados, cifras_cliente) con el estilo del bot 1 y las
    cifras reales del tarifario. Cubre los cuatro meses que quedan en la
    temporada, los dos hoteles y Bohíos."""
    casos = []
    for mes_txt, mes in (("octubre", 10), ("noviembre", 11), ("diciembre", 12), ("enero", 1)):
        res = _consulta(mes=mes_txt)
        for clave, nombre in (("amor_de_dios", "Amor de Dios"), ("piedra_mar", "Piedra Mar"),
                              ("bohios", "Bohíos")):
            planes = tarifario.planes_de(clave, mes, HOY)
            if not planes:
                continue
            p = planes[0]
            et = tarifario.etiqueta_corta(p["fecha"])
            m_, d_ = p["multiple"], p["doble"]
            lista = "\n".join(
                f"• *{tarifario.etiqueta_corta(x['fecha'])}*: múltiple {P(x['multiple'])} · "
                f"doble {P(x['doble'])} ({x['noches']} noches / {x['dias']} días)"
                for x in planes
            )
            casos += [
                (f"¡Claro! 🌴 Para *{mes_txt}* en *{nombre}* tenemos estas salidas:\n"
                 f"{lista}\n¿Cuál te sirve más? 😊", [res], set()),
                (f"La salida del *{et}* de {mes_txt} en {nombre} queda en {P(m_)} por "
                 f"persona en múltiple y {P(d_)} en doble 🙌 ¿Te la aparto?", [res], set()),
                (f"Para 2 personas en doble serían {P(2 * d_)} en total, y apartas tu "
                 f"cupo con un anticipo del {PCT}% ({P(2 * d_ * PCT // 100)}) 🙌. El "
                 f"saldo ({P(2 * d_ - 2 * d_ * PCT // 100)}) se paga de 8 a 10 días "
                 f"hábiles antes del viaje.", [res], set()),
                (f"Para 2 adultos en múltiple y un niño de 3 años serían "
                 f"{P(2 * m_ + NINO_3A4)}: el niño paga silla más seguro, {P(NINO_3A4)} 😊",
                 [res], set()),
            ]
        minimo = min(x["multiple"] for h in ("amor_de_dios", "piedra_mar")
                     for x in tarifario.planes_de(h, mes, HOY))
        casos.append((f"Para {mes_txt} está desde {P(minimo)} por persona en múltiple 🌴 "
                      f"Te mando el flyer con todas las fechas 👇", [res], set()))
        amor = tarifario.planes_de("amor_de_dios", mes, HOY)[0]
        piedra = next(x for x in tarifario.planes_de("piedra_mar", mes, HOY)
                      if x["inicio"] == amor["inicio"])
        casos.append((
            f"Del {tarifario.etiqueta_corta(amor['fecha'])} de {mes_txt}: Amor de Dios "
            f"queda en {P(amor['multiple'])} y Piedra Mar en {P(piedra['multiple'])} por "
            f"persona en múltiple 🌴", [res], set()))
    casos += [
        ("La canoa a la Casa Flotante es opcional, $25.000 aprox. por persona 🚣‍♀️",
         [], set()),
        (f"Con tus 450 mil te alcanza para el 8 al 11 de diciembre en Amor de Dios, que "
         f"queda en {P(_fila('amor_de_dios', '2026-12-08', 'DICIEMBRE 08')['multiple'])} "
         f"en múltiple 🌴", [PRESUPUESTO], {450_000}),
        (f"Para el 17 de octubre no tenemos salida, pero muy cerquita está la del "
         f"*16 al 19* en {P(AMOR_16['multiple'])} por persona en múltiple 🌴 ¿Te sirve?",
         [_consulta(fecha="2026-10-17", hotel="Amor de Dios")], set()),
        (f"¡Hola! 👋 Tenemos plan a Coveñas desde {P(tarifario.desde_temporada(HOY))} "
         f"por persona, con transporte, hotel y alimentación 🌴", [], set()),
        (f"En Bohíos, del 16 al 19 de octubre, queda en {P(AMOR_16['multiple'])} en "
         f"múltiple; el flyer sale a nombre de Amor de Dios pero el precio aplica igual 🙌",
         [OCT_BOHIOS], set()),
        (f"Del 16 al 19 de octubre en Amor de Dios queda en {P(AMOR_16['multiple'])} por "
         f"persona en múltiple. Si prefieres Piedra Mar, el 23 al 26 queda en "
         f"{P(_fila('piedra_mar', '2026-10-23', 'OCTUBRE 23')['multiple'])}.", [OCT], set()),
        (f"Queda en {P(AMOR_16['multiple'])} por persona en el 16 al 19; si prefieres el "
         f"festivo del 9 al 12, sube a "
         f"{P(_fila('amor_de_dios', '2026-10-09', 'OCTUBRE 09')['multiple'])} 🌴", [OCT], set()),
        (f"El del 30 al 2 de noviembre (festivo) en Amor de Dios queda en "
         f"{P(_fila('amor_de_dios', '2026-10-30', 'OCTUBRE 30')['multiple'])} en múltiple.",
         [OCT], set()),
    ]
    return casos


MENSAJES_BOT_1 = _mensajes_del_bot_1()


def test_la_bateria_tiene_al_menos_30_mensajes():
    assert len(MENSAJES_BOT_1) >= 30


@pytest.mark.parametrize("i", range(len(MENSAJES_BOT_1)))
def test_no_salta_en_mensajes_del_bot_1(i):
    texto, resultados, cliente = MENSAJES_BOT_1[i]
    assert extraer_montos(texto), "el mensaje de prueba tiene que traer precio"
    assert v(texto, resultados, cliente=cliente) is None, texto


def test_no_salta_en_ninguna_fila_de_la_temporada():
    """Barrido: cada salida de la temporada (desde julio), cada hotel, con las
    formas en que el bot 1 cotiza. Cero falsos positivos."""
    hoy = date(2026, 7, 1)
    desde = {tarifario.desde_temporada(hoy)}
    fallos = []
    for mes_txt in ("julio", "agosto", "septiembre", "octubre", "noviembre",
                    "diciembre", "enero"):
        mes = tarifario.normalizar_mes(mes_txt)
        for clave, nombre in (("amor_de_dios", "Amor de Dios"),
                              ("piedra_mar", "Piedra Mar"), ("bohios", "Bohíos")):
            res = [tarifario.consultar(LLM_CONFIG, mes=mes_txt, hotel=nombre, hoy=hoy)]
            for p in tarifario.planes_de(clave, mes, hoy):
                et = tarifario.etiqueta_corta(p["fecha"])
                m_, d_ = p["multiple"], p["doble"]
                anticipo2 = round(2 * d_ * PCT / 100, -3)
                for msg in (
                    f"La salida del *{et}* de {mes_txt} en {nombre} queda en {P(m_)} por persona en múltiple y {P(d_)} en doble 🙌",
                    f"*{nombre}* — {et} de {mes_txt}\n• Múltiple: {P(m_)}\n• Doble: {P(d_)}\n¿Te la aparto? 😊",
                    f"En doble, el {et} sale en {P(d_)} por persona; para los 2 serían {P(2 * d_)} 🙌",
                    f"Para separar el {et} en {nombre} el anticipo es del {PCT}%: {P(m_ * PCT // 100)} por persona en múltiple.",
                    f"El anticipo para 2 en doble es de {P(anticipo2)} y el saldo de {P(2 * d_ - anticipo2)} se paga de 8 a 10 días hábiles antes 🤗",
                    f"Para 2 adultos y un niño de 4 años en múltiple del {et}: {P(2 * m_)} + {P(NINO_3A4)} = {P(2 * m_ + NINO_3A4)} 🌴",
                    f"La doble del {et} cuesta {P(d_ - m_)} más por persona que la múltiple.",
                    f"Uy, ese queda en {P(m_)} por persona en {nombre} ({et}). Si quieres te paso las otras fechas 😊",
                ):
                    if v(msg, res, desde=desde) is not None:
                        fallos.append(msg)
    assert not fallos, fallos[:5]


# ---------------------------------------------------------------------------
# Rendimiento con entradas adversariales (auditoría H1)
# ---------------------------------------------------------------------------

_N = 20_000
_ADVERSARIALES = {
    "digitos": "9" * _N,
    "digitos_millones": "9" * _N + " millones",
    "digitos_mil": "9" * _N + " mil",
    "digitos_pesos": "9" * _N + " pesos",
    "puntos_digitos": "999." * (_N // 4),
    "puntos_digitos_pesos": "999." * (_N // 4) + "999 pesos",
    "pesos_puntos": "$999." * (_N // 5),
    "comas": "9," * (_N // 2),
    "apostrofes": "9'" * (_N // 2),
    "espacios": " " * _N,
    "digitos_espacios": "9 " * (_N // 2),
    "espacios_millones": "9" + " " * _N + "millones",
    "puntos": "." * _N,
    "saltos": "\n" * _N,
    "rangos": "1 al " * (_N // 5),
    "rangos_espacios": "1" + " " * _N + "al 2",
    "guiones": "1-" * (_N // 2),
    "meses": "octubre 1 " * (_N // 10),
    "desde": "desde " * (_N // 6),
    "montos_seguidos": "$459.000 " * (_N // 9),
    "montos_con_atributos": "Amor de Dios 16 al 19 de octubre doble $505.000 " * (_N // 48),
    "vinetas": "· " * (_N // 2),
    "vineta_larga": "· " + "x" * _N + " — multiple $1.000",
}


@pytest.mark.parametrize("nombre", sorted(_ADVERSARIALES))
def test_extraer_montos_es_lineal(nombre):
    import time

    texto = _ADVERSARIALES[nombre]
    t = time.perf_counter()
    extraer_montos(texto)
    assert time.perf_counter() - t < 0.05, nombre


@pytest.mark.parametrize("nombre", sorted(_ADVERSARIALES))
def test_viola_precio_es_lineal(nombre):
    """Texto del bot de 20.000 caracteres, con resultados y cifras del cliente
    para que recorra todas las reglas."""
    import time

    texto = _ADVERSARIALES[nombre]
    t = time.perf_counter()
    v(texto, [OCT], cliente={505_000, 459_000})
    assert time.perf_counter() - t < 0.05, nombre


@pytest.mark.parametrize("nombre", sorted(_ADVERSARIALES))
def test_leer_resultados_es_lineal(nombre):
    import time

    t = time.perf_counter()
    filas_de_resultados([_ADVERSARIALES[nombre]])
    assert time.perf_counter() - t < 0.05, nombre


# ---------------------------------------------------------------------------
# QA contra Bedrock real (2026-10-07): las cadenas que daban falso positivo o
# falso negativo, tal como las escribió el modelo (ningún dato de cliente).
# ---------------------------------------------------------------------------

NOV = _consulta(mes="noviembre")
DIC = _consulta(mes="diciembre")
PRESUPUESTO_350 = _consulta(presupuesto="350 mil")

LISTA_OCTUBRE_GUIONES = """Perfecto 🌴 Para octubre tenemos varias salidas. Te dejo las opciones:

*Amor de Dios y Bohíos*:
• 9-12 de octubre (festivo): $559.000 múltiple
• 16-19 de octubre: $459.000 múltiple
• 16-20 de octubre (Barú incluido): $550.000 múltiple
• 23-26 de octubre: $459.000 múltiple
• 30 oct-2 nov (festivo): $559.000 múltiple

*Piedra Mar*:
• 9-12 de octubre (festivo): $570.000 múltiple
• 16-19 de octubre: $469.000 múltiple
• 16-20 de octubre (Barú incluido): $620.000 múltiple
• 23-26 de octubre: $469.000 múltiple
• 30 oct-2 nov (festivo): $570.000 múltiple

Mira el tarifario aquí 👇"""

LISTA_OCTUBRE_ABREVIADA = """Perfecto 🌴 En octubre tenemos varias salidas:

**Amor de Dios & Bohíos** (desde $459.000):
• Oct 09–12 (festivo): $559.000
• Oct 16–19: $459.000 
• Oct 16–20 (con Barú): $550.000
• Oct 23–26: $459.000
• Oct 30–Nov 02 (festivo): $559.000

**Piedra Mar** (desde $469.000):
• Oct 09–12 (festivo): $570.000
• Oct 16–19: $469.000
• Oct 16–20 (con Barú): $620.000
• Oct 23–26: $469.000
• Oct 30–Nov 02 (festivo): $570.000

Te dejo los tarifarios completos 📦"""

LISTA_OCTUBRE_30_NOV_02 = """Te muestro las opciones en octubre 🌴

**Amor de Dios / Bohíos:**
· 09 al 12 (festivo) — desde $559.000 en múltiple
· 16 al 19 — desde $459.000 en múltiple ✨
· 16 al 20 (Barú incluido) — $550.000 en múltiple
· 23 al 26 — $459.000 en múltiple
· 30 nov 02 (festivo) — $559.000 en múltiple

**Piedra Mar:**
· 09 al 12 (festivo) — desde $570.000 en múltiple
· 16 al 19 — desde $469.000 en múltiple ✨
· 16 al 20 (Barú incluido) — $620.000 en múltiple
· 23 al 26 — $469.000 en múltiple
· 30 nov 02 (festivo) — $570.000 en múltiple

¿Cuál fecha te sirve? 😊"""

LISTA_DICIEMBRE = """Tenemos muchas opciones en diciembre 🎄 Aquí van las salidas de Amor de Dios / Bohíos:

💰 Desde *$369.000* (8-11 dic)
💰 *$459.000* (4-7, 11-14, 18-21 dic)
💰 *$799.000* (29 dic-2 ene Fin de Año)

¿Cuál te llama más? 🌴"""


class TestQA20261007:
    # 1. Atributos de una viñeta no pasan a la siguiente.
    def test_la_festiva_no_se_arrastra_a_la_vineta_siguiente(self):
        assert v(LISTA_OCTUBRE_GUIONES) is None

    def test_vinetas_con_mes_abreviado(self):
        assert v(LISTA_OCTUBRE_ABREVIADA) is None

    def test_cada_vineta_sigue_juzgandose_contra_su_salida(self):
        mal = LISTA_OCTUBRE_GUIONES.replace("• 16-19 de octubre: $459.000", "• 16-19 de octubre: $559.000")
        assert v(mal) is not None

    def test_una_viñeta_no_hereda_el_hotel_del_encabezado_para_condenar(self):
        msg = "*Piedra Mar*:\n• 16-19 de octubre: $459.000 múltiple"
        # Sin hotel en la viñeta, se juzga contra la fecha: $459.000 es de esa
        # fecha (Amor de Dios), así que no se rechaza un listado correcto.
        assert v(msg) is None

    # 2. Rangos que cruzan de mes.
    @pytest.mark.parametrize("rango", ["30 oct-2 nov", "Oct 30–Nov 02", "30 nov 02",
                                       "30 de oct al 02 de nov", "Oct 30 - Nov 02"])
    def test_rangos_que_cruzan_de_mes(self, rango):
        festivo = _fila("amor_de_dios", "2026-10-30", "OCTUBRE 30")
        bien = f"• 23-26 de octubre: {P(AMOR_16['multiple'])}\n• {rango} (festivo): {P(festivo['multiple'])} en Amor de Dios"
        mal = f"• 23-26 de octubre: {P(AMOR_16['multiple'])}\n• {rango} (festivo): {P(AMOR_16['multiple'])} en Amor de Dios"
        assert v(bien) is None
        assert v(mal) is not None

    def test_rango_que_cruza_de_anio(self):
        assert v(LISTA_DICIEMBRE, [DIC]) is None
        mal = LISTA_DICIEMBRE.replace("*$799.000* (29 dic-2 ene", "*$459.000* (29 dic-2 ene")
        assert v(mal, [DIC]) is not None

    def test_lista_con_30_nov_02(self):
        assert v(LISTA_OCTUBRE_30_NOV_02) is None

    # 3. Hotel nombrado después del monto.
    def test_hotel_despues_del_monto(self):
        msg = ("Las salidas en noviembre empiezan desde *$459.000* por persona en Amor "
               "de Dios y *$469.000* en Piedra Mar, en acomodación múltiple.")
        assert v(msg, [NOV]) is None
        msg2 = ("Fin de semana estándar (viernes a lunes): *$459.000* en Amor de "
                "Dios/Bohíos o *$469.000* en Piedra Mar")
        assert v(msg2, [NOV]) is None

    # 4. Línea que no casa con ninguna fila → regla 4 (permisiva).
    def test_linea_sin_fila_que_case_cae_a_la_regla_4(self):
        msg = "• 17-20 de octubre (sin salida así): $459.000 en Amor de Dios"
        assert v(msg) is None

    # 5. Falso negativo: el «desde» de temporada con un mes consultado.
    def test_desde_de_temporada_con_mes_consultado_viola(self):
        desde = tarifario.desde_temporada(HOY)
        msg = f"🌟 *Viernes 10 de octubre* → desde {P(desde)} por persona 🌴"
        assert v(msg, [OCT]) is not None
        assert v(f"*Amor de Dios* y *Bohíos*: desde {P(desde)} por persona en múltiple", [OCT]) is not None

    def test_desde_de_temporada_sin_consulta_vale(self):
        assert v(f"Tenemos planes desde {P(tarifario.desde_temporada(HOY))} 🌴", []) is None

    def test_desde_de_temporada_si_es_el_minimo_consultado(self):
        assert v(f"Lo más económico arranca en {P(tarifario.desde_temporada(HOY))} por persona",
                 [PRESUPUESTO]) is None

    # 6. Porcentaje del anticipo.
    @pytest.mark.parametrize("msg", [
        "El anticipo es del *40%* y el saldo se paga 8 a 10 días antes del viaje 🙌",
        "Apartas tu cupo con un *anticipo del 40%* ($191.600 por persona)",
        "Se separa con el 50% de anticipo 🙌",
        "La cuota inicial es de un 50 %",
    ])
    def test_anticipo_inventado(self, msg):
        assert v(msg, []) is not None

    @pytest.mark.parametrize("msg", [
        "Apartas tu cupo con un anticipo del 30% 🙌",
        "El *30%* de anticipo y el 70% restante antes del viaje",
        "Los niños menores de 12 años pagan el 50%",   # no es anticipo: no lo juzga esta regla
    ])
    def test_anticipo_correcto_o_ajeno(self, msg):
        assert v(msg, []) is None

    # 7. «Con $350.000…» del cliente.
    def test_con_350_y_el_precio_real_de_la_fila_pasa(self):
        msg = ("Con $350.000 se pasa un poquito, pero muy cerquita está lo más económico "
               "que hay: *Amor de Dios o Bohíos* del *8 al 11 de diciembre* en múltiple a "
               "*$369.000* por persona 🌴 Es una salida entre semana.")
        assert v(msg, [PRESUPUESTO_350], cliente={350_000}) is None

    def test_con_350_sin_nombrar_fila_pasa(self):
        msg = "Con $350.000 no alcanza para ninguna salida en este momento 😕"
        assert v(msg, [PRESUPUESTO_350], cliente={350_000}) is None

    def test_con_350_nombrando_la_fila_sin_su_precio_viola(self):
        msg = ("Con $350.000 te alcanza *Amor de Dios* del *8 al 11 de diciembre* en "
               "múltiple 🌴")
        assert v(msg, [PRESUPUESTO_350], cliente={350_000}) is not None


class TestDiferenciaConElPresupuesto:
    MINIMO = _fila("amor_de_dios", "2026-12-08", "DICIEMBRE 08")["multiple"]

    @pytest.mark.parametrize("cola", [
        "Solo te pasas {d}.",
        "Se te pasa solo {d} por persona, ¡bien cerquita!",
        "apenas {d} más de tu presupuesto 🌴",
    ])
    def test_lo_que_le_falta_al_presupuesto_pasa(self, cola):
        d = P(self.MINIMO - 350_000)
        msg = (f"Con $350.000 se ajusta un poquito: la más económica es *Amor de Dios* del "
               f"*8 al 11 de diciembre* en *{P(self.MINIMO)}* por persona en múltiple 🌴 "
               + cola.format(d=d))
        assert v(msg, [PRESUPUESTO_350], cliente={350_000}) is None

    def test_sin_hablar_de_pasarse_no_pasa(self):
        d = P(self.MINIMO - 350_000)
        msg = f"En Amor de Dios del 8 al 11 de diciembre el seguro es de {d} 🌴"
        assert v(msg, [PRESUPUESTO_350], cliente={350_000}) is not None

    def test_una_diferencia_inventada_no_pasa(self):
        msg = ("Con $350.000 la más económica es *Amor de Dios* del *8 al 11 de diciembre* "
               f"en *{P(self.MINIMO)}*. Solo te pasas $45.000.")
        assert v(msg, [PRESUPUESTO_350], cliente={350_000}) is not None


class TestReauditoriaM1Delta:
    """Los dos caminos por los que se reabrió M1 (cifra del cliente como precio)."""

    NOV_AMOR = _consulta(mes="noviembre", hotel="Amor de Dios")

    @pytest.mark.parametrize("msg,res", [
        # Salida que no se consultó: solo noviembre / solo Amor de Dios.
        ("Con $200.000 te queda la doble en Amor de Dios del 6 al 9 de diciembre 🌴", "nov"),
        ("Con $200.000 te queda la doble en Piedra Mar del 6 al 9 de noviembre 🌴", "nov_amor"),
    ])
    def test_salida_no_consultada_no_pasa_por_el_presupuesto(self, msg, res):
        resultados = [NOV] if res == "nov" else [self.NOV_AMOR]
        assert v(msg, resultados, cliente={200_000}) is not None

    def test_salida_nombrada_sin_ninguna_consulta(self):
        assert v("Con $200.000 te queda la doble en Amor de Dios del 6 al 9 de noviembre 🌴",
                 [], cliente={200_000}) is not None

    @pytest.mark.parametrize("msg", [
        "La doble en Amor de Dios del 6 al 9 de noviembre te queda en $200.000 y no te pasas 🙌",
        "Te falta poquito: la doble del 6 al 9 de noviembre en Amor de Dios queda en $200.000",
    ])
    def test_diferencia_suelta_en_la_frase_no_cuenta(self, msg):
        # 305 mil − 505 mil (la doble real) = 200 mil: antes pasaba por 0b.
        assert _fila("amor_de_dios", "2026-11-06", "NOVIEMBRE 06")["doble"] - 305_000 == 200_000
        assert v(msg, [self.NOV_AMOR], cliente={305_000}) is not None

    def test_diferencia_contra_otra_fila_no_cuenta(self):
        """Con salida nombrada, la diferencia se calcula solo contra esa salida."""
        doble = _fila("amor_de_dios", "2026-11-06", "NOVIEMBRE 06")["doble"]
        otra = _fila("amor_de_dios", "2026-11-13", "NOVIEMBRE 13")["doble"]
        msg = (f"La doble en Amor de Dios del 6 al 9 de noviembre es {P(doble)}; "
               f"solo te pasas {P(otra - 305_000)}")
        assert otra != doble
        assert v(msg, [self.NOV_AMOR], cliente={305_000}) is not None

    def test_eco_legitimo_con_el_precio_real(self):
        multiple = _fila("amor_de_dios", "2026-11-06", "NOVIEMBRE 06")["multiple"]
        msg = (f"Con tus 450 mil te alcanza el 6 al 9 de noviembre en Amor de Dios, "
               f"que queda en {P(multiple)} 🌴")
        assert v(msg, [self.NOV_AMOR], cliente={450_000}) is None

    def test_solo_te_pasas_legitimo(self):
        multiple = _fila("amor_de_dios", "2026-11-06", "NOVIEMBRE 06")["multiple"]
        cliente = multiple - 19_000
        msg = (f"La del 6 al 9 de noviembre en Amor de Dios queda en {P(multiple)} en "
               f"múltiple. Solo te pasas $19.000 🙌")
        assert v(msg, [self.NOV_AMOR], cliente={cliente}) is None
