"""Andamiaje compartido de las pruebas de Interesados (estrategia #22).

Base SQLite en memoria, una agencia con su dueño, una asesora (`agent`) y el
bot 2 con `intencion_compra`; un "motor" falso que reemplaza a
`llm_engine.advance` (lo que se prueba aquí es lo que hace `bot_runner` con el
resultado del turno y lo que muestra la API, no lo que redacta el modelo).

Teléfonos sintéticos, nombres y frases inventados: el repositorio es público y
lo que escriben los clientes son datos de terceros (regla #8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.data.bot_viajes import LLM_CONFIG

CLAVE = "Clave-De-Prueba-1"
WA_1 = "573000000201"
WA_2 = "573000000202"
WA_3 = "573000000203"

#: Config del bot 2 para estas pruebas: la del bot 1 + los flags de Interesados.
FLAGS_INTERESADOS = {
    "intencion_compra": {"horas_para_interesado": 6},
    "presentacion_una_vez": True,
}


def config_bot2(**extra: Any) -> Dict[str, Any]:
    cfg = json.loads(json.dumps(LLM_CONFIG))
    cfg.update(FLAGS_INTERESADOS)
    cfg.update(extra)
    return cfg


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
    sesion = Sesion()
    yield sesion
    sesion.close()


def _usuario(db, correo: str, nombre: str, doc: str) -> models.User:
    return crud.create_user(
        db,
        schemas.UserCreate(
            nombre=nombre, correo=correo, tipo_documento="CC",
            documento=doc, password=CLAVE,
        ),
    )


def crear_agencia(
    db,
    *,
    sufijo: str,
    cfg: Optional[Dict[str, Any]] = None,
    permiso_responder: bool = True,
) -> Dict[str, Any]:
    """Dueño + asesora (`agent`) + bot LLM activo, como una cuenta real."""
    duenio = _usuario(db, f"dueno_{sufijo}@test.com", f"Agencia {sufijo}", f"DOC-D-{sufijo}")
    team = models.Team(nombre=f"Agencia {sufijo}", owner_user_id=duenio.id,
                       asesores_rotacion=["Camila", "Julián"])
    db.add(team)
    db.flush()
    m_duenio = models.TeamMember(team_id=team.id, user_id=duenio.id, role="owner")
    db.add(m_duenio)
    db.commit()
    crud.set_member_permissions(db, m_duenio, {k: True for k in models.AVAILABLE_PERMISSIONS})

    asesora = _usuario(db, f"asesora_{sufijo}@test.com", f"Sofía {sufijo}", f"DOC-A-{sufijo}")
    m_asesora = crud.add_member_to_team(
        db, team, asesora, role="agent",
        permissions={**models.ASESOR_DEFAULT_PERMISSIONS,
                     "can_reply_messages": permiso_responder},
    )
    bot = models.Bot(
        user_id=duenio.id, team_id=team.id, name=f"Bot Viajes B {sufijo}",
        engine="llm", status="active", trigger_type=models.BOT_TRIGGER_DEFAULT,
        llm_config=json.dumps(cfg if cfg is not None else config_bot2(), ensure_ascii=False),
    )
    db.add(bot)
    db.commit()
    for obj in (team, m_duenio, m_asesora, bot, duenio, asesora):
        db.refresh(obj)
    return {
        "team": team, "duenio": duenio, "m_duenio": m_duenio,
        "asesora": asesora, "m_asesora": m_asesora, "bot": bot,
    }


def conversacion(db, team, wa_id: str = WA_1, nombre: Optional[str] = "Valentina") -> models.Conversation:
    conv = models.Conversation(
        team_id=team.id, contact_wa_id=wa_id, contact_name=nombre,
        status="open", assigned_to="bot",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def mensaje(db, conv, direccion: str, texto: str, cuando: datetime, **kw) -> models.Message:
    msg = models.Message(
        conversation_id=conv.id, direction=direccion, content=texto,
        message_type=kw.get("tipo", "text"), status=kw.get("status", "sent"),
        sent_by_user_id=kw.get("por"), created_at=cuando,
    )
    db.add(msg)
    db.commit()
    return msg


def sesion_bot(db, bot, conv, inicio: datetime, status=models.BOT_SESSION_WAITING) -> models.BotSession:
    s = models.BotSession(
        bot_id=bot.id, conversation_id=conv.id, status=status,
        started_at=inicio, updated_at=inicio,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def interesado(
    db,
    agencia: Dict[str, Any],
    *,
    wa_id: str = WA_1,
    inicio: datetime,
    ultimo_entrante: Optional[datetime] = None,
    tipos: Optional[List[str]] = None,
    horas: float = 6,
    nombre: Optional[str] = "Valentina",
) -> models.IntencionCompra:
    """Un episodio completo: conversación con el bot, sesión viva, mensajes y
    la fila de intención (como la dejaría `registrar_intencion`)."""
    conv = conversacion(db, agencia["team"], wa_id, nombre)
    mensaje(db, conv, "inbound", "Hola, quiero información del plan", inicio)
    mensaje(db, conv, "outbound", "¡Hola! Soy Luisa…", inicio + timedelta(minutes=1))
    if ultimo_entrante:
        mensaje(db, conv, "inbound", "¿Cuánto es el anticipo para separar?", ultimo_entrante)
    ses = sesion_bot(db, agencia["bot"], conv, inicio)
    fila = models.IntencionCompra(
        team_id=agencia["team"].id, conversation_id=conv.id, session_id=ses.id,
        bot_id=agencia["bot"].id, tipos=tipos or ["anticipo"],
        origen=models.INTENCION_ORIGEN_REGEX,
        fragmento="¿Cuánto es el anticipo para separar?", resumen=None,
        primera_at=ultimo_entrante or inicio, ultima_at=ultimo_entrante or inicio,
        visible_desde=inicio + timedelta(hours=horas),
        estado=models.INTENCION_POR_CONTACTAR,
    )
    db.add(fila)
    db.commit()
    db.refresh(fila)
    return fila


class MotorFalso:
    """Reemplaza `llm_engine.advance`: devuelve turnos guionados y guarda el
    `runtime` que recibió cada uno."""

    def __init__(self) -> None:
        self.runtimes: List[Dict[str, Any]] = []
        self.guion: List[Dict[str, Any]] = []
        self.durante = None   # callback que corre "mientras el modelo piensa"

    def turno(self, texto: str = "Claro que sí 😊", *, intenciones=None,
              finished: bool = False, extra_actions=None) -> None:
        actions = [{"type": "say", "payload": {"text": texto}}]
        actions += list(extra_actions or [])
        self.guion.append({
            "actions": actions,
            "next_state": {"history": [{"role": "assistant", "content": texto}]},
            "finished": finished,
            "telemetry": {
                "camino": "respuesta_libre", "tools": [], "rounds": 1,
                **({"intenciones": intenciones} if intenciones is not None else {}),
            },
        })

    def __call__(self, bot, state, user_input, runtime=None):
        self.runtimes.append(dict(runtime or {}))
        if self.durante:
            self.durante()
        if not self.guion:
            self.turno()
        return self.guion.pop(0)


@pytest.fixture
def motor(monkeypatch) -> MotorFalso:
    from app.services import llm_engine

    falso = MotorFalso()
    monkeypatch.setattr(llm_engine, "advance", falso)
    # Que ningún turno salga a la red.
    monkeypatch.setattr(llm_engine, "record_booking", lambda *a, **k: None)
    return falso


def test_el_andamiaje_arma_una_agencia(db):
    ag = crear_agencia(db, sufijo="X0")
    assert ag["m_asesora"].role == "agent"
    assert crud.member_has_permission(ag["m_asesora"], "can_reply_messages")
