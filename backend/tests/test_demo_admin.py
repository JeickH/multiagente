"""#627: eventos del CTA de la demo, `traspaso_at` y el panel `/admin/demos`.

SQLite en memoria, sin red. El portero es el real (`require_gloma_account`) con
JWT firmados como los de `/auth/login`.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app import crud, models
from app.dependencies import GLOMA_EMAIL
from app.routers import admin_demos
from app.routers import demo as router_demo
from app.routers.auth import create_access_token
from app.services import llm_engine
from tests.test_demo_api import (  # noqa: F401  (fixtures)
    ModeloFalso, Sesion, _demo_de, _demo_lista, _h, _iniciar, _tool, client,
    cuenta_demos, db, entorno, generacion_modelo,
)


@pytest.fixture(autouse=True)
def eventos_limpios(monkeypatch):
    from app.services import ratelimit

    monkeypatch.setattr(router_demo, "_RATE_EVENTOS", ratelimit.SlidingWindow(30, 2000))


# ---------------------------------------------------------------------------
# POST /demo/{id}/evento
# ---------------------------------------------------------------------------

def _evento(client, demo_id, token, tipo, **headers):
    return client.post(f"/demo/{demo_id}/evento", headers={**_h(token), **headers},
                       json={"tipo": tipo})


def test_eventos_suben_contadores_y_fechas(client, db):
    demo_id, token = _demo_lista(client)
    for _ in range(3):
        assert _evento(client, demo_id, token, "whatsapp").status_code == 204
    # #629: «agendada» sin apertura previa no escribe (y responde 204 igual).
    assert _evento(client, demo_id, token, "llamada_agendada").status_code == 204
    assert _demo_de(db, demo_id).llamada_agendada_at is None
    assert _evento(client, demo_id, token, "llamada_abierta").status_code == 204
    r = _evento(client, demo_id, token, "llamada_agendada")
    assert r.status_code == 204 and r.content == b""
    demo = _demo_de(db, demo_id)
    assert demo.clics_whatsapp == 3 and demo.aperturas_llamada == 1
    primer = demo.primer_clic_whatsapp_at
    assert primer is not None and demo.primer_apertura_llamada_at is not None
    agendada = demo.llamada_agendada_at
    assert agendada is not None
    # Las fechas «primer_*» y la de agendada no se pisan.
    _evento(client, demo_id, token, "whatsapp")
    _evento(client, demo_id, token, "llamada_agendada")
    demo = _demo_de(db, demo_id)
    assert demo.primer_clic_whatsapp_at == primer and demo.llamada_agendada_at == agendada


def test_techo_de_100(client, db, monkeypatch):
    from app.services import ratelimit

    monkeypatch.setattr(router_demo, "_RATE_EVENTOS", ratelimit.SlidingWindow(10_000, 10_000))
    demo_id, token = _demo_lista(client)
    demo = _demo_de(db, demo_id)
    demo.clics_whatsapp = 99
    db.commit()
    for _ in range(3):
        assert _evento(client, demo_id, token, "whatsapp").status_code == 204
    assert _demo_de(db, demo_id).clics_whatsapp == 100


def test_contador_atomico_con_hilos(tmp_path):
    """El UPDATE con LEAST/MIN no pierde clics con N hilos a la vez ni pasa del
    techo (base en archivo, una conexión por hilo)."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    from app.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'ev.db'}",
                           connect_args={"check_same_thread": False, "timeout": 30})
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    lead = models.Lead(email="x@example.com", telefono="+573000000000", source="gloma_demo")
    s.add(lead)
    s.flush()
    demo = models.Demo(empresa="E", tipo_empresa="hotel", acepta_contacto_at=datetime.utcnow(),
                       consent_version="demo-2026-10", lead_id=lead.id)
    s.add(demo)
    s.commit()
    demo_id = demo.id
    s.close()

    def _uno():
        ss = S()
        try:
            ss.execute(text(router_demo._sql_de("whatsapp", "sqlite")),
                       {"id": demo_id, "techo": 100, "ahora": datetime.utcnow()})
            ss.commit()
        finally:
            ss.close()

    for n, esperado in ((40, 40), (80, 100)):
        hilos = [threading.Thread(target=_uno) for _ in range(n)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join()
        s = S()
        assert s.query(models.Demo).get(demo_id).clics_whatsapp == esperado
        s.close()
    engine.dispose()


def test_el_sql_de_postgres_usa_least():
    assert "LEAST(clics_whatsapp + 1, :techo)" in router_demo._sql_de("whatsapp", "postgresql")
    assert "MIN(" in router_demo._sql_de("whatsapp", "sqlite")


def test_evento_funciona_en_generando_y_error(client, db, monkeypatch):
    monkeypatch.setattr(router_demo, "generar_en_fondo", lambda demo_id: None)
    demo_id, token = _demo_lista(client)
    assert _demo_de(db, demo_id).estado == "generando"
    assert _evento(client, demo_id, token, "whatsapp").status_code == 204
    demo = _demo_de(db, demo_id)
    demo.estado = "error"
    db.commit()
    assert _evento(client, demo_id, token, "llamada_abierta").status_code == 204
    demo = _demo_de(db, demo_id)
    assert (demo.clics_whatsapp, demo.aperturas_llamada) == (1, 1)


def test_tipo_invalido_422(client):
    demo_id, token = _demo_lista(client)
    for cuerpo in ({"tipo": "otro"}, {"tipo": ""}, {}, {"tipo": "whatsapp", "extra": 1}):
        r = client.post(f"/demo/{demo_id}/evento", headers=_h(token), json=cuerpo)
        assert r.status_code == 422


def test_evento_404_uniformes(client, db):
    demo_id, token = _demo_lista(client)
    otro_id, otro_token = _demo_lista(client)
    for path_id, tok in (
        (demo_id, None), (demo_id, "basura"), (demo_id, otro_token),
        ("no-es-uuid", token), (str(uuid.uuid4()), token),
    ):
        headers = _h(tok) if tok is not None else {}
        r = client.post(f"/demo/{path_id}/evento", headers=headers, json={"tipo": "whatsapp"})
        assert r.status_code == 404 and r.json() == {"detail": "Demo no encontrada"}
    assert _demo_de(db, demo_id).clics_whatsapp == 0
    assert _demo_de(db, otro_id).clics_whatsapp == 0


def test_evento_origen_ajeno_404(client, db):
    demo_id, token = _demo_lista(client)
    r = _evento(client, demo_id, token, "whatsapp", Origin="https://evil.example")
    assert r.status_code == 404 and r.json() == {"detail": "Demo no encontrada"}
    assert _evento(client, demo_id, token, "whatsapp", Origin="https://glomacx.com").status_code == 204
    assert _demo_de(db, demo_id).clics_whatsapp == 1


def test_rate_limit_de_eventos(client, db, monkeypatch):
    """#629: por encima del tope, el mismo 204 sin escribir."""
    from app.services import ratelimit

    monkeypatch.setattr(router_demo, "_RATE_EVENTOS", ratelimit.SlidingWindow(3, 2000))
    demo_id, token = _demo_lista(client)
    codigos = [_evento(client, demo_id, token, "whatsapp",
                       **{"x-forwarded-for": "4.4.4.4"}).status_code for _ in range(5)]
    assert codigos == [204] * 5
    assert _demo_de(db, demo_id).clics_whatsapp == 3
    # Otra IP no comparte la ventana.
    _evento(client, demo_id, token, "whatsapp", **{"x-forwarded-for": "5.5.5.5"})
    assert _demo_de(db, demo_id).clics_whatsapp == 4


def test_rate_limit_global_de_eventos(client, db, monkeypatch):
    from app.services import ratelimit

    monkeypatch.setattr(router_demo, "_RATE_EVENTOS", ratelimit.SlidingWindow(30, 2))
    demo_id, token = _demo_lista(client)
    for n in range(4):
        _evento(client, demo_id, token, "whatsapp", **{"x-forwarded-for": f"6.6.6.{n}"})
    assert _demo_de(db, demo_id).clics_whatsapp == 2


def test_defaults_de_la_ventana_de_eventos():
    ventana = router_demo.ratelimit.SlidingWindow(30, 2000)
    assert (router_demo._RATE_EVENTOS._por_ip, router_demo._RATE_EVENTOS._global) == \
        (ventana._por_ip, ventana._global)


def test_evento_del_honeypot_da_404(client):
    r = _iniciar(client, sitio_web="spam")
    falso = r.json()
    resp = client.post(f"/demo/{falso['demo_id']}/evento", headers=_h(falso["token"]),
                       json={"tipo": "whatsapp"})
    assert resp.status_code == 404 and resp.json() == {"detail": "Demo no encontrada"}


# ---------------------------------------------------------------------------
# traspaso_at
# ---------------------------------------------------------------------------

def test_traspaso_at_al_handoff(client, db):
    demo_id, token = _demo_lista(client)
    with patch.object(llm_engine, "_invoke_model", ModeloFalso([
        {"content": [{"type": "text", "text": "¿Para cuántas personas?"}], "stop_reason": "end_turn"},
    ])):
        client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    assert _demo_de(db, demo_id).traspaso_at is None
    escala = _tool("escalar_a_asesor", {"motivo": "reserva"}, texto="Te paso con el equipo 🙌")
    with patch.object(llm_engine, "_invoke_model", ModeloFalso([escala])):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "lo quiero"})
    assert r.json()["handoff"] is True
    primero = _demo_de(db, demo_id).traspaso_at
    assert primero is not None
    with patch.object(llm_engine, "_invoke_model", ModeloFalso([escala])):
        client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "otra vez"})
    assert _demo_de(db, demo_id).traspaso_at == primero


