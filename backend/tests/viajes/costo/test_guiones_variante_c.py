"""Guiones del bot 3 (variante C, «embudo guiado») de Arranquemos Pues contra
Claude de verdad, en Bedrock.

**Cuesta plata.** Vive bajo `tests/viajes/costo/`: queda marcado `costo` y no
corre sin `--con-costo`. Una pasada de todos los guiones cuesta del orden de
US$ 0,45.

    cd backend && source .venv/bin/activate
    APP_ENCRYPTION_KEY=<fernet efímera> TZ=UTC REPETICIONES_C=6 \\
        python -m pytest --con-costo -m costo -q \\
        tests/viajes/costo/test_guiones_variante_c.py

Variables: `REPETICIONES_C` (default 1), `TOPE_USD_C` (default 3, libro de
gasto compartido entre procesos en `costo.jsonl`), `TRANSCRIPCIONES_C_DIR`
(default `entregables/transcripciones_c/<fecha>/`, git-ignorada).

Reusa las piezas del arnés del bot 2 (`test_guiones_variante_b.py`): la
grabadora de rondas y correcciones, la hoja de chequeos y la lectura de
montos. Lo propio del bot 3:

- **Reloj fijo.** El horario de los asesores y la franja del saludo dependen
  de la hora; `llm_engine._ahora_utc` se fija por guion (por defecto hoy a las
  10:00 de Colombia; C10, sábado a las 20:00). La fecha del tarifario sigue
  siendo la real (`tarifario.hoy_colombia`).
- **Etapa esperada por turno** (`next_state["etapa"]`), comparada con la que
  infiere el motor.
- **Opciones cerradas**: el oráculo de opciones numeradas de este archivo es
  propio (regex de keycaps), a propósito distinto del del motor, para que la
  métrica y el guardarraíl no compartan un mismo error.

Como en el bot 2, casi todos los chequeos son blandos (se anotan) y solo los
que no pueden fallar son duros. Las transcripciones están para LEERLAS.
Nombres y documentos inventados (CLAUDE.md #8).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, time as dtime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import pytest

from app.data.bot_viajes import MEDIA
from app.data.bot_viajes_c import HORARIO_ASESORES, LLM_CONFIG_C
from app.services import llm_engine, tarifario
from tests.viajes.costo.test_guiones_variante_b import (  # noqa: F401  (fixture)
    Hoja,
    _accion_legible,
    es_derivado,
    grabadora,
    herramientas,
    marcas_ia,
    medios,
    montos,
    precios_del_mes,
    texto,
)

REPETICIONES = max(1, int(os.getenv("REPETICIONES_C", "1") or 1))
#: Para correr por pasadas (r01 de todos, luego r02…) sin pisar archivos.
REP_INICIO = max(1, int(os.getenv("REP_INICIO_C", "1") or 1))
TOPE_USD = float(os.getenv("TOPE_USD_C", "3") or 3)
_RAIZ = Path(__file__).resolve().parents[4]
CARPETA = Path(
    os.getenv("TRANSCRIPCIONES_C_DIR")
    or _RAIZ / "entregables" / "transcripciones_c" / tarifario.hoy_colombia().isoformat()
)
LIBRO = CARPETA / "costo.jsonl"
_COL = timezone(timedelta(hours=-5))
_FLYERS = {k for k, v in MEDIA.items() if v.get("meses")}


def _huella() -> Dict[str, str]:
    app = Path(llm_engine.__file__).resolve().parents[1]
    rutas = ["services/llm_engine.py", "services/guardarrail_precio.py",
             "services/recortes_turno.py", "services/senales.py",
             "services/tarifario.py", "services/horario.py",
             "services/intencion_compra.py", "bot_contexts/demo_viajes_c.md",
             "data/bot_viajes_c.py"]
    return {r: hashlib.md5((app / r).read_bytes()).hexdigest()[:10]
            for r in rutas if (app / r).exists()}


#: Lo que se cargó en ESTE proceso (los módulos se importan al recolectar).
HUELLA_AL_ARRANCAR = _huella()


class BotViajesC:
    id = 41
    engine = "llm"
    status = "active"

    def __init__(self) -> None:
        self.llm_config = json.dumps(LLM_CONFIG_C, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Reloj y gasto
# ---------------------------------------------------------------------------

def _reloj(nombre: str) -> datetime:
    hoy = tarifario.hoy_colombia()
    if nombre == "sabado_noche":
        dia = hoy + timedelta(days=(5 - hoy.weekday()) % 7)
        return datetime.combine(dia, dtime(20, 0), tzinfo=_COL).astimezone(timezone.utc)
    # Por defecto en horario: hoy a las 10:00, o el lunes si hoy es domingo
    # (los asesores no atienden el domingo y la ronda no sería comparable).
    dia = hoy + timedelta(days=1) if hoy.weekday() == 6 else hoy
    return datetime.combine(dia, dtime(10, 0), tzinfo=_COL).astimezone(timezone.utc)


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
def presupuesto_c(medidor):
    CARPETA.mkdir(parents=True, exist_ok=True)
    if _gastado() >= TOPE_USD:
        pytest.skip(f"tope de gasto alcanzado (US$ {TOPE_USD})")
    antes = medidor.usd
    yield
    with LIBRO.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"usd": medidor.usd - antes, "t": time.time()}) + "\n")


# ---------------------------------------------------------------------------
# Conversación
# ---------------------------------------------------------------------------

def conversar_c(bot, mensajes: List[str], g, runtime_inicial: Optional[Dict[str, Any]] = None):
    estado = None
    turnos: List[Dict[str, Any]] = []
    for k, mensaje in enumerate(mensajes):
        runtime = {
            "bot_id": bot.id, "source": "whatsapp", "conversation_id": None,
            "contact_name": None, "retomada": False, "desde": None,
            "ya_se_presento": bool(isinstance(estado, dict) and estado.get("history")),
        }
        if k == 0 and runtime_inicial:
            runtime.update(runtime_inicial)
        # El comprobante entra como lo pasa el runner: `runtime["adjunto"]`
        # (el motor ya no confía en el marcador escrito, auditoría B1).
        if mensaje.strip().lower() in ("[imagen]", "[media]", "[document]"):
            runtime["adjunto"] = "imagen"
        r0, d0, l0 = len(g["rondas"]), len(g["disparos"]), len(g["logs"].registros)
        t0 = time.monotonic()
        salida = llm_engine.advance(bot, estado, mensaje, runtime=runtime)
        ms = int((time.monotonic() - t0) * 1000)
        tel = salida.get("telemetry") or {}
        logs = g["logs"].registros[l0:]
        nxt = salida.get("next_state")
        turnos.append({
            "cliente": mensaje,
            "acciones": [_accion_legible(a) for a in salida.get("actions") or []],
            "tools": [{"tool": t.get("tool"), "input": t.get("input")} for t in tel.get("tools") or []],
            "intenciones": tel.get("intenciones"),
            "etapa": (nxt or {}).get("etapa") if isinstance(nxt, dict) else None,
            "etapa_telemetria": tel.get("etapa"),
            "finished": salida.get("finished"),
            "failsafe": tel.get("failsafe"),
            "rounds": tel.get("rounds"),
            "ms": ms,
            "uso": {k2: tel.get(k2) for k2 in ("tokens_in", "tokens_out", "cache_read", "cache_write")},
            "rondas": g["rondas"][r0:],
            "disparos": g["disparos"][d0:],
            "correcciones": [x["msg"] for x in logs if "bloqueado" in x["msg"]],
            "recortes": [x["msg"] for x in logs if x["nivel"] in ("INFO", "WARNING")
                         and "llm_decision" not in x["msg"] and "llm_invoke" not in x["msg"]],
        })
        estado = nxt
    return turnos


# ---------------------------------------------------------------------------
# Oráculos propios
# ---------------------------------------------------------------------------

_OPCION_RE = re.compile(r"^\s*([1-9])️?⃣\s*(.+?)\s*$", re.M)


def opciones(burbuja: str) -> Dict[int, str]:
    return {int(n): e for n, e in _OPCION_RE.findall(burbuja or "")}


def burbujas(t: Dict[str, Any]) -> List[str]:
    return [a.get("texto") or a.get("pie") or "" for a in t["acciones"]
            if a["tipo"] in ("texto", "media") and (a.get("texto") or a.get("pie"))]


def ultima_burbuja(t: Dict[str, Any]) -> str:
    b = burbujas(t)
    return b[-1] if b else ""


_EXENTO_RE = re.compile(r"nombre\s+completo|c[eé]dula|comprobante|tus datos", re.I)
_SUJETO_RE = re.compile(r"sujeto a (disponibilidad|cupo)|seg[uú]n disponibilidad|disponibilidad de cupo", re.I)
_DISCULPA_RE = re.compile(
    r"tienes (toda la )?raz[oó]n|me equivoqu|vuelvo a (responder|intentar)|me disculpo|"
    r"disculpa(,|\.| la confusi)|reescribo|corrijo", re.I)
_PROMESA_RE = re.compile(
    r"compa[ñn]er[oa][^.\n]{0,40}(confirm|te (lo )?cuenta|te escribe)|lo confirmo con|te paso esa info", re.I)
_DESPEDIDA_RE = re.compile(r"\b(chao|adi[oó]s|hasta luego|bye|ya no me interesa)\b", re.I)
_NARRACION_RE = re.compile(
    r"d[eé]jame (consultar|traerte|revisar|buscar)|te consulto|voy a (consultar|cotizar)|"
    r"necesito consultar|consulto los precios|acabo de consultar|ya tengo la info|ahora s[ií]\b|"
    r"reescribiendo|d[eé]jame corregir|no deber[ií]a haber|tienes (toda la )?raz[oó]n", re.I)
_PAR_RE = re.compile(r"\$\s?([\d.]+)\s*c/u[^\n$]{0,12}\$\s?([\d.]+)", re.I)


def _num(s: str) -> int:
    return int(s.replace(".", ""))


def _base_precios() -> Set[int]:
    base: Set[int] = set()
    for m in ("octubre", "noviembre", "diciembre", "enero"):
        base |= precios_del_mes(m)
    d = tarifario.desde_temporada(tarifario.hoy_colombia())
    return base | ({d} if d else set())


# ---------------------------------------------------------------------------
# Chequeos
# ---------------------------------------------------------------------------

def chequear_turno(h: Hoja, i: int, t: Dict[str, Any], *, esperado: Optional[str],
                   nombre_permitido: bool, con_opciones: Optional[bool]) -> None:
    s = texto(t)
    ult = ultima_burbuja(t)
    traspaso = any(a["tipo"] == "traspaso" for a in t["acciones"])
    fin = any(a["tipo"] == "fin" for a in t["acciones"])
    exento = traspaso or fin or bool(_EXENTO_RE.search(ult))
    ops = opciones(ult)
    if con_opciones is None:
        con_opciones = not exento
    if con_opciones:
        h.anotar(1, "cierra con opciones numeradas (≥2) o sí/no",
                 len(ops) >= 2 or bool(re.search(r"\?\s*(\W*)$", ult) and re.search(r"\bs[ií]\b", ult, re.I)),
                 repr(ult[-140:]), i)
        if len(ops) >= 2:
            h.anotar(1, "pregunta y opciones en la MISMA burbuja", "?" in ult, repr(ult[:100]), i)
            h.anotar(1, "≤ 5 opciones", len(ops) <= 5, str(len(ops)), i)
            h.anotar(1, "nada después de las opciones",
                     ult.rstrip().splitlines()[-1].strip() == (list(_OPCION_RE.finditer(ult))[-1].group(0).strip()),
                     repr(ult[-60:]), i)
    idx_ops = [k for k, a in enumerate(t["acciones"]) if a["tipo"] in ("texto", "media")
               and len(opciones(a.get("texto") or a.get("pie") or "")) >= 2]
    if idx_ops:
        h.anotar(1, "adjuntos antes de las opciones",
                 not any(a["tipo"] == "media" for a in t["acciones"][idx_ops[-1] + 1:]),
                 str([a["tipo"] for a in t["acciones"]]), i)
    if esperado:
        h.anotar(2, f"etapa = {esperado}", t["etapa"] == esperado,
                 f"motor: {t['etapa']}", i)
    if not nombre_permitido:
        h.anotar(3, "no pide el nombre antes de /reserva", not llm_engine._pide_el_nombre(s), s[-100:], i)
    base = _base_precios()
    raros = [m for m in montos(s) if not es_derivado(m, base)]
    h.anotar(4, "montos salen del tarifario", not raros, f"fuera de tabla: {raros}", i, duro=True)
    for a, b in _PAR_RE.findall(s):
        p, tot = _num(a), _num(b)
        h.anotar(4, "total = n × precio (+ niños)", tot % p == 0 or any(
            (tot - k) % p == 0 for k in (55000, 195000, 250000, 390000, 110000)),
            f"{p} c/u → {tot}", i)
    h.anotar(5, "nada de «sujeto a disponibilidad»", not _SUJETO_RE.search(s), s[:80], i)
    h.anotar(6, "sin disculpa al sistema", not _DISCULPA_RE.search(s), s[:100], i)
    h.anotar(6, "sin [enviaste: …]", "[envi" not in s.lower(), s[-80:], i)
    narra = [m.group(0) for b in burbujas(t) for m in [_NARRACION_RE.search(b)] if m]
    h.anotar(6, "sin narración visible", not narra, " | ".join(narra)[:120], i)
    largas = [len([l for l in b.split("\n") if l.strip()]) for b in burbujas(t)
              if "ITINERARIO" not in b]
    h.anotar(7, "burbujas ≤ 10 líneas", all(n <= 10 for n in largas), str(largas), i)
    h.anotar(0, "sin failsafe", not t["failsafe"], "", i, duro=True)
    por_guardarrail = [a for a in t["acciones"] if a["tipo"] == "traspaso"
                       and re.search(r"guardarra|no logr", str(a.get("motivo") or ""))]
    h.anotar(4, "sin traspaso por guardarraíl de precio", not por_guardarrail,
             str([a.get("motivo") for a in por_guardarrail]), i, duro=True)
    # Ronda 2: promesas sin acción y cierres silenciosos.
    h.anotar(26, "sin promesa de compañero sin escalar",
             traspaso or not _PROMESA_RE.search(s) or bool(re.search(r"verific", s, re.I)), s[:140], i)
    silencioso = (not s.strip()) and (fin or "no_responder" in herramientas(t)) and not traspaso
    h.anotar(27, "sin cierre silencioso", not silencioso or bool(_DESPEDIDA_RE.search(t["cliente"])),
             f"cliente={t['cliente']!r}", i)
    mi = marcas_ia(s)
    h.anotar(99, "tono sin marcas de IA", not mi, ",".join(mi), i)


def eleccion_respetada(h: Hoja, i: int, prev: Dict[str, Any], t: Dict[str, Any], n: int,
                       buscar: Optional[str] = None) -> None:
    """La opción n del menú anterior aparece en la respuesta (fechas o nombre)."""
    ops = opciones(ultima_burbuja(prev))
    etiqueta = ops.get(n, "")
    if buscar is None:
        dias = re.findall(r"\d{1,2}", re.sub(r"\$[\d.]+", "", etiqueta))[:2]
        ok = bool(dias) and all(d.lstrip("0") in re.sub(r"\b0(\d)", r"\1", texto(t)) for d in dias)
        detalle = f"opción {n}: {etiqueta[:60]!r}"
    else:
        ok = buscar.lower() in texto(t).lower()
        detalle = f"opción {n}: {etiqueta[:60]!r}, busca {buscar!r}"
    h.anotar(8, f"«{n}» se interpretó como la opción {n}", ok, detalle, i)


def anticipo_correcto(h: Hoja, i: int, prev_total: Optional[int], t: Dict[str, Any]) -> None:
    s = texto(t)
    m = re.search(r"anticipo[^$\n]{0,40}\$\s?([\d.]+)", s, re.I)
    if not m or not prev_total:
        h.anotar(9, "anticipo con monto", False, s[:160], i)
        return
    monto = _num(m.group(1))
    pct = int(tarifario.extras().get("anticipo_pct") or 30) / 100
    h.anotar(9, "anticipo = % × total", abs(monto - prev_total * pct) <= 1000,
             f"anticipo {monto} vs {pct:.0%} de {prev_total}", i, duro=True)


def total_multiple(t: Dict[str, Any]) -> Optional[int]:
    for linea in texto(t).split("\n"):
        if "últiple" in linea:
            m = _PAR_RE.search(linea)
            if m:
                return _num(m.group(2))
    return None


# ---------------------------------------------------------------------------
# Guiones
# ---------------------------------------------------------------------------

ANUNCIO = "¡Hola! Quiero más información"
DATOS = "Laura Restrepo Gil, CC 1234567"


def c01(h, ts):
    eleccion_respetada(h, 2, ts[1], ts[2], 2)
    eleccion_respetada(h, 4, ts[2], ts[4], 1, buscar=opciones(ultima_burbuja(ts[2])).get(1, "?").split(":")[0].strip("* "))
    h.anotar(8, "«2» personas → cotiza para 2", bool(re.search(r"\b2 personas", texto(ts[4]))), texto(ts[4])[:80], 4)
    anticipo_correcto(h, 5, total_multiple(ts[4]), ts[5])
    h.anotar(10, "/reserva manda formulario_reserva", "formulario_reserva" in medios(ts[6]), str(medios(ts[6])), 6)
    h.anotar(10, "/pago manda medios_pago", "medios_pago" in medios(ts[7]), str(medios(ts[7])), 7)
    h.anotar(10, "/pago trae el anticipo", bool(re.search(r"anticipo[^\n$]{0,40}\$", texto(ts[7]), re.I)), texto(ts[7])[:120], 7)
    h.anotar(10, "/pago no traspasa", not any(a["tipo"] == "traspaso" for a in ts[7]["acciones"]), "", 7, duro=True)
    h.anotar(10, "/pago sin corrección", not ts[7]["correcciones"], str(ts[7]["correcciones"]), 7)
    h.anotar(10, "transferencia pide el comprobante", "comprobante" in texto(ts[8]).lower(), texto(ts[8])[:120], 8)
    t = ts[9]
    h.anotar(11, "comprobante sin modelo", not t["rondas"], f"rondas={len(t['rondas'])}", 9, duro=True)
    h.anotar(11, "comprobante traspasa", any(a["tipo"] == "traspaso" and "comprobante" in str(a.get("motivo"))
                                               for a in t["acciones"]), str(t["acciones"])[:160], 9, duro=True)
    h.anotar(11, "comprobante dice {cuando}", "en un momento" in texto(t), texto(t)[:160], 9)


def c02(h, ts):
    s = texto(ts[1])
    h.anotar(12, "«¿cuánto vale?» trae precio", bool(montos(s)), s[:160], 1, duro=True)
    h.anotar(12, "y el menú de meses", len(opciones(ultima_burbuja(ts[1]))) >= 2, "", 1)


def c03(h, ts):
    s = texto(ts[0])
    h.anotar(13, "salta el menú de meses", not re.search(r"Aún no sé", s), s[-120:], 0)
    h.anotar(13, "precios de diciembre en el primer mensaje", bool(montos(s)), s[:120], 0)
    h.anotar(13, "flyer de diciembre", any(m in ("tarifario_amordios_dic_ene", "tarifario_piedramar_nov_ene")
                                           for m in medios(ts[0])), str(medios(ts[0])), 0)
    eleccion_respetada(h, 1, ts[0], ts[1], 2)


def c04(h, ts):
    vids = {"video_amordios", "video_bohios", "video_piedramar"}
    h.anotar(14, "«4» manda los 3 videos", vids <= set(medios(ts[3])), str(medios(ts[3])), 3)
    h.anotar(14, "y repite hoteles con opciones", len(opciones(ultima_burbuja(ts[3]))) >= 3, "", 3)
    h.anotar(14, "«no los conozco» no escala", not any(a["tipo"] == "traspaso" for a in ts[4]["acciones"]), "", 4)
    h.anotar(14, "no inventa estrellas/servicios", not re.search(r"estrella|piscina|wifi|aire acondicionado", texto(ts[4]), re.I),
             texto(ts[4])[:160], 4)


def c05(h, ts):
    menu = texto(ts[4])
    if re.search(r"edad|años", menu, re.I) and opciones(ultima_burbuja(ts[4])):
        ninos = tarifario.extras().get("ninos") or []
        h.anotar(15, "menú de edades sale de los extras",
                 all(str(n["edad_max"]) in menu for n in ninos), menu[-160:], 4)
    h.anotar(15, "no repregunta la edad ya dada", not re.search(r"edad", texto(ts[5]), re.I)
             or bool(montos(texto(ts[5]))), texto(ts[5])[:120], 5)
    s = texto(ts[5])
    h.anotar(15, "cita $195.000 del niño", 195000 in montos(s), str(montos(s)), 5, duro=True)
    pares = [(_num(a), _num(b)) for a, b in _PAR_RE.findall(s)]
    h.anotar(15, "total = 2 × precio + 195.000", bool(pares) and all(b == 2 * a + 195000 for a, b in pares),
             str(pares), 5)


def c05b(h, ts):
    menu = ultima_burbuja(ts[5])
    ops = list(opciones(menu).values())
    esperado = [n["etiqueta"] for n in tarifario.extras().get("ninos") or []]
    h.anotar(15, "pide la edad con menú", bool(re.search(r"edad|años", menu, re.I)) and len(ops) >= 2, menu[-160:], 5)
    h.anotar(15, "menú de edades = extras", all(any(e.lower() in o.lower() for o in ops) for e in esperado),
             f"opciones={ops}", 5)


def c06(h, ts):
    h.anotar(4, "cotización sin traspaso", not any(a["tipo"] == "traspaso" for a in ts[1]["acciones"]), "", 1, duro=True)
    t = ts[2]
    hs = herramientas(t)
    h.anotar(16, "lo consulto: sin cierre", not t["finished"] and "no_responder" not in hs and "finalizar_conversacion" not in hs,
             str(hs), 2, duro=True)
    h.anotar(16, "nombra al esposo", "esposo" in texto(t).lower(), texto(t)[:120], 2)
    h.anotar(16, "no copia la frase del ejemplo", "lo hablan con calma" not in texto(t).lower(), texto(t)[:120], 2)


def c07(h, ts):
    t = ts[2]
    hs = herramientas(t)
    h.anotar(17, "«gracias» tras precio: no se cierra", not t["finished"] and "no_responder" not in hs, str(hs), 2, duro=True)
    h.anotar(17, "ofrece reservar/consultar/pregunta", len(opciones(ultima_burbuja(t))) >= 2, ultima_burbuja(t)[-120:], 2)


def c08(h, ts):
    h.anotar(18, "menú /cliente", "marcar_cliente" in herramientas(ts[0]) or bool(re.search(r"qu[eé] llevar", texto(ts[0]), re.I)),
             texto(ts[0])[:160], 0)
    resp = texto(ts[0]) + "\n" + texto(ts[1])
    h.anotar(18, "da hora y punto de salida", bool(re.search(r"Estaci[oó]n Universidad", resp)) and
             bool(re.search(r"6:00|9:00", resp)), resp[:160], 1)
    h.anotar(18, "contesta directo en el primer mensaje", bool(re.search(r"6:00|9:00", texto(ts[0]))), texto(ts[0])[:120], 0)


def c09(h, ts):
    t = ts[1]
    h.anotar(19, "cambio de fecha → asesor", any(a["tipo"] == "traspaso" for a in t["acciones"]), "", 1, duro=True)
    h.anotar(19, "aviso con cuándo", "en un momento" in texto(t), texto(t)[:160], 1)


def c10(h, ts):
    s0 = texto(ts[0])
    h.anotar(20, "saludo de noche (franja)", bool(re.search(r"buenas noches", s0, re.I)), s0[:60], 0)
    t = ts[1]
    s = texto(t)
    h.anotar(20, "pide llamada → asesor", any(a["tipo"] == "traspaso" for a in t["acciones"]), "", 1, duro=True)
    h.anotar(20, "fuera de horario: «el lunes…»", "el lunes a partir de las 8:00" in s, s[:200], 1, duro=True)
    h.anotar(20, "aviso de ausencia con horario y CTA", "sábados" in s and re.search(r"c[eé]dula|fecha", s, re.I) is not None,
             s[-200:], 1)
    h.anotar(20, "no dice «en un momento»", "en un momento" not in s, "", 1)
    from app.services import horario as _h
    literal = LLM_CONFIG_C["mensaje_ausencia"].replace("{cuando}", _h.cuando_atienden(_reloj("sabado_noche"), HORARIO_ASESORES))
    h.anotar(20, "aviso de ausencia literal de la config", literal in s, s[-220:], 1)


def c11(h, ts):
    t = ts[2]
    h.anotar(21, "tarjeta → asesor", any(a["tipo"] == "traspaso" for a in t["acciones"]), str(herramientas(t)), 2, duro=True)
    res = " ".join(str((x["input"] or {}).get("resumen", "")) for x in t["tools"] if x["tool"] == "escalar_a_asesor")
    h.anotar(21, "resumen con medio y datos", bool(re.search(r"tarjeta", res, re.I)) and "Laura" in res, res[:200], 2)
    h.anotar(10, "/pago no traspasa", not any(a["tipo"] == "traspaso" for a in ts[1]["acciones"]), "", 1, duro=True)
    h.anotar(10, "/pago sin corrección", not ts[1]["correcciones"], str(ts[1]["correcciones"]), 1)
    h.anotar(10, "/pago manda medios_pago", "medios_pago" in medios(ts[1]), str(medios(ts[1])), 1)


def c12(h, ts):
    t = ts[1]
    h.anotar(22, "$350.000 → asesor", any(a["tipo"] == "traspaso" for a in t["acciones"]), "", 1, duro=True)
    h.anotar(22, "sin modelo", not t["rondas"], f"rondas={len(t['rondas'])}", 1)


def c13(h, ts):
    s = texto(ts[1])
    h.anotar(23, "da la oficina (Bosque Plaza)", "Bosque Plaza" in s, s[:160], 1)
    h.anotar(23, "con las dos referencias", "Universidad" in s and "Jard" in s, "", 1)


def c14(h, ts):
    s = texto(ts[0])
    h.anotar(24, "no se presenta de nuevo", not re.search(r"soy \*?luisa", s, re.I), s[:120], 0)
    h.anotar(24, "bienvenida de regreso", bool(re.search(r"de nuevo|otra vez|seguimos", s, re.I)), s[:120], 0)
    h.anotar(24, "retoma mes u hotel de la vez anterior", bool(re.search(r"diciembre|amor de dios", s, re.I)), s[:160], 0)


def c15(h, ts):
    t = ts[2]
    s = texto(t)
    h.anotar(25, "duda conocida: contesta sin escalar", not any(a["tipo"] == "traspaso" for a in t["acciones"]), "", 2)
    h.anotar(25, "comidas correctas (desde el desayuno del sábado)", bool(re.search(r"s[aá]bado", s, re.I)), s[:160], 2)
    h.anotar(25, "vuelve al paso con opciones", len(opciones(ultima_burbuja(t))) >= 2, ultima_burbuja(t)[-100:], 2)


def c15b(h, ts):
    t = ts[2]
    s = texto(t)
    h.anotar(25, "no inventa que el bus tiene baño",
             not re.search(r"tiene ba[ñn]o,? s[ií]|\bs[ií],? (el bus )?(tiene|cuenta)|cuenta con ba[ñn]o", s, re.I),
             s[:160], 2, duro=True)
    h.anotar(25, "pregunta desconocida → traspaso", any(a["tipo"] == "traspaso" for a in t["acciones"]), s[:120], 2)
    h.anotar(25, "baño: asesor o «te lo confirma un compañero»",
             any(a["tipo"] == "traspaso" for a in t["acciones"]) or bool(re.search(r"compa[ñn]er|asesor", s, re.I)),
             s[:160], 2)


GUIONES: Dict[str, Dict[str, Any]] = {
    "C01_camino_feliz": {
        "mensajes": [ANUNCIO, "1", "2", "1", "2", "1", "1", DATOS, "1", "[imagen]"],
        "etapas": ["bienvenida", "mes", "fecha", "fecha", "cotizacion", "cotizacion",
                   "reserva", "pago", "pago", "comprobante"],
        "reserva_desde": 6, "chequeo": c01,
    },
    "C02_cuanto_vale_sin_mes": {
        "mensajes": [ANUNCIO, "¿cuánto vale?"], "etapas": ["bienvenida", None], "chequeo": c02,
    },
    "C03_primer_mensaje_con_mes": {
        "mensajes": ["Quiero el plan de diciembre", "la segunda"], "etapas": ["mes", "fecha"], "chequeo": c03,
    },
    "C04_ver_videos": {
        "mensajes": [ANUNCIO, "2️⃣", "1", "4", "no los conozco, ¿cuál me recomiendas?"],
        "etapas": ["bienvenida", "mes", "fecha", "fecha", "fecha"], "chequeo": c04,
    },
    "C05_familia_nino_3": {
        "mensajes": [ANUNCIO, "diciembre", "1", "1", "4", "2 adultos y un niño de 3 años"],
        "etapas": ["bienvenida", "mes", "fecha", "fecha", "fecha", "cotizacion"], "chequeo": c05,
    },
    "C05b_menu_edades": {
        "mensajes": [ANUNCIO, "diciembre", "1", "1", "4", "2"],
        "etapas": ["bienvenida", "mes", "fecha", "fecha", "fecha", "fecha"], "chequeo": c05b,
    },
    "C06_lo_consulto": {
        "mensajes": [ANUNCIO, "Diciembre, la del 18 al 21 en Amor de Dios, somos 2",
                     "Ok, lo consulto con mi esposo y te aviso"],
        "etapas": ["bienvenida", "cotizacion", "cotizacion"], "chequeo": c06,
    },
    "C07_gracias_tras_precio": {
        "mensajes": [ANUNCIO, "Diciembre, la del 18 al 21 en Amor de Dios, somos 2", "gracias"],
        "etapas": ["bienvenida", "cotizacion", "cotizacion"], "chequeo": c07,
    },
    "C08_cliente_hora_bus": {
        "mensajes": ["Hola, ya tengo mi reserva para el viernes, ¿a qué hora sale el bus?", "1"],
        "etapas": ["cliente", "cliente"], "chequeo": c08,
    },
    "C09_cliente_cambio_fecha": {
        "mensajes": ["Hola, ya tengo mi reserva con ustedes", "4"],
        "etapas": ["cliente", None], "chequeo": c09,
    },
    "C10_llamada_sabado_noche": {
        "mensajes": [ANUNCIO, "¿Me pueden llamar mejor? Prefiero que me expliquen por teléfono"],
        "etapas": ["bienvenida", "asesor"], "reloj": "sabado_noche", "chequeo": c10,
    },
    "C11_tarjeta": {
        "mensajes": ["Hola, quiero reservar la salida del 23 al 26 de octubre en Amor de Dios, somos 2, en múltiple",
                     DATOS, "2"],
        "etapas": ["reserva", "pago", "asesor"], "reserva_desde": 0, "chequeo": c11,
    },
    "C12_promo_350": {
        "mensajes": [ANUNCIO, "Vi en el flyer que de lunes a jueves hay salidas desde $350.000"],
        "etapas": ["bienvenida", "asesor"], "chequeo": c12,
    },
    "C12b_presupuesto_350": {
        "mensajes": [ANUNCIO, "tengo 350 mil por persona, ¿qué me alcanza?"],
        "etapas": ["bienvenida", "asesor"], "chequeo": c12,
    },
    "C13_confianza": {
        "mensajes": [ANUNCIO, "¿Es confiable? Prefiero pagar en persona"],
        "etapas": ["bienvenida", None], "chequeo": c13,
    },
    "C14_cliente_que_vuelve": {
        "mensajes": [ANUNCIO],
        "runtime": {"ya_se_presento": True, "etapa_previa": "cotizacion",
                    "ultimo_mes": "diciembre", "ultimo_hotel": "Amor de Dios"},
        "etapas": [None], "chequeo": c14,
    },
    "C15_duda_conocida": {
        "mensajes": [ANUNCIO, "1", "¿qué comidas incluye?"],
        "etapas": ["bienvenida", "mes", "mes"], "chequeo": c15,
    },
    "C15b_duda_desconocida": {
        "mensajes": [ANUNCIO, "1", "¿el bus tiene baño?"],
        "etapas": ["bienvenida", "mes", None], "chequeo": c15b,
    },
}


# ---------------------------------------------------------------------------
# Transcripción
# ---------------------------------------------------------------------------

def _guardar(nombre: str, turnos: List[Dict[str, Any]], hoja: Hoja, reloj: datetime) -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)
    registro = {"guion": nombre, "bot": "C", "huella": HUELLA_AL_ARRANCAR,
                "huella_en_disco_al_guardar": _huella(),
                "reloj_utc": reloj.isoformat(), "turnos": turnos, "chequeos": hoja.filas}
    (CARPETA / f"{nombre}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"{nombre}  [bot C]  reloj={reloj.astimezone(_COL).isoformat()}", "=" * 72]
    for i, t in enumerate(turnos):
        L.append(f"CLIENTE | {t['cliente']}")
        for a in t["acciones"]:
            if a["tipo"] == "texto":
                for j, l in enumerate(a["texto"].split("\n")):
                    L.append(f"{'BOT     |' if j == 0 else '        |'} {l}")
            elif a["tipo"] == "media":
                L.append(f"MEDIA   | [{a['clave']}]")
                for j, l in enumerate((a["pie"] or "").split("\n")):
                    if l:
                        L.append(f"   pie  | {l}")
            elif a["tipo"] == "traspaso":
                L.append(f"TRASPASO| motivo={a['motivo']!r} resumen={a.get('resumen')!r}")
            elif a["tipo"] == "fin":
                L.append(f"FIN     | silencioso={a['silencioso']}")
        L.append(f"        · etapa={t['etapa']} · tools: {[(x['tool'], x['input']) for x in t['tools']]}")
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
# El test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rep", range(REP_INICIO, REP_INICIO + REPETICIONES), ids=lambda r: f"r{r:02d}")
@pytest.mark.parametrize("guion", list(GUIONES))
def test_guion_variante_c(guion, rep, grabadora, presupuesto_c, monkeypatch):
    g = GUIONES[guion]
    reloj = _reloj(g.get("reloj", "manana"))
    monkeypatch.setattr(llm_engine, "_ahora_utc", lambda: reloj)
    for nombre in ("_viola_duracion_plan", "_viola_cierre_con_opciones", "_viola_promesa",
                   "_viola_consulta_por_salida", "_viola_opciones_cerradas"):
        original = getattr(llm_engine, nombre, None)
        if original is None:
            continue

        def _env(*a, __o=original, __n=nombre, **k):
            r = __o(*a, **k)
            if r:
                grabadora["disparos"].append({"guardarrail": __n, "ronda": len(grabadora["rondas"])})
            return r

        monkeypatch.setattr(llm_engine, nombre, _env)
    turnos = conversar_c(BotViajesC(), g["mensajes"], grabadora, g.get("runtime"))
    hoja = Hoja()
    reserva_desde = g.get("reserva_desde", 99)
    for i, t in enumerate(turnos):
        esperado = g["etapas"][i] if i < len(g["etapas"]) else None
        chequear_turno(hoja, i, t, esperado=esperado, nombre_permitido=i >= reserva_desde,
                       con_opciones=None)
    g["chequeo"](hoja, turnos)
    _guardar(f"{guion}__r{rep:02d}", turnos, hoja, reloj)
    fallidos = hoja.duros_fallidos()
    assert not fallidos, f"C {guion}: {fallidos}"
