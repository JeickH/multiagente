"""#635: la demo con los reintentos y el modelo de respaldo de main (2747cf4),
todo por env para el modo convención, y `CONSENT_VERSION` nuevo.

La demo SÍ usa el modelo de respaldo cuando Haiku cae (en una convención es
mejor una respuesta de Sonnet que la disculpa técnica), pero con menos intentos
y siempre dentro del plazo del turno (`DEMO_TURNO_PRESUPUESTO_S`, 25 s). Los
bots de clientes siguen exactamente con el plan de main.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError

from app.routers import demo as router_demo
from app.services import llm_engine

PRINCIPAL = llm_engine._DEFAULT_MODEL_ID
RESPALDO = llm_engine._DEFAULT_FALLBACK_MODEL_ID
RAIZ = Path(__file__).resolve().parent.parent


class _Bot:
    id = 51
    team_id = None
    instrucciones = "Asesor de prueba."

    def __init__(self, cfg):
        self.llm_config = json.dumps(cfg)


def _caida(code="ServiceUnavailableException"):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "InvokeModel")


class Reloj:
    """Reloj falso: cada llamada al modelo «tarda» `costo` segundos."""

    def __init__(self):
        self.t = 1000.0

    def monotonic(self):
        return self.t


class Modelo:
    def __init__(self, reloj, fallas, costo_falla=0.2, costo_ok=1.0):
        self.reloj = reloj
        self.fallas = {m: list(f) for m, f in fallas.items()}
        self.costo_falla, self.costo_ok = costo_falla, costo_ok
        self.llamadas = []

    def __call__(self, model_id, system, messages, tools):
        self.llamadas.append(model_id)
        pendientes = self.fallas.get(model_id) or []
        if pendientes:
            self.reloj.t += self.costo_falla
            raise pendientes.pop(0)
        self.reloj.t += self.costo_ok
        return {"content": [{"type": "text", "text": f"Responde {model_id[:10]}"}],
                "stop_reason": "end_turn", "usage": {}}


@pytest.fixture
def reloj(monkeypatch):
    r = Reloj()
    monkeypatch.setattr(llm_engine.time, "monotonic", r.monotonic)
    pausas = []

    def _dormir(s):
        pausas.append(s)
        r.t += s
    monkeypatch.setattr(llm_engine.time, "sleep", _dormir)
    r.pausas = pausas
    for var in ("DEMO_TURNO_PRESUPUESTO_S", "DEMO_LLM_INTENTOS_MODELO",
                "DEMO_LLM_INTENTOS_RESPALDO", "DEMO_CHAT_FALLBACK_MODEL_ID",
                "LLM_FALLBACK_MODEL_ID"):
        monkeypatch.delenv(var, raising=False)
    return r


def _turno(cfg, modelo):
    with patch.object(llm_engine, "_invoke_model", modelo):
        return llm_engine.advance(_Bot(cfg), None, "hola")


def _dichos(r):
    return [a["payload"]["text"] for a in r["actions"] if a["type"] == "say"]


# ---------------------------------------------------------------------------
# 1. Respaldo en la demo, dentro del plazo
# ---------------------------------------------------------------------------

def test_demo_usa_el_respaldo_cuando_haiku_cae(reloj):
    m = Modelo(reloj, {PRINCIPAL: [_caida(), _caida()]})
    r = _turno({"demo": True}, m)
    assert m.llamadas == [PRINCIPAL, PRINCIPAL, RESPALDO]
    assert _dichos(r) == [f"Responde {RESPALDO[:10]}"]
    assert r["telemetry"]["failsafe"] is False
    assert r["telemetry"]["model_id"] == RESPALDO
    assert reloj.pausas == [0.5]                 # pausas cortas en la demo


def test_demo_con_un_solo_tropiezo_no_llega_al_respaldo(reloj):
    m = Modelo(reloj, {PRINCIPAL: [_caida()]})
    r = _turno({"demo": True}, m)
    assert m.llamadas == [PRINCIPAL, PRINCIPAL]
    assert r["telemetry"]["model_id"] == PRINCIPAL


def test_todo_falla_sale_el_failsafe(reloj):
    m = Modelo(reloj, {PRINCIPAL: [_caida()] * 5, RESPALDO: [_caida()] * 5})
    r = _turno({"demo": True}, m)
    assert m.llamadas == [PRINCIPAL, PRINCIPAL, RESPALDO]
    assert r["telemetry"]["failsafe"] is True


def test_los_timeouts_no_pasan_el_plazo_del_turno(reloj):
    """Cada intento que se cuelga gasta 12 s: con 25 s de plazo caben dos y el
    respaldo ya no alcanza (quedarían 0,5 s). Nunca más de ~25 s."""
    timeout = ReadTimeoutError(endpoint_url="https://bedrock")
    m = Modelo(reloj, {PRINCIPAL: [timeout, timeout]}, costo_falla=12.0)
    inicio = reloj.t
    r = _turno({"demo": True}, m)
    assert m.llamadas == [PRINCIPAL, PRINCIPAL]
    assert reloj.t - inicio <= 25.0
    assert r["telemetry"]["failsafe"] is True


def test_el_plazo_es_configurable(reloj, monkeypatch):
    monkeypatch.setenv("DEMO_TURNO_PRESUPUESTO_S", "40")
    timeout = ReadTimeoutError(endpoint_url="https://bedrock")
    m = Modelo(reloj, {PRINCIPAL: [timeout, timeout]}, costo_falla=12.0)
    r = _turno({"demo": True}, m)
    assert m.llamadas == [PRINCIPAL, PRINCIPAL, RESPALDO]
    assert r["telemetry"]["failsafe"] is False


def test_intentos_configurables_y_respaldo_propio_de_la_demo(reloj, monkeypatch):
    monkeypatch.setenv("DEMO_LLM_INTENTOS_MODELO", "1")
    monkeypatch.setenv("DEMO_CHAT_FALLBACK_MODEL_ID", "modelo-respaldo-demo")
    m = Modelo(reloj, {PRINCIPAL: [_caida()]})
    _turno({"demo": True}, m)
    assert m.llamadas == [PRINCIPAL, "modelo-respaldo-demo"]


def test_sin_respaldo_si_se_apaga(reloj, monkeypatch):
    monkeypatch.setenv("DEMO_LLM_INTENTOS_RESPALDO", "0")
    m = Modelo(reloj, {PRINCIPAL: [_caida(), _caida()]})
    r = _turno({"demo": True}, m)
    assert m.llamadas == [PRINCIPAL, PRINCIPAL]
    assert r["telemetry"]["failsafe"] is True


def test_bot_de_cliente_sigue_con_el_plan_de_main(reloj, monkeypatch):
    """Contraprueba: 3 intentos del modelo, pausas de 1 y 3 s, 2 del respaldo; y
    `DEMO_CHAT_FALLBACK_MODEL_ID` no lo toca."""
    monkeypatch.setenv("DEMO_CHAT_FALLBACK_MODEL_ID", "modelo-respaldo-demo")
    m = Modelo(reloj, {PRINCIPAL: [_caida()] * 3, RESPALDO: [_caida()]})
    r = _turno({}, m)
    assert m.llamadas == [PRINCIPAL] * 3 + [RESPALDO] * 2
    assert reloj.pausas == [1.0, 3.0, 1.0]
    assert r["telemetry"]["failsafe"] is False


def test_cliente_de_demo_ajusta_el_timeout_a_lo_que_queda(reloj, monkeypatch):
    vistos = []
    monkeypatch.setattr(llm_engine, "_bedrock_client_demo", lambda t=15: vistos.append(t) or t)
    marca = llm_engine._PLAZO_DEMO.set(reloj.t + 9.6)
    try:
        llm_engine._cliente_demo_para_el_plazo()
        reloj.t += 8.0
        llm_engine._cliente_demo_para_el_plazo()
    finally:
        llm_engine._PLAZO_DEMO.reset(marca)
    marca = llm_engine._PLAZO_DEMO.set(reloj.t + 100)
    try:
        llm_engine._cliente_demo_para_el_plazo()
    finally:
        llm_engine._PLAZO_DEMO.reset(marca)
    assert vistos == [9, 3, 15]


def test_cliente_de_demo_sin_reintentos_de_botocore():
    llm_engine._bedrock_client_demo.cache_clear()
    try:
        with patch("boto3.client") as mk:
            llm_engine._bedrock_client_demo(11)
        cfg = mk.call_args.kwargs["config"]
        assert cfg.read_timeout == 11 and cfg.connect_timeout == 3
        assert cfg.retries["total_max_attempts"] == 1
    finally:
        llm_engine._bedrock_client_demo.cache_clear()


def test_el_plazo_no_queda_puesto_despues_del_turno(reloj):
    _turno({"demo": True}, Modelo(reloj, {}))
    assert llm_engine._PLAZO_DEMO.get() is None and llm_engine._TURNO_DEMO.get() is False


# ---------------------------------------------------------------------------
# 2. Todo por env (se leen al importar: se prueban en un proceso aparte)
# ---------------------------------------------------------------------------

def _leer_en_proceso(env: dict, codigo: str) -> str:
    entorno = {**os.environ, **env}
    entorno.setdefault("APP_ENCRYPTION_KEY", os.environ["APP_ENCRYPTION_KEY"])
    salida = subprocess.run(
        [sys.executable, "-c", codigo], cwd=RAIZ, env=entorno,
        capture_output=True, text=True, timeout=120,
    )
    assert salida.returncode == 0, salida.stderr[-2000:]
    return salida.stdout.strip().splitlines()[-1]


def test_concurrencia_y_rate_limits_por_env():
    codigo = (
        "from app.services import demo_bot; from app.routers import demo as d;"
        "print(demo_bot.MAX_CONCURRENTES, demo_bot.MAX_EN_ESPERA, demo_bot._EJECUTOR._max_workers,"
        " d._SEM_TURNOS._initial_value, d._RATE_TURNOS._por_ip, d._RATE_TURNOS._global,"
        " d._RATE_EVENTOS._por_ip, d._RATE_EVENTOS._global)"
    )
    por_defecto = _leer_en_proceso({}, codigo)
    assert por_defecto == "2 4 2 4 60 200 30 2000"
    convencion = _leer_en_proceso({
        "DEMO_GENERACIONES_SIMULTANEAS": "6", "DEMO_GENERACIONES_EN_ESPERA": "10",
        "DEMO_TURNOS_SIMULTANEOS": "10", "DEMO_TURNOS_IP_HORA": "100000",
        "DEMO_TURNOS_GLOBAL_HORA": "20000", "DEMO_EVENTOS_IP_HORA": "100000",
        "DEMO_EVENTOS_GLOBAL_HORA": "100000",
    }, codigo)
    assert convencion == "6 10 6 10 100000 20000 100000 100000"


def test_topes_por_env(monkeypatch):
    for nombre, valor in (("DEMO_MAX_POR_IP_HORA", "100000"), ("DEMO_MAX_TURNOS", "40"),
                          ("DEMO_MAX_LEADS_DIA", "10000")):
        monkeypatch.setenv(nombre, valor)
        assert router_demo._tope(nombre) == int(valor)


# ---------------------------------------------------------------------------
# 3. CONSENT_VERSION
# ---------------------------------------------------------------------------

def test_consent_version():
    assert router_demo.CONSENT_VERSION == "demo-2026-10b"


# ---------------------------------------------------------------------------
# Ráfaga de convención: nada retiene una conexión mientras habla con Bedrock
# ---------------------------------------------------------------------------

from tests.test_demo_api import (  # noqa: E402,F401  (fixtures)
    Sesion, _demo_lista, _h, _iniciar, client, cuenta_demos, db, entorno, generacion_modelo,
)


def test_la_generacion_suelta_la_conexion_mientras_genera(client, Sesion, monkeypatch):
    from app.services import demo_bot

    sesiones = []

    def _nueva():
        s = Sesion()
        sesiones.append(s)
        return s
    monkeypatch.setattr(router_demo, "_nueva_sesion", _nueva)
    vistos = []
    original = demo_bot.generar_contenido

    def _generar(*a, **k):
        vistos.append(sesiones[-1].in_transaction())
        return original(*a, **k)
    monkeypatch.setattr(demo_bot, "generar_contenido", _generar)
    r = _iniciar(client)
    assert r.status_code == 202
    assert vistos == [False]


def test_el_turno_no_retiene_la_sesion_ni_el_bot(client, monkeypatch):
    import sqlalchemy

    demo_id, token = _demo_lista(client)
    vistos = []

    def _advance(bot, state, mensaje, runtime=None):
        vistos.append(sqlalchemy.inspect(bot).detached)
        assert bot.llm_config and bot.instrucciones          # lo cargado sigue ahí
        return {"actions": [{"type": "say", "payload": {"text": "Hola"}}],
                "next_state": None, "finished": False, "telemetry": None}
    monkeypatch.setattr(llm_engine, "advance", _advance)
    r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert r.status_code == 200 and vistos == [True]


def test_pool_de_la_base_por_env():
    codigo = "from app.database import engine; print(engine.pool.size(), engine.pool._max_overflow)"
    assert _leer_en_proceso({}, codigo) == "5 10"
    assert _leer_en_proceso({"DB_POOL_SIZE": "15", "DB_MAX_OVERFLOW": "15"}, codigo) == "15 15"


def test_turno_espera_un_cupo_si_se_configura(client, db, monkeypatch):
    import threading as _th

    demo_id, token = _demo_lista(client)
    sem = _th.BoundedSemaphore(1)
    sem.acquire()
    monkeypatch.setattr(router_demo, "_SEM_TURNOS", sem)
    # Sin espera (default): «muy solicitada» de una.
    r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert r.json()["actions"][0]["text"] == router_demo.TEXTO_MUY_SOLICITADA
    # Con espera: el cupo que se libera a los 0,2 s atiende el turno.
    monkeypatch.setenv("DEMO_TURNO_ESPERA_S", "3")
    _th.Timer(0.2, sem.release).start()
    with patch.object(llm_engine, "advance", return_value={
        "actions": [{"type": "say", "payload": {"text": "Hola 😊"}}],
        "next_state": None, "finished": False, "telemetry": None,
    }):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert r.json()["actions"][0]["text"] == "Hola 😊"


def test_hilos_del_threadpool_por_env():
    codigo = (
        "import anyio, anyio.to_thread\n"
        "from app.main import _hilos_del_threadpool\n"
        "async def f():\n"
        "    await _hilos_del_threadpool()\n"
        "    return anyio.to_thread.current_default_thread_limiter().total_tokens\n"
        "print(anyio.run(f))"
    )
    env = {"POSTGRES_HOST": "localhost", "POSTGRES_PORT": "1", "POSTGRES_USER": "x",
           "POSTGRES_DB": "x"}
    assert _leer_en_proceso({**env, "APP_HILOS": "80"}, _codigo_sin_db(codigo)) == "80"
    assert _leer_en_proceso(env, _codigo_sin_db(codigo)) == "40"


def _codigo_sin_db(codigo: str) -> str:
    """`app.main` hace `create_all()` al importarse: en el proceso de prueba se
    cambia por un motor SQLite en memoria antes de importarlo."""
    return (
        "import sqlalchemy, app.database as d;"
        "d.engine = sqlalchemy.create_engine('sqlite://');"
        "d.Base.metadata.create_all = lambda *a, **k: None;\n" + codigo
    )
