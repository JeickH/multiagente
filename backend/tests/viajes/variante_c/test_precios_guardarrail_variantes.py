"""Guardarraíl de precio: variantes de una misma salida (QA bot 3, C06 r01).

El bot escribió «Para el *18 al 21 de diciembre* en *Amor de Dios* … 2️⃣
*Obsequio a Barú* (3 noches / 4 días): $550.000». $550.000 es la salida del
18 al 22 (Obsequio a Barú), que sale el mismo día; el guardarraíl la juzgaba
contra la del 18 al 21 del encabezado y el turno terminó en traspaso tras tres
reescrituras idénticas. Las variantes se leen del resultado de la herramienta
(paréntesis de la fecha, «festivo», plan al final del renglón), no de una
lista a mano. Cifras siempre del tarifario real.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import tarifario
from app.services.guardarrail_precio import filas_de_resultados, viola_precio

HOY = date(2026, 10, 11)
P = tarifario._pesos
DIC_AMOR = tarifario.consultar(LLM_CONFIG, mes="diciembre", hotel="Amor de Dios",
                               fecha="2026-12-18", hoy=HOY)
DIC = tarifario.consultar(LLM_CONFIG, mes="diciembre", hoy=HOY)
OCT = tarifario.consultar(LLM_CONFIG, mes="octubre", hoy=HOY)


def _fila(hotel, inicio, prefijo):
    return next(p for p in tarifario._datos()["planes"]
                if hotel in p["hoteles"] and p["inicio"] == inicio and p["fecha"].startswith(prefijo))


ESTANDAR = _fila("amor_de_dios", "2026-12-18", "DICIEMBRE 18 AL 21")
BARU = _fila("amor_de_dios", "2026-12-18", "DICIEMBRE 18 AL 22")
PIEDRA_BARU = _fila("piedra_mar", "2026-12-18", "DICIEMBRE 18 AL 22")


def v(texto, resultados=None):
    return viola_precio(
        texto, resultados_precios=[DIC_AMOR] if resultados is None else resultados,
        desde_validos={tarifario.desde_temporada(HOY)}, cifras_cliente=set(),
        extras=tarifario.extras(),
    )


C06 = f"""Para el *18 al 21 de diciembre* en *Amor de Dios* tenemos dos opciones ✨

1️⃣ *Plan estándar* (2 noches / 3 días): *{P(ESTANDAR['multiple'])} c/u* → *{P(2 * ESTANDAR['multiple'])} total*
2️⃣ *Obsequio a Barú* (3 noches / 4 días): *{P(BARU['multiple'])} c/u* → *{P(2 * BARU['multiple'])} total*

¿Cuál prefieres? 👇