# ---------------------------------------------------------------------------
# /admin/demos
# ---------------------------------------------------------------------------

@pytest.fixture
def admin(Sesion, client, monkeypatch):
    """App con el router admin y la cuenta de Gloma + una cuenta cualquiera.

    Los correos de prueba son de `example.com`, que por defecto es dominio
    interno: aquí los internos son otros, salvo en los tests de internas."""
    monkeypatch.setenv("DEMO_DOMINIOS_INTERNOS", "interno.test")
    # En el CI no hay SECRET_KEY ni ALGORITHM en el entorno: una clave de prueba
    # para firmar y verificar los JWT con el portero real.
    from app import dependencies
    from app.routers import auth as router_auth
    for modulo in (dependencies, router_auth):
        monkeypatch.setattr(modulo, "SECRET_KEY", "clave-solo-para-tests", raising=False)
        monkeypatch.setattr(modulo, "ALGORITHM", "HS256", raising=False)
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_db

    s = Sesion()
    gloma = models.User(nombre="Gloma", tipo_documento="NIT", documento="GLOMA1",
                        correo=GLOMA_EMAIL, hashed_password="x")
    otra = models.User(nombre="Otra", tipo_documento="CC", documento="OTRA1",
                       correo="otra@example.com", hashed_password="x")
    miembro = models.User(nombre="Ventas", tipo_documento="CC", documento="VENTAS1",
                          correo="ventas@example.com", hashed_password="x")
    s.add_all([gloma, otra, miembro])
    s.commit()
    sin_llave = models.User(nombre="Asesor", tipo_documento="CC", documento="ASESOR1",
                            correo="asesor@example.com", hashed_password="x")
    s.add(sin_llave)
    s.commit()
    team = crud.create_team(s, "Gloma", gloma)
    m = crud.add_member_to_team(s, team, miembro, role="agent")
    crud.add_member_to_team(s, team, sin_llave, role="agent")
    s.add(models.TeamPermission(team_member_id=m.id, permission_key="ver_demos", enabled=True))
    s.commit()
    s.close()

    app = client.app
    app.include_router(admin_demos.router)

    def _token(correo):
        return {"Authorization": f"Bearer {create_access_token({'sub': correo})}"}

    return client, _token


