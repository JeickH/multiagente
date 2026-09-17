"""La duración del plan: 3 días / 2 noches, y el otro que sí es de 4 / 3.

Bug real de producción: el bot le decía a la gente «4 días / 3 noches» un plan
que es de **3 días / 2 noches**. El tarifario nunca se equivocó —sus 102 filas
traen `noches` y `dias` correctos— y `consultar_tarifario` le entregaba el dato
al modelo en el mismo turno. Lo que pasaba es que el contexto del bot manda un
itinerario con **cuatro bloques de día** (🚌 Viernes de viaje, 📍 Sábado, 📍
Domingo, 🚌 Lunes de regreso), el modelo los contaba y le ganaba la frase del
prompt al dato de la herramienta. El viernes se viaja de noche en bus: se llega
el sábado, se duerme sábado y domingo, y el plan es de 3 días / 2 noches.

El CEO pidió que los dos planes queden fijados aquí:

- el **estándar** (viernes con lunes, y el de lunes con jueves): 2 noches / 3 días;
- el de **«Obsequio a Barú»** (viernes con martes): 3 noches / 4 días.

La fecha se inyecta (`hoy=`) como en todo `test_tarifario.py`: si no, la suite
empieza a fallar sola cuando pase la última salida del tarifario.

Los tests del guardarraíl mockean el modelo, así que no cuestan un centavo.
"""
from __future__ import annotations

import json
import re
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine, tarifario

CFG = LLM_CONFIG

# Mitad de la temporada: quedan salidas por delante y ya quedaron unas atrás.
HOY = date(2026, 8, 19)

MESES_PUBLICADOS = ("agosto", "septiembre", "octubre", "noviembre", "diciembre",
                    "enero")
HOTELES = ("", "Amor de Dios", "Piedra Mar", "Bohíos")

# "2 noches / 3 días" en cualquiera de los dos órdenes.
_PAR_RE = re.compile(
    r"(\d{1,2})\s*(noches?|d[ií]as?)\s*(?:[/·,\-–—]|y)?\s*"
    r"(\d{1,2})\s*(noches?|d[ií]as?)",
    re.IGNORECASE,
)


def duraciones_de(texto: str) -> set:
    """Los pares (noches, días) que aparecen en un texto."""
    salida = set()
    for n1, p1, n2, p2 in _PAR_RE.findall(texto or ""):
        primero_noche = p1.lower().startswith("noche")
        if primero_noche == p2.lower().startswith("noche"):
            continue
        noches, dias = (n1, n2) if primero_noche else (n2, n1)
        salida.add((int(noches), int(dias)))
    return salida


def duraciones_publicadas(hotel_clave=None, mes=None, hoy: date = HOY) -> set:
    """Las duraciones que el JSON publica, leídas sin pasar por el código.

    A propósito no se usa `tarifario.planes_vigentes`: si el filtro por `hoy` se
    rompiera, un test que reusara esa función se rompería igual y no habría
    manera de notarlo. Mismo criterio que `minimo_crudo` en `test_tarifario.py`.
    """
    return {
        (p["noches"], p["dias"])
        for p in tarifario._datos()["planes"]
        if (hotel_clave is None or hotel_clave in p["hoteles"])
        and (mes is None or p["mes"] == mes)
        and date.fromisoformat(p["inicio"]) >= hoy
    }


#: Etiqueta de salida («SEPTIEMBRE 11 AL 14») -> duraciones que el JSON le da.
#: Leído del JSON directo, sin pasar por el código que se prueba.
POR_ETIQUETA: dict = {}
for _p in tarifario._datos()["planes"]:
    POR_ETIQUETA.setdefault(_p["fecha"], set()).add((_p["noches"], _p["dias"]))


def etiqueta_de(linea: str):
    """La etiqueta de salida que menciona una línea de la respuesta.

    Se toma la más larga que calce, porque «SEPTIEMBRE 11 AL 14» es prefijo de
    «SEPTIEMBRE 11 AL 14 FESTIVO».
    """
    calzan = [e for e in POR_ETIQUETA if e in linea]
    return max(calzan, key=len) if calzan else None


def fin_de(plan: dict) -> date:
    """La fecha de regreso, leída de la etiqueta («SEPTIEMBRE 11 AL 14»).

    El JSON no trae columna de regreso, y derivarla de `dias` sería circular:
    estos tests existen justamente para verificar `dias`.
    """
    dia = int(re.search(r"AL\s+(\d+)", plan["fecha"]).group(1))
    fecha = date.fromisoformat(plan["inicio"])
    for _ in range(15):
        if fecha.day == dia and fecha != date.fromisoformat(plan["inicio"]):
            return fecha
        fecha += timedelta(days=1)
    raise AssertionError(f"etiqueta rara: {plan['fecha']}")


