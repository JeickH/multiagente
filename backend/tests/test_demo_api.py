"""Tests de la API pública de la demo (`routers/demo.py`, Sprint 32 #613).

Todo corre contra SQLite en memoria con Bedrock mockeado: la generación por
`demo_bot._invocar` y el chat por `llm_engine._invoke_model`. Sin red, sin AWS.

Lo que protegen (revisión de seguridad #608):
  * A1: topes en la base por IP, correo y teléfono (normalizados), global y
    mensual; un solo texto para todos los 429.
  * A2: semáforo y rate-limit de turnos; `generando` vencido → respaldo.
  * A3: contador de turnos atómico en la fila y tope de 15.
  * Token: 404 uniforme para todo lo inválido.
  * M5: ninguna respuesta devuelve nombre, correo ni teléfono; la telemetría no
    guarda el texto.
  * M6: el bot de demo no toma mensajes entrantes y solo declara sus 5
    herramientas.
"""
from __future__ import annotations

import importlib.util
import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models
from app.routers import demo as router_demo
from app.services import bot_router, demo_bot, llm_engine, productos, ratelimit

OWNER = "demos@glomacx.com"
NOMBRE = "Ana Prueba Ficticia"
CORREO = "ana.ficticia@example.com"
TELEFONO = "300 000 0001"           # sintético (regla #8)
TELEFONO_E164 = "+573000000001"

