"""El actualizador de la config del bot de viajes no puede apagar el piloto.

`scripts/actualizar_bot_viajes.py` reconstruye `llm_config` desde
`app/data/bot_viajes.py` para poder cambiar los caminos y el catálogo de medios
sin borrar el bot (el seed sí lo borra, y con él las sesiones abiertas y la
telemetría).

El problema: conservaba una lista blanca de una sola llave (`model_id`). Todo
lo demás que no viniera del archivo se perdía — y ahí vive `fuente_datos`, el
interruptor que apunta el bot al catálogo de la base. Correrlo contra
producción durante la ventana de observación del piloto lo devolvía al motor
viejo **en silencio**: el script imprimía su resumen de siempre y el bot seguía
contestando, solo que con la otra fuente de datos. Un apagón así no se ve en
ninguna alarma; se ve semanas después, en una medición que no cuadra.

La regla que fija este archivo: el archivo de datos manda sobre lo suyo, y
sobre nada más.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.data.bot_viajes import LLM_CONFIG

# El script vive en `scripts/`, fuera del paquete `app`.
RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts import actualizar_bot_viajes as actualizador  # noqa: E402


class TestFusionar:
    def test_conserva_fuente_datos(self):
        """El defecto concreto: correr esto no puede apagar el piloto."""
        nueva = actualizador.fusionar({"fuente_datos": "productos"})

        assert nueva["fuente_datos"] == "productos"

    def test_conserva_el_model_id_fijado_a_mano(self):
        """Lo que la lista blanca vieja ya cuidaba, que se siga cuidando."""
        nueva = actualizador.fusionar({"model_id": "un-modelo-fijado-a-mano"})

        assert nueva["model_id"] == "un-modelo-fijado-a-mano"

    def test_conserva_una_llave_que_todavia_no_existe(self):
        """La parte que importa a futuro.

        La regla no es «acuérdate de agregar la llave nueva a la lista»: es que
        lo que el archivo de datos no declara, no se toca. El próximo
        interruptor operativo va a estar protegido sin que nadie edite esto —
        que es justo lo que no pasó con `fuente_datos`.
        """
        nueva = actualizador.fusionar({"interruptor_que_no_existe_aun": True})

        assert nueva["interruptor_que_no_existe_aun"] is True

    def test_el_archivo_de_datos_manda_sobre_lo_suyo(self):
        """Para eso se corre: lo que el archivo declara, se pisa."""
        nueva = actualizador.fusionar(
            {"media": {"flyer_viejo": {"url": "https://ejemplo/viejo.jpg"}}}
        )

        assert nueva["media"] == LLM_CONFIG["media"]
        assert "flyer_viejo" not in nueva["media"]

    @pytest.mark.parametrize("clave", sorted(LLM_CONFIG))
    def test_ninguna_llave_del_archivo_sobrevive_a_la_version_vieja(self, clave):
        """Una por una, para que agregar una llave al archivo no abra un hueco."""
        nueva = actualizador.fusionar({clave: "valor viejo que debe desaparecer"})

        assert nueva[clave] == LLM_CONFIG[clave]

    def test_el_assignee_fijo_si_se_borra(self):
        """La única llave que el script borra a propósito: mientras esté puesta
        gana sobre el reparto por turnos y todos los chats caen en la misma
        persona."""
        nueva = actualizador.fusionar({"assignee": "asesor_1"})

        assert "assignee" not in nueva

    def test_con_la_config_vacia_queda_exactamente_el_archivo(self):
        nueva = actualizador.fusionar({})

        assert nueva == dict(LLM_CONFIG)

    def test_no_muta_la_config_anterior_ni_el_archivo(self):
        """`dict(LLM_CONFIG)` es superficial: el archivo es un módulo importado
        una sola vez por proceso y escribirle encima contaminaría a todo el que
        lo lea después, tests incluidos."""
        anterior = {"fuente_datos": "productos"}
        antes_del_archivo = dict(LLM_CONFIG)

        actualizador.fusionar(anterior)

        assert anterior == {"fuente_datos": "productos"}
        assert LLM_CONFIG == antes_del_archivo


# ---------------------------------------------------------------------------
# Solo el bot 1 (la cuenta tiene además el bot 2, variante B)
# ---------------------------------------------------------------------------
#
# Antes el actualizador recorría TODOS los bots LLM del dueño y les pisaba la
# config con la del bot 1. Con el bot 2 en la cuenta, una corrida le borraba el
# guion y las banderas de la variante y el A/B dejaba de comparar nada, sin
# que nadie lo notara. Y traía el correo real del cliente como valor por
# defecto, en un repo público.

import json  # noqa: E402

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import crud, models  # noqa: E402
from app.data.bot_viajes_b import LLM_CONFIG_B  # noqa: E402

CORREO_PRUEBA = "duena_actualizador@example.com"
SECRETO = "gAAAA-credencial-cifrada-de-prueba"


class TestEsBot1:
    def test_el_bot_1(self):
        assert actualizador.es_bot_1({"context_key": "demo_viajes"})

    def test_la_variante_b_no(self):
        assert not actualizador.es_bot_1(LLM_CONFIG_B)

    def test_una_variante_con_el_contexto_del_bot_1_tampoco(self):
        """Durante un instante la variante recién duplicada tiene el contexto
        del bot 1; con `variante` puesta ya no es el bot 1."""
        assert not actualizador.es_bot_1({"context_key": "demo_viajes", "variante": "C"})

    def test_otro_contexto_no(self):
        assert not actualizador.es_bot_1({"context_key": "natulce"})
        assert not actualizador.es_bot_1({})


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


def _dueño(db):
    u = models.User(
        nombre="Dueña", tipo_documento="CC", documento="ACT1",
        correo=CORREO_PRUEBA, hashed_password="x",
    )
    db.add(u)
    db.commit()
    team = crud.create_team(db, "Agencia", u)
    return u, team


def _bot(db, u, team, cfg):
    b = models.Bot(
        user_id=u.id, team_id=team.id, name="bot", status="active",
        channels="whatsapp", engine="llm", llm_config=json.dumps(cfg),
        trigger_type=models.BOT_TRIGGER_DEFAULT,
    )
    db.add(b)
    db.commit()
    return b


class TestMain:
    def test_sin_correo_aborta(self, db, monkeypatch, capsys):
        monkeypatch.delenv("BOT_OWNER_EMAIL", raising=False)
        assert actualizador.main(db=db) == 2
        assert "BOT_OWNER_EMAIL" in capsys.readouterr().out

    def test_no_hay_correo_por_defecto_en_el_script(self):
        texto = Path(actualizador.__file__).read_text(encoding="utf-8")
        assert "@gmail.com" not in texto

    def test_solo_toca_el_bot_1(self, db, capsys):
        u, team = _dueño(db)
        a = _bot(db, u, team, {"context_key": "demo_viajes", "fuente_datos": "productos"})
        b = _bot(db, u, team, {**json.loads(json.dumps(LLM_CONFIG_B)), "fuente_datos": "productos"})
        cfg_b_antes = b.llm_config

        assert actualizador.main(db=db, correo=CORREO_PRUEBA) == 0
        db.expire_all()
        assert db.get(models.Bot, b.id).llm_config == cfg_b_antes
        cfg_a = json.loads(db.get(models.Bot, a.id).llm_config)
        assert cfg_a["media"] == LLM_CONFIG["media"]
        assert cfg_a["fuente_datos"] == "productos"
        assert f"bot {b.id} omitido" in capsys.readouterr().out

    @pytest.mark.parametrize("cuantos", [0, 2])
    def test_sin_exactamente_un_bot_1_no_escribe(self, db, cuantos, capsys):
        u, team = _dueño(db)
        bots = [_bot(db, u, team, {"context_key": "demo_viajes", "media": {}})
                for _ in range(cuantos)]
        _bot(db, u, team, json.loads(json.dumps(LLM_CONFIG_B)))
        antes = {x.id: x.llm_config for x in db.query(models.Bot).all()}

        assert actualizador.main(db=db, correo=CORREO_PRUEBA) == 1
        assert "No se escribió nada" in capsys.readouterr().out
        db.expire_all()
        assert {x.id: x.llm_config for x in db.query(models.Bot).all()} == antes
        assert len(bots) == cuantos

    def test_imprime_nombres_de_llaves_nunca_valores(self, db, capsys):
        """La salida de una corrida contra RDS queda en CloudWatch: un valor
        conservado puede ser una credencial cifrada."""
        u, team = _dueño(db)
        _bot(db, u, team, {
            "context_key": "demo_viajes", "fuente_datos": "productos",
            "shopify": {"encrypted_client_secret": SECRETO}, "assignee": "asesor_x",
        })
        assert actualizador.main(db=db, correo=CORREO_PRUEBA) == 0
        salida = capsys.readouterr().out
        assert "shopify" in salida and "fuente_datos" in salida
        assert SECRETO not in salida
        assert "asesor_x" not in salida
        assert CORREO_PRUEBA not in salida