class TestLosDosPlanesDelTarifario:
    """El hecho del negocio, fijado contra los datos. Si alguien "corrige" el
    JSON pensando que viernes→lunes son 4 días, estos tests se lo dicen."""

    def test_el_estandar_de_fin_de_semana_es_de_2_noches_3_dias(self):
        viernes_lunes = [
            p for p in tarifario._datos()["planes"]
            if date.fromisoformat(p["inicio"]).weekday() == 4
            and fin_de(p).weekday() == 0
        ]
        assert len(viernes_lunes) == 47
        assert {(p["noches"], p["dias"]) for p in viernes_lunes} == {(2, 3)}

    def test_el_de_viernes_a_martes_es_de_3_noches_4_dias(self):
        """Son las de «Obsequio a Barú»: una noche más y un día más."""
        viernes_martes = [
            p for p in tarifario._datos()["planes"]
            if date.fromisoformat(p["inicio"]).weekday() == 4
            and fin_de(p).weekday() == 1
        ]
        assert len(viernes_martes) == 31
        assert {(p["noches"], p["dias"]) for p in viernes_martes} == {(3, 4)}

    def test_todas_las_de_obsequio_a_baru_son_de_3_noches_4_dias(self):
        """La etiqueta `plan` no es de fiar para agrupar —mezcla «Plan
        estándar» con salidas de distinto largo—, pero la de Barú sí es
        inequívoca, y es la que el CEO nombró."""
        baru = [
            p for p in tarifario._datos()["planes"]
            if "Barú" in (p.get("plan") or "")
        ]
        assert baru
        assert {(p["noches"], p["dias"]) for p in baru} == {(3, 4)}

    def test_el_de_lunes_a_jueves_tambien_es_de_2_noches_3_dias(self):
        lunes_jueves = [
            p for p in tarifario._datos()["planes"]
            if date.fromisoformat(p["inicio"]).weekday() == 0
            and fin_de(p).weekday() == 3
        ]
        assert len(lunes_jueves) == 6
        assert {(p["noches"], p["dias"]) for p in lunes_jueves} == {(2, 3)}


class TestNingunaDuracionSeInventa:
    """Hermano de `TestNingunaCifraSeInventa`: lo mismo, con las duraciones.

    Toda duración que salga de la herramienta tiene que existir como fila del
    tarifario de ese hotel y ese mes. Si mañana alguien pega un «4 días» a mano
    en un `f"..."`, este test lo caza.
    """

    @pytest.mark.parametrize("hotel", HOTELES)
    @pytest.mark.parametrize("mes", MESES_PUBLICADOS)
    def test_toda_duracion_de_la_respuesta_esta_publicada(self, hotel, mes):
        out = tarifario.consultar(CFG, hotel=hotel, mes=mes, hoy=HOY)
        num_mes = tarifario.normalizar_mes(mes)
        clave = tarifario.normalizar_hotel(hotel) if hotel else None
        # Sin hotel la respuesta compara los dos tarifarios, así que valen las
        # duraciones de cualquiera de ellos.
        if clave is None:
            permitidas = duraciones_publicadas(mes=num_mes)
        else:
            permitidas = duraciones_publicadas(clave, num_mes)
        inventadas = duraciones_de(out) - permitidas
        assert not inventadas, f"{hotel or 'ambos'}/{mes}: {sorted(inventadas)}"

    @pytest.mark.parametrize("hotel", HOTELES)
    @pytest.mark.parametrize("mes", MESES_PUBLICADOS)
    def test_cada_salida_trae_la_duracion_de_SU_fila(self, hotel, mes):
        """El chequeo fino: todos los meses publican las dos duraciones, así
        que «está publicada» no basta — la del *SEPTIEMBRE 11 AL 14* no puede
        salir con la del *11 AL 15*, que arranca el mismo viernes."""
        out = tarifario.consultar(CFG, hotel=hotel, mes=mes, hoy=HOY)
        for linea in out.split("\n"):
            if not linea.strip().startswith("· "):
                continue
            etiqueta = etiqueta_de(linea)
            assert etiqueta, linea
            assert duraciones_de(linea) == POR_ETIQUETA[etiqueta], linea