#: #619: sin `fechas_disponibles` (su «Octubre: todo el mes» se leía como
#: disponibilidad).
HERRAMIENTAS_DEMO = {
    "escalar_a_asesor", "finalizar_conversacion",
    "abrir_producto", "consultar_precios",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def Sesion():
    from app.database import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def db(Sesion):
    s = Sesion()
    yield s
    s.close()


def _usuario(db, correo, documento):
    u = models.User(
        nombre="Cuenta", tipo_documento="NIT", documento=documento,
        correo=correo, hashed_password="sin-clave",
    )
    db.add(u)
    db.commit()
    return u


@pytest.fixture
def cuenta_demos(db):
    owner = _usuario(db, OWNER, "GLOMADEMOS1")
    team = crud.create_team(db, "Demos", owner)
    return SimpleNamespace(owner=owner, team=team)


@pytest.fixture(autouse=True)
def entorno(monkeypatch, Sesion):
    for var in (
        "DEMO_IP_HEADER", "DEMO_TURNSTILE_SECRET", "DEMO_OWNER_EMAIL",
        "DEMO_MAX_POR_IP_HORA", "DEMO_MAX_POR_IP_DIA", "DEMO_MAX_POR_CORREO_DIA",
        "DEMO_MAX_POR_TELEFONO_DIA", "DEMO_MAX_GLOBAL_DIA", "DEMO_MAX_TURNOS_MES",
        "DEMO_MAX_TURNOS",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(router_demo, "_nueva_sesion", Sesion)
    monkeypatch.setattr(llm_engine, "_productos_db", Sesion)
    monkeypatch.setattr(router_demo, "_RATE_TURNOS", ratelimit.SlidingWindow(60, 200))
    monkeypatch.setattr(router_demo, "_SEM_TURNOS", threading.BoundedSemaphore(4))
    router_demo.limpiar_cache_dueno()
    productos.limpiar_cache()
    yield
    router_demo.limpiar_cache_dueno()
    productos.limpiar_cache()


@pytest.fixture
def generacion_modelo(monkeypatch):
    """Bedrock de la generación: devuelve el respaldo del tipo como si fuera el
    modelo (pasa la misma validación)."""
    def _falso(model_id, system, user):
        tipo = "agencia_viajes" if "agencia_viajes" in user else "hotel"
        return {
            "stop_reason": "tool_use",
            "content": [{
                "type": "tool_use", "name": demo_bot._TOOL_NAME,
                "input": demo_bot.respaldo_crudo(tipo),
            }],
        }
    monkeypatch.setattr(demo_bot, "_invocar", _falso)


@pytest.fixture
def client(Sesion, cuenta_demos, generacion_modelo):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_db

    app = FastAPI()
    app.include_router(router_demo.router)

    def _get_db():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


_ip_n = iter(range(1, 100_000))


def _cuerpo(**over) -> Dict[str, Any]:
    base = {
        "nombre": NOMBRE,
        "empresa": "Hotel Brisas del Carmen",
        "telefono": TELEFONO,
        "correo": CORREO,
        "tipo_empresa": "hotel",
        "acepta_contacto": True,
        "acepta_promociones": False,
        "sitio_web": "",
        "form_ms": 9000,
    }
    base.update(over)
    return base


def _iniciar(client, *, ip=None, **over):
    ip = ip or f"10.0.{next(_ip_n) // 250}.{next(_ip_n) % 250}"
    return client.post("/demo/iniciar", json=_cuerpo(**over),
                       headers={"x-forwarded-for": ip})


def _h(token):
    return {"X-Demo-Token": token}


def _texto(content: str, stop="end_turn"):
    return {"content": [{"type": "text", "text": content}], "stop_reason": stop}


def _tool(name, input_, texto=None, idx="t1"):
    content = []
    if texto:
        content.append({"type": "text", "text": texto})
    content.append({"type": "tool_use", "id": idx, "name": name, "input": input_})
    return {"content": content, "stop_reason": "tool_use"}


class ModeloFalso:
    """`_invoke_model` con respuestas en cola; guarda las herramientas que vio."""

    def __init__(self, respuestas: List[Dict[str, Any]]):
        self.respuestas = list(respuestas)
        self.tools_vistas: List[set] = []
        self.llamadas = 0

    def __call__(self, model_id, system, messages, tools):
        self.llamadas += 1
        self.tools_vistas.append({t["name"] for t in tools})
        resp = self.respuestas.pop(0) if self.respuestas else _texto("¿Algo más?")
        resp = dict(resp)
        resp.setdefault("usage", {"input_tokens": 100, "output_tokens": 20})
        return resp


def _contar(db, modelo):
    db.expire_all()
    return db.query(modelo).count()


def _demo_de(db, demo_id):
    db.expire_all()
    return db.query(models.Demo).filter(
        models.Demo.public_id == uuid.UUID(demo_id)
    ).one()


def _sin_pii(texto: str):
    bajo = texto.lower()
    assert NOMBRE.lower() not in bajo
    assert CORREO.lower() not in bajo
    assert "3000000001" not in texto and TELEFONO not in texto


# ---------------------------------------------------------------------------
# Flujo feliz
# ---------------------------------------------------------------------------

def test_flujo_feliz_iniciar_estado_chat(client, db, cuenta_demos):
    r = _iniciar(client, correo="Ana.Ficticia@EXAMPLE.com")
    assert r.status_code == 202, r.text
    _sin_pii(r.text)
    body = r.json()
    demo_id, token = body["demo_id"], body["token"]

    # Lead con PII normalizada.
    lead = db.query(models.Lead).one()
    assert lead.source == "gloma_demo"
    assert lead.email == CORREO
    assert lead.telefono == TELEFONO_E164
    assert lead.agencia == "Hotel Brisas del Carmen"
    assert lead.acepto_privacidad_at is not None

    # La tarea de fondo ya corrió (TestClient la ejecuta antes de volver).
    demo = _demo_de(db, demo_id)
    assert demo.estado == "lista"
    assert demo.origen_productos == "modelo"
    assert demo.consent_version == "demo-2026-10c"
    assert demo.acepta_promociones is False and demo.acepta_promociones_at is None
    bot = db.query(models.Bot).get(demo.bot_id)
    assert bot.user_id == cuenta_demos.owner.id and bot.team_id == cuenta_demos.team.id
    assert bot.channels == "demo" and bot.engine == "llm" and bot.status == "active"
    assert bot.trigger_type == models.BOT_TRIGGER_MANUAL
    assert bot.reparto_pct is None and bot.reparto_desde is None
    assert json.loads(bot.llm_config) == {
        "fuente_datos": "productos", "demo": True,
        "model_id": "global.anthropic.claude-haiku-4-5-20251001-v1:0",
    }
    # Las 3 fichas van al final de las instrucciones (#619).
    assert "## Fichas de los productos" in bot.instrucciones
    assert "«Hotel Brisas del Carmen»" in bot.instrucciones
    assert "«Hotel»" in bot.instrucciones
    assert "{empresa}" not in bot.instrucciones and "{tipo_empresa}" not in bot.instrucciones
    prods = db.query(models.BotProducto).filter(
        models.BotProducto.team_id == cuenta_demos.team.id
    ).all()
    assert len(prods) == 3
    prefijo = f"demo-{uuid.UUID(demo_id).hex[:12]}-"
    assert all(p.slug.startswith(prefijo) for p in prods)
    assert all(p.estado == "publicado" for p in prods)
    assert db.query(models.BotProductoFila).count() == 36
    assert db.query(models.BotProductoBot).filter_by(bot_id=bot.id).count() == 3

    r = client.get(f"/demo/{demo_id}/estado", headers=_h(token))
    assert r.status_code == 200
    _sin_pii(r.text)
    est = r.json()
    assert est["estado"] == "lista"
    assert est["empresa"] == "Hotel Brisas del Carmen"
    assert len(est["productos"]) == 3 and set(est["productos"][0]) == {"nombre", "resumen"}
    assert est["mensaje_sugerido"]

    slug = prods[0].slug
    modelo = ModeloFalso([
        _tool("abrir_producto", {"producto": slug}),
        _texto("¡Hola! Qué bueno que nos escribes 😊 ¿Con quién tengo el gusto?"),
    ])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token),
                        json={"message": est["mensaje_sugerido"], "session": "basura"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["session"] is None
    assert out["finished"] is False and out["handoff"] is False
    assert out["actions"][0]["text"].startswith("¡Hola!")
    _sin_pii(r.text)

    # Las herramientas que vio el modelo: las 5 de la demo, ni una más.
    assert modelo.tools_vistas[0] == HERRAMIENTAS_DEMO

    demo = _demo_de(db, demo_id)
    assert demo.turnos == 1
    assert [t["rol"] for t in demo.transcripcion] == ["usuario", "bot"]
    assert len(demo.chat_state["history"]) == 2

    # Telemetría: tokens sí, texto no.
    dec = db.query(models.BotLlmDecision).one()
    assert dec.source == "demo" and dec.bot_id == bot.id
    assert dec.user_input is None and dec.reply_preview is None
    assert dec.tokens_in == 200
    assert json.loads(dec.tools_called) == [{"tool": "abrir_producto"}]
    assert dec.chat_ref == f"demo-{demo.id}"

    # Segundo turno: el historial sale de la fila, no del cliente.
    modelo2 = ModeloFalso([_texto("Perfecto, Andrés. ¿Para cuántas personas?")])
    with patch.object(llm_engine, "_invoke_model", modelo2):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token),
                        json={"message": "Soy Andrés, para diciembre"})
    assert r.status_code == 200
    demo = _demo_de(db, demo_id)
    assert demo.turnos == 2 and len(demo.chat_state["history"]) == 4