def _sembrar(client, n, **over):
    ids = []
    for i in range(n):
        body = dict(correo=f"p{i}.{uuid.uuid4().hex[:6]}@example.com",
                    telefono=f"300 444 {len(ids) + i:04d}", **over)
        r = _iniciar(client, **body)
        assert r.status_code == 202, r.text
        ids.append(r.json()["demo_id"])
    return ids


def test_portero(admin):
    client, token = admin
    assert client.get("/admin/demos").status_code in (401, 403)   # sin sesión
    r = client.get("/admin/demos", headers={"Authorization": "Bearer basura"})
    assert r.status_code == 401
    assert client.get("/admin/demos", headers=token("otra@example.com")).status_code == 403
    assert client.get("/admin/demos", headers=token(GLOMA_EMAIL)).status_code == 200
    assert client.get("/admin/demos", headers=token("ventas@example.com")).status_code == 200
    # Miembro del team de Gloma SIN la llave `ver_demos` (#629): 403.
    assert client.get("/admin/demos", headers=token("asesor@example.com")).status_code == 403
    assert client.get(f"/admin/demos/{uuid.uuid4()}",
                      headers=token("asesor@example.com")).status_code == 403
    r = client.get(f"/admin/demos/{uuid.uuid4()}", headers=token("otra@example.com"))
    assert r.status_code == 403