class TestCadaSalidaOfrecidaTraeSuDuracion:
    """Ninguna salida se ofrece sin la duración al lado.

    Donde el modelo se queda sin el dato, lo inventa: por eso la duración viaja
    pegada a cada fecha que la herramienta pone sobre la mesa, incluidas las que
    ofrece como alternativa.
    """

    @pytest.mark.parametrize("hotel", HOTELES)
    @pytest.mark.parametrize("mes", MESES_PUBLICADOS)
    def test_toda_linea_de_salida_lleva_su_duracion(self, hotel, mes):
        out = tarifario.consultar(CFG, hotel=hotel, mes=mes, hoy=HOY)
        for linea in out.split("\n"):
            if not linea.strip().startswith("· "):
                continue
            assert duraciones_de(linea), linea

    def test_las_fechas_cercanas_van_con_duracion(self):
        """El bloque de «no hay salida que arranque el <fecha>»: antes ofrecía
        dos fechas peladas y ahí el modelo volvía a contar bloques."""
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre",
            fecha="2026-09-20", hoy=HOY,
        )
        linea = [l for l in out.split("\n") if "no hay salida que arranque" in l][0]
        assert len(duraciones_de(linea)) >= 1
        # Una duración por cada fecha ofrecida.
        assert linea.count("noches /") == 2

    @pytest.mark.parametrize("mes", MESES_PUBLICADOS)
    def test_el_desde_del_mes_dice_cuanto_dura_esa_salida(self, mes):
        out = tarifario.consultar(CFG, hotel="Amor de Dios", mes=mes, hoy=HOY)
        desde = [l for l in out.split("\n") if "«desde» de" in l]
        for linea in desde:
            assert duraciones_de(linea), linea

    def test_la_busqueda_por_presupuesto_tambien(self):
        out = tarifario.consultar(CFG, presupuesto="450 mil", hoy=HOY)
        for linea in out.split("\n"):
            if linea.strip().startswith("· "):
                assert duraciones_de(linea), linea


class TestLosDosPlanesEnLaRespuesta:
    """Lo que el CEO pidió textualmente: los dos planes, cada uno con lo suyo.

    Las dos salidas arrancan el mismo viernes 11 de septiembre y se diferencian
    solo en el regreso, que es justo el caso donde el bot mezclaba las dos.
    """

    ESTANDAR = "SEPTIEMBRE 11 AL 14"
    BARU = "SEPTIEMBRE 11 AL 15"

    def _linea(self, out: str, fecha: str) -> str:
        candidatas = [
            l for l in out.split("\n")
            if l.strip().startswith("· ") and fecha in l
        ]
        assert candidatas, f"no apareció {fecha}"
        return candidatas[0]

    def test_la_estandar_sale_con_2_noches_3_dias(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY
        )
        assert duraciones_de(self._linea(out, self.ESTANDAR)) == {(2, 3)}

    def test_la_de_baru_sale_con_3_noches_4_dias(self):
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY
        )
        assert duraciones_de(self._linea(out, self.BARU)) == {(3, 4)}

    def test_las_dos_conviven_sin_contagiarse_la_duracion(self):
        """El mes publica las dos, y cada línea trae la suya y solo la suya."""
        out = tarifario.consultar(
            CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY
        )
        estandar = self._linea(out, self.ESTANDAR)
        baru = self._linea(out, self.BARU)
        assert (3, 4) not in duraciones_de(estandar)
        assert (2, 3) not in duraciones_de(baru)
        assert duraciones_de(out) == {(2, 3), (3, 4)}


# --------------------------------------------------------------------------
# El guardarraíl determinista, con el modelo mockeado.
#
# Los resultados de la tool son la salida REAL de `consultar()`, nunca un
# string fabricado. La primera versión de estos tests usaba uno inventado con
# una sola duración y por eso pasaban todos mientras el bug seguía vivo: en
# septiembre conviven 2n/3d y 3n/4d, y ahí es donde el guardarraíl tenía que
# distinguir. Es el patrón que este proyecto ya conoce — 63 chequeos verdes con
# el bot perdiendo ventas igual.
# --------------------------------------------------------------------------

#: Septiembre publica las DOS duraciones, y las dos salidas del 11 arrancan el
#: mismo viernes: la estándar regresa el 14 y la de Barú el 15.
TARIFARIO_SEPTIEMBRE = tarifario.consultar(
    CFG, hotel="Amor de Dios", mes="septiembre", hoy=HOY
)