def test_promociones_guarda_la_fecha(client, db):
    r = _iniciar(client, acepta_promociones=True)
    demo = _demo_de(db, r.json()["demo_id"])
    assert demo.acepta_promociones is True and demo.acepta_promociones_at is not None


def test_tipo_otro_se_descarta_si_el_tipo_no_es_otro(client, db):
    r = _iniciar(client, tipo_otro="avistamiento de aves")
    assert r.status_code == 202
    assert _demo_de(db, r.json()["demo_id"]).tipo_otro is None


def test_tipo_otro_llega_a_la_plantilla(client, db):
    r = _iniciar(client, tipo_empresa="otro", tipo_otro="Avistamiento de aves")
    demo = _demo_de(db, r.json()["demo_id"])
    assert demo.tipo_otro == "Avistamiento de aves"
    bot = db.query(models.Bot).get(demo.bot_id)
    assert "«Avistamiento de aves»" in bot.instrucciones


# ---------------------------------------------------------------------------
# Validación (422)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("over,campo", [
    ({"acepta_contacto": False}, None),
    ({"tipo_empresa": "casino"}, "tipo_empresa"),
    ({"empresa": "Hotel 3001234567"}, "empresa"),
    ({"empresa": "Hotel {empresa}"}, "empresa"),
    ({"empresa": "ver hotelx.com"}, "empresa"),
    ({"telefono": "abc"}, "telefono"),
    ({"correo": "no-es-correo"}, "correo"),
])
def test_entradas_invalidas_dan_422(client, db, over, campo):
    r = _iniciar(client, **over)
    assert r.status_code == 422
    if campo:
        assert any(d["loc"][-1] == campo for d in r.json()["detail"])
    assert _contar(db, models.Lead) == 0


# ---------------------------------------------------------------------------
# Honeypot y tiempo de llenado (M7)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("over", [
    {"sitio_web": "http://spam.example"},
    {"form_ms": 1200},
    {"form_ms": None},
])
def test_honeypot_y_tiempo_dan_202_falso_sin_crear_nada(client, db, over):
    r = _iniciar(client, **over)
    assert r.status_code == 202
    body = r.json()
    assert set(body) == {"demo_id", "token"}
    uuid.UUID(body["demo_id"])
    assert _contar(db, models.Lead) == 0
    assert _contar(db, models.Demo) == 0
    assert _contar(db, models.Bot) == 0
    # Y el token falso no abre nada.
    r = client.get(f"/demo/{body['demo_id']}/estado", headers=_h(body["token"]))
    assert r.status_code == 404


