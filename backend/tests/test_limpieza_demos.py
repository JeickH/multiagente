"""Limpieza de los bots de demo inactivos (Sprint 33, #638).

SQLite con claves foráneas ACTIVAS (como Postgres): así las cascadas y el
`SET NULL` de `demos.bot_id` se prueban de verdad, además de los borrados
explícitos del servicio.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models
from app.routers import demo as router_demo
from app.services import demo_bot, limpieza_demos, productos

AHORA = datetime(2026, 10, 21, 15, 0)
HOY = AHORA.date()


@pytest.fixture
def Sesion(monkeypatch):
    from app.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(conexion, _):
        conexion.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    monkeypatch.delenv("DEMO_OWNER_EMAIL", raising=False)
    monkeypatch.delenv("DEMO_BOT_RETENCION_HORAS", raising=False)
    productos.limpiar_cache()
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def db(Sesion):
    s = Sesion()
    yield s
    s.close()


def _usuario(db, correo, doc):
    u = models.User(nombre="Cuenta", tipo_documento="NIT", documento=doc, correo=correo,
                    hashed_password="x")
    db.add(u)
    db.commit()
    team = crud.create_team(db, "Team " + doc, u)
    return u, team


@pytest.fixture
def cuentas(db):
    demos, team_demos = _usuario(db, "demos@glomacx.com", "DEMOS1")
    cliente, team_cliente = _usuario(db, "cliente@agencia.co", "CLIENTE1")
    return {"demos": (demos, team_demos), "cliente": (cliente, team_cliente)}


_n = iter(range(1, 10_000))


def _lead(db):
    lead = models.Lead(email=f"p{next(_n)}@cliente.co", telefono="+573000000000",
                       source="gloma_demo", nombre="Prospecto Ficticio")
    db.add(lead)
    db.flush()
    return lead


def _demo_con_bot(db, cuenta, *, actividad_hace_h=72, cfg=None, estado="lista",
                  con_decisiones=True, enlazar=True):
    """Una demo con su bot de demo, sus 3 productos y telemetría."""
    user, team = cuenta
    lead = _lead(db)
    bot = models.Bot(
        user_id=user.id, team_id=team.id, name="Demo", engine="llm", channels="demo",
        status="active", trigger_type=models.BOT_TRIGGER_MANUAL,
        llm_config=json.dumps(cfg if cfg is not None else {"fuente_datos": "productos", "demo": True}),
    )
    db.add(bot)
    db.flush()
    contenido = demo_bot.respaldo("Hotel Ficticio", "hotel")
    for i, p in enumerate(contenido.productos, start=1):
        spec = demo_bot.catalogo_demo(p, HOY)
        datos = dict(spec["producto"])
        prod = models.BotProducto(team_id=team.id, slug=f"demo-{bot.id}-{i}-{datos.pop('slug')}", **datos)
        db.add(prod)
        db.flush()
        for v in spec["variantes"]:
            db.add(models.BotProductoVariante(producto_id=prod.id, **v))
        for f in spec["filas"]:
            db.add(models.BotProductoFila(producto_id=prod.id, **f))
        db.add(models.BotProductoBot(bot_id=bot.id, producto_id=prod.id, orden=i))
    if con_decisiones:
        for modelo, t_in, t_out, c_r, c_w in (
            ("global.anthropic.claude-haiku-4-5-20251001-v1:0", 1000, 200, 6000, 6000),
            ("global.anthropic.claude-haiku-4-5-20251001-v1:0", 500, 100, 6000, 0),
            ("global.anthropic.claude-sonnet-4-5-20250929-v1:0", 800, 150, 0, 6000),
        ):
            db.add(models.BotLlmDecision(bot_id=bot.id, source="demo", model_id=modelo, rounds=2,
                                         tokens_in=t_in, tokens_out=t_out, cache_read=c_r,
                                         cache_write=c_w))
    demo = models.Demo(
        empresa="Hotel Ficticio", tipo_empresa="hotel",
        acepta_contacto_at=AHORA - timedelta(days=5), consent_version="demo-2026-10b",
        lead_id=lead.id, bot_id=bot.id if enlazar else None, estado=estado,
        turnos=3, created_at=AHORA - timedelta(days=5),
        lista_at=AHORA - timedelta(days=5),
        ultima_actividad_at=AHORA - timedelta(hours=actividad_hace_h),
        transcripcion=[{"rol": "usuario", "texto": "hola", "at": "x"}],
    )
    db.add(demo)
    db.commit()
    return demo, bot


def _limpiar(db, **kw):
    return limpieza_demos.limpiar_bots_demo_inactivos(db, ahora=AHORA, **kw)


def _conteos(db):
    return {m.__tablename__: db.query(m).count() for m in (
        models.Lead, models.Demo, models.Bot, models.BotProducto, models.BotProductoFila,
        models.BotProductoVariante, models.BotProductoBot, models.BotLlmDecision)}


# ---------------------------------------------------------------------------
# Lo que se borra y lo que se conserva
# ---------------------------------------------------------------------------

def test_borra_el_bot_y_conserva_al_prospecto(db, cuentas):
    demo, bot = _demo_con_bot(db, cuentas["demos"])
    antes = _conteos(db)
    r = _limpiar(db)
    assert r.borradas == [demo.id] and not r.saltadas
    db.expire_all()
    despues = _conteos(db)
    assert despues["leads"] == antes["leads"] and despues["demos"] == antes["demos"]
    for tabla in ("bots", "bot_productos", "bot_producto_filas", "bot_producto_variantes",
                  "bot_producto_bots", "bot_llm_decisions"):
        assert despues[tabla] == 0, tabla
    demo = db.query(models.Demo).get(demo.id)
    assert demo.bot_id is None and demo.bot_eliminado_at == AHORA
    assert demo.transcripcion and demo.turnos == 3          # el resto de la fila intacto


def test_snapshot_de_productos(db, cuentas):
    demo, _ = _demo_con_bot(db, cuentas["demos"])
    esperado = demo_bot.respaldo("Hotel Ficticio", "hotel").productos
    _limpiar(db)
    db.expire_all()
    snap = db.query(models.Demo).get(demo.id).productos_snapshot
    assert [p["nombre"] for p in snap] == [p.nombre for p in esperado]
    assert [p["precio_cop"] for p in snap] == [p.precio_cop for p in esperado]
    assert [p["unidad_precio"] for p in snap] == [p.unidad_precio for p in esperado]
    assert all(p["ficha"] and p["resumen"] for p in snap)
    assert set(snap[0]) == {"nombre", "resumen", "ficha", "precio_cop", "unidad_precio"}


def test_uso_resumen(db, cuentas):
    demo, _ = _demo_con_bot(db, cuentas["demos"])
    _limpiar(db)
    db.expire_all()
    uso = db.query(models.Demo).get(demo.id).uso_resumen
    assert uso["turnos"] == 3 and uso["decisiones"] == 3 and uso["rondas"] == 6
    assert (uso["tokens_in"], uso["tokens_out"], uso["cache_read"], uso["cache_write"]) == \
        (2300, 450, 12000, 12000)
    assert sorted(uso["modelos"]) == sorted([
        "global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ])
    # Haiku: (1500×1 + 300×5 + 12000×0,10 + 6000×1,25)/1e6; Sonnet: (800×3 + 150×15 + 6000×3,75)/1e6
    haiku = (1500 * 1 + 300 * 5 + 12000 * 0.10 + 6000 * 1.25) / 1e6
    sonnet = (800 * 3 + 150 * 15 + 6000 * 3.75) / 1e6
    assert uso["costo_usd_estimado"] == pytest.approx(haiku + sonnet)
    assert uso["sin_tokens"] == 0 and uso["failsafe"] == 0 and uso["escalados"] == 0
    assert uso["primera_decision_at"] and uso["ultima_decision_at"]


def test_modelo_sin_precio_deja_el_costo_en_null(db, cuentas):
    demo, bot = _demo_con_bot(db, cuentas["demos"], con_decisiones=False)
    db.add(models.BotLlmDecision(bot_id=bot.id, source="demo", model_id="otro-modelo",
                                 tokens_in=10, tokens_out=1))
    db.commit()
    _limpiar(db)
    db.expire_all()
    assert db.query(models.Demo).get(demo.id).uso_resumen["costo_usd_estimado"] is None


# ---------------------------------------------------------------------------
# Umbral, estados e idempotencia
# ---------------------------------------------------------------------------

def test_umbral_exacto(db, cuentas):
    justo, _ = _demo_con_bot(db, cuentas["demos"], actividad_hace_h=48)          # no: <, no <=
    pasada, _ = _demo_con_bot(db, cuentas["demos"], actividad_hace_h=48.01)
    reciente, _ = _demo_con_bot(db, cuentas["demos"], actividad_hace_h=47)
    r = _limpiar(db)
    assert r.borradas == [pasada.id]


def test_umbral_por_env_y_por_parametro(db, cuentas, monkeypatch):
    demo, _ = _demo_con_bot(db, cuentas["demos"], actividad_hace_h=30)
    monkeypatch.setenv("DEMO_BOT_RETENCION_HORAS", "72")
    assert _limpiar(db).borradas == []
    assert _limpiar(db, horas=24).borradas == [demo.id]


def test_sin_actividad_registrada_no_se_limpia(db, cuentas):
    """`ultima_actividad_at` NULL falla hacia conservar (la migración la rellena)."""
    demo, _ = _demo_con_bot(db, cuentas["demos"])
    demo.ultima_actividad_at = None
    db.commit()
    assert _limpiar(db).candidatas == 0


def test_actividad_entre_la_seleccion_y_el_borrado(db, cuentas, monkeypatch):
    """Re-chequeo bajo el lock: si llega un turno después de elegirla, se salta."""
    demo, bot = _demo_con_bot(db, cuentas["demos"])
    original = limpieza_demos._candidatas

    def _y_llega_un_turno(sesion, corte, lote):
        filas = original(sesion, corte, lote)
        sesion.execute(models.Demo.__table__.update().values(ultima_actividad_at=AHORA))
        sesion.commit()
        return filas
    monkeypatch.setattr(limpieza_demos, "_candidatas", _y_llega_un_turno)
    r = _limpiar(db)
    assert r.borradas == [] and r.saltadas == [(demo.id, "ya_no_inactiva")]
    assert db.query(models.Bot).get(bot.id) is not None


def test_bot_de_otro_team_no_se_toca(db, cuentas):
    demo, bot = _demo_con_bot(db, cuentas["demos"])
    bot.team_id = cuentas["cliente"][1].id
    db.commit()
    assert _limpiar(db).saltadas == [(demo.id, "bot_de_otro_team")]
    assert db.query(models.Bot).get(bot.id) is not None


def test_recordatorios_del_bot_no_quedan_huerfanos(db, cuentas):
    """`bot_recordatorios` no tiene FK a bots: se borran los de ese bot; los
    de todo el team (`bot_id = 0`) se quedan."""
    demo, bot = _demo_con_bot(db, cuentas["demos"])
    bot_id, team_id = bot.id, cuentas["demos"][1].id
    db.add(models.BotRecordatorio(team_id=team_id, bot_id=bot_id, minutos=30, texto="¿Sigues ahí?"))
    db.add(models.BotRecordatorio(team_id=team_id, bot_id=0, minutos=60, texto="General"))
    db.commit()
    _limpiar(db)
    db.expire_all()
    assert db.query(models.BotRecordatorio).filter_by(bot_id=bot_id).count() == 0
    assert db.query(models.BotRecordatorio).filter_by(bot_id=0).count() == 1


def test_generando_no_se_toca(db, cuentas):
    _demo_con_bot(db, cuentas["demos"], estado="generando")
    assert _limpiar(db).candidatas == 0


def test_idempotente(db, cuentas):
    _demo_con_bot(db, cuentas["demos"])
    assert len(_limpiar(db).borradas) == 1
    segunda = _limpiar(db)
    assert segunda.candidatas == 0 and segunda.borradas == []


def test_simular_no_escribe(db, cuentas):
    demo, _ = _demo_con_bot(db, cuentas["demos"])
    antes = _conteos(db)
    r = _limpiar(db, simular=True)
    assert r.borradas == [demo.id] and r.simular
    db.expire_all()
    assert _conteos(db) == antes
    d = db.query(models.Demo).get(demo.id)
    assert d.bot_eliminado_at is None and d.productos_snapshot is None and d.bot_id is not None


def test_lote_acotado(db, cuentas):
    for _ in range(3):
        _demo_con_bot(db, cuentas["demos"])
    assert len(_limpiar(db, lote=2).borradas) == 2
    assert len(_limpiar(db, lote=2).borradas) == 1


# ---------------------------------------------------------------------------
# Candados: nada que no sea un bot de demo
# ---------------------------------------------------------------------------

def test_bot_de_otra_cuenta_no_se_toca(db, cuentas, caplog):
    demo, bot = _demo_con_bot(db, cuentas["cliente"])          # demo apuntando a bot ajeno
    r = _limpiar(db)
    assert r.borradas == [] and r.saltadas == [(demo.id, "bot_de_otra_cuenta")]
    assert db.query(models.Bot).get(bot.id) is not None
    assert "Prospecto" not in caplog.text and "@" not in caplog.text


def test_bot_sin_flag_demo_no_se_toca(db, cuentas):
    demo, bot = _demo_con_bot(db, cuentas["demos"], cfg={"fuente_datos": "productos"})
    r = _limpiar(db)
    assert r.saltadas == [(demo.id, "bot_sin_flag_demo")]
    assert db.query(models.Bot).get(bot.id) is not None


def test_demo_sin_bot_no_es_candidata(db, cuentas):
    _demo_con_bot(db, cuentas["demos"], enlazar=False)
    assert _limpiar(db).candidatas == 0


def test_sin_cuenta_duena_no_borra_nada(db, cuentas, monkeypatch):
    _demo_con_bot(db, cuentas["demos"])
    monkeypatch.setenv("DEMO_OWNER_EMAIL", "no-existe@glomacx.com")
    r = _limpiar(db)
    assert r.borradas == [] and db.query(models.Bot).count() == 1


def test_bots_de_clientes_jamas_entran(db, cuentas):
    """Un bot de cliente con productos, decisiones y su propia fila en
    bot_producto_bots: nada suyo se mueve, aunque haya demos para limpiar."""
    user, team = cuentas["cliente"]
    bot_cliente = models.Bot(user_id=user.id, team_id=team.id, name="Ventas", engine="llm",
                             channels="whatsapp", llm_config=json.dumps({"fuente_datos": "productos"}))
    db.add(bot_cliente)
    db.flush()
    prod = models.BotProducto(team_id=team.id, slug="plan", nombre="Plan", estado="publicado")
    db.add(prod)
    db.flush()
    db.add(models.BotProductoBot(bot_id=bot_cliente.id, producto_id=prod.id))
    db.add(models.BotLlmDecision(bot_id=bot_cliente.id, source="whatsapp"))
    db.commit()
    _demo_con_bot(db, cuentas["demos"])
    _limpiar(db)
    db.expire_all()
    assert db.query(models.Bot).get(bot_cliente.id) is not None
    assert db.query(models.BotProducto).get(prod.id) is not None
    assert db.query(models.BotProductoBot).filter_by(bot_id=bot_cliente.id).count() == 1
    assert db.query(models.BotLlmDecision).filter_by(bot_id=bot_cliente.id).count() == 1


def test_producto_compartido_con_otro_bot_se_conserva(db, cuentas):
    demo, bot = _demo_con_bot(db, cuentas["demos"])
    otro = models.Bot(user_id=cuentas["demos"][0].id, team_id=cuentas["demos"][1].id,
                      name="Otro", engine="llm", channels="demo",
                      llm_config=json.dumps({"demo": True}))
    db.add(otro)
    db.flush()
    compartido = db.query(models.BotProductoBot).filter_by(bot_id=bot.id).first().producto_id
    db.add(models.BotProductoBot(bot_id=otro.id, producto_id=compartido))
    db.commit()
    _limpiar(db)
    db.expire_all()
    assert db.query(models.BotProducto).get(compartido) is not None
    assert db.query(models.BotProducto).count() == 1


# ---------------------------------------------------------------------------
# El tick la dispara a lo sumo una vez por hora, después de responder
# ---------------------------------------------------------------------------

def test_guardia_horaria():
    from app.routers import internal

    internal._ultima_limpieza = None
    assert internal._toca_limpieza(1000.0) is True
    assert internal._toca_limpieza(1000.0 + 3599) is False
    assert internal._toca_limpieza(1000.0 + 3600) is True
    internal._ultima_limpieza = None


def test_el_tick_la_llama_una_vez_por_hora(Sesion, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_db
    from app.routers import internal

    llamadas = []
    monkeypatch.setattr(internal, "_correr_limpieza_demos", lambda: llamadas.append(1))
    internal._ultima_limpieza = None
    reloj = [5000.0]
    monkeypatch.setattr(internal.time, "monotonic", lambda: reloj[0])
    for var in ("INTERNAL_SECRET", "INTERNAL_API_KEY", "APP_ENV"):
        monkeypatch.delenv(var, raising=False)
    app = FastAPI()
    app.include_router(internal.router)

    def _get_db():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    respuestas = []
    for paso in (0, 60, 120, 3600, 3660):
        reloj[0] = 5000.0 + paso
        respuestas.append(c.post("/internal/bot-scheduler/tick").json()["limpieza_demos"])
    assert respuestas == [True, False, False, True, False]
    assert len(llamadas) == 2
    internal._ultima_limpieza = None


def test_la_corrida_del_tick_no_revienta(monkeypatch):
    from app.routers import internal

    class _Sesion:
        def rollback(self):
            pass

        def close(self):
            pass
    monkeypatch.setattr(internal, "SessionLocal", _Sesion)
    with patch.object(limpieza_demos, "limpiar_bots_demo_inactivos", side_effect=RuntimeError("x")):
        internal._correr_limpieza_demos()          # no levanta


# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------

def _script(Sesion, monkeypatch):
    import importlib.util
    from pathlib import Path

    for var in ("LIMPIEZA_EJECUTAR", "LIMPIEZA_HORAS", "LIMPIEZA_LOTE"):
        monkeypatch.delenv(var, raising=False)
    ruta = Path(__file__).resolve().parent.parent / "scripts" / "limpiar_demos.py"
    spec = importlib.util.spec_from_file_location("limpiar_demos_test", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "SessionLocal", Sesion)
    return mod


def test_script_simula_por_defecto(Sesion, cuentas, db, monkeypatch, capsys):
    demo, _ = _demo_con_bot(db, cuentas["demos"], actividad_hace_h=24 * 365)
    mod = _script(Sesion, monkeypatch)
    assert mod.main([]) == 0
    salida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert salida["borraria"] == 1 and "borradas" not in salida
    assert salida["modo"].startswith("simulacion") and salida["demo_ids"] == [demo.id]
    db.expire_all()
    assert db.query(models.Bot).count() == 1
    assert mod.main(["--ejecutar", "--horas", "48"]) == 0
    salida = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert salida["borradas"] == 1 and salida["modo"] == "ejecucion"
    db.expire_all()
    assert db.query(models.Bot).count() == 0


def test_script_ejecuta_con_la_env(Sesion, cuentas, db, monkeypatch, capsys):
    _demo_con_bot(db, cuentas["demos"], actividad_hace_h=24 * 365)
    mod = _script(Sesion, monkeypatch)
    monkeypatch.setenv("LIMPIEZA_EJECUTAR", "1")
    assert mod.main([]) == 0
    db.expire_all()
    assert db.query(models.Bot).count() == 0


@pytest.mark.parametrize("args", [["--horas", "0"], ["--horas", "-5"], ["--horas", "5.9"],
                                  ["--lote", "0"], ["--lote", "1001"], ["--lote", "-1"]])
def test_script_rechaza_horas_y_lotes_fuera_de_rango(Sesion, cuentas, db, monkeypatch, args):
    _demo_con_bot(db, cuentas["demos"], actividad_hace_h=24 * 365)
    mod = _script(Sesion, monkeypatch)
    with pytest.raises(SystemExit) as e:
        mod.main(["--ejecutar", *args])
    assert "mínimo 6" in str(e.value) or "entre 1 y 1000" in str(e.value)
    db.expire_all()
    assert db.query(models.Bot).count() == 1


# ---------------------------------------------------------------------------
# #642: piso de la retención, lote y canal
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("horas", [0, -10, 5.9, float("nan")])
def test_la_retencion_nunca_baja_de_6_horas(db, cuentas, horas):
    reciente, _ = _demo_con_bot(db, cuentas["demos"], actividad_hace_h=5.5)
    vieja, _ = _demo_con_bot(db, cuentas["demos"], actividad_hace_h=6.5)
    assert _limpiar(db, horas=horas).borradas == [vieja.id]
    assert db.query(models.Demo).get(reciente.id).bot_id is not None


@pytest.mark.parametrize("valor,esperado", [("0", 6.0), ("-3", 6.0), ("5.9", 6.0),
                                            ("72", 72.0), ("basura", 48.0), ("", 48.0)])
def test_retencion_por_env_con_piso(monkeypatch, valor, esperado):
    monkeypatch.setenv("DEMO_BOT_RETENCION_HORAS", valor)
    assert limpieza_demos.retencion_horas() == esperado


def test_lote_acotado_a_mil(db, cuentas):
    _demo_con_bot(db, cuentas["demos"])
    assert len(_limpiar(db, lote=0).borradas) == 1          # 0 → 1
    _demo_con_bot(db, cuentas["demos"])
    assert len(_limpiar(db, lote=10**9).borradas) == 1      # tope 1.000, sin romper


def test_bot_sin_canal_demo_no_se_toca(db, cuentas):
    demo, bot = _demo_con_bot(db, cuentas["demos"])
    bot.channels = "whatsapp"
    db.commit()
    assert _limpiar(db).saltadas == [(demo.id, "bot_sin_canal_demo")]
    assert db.query(models.Bot).get(bot.id) is not None


# ---------------------------------------------------------------------------
# #642: el tick es fail-closed
# ---------------------------------------------------------------------------

@pytest.fixture
def tick(Sesion, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_db
    from app.routers import internal

    for var in ("INTERNAL_SECRET", "INTERNAL_API_KEY", "APP_ENV"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(internal, "_correr_limpieza_demos", lambda: None)
    app = FastAPI()
    app.include_router(internal.router)

    def _get_db():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _get_db
    c = TestClient(app)
    return lambda **h: c.post("/internal/bot-scheduler/tick", headers=h).status_code


def test_tick_en_produccion_sin_llave_configurada_403(tick, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    assert tick() == 403
    assert tick(**{"X-Internal-Secret": "x", "X-Internal-Key": "x"}) == 403


def test_tick_sin_llave_o_con_llave_erronea_403(tick, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_API_KEY", "llave-de-prueba")
    assert tick() == 403
    assert tick(**{"X-Internal-Key": "otra"}) == 403
    assert tick(**{"X-Internal-Secret": "llave-de-prueb"}) == 403
    assert tick(**{"X-Internal-Key": ""}) == 403


@pytest.mark.parametrize("cabecera", ["X-Internal-Key", "X-Internal-Secret"])
@pytest.mark.parametrize("variable", ["INTERNAL_API_KEY", "INTERNAL_SECRET"])
def test_tick_con_la_llave_correcta_200(tick, monkeypatch, cabecera, variable):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(variable, "llave-de-prueba")
    assert tick(**{cabecera: "llave-de-prueba"}) == 200


def test_tick_como_lo_llama_la_lambda_200(tick, monkeypatch):
    """La Lambda manda la misma llave en las dos cabeceras."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("INTERNAL_API_KEY", "llave-de-prueba")
    assert tick(**{"X-Internal-Secret": "llave-de-prueba", "X-Internal-Key": "llave-de-prueba"}) == 200


def test_tick_en_desarrollo_sin_llaves_pasa(tick):
    assert tick() == 200
