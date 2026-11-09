"""Release 1 del Sprint 36: los tres bots de Arranquemos Pues contra Bedrock.

**Cuesta plata.** Vive bajo `tests/viajes/costo/`: queda marcado `costo` y no
corre sin `--con-costo`. Una pasada (8 guiones × 3 bots) cuesta del orden de
US$ 1.

    cd backend && source .venv/bin/activate
    APP_ENCRYPTION_KEY=<fernet efímera> TZ=UTC \\
        python -m pytest --con-costo -m costo -q \\
        tests/viajes/costo/test_guiones_sprint36.py

Variables: `REPETICIONES_S36` (default 1), `TOPE_USD_S36` (default 3, libro de
gasto compartido entre procesos en `costo.jsonl`), `TRANSCRIPCIONES_S36_DIR`
(default `entregables/transcripciones_s36/<fecha>/`, git-ignorada).

Lo que cambió en los tres bots (ver `services/venta_grupo.py`):

  1. piden la venta después del total («¿Te aparto los N cupos?»);
  2. el total del grupo con la acomodación correcta (múltiple solo 3+, niños
     por su tramo del tarifario);
  3. «sale de Medellín» en el primer mensaje, y a quien vive lejos se le dice
     en una línea, sin pasarlo a un asesor;
  4. nada de «todo incluido» / «incluye todo», y a «¿es todo incluido?» no
     se contesta «¡Sí!»;
  5. listo para reservar con nombre completo y cédula de quien paga.

Los chequeos **duros** son solo lo determinista (el total y el anticipo salen
de `bloque_total`; la venta pedida, Medellín y el «todo incluido» los pone el
post-proceso; el cierre con cédula lo fuerza una corrección). Todo lo demás se
anota y se LEE en la transcripción: la lección del 19-ago (63 chequeos
verdes y el bot perdiendo ventas) sigue vigente.

**Reloj fijo.** Todos los guiones corren el sábado 7-nov-2026 a las 10:00 de
Colombia, salvo H (salida a menos de 5 días), que corre el lunes 9-nov a las
10:00: la salida del 13 al 16 de noviembre queda a 4 días y se paga completa.
Se fija la clase `datetime` de los módulos que leen la hora (motor, tarifario,
horario), no solo `_ahora_utc`, para que el «Qué día es hoy» del prompt y el
«PAGO TOTAL» de la consulta digan lo mismo.

Nombres y documentos inventados (CLAUDE.md #8).
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pytest

from app.services import horario, llm_engine, tarifario
from tests.viajes.conftest import BotViajes
from tests.viajes.costo.test_guiones_variante_b import (  # noqa: F401  (fixture)
    BotViajesB,
    Hoja,
    _accion_legible,
    es_derivado,
    grabadora,
    herramientas,
    marcas_ia,
    montos,
    precios_del_mes,
    texto,
)
from tests.viajes.costo.test_guiones_variante_c import BotViajesC
from app.data.bot_viajes_d import LLM_CONFIG_D


class BotViajesD:
    """Bot D (estrategia D, Sprint 36): conversación sin menús y «¿Te los aparto?»."""
    id = 44
    engine = "llm"
    status = "active"

    def __init__(self) -> None:
        self.llm_config = json.dumps(LLM_CONFIG_D, ensure_ascii=False)

REPETICIONES = max(1, int(os.getenv("REPETICIONES_S36", "1") or 1))
TOPE_USD = float(os.getenv("TOPE_USD_S36", "3") or 3)
_RAIZ = Path(__file__).resolve().parents[4]
_COL = timezone(timedelta(hours=-5))
CARPETA = Path(
    os.getenv("TRANSCRIPCIONES_S36_DIR")
    or _RAIZ / "entregables" / "transcripciones_s36" / tarifario.hoy_colombia().isoformat()
)
LIBRO = CARPETA / "costo.jsonl"

SABADO = datetime(2026, 11, 7, 10, 0, tzinfo=_COL)
LUNES = datetime(2026, 11, 9, 10, 0, tzinfo=_COL)

BOTS: Dict[str, Callable[[], Any]] = {
    "bot1": BotViajes,
    "bot2": BotViajesB,
    "bot3": BotViajesC,
    "botD": BotViajesD,
}


# ---------------------------------------------------------------------------
# Reloj y gasto
# ---------------------------------------------------------------------------

def _reloj_fijo(monkeypatch, instante: datetime) -> None:
    class _Fijo(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D401
            return instante.astimezone(tz) if tz else instante.astimezone(timezone.utc).replace(tzinfo=None)

    for modulo in (llm_engine, tarifario, horario):
        monkeypatch.setattr(modulo, "datetime", _Fijo)


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
def presupuesto_s36(medidor):
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

def conversar(bot, mensajes: List[str], g, runtime_inicial: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
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
        r0, d0, l0 = len(g["rondas"]), len(g["disparos"]), len(g["logs"].registros)
        t0 = time.monotonic()
        salida = llm_engine.advance(bot, estado, mensaje, runtime=runtime)
        tel = salida.get("telemetry") or {}
        logs = g["logs"].registros[l0:]
        turnos.append({
            "cliente": mensaje,
            "acciones": [_accion_legible(a) for a in salida.get("actions") or []],
            "tools": [{"tool": t.get("tool"), "input": t.get("input")} for t in tel.get("tools") or []],
            "finished": salida.get("finished"),
            "escalado": tel.get("escalated_to"),
            "failsafe": tel.get("failsafe"),
            "rounds": tel.get("rounds"),
            "ms": int((time.monotonic() - t0) * 1000),
            "uso": {k: tel.get(k) for k in ("tokens_in", "tokens_out", "cache_read", "cache_write")},
            "rondas": g["rondas"][r0:],
            "disparos": g["disparos"][d0:],
            "correcciones": [x["msg"] for x in logs if "bloqueado" in x["msg"]],
            "recortes": [x["msg"] for x in logs if x["nivel"] in ("INFO", "WARNING")
                         and "llm_decision" not in x["msg"] and "llm_invoke" not in x["msg"]],
        })
        estado = salida.get("next_state")
    return turnos


# ---------------------------------------------------------------------------
# Oráculos
# ---------------------------------------------------------------------------

_APARTO_RE = re.compile(
    r"te\s+(?:lo|la|los|las)\s+(?:aparto|separo)|\bte\s+aparto\b|cu[aá]l\s+te\s+aparto|¿\s*(?:quieres|deseas)\s+(?:apartar|reservar)"
    r"|s[ií],?\s+quiero\s+(?:reservar|apartar)",
    re.I,
)
_TODO_INCLUIDO_RE = re.compile(r"todo\s+(?:est[aá]\s+|va\s+)?inclu[ií]d[oa]|incluye\s+(?:absolutamente\s+)?todo\b", re.I)
_SI_INICIAL_RE = re.compile(r"^\W*(s[ií]\b|claro|por supuesto|as[ií] es|exacto|correcto)", re.I)
_OTRA_CIUDAD_RE = re.compile(
    r"(sale|salen|salimos|salida|recog\w*|pasamos por)[^.\n]{0,30}\b(desde|de|en|por)\s+cali\b"
    r"|desde\s+cali\s+(sale|hay|tenemos)"
    r"|(se\s+(unen|suben|montan)|recog\w*)[^.\n]{0,30}\ben\s+(el\s+camino|la\s+v[ií]a)", re.I)


def es_traspaso(t: Dict[str, Any]) -> bool:
    return any(a["tipo"] == "traspaso" for a in t["acciones"]) or "escalar_a_asesor" in herramientas(t)


def afirma_todo_incluido(s: str) -> List[str]:
    malos = []
    for m in _TODO_INCLUIDO_RE.finditer(s):
        antes = s[max(0, m.start() - 25):m.start()].lower()
        if re.search(r"\b(no|ni|tampoco)\b", antes):
            continue
        malos.append(s[max(0, m.start() - 30):m.end() + 10])
    return malos


def todo(ts: List[Dict[str, Any]]) -> str:
    return "\n".join(texto(t) for t in ts)


def pesos(n: int) -> str:
    return f"${n:,}".replace(",", ".")


def _turno_con(ts: List[Dict[str, Any]], monto: int) -> Optional[int]:
    for i, t in enumerate(ts):
        if monto in montos(texto(t)):
            return i
    return None


def total_y_venta(h: Hoja, ts, total: int, a_pagar: int, cupos: int, *, duro_total: bool = True) -> None:
    """El total del grupo aparece, y en ESE turno se pide la venta con el
    valor para apartar."""
    i = _turno_con(ts, total)
    h.anotar(2, f"da el total del grupo {pesos(total)}", i is not None,
             f"montos por turno: {[montos(texto(t)) for t in ts]}", i or 0, duro=duro_total)
    if i is None:
        return
    s = texto(ts[i])
    # Lo determinista es el post-proceso: con UN total dicho agrega «¿Te
    # aparto los N cupos?» con el valor; con varios, «¿Cuál te aparto…?»; y
    # no toca un menú numerado del bot 3 (ahí la pregunta es del modelo).
    menu = bool(re.search(r"[1-9]\ufe0f?\u20e3", s.split("?")[-1] if "?" in s else ""))
    # Dos totales (estándar y Barú) ya son «varios»: el cierre es «¿Cuál te
    # aparto…?» y no lleva un anticipo único.
    varios = (len({m for m in montos(s) if m >= 300000 and m % 1000 == 0}) >= 2
              or bool(re.search(r"cu[aá]l te aparto", s, re.I)))
    h.anotar(1, "«¿te aparto…?» en el turno del total", bool(_APARTO_RE.search(s)), s[-160:], i,
             duro=not menu)
    h.anotar(1, f"valor para apartar {pesos(a_pagar)}", a_pagar in montos(s), str(montos(s)), i,
             duro=not (menu or varios))
    h.anotar(1, f"«los {cupos} cupos» / «tu cupo»", bool(re.search(rf"\b{cupos} cupos|tu cupo", s)), s[-120:], i)


def listo_con_cedula(h: Hoja, ts, i: int) -> None:
    t = ts[i]
    llamadas = [x for x in t["tools"] if x["tool"] == "listo_para_reservar"]
    h.anotar(5, "listo_para_reservar al recibir nombre + cédula", bool(llamadas), str(herramientas(t)), i, duro=True)
    datos = " ".join(str((x["input"] or {}).get("datos", "")) for x in llamadas)
    h.anotar(5, "datos con nombre y cédula", "Restrepo" in datos and "1234567" in datos, datos[:160], i, duro=True)
    s = texto(t)
    h.anotar(5, "no pide más datos (nacimiento, correo, demás viajeros)",
             not re.search(r"fecha de nacimiento|correo|de cada viajero|de los dem[aá]s", s, re.I), s[:200], i)
    h.anotar(5, "dice el valor a pagar y pide el comprobante",
             bool(montos(s)) and "comprobante" in s.lower(), s[:200], i)


# ---------------------------------------------------------------------------
# Chequeos por guion
# ---------------------------------------------------------------------------

ANUNCIO = "¡Hola! Quiero más información"
DATOS = "Laura Restrepo Gil, CC 1234567"


def ga(h, ts):
    # Diciembre 18 al 21, Amor de Dios, 2 personas → doble 505.000 c/u.
    total_y_venta(h, ts, 2 * 505000, round(2 * 505000 * 0.3), 2)
    h.anotar(2, "a 2 no se le cotiza el total en múltiple", 2 * 459000 not in montos(todo(ts)),
             str(montos(todo(ts))), 0, duro=True)
    listo_con_cedula(h, ts, 4)


def gb(h, ts):
    s = todo(ts)
    h.anotar(2, "a 2 no se le cotiza el total en múltiple",
             not any(2 * p in montos(s) for p in (459000, 469000, 369000, 389000)),
             str(montos(s)), 0, duro=True)
    total_y_venta(h, ts, 2 * 505000, round(2 * 505000 * 0.3), 2)


def gc(h, ts):
    # Diciembre 18 al 21, Piedra Mar, 5 personas → múltiple 469.000 c/u.
    total_y_venta(h, ts, 5 * 469000, round(5 * 469000 * 0.3), 5)


def _una_pregunta(h: Hoja, ts) -> None:
    for i, t in enumerate(ts):
        s = texto(t)
        h.anotar(7, "una sola pregunta por turno", s.count("?") <= 1, s[-140:], i)


def _total_con_otra_fecha(ts, *, adultos: int, edades=()) -> List[str]:
    """Líneas donde un total del grupo va pegado a una salida que no es la
    suya (el bot 1 dijo «desde $933.000 … del 4 al 7» y $933.000 es la del 8
    al 11). Se recalcula con `bloque_total` sobre el tarifario de diciembre."""
    from app.data.bot_viajes import LLM_CONFIG
    from app.services import venta_grupo

    res = tarifario.consultar(LLM_CONFIG, mes="diciembre")
    ninos = ", ".join(str(e) for e in edades) or None
    _, totales = venta_grupo.bloque_total(res, {"adultos": str(adultos), "ninos": ninos})
    for fecha in ("2026-12-18",):
        _, mas = venta_grupo.bloque_total(tarifario.consultar(LLM_CONFIG, mes="diciembre", fecha=fecha),
                                          {"adultos": str(adultos), "ninos": ninos})
        totales += mas
    malos = []
    for t in ts:
        for linea in texto(t).split("\n"):
            dia = re.search(r"\b(\d{1,2}) al (\d{1,2})\b", linea)
            if not dia:
                continue
            for m in montos(linea):
                suyos = [x for x in totales if x.total == m]
                if suyos and not any(re.search(rf"\b0?{int(dia.group(1))} AL 0?{int(dia.group(2))}\b", x.etiqueta)
                                     for x in suyos):
                    malos.append(f"{m} con «{dia.group(0)}» es de {suyos[0].etiqueta}")
    return malos


def gd(h, ts):
    for i, t in enumerate(ts):
        h.anotar(3, "«vivo en Cali» no pasa a asesor", not es_traspaso(t), str(herramientas(t)), i, duro=True)
        h.anotar(3, "no inventa salida desde Cali", not _OTRA_CIUDAD_RE.search(texto(t)), texto(t)[:200], i, duro=True)
    h.anotar(3, "le dice que sale de Medellín", "medell" in texto(ts[1]).lower(), texto(ts[1])[:200], 1, duro=True)
    h.anotar(3, "en una línea, sin sermón", len([l for l in texto(ts[1]).split("\n") if "medell" in l.lower()]) <= 2,
             texto(ts[1])[:200], 1)


def ge(h, ts):
    # 2 adultos + niño de 3 = 3 personas → múltiple 459.000 × 2 + 195.000.
    total_y_venta(h, ts, 2 * 459000 + 195000, round((2 * 459000 + 195000) * 0.3), 3)
    # El tramo del niño ya va dentro del total (duro arriba); decirlo aparte
    # es deseable, no obligatorio.
    h.anotar(2, "nombra el valor del niño ($195.000)", 195000 in montos(todo(ts)), str(montos(todo(ts))), 0)
    h.anotar(2, "cada total con SU salida", not _total_con_otra_fecha(ts, adultos=2, edades=(3,)),
             "; ".join(_total_con_otra_fecha(ts, adultos=2, edades=(3,)))[:240], 0)


def gf(h, ts):
    t = ts[2]
    hs = herramientas(t)
    h.anotar(6, "«lo pienso»: sin cierre", not t["finished"] and "no_responder" not in hs
             and "finalizar_conversacion" not in hs, str(hs), 2, duro=True)
    h.anotar(6, "respondió algo", bool(texto(t).strip()), "", 2, duro=True)
    h.anotar(6, "no le insiste con «¿te aparto?»", not _APARTO_RE.search(texto(t)), texto(t)[:200], 2)
    h.anotar(6, "no escala", not es_traspaso(t), str(hs), 2)


def gg(h, ts):
    t = ts[1]
    s = texto(t)
    primera = next((a.get("texto") or a.get("pie") or "" for a in t["acciones"]
                    if a["tipo"] in ("texto", "media") and (a.get("texto") or a.get("pie"))), "")
    h.anotar(4, "a «¿es todo incluido?» no arranca con «Sí»", not _SI_INICIAL_RE.match(primera), primera[:120], 1, duro=True)
    h.anotar(4, "dice qué incluye (hotel, transporte, alimentación)",
             all(p in s.lower() for p in ("hotel", "transporte", "aliment")), s[:240], 1)
    h.anotar(4, "aclara desde cuándo va la alimentación o los opcionales",
             bool(re.search(r"s[aá]bado|opcional|no incluye|aparte", s, re.I)), s[:240], 1)


def gh(h, ts):
    # Lunes 9-nov: la del 13 al 16 de noviembre (festivo) sale en 4 días →
    # pago total. Amor de Dios, doble 615.000 × 2.
    total = 2 * 615000
    total_y_venta(h, ts, total, total, 2)
    i = _turno_con(ts, total)
    if i is not None:
        s = texto(ts[i])
        h.anotar(1, "dice que se paga el total (sale muy pronto)",
                 bool(re.search(r"total|completo", s, re.I)) and not re.search(r"anticipo de \$", s, re.I), s[-200:], i)
        h.anotar(1, "no ofrece el 30 %", round(total * 0.3) not in montos(s), str(montos(s)), i, duro=True)
    listo_con_cedula(h, ts, 3)


def gr(h, ts):
    """Vuelve a una conversación abandonada: no se presenta, re-consulta y pide la venta."""
    primero = texto(ts[0])
    h.anotar(4, "no se vuelve a presentar", "soy *luisa*" not in primero.lower(), primero[:160], 0, duro=True)
    consulto = any(x["tool"] in ("consultar_tarifario", "consultar_precios") for x in ts[0]["tools"])
    h.anotar(4, "re-consulta precios antes de dar cifras", consulto or not montos(primero),
             str(herramientas(ts[0])), 0, duro=True)
    h.anotar(1, "pide la venta en el regreso", bool(re.search(r"aparto", todo(ts), re.I)), todo(ts)[-160:], 0)


GUIONES: Dict[str, Dict[str, Any]] = {
    "R_vuelve_tras_abandono": {
        "mensajes": ["Hola", "la del 18 al 21 en Amor de Dios"],
        "runtime": {"regreso": {"via": "abandono", "mes": 12, "adultos": 2, "habia_total": True}},
        "chequeo": gr,
    },
    "A_somos_2_aparta_y_datos": {
        # «sí, apártame la del 18 al 21»: con dos opciones sobre la mesa
        # (estándar y Barú) el bot pregunta cuál; un «sí» a secas lo deja
        # repreguntando y no es lo que mide este guion.
        "mensajes": [ANUNCIO, "somos 2", "la del 18 al 21 de diciembre en Amor de Dios",
                     "sí, apártame la del 18 al 21", DATOS],
        "chequeo": ga,
    },
    "B_precio_para_dos": {
        "mensajes": [ANUNCIO, "¿precio para dos?", "diciembre, la del 18 al 21 en Amor de Dios"],
        "chequeo": gb,
    },
    "C_somos_5_diciembre": {
        "mensajes": [ANUNCIO, "somos 5, para diciembre", "la del 18 al 21 en Piedra Mar"],
        "chequeo": gc,
    },
    "D_vivo_en_cali": {
        "mensajes": [ANUNCIO, "vivo en Cali", "ah bueno, somos 2 para diciembre"],
        "chequeo": gd,
    },
    "E_dos_adultos_nino_3": {
        "mensajes": [ANUNCIO, "somos 2 adultos y un niño de 3 años, para diciembre",
                     "la del 18 al 21 en Amor de Dios"],
        "chequeo": ge,
    },
    "F_dejame_lo_pienso": {
        "mensajes": [ANUNCIO, "somos 2, la del 18 al 21 de diciembre en Amor de Dios", "déjame lo pienso"],
        "chequeo": gf,
    },
    "G_es_todo_incluido": {
        "mensajes": [ANUNCIO, "¿es todo incluido?"],
        "chequeo": gg,
    },
    "H_sale_en_4_dias": {
        "mensajes": [ANUNCIO, "somos 2, para la del 13 al 16 de noviembre en Amor de Dios",
                     "sí, apártamelos", DATOS],
        "reloj": LUNES,
        "chequeo": gh,
    },
}


# ---------------------------------------------------------------------------
# Chequeos de todo turno
# ---------------------------------------------------------------------------

def chequear_turno(h: Hoja, i: int, t: Dict[str, Any]) -> None:
    s = texto(t)
    h.anotar(0, "sin failsafe", not t["failsafe"], "", i, duro=True)
    malos = afirma_todo_incluido(s)
    h.anotar(4, "sin «todo incluido» / «incluye todo»", not malos, " | ".join(malos)[:200], i, duro=True)
    base = set()
    for m in ("noviembre", "diciembre", "enero"):
        base |= precios_del_mes(m)
    d = tarifario.desde_temporada(tarifario.hoy_colombia())
    if d:
        base.add(d)
    raros = [m for m in montos(s) if not es_derivado(m, base)]
    h.anotar(2, "montos salen del tarifario", not raros, f"fuera de tabla: {raros}", i, duro=True)
    por_guardarrail = [a for a in t["acciones"] if a["tipo"] == "traspaso"
                       and re.search(r"guardarra|no logr", str(a.get("motivo") or ""))]
    h.anotar(0, "sin traspaso por guardarraíl", not por_guardarrail,
             str([a.get("motivo") for a in por_guardarrail]), i, duro=True)
    if i == 0:
        h.anotar(3, "primer mensaje: sale de Medellín", "medell" in s.lower(), s[:200], i, duro=True)
    mi = marcas_ia(s)
    h.anotar(99, "tono sin marcas de IA", not mi, ",".join(mi), i)


# ---------------------------------------------------------------------------
# Transcripción
# ---------------------------------------------------------------------------

def _guardar(nombre: str, turnos: List[Dict[str, Any]], hoja: Hoja, reloj: datetime) -> None:
    CARPETA.mkdir(parents=True, exist_ok=True)
    registro = {"guion": nombre, "reloj": reloj.isoformat(), "turnos": turnos, "chequeos": hoja.filas}
    (CARPETA / f"{nombre}.json").write_text(json.dumps(registro, ensure_ascii=False, indent=1), encoding="utf-8")
    L = [f"{nombre}  reloj={reloj.isoformat()}", "=" * 72]
    for t in turnos:
        L.append(f"CLIENTE | {t['cliente']}")
        for a in t["acciones"]:
            if a["tipo"] == "texto":
                for j, l in enumerate(a["texto"].split("\n")):
                    L.append(f"{'BOT     |' if j == 0 else '        |'} {l}")
            elif a["tipo"] == "media":
                L.append(f"MEDIA   | [{a['clave']}]")
                for l in (a["pie"] or "").split("\n"):
                    if l:
                        L.append(f"   pie  | {l}")
            elif a["tipo"] == "traspaso":
                L.append(f"TRASPASO| motivo={a['motivo']!r} resumen={a.get('resumen')!r}")
            elif a["tipo"] == "fin":
                L.append(f"FIN     | silencioso={a['silencioso']}")
        L.append(f"        · tools: {[(x['tool'], x['input']) for x in t['tools']]}")
        L.append(f"        · rounds={t['rounds']} ms={t['ms']} finished={t['finished']} uso={t['uso']}")
        for c in t["correcciones"]:
            L.append(f"        ! CORRECCIÓN: {c}")
        for d in t["disparos"]:
            L.append(f"        ! DISPARO {d.get('guardarrail')}")
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
        marca = "OK " if f["ok"] else ("FALLA" if f["duro"] else "falla")
        L.append(f"  [{marca}] #{f['estrategia']} t{f['turno']} {f['chequeo']} — {f['detalle']}")
    (CARPETA / f"{nombre}.txt").write_text("\n".join(L) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# El test
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("rep", range(1, REPETICIONES + 1), ids=lambda r: f"r{r:02d}")
@pytest.mark.parametrize("guion", list(GUIONES))
@pytest.mark.parametrize("bot", list(BOTS))
def test_guion_sprint36(bot, guion, rep, grabadora, presupuesto_s36, monkeypatch):
    g = GUIONES[guion]
    reloj = g.get("reloj", SABADO)
    _reloj_fijo(monkeypatch, reloj)
    turnos = conversar(BOTS[bot](), g["mensajes"], grabadora, g.get("runtime"))
    hoja = Hoja()
    for i, t in enumerate(turnos):
        chequear_turno(hoja, i, t)
    g["chequeo"](hoja, turnos)
    _una_pregunta(hoja, turnos)
    _guardar(f"{bot}__{guion}__r{rep:02d}", turnos, hoja, reloj)
    fallidos = hoja.duros_fallidos()
    assert not fallidos, f"{bot} {guion}: " + "; ".join(
        f"t{f['turno']} {f['chequeo']} ({f['detalle'][:120]})" for f in fallidos)