def test_turnstile_obligatorio_solo_con_secreto(client, db, monkeypatch):
    monkeypatch.setenv("DEMO_TURNSTILE_SECRET", "secreto-de-prueba")
    r = _iniciar(client)
    assert r.status_code == 400
    assert _contar(db, models.Lead) == 0

    class _Resp:
        status_code = 200

        def __init__(self, ok):
            self._ok = ok

        def json(self):
            return {"success": self._ok}

    with patch.object(router_demo.httpx, "post", return_value=_Resp(False)):
        assert _iniciar(client, turnstile_token="x").status_code == 400
    with patch.object(router_demo.httpx, "post", side_effect=TimeoutError()):
        assert _iniciar(client, turnstile_token="x").status_code == 400
    with patch.object(router_demo.httpx, "post", return_value=_Resp(True)):
        assert _iniciar(client, turnstile_token="x").status_code == 202


# ---------------------------------------------------------------------------
# Topes en la base (A1) y texto único del 429 (M8)
# ---------------------------------------------------------------------------

def _correo(n):
    return f"persona{n}@example.com"


def _tel(n):
    return f"300 000 {n:04d}"


def test_tope_por_ip_hora(client, db):
    for n in range(5):
        assert _iniciar(client, ip="1.1.1.1", correo=_correo(n), telefono=_tel(n)).status_code == 202
    r = _iniciar(client, ip="1.1.1.1", correo=_correo(9), telefono=_tel(9))
    assert r.status_code == 429
    assert r.json() == {"detail": router_demo.TEXTO_429}
    assert _contar(db, models.Lead) == 5 and _contar(db, models.Demo) == 5


def test_correo_con_mayusculas_no_evade_el_tope(client, db):
    for n, correo in enumerate(["ana@example.com", "ANA@example.com", "Ana@Example.COM"]):
        assert _iniciar(client, correo=correo, telefono=_tel(n)).status_code == 202
    r = _iniciar(client, correo="aNa@EXAMPLE.com", telefono=_tel(7))
    assert r.status_code == 429
    assert r.json() == {"detail": router_demo.TEXTO_429}
    assert _contar(db, models.Lead) == 3


def test_telefono_con_otro_formato_no_evade_el_tope(client, db):
    for n, tel in enumerate(["3000000099", "+57 300 000 0099", "(300) 000-0099"]):
        assert _iniciar(client, correo=_correo(n), telefono=tel).status_code == 202
    r = _iniciar(client, correo=_correo(8), telefono="57 300 000 0099")
    assert r.status_code == 429
    assert r.json() == {"detail": router_demo.TEXTO_429}


def test_tope_global_guarda_el_lead_sin_demo(client, db, monkeypatch):
    monkeypatch.setenv("DEMO_MAX_GLOBAL_DIA", "2")
    for n in range(2):
        assert _iniciar(client, correo=_correo(n), telefono=_tel(n)).status_code == 202
    r = _iniciar(client, correo=_correo(5), telefono=_tel(5))
    assert r.status_code == 429
    assert r.json() == {"detail": router_demo.TEXTO_429}
    assert _contar(db, models.Lead) == 3      # demanda real: el lead se guarda
    assert _contar(db, models.Demo) == 2
    assert _contar(db, models.Bot) == 2


def test_freno_mensual_de_turnos_guarda_el_lead(client, db, monkeypatch):
    monkeypatch.setenv("DEMO_MAX_TURNOS_MES", "0")
    r = _iniciar(client)
    assert r.status_code == 429
    assert r.json() == {"detail": router_demo.TEXTO_429}
    assert _contar(db, models.Lead) == 1 and _contar(db, models.Demo) == 0


def test_sin_cuenta_duena_guarda_el_lead_y_da_429(client, db, monkeypatch):
    monkeypatch.setenv("DEMO_OWNER_EMAIL", "no-existe@example.com")
    r = _iniciar(client)
    assert r.status_code == 429
    assert _contar(db, models.Lead) == 1 and _contar(db, models.Demo) == 0


def test_ip_sale_solo_del_header_configurado(client, db, monkeypatch):
    monkeypatch.setenv("DEMO_IP_HEADER", "x-gloma-client-ip")
    for n in range(5):
        r = client.post("/demo/iniciar", json=_cuerpo(correo=_correo(n), telefono=_tel(n)),
                        headers={"x-gloma-client-ip": "9.9.9.9",
                                 "x-forwarded-for": f"7.7.7.{n}"})
        assert r.status_code == 202
    # Cambiar el XFF no sirve: la IP es la del header de API Gateway.
    r = client.post("/demo/iniciar", json=_cuerpo(correo=_correo(6), telefono=_tel(6)),
                    headers={"x-gloma-client-ip": "9.9.9.9", "x-forwarded-for": "8.8.8.8"})
    assert r.status_code == 429
    assert {l.ip_address for l in db.query(models.Lead).all()} == {"9.9.9.9"}


# ---------------------------------------------------------------------------
# Token: 404 uniformes
# ---------------------------------------------------------------------------

def _demo_lista(client):
    body = _iniciar(client).json()
    return body["demo_id"], body["token"]


