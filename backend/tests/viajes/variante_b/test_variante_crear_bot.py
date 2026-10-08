"""`scripts/crear_bot_viajes_b.py`: crea el bot 2 y le da el 50 % sin romper nada.

Se corre contra SQLite en memoria con `ejecutar(db, ...)`, la misma función que
usa el script por dentro. Lo que se fija:

1. **Simula por defecto**: sin `aplicar` no escribe nada.
2. **Idempotente**: la segunda corrida con `aplicar` no cambia nada y no
   reinicia `reparto_desde` (el conteo del A/B sigue).
3. La config de B es **exactamente** `LLM_CONFIG_B` + la lista blanca de A
   (`fuente_datos`, `model_id`): nada más de A pasa a B, ni credenciales ni
   banderas encendidas a mano (revisión de seguridad S7).
4. Backfill: las conversaciones viejas del team quedan con A, con
   `bot_asignado_at = created_at`; las de otras cuentas no se tocan.
5. Bloqueos: 0 o varios bots A, guion editado en la app sin `FORZAR`, otro
   reparto sin `FORZAR`, minutos de recordatorios distintos.
6. La salida no lleva el correo completo ni valores de `llm_config`.

Teléfonos y correos sintéticos (CLAUDE.md #8).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models
from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import LLM_CONFIG_B, instrucciones_b

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts import crear_bot_viajes_b as script  # noqa: E402

CORREO = "duena_viajes@example.com"
SECRETO = "gAAAA-credencial-cifrada-de-prueba"


@pytest.fixture
def db():
    from app.database import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


def _usuario(db, correo, documento):
    u = models.User(
        nombre="Dueña", tipo_documento="CC", documento=documento,
        correo=correo, hashed_password="x",
    )
    db.add(u)
    db.commit()
    return u


def _cuenta(db, correo=CORREO, documento="VB1"):
    dueño = _usuario(db, correo, documento)
    team = crud.create_team(db, "Agencia de prueba", dueño)
    return SimpleNamespace(dueño=dueño, team=team)


def _bot_a(db, c, *, extra=None, nombre="Plan de prueba (IA)"):
    cfg = dict(LLM_CONFIG)
    cfg.update({"fuente_datos": "productos", "model_id": "modelo-fijado"})
    cfg.update(extra or {})
    a = models.Bot(
        user_id=c.dueño.id, team_id=c.team.id, name=nombre, status="active",
        channels="whatsapp", engine="llm", llm_config=json.dumps(cfg),
        trigger_type=models.BOT_TRIGGER_DEFAULT,
    )
    db.add(a)
    db.commit()
    p = models.BotProducto(
        team_id=c.team.id, slug=f"plan-{a.id}", tipo=models.PRODUCTO_TIPO_PLAN,
        nombre="Plan", estado=models.PRODUCTO_ESTADO_PUBLICADO,
    )
    db.add(p)
    db.commit()
    db.add(models.BotProductoBot(bot_id=a.id, producto_id=p.id, activo=True, orden=1))
    db.add(models.BotRecordatorio(
        team_id=c.team.id, bot_id=a.id, orden=1, minutos=15, texto="¿Seguimos?",
    ))
    db.commit()
    return a


def _conversacion(db, team_id, wa, hace_dias):
    conv = crud.get_or_create_conversation(db, team_id, wa)
    conv.created_at = datetime.utcnow() - timedelta(days=hace_dias)
    db.commit()
    return conv


def _correr(db, **kw):
    lineas = []
    kw.setdefault("correo", CORREO)
    kw.setdefault("aplicar", False)
    codigo = script.ejecutar(db, out=lineas.append, **kw)
    return codigo, "\n".join(lineas)


def _bot_b(db):
    return [
        b for b in db.query(models.Bot).all()
        if json.loads(b.llm_config or "{}").get("variante") == "B"
    ]


class TestSimulacion:
    def test_no_escribe_nada(self, db):
        c = _cuenta(db)
        a = _bot_a(db, c)
        _conversacion(db, c.team.id, "573000000001", 3)
        codigo, salida = _correr(db)
        assert codigo == 0
        assert "Simulación terminada" in salida
        db.expire_all()
        assert _bot_b(db) == []
        assert db.query(models.Bot).count() == 1
        assert db.get(models.Bot, a.id).reparto_pct is None
        assert db.query(models.Conversation).filter(
            models.Conversation.bot_asignado_id.isnot(None)).count() == 0

    def test_sin_correo_no_corre(self, db):
        codigo, salida = _correr(db, correo="")
        assert codigo == 2
        assert "BOT_OWNER_EMAIL" in salida


class TestAplicar:
    def test_crea_b_con_config_exacta_reparto_y_backfill(self, db):
        c = _cuenta(db)
        a = _bot_a(db, c, extra={"shopify": {"encrypted_client_secret": SECRETO},
                                 "bandera_a_mano": True})
        viejas = [_conversacion(db, c.team.id, f"57300000001{i}", 3 + i) for i in range(3)]
        otra = _cuenta(db, "otra_duena@example.com", "VB2")
        ajena = _conversacion(db, otra.team.id, "573000000099", 2)

        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 0, salida
        db.expire_all()

        (b,) = _bot_b(db)
        cfg_b = json.loads(b.llm_config)
        esperado = dict(LLM_CONFIG_B)
        esperado.update({"fuente_datos": "productos", "model_id": "modelo-fijado"})
        assert cfg_b == json.loads(json.dumps(esperado))
        assert "shopify" not in cfg_b and "bandera_a_mano" not in cfg_b

        assert b.instrucciones == instrucciones_b()
        assert b.instrucciones_version == 1
        assert b.team_id == c.team.id and b.user_id == c.dueño.id

        a = db.get(models.Bot, a.id)
        assert (a.reparto_pct, b.reparto_pct) == (50, 50)
        assert a.reparto_desde == b.reparto_desde is not None

        # Mismos productos y recordatorios.
        assert script._productos(db, a.id) == script._productos(db, b.id)
        assert script._recordatorios(db, a.id) == script._recordatorios(db, b.id)

        for v in viejas:
            v = db.get(models.Conversation, v.id)
            assert v.bot_asignado_id == a.id
            assert v.bot_asignado_at == v.created_at
            assert v.bot_asignado_at < a.reparto_desde  # no cuentan en el A/B
        assert db.get(models.Conversation, ajena.id).bot_asignado_id is None

    def test_la_segunda_corrida_no_cambia_nada(self, db):
        c = _cuenta(db)
        _bot_a(db, c)
        _conversacion(db, c.team.id, "573000000021", 2)
        assert _correr(db, aplicar=True)[0] == 0
        db.expire_all()
        (b,) = _bot_b(db)
        antes = (b.llm_config, b.instrucciones, b.instrucciones_version,
                 b.reparto_pct, b.reparto_desde, b.updated_at)

        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 0, salida
        assert "ya está" in salida and "ya iguales" in salida and "ya al día" in salida
        db.expire_all()
        (b2,) = _bot_b(db)
        assert b2.id == b.id
        assert (b2.llm_config, b2.instrucciones, b2.instrucciones_version,
                b2.reparto_pct, b2.reparto_desde, b2.updated_at) == antes

    def test_vuelta_atras_y_vuelta_al_50(self, db):
        c = _cuenta(db)
        a = _bot_a(db, c)
        assert _correr(db, aplicar=True)[0] == 0
        assert _correr(db, aplicar=True, pct_b=0)[0] == 0
        db.expire_all()
        (b,) = _bot_b(db)
        assert db.get(models.Bot, a.id).reparto_pct == 100
        assert b.reparto_pct is None
        # Volver a encenderlo desde el 100/0 no exige FORZAR.
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 0, salida
        db.expire_all()
        assert (db.get(models.Bot, a.id).reparto_pct, db.get(models.Bot, b.id).reparto_pct) == (50, 50)

    def test_la_salida_no_lleva_correo_ni_valores_de_config(self, db):
        c = _cuenta(db)
        _bot_a(db, c, extra={"shopify": {"encrypted_client_secret": SECRETO}})
        _codigo, salida = _correr(db, aplicar=True)
        assert CORREO not in salida
        assert SECRETO not in salida
        assert "modelo-fijado" not in salida
        assert "573" not in salida


class TestBloqueos:
    def test_sin_bot_a(self, db):
        _cuenta(db)
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "exactamente un bot A" in salida

    def test_dos_bots_a(self, db):
        c = _cuenta(db)
        _bot_a(db, c)
        _bot_a(db, c, nombre="Otro igual")
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "exactamente un bot A" in salida
        assert _bot_b(db) == []

    def test_guion_editado_en_la_app_exige_forzar(self, db):
        c = _cuenta(db)
        _bot_a(db, c)
        assert _correr(db, aplicar=True)[0] == 0
        (b,) = _bot_b(db)
        b.instrucciones = "Guion editado desde la app."
        b.instrucciones_version = 2
        db.commit()

        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "FORZAR=1" in salida
        db.expire_all()
        assert db.get(models.Bot, b.id).instrucciones == "Guion editado desde la app."

        codigo, _ = _correr(db, aplicar=True, forzar=True)
        assert codigo == 0
        db.expire_all()
        b = db.get(models.Bot, b.id)
        assert b.instrucciones == instrucciones_b()
        assert b.instrucciones_version == 3

    def test_otro_reparto_exige_forzar(self, db):
        c = _cuenta(db)
        a = _bot_a(db, c)
        assert _correr(db, aplicar=True)[0] == 0
        (b,) = _bot_b(db)
        miembro = db.query(models.TeamMember).filter_by(user_id=c.dueño.id).one()
        crud.guardar_reparto(db, miembro, [(a.id, 70), (b.id, 30)])

        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "otro reparto" in salida
        db.expire_all()
        assert db.get(models.Bot, a.id).reparto_pct == 70

    def test_minutos_distintos_en_a(self, db):
        """A con un reenganche distinto al del archivo: B no puede salir así,
        el A/B mediría el reenganche y no el guion."""
        c = _cuenta(db)
        seg = json.loads(json.dumps(LLM_CONFIG["seguimiento"]))
        seg["recordatorios"][1]["minutos"] = 120
        _bot_a(db, c, extra={"seguimiento": seg})
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "actualizar_bot_viajes.py" in salida
        assert _bot_b(db) == []


class TestPiezas:
    def test_config_b_es_exactamente_la_lista_blanca(self):
        cfg_a = {"fuente_datos": "productos", "model_id": "m", "assignee": "x",
                 "shopify": {"encrypted_client_secret": SECRETO}, "context_key": "demo_viajes"}
        cfg_b = script.config_b(cfg_a)
        assert set(cfg_b) == set(LLM_CONFIG_B) | {"fuente_datos", "model_id"}
        assert cfg_b["context_key"] == "demo_viajes_b"

    def test_lista_blanca(self):
        assert script.LLAVES_DE_A == ("fuente_datos", "model_id")

    def test_enmascarar_correo(self):
        assert script.enmascarar_correo("duena_viajes@example.com") == "du***@***.com"