def test_sin_sesion_es_401(admin):
    client, _ = admin
    r = client.get("/admin/demos")
    assert r.status_code == 401, r.status_code


def test_lista_resumen_y_campos(admin, db):
    client, token = admin
    ids = _sembrar(client, 3)
    hotel = _sembrar(client, 1, tipo_empresa="otro", tipo_otro="Avistamiento de aves",
                     empresa="Alas del Chocó", acepta_promociones=True)[0]
    # Una conversó, una hizo traspaso, dos clics a WhatsApp, una agendó.
    d0, d1, d2 = (_demo_de(db, i) for i in ids)
    d0.turnos = 3
    d1.turnos = 1
    d1.traspaso_at = datetime.utcnow()
    d1.clics_whatsapp = 2
    d2.clics_whatsapp = 1
    d2.aperturas_llamada = 1
    d2.llamada_agendada_at = datetime.utcnow()
    db.commit()

    r = client.get("/admin/demos", headers=token(GLOMA_EMAIL))
    assert r.status_code == 200
    body = r.json()
    assert body["resumen"] == {"demos": 4, "conversaron": 2, "traspaso": 1,
                               "clic_whatsapp": 2, "abrieron_llamada": 1,
                               "agendaron_llamada": 1, "pidieron_hablar": 2,
                               "por_estado": {"modelo": 4, "respaldo": 0,
                                              "generando": 0, "error": 0}}
    assert body["total"] == 4 and len(body["items"]) == 4
    # Orden: la más nueva primero.
    assert body["items"][0]["public_id"] == hotel
    item = body["items"][0]
    assert set(item) == {
        "public_id", "created_at", "nombre", "empresa", "tipo_empresa",
        "tipo_empresa_label", "telefono", "correo", "acepta_promociones", "estado",
        "origen_productos", "turnos", "traspaso_at", "clics_whatsapp",
        "aperturas_llamada", "llamada_agendada_at", "tipo_otro", "interna", "lead_borrado", "bot_eliminado_at",
    }
    assert item["tipo_otro"] == "Avistamiento de aves"
    assert item["interna"] is False and item["lead_borrado"] is False
    assert item["tipo_empresa_label"] == "Otro: Avistamiento de aves"
    assert item["nombre"] == "Ana Prueba Ficticia"
    # Enmascarados en la lista (#629).
    assert item["correo"] == "p0•••@example.com"
    assert item["telefono"] == "+57 300 ••• 0000"
    assert "+573004440000" not in r.text
    assert r.headers["cache-control"] == "no-store"
    assert item["acepta_promociones"] is True
    # Nada sensible del sistema.
    texto = r.text
    for prohibido in ("chat_state", "ip_address", "user_agent", "token", '"id"', "lead_id", "bot_id"):
        assert prohibido not in texto