def test_404_uniformes(client):
    demo_id, token = _demo_lista(client)
    otro_id, otro_token = _demo_lista(client)
    vencido = router_demo._fernet().encrypt_at_time(
        json.dumps({"p": "demo", "v": 1, "d": demo_id}).encode(),
        int(time.time()) - 7 * 3600,
    ).decode()
    otro_proposito = router_demo._fernet().encrypt(
        json.dumps({"p": "otra", "v": 1, "d": demo_id}).encode()
    ).decode()
    from app.services.crypto import encrypt_secret
    con_la_clave_maestra = encrypt_secret(json.dumps({"p": "demo", "v": 1, "d": demo_id}))
    inexistente = str(uuid.uuid4())

    casos = [
        (demo_id, None),
        (demo_id, ""),
        (demo_id, "no-es-un-token"),
        (demo_id, otro_token),                 # token de otra demo
        (demo_id, vencido),
        (demo_id, otro_proposito),
        (demo_id, con_la_clave_maestra),       # Fernet de la app, no la subclave
        ("no-es-un-uuid", token),
        (inexistente, router_demo.emitir_token(uuid.UUID(inexistente))),
    ]
    for path_id, tok in casos:
        headers = _h(tok) if tok is not None else {}
        r1 = client.get(f"/demo/{path_id}/estado", headers=headers)
        r2 = client.post(f"/demo/{path_id}/chat", headers=headers, json={"message": "hola"})
        for r in (r1, r2):
            assert r.status_code == 404, (path_id, tok, r.text)
            assert r.json() == {"detail": "Demo no encontrada"}
    # El bueno sí abre.
    assert client.get(f"/demo/{demo_id}/estado", headers=_h(token)).status_code == 200
    assert client.get(f"/demo/{otro_id}/estado", headers=_h(otro_token)).status_code == 200


def test_el_token_no_es_un_token_de_la_app(client):
    """La subclave HKDF separa dominios: el token de la demo no lo abre la
    clave maestra (ni sirve como sesión del landing)."""
    from app.services.crypto import CryptoError, decrypt_secret

    _, token = _demo_lista(client)
    with pytest.raises(CryptoError):
        decrypt_secret(token)


# ---------------------------------------------------------------------------
# Contador atómico y tope de turnos (A3)
# ---------------------------------------------------------------------------

def test_tope_de_turnos(client, db, monkeypatch):
    monkeypatch.setenv("DEMO_MAX_TURNOS", "2")
    demo_id, token = _demo_lista(client)
    modelo = ModeloFalso([_texto("Uno"), _texto("Dos"), _texto("Tres")])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r1 = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "a"})
        r2 = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "b"})
        r3 = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "c"})
    assert r1.json()["finished"] is False
    assert r2.json()["finished"] is True            # el turno que llega al tope
    assert r3.json()["finished"] is True
    assert r3.json()["actions"][0]["text"] == router_demo.TEXTO_FIN_TURNOS
    assert modelo.llamadas == 2                      # el tercero no llamó al modelo
    demo = _demo_de(db, demo_id)
    assert demo.turnos == 2
    assert len(demo.transcripcion) == 4


def test_contador_atomico_con_turnos_concurrentes(tmp_path):
    """El UPDATE condicionado no deja pasar del tope aunque N hilos lo pidan a
    la vez (el chequeo y el incremento son una sola sentencia).

    Base en archivo y una conexión por hilo: con la base en memoria de las
    otras pruebas todos los hilos compartirían la misma conexión."""
    from sqlalchemy import text

    from app.database import Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'turnos.db'}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Sesion()
    lead = models.Lead(email="x@example.com", telefono="+573000000000", source="gloma_demo")
    s.add(lead)
    s.flush()
    demo = models.Demo(
        empresa="E", tipo_empresa="hotel", acepta_contacto_at=datetime.utcnow(),
        consent_version="demo-2026-10", lead_id=lead.id,
    )
    s.add(demo)
    s.commit()
    demo_id = demo.id
    s.close()

    ganados: List[int] = []
    lock = threading.Lock()

    def _intento():
        ss = Sesion()
        try:
            n = ss.execute(
                text("UPDATE demos SET turnos = turnos + 1 WHERE id = :id AND turnos < :max RETURNING turnos"),
                {"id": demo_id, "max": 15},
            ).scalar()
            ss.commit()
            if n is not None:
                with lock:
                    ganados.append(n)
        finally:
            ss.close()

    hilos = [threading.Thread(target=_intento) for _ in range(40)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    engine.dispose()
    assert sorted(ganados) == list(range(1, 16))


def test_semaforo_lleno_no_gasta_turno(client, db, monkeypatch):
    demo_id, token = _demo_lista(client)
    sem = threading.BoundedSemaphore(1)
    sem.acquire()
    monkeypatch.setattr(router_demo, "_SEM_TURNOS", sem)
    modelo = ModeloFalso([_texto("no debería salir")])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert r.json()["actions"][0]["text"] == router_demo.TEXTO_MUY_SOLICITADA
    assert r.json()["finished"] is False
    assert modelo.llamadas == 0
    assert _demo_de(db, demo_id).turnos == 0


def test_rate_limit_de_turnos_no_gasta_turno(client, db, monkeypatch):
    demo_id, token = _demo_lista(client)
    monkeypatch.setattr(router_demo, "_RATE_TURNOS", ratelimit.SlidingWindow(1, 100))
    modelo = ModeloFalso([_texto("uno")])
    with patch.object(llm_engine, "_invoke_model", modelo):
        client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "a"})
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "b"})
    assert r.json()["actions"][0]["text"] == router_demo.TEXTO_MUY_SOLICITADA
    assert _demo_de(db, demo_id).turnos == 1


