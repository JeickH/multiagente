"""El chat de la página queda en la bandeja de Gloma (CEO, 2026-10-29).

Todo lo que dice el agente tiene que verse en la app: por WhatsApp ya quedaba
(webhook de Twilio); el chat de la landing era anónimo y no dejaba nada. Ahora
cada visitante es una conversación del team dueño del bot, con un contacto
`web-<hex>` que viaja cifrado en el token de la sesión, y la mensajería se
niega a mandarle un WhatsApp a ese contacto.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())

from app import models  # noqa: E402
from app.database import Base  # noqa: E402
from app.routers import landing  # noqa: E402
from app.services import llm_engine, messaging  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def bot(db):
    duena = models.User(nombre="Gloma", correo="gloma@test.com", tipo_documento="CC",
                        documento="G1", hashed_password="x")
    otra = models.User(nombre="Otra", correo="otra@test.com", tipo_documento="CC",
                       documento="O1", hashed_password="x")
    db.add_all([duena, otra])
    db.commit()
    # Un team ajeno creado antes, para que no gane por id.
    db.add(models.Team(nombre="Otra", owner_user_id=otra.id))
    db.add(models.Team(nombre="Gloma", owner_user_id=duena.id))
    db.commit()
    return SimpleNamespace(id=16, user_id=duena.id, engine="llm", status="active",
                           llm_config=json.dumps({"context_key": "gloma"}))


def _turno(db, bot, session, mensaje, texto_bot):
    landing._hits_by_ip.clear()
    landing._hits_global.clear()
    req = SimpleNamespace(headers={"x-forwarded-for": "1.2.3.4"}, client=None)
    with patch.object(landing, "_gloma_bot", return_value=bot), \
         patch.object(landing.llm_engine, "record_decision"), \
         patch.object(landing.llm_engine, "record_booking"), \
         patch.object(llm_engine, "_invoke_model",
                      return_value={"content": [{"type": "text", "text": texto_bot}], "stop_reason": "end_turn"}):
        return landing.landing_chat(landing.ChatIn(session=session, message=mensaje), req, db=db)


def _team_gloma(db):
    return db.query(models.Team).filter(models.Team.nombre == "Gloma").one()


def test_el_saludo_y_cada_turno_quedan_en_la_bandeja_del_dueno(db, bot):
    out1 = _turno(db, bot, None, None, "¡Hola! Soy Lía")
    out2 = _turno(db, bot, out1.session, "Quiero agendar una llamada", "Te tengo estos horarios")

    convs = db.query(models.Conversation).all()
    assert len(convs) == 1
    conv = convs[0]
    assert conv.team_id == _team_gloma(db).id
    assert messaging.es_chat_web(conv.contact_wa_id)
    assert conv.contact_name.startswith("Chat web")
    msgs = db.query(models.Message).filter_by(conversation_id=conv.id).order_by(models.Message.id).all()
    assert [(m.direction, m.content) for m in msgs] == [
        ("outbound", "¡Hola! Soy Lía"),
        ("inbound", "Quiero agendar una llamada"),
        ("outbound", "Te tengo estos horarios"),
    ]
    assert out2.session


def test_cada_visitante_es_su_propia_conversacion(db, bot):
    _turno(db, bot, None, "hola", "¡Hola!")
    _turno(db, bot, None, "buenas", "¡Hola!")
    contactos = {c.contact_wa_id for c in db.query(models.Conversation).all()}
    assert len(contactos) == 2


def test_un_token_de_antes_sin_contacto_recibe_uno_nuevo(db, bot):
    viejo = landing._dump_session([{"role": "user", "content": "x"}], 1)
    _turno(db, bot, viejo, "sigo aquí", "Claro")
    assert db.query(models.Conversation).count() == 1


def test_el_contacto_no_lo_elige_el_visitante(db, bot):
    # Un token con un "c" raro (no es web-<12 hex>) se ignora.
    raro = landing.encrypt_secret(json.dumps({"h": [], "n": 1, "c": "573001112233"}))
    assert landing._load_session(raro)["contacto"] is None


def test_si_la_base_falla_el_visitante_igual_recibe_respuesta(db, bot):
    with patch.object(landing.crud, "get_or_create_conversation", side_effect=RuntimeError("bd caída")):
        out = _turno(db, bot, None, "hola", "¡Hola!")
    assert out.actions[0].text == "¡Hola!"


@pytest.mark.parametrize("enviar", [
    lambda c: messaging.send_text(c, "web-0123456789ab", "hola"),
    lambda c: messaging.send_media(c, "web-0123456789ab", "https://x.test/a.jpg"),
    lambda c: messaging.send_template(c, "web-0123456789ab", "plantilla"),
])
def test_nunca_sale_un_whatsapp_hacia_un_contacto_web(enviar):
    cuenta = SimpleNamespace(provider="twilio")
    with patch("app.services.messaging.twilio_adapter.send_text") as t, \
         patch("app.services.messaging.twilio_adapter.send_media") as m, \
         patch("app.services.messaging.twilio_adapter.send_template") as p:
        with pytest.raises(messaging.MessagingError):
            enviar(cuenta)
    assert not (t.called or m.called or p.called)