def test_resumen_cuadra_con_la_lista(admin, db):
    client, token = admin
    _sembrar(client, 5)
    for i, d in enumerate(db.query(models.Demo).all()):
        d.clics_whatsapp = i % 2
        d.turnos = i
    db.commit()
    body = client.get("/admin/demos?page_size=50", headers=token(GLOMA_EMAIL)).json()
    items = body["items"]
    assert body["resumen"]["demos"] == body["total"] == len(items)
    assert body["resumen"]["clic_whatsapp"] == sum(1 for it in items if it["clics_whatsapp"] > 0)
    assert body["resumen"]["conversaron"] == sum(1 for it in items if it["turnos"] > 0)


def test_filtros(admin, db):
    client, token = admin
    hoteles = _sembrar(client, 2)                                  # tipo hotel
    agencia = _sembrar(client, 1, tipo_empresa="agencia_viajes", empresa="Rumbo Caribe")[0]
    vieja = _demo_de(db, hoteles[0])
    vieja.created_at = datetime(2026, 10, 1, 4, 0)    # 30-sep a las 23:00 en Colombia
    db.commit()
    clic = _demo_de(db, hoteles[1])
    clic.aperturas_llamada = 1
    db.commit()
    h = token(GLOMA_EMAIL)

    r = client.get("/admin/demos?tipo=agencia_viajes", headers=h).json()
    assert [i["public_id"] for i in r["items"]] == [agencia]
    assert r["total"] == 1
    assert r["resumen"]["demos"] == 3            # el resumen NO filtra por tipo (PM #627)

    r = client.get("/admin/demos?desde=2026-10-01", headers=h).json()
    assert vieja.public_id.hex not in [uuid.UUID(i["public_id"]).hex for i in r["items"]]
    r = client.get("/admin/demos?desde=2026-09-30&hasta=2026-09-30", headers=h).json()
    assert [i["public_id"] for i in r["items"]] == [hoteles[0]]
    assert r["resumen"]["demos"] == 1

    for etapa, esperado in (("llamada_abierta", [hoteles[1]]), ("pidieron_hablar", [hoteles[1]]),
                            ("whatsapp", []), ("conversaron", []), ("traspaso", []),
                            ("llamada_agendada", [])):
        r = client.get(f"/admin/demos?etapa={etapa}", headers=h).json()
        assert [i["public_id"] for i in r["items"]] == esperado, etapa
        assert r["resumen"]["demos"] == 3        # la etapa no cambia el resumen

    r = client.get("/admin/demos?estado=modelo", headers=h).json()
    assert r["total"] == 3
    assert client.get("/admin/demos?estado=respaldo", headers=h).json()["total"] == 0
    assert client.get("/admin/demos?estado=lista", headers=h).json()["total"] == 3

    r = client.get("/admin/demos?q=rumbo", headers=h).json()
    assert [i["public_id"] for i in r["items"]] == [agencia]
    r = client.get("/admin/demos?q=Ana Prueba", headers=h).json()
    assert r["total"] == 3
    # El correo se busca COMPLETO del lado del servidor aunque la lista lo enmascare.
    correo = db.query(models.Lead).filter(models.Lead.id == _demo_de(db, agencia).lead_id).one().email
    r = client.get(f"/admin/demos?q={correo}", headers=h).json()
    assert [i["public_id"] for i in r["items"]] == [agencia]
    # No se busca por teléfono.
    assert client.get("/admin/demos?q=300444", headers=h).json()["total"] == 0

    for malo in ("tipo=casino", "desde=2026-10-10&hasta=2026-10-01", "desde=ayer", "page=0",
                 "page_size=101", "desde=2025-01-01&hasta=2026-10-01", "desde=2020-01-01",
                 "estado=borrada", "etapa=agendo"):
        assert client.get(f"/admin/demos?{malo}", headers=h).status_code == 422, malo


def test_paginacion(admin):
    client, token = admin
    _sembrar(client, 7)
    h = token(GLOMA_EMAIL)
    assert client.get("/admin/demos", headers=h).json()["page_size"] == 25
    assert client.get("/admin/demos?page_size=100", headers=h).status_code == 200
    p1 = client.get("/admin/demos?page_size=3&page=1", headers=h).json()
    p3 = client.get("/admin/demos?page_size=3&page=3", headers=h).json()
    assert p1["total"] == 7 and len(p1["items"]) == 3 and len(p3["items"]) == 1
    assert p1["page"] == 1 and p1["page_size"] == 3
    todos = [i["public_id"] for p in (1, 2, 3)
             for i in client.get(f"/admin/demos?page_size=3&page={p}", headers=h).json()["items"]]
    assert len(set(todos)) == 7


