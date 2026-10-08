"""Lo que el tarifario le entrega al bot 2: extras, «desde», flyer y salidas.

Todo se compara contra los datos (`tarifario_covenas.json`, el prompt del bot
1, el catálogo de medios), nunca contra una cifra escrita en esta prueba: si
el CEO cambia de temporada, estas pruebas siguen diciendo la verdad.
"""
from __future__ import annotations

import inspect
import re
from datetime import date
from pathlib import Path

import pytest

from app.data.bot_viajes import LLM_CONFIG, MEDIA
from app.services import tarifario

_PROMPT_BOT1 = (
    Path(tarifario.__file__).resolve().parent.parent / "bot_contexts" / "demo_viajes.md"
)


def _planes():
    return tarifario._datos()["planes"]


def _pesos_en(texto: str):
    return {int(m.replace(".", "")) for m in re.findall(r"\$(\d{1,3}(?:\.\d{3})+)", texto)}


# ---------------------------------------------------------------------------
# extras() y linea_ninos()
# ---------------------------------------------------------------------------

class TestExtras:
    def test_trae_las_llaves_del_contrato(self):
        e = tarifario.extras()
        assert e["anticipo_pct"] == 30
        assert [(n["edad_min"], n["edad_max"]) for n in e["ninos"]] == [(0, 2), (3, 4)]
        assert all(isinstance(n["valor"], int) and n["valor"] > 0 for n in e["ninos"])
        assert e["nota_ninos"]

    def test_los_valores_de_ninos_son_los_del_prompt_del_bot_1(self):
        """Se movieron del `.md` al JSON con el mismo valor (y el `.md` del bot
        1 no se tocó: sigue teniéndolos)."""
        prompt = _PROMPT_BOT1.read_text(encoding="utf-8")
        seccion = prompt.split("### Niños", 1)[1].split("###", 1)[0]
        menor2 = re.search(r"Menores de \*\*2 años\*\*.*?\$(\d{1,3}(?:\.\d{3})+)", seccion)
        de3a4 = re.search(r"De \*\*3 a 4 años\*\*.*?\$(\d{1,3}(?:\.\d{3})+)", seccion)
        assert menor2 and de3a4, "el prompt del bot 1 perdió la sección de niños"
        valores = {(n["edad_min"], n["edad_max"]): n["valor"] for n in tarifario.extras()["ninos"]}
        assert valores[(0, 2)] == int(menor2.group(1).replace(".", ""))
        assert valores[(3, 4)] == int(de3a4.group(1).replace(".", ""))

    def test_el_anticipo_es_el_del_prompt_del_bot_1(self):
        prompt = _PROMPT_BOT1.read_text(encoding="utf-8")
        m = re.search(r"anticipo del (\d+)% del valor", prompt)
        assert m and int(m.group(1)) == tarifario.extras()["anticipo_pct"]

    def test_los_otros_montos_del_itinerario_estan_en_extras(self):
        """Canoa y bici-taxi viven en el itinerario del prompt: el bot los
        cita y el guardarraíl tiene que conocerlos."""
        prompt = _PROMPT_BOT1.read_text(encoding="utf-8")
        itinerario = prompt.split("ITINERARIO", 1)[1].split("### Precios", 1)[0]
        en_prompt = _pesos_en(itinerario)
        en_extras = set()
        for o in tarifario.extras()["otros"]:
            en_extras |= {o[k] for k in ("valor", "valor_min", "valor_max") if k in o}
        assert en_prompt and en_prompt <= en_extras

    def test_devuelve_una_copia(self):
        e = tarifario.extras()
        e["ninos"][0]["valor"] = 1
        assert tarifario.extras()["ninos"][0]["valor"] != 1

    def test_linea_ninos_lleva_los_valores_del_json(self):
        linea = tarifario.linea_ninos()
        assert "\n" not in linea
        assert _pesos_en(linea) == {n["valor"] for n in tarifario.extras()["ninos"]}
        assert tarifario.extras()["nota_ninos"] in linea

    def test_linea_ninos_vacia_sin_datos(self, monkeypatch):
        monkeypatch.setattr(tarifario, "_extras_crudos", lambda: {})
        assert tarifario.linea_ninos() == ""