def test_freno_mensual_corta_el_chat(client, db, monkeypatch):
    demo_id, token = _demo_lista(client)
    monkeypatch.setenv("DEMO_MAX_TURNOS_MES", "0")
    modelo = ModeloFalso([_texto("uno")])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "a"})
    assert r.json()["actions"][0]["text"] == router_demo.TEXTO_MUY_SOLICITADA
    assert modelo.llamadas == 0


def test_mensaje_vacio_da_422_sin_gastar_turno(client, db):
    demo_id, token = _demo_lista(client)
    r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "  "})
    assert r.status_code == 422
    assert _demo_de(db, demo_id).turnos == 0


# ---------------------------------------------------------------------------
# Handoff, medios y aislamiento del bot
# ---------------------------------------------------------------------------

def test_handoff_sin_contactos_de_gloma(client, db):
    demo_id, token = _demo_lista(client)
    modelo = ModeloFalso([
        _tool("escalar_a_asesor", {"motivo": "reserva", "resumen": "2 personas"},
              texto="Listo 🙌 Le paso tu reserva a una persona del equipo."),
    ])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token),
                        json={"message": "Lo quiero, soy Ana, 2 personas el 20 de diciembre"})
    out = r.json()
    assert out["handoff"] is True and out["finished"] is True
    texto = " ".join(a["text"] for a in out["actions"])
    assert "315" not in texto and "wa.me" not in texto and "WhatsApp" not in texto
    # El historial se conserva aunque el motor cierre la sesión.
    assert len(_demo_de(db, demo_id).chat_state["history"]) == 2
    dec = db.query(models.BotLlmDecision).one()
    assert json.loads(dec.tools_called) == [{"tool": "escalar_a_asesor"}]


def test_say_media_se_descarta(client):
    demo_id, token = _demo_lista(client)
    falso = {
        "actions": [
            {"type": "say_media", "payload": {"url": "https://x.example/a.jpg", "caption": "c"}},
            {"type": "say", "payload": {"text": "Hola"}},
        ],
        "next_state": {"history": [{"role": "user", "content": "a"},
                                   {"role": "assistant", "content": "Hola"}]},
        "finished": False,
        "telemetry": None,
    }
    with patch.object(llm_engine, "advance", return_value=falso):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "a"})
    assert [a["type"] for a in r.json()["actions"]] == ["say"]


def test_bot_de_otra_cuenta_no_se_carga(client, db):
    demo_id, token = _demo_lista(client)
    ajeno = _usuario(db, "ajena@example.com", "AJENA1")
    bot = models.Bot(user_id=ajeno.id, name="Ajeno", engine="llm", channels="whatsapp")
    db.add(bot)
    db.commit()
    demo = _demo_de(db, demo_id)
    demo.bot_id = bot.id
    db.commit()
    r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert r.status_code == 404


def test_chat_antes_de_lista_da_409(client, db, monkeypatch):
    monkeypatch.setattr(router_demo, "generar_en_fondo", lambda demo_id: None)
    demo_id, token = _demo_lista(client)
    r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert r.status_code == 409


# ---------------------------------------------------------------------------
# `generando` vencido (A2)
# ---------------------------------------------------------------------------