def test_detalle(admin, db):
    client, token = admin
    demo_id, demo_token = _demo_lista(client)
    with patch.object(llm_engine, "_invoke_model", ModeloFalso([
        {"content": [{"type": "text", "text": "¡Hola! ¿Para cuántos?"}], "stop_reason": "end_turn"},
    ])):
        client.post(f"/demo/{demo_id}/chat", headers=_h(demo_token), json={"message": "hola"})
    r = client.get(f"/admin/demos/{demo_id}", headers=token(GLOMA_EMAIL))
    assert r.status_code == 200
    d = r.json()
    assert d["public_id"] == demo_id and d["turnos"] == 1
    assert len(d["productos"]) == 3
    assert all(p["precio_cop"] > 0 and p["unidad_precio"] and p["ficha"] for p in d["productos"])
    assert set(d["productos"][0]) == {"nombre", "resumen", "ficha", "precio_cop", "unidad_precio"}
    # Consentimiento.
    assert d["acepto_contacto_at"] and d["consent_version"] == router_demo.CONSENT_VERSION == "demo-2026-10b"
    assert d["acepta_promociones_at"] is None
    assert [m["rol"] for m in d["transcripcion"]] == ["usuario", "bot"]
    for prohibido in ("chat_state", "ip_address", "user_agent", "history"):
        assert prohibido not in r.text
    # En el detalle, teléfono y correo completos; y sin caché.
    assert d["telefono"] == "+573000000001" and d["correo"] == "ana.ficticia@example.com"
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("tel,esperado", [
    ("+573001234567", "+57 300 ••• 4567"), ("+14155550100", "+141 ••• 0100"),
    (None, None), ("123", "•••"),
])
def test_enmascarar_telefono(tel, esperado):
    assert admin_demos.enmascarar_telefono(tel) == esperado


@pytest.mark.parametrize("correo,esperado", [
    ("camila.ruiz@dominio.com", "ca•••@dominio.com"), ("a@b.co", "a•••@b.co"), (None, None),
])
def test_enmascarar_correo(correo, esperado):
    assert admin_demos.enmascarar_correo(correo) == esperado


def test_log_de_auditoria_sin_pii(admin, caplog):
    import logging

    client, token = admin
    demo_id = _sembrar(client, 1)[0]
    with caplog.at_level(logging.INFO, logger="app.routers.admin_demos"):
        client.get("/admin/demos?page=1", headers=token(GLOMA_EMAIL))
        client.get(f"/admin/demos/{demo_id}", headers=token(GLOMA_EMAIL))
    mensajes = [r.getMessage() for r in caplog.records if r.name == "app.routers.admin_demos"]
    assert any(m.startswith("admin_demos lista user_id=") and "pagina=1" in m for m in mensajes)
    assert any(m.startswith("admin_demos detalle user_id=") and "demo_id=" in m for m in mensajes)
    for m in mensajes:
        assert "@" not in m and "Ana" not in m and "300" not in m and demo_id not in m


def test_llamada_agendada_documentada_como_del_navegador():
    campo = admin_demos.DemoAdminItemOut.model_fields["llamada_agendada_at"]
    assert "navegador" in (campo.description or "")


def test_detalle_404(admin):
    client, token = admin
    h = token(GLOMA_EMAIL)
    for pid in ("no-es-uuid", str(uuid.uuid4())):
        r = client.get(f"/admin/demos/{pid}", headers=h)
        assert r.status_code == 404 and r.json() == {"detail": "Demo no encontrada"}



# ---------------------------------------------------------------------------
# /admin/demos/access y demos internas
# ---------------------------------------------------------------------------

