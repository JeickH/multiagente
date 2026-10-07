"""Varios bots default con distinto guion y reparto por porcentaje (A/B).

Lo que se fija aquí:

1. **La elección es determinista por déficit**, no aleatoria: un 70/30 en diez
   conversaciones da exactamente 7/3, y un empate lo gana el de menor id.
2. **El router** solo cambia el paso 3 (bot default). Sin reparto todo queda
   como antes —el default de menor id, sin escribir nada en la conversación—;
   con reparto la asignación es pegajosa, un bot pausado deja de serlo, y una
   sesión activa o una keyword siguen ganándole al reparto.
3. **Los endpoints**: validaciones del reparto, aislamiento entre cuentas
   (404 idéntico), duplicar copia la configuración y no el historial, la
   variante no recibe tráfico hasta configurar el reparto, y `llm_config` no
   sale en ninguna respuesta (regla #2).

Todo contra SQLite en memoria, como el resto de la suite. Los teléfonos son
sintéticos (regla #8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models
from app.services import bot_router, llm_engine
from app.services.bot_router import elegir_por_reparto

CONFIG_LLM = json.dumps(
    {
        "context_key": "demo_viajes",
        "retomar": {"horas": 24},
        "shopify": {"shop": "x.myshopify.com", "encrypted_client_secret": "gAAAA-cifrado"},
    }
)


# ---------------------------------------------------------------------------
# 1) Función pura
# ---------------------------------------------------------------------------

def _b(id_: int, pct: int):
    return SimpleNamespace(id=id_, reparto_pct=pct)


def _simular(bots, n: int) -> list[int]:
    conteos: dict[int, int] = {}
    elegidos = []
    for _ in range(n):
        b = elegir_por_reparto(bots, conteos)
        conteos[b.id] = conteos.get(b.id, 0) + 1
        elegidos.append(b.id)
    return elegidos


class TestElegirPorReparto:
    def test_50_50_alterna(self):
        assert _simular([_b(1, 50), _b(2, 50)], 6) == [1, 2, 1, 2, 1, 2]

    def test_70_30_en_diez_da_exactamente_7_y_3(self):
        elegidos = _simular([_b(1, 70), _b(2, 30)], 10)
        assert elegidos.count(1) == 7 and elegidos.count(2) == 3

    def test_tres_bots_50_30_20_en_diez(self):
        elegidos = _simular([_b(1, 50), _b(2, 30), _b(3, 20)], 10)
        assert (elegidos.count(1), elegidos.count(2), elegidos.count(3)) == (5, 3, 2)

    def test_en_cualquier_prefijo_nadie_se_aleja_mas_de_una(self):
        """Determinista: después de cada conversación el reparto ya es el justo
        (a una de distancia), no solo al final."""
        bots = [_b(1, 70), _b(2, 30)]
        elegidos = _simular(bots, 30)
        for k in range(1, 31):
            a = elegidos[:k].count(1)
            assert abs(a - 0.7 * k) < 1.0001

    def test_empate_gana_el_menor_id(self):
        assert elegir_por_reparto([_b(9, 50), _b(4, 50)], {}).id == 4
        assert elegir_por_reparto([_b(9, 50), _b(4, 50)], {4: 3, 9: 3}).id == 4

    def test_el_que_va_atrasado_recupera(self):
        assert elegir_por_reparto([_b(1, 50), _b(2, 50)], {1: 5, 2: 1}).id == 2


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

@pytest.fixture
def Sesion():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def db(Sesion):
    s = Sesion()
    yield s
    s.close()


def _usuario(db, nombre, correo, documento):
    u = models.User(
        nombre=nombre, tipo_documento="CC", documento=documento,
        correo=correo, hashed_password="x",
    )
    db.add(u)
    db.commit()
    return u


def _cuenta(db, sufijo: str):
    dueño = _usuario(db, f"Dueña {sufijo}", f"rep_owner_{sufijo}@example.com", f"REP{sufijo}1")
    team = crud.create_team(db, f"Agencia {sufijo}", dueño)
    asesor = _usuario(db, f"Asesor {sufijo}", f"rep_agent_{sufijo}@example.com", f"REP{sufijo}2")
    crud.add_member_to_team(db, team, asesor, role="agent")
    return SimpleNamespace(team=team, dueño=dueño, asesor=asesor)


@pytest.fixture
def cuenta(db):
    return _cuenta(db, "A")


@pytest.fixture
def otra(db):
    return _cuenta(db, "B")


def _bot(
    db, c, nombre, *, trigger="default", status="active", pct=None, desde=None,
    keywords=None, instrucciones=None,
):
    b = models.Bot(
        user_id=c.dueño.id,
        team_id=c.team.id,
        name=nombre,
        status=status,
        channels="whatsapp",
        engine="llm",
        llm_config=CONFIG_LLM,
        instrucciones=instrucciones,
        trigger_type=trigger,
        trigger_config=json.dumps({"keywords": keywords}) if keywords else None,
        reparto_pct=pct,
        reparto_desde=desde,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


_n = iter(range(1, 10_000))


def _entra(db, c, *, wa_id=None, texto="hola"):
    wa_id = wa_id or f"5730000{next(_n):05d}"
    conv = crud.get_or_create_conversation(db, c.team.id, wa_id)
    bot, sesion = bot_router.resolve_bot_for_incoming_message(
        db, team=c.team, conversation_id=conv.id, message_text=texto,
    )
    db.commit()  # lo que harían el webhook / bot_runner a continuación
    db.refresh(conv)
    return conv, bot, sesion


def _cerrar_sesion(db, conv, bot, *, hace):
    s = models.BotSession(
        bot_id=bot.id, conversation_id=conv.id,
        status=models.BOT_SESSION_FINISHED,
        started_at=datetime.utcnow() - hace,
        updated_at=datetime.utcnow() - hace,
        finished_at=datetime.utcnow() - hace,
    )
    db.add(s)
    db.commit()
    return s


# ---------------------------------------------------------------------------
# 2) Router
# ---------------------------------------------------------------------------

class TestRouter:
    def test_sin_reparto_gana_el_default_de_menor_id_y_no_escribe(self, db, cuenta):
        a = _bot(db, cuenta, "Original")
        _bot(db, cuenta, "Variante")
        for _ in range(3):
            conv, bot, sesion = _entra(db, cuenta)
            assert bot.id == a.id and sesion is None
            assert conv.bot_asignado_id is None and conv.bot_asignado_at is None

    def test_50_50_en_cuatro_conversaciones_da_2_y_2(self, db, cuenta):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        a = _bot(db, cuenta, "A", pct=50, desde=ahora)
        b = _bot(db, cuenta, "B", pct=50, desde=ahora)
        ids = [_entra(db, cuenta)[1].id for _ in range(4)]
        assert ids == [a.id, b.id, a.id, b.id]
        convs = db.query(models.Conversation).all()
        assert all(c.bot_asignado_at is not None for c in convs)
        assert sorted(c.bot_asignado_id for c in convs) == sorted([a.id, a.id, b.id, b.id])

    def test_pegajoso_tras_cerrar_sesion_fuera_de_la_ventana(self, db, cuenta):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        a = _bot(db, cuenta, "A", pct=50, desde=ahora)
        b = _bot(db, cuenta, "B", pct=50, desde=ahora)
        _entra(db, cuenta)  # primera conversación → A
        conv, bot, _ = _entra(db, cuenta, wa_id="573000000099")
        assert bot.id == b.id
        # Su sesión se cerró hace 3 días (fuera de `retomar.horas = 24`).
        _cerrar_sesion(db, conv, b, hace=timedelta(days=3))
        # Entran otras dos personas entretanto (A y B): con 2/2 el empate lo
        # ganaría A, así que si vuelve a B es por la asignación pegajosa.
        _entra(db, cuenta)
        _entra(db, cuenta)
        assert elegir_por_reparto([a, b], {a.id: 2, b.id: 2}).id == a.id
        conv2, bot2, sesion2 = _entra(db, cuenta, wa_id="573000000099")
        assert conv2.id == conv.id
        assert bot2.id == b.id and sesion2 is None

    def test_bot_asignado_pausado_se_reasigna(self, db, cuenta):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        a = _bot(db, cuenta, "A", pct=50, desde=ahora)
        b = _bot(db, cuenta, "B", pct=50, desde=ahora)
        c = _bot(db, cuenta, "C", pct=0)
        conv, bot, _ = _entra(db, cuenta)
        assert bot.id == a.id
        a.status = "paused"
        db.commit()
        conv2, bot2, _ = _entra(db, cuenta, wa_id=conv.contact_wa_id)
        assert bot2.id == b.id
        assert conv2.bot_asignado_id == b.id
        assert c.id not in (bot.id, bot2.id)

    def test_bot_asignado_en_cero_por_ciento_se_reasigna(self, db, cuenta):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        a = _bot(db, cuenta, "A", pct=50, desde=ahora)
        b = _bot(db, cuenta, "B", pct=50, desde=ahora)
        conv, _, _ = _entra(db, cuenta)
        assert conv.bot_asignado_id == a.id
        a.reparto_pct, b.reparto_pct = None, 100
        db.commit()
        conv2, bot2, _ = _entra(db, cuenta, wa_id=conv.contact_wa_id)
        assert bot2.id == b.id and conv2.bot_asignado_id == b.id

    def test_nuevo_reparto_reinicia_el_conteo(self, db, cuenta):
        hace_rato = datetime.utcnow() - timedelta(hours=1)
        a = _bot(db, cuenta, "A", pct=100, desde=hace_rato)
        b = _bot(db, cuenta, "B")
        for _ in range(4):
            assert _entra(db, cuenta)[1].id == a.id
        # Se cambia a 50/50: si se contara desde antes, B se llevaría las
        # cuatro siguientes para "ponerse al día".
        ahora = datetime.utcnow()
        a.reparto_pct, a.reparto_desde = 50, ahora
        b.reparto_pct, b.reparto_desde = 50, ahora
        db.commit()
        ids = [_entra(db, cuenta)[1].id for _ in range(4)]
        assert ids == [a.id, b.id, a.id, b.id]

    def test_keyword_le_gana_al_reparto(self, db, cuenta):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        _bot(db, cuenta, "A", pct=50, desde=ahora)
        _bot(db, cuenta, "B", pct=50, desde=ahora)
        kw = _bot(db, cuenta, "Reclamos", trigger="keyword", keywords=["reclamo"])
        conv, bot, _ = _entra(db, cuenta, texto="tengo un RECLAMO")
        assert bot.id == kw.id
        assert conv.bot_asignado_id is None

    def test_sesion_activa_le_gana_al_reparto(self, db, cuenta):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        a = _bot(db, cuenta, "A", pct=50, desde=ahora)
        b = _bot(db, cuenta, "B", pct=50, desde=ahora)
        conv = crud.get_or_create_conversation(db, cuenta.team.id, "573000000022")
        activa = models.BotSession(
            bot_id=b.id, conversation_id=conv.id, status=models.BOT_SESSION_WAITING,
        )
        db.add(activa)
        db.commit()
        _, bot, sesion = _entra(db, cuenta, wa_id="573000000022")
        assert bot.id == b.id and sesion.id == activa.id
        assert a.id != bot.id

    def test_conversacion_con_asesor_humano_no_entra(self, db, cuenta):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        _bot(db, cuenta, "A", pct=50, desde=ahora)
        _bot(db, cuenta, "B", pct=50, desde=ahora)
        conv = crud.get_or_create_conversation(db, cuenta.team.id, "573000000044")
        conv.assigned_to = "Camila"
        db.commit()
        conv, bot, sesion = _entra(db, cuenta, wa_id="573000000044")
        assert (bot, sesion) == (None, None)
        assert conv.bot_asignado_id is None

    def test_el_conteo_no_mezcla_otra_cuenta(self, db, cuenta, otra):
        """Conversaciones de otro team con `bot_asignado_id` de esta cuenta (un
        dato que no debería existir) no mueven el reparto de esta."""
        ahora = datetime.utcnow() - timedelta(minutes=1)
        a = _bot(db, cuenta, "A", pct=50, desde=ahora)
        b = _bot(db, cuenta, "B", pct=50, desde=ahora)
        for i in range(5):
            db.add(models.Conversation(
                team_id=otra.team.id, contact_wa_id=f"57301000000{i}",
                bot_asignado_id=a.id, bot_asignado_at=datetime.utcnow(),
            ))
        db.commit()
        assert _entra(db, cuenta)[1].id == a.id
        assert _entra(db, cuenta)[1].id == b.id

    def test_pegajoso_a_bot_ajeno_se_ignora(self, db, cuenta, otra):
        ahora = datetime.utcnow() - timedelta(minutes=1)
        a = _bot(db, cuenta, "A", pct=50, desde=ahora)
        _bot(db, cuenta, "B", pct=50, desde=ahora)
        ajeno = _bot(db, otra, "Ajeno", pct=100, desde=ahora)
        conv = crud.get_or_create_conversation(db, cuenta.team.id, "573000000066")
        conv.bot_asignado_id = ajeno.id
        conv.bot_asignado_at = datetime.utcnow()
        db.commit()
        conv, bot, _ = _entra(db, cuenta, wa_id="573000000066")
        assert bot.id == a.id
        assert conv.bot_asignado_id == a.id

    def test_compare_and_set_respeta_al_que_gano(self, db, cuenta, monkeypatch):
        """Si otro proceso asignó entre la lectura y el UPDATE, se usa el suyo."""
        ahora = datetime.utcnow() - timedelta(minutes=1)
        _bot(db, cuenta, "A", pct=50, desde=ahora)
        b = _bot(db, cuenta, "B", pct=50, desde=ahora)
        conv = crud.get_or_create_conversation(db, cuenta.team.id, "573000000088")

        original = bot_router._conteos_del_reparto

        def _conteos_y_carrera(db_, **kw):
            # El "otro proceso" asigna B justo después de la lectura.
            db_.query(models.Conversation).filter(
                models.Conversation.id == conv.id
            ).update(
                {"bot_asignado_id": b.id, "bot_asignado_at": datetime.utcnow()},
                synchronize_session=False,
            )
            return original(db_, **kw)

        monkeypatch.setattr(bot_router, "_conteos_del_reparto", _conteos_y_carrera)
        conv, bot, _ = _entra(db, cuenta, wa_id="573000000088")
        assert bot.id == b.id
        assert conv.bot_asignado_id == b.id


# ---------------------------------------------------------------------------
# 3) Endpoints
# ---------------------------------------------------------------------------

def _cliente(Sesion, usuario):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_db
    from app.routers import bots as router_bots

    app = FastAPI()
    app.include_router(router_bots.router)

    def _get_db():
        s = Sesion()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


@pytest.fixture
def dueño(Sesion, cuenta):
    with _cliente(Sesion, cuenta.dueño) as c:
        yield c


@pytest.fixture
def asesor(Sesion, cuenta):
    with _cliente(Sesion, cuenta.asesor) as c:
        yield c


def _sin_llm_config(respuesta):
    texto = respuesta.text
    assert "llm_config" not in texto
    assert "encrypted_client_secret" not in texto
    assert "gAAAA-cifrado" not in texto


class TestPutReparto:
    def test_guarda_y_lista(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        b = _bot(db, cuenta, "B")
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 70}, {"bot_id": b.id, "pct": 30},
        ]})
        assert r.status_code == 200, r.text
        _sin_llm_config(r)
        por_id = {x["id"]: x for x in r.json()}
        assert por_id[a.id]["reparto_pct"] == 70
        assert por_id[b.id]["reparto_pct"] == 30
        assert por_id[a.id]["conversaciones_reparto"] == 0
        db.expire_all()
        assert db.get(models.Bot, a.id).reparto_desde == db.get(models.Bot, b.id).reparto_desde
        assert db.get(models.Bot, a.id).reparto_desde is not None

    def test_el_listado_cuenta_las_conversaciones_desde_el_reparto(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        b = _bot(db, cuenta, "B")
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 50}, {"bot_id": b.id, "pct": 50},
        ]})
        assert r.status_code == 200
        db.expire_all()
        for _ in range(3):
            _entra(db, cuenta)
        lista = {x["id"]: x for x in dueño.get("/bots").json()}
        assert lista[a.id]["conversaciones_reparto"] == 2
        assert lista[b.id]["conversaciones_reparto"] == 1

    def test_suma_distinta_de_100_da_400(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        b = _bot(db, cuenta, "B")
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 50}, {"bot_id": b.id, "pct": 40},
        ]})
        assert r.status_code == 400
        db.expire_all()
        assert db.get(models.Bot, a.id).reparto_pct is None

    def test_ids_repetidos_dan_400(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 50}, {"bot_id": a.id, "pct": 50},
        ]})
        assert r.status_code == 400

    def test_pct_fuera_de_rango_o_no_entero_se_rechaza(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        for pct in (101, -1, 50.5, "100"):
            r = dueño.put("/bots/reparto", json={"reparto": [{"bot_id": a.id, "pct": pct}]})
            assert r.status_code in (400, 422), pct

    def test_campos_extra_y_demasiados_items_se_rechazan(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 100, "user_id": 1},
        ]})
        assert r.status_code == 422
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": i, "pct": 0} for i in range(1, 23)
        ]})
        assert r.status_code == 422

    def test_bot_de_otra_cuenta_e_inexistente_dan_el_mismo_404(self, db, cuenta, otra, dueño):
        a = _bot(db, cuenta, "A")
        ajeno = _bot(db, otra, "Ajeno")
        r1 = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 50}, {"bot_id": ajeno.id, "pct": 50},
        ]})
        r2 = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 50}, {"bot_id": 999_999, "pct": 50},
        ]})
        assert r1.status_code == r2.status_code == 404
        assert r1.json() == r2.json() == {"detail": "Bot no encontrado"}
        db.expire_all()
        assert db.get(models.Bot, ajeno.id).reparto_pct is None

    @pytest.mark.parametrize("cambio", [{"trigger": "keyword"}, {"status": "paused"}])
    def test_bot_keyword_o_pausado_da_400(self, db, cuenta, dueño, cambio):
        a = _bot(db, cuenta, "A")
        x = _bot(db, cuenta, "X", **cambio)
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 50}, {"bot_id": x.id, "pct": 50},
        ]})
        assert r.status_code == 400

    def test_agente_no_owner_da_403(self, db, cuenta, asesor):
        a = _bot(db, cuenta, "A")
        r = asesor.put("/bots/reparto", json={"reparto": [{"bot_id": a.id, "pct": 100}]})
        assert r.status_code == 403

    def test_lista_vacia_limpia_y_vuelve_al_historico(self, db, cuenta, dueño):
        ahora = datetime.utcnow()
        a = _bot(db, cuenta, "A", pct=30, desde=ahora)
        b = _bot(db, cuenta, "B", pct=70, desde=ahora)
        r = dueño.put("/bots/reparto", json={"reparto": []})
        assert r.status_code == 200
        assert all(x["reparto_pct"] is None for x in r.json())
        db.expire_all()
        assert db.get(models.Bot, b.id).reparto_pct is None
        conv, bot, _ = _entra(db, cuenta)
        assert bot.id == a.id and conv.bot_asignado_id is None

    def test_cero_se_guarda_como_null_y_los_no_listados_quedan_fuera(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        b = _bot(db, cuenta, "B")
        c = _bot(db, cuenta, "C", pct=40, desde=datetime.utcnow())
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 100}, {"bot_id": b.id, "pct": 0},
        ]})
        assert r.status_code == 200
        db.expire_all()
        assert db.get(models.Bot, a.id).reparto_pct == 100
        assert db.get(models.Bot, b.id).reparto_pct is None
        assert db.get(models.Bot, c.id).reparto_pct is None


def _producto(db, team_id, slug):
    p = models.BotProducto(
        team_id=team_id, slug=slug, tipo=models.PRODUCTO_TIPO_PLAN,
        nombre=slug.title(), estado=models.PRODUCTO_ESTADO_PUBLICADO,
    )
    db.add(p)
    db.commit()
    return p


class TestDuplicar:
    def _original_completo(self, db, c):
        a = _bot(db, c, "Guion largo", instrucciones="Guion A: saluda y vende.")
        a.triggered_count, a.finished_count, a.completed_steps_count = 40, 12, 99
        db.commit()
        p1 = _producto(db, c.team.id, "san-andres")
        p2 = _producto(db, c.team.id, "cartagena")
        db.add_all([
            models.BotProductoBot(bot_id=a.id, producto_id=p1.id, activo=True, orden=2),
            models.BotProductoBot(bot_id=a.id, producto_id=p2.id, activo=False, orden=1),
        ])
        db.add_all([
            models.BotRecordatorio(team_id=c.team.id, bot_id=a.id, orden=1, minutos=15, texto="¿Seguimos?"),
            models.BotRecordatorio(team_id=c.team.id, bot_id=a.id, orden=2, minutos=60, texto="Última"),
            models.BotRecordatorio(team_id=c.team.id, bot_id=models.REF_TODAS, orden=1, minutos=30, texto="Todos"),
        ])
        # Pasos con un next_step_id no lineal (1 → 3 → 2).
        s1 = models.BotStep(bot_id=a.id, position=1, step_type="message", label="uno", config="{}")
        s2 = models.BotStep(bot_id=a.id, position=2, step_type="message", label="dos", config="{}")
        s3 = models.BotStep(bot_id=a.id, position=3, step_type="message", label="tres", config="{}")
        db.add_all([s1, s2, s3])
        db.flush()
        s1.next_step_id, s3.next_step_id = s3.id, s2.id
        conv = crud.get_or_create_conversation(db, c.team.id, "573000000055")
        db.add(models.BotSession(bot_id=a.id, conversation_id=conv.id, status=models.BOT_SESSION_FINISHED))
        db.commit()
        return a

    def test_copia_configuracion_y_no_historial(self, db, cuenta, dueño):
        a = self._original_completo(db, cuenta)
        r = dueño.post(f"/bots/{a.id}/duplicar", json={})
        assert r.status_code == 201, r.text
        _sin_llm_config(r)
        d = r.json()
        assert d["name"] == "Guion largo (variante)"
        assert d["status"] == "active"
        assert d["reparto_pct"] is None
        assert d["instrucciones"] == "Guion A: saluda y vende."
        assert (d["triggered_count"], d["finished_count"], d["completed_steps_count"]) == (0, 0, 0)

        db.expire_all()
        nuevo = db.get(models.Bot, d["id"])
        assert nuevo.user_id == cuenta.dueño.id and nuevo.team_id == cuenta.team.id
        assert nuevo.llm_config == a.llm_config
        assert nuevo.trigger_type == "default"
        assert nuevo.instrucciones_version == 1
        assert nuevo.reparto_desde is None

        enlaces = {
            e.producto_id: (e.activo, e.orden)
            for e in db.query(models.BotProductoBot).filter_by(bot_id=nuevo.id)
        }
        originales = {
            e.producto_id: (e.activo, e.orden)
            for e in db.query(models.BotProductoBot).filter_by(bot_id=a.id)
        }
        assert enlaces == originales and len(enlaces) == 2

        recs = db.query(models.BotRecordatorio).filter_by(bot_id=nuevo.id).order_by("orden").all()
        assert [(r.orden, r.minutos, r.texto) for r in recs] == [(1, 15, "¿Seguimos?"), (2, 60, "Última")]
        assert db.query(models.BotRecordatorio).filter_by(bot_id=models.REF_TODAS).count() == 1

        pasos = {s.label: s for s in db.query(models.BotStep).filter_by(bot_id=nuevo.id)}
        assert set(pasos) == {"uno", "dos", "tres"}
        assert pasos["uno"].next_step_id == pasos["tres"].id
        assert pasos["tres"].next_step_id == pasos["dos"].id
        assert pasos["dos"].next_step_id is None

        assert db.query(models.BotSession).filter_by(bot_id=nuevo.id).count() == 0

    def test_la_variante_no_recibe_trafico_hasta_configurar_el_reparto(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "Original")
        r = dueño.post(f"/bots/{a.id}/duplicar", json={"name": "Guion corto"})
        assert r.status_code == 201
        variante_id = r.json()["id"]
        assert r.json()["name"] == "Guion corto"
        db.expire_all()
        for _ in range(3):
            assert _entra(db, cuenta)[1].id == a.id
        r = dueño.put("/bots/reparto", json={"reparto": [
            {"bot_id": a.id, "pct": 50}, {"bot_id": variante_id, "pct": 50},
        ]})
        assert r.status_code == 200
        db.expire_all()
        ids = [_entra(db, cuenta)[1].id for _ in range(2)]
        assert ids == [a.id, variante_id]

    def test_las_instrucciones_del_md_pasan_a_la_columna(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "Con .md")  # sin columna → demo_viajes.md
        md = llm_engine.instrucciones_efectivas(a)
        assert md
        r = dueño.post(f"/bots/{a.id}/duplicar")
        assert r.status_code == 201
        db.expire_all()
        assert db.get(models.Bot, r.json()["id"]).instrucciones == md

    def test_nombre_por_defecto_se_recorta_a_120(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "x" * 120)
        r = dueño.post(f"/bots/{a.id}/duplicar")
        assert r.status_code == 201
        assert len(r.json()["name"]) == 120

    def test_nombre_largo_o_campos_extra_se_rechazan(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        # El largo lo corta el schema (422); los caracteres ocultos, crud (400).
        assert dueño.post(f"/bots/{a.id}/duplicar", json={"name": "y" * 121}).status_code == 422
        assert dueño.post(f"/bots/{a.id}/duplicar", json={"name": "B\u202e"}).status_code == 400
        for extra in ({"llm_config": "{}"}, {"user_id": 1}, {"team_id": 1}, {"context_key": "gloma"}):
            assert dueño.post(f"/bots/{a.id}/duplicar", json=extra).status_code == 422

    def test_guion_que_no_cabe_en_el_tope_no_se_duplica(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        a.instrucciones = "x" * (crud.MAX_INSTRUCCIONES + 1)
        db.commit()
        r = dueño.post(f"/bots/{a.id}/duplicar")
        assert r.status_code == 400
        assert "acórtalo" in r.json()["detail"]

    def test_solo_bots_default(self, db, cuenta, dueño):
        kw = _bot(db, cuenta, "Reclamos", trigger="keyword", keywords=["reclamo"])
        assert dueño.post(f"/bots/{kw.id}/duplicar").status_code == 400

    def test_bot_de_otra_cuenta_da_404(self, db, cuenta, otra, dueño):
        ajeno = _bot(db, otra, "Ajeno")
        r = dueño.post(f"/bots/{ajeno.id}/duplicar")
        assert r.status_code == 404
        assert r.json() == {"detail": "Bot no encontrado"}

    def test_bot_del_owner_en_otro_team_da_409(self, db, cuenta, otra, dueño):
        a = _bot(db, cuenta, "A")
        a.team_id = otra.team.id
        db.commit()
        assert dueño.post(f"/bots/{a.id}/duplicar").status_code == 409

    def test_solo_copia_hijos_de_la_misma_cuenta(self, db, cuenta, otra, dueño):
        a = _bot(db, cuenta, "A")
        propio = _producto(db, cuenta.team.id, "propio")
        ajeno = _producto(db, otra.team.id, "ajeno")
        db.add_all([
            models.BotProductoBot(bot_id=a.id, producto_id=propio.id),
            models.BotProductoBot(bot_id=a.id, producto_id=ajeno.id),
            models.BotRecordatorio(team_id=otra.team.id, bot_id=a.id, orden=1, minutos=10, texto="ajeno"),
        ])
        db.commit()
        r = dueño.post(f"/bots/{a.id}/duplicar")
        assert r.status_code == 201
        db.expire_all()
        nuevo_id = r.json()["id"]
        assert [e.producto_id for e in db.query(models.BotProductoBot).filter_by(bot_id=nuevo_id)] == [propio.id]
        assert db.query(models.BotRecordatorio).filter_by(bot_id=nuevo_id).count() == 0

    def test_tope_de_bots_por_cuenta(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        for i in range(crud.MAX_BOTS_POR_CUENTA - 1):
            _bot(db, cuenta, f"Relleno {i}", trigger="manual")
        r = dueño.post(f"/bots/{a.id}/duplicar")
        assert r.status_code == 400
        assert "20" in r.json()["detail"]

    def test_agente_no_owner_da_403(self, db, cuenta, asesor):
        a = _bot(db, cuenta, "A")
        assert asesor.post(f"/bots/{a.id}/duplicar").status_code == 403


class TestDetalleEInstrucciones:
    def test_detalle_expone_instrucciones_solo_al_owner(self, db, cuenta, dueño, asesor):
        a = _bot(db, cuenta, "A", pct=100, desde=datetime.utcnow(), instrucciones="Guion propio")
        r = dueño.get(f"/bots/{a.id}")
        assert r.status_code == 200
        _sin_llm_config(r)
        assert r.json()["instrucciones"] == "Guion propio"
        assert r.json()["reparto_pct"] == 100
        r = asesor.get(f"/bots/{a.id}")
        assert r.status_code == 200
        _sin_llm_config(r)
        assert r.json()["instrucciones"] is None

    def test_el_listado_y_el_export_no_llevan_secretos_ni_guion(self, db, cuenta, dueño):
        _bot(db, cuenta, "A", instrucciones="Guion propio")
        r = dueño.get("/bots")
        _sin_llm_config(r)
        r = dueño.get("/bots/export")
        _sin_llm_config(r)
        assert "Guion propio" not in r.text

    def test_editar_sube_la_version(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        r = dueño.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": "  Nuevo guion\n\tcon tab  "})
        assert r.status_code == 200, r.text
        _sin_llm_config(r)
        assert r.json()["instrucciones"] == "Nuevo guion\n\tcon tab"
        db.expire_all()
        assert db.get(models.Bot, a.id).instrucciones_version == 1
        dueño.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": "Otra"})
        db.expire_all()
        assert db.get(models.Bot, a.id).instrucciones_version == 2
        # Y el motor lo usa desde el turno siguiente.
        assert llm_engine.instrucciones_efectivas(db.get(models.Bot, a.id)) == "Otra"

    @pytest.mark.parametrize(
        "texto", ["", "   ", "x" * (crud.MAX_INSTRUCCIONES + 1), "hola\x00", "hola\x1bmundo", "a\x7f"]
    )
    def test_instrucciones_invalidas_dan_400(self, db, cuenta, dueño, texto):
        a = _bot(db, cuenta, "A")
        r = dueño.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": texto})
        assert r.status_code == 400
        db.expire_all()
        assert db.get(models.Bot, a.id).instrucciones_version == 0

    @pytest.mark.parametrize(
        "md", sorted(p.name for p in (Path(llm_engine.__file__).parent.parent / "bot_contexts").glob("*.md"))
    )
    def test_los_guiones_del_repo_se_guardan_tal_cual(self, db, cuenta, dueño, md):
        """Regresión: el ZWJ de los emojis compuestos (🚣‍♀️ en el guion de
        viajes) caía en el filtro de caracteres ocultos y el guion duplicado no
        se podía volver a guardar."""
        texto = (Path(llm_engine.__file__).parent.parent / "bot_contexts" / md).read_text()
        if len(texto.strip()) > crud.MAX_INSTRUCCIONES:
            pytest.skip("más largo que el tope")
        a = _bot(db, cuenta, "A")
        r = dueño.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": texto})
        assert r.status_code == 200, r.text

    @pytest.mark.parametrize("oculto", ["\u200b", "\u202e", "\u2066", "\ufeff", "\u0085"])
    def test_caracteres_ocultos_dan_400(self, db, cuenta, dueño, oculto):
        a = _bot(db, cuenta, "A")
        r = dueño.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": f"hola{oculto}mundo"})
        assert r.status_code == 400

    def test_tope_exacto_se_acepta(self, db, cuenta, dueño):
        a = _bot(db, cuenta, "A")
        r = dueño.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": "x" * crud.MAX_INSTRUCCIONES})
        assert r.status_code == 200

    def test_el_log_de_auditoria_no_lleva_el_contenido(self, db, cuenta, dueño, caplog):
        a = _bot(db, cuenta, "A")
        with caplog.at_level("INFO"):
            r = dueño.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": "SECRETO-DEL-GUION"})
        assert r.status_code == 200
        assert "SECRETO-DEL-GUION" not in caplog.text
        assert f"bot_id={a.id}" in caplog.text and "version=1" in caplog.text

    def test_agente_no_owner_da_403(self, db, cuenta, asesor):
        a = _bot(db, cuenta, "A")
        r = asesor.put(f"/bots/{a.id}/instrucciones", json={"instrucciones": "x"})
        assert r.status_code == 403

    def test_bot_de_otra_cuenta_da_404(self, db, otra, dueño):
        ajeno = _bot(db, otra, "Ajeno")
        r = dueño.put(f"/bots/{ajeno.id}/instrucciones", json={"instrucciones": "x"})
        assert r.status_code == 404