#: Un ámbito con UNA sola duración, para el caso en que generalizar sí vale.
#: Se busca en los datos por presupuesto (ninguna de Barú cabe en $460.000) en
#: vez de inventarlo: todos los meses del tarifario publican las dos.
TARIFARIO_UNA_SOLA = tarifario.consultar(
    CFG, hotel="Amor de Dios", presupuesto="460 mil", hoy=HOY
)

ESTANDAR = "SEPTIEMBRE 11 AL 14"      # 2 noches / 3 días
BARU = "SEPTIEMBRE 11 AL 15"          # 3 noches / 4 días


def test_los_dos_ambitos_de_prueba_son_los_que_se_creen():
    """Si el Excel cambia y estos supuestos dejan de valer, el resto de la
    clase se vuelve decorativo sin avisar. Se verifica aquí, una vez."""
    assert duraciones_de(TARIFARIO_SEPTIEMBRE) == {(2, 3), (3, 4)}
    assert ESTANDAR in TARIFARIO_SEPTIEMBRE and BARU in TARIFARIO_SEPTIEMBRE
    assert duraciones_de(TARIFARIO_UNA_SOLA) == {(2, 3)}


class BotViajesFake:
    id = 12
    engine = "llm"

    def __init__(self, cfg: dict):
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


def _resp(content, stop_reason="end_turn"):
    return {"content": content, "stop_reason": stop_reason}


def _texto(t):
    return [{"type": "text", "text": t}]


def _tool_use(name, tool_input, tid="t1"):
    return {"type": "tool_use", "id": tid, "name": name, "input": tool_input}


def _corre_con_tool(resultado_tool, textos_del_modelo, cfg=None):
    """Un turno completo con el modelo mockeado y la tool devolviendo lo dado.

    `textos_del_modelo` es la cola de respuestas de texto: la segunda solo se
    usa si el guardarraíl tumbó la primera y pidió reintento.
    """
    cola = list(textos_del_modelo)

    def responder(model_id, system, messages, tools):
        ultimo = messages[-1]["content"]
        es_resultado = (
            isinstance(ultimo, list) and ultimo
            and isinstance(ultimo[0], dict)
            and ultimo[0].get("type") == "tool_result"
        )
        es_correccion = isinstance(ultimo, str) and "ALTO:" in ultimo
        if es_resultado or es_correccion:
            return _resp(_texto(cola.pop(0)))
        return _resp(
            [_tool_use("consultar_tarifario", {"mes": "septiembre"})],
            stop_reason="tool_use",
        )

    with patch.object(llm_engine, "_invoke_model") as mock, \
            patch.object(llm_engine, "_run_tool") as run_tool:
        run_tool.return_value = (resultado_tool, False)
        mock.side_effect = responder
        out = llm_engine.advance(
            BotViajesFake(cfg if cfg is not None else dict(LLM_CONFIG)),
            {"history": []},
            "¿cuántos días dura el plan?",
        )
    textos = [a["payload"]["text"] for a in out["actions"] if a["type"] == "say"]
    return textos, mock.call_count


class TestElBugDeProduccion:
    """El caso reportado, contra la respuesta real de la herramienta.

    El bot está vendiendo la salida del *11 al 14* —2 noches / 3 días— y dice
    «4 días y 3 noches». Ese par existe en septiembre, pero es el de la salida
    de Barú, que regresa el 15. Un guardarraíl que mire el menú del mes en vez
    de la salida deja pasar esto.
    """

    def test_pegarle_a_una_salida_la_duracion_de_la_otra_dispara(self):
        assert llm_engine._viola_duracion(
            LLM_CONFIG,
            [f"La del *{ESTANDAR}* es de 4 días y 3 noches 🌴"],
            [TARIFARIO_SEPTIEMBRE],
        )

    def test_la_misma_frase_sin_nombrar_salida_tambien_dispara(self):
        """«El plan es de 4 días y 3 noches» es falso para media temporada."""
        assert llm_engine._viola_duracion(
            LLM_CONFIG,
            ["El plan es de 4 días y 3 noches 🌴"],
            [TARIFARIO_SEPTIEMBRE],
        )

    def test_noches_sueltas_sin_salida_en_un_mes_de_dos_duraciones(self):
        assert llm_engine._viola_duracion(
            LLM_CONFIG, ["Son 3 noches en el hotel 🌴"], [TARIFARIO_SEPTIEMBRE]
        )

    def test_no_llega_al_cliente_y_hay_reintento(self):
        malo = f"La del *{ESTANDAR}* es de 4 días y 3 noches 🌴"
        bueno = f"La del *{ESTANDAR}* es de 2 noches / 3 días 🌴"
        textos, llamadas = _corre_con_tool(TARIFARIO_SEPTIEMBRE, [malo, bueno])
        assert malo not in textos
        assert bueno in textos
        # 3 llamadas: la que pidió la tool, la que se descartó y el reintento.
        assert llamadas == 3