def test_access(admin):
    client, token = admin
    for correo, esperado in ((GLOMA_EMAIL, True), ("ventas@example.com", True),
                             ("asesor@example.com", False), ("otra@example.com", False)):
        r = client.get("/admin/demos/access", headers=token(correo))
        assert r.status_code == 200 and r.json() == {"allowed": esperado}, correo
        assert r.headers["cache-control"] == "no-store"
    assert client.get("/admin/demos/access").status_code == 401


def test_internas_se_ocultan_por_defecto(admin, db, monkeypatch):
    client, token = admin
    monkeypatch.setenv("DEMO_DOMINIOS_INTERNOS", "example.com, glomacx.com")
    externa = _iniciar(client, correo="laura@cliente.co", telefono="300 555 0001").json()["demo_id"]
    interna = _iniciar(client, correo="qa@Example.com", telefono="300 555 0002").json()["demo_id"]
    h = token(GLOMA_EMAIL)
    r = client.get("/admin/demos", headers=h).json()
    assert [i["public_id"] for i in r["items"]] == [externa]
    assert r["resumen"]["demos"] == 1 and r["total"] == 1
    r = client.get("/admin/demos?incluir_internas=true", headers=h).json()
    assert {i["public_id"] for i in r["items"]} == {externa, interna}
    assert r["resumen"]["demos"] == 2
    marcas = {i["public_id"]: i["interna"] for i in r["items"]}
    assert marcas == {externa: False, interna: True}
    # Un dominio que solo termina parecido no es interno.
    assert admin_demos.es_interna("x@noexample.com") is False
    assert admin_demos.es_interna("x@sub.example.com") is False
    assert admin_demos.es_interna("x@example.com") is True


def test_dominios_internos_por_defecto(monkeypatch):
    monkeypatch.delenv("DEMO_DOMINIOS_INTERNOS", raising=False)
    assert admin_demos.dominios_internos() == ["example.com", "glomacx.com", "glomabeauty.com"]


def test_lead_borrado(admin, db):
    client, token = admin
    demo_id = _sembrar(client, 1)[0]
    demo = _demo_de(db, demo_id)
    demo.lead_id = None
    db.commit()
    r = client.get("/admin/demos", headers=token(GLOMA_EMAIL)).json()
    item = r["items"][0]
    assert item["lead_borrado"] is True and item["nombre"] is None and item["correo"] is None
    assert item["interna"] is False


def test_pidieron_hablar_no_cuenta_doble(admin, db):
    client, token = admin
    a, b = _sembrar(client, 2)
    da = _demo_de(db, a)
    da.clics_whatsapp = 3
    da.aperturas_llamada = 2
    db.commit()
    db_ = _demo_de(db, b)
    db_.clics_whatsapp = 1
    db.commit()
    resumen = client.get("/admin/demos", headers=token(GLOMA_EMAIL)).json()["resumen"]
    assert (resumen["clic_whatsapp"], resumen["abrieron_llamada"], resumen["pidieron_hablar"]) == (2, 1, 2)


def test_por_estado(admin, db, monkeypatch):
    client, token = admin
    ids = _sembrar(client, 3)
    d1, d2 = _demo_de(db, ids[1]), None
    d1.origen_productos = "respaldo"
    db.commit()
    d2 = _demo_de(db, ids[2])
    d2.estado = "error"
    d2.origen_productos = None
    db.commit()
    r = client.get("/admin/demos", headers=token(GLOMA_EMAIL)).json()
    assert r["resumen"]["por_estado"] == {"modelo": 1, "respaldo": 1, "generando": 0, "error": 1}
    assert [i["public_id"] for i in client.get("/admin/demos?estado=error",
            headers=token(GLOMA_EMAIL)).json()["items"]] == [ids[2]]


# ---------------------------------------------------------------------------
# #638: la demo cuyo bot ya se borró por inactividad
# ---------------------------------------------------------------------------