1️⃣ Plan estándar
2️⃣ Obsequio a Barú
3️⃣ Tengo una pregunta 🤔"""


def test_las_cifras_del_caso_son_las_del_tarifario():
    assert ESTANDAR["plan"] == "Plan estándar" and BARU["plan"] == "Obsequio a Barú"
    assert ESTANDAR["multiple"] != BARU["multiple"]


def test_las_variantes_salen_del_resultado():
    variantes = {f.etiqueta: f.variantes for f in filas_de_resultados([DIC_AMOR])}
    assert "obsequio a baru" in variantes["DICIEMBRE 18 AL 22 (Obsequio a Barú)"]
    assert "plan estandar" in variantes["DICIEMBRE 18 AL 21"]
    assert {"cena navidena", "fin de semana festivo"} <= variantes["DICIEMBRE 23 AL 26 (Cena Navideña)"]
    assert "fin de ano" in next(v_ for k, v_ in variantes.items() if k.startswith("DICIEMBRE 29"))


def test_caso_c06_pasa():
    assert v(C06) is None
    assert v(C06, [DIC]) is None


def test_caso_c06_en_prosa_pasa():
    msg = (f"Para el 18 al 21 de diciembre en Amor de Dios, el Obsequio a Barú "
           f"queda en {P(BARU['multiple'])} por persona en múltiple.")
    assert v(msg) is None


@pytest.mark.parametrize("variante", ["Obsequio a Barú", "obsequio a baru", "*Obsequio a Barú*"])
def test_la_variante_se_reconoce_como_la_escriba(variante):
    msg = f"Del 18 al 21 de diciembre en Amor de Dios, {variante}: {P(BARU['doble'])} en doble"
    assert v(msg) is None


def test_sin_nombrar_la_variante_sigue_siendo_otra_fila():
    msg = (f"Para el 18 al 21 de diciembre en Amor de Dios queda en "
           f"{P(BARU['multiple'])} por persona en múltiple.")
    error = v(msg)
    assert error is not None
    # El detalle le dice de qué salida es esa cifra, para que no repita el texto.
    assert "18 AL 22 (Obsequio a Barú)" in error and P(BARU["multiple"]) in error
    assert len(error) <= 300


def test_la_variante_no_tapa_un_precio_inventado():
    msg = f"Del 18 al 21 de diciembre en Amor de Dios, Obsequio a Barú: $587.000 en múltiple"
    assert v(msg) is not None


def test_la_variante_de_otro_hotel_no_pasa():
    msg = (f"Del 18 al 21 de diciembre en Amor de Dios, Obsequio a Barú: "
           f"{P(PIEDRA_BARU['multiple'])} en múltiple")
    assert v(msg, [DIC]) is not None


def test_la_variante_de_otra_fecha_no_pasa():
    """El Barú del 11 al 15 cuesta lo mismo, pero si el bot dijo 18 al 21 con
    un precio que NO es de ninguna variante del 18, sigue violando."""
    otra = _fila("amor_de_dios", "2026-12-23", "DICIEMBRE 23 AL 27")
    msg = f"Del 18 al 21 de diciembre en Amor de Dios, Obsequio a Barú: {P(otra['multiple'])} en múltiple"
    assert v(msg) is not None


def test_plan_estandar_nombrado_con_el_precio_de_baru_no_pasa():
    msg = (f"Amor de Dios del 18 al 21 de diciembre, plan estándar, en múltiple: "
           f"{P(BARU['multiple'])}")
    assert v(msg) is not None


def test_dos_salidas_en_un_renglon_con_una_variante():
    """La variante SUMA filas, no reemplaza las de la fecha escrita."""
    once = _fila("amor_de_dios", "2026-12-11", "DICIEMBRE 11 AL 14")
    baru = _fila("amor_de_dios", "2026-12-11", "DICIEMBRE 11 AL 15")
    msg = (f"En Amor de Dios tenemos el 11 al 14 de diciembre a {P(once['multiple'])} "
           f"y el 11 al 15 (Obsequio a Barú) a {P(baru['multiple'])}.")
    assert v(msg, [DIC]) is None


def test_festivo_nombrado():
    festivo = _fila("amor_de_dios", "2026-10-30", "OCTUBRE 30")
    msg = f"Del 30 de octubre en Amor de Dios, el festivo queda en {P(festivo['multiple'])} 🌴"
    assert v(msg, [OCT]) is None


def test_lista_numerada_no_hereda_la_fecha_del_encabezado():
    """«1️⃣ …» y «2. …» son viñetas: cada opción es su propia salida."""
    msg = (f"Salidas de diciembre en Amor de Dios 📅\n"
           f"1. 18 al 21: {P(ESTANDAR['multiple'])}\n"
           f"2. Obsequio a Barú (3 noches / 4 días): {P(BARU['multiple'])}")
    assert v(msg) is None


# ---------------------------------------------------------------------------
# «desde» con negrita y contra la salida nombrada (QA bot 3, C05 r03)
# ---------------------------------------------------------------------------

def test_desde_con_negrita_de_una_salida_nombrada():
    cuatro = _fila("amor_de_dios", "2026-12-04", "DICIEMBRE 04 AL 07")
    ocho = _fila("amor_de_dios", "2026-12-08", "DICIEMBRE 08 AL 11")
    bien = f"1️⃣ *Del 4 al 7 de diciembre* en Amor de Dios: desde *{P(cuatro['multiple'])}*"
    mal = f"1️⃣ *Del 4 al 7 de diciembre* en Amor de Dios: desde *{P(ocho['multiple'])}*"
    assert v(bien) is None
    error = v(mal)
    assert error is not None and "desde" in error and P(cuatro["multiple"]) in error


def test_desde_de_una_variante_que_no_es_la_suya():
    fin_de_anio = _fila("amor_de_dios", "2026-12-29", "DICIEMBRE 29")
    navidad = _fila("amor_de_dios", "2026-12-23", "DICIEMBRE 23 AL 27")
    assert navidad["multiple"] < fin_de_anio["multiple"]
    msg = f"4️⃣ *Del 29 de dic al 2 de ene – Fin de Año*: desde *{P(navidad['multiple'])}*"
    assert v(msg) is not None
    assert v(msg.replace(P(navidad["multiple"]), P(fin_de_anio["multiple"]))) is None


def test_desde_del_mes_sin_salida_nombrada_sigue_igual():
    minimo = min(p["multiple"] for p in tarifario.planes_vigentes("amor_de_dios", HOY, 12))
    assert v(f"En diciembre, Amor de Dios arranca desde *{P(minimo)}* 🌴") is None
