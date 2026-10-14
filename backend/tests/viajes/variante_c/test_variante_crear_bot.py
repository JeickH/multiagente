"""`scripts/crear_bot_viajes_variante.py`: crea el bot 3 y deja el reparto 34/33/33.

Contra SQLite en memoria con `ejecutar(db, ...)`. Lo que se fija:

1. Simula por defecto; `aplicar` escribe; la segunda corrida no cambia nada
   ni reinicia `reparto_desde`.
2. La config de C es **exactamente** `LLM_CONFIG_C` + la lista blanca de A.
3. Pasar de 50/50 (A/B) a 34/33/33 no exige `FORZAR`: son bots de viajes.
   Un reparto con un bot ajeno sí.
4. Vuelta atrás `A=50,B=50,C=0`: C sale del reparto, no se borra.
5. Bloqueos: falta B con porcentaje, REPARTO mal escrito, guion editado.
6. El actualizador del bot 1 se sigue saltando B y C.
7. La salida no lleva el correo ni valores de `llm_config`.
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
from app.data.bot_viajes_c import LLM_CONFIG_C, instrucciones_c

RAIZ = Path(__file__).resolve().parents[3]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts import actualizar_bot_viajes as actualizador  # noqa: E402
from scripts import crear_bot_viajes_variante as script  # noqa: E402

CORREO = "duena_variante_c@example.com"
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


def _cuenta(db, correo=CORREO, documento="VC1"):
    u = models.User(nombre="Dueña", tipo_documento="CC", documento=documento,
                    correo=correo, hashed_password="x")
    db.add(u)
    db.commit()
    return SimpleNamespace(dueño=u, team=crud.create_team(db, "Agencia", u))


def _bot(db, c, cfg, nombre="Plan de prueba (IA)", instrucciones=None):
    b = models.Bot(
        user_id=c.dueño.id, team_id=c.team.id, name=nombre, status="active",
        channels="whatsapp", engine="llm", llm_config=json.dumps(cfg),
        trigger_type=models.BOT_TRIGGER_DEFAULT, instrucciones=instrucciones,
    )
    db.add(b)
    db.commit()
    return b


def _a_y_b(db, c, *, extra_a=None, con_b=True, reparto_ab=True):
    cfg_a = {**json.loads(json.dumps(LLM_CONFIG)), "fuente_datos": "productos",
             "model_id": "modelo-fijado", **(extra_a or {})}
    a = _bot(db, c, cfg_a)
    p = models.BotProducto(team_id=c.team.id, slug=f"plan-{a.id}", tipo=models.PRODUCTO_TIPO_PLAN,
                           nombre="Plan", estado=models.PRODUCTO_ESTADO_PUBLICADO)
    db.add(p)
    db.commit()
    db.add(models.BotProductoBot(bot_id=a.id, producto_id=p.id, activo=True, orden=1))
    db.add(models.BotRecordatorio(team_id=c.team.id, bot_id=a.id, orden=1, minutos=15, texto="¿Seguimos?"))
    db.commit()
    b = None
    if con_b:
        cfg_b = {**json.loads(json.dumps(LLM_CONFIG_B)), "fuente_datos": "productos",
                 "model_id": "modelo-fijado"}
        b = _bot(db, c, cfg_b, nombre="Plan · B", instrucciones=instrucciones_b())
        db.add(models.BotProductoBot(bot_id=b.id, producto_id=p.id, activo=True, orden=1))
        db.commit()
        if reparto_ab:
            miembro = db.query(models.TeamMember).filter_by(user_id=c.dueño.id).one()
            crud.guardar_reparto(db, miembro, [(a.id, 50), (b.id, 50)])
    return a, b


def _correr(db, **kw):
    lineas = []
    kw.setdefault("correo", CORREO)
    kw.setdefault("variante", "C")
    kw.setdefault("aplicar", False)
    codigo = script.ejecutar(db, out=lineas.append, **kw)
    return codigo, "\n".join(lineas)


def _de(db, letra):
    return [b for b in db.query(models.Bot).all()
            if json.loads(b.llm_config or "{}").get("variante") == letra]


class TestParsearReparto:
    def test_bien(self):
        assert script.parsear_reparto("A=34, B=33 ,c=33") == {"A": 34, "B": 33, "C": 33}

    @pytest.mark.parametrize("malo", ["A=50,B=40", "B=50,C=50", "A=34,B=33,X=33",
                                      "A=34,A=33,C=33", "A=101", "A=diez,C=90", "A=50,C"])
    def test_mal(self, malo):
        with pytest.raises(ValueError):
            script.parsear_reparto(malo)


class TestSimulacion:
    def test_no_escribe(self, db):
        c = _cuenta(db)
        a, b = _a_y_b(db, c)
        desde = db.get(models.Bot, a.id).reparto_desde
        codigo, salida = _correr(db)
        assert codigo == 0, salida
        assert "Simulación terminada" in salida
        db.expire_all()
        assert _de(db, "C") == []
        assert db.get(models.Bot, a.id).reparto_pct == 50
        assert db.get(models.Bot, a.id).reparto_desde == desde


class TestAplicar:
    def test_crea_c_y_deja_34_33_33(self, db):
        c = _cuenta(db)
        a, b = _a_y_b(db, c, extra_a={"shopify": {"encrypted_client_secret": SECRETO}})
        conv = crud.get_or_create_conversation(db, c.team.id, "573000000701")
        conv.created_at = datetime.utcnow() - timedelta(days=4)
        db.commit()

        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 0, salida
        db.expire_all()
        (bot_c,) = _de(db, "C")
        cfg_c = json.loads(bot_c.llm_config)
        esperado = {**LLM_CONFIG_C, "fuente_datos": "productos", "model_id": "modelo-fijado"}
        assert cfg_c == json.loads(json.dumps(esperado))
        assert "shopify" not in cfg_c
        assert bot_c.instrucciones == instrucciones_c() and bot_c.instrucciones_version == 1
        pcts = {x.id: x.reparto_pct for x in db.query(models.Bot).all()}
        assert (pcts[a.id], pcts[b.id], pcts[bot_c.id]) == (34, 33, 33)
        desdes = {x.reparto_desde for x in db.query(models.Bot).all()}
        assert len(desdes) == 1
        assert script._productos(db, bot_c.id) == script._productos(db, a.id)
        assert script._recordatorios(db, bot_c.id) == script._recordatorios(db, a.id)
        conv = db.get(models.Conversation, conv.id)
        assert conv.bot_asignado_id == a.id and conv.bot_asignado_at == conv.created_at
        # B no se tocó.
        assert json.loads(db.get(models.Bot, b.id).llm_config)["variante"] == "B"

    def test_la_segunda_corrida_no_cambia_nada(self, db):
        c = _cuenta(db)
        _a_y_b(db, c)
        assert _correr(db, aplicar=True)[0] == 0
        db.expire_all()
        foto = [(x.id, x.llm_config, x.instrucciones_version, x.reparto_pct, x.reparto_desde,
                 x.updated_at) for x in db.query(models.Bot).order_by(models.Bot.id)]
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 0, salida
        assert "ya está" in salida and "ya iguales" in salida and "ya al día" in salida
        db.expire_all()
        assert foto == [(x.id, x.llm_config, x.instrucciones_version, x.reparto_pct,
                         x.reparto_desde, x.updated_at)
                        for x in db.query(models.Bot).order_by(models.Bot.id)]

    def test_vuelta_atras_c_en_cero(self, db):
        c = _cuenta(db)
        a, b = _a_y_b(db, c)
        assert _correr(db, aplicar=True)[0] == 0
        codigo, salida = _correr(db, aplicar=True, reparto="A=50,B=50,C=0")
        assert codigo == 0, salida
        db.expire_all()
        (bot_c,) = _de(db, "C")
        assert (db.get(models.Bot, a.id).reparto_pct, db.get(models.Bot, b.id).reparto_pct,
                bot_c.reparto_pct) == (50, 50, None)
        assert bot_c.status == "active"  # no se borra ni se pausa

    def test_la_variante_b_tambien_sirve(self, db):
        c = _cuenta(db)
        a, _ = _a_y_b(db, c, con_b=False)
        codigo, salida = _correr(db, aplicar=True, variante="B")
        assert codigo == 0, salida
        db.expire_all()
        (b,) = _de(db, "B")
        assert (db.get(models.Bot, a.id).reparto_pct, b.reparto_pct) == (50, 50)

    def test_la_salida_no_lleva_correo_ni_valores(self, db):
        c = _cuenta(db)
        _a_y_b(db, c, extra_a={"shopify": {"encrypted_client_secret": SECRETO}})
        _, salida = _correr(db, aplicar=True)
        assert CORREO not in salida and SECRETO not in salida
        assert "modelo-fijado" not in salida and "573" not in salida


class TestBloqueos:
    def test_sin_correo_o_variante(self, db):
        assert _correr(db, correo="")[0] == 2
        assert _correr(db, variante="Z")[0] == 2
        assert _correr(db, reparto="A=50,B=50")[0] == 2   # falta C

    def test_b_con_porcentaje_que_no_existe(self, db):
        c = _cuenta(db)
        _a_y_b(db, c, con_b=False)
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "variante B, que no existe" in salida
        assert _de(db, "C") == []

    def test_bot_ajeno_en_el_reparto_exige_forzar(self, db):
        c = _cuenta(db)
        a, b = _a_y_b(db, c, reparto_ab=False)
        otro = _bot(db, c, {"context_key": "natulce"}, nombre="Otro")
        miembro = db.query(models.TeamMember).filter_by(user_id=c.dueño.id).one()
        crud.guardar_reparto(db, miembro, [(a.id, 50), (otro.id, 50)])
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "no son de viajes" in salida
        codigo, salida = _correr(db, aplicar=True, forzar=True)
        assert codigo == 0, salida
        db.expire_all()
        assert db.get(models.Bot, otro.id).reparto_pct is None

    def test_guion_editado_exige_forzar(self, db):
        c = _cuenta(db)
        _a_y_b(db, c)
        assert _correr(db, aplicar=True)[0] == 0
        (bot_c,) = _de(db, "C")
        bot_c.instrucciones = "Editado desde la app."
        db.commit()
        codigo, salida = _correr(db, aplicar=True)
        assert codigo == 1 and "FORZAR=1" in salida


class TestActualizadorDelBot1:
    def test_se_salta_b_y_c(self, db, capsys):
        c = _cuenta(db)
        a, b = _a_y_b(db, c)
        assert _correr(db, aplicar=True)[0] == 0
        (bot_c,) = _de(db, "C")
        antes = {x.id: x.llm_config for x in (db.get(models.Bot, b.id), bot_c)}
        assert actualizador.main(db=db, correo=CORREO) == 0
        db.expire_all()
        assert {x.id: x.llm_config for x in (db.get(models.Bot, b.id), db.get(models.Bot, bot_c.id))} == antes
        salida = capsys.readouterr().out
        assert f"bot {b.id} omitido" in salida and f"bot {bot_c.id} omitido" in salida