def test_ultima_actividad_al_crear_en_cada_turno_y_en_cada_evento(client, db):
    demo_id, token = _demo_lista(client)
    creada = _demo_de(db, demo_id).ultima_actividad_at
    assert creada is not None
    with patch.object(llm_engine, "_invoke_model", ModeloFalso([])):
        client.post(f"/demo/{demo_id}/chat", headers=_h(token), json={"message": "hola"})
    tras_turno = _demo_de(db, demo_id).ultima_actividad_at
    assert tras_turno >= creada
    db.query(models.Demo).update({models.Demo.ultima_actividad_at: datetime(2020, 1, 1)})
    db.commit()
    assert _evento(client, demo_id, token, "whatsapp").status_code == 204
    assert _demo_de(db, demo_id).ultima_actividad_at > datetime(2020, 1, 2)


def test_demo_con_bot_borrado(admin, db):
    from app.services import limpieza_demos

    client, token = admin
    demo_id, demo_token = _demo_lista(client)
    with patch.object(llm_engine, "_invoke_model", ModeloFalso([])):
        client.post(f"/demo/{demo_id}/chat", headers=_h(demo_token), json={"message": "hola"})
    antes = client.get(f"/admin/demos/{demo_id}", headers=token(GLOMA_EMAIL)).json()
    assert antes["bot_eliminado_at"] is None and antes["uso_resumen"] is None
    leads = db.query(models.Lead).count()

    r = limpieza_demos.limpiar_bots_demo_inactivos(db, ahora=datetime.utcnow() + timedelta(days=3))
    assert len(r.borradas) == 1
    assert db.query(models.Lead).count() == leads

    # El prospecto (con el token aún vigente) ve la demo terminada, no un 500.
    e = client.get(f"/demo/{demo_id}/estado", headers=_h(demo_token))
    assert e.status_code == 200
    assert e.json()["terminada"] is True and e.json()["estado"] == "lista"
    assert [p["nombre"] for p in e.json()["productos"]] == [p["nombre"] for p in antes["productos"]]
    modelo = ModeloFalso([])
    with patch.object(llm_engine, "_invoke_model", modelo):
        c = client.post(f"/demo/{demo_id}/chat", headers=_h(demo_token), json={"message": "sigo"})
    assert c.status_code == 200 and c.json()["finished"] is True
    assert "terminó" in c.json()["actions"][0]["text"] and modelo.llamadas == 0
    assert _evento(client, demo_id, demo_token, "whatsapp").status_code == 204

    # El panel: productos desde la copia, la fecha del borrado y el consumo.
    d = client.get(f"/admin/demos/{demo_id}", headers=token(GLOMA_EMAIL)).json()
    assert d["productos"] == antes["productos"]
    assert d["bot_eliminado_at"] and d["uso_resumen"]["turnos"] == 1
    assert d["uso_resumen"]["decisiones"] >= 1 and d["uso_resumen"]["tokens_in"] > 0
    assert d["transcripcion"] == antes["transcripcion"]
    fila = next(i for i in client.get("/admin/demos", headers=token(GLOMA_EMAIL)).json()["items"]
                if i["public_id"] == demo_id)
    assert fila["bot_eliminado_at"]


def test_turno_con_el_bot_borrado_en_medio_no_llama_al_modelo(client, db, monkeypatch):
    """#642 (B2): si la limpieza borra el bot entre la lectura de la demo y el
    UPDATE del contador, el turno no avanza ni llama al modelo."""
    demo_id, demo_token = _demo_lista(client)
    original = router_demo._turno

    def _borrado_justo_antes(sesion, demo, bot, mensaje):
        sesion.execute(models.Demo.__table__.update()
                       .where(models.Demo.id == demo.id)
                       .values(bot_eliminado_at=datetime.utcnow()))
        sesion.commit()
        return original(sesion, demo, bot, mensaje)
    monkeypatch.setattr(router_demo, "_turno", _borrado_justo_antes)
    modelo = ModeloFalso([])
    with patch.object(llm_engine, "_invoke_model", modelo):
        r = client.post(f"/demo/{demo_id}/chat", headers=_h(demo_token), json={"message": "hola"})
    assert r.status_code == 200 and r.json()["finished"] is True
    assert r.json()["actions"][0]["text"] == router_demo.TEXTO_DEMO_TERMINADA
    assert modelo.llamadas == 0 and _demo_de(db, demo_id).turnos == 0