def test_generando_vencido_se_resuelve_con_el_respaldo(client, db, monkeypatch):
    monkeypatch.setattr(router_demo, "generar_en_fondo", lambda demo_id: None)
    demo_id, token = _demo_lista(client)

    r = client.get(f"/demo/{demo_id}/estado", headers=_h(token))
    assert r.json() == {"estado": "generando", "empresa": "Hotel Brisas del Carmen",
                        "productos": [], "mensaje_sugerido": None, "terminada": False}

    demo = _demo_de(db, demo_id)
    demo.created_at = datetime.utcnow() - timedelta(seconds=90)
    db.commit()

    r = client.get(f"/demo/{demo_id}/estado", headers=_h(token))
    est = r.json()
    assert est["estado"] == "lista"
    respaldo = demo_bot.respaldo("Hotel Brisas del Carmen", "hotel")
    assert [p["nombre"] for p in est["productos"]] == [p.nombre for p in respaldo.productos]
    assert est["mensaje_sugerido"] == respaldo.mensaje_sugerido
    assert _demo_de(db, demo_id).origen_productos == "respaldo"

    # Una segunda consulta no arma otro bot.
    client.get(f"/demo/{demo_id}/estado", headers=_h(token))
    assert _contar(db, models.Bot) == 1


def test_la_tarea_tardia_no_duplica_el_bot(client, db, monkeypatch):
    """Si el respaldo por vencimiento ya resolvió la demo, la tarea de fondo
    que llega tarde no arma un segundo bot."""
    monkeypatch.setattr(router_demo, "generar_en_fondo", lambda demo_id: None)
    demo_id, token = _demo_lista(client)
    demo = _demo_de(db, demo_id)
    demo.created_at = datetime.utcnow() - timedelta(seconds=90)
    db.commit()
    client.get(f"/demo/{demo_id}/estado", headers=_h(token))
    monkeypatch.undo()
    router_demo.generar_en_fondo(demo.id)
    assert _contar(db, models.Bot) == 1


def test_fallo_de_bedrock_sale_el_respaldo(client, db, monkeypatch):
    def _revienta(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(demo_bot, "_invocar", _revienta)
    demo_id, token = _demo_lista(client)
    est = client.get(f"/demo/{demo_id}/estado", headers=_h(token)).json()
    assert est["estado"] == "lista"
    assert _demo_de(db, demo_id).origen_productos == "respaldo"


def test_fallo_de_bd_deja_la_demo_en_error(client, db, monkeypatch):
    def _revienta(*a, **k):
        raise RuntimeError("bd caída")
    monkeypatch.setattr(router_demo, "materializar", _revienta)
    demo_id, token = _demo_lista(client)
    assert client.get(f"/demo/{demo_id}/estado", headers=_h(token)).json()["estado"] == "error"


# ---------------------------------------------------------------------------
# Aislamiento de la cuenta de demos (M6)
# ---------------------------------------------------------------------------

def test_router_de_entrantes_ignora_bots_de_demo(db, cuenta_demos):
    bot = models.Bot(
        user_id=cuenta_demos.owner.id, team_id=cuenta_demos.team.id, name="Demo",
        engine="llm", channels="demo", status="active",
        # Aunque alguien le cambie el trigger a default o a palabra clave.
        trigger_type=models.BOT_TRIGGER_DEFAULT,
        llm_config=json.dumps({"fuente_datos": "productos", "demo": True}),
    )
    bot_kw = models.Bot(
        user_id=cuenta_demos.owner.id, team_id=cuenta_demos.team.id, name="Demo kw",
        engine="llm", channels="demo", status="active",
        trigger_type=models.BOT_TRIGGER_KEYWORD,
        trigger_config=json.dumps({"keywords": ["hola"]}),
        llm_config=json.dumps({"demo": True}),
    )
    db.add_all([bot, bot_kw])
    db.commit()
    conv = crud.get_or_create_conversation(db, cuenta_demos.team.id, "573000000002")
    elegido, sesion = bot_router.resolve_bot_for_incoming_message(
        db, team=cuenta_demos.team, conversation_id=conv.id, message_text="hola",
    )
    assert elegido is None and sesion is None


def test_tools_del_bot_de_demo():
    cfg = {"fuente_datos": "productos", "demo": True}
    c = demo_bot.respaldo("Viajes Prueba", "agencia_viajes")
    from tests.test_demo_bot import HOY, _a_catalogo

    cats = tuple(_a_catalogo(demo_bot.catalogo_demo(p, HOY), i + 1)
                 for i, p in enumerate(c.productos))
    from app.services import productos_bot

    ctx = productos_bot.Contexto(team_id=7, bot_id=5, catalogos=cats, hoy=HOY)
    nombres = {t["name"] for t in llm_engine._tools_for(cfg, ctx, "")}
    assert nombres == HERRAMIENTAS_DEMO


def _cargar_seed():
    ruta = Path(__file__).resolve().parent.parent / "scripts" / "seed_cuenta_demos.py"
    spec = importlib.util.spec_from_file_location("seed_cuenta_demos_test", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_seed_idempotente_sin_canal_y_sin_imprimir_la_clave(Sesion, monkeypatch, capsys):
    seed = _cargar_seed()
    monkeypatch.setattr(seed, "SessionLocal", Sesion)
    hash_falso = "$2b$12$" + "a" * 53
    monkeypatch.setenv("DEMOS_PWD_HASH", hash_falso)
    assert seed.main() == 0
    assert seed.main() == 0                       # idempotente
    salida = capsys.readouterr().out
    assert hash_falso not in salida

    s = Sesion()
    users = s.query(models.User).filter(models.User.correo == OWNER).all()
    assert len(users) == 1 and users[0].hashed_password == hash_falso
    team = s.query(models.Team).filter(models.Team.owner_user_id == users[0].id).one()
    assert team.modo == models.TEAM_MODO_DEMO
    assert s.query(models.MetaAccount).filter_by(team_id=team.id).count() == 0
    # No es la cuenta de Gloma ni una cuenta supervisada.
    from app.dependencies import GLOMA_EMAIL
    from app.routers.supervision import cuentas_supervisadas
    assert OWNER != GLOMA_EMAIL and OWNER not in cuentas_supervisadas()
    s.close()


def test_seed_sin_hash_deja_una_clave_inutilizable(Sesion, monkeypatch):
    seed = _cargar_seed()
    monkeypatch.setattr(seed, "SessionLocal", Sesion)
    monkeypatch.delenv("DEMOS_PWD_HASH", raising=False)
    assert seed.main() == 0
    s = Sesion()
    u = s.query(models.User).filter(models.User.correo == OWNER).one()
    assert u.hashed_password.startswith("$2")
    assert not crud.pwd_context.verify("", u.hashed_password)
    s.close()


def test_seed_rechaza_un_hash_mal_formado(Sesion, monkeypatch):
    seed = _cargar_seed()
    monkeypatch.setattr(seed, "SessionLocal", Sesion)
    monkeypatch.setenv("DEMOS_PWD_HASH", "contraseña-en-claro")
    with pytest.raises(SystemExit):
        seed.main()


# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,e164", [
    ("3001234567", "+573001234567"),
    ("300 123 4567", "+573001234567"),
    ("+57 300 123 4567", "+573001234567"),
    ("(300) 123-4567", "+573001234567"),
    ("0057 300 123 4567", "+573001234567"),
    ("573001234567", "+573001234567"),
    ("+1 415 555 0100", "+14155550100"),
])
def test_normalizar_telefono(crudo, e164):
    assert router_demo.normalizar_telefono(crudo) == e164