class TestCadaSalidaConSuDuracion:
    """Lo que sí tiene que pasar: la duración pegada a la salida que es."""

    @pytest.mark.parametrize("texto", [
        f"La del *{ESTANDAR}* son 2 noches / 3 días 🌴",
        f"La del *{ESTANDAR}* son 3 días y 2 noches 🌴",
        f"Sale el *{ESTANDAR}*: 2 noches / 3 días, desde $459.000 👌",
        f"Son *3 días y 2 noches* 🌴 saliendo el {ESTANDAR}.",
        "La del *11 al 14* son 2 noches / 3 días 🌴",     # sin el mes escrito
    ])
    def test_la_estandar_con_la_suya_pasa(self, texto):
        assert not llm_engine._viola_duracion(
            LLM_CONFIG, [texto], [TARIFARIO_SEPTIEMBRE]
        )

    @pytest.mark.parametrize("texto", [
        f"La del *{BARU}* con Obsequio a Barú son 3 noches / 4 días ✨",
        "La del *11 al 15* son 4 días y 3 noches ✨",
    ])
    def test_la_de_baru_con_la_suya_pasa(self, texto):
        assert not llm_engine._viola_duracion(
            LLM_CONFIG, [texto], [TARIFARIO_SEPTIEMBRE]
        )

    def test_las_dos_en_el_mismo_mensaje_cada_una_con_la_suya(self):
        texto = (
            f"Tenemos dos opciones esa semana 🌴 la del *{ESTANDAR}* que son "
            f"2 noches / 3 días, y la del *{BARU}* con Obsequio a Barú que son "
            f"3 noches / 4 días ✨"
        )
        assert not llm_engine._viola_duracion(
            LLM_CONFIG, [texto], [TARIFARIO_SEPTIEMBRE]
        )

    def test_cruzarlas_dispara(self):
        """Las mismas dos salidas con las duraciones intercambiadas."""
        texto = (
            f"la del *{ESTANDAR}* son 3 noches / 4 días y la del *{BARU}* son "
            f"2 noches / 3 días"
        )
        assert llm_engine._viola_duracion(
            LLM_CONFIG, [texto], [TARIFARIO_SEPTIEMBRE]
        )

    def test_mas_duraciones_que_salidas_nombradas_dispara(self):
        texto = f"La del *{ESTANDAR}* son 2 noches / 3 días, y también hay de 3 noches"
        assert llm_engine._viola_duracion(
            LLM_CONFIG, [texto], [TARIFARIO_SEPTIEMBRE]
        )

    def test_el_turno_bueno_de_baru_llega_al_cliente(self):
        bueno = f"La del *{BARU}* son 3 noches / 4 días ✨"
        textos, llamadas = _corre_con_tool(
            TARIFARIO_SEPTIEMBRE, [bueno, "no debió llegar aquí"]
        )
        assert bueno in textos
        assert llamadas == 2


class TestGeneralizarSoloCuandoTodasDuranIgual:
    """Sin salida nombrada, la duración es una afirmación sobre todo el ámbito.

    Vale si el resultado trae una sola duración, y no vale si trae dos: ahí
    «el plan es de X noches» es falso para la mitad de lo que se ofreció.
    """

    @pytest.mark.parametrize("texto", [
        "Son 3 días / 2 noches 🌴",
        "El plan es de 2 noches y 3 días 🌴",
        "Son 2 noches de alojamiento 🌴",
    ])
    def test_con_un_solo_plan_en_el_resultado_pasa(self, texto):
        assert not llm_engine._viola_duracion(
            LLM_CONFIG, [texto], [TARIFARIO_UNA_SOLA]
        )

    @pytest.mark.parametrize("texto", [
        "Son 3 días / 2 noches 🌴",
        "Son 2 noches de alojamiento 🌴",
    ])
    def test_las_mismas_frases_con_dos_planes_en_el_resultado_disparan(
        self, texto
    ):
        assert llm_engine._viola_duracion(
            LLM_CONFIG, [texto], [TARIFARIO_SEPTIEMBRE]
        )

    def test_una_duracion_ajena_no_pasa_ni_con_un_solo_plan(self):
        assert llm_engine._viola_duracion(
            LLM_CONFIG, ["Son 4 días / 3 noches 🌴"], [TARIFARIO_UNA_SOLA]
        )