class TestLineaExtras:
    def test_dos_lineas_con_ninos_anticipo_y_opcionales(self):
        linea = tarifario.linea_extras()
        e = tarifario.extras()
        assert linea.count("\n") == 1
        assert linea.splitlines()[0] == tarifario.linea_ninos()
        assert f"{e['anticipo_pct']}%" in linea
        assert e["saldo_texto"] in linea
        for o in e["otros"]:
            assert o["concepto"] in linea
            for k in ("valor", "valor_min", "valor_max"):
                if k in o:
                    assert tarifario._pesos(o[k]) in linea

    def test_lo_que_falta_no_se_dice(self, monkeypatch):
        monkeypatch.setattr(tarifario, "_extras_crudos", lambda: {"anticipo_pct": 30})
        linea = tarifario.linea_extras()
        assert "30%" in linea and "NIÑOS" not in linea and "OPCIONALES" not in linea
        monkeypatch.setattr(tarifario, "_extras_crudos", lambda: {})
        assert tarifario.linea_extras() == ""

    def test_el_guardarrail_acepta_lo_que_dice_la_linea(self):
        """Si el bot repite la línea tal cual, ningún monto suyo es inventado."""
        from app.services.guardarrail_precio import viola_precio

        assert viola_precio(
            tarifario.linea_extras(), resultados_precios=[], desde_validos=set(),
            cifras_cliente=set(), extras=tarifario.extras(),
        ) is None


# ---------------------------------------------------------------------------
# desde_temporada()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hoy", [
    date(2026, 7, 1), date(2026, 10, 7), date(2026, 12, 9), date(2026, 12, 15),
    date(2027, 1, 13), date(2027, 1, 15),
])
def test_desde_temporada_es_el_minimo_de_lo_que_queda(hoy):
    esperado = min(
        min(p["multiple"], p["doble"]) for p in _planes()
        if date.fromisoformat(p["inicio"]) >= hoy
    )
    assert tarifario.desde_temporada(hoy) == esperado


def test_desde_temporada_no_cuenta_salidas_pasadas():
    """El 9 de diciembre ya salió la del 8 (la más barata de Amor de Dios),
    pero sigue la del 14 con el mismo valor; el 15 ya no queda ninguna de esas
    dos y el «desde» tiene que subir."""
    antes = tarifario.desde_temporada(date(2026, 12, 8))
    despues = tarifario.desde_temporada(date(2026, 12, 15))
    assert despues > antes


def test_desde_temporada_sin_salidas_es_none():
    assert tarifario.desde_temporada(date(2027, 6, 1)) is None


# ---------------------------------------------------------------------------
# flyer_apertura()
# ---------------------------------------------------------------------------

def _flyers_del_mes(mes):
    return {
        k for k, v in MEDIA.items()
        if isinstance(v, dict) and isinstance(v.get("meses"), list) and mes in v["meses"]
    }


@pytest.mark.parametrize("hoy", [
    date(2026, 7, 20), date(2026, 8, 1), date(2026, 9, 15), date(2026, 10, 7),
    date(2026, 11, 1), date(2026, 12, 2), date(2027, 1, 2),
])
def test_flyer_apertura_es_del_mes_en_curso(hoy):
    clave = tarifario.flyer_apertura(hoy)
    assert clave in _flyers_del_mes(hoy.month)
    assert MEDIA[clave]["hotel"] != "bohios"


def test_flyer_apertura_es_el_del_hotel_mas_barato_del_mes():
    hoy = date(2026, 10, 7)
    clave = tarifario.flyer_apertura(hoy)
    hotel = MEDIA[clave]["hotel"]
    minimos = {
        h: min(p["multiple"] for p in tarifario.planes_vigentes(h, hoy, 10))
        for h in ("amor_de_dios", "piedra_mar")
    }
    assert minimos[hotel] == min(minimos.values())


def test_flyer_apertura_pasa_al_mes_siguiente_si_el_mes_ya_no_tiene_salidas():
    """El 31 de octubre ya salió la última de octubre (la del 30): el flyer
    tiene que ser el de noviembre, no uno de un mes sin nada que vender."""
    hoy = date(2026, 10, 31)
    assert not any(
        tarifario.planes_vigentes(h, hoy, 10) for h in ("amor_de_dios", "piedra_mar")
    )
    assert tarifario.flyer_apertura(hoy) in _flyers_del_mes(11)


def test_flyer_apertura_lee_la_media_del_cfg():
    cfg = {"media": {"solo_este": {"hotel": "piedra_mar", "meses": [10]}}}
    assert tarifario.flyer_apertura(date(2026, 10, 7), cfg) == "solo_este"
    assert tarifario.flyer_apertura(date(2026, 10, 7), {"media": {}}) is None


def test_flyer_apertura_con_la_config_del_bot_1_coincide_con_el_default():
    hoy = date(2026, 10, 7)
    assert tarifario.flyer_apertura(hoy, LLM_CONFIG) == tarifario.flyer_apertura(hoy)


def test_flyer_apertura_sin_temporada_es_none():
    assert tarifario.flyer_apertura(date(2027, 6, 1)) is None