def test_normalizar_telefono_rechaza_basura():
    for crudo in ("abc", "12", "+0 000"):
        with pytest.raises(ValueError):
            router_demo.normalizar_telefono(crudo)


# ---------------------------------------------------------------------------
# Recorte de la narración (solo demo)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("crudo,limpio", [
    ("¡Hola! Qué bueno que nos escribes 😊 Déjame abrir el producto para mostrarte qué incluye.",
     "¡Hola! Qué bueno que nos escribes 😊"),
    ("¡Hola! 😊 Déjame verificar la disponibilidad de la *Suite Premium* para ese fin de semana.",
     "¡Hola! 😊"),
    ("Voy a consultar los precios de diciembre.", ""),
    ("¡Hola! Qué bueno que nos escribes 😊 Déjame traerte esa información.",
     "¡Hola! Qué bueno que nos escribes 😊"),
    ("Permíteme revisarte las fechas.", ""),
    ("Perfecto, Carlos 🙌 ¿Del 20 al 23? Y déjame consultar el precio de diciembre.",
     "Perfecto, Carlos 🙌 ¿Del 20 al 23?"),
    ("Claro, déjame revisar las fechas.", "Claro"),
    ("¡Hola! 🏔️ Déjame ver qué fechas tenemos disponibles para el *Plan* en noviembre.",
     "¡Hola! 🏔️"),
    ("Voy a pasarte con una persona del equipo.", "Voy a pasarte con una persona del equipo."),
    ("Tienes razón: soy un agente de prueba y estos productos son de ejemplo.",
     "Tienes razón: soy un agente de prueba y estos productos son de ejemplo."),
    ("La *Suite* está en *$520.000* por noche. ¿Para cuántas personas?",
     "La *Suite* está en *$520.000* por noche. ¿Para cuántas personas?"),
])
def test_sin_narracion_demo(crudo, limpio):
    assert llm_engine.sin_narracion_demo(crudo) == limpio


def test_burbuja_de_pura_narracion_no_sale(client):
    demo_id, token = _demo_lista(client)
    modelo = ModeloFalso([
        _tool("abrir_producto", {"producto": "x"}, texto="Déjame abrir el producto."),
        _texto("La suite incluye jacuzzi. ¿Para qué fecha?"),
    ])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert [a["text"] for a in r.json()["actions"]] == ["La suite incluye jacuzzi. ¿Para qué fecha?"]
