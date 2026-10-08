"""Guiones del bot 2 (variante B) de Arranquemos Pues contra Claude de verdad.

**Cuesta plata.** Vive bajo `tests/viajes/costo/`, así que queda marcado
`costo` y no corre sin `--con-costo`. Una pasada de los 11 guiones cuesta del
orden de US$ 0,30; con repeticiones, multiplicar.

    cd backend && source .venv/bin/activate
    APP_ENCRYPTION_KEY=<fernet efímera> TZ=UTC REPETICIONES_B=6 \
        python -m pytest --con-costo -m costo -q \
        tests/viajes/costo/test_guiones_variante_b.py

Variables:
  - `REPETICIONES_B` (default 1): cuántas veces corre cada guion. Para comparar
    dos versiones del prompt hacen falta ≥12 (gotcha «las reglas del prompt se
    diluyen»): una corrida no dice nada.
  - `TOPE_USD_B` (default 7.5): tope duro de gasto. Se suma en un libro
    compartido (`costo.jsonl` en la carpeta de transcripciones), así que vale
    aunque se lancen varios pytest en paralelo. Al llegar al tope, el resto de
    los guiones se salta.
  - `TRANSCRIPCIONES_B_DIR`: dónde se guardan. Por defecto
    `entregables/transcripciones_b/<fecha>/` (carpeta git-ignorada: las
    transcripciones son del modelo, pero no se versionan).

Por qué se guarda TODO (rondas, correcciones, recortes del motor) y no solo el
pass/fail: la lección del 19-ago-2026 — doce guiones pasaron 63 chequeos y el
bot igual perdía ventas. Los chequeos de abajo cubren lo afirmable sin leer;
las transcripciones están para que una persona las lea. Por eso casi todos los
chequeos son **blandos** (se anotan en el JSON y no tumban el test) y solo los
que no pueden fallar nunca son **duros**: precio de otra fila, cierre de una
venta en pausa, la promo de $350.000 sin traspaso.

Los montos esperados no se escriben a mano: salen del tarifario del día
(`tarifario.consultar`), igual que los saca el bot.

Nombres y documentos inventados (CLAUDE.md #8: el repo es público).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import pytest

from app.data.bot_viajes import MEDIA
from app.data.bot_viajes_b import LLM_CONFIG_B
from app.services import guardarrail_precio, llm_engine, tarifario

REPETICIONES = max(1, int(os.getenv("REPETICIONES_B", "1") or 1))
TOPE_USD = float(os.getenv("TOPE_USD_B", "7.5") or 7.5)
_RAIZ = Path(__file__).resolve().parents[4]
CARPETA = Path(
    os.getenv("TRANSCRIPCIONES_B_DIR")
    or _RAIZ / "entregables" / "transcripciones_b" / tarifario.hoy_colombia().isoformat()
)
LIBRO = CARPETA / "costo.jsonl"

_CLAVE_DE_URL = {v.get("url"): k for k, v in MEDIA.items() if v.get("url")}
_FLYERS = {k for k, v in MEDIA.items() if v.get("meses")}


# ---------------------------------------------------------------------------
# Los dos bots, sin base de datos
# ---------------------------------------------------------------------------

class BotViajesB:
    """El bot 2 tal como lo despacha `app/data/bot_viajes_b.py`."""

    id = 40
    engine = "llm"
    status = "active"

    def __init__(self, **extra: Any) -> None:
        cfg: Dict[str, Any] = dict(LLM_CONFIG_B)
        cfg.update(extra)
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


def _bot_a():
    from tests.viajes.conftest import BotViajes

    return BotViajes()


# ---------------------------------------------------------------------------
# Libro de gasto compartido entre procesos
# ---------------------------------------------------------------------------

def _gastado() -> float:
    if not LIBRO.exists():
        return 0.0
    total = 0.0
    for linea in LIBRO.read_text(encoding="utf-8").splitlines():
        try:
            total += float(json.loads(linea).get("usd") or 0)
        except ValueError:
            continue
    return total


@pytest.fixture
def presupuesto(medidor):
    CARPETA.mkdir(parents=True, exist_ok=True)
    if _gastado() >= TOPE_USD:
        pytest.skip(f"tope de gasto alcanzado (US$ {TOPE_USD})")
    antes = medidor.usd
    yield
    with LIBRO.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"usd": medidor.usd - antes, "t": time.time()}) + "\n")


# ---------------------------------------------------------------------------
# Grabadora: rondas del modelo, correcciones y recortes del motor
# ---------------------------------------------------------------------------

class _Capturador(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self.registros: List[Dict[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.registros.append({"nivel": record.levelname, "msg": record.getMessage()})


@pytest.fixture
def grabadora(modelo_real, monkeypatch):
    """Envuelve lo medido por `modelo_real` y anota cada ronda, cada disparo de
    guardarraíl y cada recorte del post-proceso (que solo deja huella en el
    log, sin contenido del cliente)."""
    g: Dict[str, Any] = {"rondas": [], "disparos": [], "logs": _Capturador()}
    log = logging.getLogger(llm_engine.__name__)
    nivel_previo = log.level
    log.setLevel(logging.INFO)
    log.addHandler(g["logs"])

    medido = llm_engine._invoke_model

    def _ronda(model_id, system, messages, tools):
        t0 = time.monotonic()
        data = medido(model_id, system, messages, tools)
        bloques = []
        for b in data.get("content") or []:
            if b.get("type") == "text":
                bloques.append({"texto": b.get("text")})
            elif b.get("type") == "tool_use":
                bloques.append({"tool": b.get("name"), "input": b.get("input")})
        g["rondas"].append({
            "ms": int((time.monotonic() - t0) * 1000),
            "stop": data.get("stop_reason"),
            "bloques": bloques,
            "uso": {k: (data.get("usage") or {}).get(k) for k in (
                "input_tokens", "output_tokens",
                "cache_read_input_tokens", "cache_creation_input_tokens")},
        })
        return data

    monkeypatch.setattr(llm_engine, "_invoke_model", _ronda)

    for nombre in ("_viola_contacto", "_viola_ficha", "_viola_link",
                   "_viola_duracion", "_viola_disponibilidad",
                   "_viola_precio", "_viola_cierre_aplazado",
                   "_viola_duracion_por_plan", "_viola_consulta_por_mes"):
        original = getattr(llm_engine, nombre, None)
        if original is None:
            continue

        def _envuelta(*a, __o=original, __n=nombre, **k):
            r = __o(*a, **k)
            if r:
                evento = {"guardarrail": __n, "ronda": len(g["rondas"])}
                if __n == "_viola_precio":
                    evento["detalle"] = r
                    evento["textos"] = list(a[1]) if len(a) > 1 else None
                g["disparos"].append(evento)
            return r

        monkeypatch.setattr(llm_engine, nombre, _envuelta)
    yield g
    log.removeHandler(g["logs"])
    log.setLevel(nivel_previo)


def _accion_legible(a: Dict[str, Any]) -> Dict[str, Any]:
    p = a.get("payload") or {}
    tipo = a.get("type")
    if tipo == "say":
        return {"tipo": "texto", "texto": p.get("text") or ""}
    if tipo == "say_media":
        return {
            "tipo": "media",
            "clave": _CLAVE_DE_URL.get(p.get("url"), "?"),
            "pie": p.get("caption") or "",
        }
    if tipo == "handoff":
        return {"tipo": "traspaso", "motivo": p.get("motivo"), "resumen": p.get("resumen")}
    if tipo == "end":
        return {"tipo": "fin", "silencioso": bool(p.get("silencioso"))}
    return {"tipo": tipo}


def conversar(bot, mensajes: List[str], grabadora, contact_name: Optional[str] = None):
    """Corre el guion turno a turno, con el runtime que arma `bot_runner`
    (`ya_se_presento` = la sesión ya trae historial)."""
    estado = None
    turnos: List[Dict[str, Any]] = []
    for mensaje in mensajes:
        runtime = {
            "bot_id": bot.id, "source": "whatsapp", "conversation_id": None,
            "contact_name": contact_name, "retomada": False, "desde": None,
            "ya_se_presento": bool(isinstance(estado, dict) and estado.get("history")),
        }
        r0, d0, l0 = len(grabadora["rondas"]), len(grabadora["disparos"]), len(grabadora["logs"].registros)
        t0 = time.monotonic()
        salida = llm_engine.advance(bot, estado, mensaje, runtime=runtime)
        ms = int((time.monotonic() - t0) * 1000)
        tel = salida.get("telemetry") or {}
        logs = grabadora["logs"].registros[l0:]
        turnos.append({
            "cliente": mensaje,
            "acciones": [_accion_legible(a) for a in salida.get("actions") or []],
            "tools": [{"tool": t.get("tool"), "input": t.get("input")} for t in tel.get("tools") or []],
            "intenciones": tel.get("intenciones"),
            "finished": salida.get("finished"),
            "escalado": tel.get("escalated_to"),
            "failsafe": tel.get("failsafe"),
            "rounds": tel.get("rounds"),
            "ms": ms,
            "uso": {k: tel.get(k) for k in ("tokens_in", "tokens_out", "cache_read", "cache_write")},
            "rondas": grabadora["rondas"][r0:],
            "disparos": grabadora["disparos"][d0:],
            "correcciones": [x["msg"] for x in logs if "bloqueado" in x["msg"]],
            "recortes": [x["msg"] for x in logs if x["nivel"] == "INFO" and "llm_decision" not in x["msg"]],
        })
        estado = salida.get("next_state")
    return turnos


# ---------------------------------------------------------------------------
# Lectura de un turno
# ---------------------------------------------------------------------------

def texto(t: Dict[str, Any]) -> str:
    partes = []
    for a in t["acciones"]:
        if a["tipo"] == "texto":
            partes.append(a["texto"])
        elif a["tipo"] == "media" and a["pie"]:
            partes.append(a["pie"])
    return "\n".join(partes)


def medios(t: Dict[str, Any]) -> List[str]:
    return [a["clave"] for a in t["acciones"] if a["tipo"] == "media"]


def herramientas(t: Dict[str, Any]) -> List[str]:
    return [x["tool"] for x in t["tools"]]


def n_preguntas(s: str) -> int:
    return s.count("?")


def termina_en_pregunta(t: Dict[str, Any]) -> bool:
    con_texto = [a for a in t["acciones"] if a["tipo"] in ("texto", "media") and
                 (a.get("texto") or a.get("pie"))]
    if not con_texto:
        return False
    ultimo = con_texto[-1].get("texto") or con_texto[-1].get("pie") or ""
    return re.sub(r"[^\w?¿]+$", "", ultimo.strip()).endswith("?")


def adjunto_despues_de_pregunta(t: Dict[str, Any]) -> bool:
    visto = False
    for a in t["acciones"]:
        s = a.get("texto") or a.get("pie") or ""
        if a["tipo"] == "media" and visto:
            return True
        if "?" in s:
            visto = True
    return False


def se_presenta(s: str) -> bool:
    return bool(re.search(r"soy \*?luisa", s, re.I))


def montos(s: str) -> List[int]:
    return guardarrail_precio.extraer_montos(s)


_CACHE_MES: Dict[str, Set[int]] = {}


def precios_del_mes(mes: str) -> Set[int]:
    """Todas las cifras del resultado real de la consulta para ese mes."""
    if mes not in _CACHE_MES:
        res = tarifario.consultar(LLM_CONFIG_B, mes=mes)
        _CACHE_MES[mes] = {int(x.replace(".", "")) for x in re.findall(r"\$(\d{1,3}(?:\.\d{3})+)", res)}
    return _CACHE_MES[mes]


def _ninos() -> List[int]:
    return [int(n["valor"]) for n in tarifario.extras().get("ninos") or []]


def es_derivado(m: int, base: Set[int]) -> bool:
    """¿`m` sale de un precio de `base`: n personas, + niños, anticipo 30 % o
    saldo 70 % (±1.000)?"""
    ninos = _ninos()
    extras_planos = set(ninos) | {25000, 3000, 4000}
    if m in extras_planos or m in base:
        return True
    pct = int(tarifario.extras().get("anticipo_pct") or 30) / 100
    sumas_ninos = {0} | set(ninos) | {a + b for a in ninos for b in ninos}
    for p in base:
        for n in range(1, 9):
            for k in sumas_ninos:
                x = n * p + k
                if m == x or abs(m - x * pct) <= 1000 or abs(m - x * (1 - pct)) <= 1000:
                    return True
    return False


_MARCAS_IA = {
    "guion_largo": re.compile(r"—"),
    "no_es_solo": re.compile(r"no (es|son) solo", re.I),
    "muletilla": re.compile(r"cabe destacar|vale la pena mencionar|es importante (destacar|mencionar)", re.I),
    "real_intensificador": re.compile(r"\b(real|reales|verdadero|verdadera)\b", re.I),
    "inflado": re.compile(r"profundiz|potenci|experiencia inolvidable|sum[eé]rgete", re.I),
}


def marcas_ia(s: str) -> List[str]:
    return [k for k, rx in _MARCAS_IA.items() if rx.search(s)]


# ---------------------------------------------------------------------------
# Chequeos por estrategia
# ---------------------------------------------------------------------------

class Hoja:
    def __init__(self) -> None:
        self.filas: List[Dict[str, Any]] = []

    def anotar(self, estrategia: int, chequeo: str, ok: bool, detalle: str = "",
               turno: int = 0, duro: bool = False) -> None:
        self.filas.append({"estrategia": estrategia, "chequeo": chequeo, "ok": bool(ok),
                           "detalle": detalle[:300], "turno": turno, "duro": duro})

    def duros_fallidos(self) -> List[Dict[str, Any]]:
        return [f for f in self.filas if f["duro"] and not f["ok"]]


def chequear_apertura(h: Hoja, t: Dict[str, Any], *, flyer_esperado: str,
                      desde: Optional[int], max_chars: int = 250) -> None:
    s = texto(t)
    h.anotar(1, "apertura ≤ 250 caracteres", len(s) <= max_chars, f"{len(s)} caracteres")
    h.anotar(2, "no pide el nombre en la apertura", not llm_engine._pide_el_nombre(s), s[-120:])
    if desde:
        h.anotar(3, "«desde» de temporada", tarifario._pesos(desde) in s if hasattr(tarifario, "_pesos") else str(desde) in s,
                 f"esperado {desde}; montos {montos(s)}")
    fl = [m for m in medios(t) if m in _FLYERS]
    h.anotar(4, "un solo flyer, el del mes", fl == [flyer_esperado], f"medios={medios(t)}")
    h.anotar(5, "cierra con una sola pregunta", termina_en_pregunta(t) and n_preguntas(s) == 1,
             f"{n_preguntas(s)} '?'; final={s[-80:]!r}")
    h.anotar(10, "una pregunta por turno", n_preguntas(s) <= 1, f"{n_preguntas(s)} '?'")


def chequear_turno_general(h: Hoja, i: int, t: Dict[str, Any], *, nombre_permitido: bool,
                           ya_pidio_nombre: bool) -> bool:
    """Lo que aplica a todo turno. Devuelve si este turno pidió el nombre."""
    s = texto(t)
    cierre = t["finished"] or any(a["tipo"] in ("traspaso", "fin") for a in t["acciones"])
    if not cierre:
        h.anotar(10, "una pregunta por turno", n_preguntas(s) <= 1, f"{n_preguntas(s)} '?'", i)
        h.anotar(17, "termina en pregunta", termina_en_pregunta(t), repr(s[-80:]), i)
    h.anotar(17, "ningún adjunto después de la pregunta", not adjunto_despues_de_pregunta(t),
             f"acciones={[a['tipo'] for a in t['acciones']]}", i)
    if i > 0:
        h.anotar(11, "no se vuelve a presentar", not se_presenta(s), s[:100], i)
    pide = llm_engine._pide_el_nombre(s)
    if pide and not nombre_permitido:
        h.anotar(2, "nombre solo al reservar", False, s[-120:], i)
    if pide and ya_pidio_nombre:
        h.anotar(8, "no pide el nombre dos veces", False, s[-120:], i)
    h.anotar(21, "no interroga por el origen de un precio",
             not re.search(r"de d[oó]nde (sacaste|viste|sali[oó])", s, re.I), s[:100], i)
    h.anotar(0, "sin failsafe", not t["failsafe"], "", i, duro=True)
    # El guardarraíl de precio agotó sus correcciones y pasó el chat a un
    # asesor: es una venta cortada. Si el precio estaba bien, es un falso
    # positivo; si estaba mal, el modelo no supo corregirlo. Las dos cosas son
    # graves, y la transcripción dice cuál fue.
    por_guardarrail = [a for a in t["acciones"] if a["tipo"] == "traspaso"
                       and "guardarra" in str(a.get("motivo") or "")]
    h.anotar(18, "sin traspaso por guardarraíl de precio", not por_guardarrail,
             f"correcciones={len(t['correcciones'])}", i, duro=True)
    mi = marcas_ia(s)
    h.anotar(99, "tono sin marcas de IA", not mi, ",".join(mi), i)
    # Ronda 2: lo que la ronda 1 encontró leyendo.
    h.anotar(99, "sin disculpa dirigida al sistema", not _DISCULPA.search(s), s[:120], i)
    h.anotar(17, "sin etiqueta [enviaste: …] filtrada", "[envi" not in s.lower(), s[-120:], i)
    textos_turno = [a["texto"] for a in t["acciones"] if a["tipo"] == "texto"]
    narra = [x for x in textos_turno[:-1] if _NARRACION.search(x) and len(x) < 160]
    h.anotar(10, "sin burbuja de narración", not narra, " | ".join(narra)[:160], i)
    if any(a["tipo"] == "traspaso" for a in t["acciones"]):
        h.anotar(22, "el traspaso lleva aviso al cliente", bool(s.strip()), "", i)
    return pide


_DISCULPA = re.compile(
    r"tienes (toda la )?raz[oó]n|me equivoqu|vuelvo a (responder|intentar)|"
    r"voy a responder bien|me disculpo|disculpa(,|\.| la confusi)|reescribo|corrijo", re.I)
_NARRACION = re.compile(
    r"d[eé]jame (consultar|traerte|revisar|buscar|ver)|te consulto|voy a consultar|un momento", re.I)


def chequear_largo_con_mes(h: Hoja, i: int, t: Dict[str, Any]) -> None:
    s = texto(t)
    n = len([l for l in s.split("\n") if l.strip()])
    h.anotar(1, "respuesta con mes ≤ 8 líneas", n <= 8, f"{n} líneas, {len(s)} caracteres", i)


def chequear_precios(h: Hoja, i: int, t: Dict[str, Any], meses: List[str], *,
                     exigir: Optional[List[int]] = None, prohibir: Optional[List[int]] = None) -> None:
    s = texto(t)
    # El «desde» de la temporada siempre se puede decir (lo da el sistema).
    base: Set[int] = {d for d in [_desde()] if d}
    for m in meses:
        base |= precios_del_mes(m)
    raros = [m for m in montos(s) if not es_derivado(m, base)]
    h.anotar(18, "montos salen del tarifario del mes", not raros, f"fuera de tabla: {raros}", i, duro=True)
    for v in exigir or []:
        h.anotar(18, f"cita {v}", v in montos(s), f"montos={montos(s)}", i)
    for v in prohibir or []:
        h.anotar(18, f"no cita {v}", v not in montos(s), f"montos={montos(s)}", i, duro=True)


def chequear_intencion(h: Hoja, i: int, t: Dict[str, Any], tipo: str) -> None:
    tipos = [x.get("tipo") for x in (t.get("intenciones") or [])]
    h.anotar(22, f"registrar_intencion({tipo})", tipo in tipos, f"intenciones={tipos}", i)


def chequear_anticipo(h: Hoja, i: int, t: Dict[str, Any]) -> None:
    s = texto(t)
    h.anotar(16, "anticipo 30 %", bool(re.search(r"30\s*%", s)), s[:160], i, duro=True)
    h.anotar(16, "saldo 8-10 días", bool(re.search(r"8 a 10|8-10|ocho a diez", s)), "", i)
    h.anotar(16, "manda medios_pago", "medios_pago" in medios(t), f"medios={medios(t)}", i)


def sin_cierre(h: Hoja, i: int, t: Dict[str, Any]) -> None:
    hs = herramientas(t)
    cerro = t["finished"] or "no_responder" in hs or "finalizar_conversacion" in hs
    h.anotar(14, "venta en pausa sin cierre", not cerro, f"tools={hs} finished={t['finished']}", i, duro=True)
    h.anotar(14, "respondió algo", bool(texto(t).strip()), "", i, duro=True)


# ---------------------------------------------------------------------------
# Guiones
# ---------------------------------------------------------------------------

def _flyer_hoy() -> str:
    return tarifario.flyer_apertura(tarifario.hoy_colombia(), LLM_CONFIG_B)


def _desde() -> Optional[int]:
    return tarifario.desde_temporada(tarifario.hoy_colombia())


def g01(h, ts):
    chequear_apertura(h, ts[0], flyer_esperado=_flyer_hoy(), desde=_desde())
    chequear_precios(h, 0, ts[0], [])
    chequear_precios(h, 1, ts[1], ["diciembre"])
    h.anotar(4, "turno 2 manda el tarifario de diciembre",
             "tarifario_amordios_dic_ene" in medios(ts[1]), f"medios={medios(ts[1])}", 1)


def g02(h, ts):
    s = texto(ts[0])
    h.anotar(3, "contesta «¿cuánto vale?» con el desde", _desde() in montos(s), f"montos={montos(s)}")
    h.anotar(5, "pregunta el mes", bool(re.search(r"qu[eé] mes", s, re.I)), s[-80:])
    chequear_precios(h, 0, ts[0], [])  # sin consulta: solo el «desde» de temporada
    chequear_precios(h, 1, ts[1], ["octubre"])
    oct_min = min(p for p in precios_del_mes("octubre") if p > 100000)
    h.anotar(18, "el desde de octubre (no el de temporada)",
             _desde() not in montos(texto(ts[1])) or _desde() in precios_del_mes("octubre"),
             f"montos={montos(texto(ts[1]))} min_oct={oct_min}", 1)


def g03(h, ts):
    chequear_anticipo(h, 2, ts[2])
    chequear_intencion(h, 2, ts[2], "anticipo")
    chequear_precios(h, 2, ts[2], ["octubre"])


def g04a(h, ts):
    t = ts[1]
    h.anotar(20, "promo $350.000 → traspaso", any(a["tipo"] == "traspaso" for a in t["acciones"]),
             f"acciones={[a['tipo'] for a in t['acciones']]}", 1, duro=True)
    h.anotar(20, "no cotiza otra cosa", not montos(texto(t)), f"montos={montos(texto(t))}", 1)
    h.anotar(21, "no pregunta de dónde lo sacó", not re.search(r"d[oó]nde", texto(t), re.I), texto(t)[:120], 1)


def g04b(h, ts):
    g04a(h, ts)
    motivo = " ".join(str(a.get("motivo") or "") for a in ts[1]["acciones"] if a["tipo"] == "traspaso")
    h.anotar(20, "nota interna habla de presupuesto, no de flyer",
             "presupuesto" in motivo.lower(), motivo[:160], 1)
    h.anotar(20, "decidido sin rondas de corrección", not ts[1]["correcciones"],
             f"rounds={ts[1]['rounds']}", 1)


def g05(h, ts):
    t = ts[1]
    s = texto(t)
    ninos = _ninos()
    h.anotar(19, "cita el valor del niño de 3-4 años", ninos[1] in montos(s) if len(ninos) > 1 else False,
             f"montos={montos(s)}", 1, duro=True)
    h.anotar(19, "no escala por el niño", not any(a["tipo"] == "traspaso" for a in t["acciones"]), "", 1)
    chequear_precios(h, 1, t, ["diciembre"])


def g06(h, ts):
    sin_cierre(h, 2, ts[2])
    s = texto(ts[2])
    h.anotar(14, "respuesta corta (≤ 3 líneas)", len([l for l in s.split("\n") if l.strip()]) <= 3, s[:160], 2)
    h.anotar(14, "no manda más material", not medios(ts[2]), f"medios={medios(ts[2])}", 2)
    h.anotar(14, "no copia literal la frase guía del prompt",
             "es una decisión para tomar juntos" not in s.lower(), s[:160], 2)


def g07(h, ts):
    t = ts[1]
    chequear_precios(h, 1, t, ["octubre"], exigir=[505000], prohibir=[549000])
    chequear_intencion(h, 1, t, "fecha_concreta")


def g08(h, ts):
    s0 = texto(ts[0])
    h.anotar(9, "no saluda por «Casa»", not re.search(r"\bcasa\b", s0, re.I), s0[:80], 0, duro=True)
    chequear_apertura(h, ts[0], flyer_esperado=_flyer_hoy(), desde=_desde())
    reg = [x for x in ts[1]["tools"] if x["tool"] == "registrar_nombre"]
    h.anotar(9, "registra «Marcela»", any("marcela" in str(x["input"]).lower() for x in reg), str(reg), 1)
    chequear_precios(h, 1, ts[1], ["noviembre"])


def g09(h, ts):
    t = ts[0]
    h.anotar(4, "flyer de diciembre en la apertura", "tarifario_amordios_dic_ene" in medios(t)
             or "tarifario_piedramar_nov_ene" in medios(t), f"medios={medios(t)}")
    h.anotar(4, "apertura con mes: un solo flyer", len([m for m in medios(t) if m in _FLYERS]) == 1,
             f"medios={medios(t)}")
    h.anotar(3, "consulta precios de diciembre", "consultar_tarifario" in herramientas(t)
             or "consultar_precios" in herramientas(t), str(herramientas(t)))
    chequear_precios(h, 0, t, ["diciembre"])
    chequear_precios(h, 1, ts[1], ["diciembre"], exigir=[516000])


def g10(h, ts):
    t2, t3 = ts[2], ts[3]
    chequear_intencion(h, 2, t2, "reservar")
    h.anotar(2, "pide el nombre al reservar", llm_engine._pide_el_nombre(texto(t2))
             or bool(re.search(r"nombre completo", texto(t2), re.I)), texto(t2)[-120:], 2)
    h.anotar(17, "manda formulario_reserva", "formulario_reserva" in medios(t2), f"medios={medios(t2)}", 2)
    chequear_precios(h, 2, t2, ["diciembre"])
    chequear_intencion(h, 3, t3, "datos")
    h.anotar(22, "aviso al cliente al recibir los datos", bool(texto(t3).strip()), texto(t3)[:160], 3, duro=True)
    h.anotar(22, "escala con los datos", any(a["tipo"] == "traspaso" for a in t3["acciones"])
             or "escalar_a_asesor" in herramientas(t3), str(herramientas(t3)), 3, duro=True)
    res = " ".join(str(x["input"].get("resumen", "")) for x in t3["tools"] if x["tool"] == "escalar_a_asesor")
    h.anotar(22, "resumen del escalamiento con fecha y personas",
             bool(re.search(r"18", res)) and bool(re.search(r"2 personas|dos personas|2 adultos|2 pax", res, re.I)),
             res[:200], 3)


GUIONES: Dict[str, Dict[str, Any]] = {
    "G01_apertura_anuncio": {
        "mensajes": ["¡Hola! Quiero más información", "para diciembre"],
        "chequeo": g01,
    },
    "G02_cuanto_vale": {
        "mensajes": ["¿cuánto vale?", "octubre"],
        "chequeo": g02,
    },
    "G03_con_cuanto_se_separa": {
        "mensajes": ["¡Hola! Quiero más información", "octubre", "¿con cuánto se separa?"],
        "chequeo": g03,
    },
    "G04a_promo_350": {
        "mensajes": ["¡Hola! Quiero más información",
                     "En el flyer dice que de lunes a jueves hay salidas desde $350.000, ¿para cuándo es eso?"],
        "chequeo": g04a,
    },
    "G04b_tengo_350_mil": {
        "mensajes": ["¡Hola! Quiero más información", "tengo 350 mil por persona, ¿qué me alcanza?"],
        "chequeo": g04b,
    },
    "G05_familia_nino_3": {
        "mensajes": ["Hola, info por favor",
                     "Somos 2 adultos y un niño de 3 años, para diciembre. ¿Cuánto nos saldría?"],
        "chequeo": g05,
    },
    "G06_lo_consulto_esposo": {
        "mensajes": ["Hola", "noviembre", "Ok, lo consulto con mi esposo y te aviso"],
        "chequeo": g06,
    },
    "G07_fecha_concreta_doble": {
        "mensajes": ["¡Hola! Quiero más información", "del 16 al 19 de octubre en doble, ¿cuánto vale?"],
        "chequeo": g07,
    },
    "G08_perfil_casa": {
        "mensajes": ["¡Hola! Quiero más información", "Soy Marcela, para noviembre"],
        "contact_name": "Casa",
        "chequeo": g08,
    },
    "G09_cuanto_vale_diciembre": {
        "mensajes": ["¿cuánto vale en diciembre?", "en Piedra Mar, la del 18 al 21 en doble"],
        "chequeo": g09,
    },
    "G10_reserva_con_datos": {
        "mensajes": ["Hola", "diciembre", "quiero reservar la del 18 al 21 en Amor de Dios",
                     "Laura Restrepo Gil, CC 1234567, 2 personas, salida del 18 de diciembre"],
        "chequeo": g10,
    },
}

_RESERVA = {"G10_reserva_con_datos": 2}
#: Turnos en que el cliente acaba de dar el mes: la respuesta trae precios.
_TURNO_CON_MES = {"G01_apertura_anuncio": 1, "G02_cuanto_vale": 1, "G03_con_cuanto_se_separa": 1,
                  "G05_familia_nino_3": 1, "G06_lo_consulto_esposo": 1, "G08_perfil_casa": 1,
                  "G09_cuanto_vale_diciembre": 0, "G10_reserva_con_datos": 1}


# ---------------------------------------------------------------------------
# Escritura de la transcripción
# ---------------------------------------------------------------------------

def _huella() -> Dict[str, str]:
    """md5 de lo que se está probando: el árbol tiene cambios sin commitear y
    otras sesiones pueden estar editándolo durante la corrida."""
    import hashlib

    app = Path(llm_engine.__file__).resolve().parents[1]
    rutas = ["services/llm_engine.py", "services/guardarrail_precio.py",
             "services/recortes_turno.py", "services/senales.py",
             "services/tarifario.py", "bot_contexts/demo_viajes_b.md",
             "data/bot_viajes_b.py", "services/intencion_compra.py"]
    return {r: hashlib.md5((app / r).read_bytes()).hexdigest()[:10]
            for r in rutas if (app / r).exists()}


#: Lo que se cargó en ESTE proceso. Los módulos se importan una vez, al
#: recolectar los tests: si alguien edita el árbol a mitad de la corrida, lo que
#: corre es esto y no lo que hay en disco al final (ronda 1 lo confundió).
HUELLA_AL_ARRANCAR = _huella()


def _guardar(nombre: str, bot: str, turnos: List[Dict[str, Any]], hoja: Hoja) -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)
    registro = {"guion": nombre, "bot": bot, "huella": HUELLA_AL_ARRANCAR,
                "huella_en_disco_al_guardar": _huella(), "turnos": turnos,
                "chequeos": hoja.filas}
    (CARPETA / f"{nombre}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"{nombre}  [bot {bot}]", "=" * 72]
    for i, t in enumerate(turnos):
        L.append(f"CLIENTE | {t['cliente']}")
        for a in t["acciones"]:
            if a["tipo"] == "texto":
                for j, l in enumerate(a["texto"].split("\n")):
                    L.append(f"{'BOT     |' if j == 0 else '        |'} {l}")
            elif a["tipo"] == "media":
                L.append(f"MEDIA   | [{a['clave']}]" + (f" pie: {a['pie']!r}" if a["pie"] else ""))
            elif a["tipo"] == "traspaso":
                L.append(f"TRASPASO| motivo={a['motivo']!r} resumen={a.get('resumen')!r}")
            elif a["tipo"] == "fin":
                L.append(f"FIN     | silencioso={a['silencioso']}")
        L.append(f"        · tools: {[(x['tool'], x['input']) for x in t['tools']]}")
        if t.get("intenciones"):
            L.append(f"        · intenciones: {t['intenciones']}")
        L.append(f"        · rounds={t['rounds']} ms={t['ms']} finished={t['finished']} uso={t['uso']}")
        for c in t["correcciones"]:
            L.append(f"        ! CORRECCIÓN: {c}")
        for d in t["disparos"]:
            L.append(f"        ! DISPARO {d}")
        for r in t["recortes"]:
            L.append(f"        ~ {r}")
        if t["correcciones"]:
            for k, r in enumerate(t["rondas"]):
                for b in r["bloques"]:
                    if "texto" in b:
                        L.append(f"          ronda {k + 1} texto: {b['texto']!r}")
        L.append("-" * 72)
    L.append("CHEQUEOS:")
    for f in hoja.filas:
        L.append(f"  [{'OK ' if f['ok'] else 'FALLA'}] #{f['estrategia']} t{f['turno']} {f['chequeo']} — {f['detalle']}")
    (CARPETA / f"{nombre}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Los tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rep", range(1, REPETICIONES + 1), ids=lambda r: f"r{r:02d}")
@pytest.mark.parametrize("guion", list(GUIONES))
def test_guion_variante_b(guion, rep, grabadora, presupuesto, medidor):
    g = GUIONES[guion]
    grabadora_etq = f"B {guion}"
    llm_engine_bot = BotViajesB()
    turnos = conversar(llm_engine_bot, g["mensajes"], grabadora, g.get("contact_name"))
    hoja = Hoja()
    pidio = False
    reserva_desde = _RESERVA.get(guion, 99)
    for i, t in enumerate(turnos):
        pidio = chequear_turno_general(
            hoja, i, t, nombre_permitido=i >= reserva_desde, ya_pidio_nombre=pidio
        ) or pidio
    g["chequeo"](hoja, turnos)
    if guion in _TURNO_CON_MES:
        chequear_largo_con_mes(hoja, _TURNO_CON_MES[guion], turnos[_TURNO_CON_MES[guion]])
    _guardar(f"{guion}__r{rep:02d}", "B", turnos, hoja)
    fallidos = hoja.duros_fallidos()
    assert not fallidos, f"{grabadora_etq}: {fallidos}"


@pytest.mark.parametrize("rep", range(1, REPETICIONES + 1), ids=lambda r: f"r{r:02d}")
def test_apertura_bot_a(rep, grabadora, presupuesto):
    """Solo para comparar largo y contenido de la apertura con el bot 1."""
    turnos = conversar(_bot_a(), ["¡Hola! Quiero más información"], grabadora)
    hoja = Hoja()
    s = texto(turnos[0])
    hoja.anotar(1, "largo de la apertura (bot A)", True, f"{len(s)} caracteres")
    hoja.anotar(10, "preguntas", True, f"{n_preguntas(s)} '?'")
    _guardar(f"A_apertura__r{rep:02d}", "A", turnos, hoja)
