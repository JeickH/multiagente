"""Horario de silencio, recordatorios del Simulacro y «lo pienso» (CEO, 2026-10-21).

- Ningún recordatorio sale entre las 11 p.m. y las 5 a.m. de Colombia: se corre
  al borde permitido más cercano (10:59 p.m. o 5:00 a.m.), nunca al pasado.
- En una conversación del Simulacro, que ya se paga completo, el recordatorio
  que habla de «anticipo» sale corregido.
- «Lo pienso y te aviso» queda como interesada (tipo `lo_pensara`).
Datos inventados (regla #8).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app import crud, models
from app.services import bot_runner, intencion_compra, silencio, tarifario

from .variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    conversacion,
    crear_agencia,
    db,
)


def utc(local: str) -> datetime:
    """'2026-10-21 23:10' en Colombia → UTC sin marcar."""
    return datetime.fromisoformat(local) + timedelta(hours=5)


@pytest.fixture
def con_silencio(monkeypatch):
    monkeypatch.setattr(silencio, "ACTIVO", True)


@pytest.mark.parametrize("cuando,ahora,esperado", [
    # De día no se toca.
    ("2026-10-21 15:00", "2026-10-21 14:45", "2026-10-21 15:00"),
    ("2026-10-21 22:59", "2026-10-21 22:44", "2026-10-21 22:59"),
    # 11:10 p.m. agendado a las 6 p.m.: lo más cercano es 10:59 p.m. de esa noche.
    ("2026-10-21 23:10", "2026-10-21 18:10", "2026-10-21 22:59"),
    # 3:10 a.m.: lo más cercano es 5:00 a.m.
    ("2026-10-22 03:10", "2026-10-21 22:10", "2026-10-22 05:00"),
    # 1:00 a.m. agendado a las 8 p.m.: 10:59 p.m. queda a 2 h, 5 a.m. a 4 h.
    ("2026-10-22 01:00", "2026-10-21 20:00", "2026-10-21 22:59"),
    # Pero si las 10:59 p.m. ya pasaron, nunca al pasado: 5:00 a.m.
    ("2026-10-21 23:20", "2026-10-21 23:05", "2026-10-22 05:00"),
    ("2026-10-22 00:30", "2026-10-21 23:40", "2026-10-22 05:00"),
])
def test_corre_al_borde_permitido_mas_cercano(con_silencio, cuando, ahora, esperado):
    assert silencio.fuera_del_silencio(utc(cuando), utc(ahora)) == utc(esperado)


def test_apagado_no_mueve_nada():
    assert silencio.fuera_del_silencio(utc("2026-10-22 03:10"), utc("2026-10-21 22:00")) == utc("2026-10-22 03:10")


# ---------------------------------------------------------------------------
# Al agendar y al enviar
# ---------------------------------------------------------------------------

def _sesion_esperando(db, ag, conv):
    s = models.BotSession(bot_id=ag["bot"].id, conversation_id=conv.id,
                          status=models.BOT_SESSION_WAITING, state='{"history": []}')
    db.add(s)
    db.commit()
    return s


def test_al_agendar_no_queda_en_la_madrugada(db, con_silencio, monkeypatch):
    ag = crear_agencia(db, sufijo="SL1")
    conv = conversacion(db, ag["team"])
    s = _sesion_esperando(db, ag, conv)
    reloj = utc("2026-10-21 22:10")
    monkeypatch.setattr(silencio, "ahora", lambda: reloj)
    monkeypatch.setattr(bot_runner, "datetime", type("dt", (), {"utcnow": staticmethod(lambda: reloj)}))
    pa = bot_runner._programar(db, s, models.BOT_PENDING_ACTION_SEGUIMIENTO, 300, etapa=1)
    assert pa.scheduled_at == utc("2026-10-22 05:00")      # 3:10 a.m. → 5:00 a.m.


def test_al_enviar_en_la_madrugada_se_corre_sin_mandar(db, con_silencio, monkeypatch):
    ag = crear_agencia(db, sufijo="SL2")
    conv = conversacion(db, ag["team"])
    s = _sesion_esperando(db, ag, conv)
    pa = models.BotPendingAction(session_id=s.id, scheduled_at=utc("2026-10-22 03:10"),
                                 action_type=models.BOT_PENDING_ACTION_SEGUIMIENTO,
                                 payload='{"etapa": 1}', status=models.BOT_PENDING_STATUS_PENDING)
    db.add(pa)
    db.commit()
    monkeypatch.setattr(silencio, "ahora", lambda: utc("2026-10-22 03:11"))
    enviados = []
    monkeypatch.setattr(bot_runner, "_send_text", lambda *a, **k: enviados.append(a))
    bot_runner.process_pending_action(db, pa)
    db.refresh(pa)
    assert enviados == []
    assert pa.status == models.BOT_PENDING_STATUS_PENDING
    assert pa.scheduled_at == utc("2026-10-22 05:00")


# ---------------------------------------------------------------------------
# Texto del Simulacro
# ---------------------------------------------------------------------------

ANTICIPO = ("¡Hola de nuevo! 👋 Apartas tu cupo con un anticipo y el resto lo pagas antes "
            "del viaje 🙌 ¿Seguimos? 👇\n1️⃣ Sí, quiero reservar ✅\n2️⃣ Tengo una pregunta 🤔")
PAUTA = "¡Hola! Quiero más información del simulacro decembrino"


@pytest.mark.parametrize("primero,hoy,cambia", [
    (PAUTA, date(2026, 10, 21), True),          # sale en 2 días: pago total
    (PAUTA, date(2026, 10, 15), False),         # faltan 8 días: el anticipo vale
    ("Hola, info del plan", date(2026, 10, 21), False),
])
def test_el_recordatorio_del_simulacro_no_habla_de_anticipo(db, monkeypatch, primero, hoy, cambia):
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: hoy)
    ag = crear_agencia(db, sufijo=f"SM{int(cambia)}{hoy.day}{len(primero)}")
    conv = conversacion(db, ag["team"])
    crud.add_message(db, conv, direction="inbound", content=primero, status="received")
    texto = bot_runner._texto_de_promocion(db, conv, ANTICIPO, ultimo=False)
    if cambia:
        assert "anticipo" not in texto.lower() and "Simulacro decembrino" in texto
        assert "1️⃣" in texto
    else:
        assert texto == ANTICIPO


def test_tambien_si_el_bot_le_ofrecio_la_promocion(db, monkeypatch):
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: date(2026, 10, 21))
    ag = crear_agencia(db, sufijo="SM9")
    conv = conversacion(db, ag["team"])
    crud.add_message(db, conv, direction="inbound", content="Hola, info", status="received")
    crud.add_message(db, conv, direction="outbound", content="Te cuento del *Simulacro decembrino* 🎉", status="sent")
    ultimo = bot_runner._texto_de_promocion(db, conv, "Última razón por hoy 🌴 la apartas con el 30% de anticipo", ultimo=True)
    assert ultimo.startswith("Última razón por hoy") and "anticipo" not in ultimo


def test_un_texto_sin_anticipo_no_se_toca(db):
    ag = crear_agencia(db, sufijo="SM8")
    conv = conversacion(db, ag["team"])
    assert bot_runner._texto_de_promocion(db, conv, "¿Te quedó alguna otra pregunta?", ultimo=False) == "¿Te quedó alguna otra pregunta?"


# ---------------------------------------------------------------------------
# «Lo pienso» → interesada
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "Ok te confirmo gracias", "Lo voy a consultar con mi esposo", "Apenas tenga una respuesta te aviso",
    "consulto el bolsillo y pido permiso en la empresa y te escribo",
])
def test_lo_pienso_es_una_senal_de_interes(texto):
    assert "lo_pensara" in intencion_compra.detectar(texto)


def test_un_saludo_no_es_lo_pienso():
    assert "lo_pensara" not in intencion_compra.detectar("Hola, buenas tardes")