class TestElGuardarrailNoMuerdeLoLegitimo:
    """Un guardarraíl con falsos positivos se desactiva solo, y mientras tanto
    le tumba el turno a un bot que estaba respondiendo bien."""

    @pytest.mark.parametrize("frase", [
        "El pago total va de 8 a 10 días hábiles antes del viaje 🤗",
        "Apartas tu cupo con un anticipo del 30% y pagas 8 días antes.",
        "La hora exacta se confirma 1 día antes por el grupo de WhatsApp.",
        "Te respondo en menos de 24 horas 😊",
        "Salimos entre 6:00 y 9:00 pm y llegamos al otro día.",
        "El bici-taxi al Malecón vale entre $3.000 y $4.000 por persona.",
    ])
    @pytest.mark.parametrize("resultado", [[], [TARIFARIO_SEPTIEMBRE]])
    def test_frases_con_dias_que_no_son_duracion(self, frase, resultado):
        assert not llm_engine._viola_duracion(LLM_CONFIG, [frase], resultado)

    def test_un_turno_sin_duracion_nunca_dispara(self):
        assert not llm_engine._viola_duracion(
            LLM_CONFIG, ["¿Para qué mes lo estás pensando? 😊"],
            [TARIFARIO_SEPTIEMBRE],
        )

    def test_sin_tarifario_el_guardarrail_no_aplica(self):
        """Otros bots (mascotas, Jerarquía) hablan de noches legítimamente."""
        assert not llm_engine._viola_duracion(
            {"context_key": "gloma"}, ["son 3 noches de hospedaje"], []
        )

    def test_el_texto_del_itinerario_completo_no_dispara(self):
        """Lo que más manda el bot: el itinerario, que no trae ninguna cifra de
        duración. Si esto disparara, el primer mensaje quedaría inservible."""
        from pathlib import Path

        doc = Path(llm_engine.__file__).resolve().parent.parent / "bot_contexts"
        itinerario = [
            l for l in (doc / "demo_viajes.md").read_text(encoding="utf-8").split("\n")
            if l.startswith(("🚌", "📍", "⚠️"))
        ]
        assert itinerario
        assert not llm_engine._viola_duracion(
            LLM_CONFIG, itinerario, [TARIFARIO_SEPTIEMBRE]
        )

    def test_sin_haber_llamado_la_herramienta_cualquier_duracion_dispara(self):
        """No es un falso positivo: es la regla. Sin consultar no hay duración
        que decir, igual que no hay precio."""
        assert llm_engine._viola_duracion(
            LLM_CONFIG, [f"La del *{ESTANDAR}* son 2 noches / 3 días"], []
        )


class TestComoSeLeeElResultadoDeLaHerramienta:
    """El parser que empareja salida con duración, a solas."""

    def test_empareja_cada_linea_con_su_salida(self):
        mapa = {}
        for ref, clase, valor in llm_engine._menciones_de_duracion(
            TARIFARIO_SEPTIEMBRE
        ):
            if clase == "par" and ref is not None:
                mapa.setdefault(ref, set()).add(valor)
        assert mapa[(11, 14)] == {(2, 3)}
        assert mapa[(11, 15)] == {(3, 4)}

    def test_la_duracion_hereda_la_salida_nombrada_antes(self):
        menciones = llm_engine._menciones_de_duracion(
            "la del 11 al 14 son 2 noches / 3 días y la del 11 al 15 son "
            "3 noches / 4 días"
        )
        assert menciones == [
            ((11, 14), "par", (2, 3)),
            ((11, 15), "par", (3, 4)),
        ]

    def test_con_una_sola_salida_la_duracion_la_toma_aunque_vaya_antes(self):
        assert llm_engine._menciones_de_duracion(
            "son 3 días y 2 noches saliendo el 11 al 14"
        ) == [((11, 14), "par", (2, 3))]

    def test_las_noches_del_par_no_se_cuentan_dos_veces(self):
        assert llm_engine._menciones_de_duracion("2 noches / 3 días") == [
            (None, "par", (2, 3))
        ]

    def test_un_rango_con_a_suelta_no_es_una_salida(self):
        """«de 8 a 10 días hábiles» no puede leerse como la salida 8→10."""
        assert llm_engine._menciones_de_duracion(
            "el pago va de 8 a 10 días hábiles antes"
        ) == []
