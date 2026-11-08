"""Sprint 36 — el reclamo del que vuelve con sesiones reales de Postgres (diseño 2.1, 2.5).

Dos (o tres) entrantes del mismo cliente que llegan a la vez, cada uno en su
propia conexión: el UPDATE atómico de `reenganche.reclamar` deja ganar a uno
solo, y solo el ganador escribe la nota «🔥 Volvió» y abre la sesión de
regreso. En SQLite no se puede probar (no hay dos conexiones de verdad).

Mismo marcador y mismos esquemas temporales que
`test_sprint36_schema_postgres.py` (ver ahí cómo apuntar al docker compose
local). No toca RDS. Datos inventados (regla #8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app import models
from app.data.bot_viajes import LLM_CONFIG
from app.services import bot_router, reenganche

from .test_sprint36_schema_postgres import _en_paralelo, base, esquema  # noqa: F401

pytestmark = pytest.mark.postgres


@pytest.fixture
def motor(esquema):  # noqa: F811
    return esquema()


def _agencia_con_abandonada(db, sufijo: str, *, humano_hace=None, cerrada=False):
    user = models.User(
        nombre=f"Prueba {sufijo}", tipo_documento="CC", documento=f"S36RG-{sufijo}",
        correo=f"s36rg-{sufijo}@ejemplo.invalid", hashed_password="x",
    )
    db.add(user)
    db.flush()
    team = models.Team(nombre=f"Equipo {sufijo}", owner_user_id=user.id,
                       asesores_rotacion=["Ana", "Luis"])
    db.add(team)
    db.flush()
    bot = models.Bot(
        user_id=user.id, team_id=team.id, name="Bot", engine="llm", status="active",
        trigger_type=models.BOT_TRIGGER_DEFAULT,
        llm_config=json.dumps(LLM_CONFIG, ensure_ascii=False),
    )
    db.add(bot)
    db.flush()
    ahora = datetime.utcnow()
    conv = models.Conversation(
        team_id=team.id, contact_wa_id="573000036999",
        status="closed" if cerrada else "pending", assigned_to="Ana",
        etiqueta="conversación abandonada", abandono_at=ahora - timedelta(days=1),
        abandono_asesor="Ana", reclamos_abandono=0,
        cerrada_por_inactividad_at=(ahora - timedelta(hours=3)) if cerrada else None,
        ultimo_mensaje_humano_at=humano_hace and ahora - humano_hace,
        bot_asignado_id=bot.id, bot_asignado_at=ahora - timedelta(days=2),
    )
    db.add(conv)
    db.flush()
    db.add(models.Message(conversation_id=conv.id, direction="inbound",
                          content="hola, ¿siguen con el plan?", status="received"))
    db.commit()
    return team.id, conv.id


def _notas_volvio(motor, conv_id: int) -> int:
    with motor.connect() as c:
        return c.execute(text(
            "SELECT COUNT(*) FROM messages WHERE conversation_id = :c "
            "AND message_type = 'nota_interna' AND content LIKE :t"
        ), {"c": conv_id, "t": reenganche.TITULO_VOLVIO + "%"}).scalar()


def _reclamar(team_id: int, conv_id: int):
    def trabajo(sesion):
        team = sesion.get(models.Team, team_id)
        conv = sesion.get(models.Conversation, conv_id)
        reclamo = reenganche.reclamar(sesion, team, conv, conv.assigned_to)
        return None if reclamo is None else ("bot" if reclamo.tomo_el_bot else "aviso")
    return trabajo


@pytest.mark.parametrize("n", [2, 3])
def test_entrantes_a_la_vez_reclaman_una_sola_vez(motor, n):
    with sessionmaker(bind=motor)() as db:
        team_id, conv_id = _agencia_con_abandonada(db, f"r{n}")

    resultados = _en_paralelo(motor, n, _reclamar(team_id, conv_id))

    assert resultados.count("bot") == 1, resultados
    assert resultados.count(None) == n - 1, resultados
    with motor.connect() as c:
        fila = c.execute(text(
            "SELECT reclamos_abandono, assigned_to, status, marcador_consumido "
            "FROM conversations WHERE id = :c"), {"c": conv_id}).one()
    assert tuple(fila) == (1, "bot", "open", models.MARCADOR_CONSUMIDO_VOLVIO)


def test_con_humano_reciente_una_sola_nota(motor):
    with sessionmaker(bind=motor)() as db:
        team_id, conv_id = _agencia_con_abandonada(
            db, "h", humano_hace=timedelta(minutes=30), cerrada=True)

    resultados = _en_paralelo(motor, 3, _reclamar(team_id, conv_id))

    assert resultados.count("aviso") == 1 and resultados.count(None) == 2, resultados
    assert _notas_volvio(motor, conv_id) == 1
    with motor.connect() as c:
        fila = c.execute(text(
            "SELECT reclamos_abandono, assigned_to, status FROM conversations WHERE id = :c"
        ), {"c": conv_id}).one()
    # Sigue con la asesora y vuelve a pendientes.
    assert tuple(fila) == (1, "Ana", "pending")


def test_por_el_router_una_nota_y_una_sesion_de_regreso(motor):
    """El camino completo de dos webhooks a la vez: un reclamo, una nota, una
    sesión con la bandera de regreso."""
    with sessionmaker(bind=motor)() as db:
        team_id, conv_id = _agencia_con_abandonada(db, "router")

    def trabajo(sesion):
        team = sesion.get(models.Team, team_id)
        bot, s = bot_router.resolve_bot_for_incoming_message(
            sesion, team=team, conversation_id=conv_id,
            message_text="hola, ¿siguen con el plan?")
        return (bot.id if bot else None, s.id if s else None)

    resultados = _en_paralelo(motor, 2, trabajo)

    assert all(not isinstance(r, Exception) for r in resultados), resultados
    assert _notas_volvio(motor, conv_id) == 1
    with motor.connect() as c:
        estados = [e for (e,) in c.execute(text(
            "SELECT state FROM bot_sessions WHERE conversation_id = :c"), {"c": conv_id})]
        reclamos = c.execute(text(
            "SELECT reclamos_abandono FROM conversations WHERE id = :c"), {"c": conv_id}).scalar()
    assert reclamos == 1
    assert sum(1 for e in estados if e and '"regreso"' in e) == 1