# ---------------------------------------------------------------------------
# salidas_restantes()
# ---------------------------------------------------------------------------

def test_salidas_restantes_solo_las_que_no_han_pasado():
    hoy = date(2026, 10, 17)
    salidas = tarifario.salidas_restantes(10, 2026, "Amor de Dios", hoy)
    etiquetas = [s["etiqueta"] for s in salidas]
    assert etiquetas == ["23 al 26", "30 al 2 de noviembre"]
    for s in salidas:
        fila = next(
            p for p in tarifario.planes_vigentes("amor_de_dios", hoy, 10)
            if tarifario.etiqueta_corta(p["fecha"]) == s["etiqueta"]
        )
        assert s["desde"] == fila["multiple"]


def test_salidas_restantes_separa_el_plan_de_baru():
    """El 16 al 19 y el 16 al 20 salen el mismo día pero son planes
    distintos."""
    etiquetas = [s["etiqueta"] for s in
                 tarifario.salidas_restantes(10, 2026, None, date(2026, 10, 7))]
    assert "16 al 19" in etiquetas and "16 al 20" in etiquetas
    assert etiquetas == sorted(etiquetas, key=lambda e: etiquetas.index(e))


def test_salidas_restantes_sin_hotel_toma_el_minimo_de_los_dos():
    hoy = date(2026, 10, 7)
    todas = {s["etiqueta"]: s["desde"] for s in tarifario.salidas_restantes(10, 2026, None, hoy)}
    amor = {s["etiqueta"]: s["desde"] for s in tarifario.salidas_restantes(10, 2026, "amor de dios", hoy)}
    piedra = {s["etiqueta"]: s["desde"] for s in tarifario.salidas_restantes(10, 2026, "piedra mar", hoy)}
    for et, v in todas.items():
        assert v == min(x for x in (amor.get(et), piedra.get(et)) if x is not None)


def test_salidas_restantes_bohios_usa_la_tabla_de_amor_de_dios():
    hoy = date(2026, 10, 7)
    assert (tarifario.salidas_restantes(10, 2026, "Bohíos", hoy)
            == tarifario.salidas_restantes(10, 2026, "Amor de Dios", hoy))


def test_salidas_restantes_casos_vacios():
    hoy = date(2026, 10, 7)
    assert tarifario.salidas_restantes(10, 2026, "Hotel Inventado", hoy) == []
    assert tarifario.salidas_restantes(10, 2027, None, hoy) == []      # otro año
    assert tarifario.salidas_restantes(9, 2026, None, hoy) == []       # ya pasó
    assert tarifario.salidas_restantes(10, 2026, None, date(2026, 10, 31)) == []


def test_salidas_restantes_enero_del_anio_siguiente():
    salidas = tarifario.salidas_restantes(1, 2027, None, date(2026, 10, 7))
    assert salidas and salidas[0]["etiqueta"].startswith("4 al")


@pytest.mark.parametrize("fecha,esperada", [
    ("OCTUBRE 16 AL 19", "16 al 19"),
    ("OCTUBRE 16 AL 20 (Obsequio a Barú)", "16 al 20"),
    ("DICIEMBRE 08 AL 11", "8 al 11"),
    ("OCTUBRE 30 AL 02 DE NOVIEMBRE FESTIVO", "30 al 2 de noviembre"),
    ("DICIEMBRE 29 AL 02 DE ENERO (Fin de Año)", "29 al 2 de enero"),
])
def test_etiqueta_corta(fecha, esperada):
    assert tarifario.etiqueta_corta(fecha) == esperada


# ---------------------------------------------------------------------------
# Lo nuevo no trae cifras a mano y no toca lo viejo
# ---------------------------------------------------------------------------

def test_lo_nuevo_no_tiene_precios_escritos_a_mano():
    fuente = "".join(
        inspect.getsource(f) for f in (
            tarifario.extras, tarifario.linea_ninos, tarifario.desde_temporada,
            tarifario.flyer_apertura, tarifario._mes_de_apertura,
            tarifario.salidas_restantes, tarifario.etiqueta_corta,
            tarifario.linea_extras, tarifario._linea_anticipo, tarifario._linea_otros,
        )
    )
    assert not re.search(r"\d{2,3}[.,]?000", fuente)


def test_consultar_no_cambio_no_trae_ninos():
    """El resultado del bot 1 no cambia: la línea de niños es del bot 2 y la
    pega el motor solo con su flag."""
    texto = tarifario.consultar(LLM_CONFIG, mes="octubre", hoy=date(2026, 10, 7))
    assert "NIÑOS" not in texto
    for n in tarifario.extras()["ninos"]:
        assert tarifario._pesos(n["valor"]) not in texto
