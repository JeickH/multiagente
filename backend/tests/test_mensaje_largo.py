"""La asesora escribe un mensaje que no cabe en WhatsApp.

El caso real: desde `/mensajes` salió un texto de más de 1.600 caracteres,
Twilio lo rechazó con su código 21617 ("The concatenated message body exceeds
the 1600 character limit") y la asesora vio un **502 Bad Gateway**. Un 502 no le
dice a nadie que tiene que partir el mensaje en dos, así que lo volvió a
intentar igual.

El límite es de Twilio y es real: su plataforma corta en 1.600 el `Body` de
cualquier canal (https://www.twilio.com/docs/api/errors/21617). Lo que estaba
mal era la traducción. Acá se protege que:

1. Justo en 1.600 el mensaje sale; con 1.601 lo rechaza. El borde exacto, que
   es donde un `>=` de más rompe un mensaje legítimo.
2. El rechazo es **400**, no 502: el texto ya está escrito y reintentarlo va a
   fallar igual — no es una falla del proveedor.
3. Lo que llega al navegador es una instrucción ("pártelo en dos") con los dos
   números, y **nada** de Twilio: ni el código, ni el status, ni la respuesta
   (regla de seguridad #6).
4. El adaptador mide antes de salir a la red, incluso en sandbox: un texto que
   en demo pasa y en producción rebota es una trampa.
5. El número declarado en el navegador (`frontend/lib/mensajeTexto.ts`) es el
   mismo de acá. Es el test que ata los dos lados: el caso de los videos ya
   enseñó que dos copias sin hilo terminan separándose.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.routers import mensajes
from app.services import messaging
from app.services.messaging import base as messaging_base

CLAVE = "Clave-De-Prueba-1"
# Repo público (regla #8): número inventado, ningún cliente real.
NUMERO_DE_PRUEBA = "573000000002"

MAX = messaging.MAX_TEXTO_WHATSAPP


# ---------------------------------------------------------------------------
# Mundo mínimo
# ---------------------------------------------------------------------------

@pytest.fixture
def db_session():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sesion = Sesion()
    yield sesion
    sesion.close()
    engine.dispose()


@pytest.fixture
def equipo(db_session):
    user = crud.create_user(
        db_session,
        schemas.UserCreate(
            nombre="Agencia", correo="asesora@test.com", tipo_documento="CC",
            documento="LARGO-0001", password=CLAVE,
        ),
    )
    team = crud.create_team(db_session, nombre="Agencia", owner=user)
    db_session.add(models.MetaAccount(
        team_id=team.id,
        provider="twilio",
        display_phone="+57 300 000 0000",
        is_active=True,
        status="active",
    ))
    db_session.commit()
    return crud.get_membership_for_user(db_session, user)


@pytest.fixture
def conversacion(db_session, equipo):
    conv = models.Conversation(
        team_id=equipo.team_id,
        contact_wa_id=NUMERO_DE_PRUEBA,
        contact_name="Clienta de prueba",
        status="open",
        last_message_at=datetime(2026, 9, 16, 9, 0, 0),
    )
    db_session.add(conv)
    db_session.commit()
    return conv


@pytest.fixture
def enviados(monkeypatch):
    """Reemplaza el puerto y anota lo que se le pidió mandar."""
    llamadas = []

    def _fake(account, to_wa_id, body):
        llamadas.append({"to": to_wa_id, "body": body})
        return f"SM-prueba-{len(llamadas)}", {"sandbox": True}

    monkeypatch.setattr(messaging, "send_text", _fake)
    return llamadas


def _enviar(db, equipo, conv, texto):
    return mensajes.send_message_in_conversation(
        conversation_id=conv.id,
        payload=schemas.MessageSendIn(content=texto),
        db=db,
        member=equipo,
    )


# ---------------------------------------------------------------------------
# El borde exacto
# ---------------------------------------------------------------------------

def test_justo_en_el_limite_sale(db_session, equipo, conversacion, enviados):
    """1.600 caracteres clavados es un mensaje válido y se envía."""
    texto = "a" * MAX
    salida = _enviar(db_session, equipo, conversacion, texto)

    assert len(enviados) == 1
    assert len(enviados[0]["body"]) == MAX
    assert salida.status == "sent"


def test_uno_mas_lo_rechaza(db_session, equipo, conversacion, enviados):
    """1.601 no sale, y ni siquiera se molesta al proveedor."""
    with pytest.raises(HTTPException) as err:
        _enviar(db_session, equipo, conversacion, "a" * (MAX + 1))

    assert err.value.status_code == 400
    assert enviados == [], "no se debe llamar al proveedor por algo que ya sabemos que rebota"


def test_el_rechazo_no_deja_un_mensaje_fallido(db_session, equipo, conversacion, enviados):
    """No se intentó enviar nada: el chat no se ensucia con una burbuja roja."""
    with pytest.raises(HTTPException):
        _enviar(db_session, equipo, conversacion, "a" * (MAX + 500))

    guardados = db_session.query(models.Message).filter_by(
        conversation_id=conversacion.id
    ).all()
    assert guardados == []


def test_el_mensaje_dice_que_hacer(db_session, equipo, conversacion, enviados):
    """Los dos números y la instrucción, en el español de la app y tuteando."""
    with pytest.raises(HTTPException) as err:
        _enviar(db_session, equipo, conversacion, "a" * 1742)

    detalle = err.value.detail
    assert "1.742" in detalle and "1.600" in detalle
    assert "Pártelo en dos" in detalle


def test_no_se_filtra_nada_de_twilio(db_session, equipo, conversacion, enviados):
    """Regla #6: el proveedor y su código se quedan del lado del servidor."""
    with pytest.raises(HTTPException) as err:
        _enviar(db_session, equipo, conversacion, "a" * (MAX + 1))

    detalle = err.value.detail.lower()
    for rastro in ("twilio", "21617", "body", "http", "400"):
        assert rastro not in detalle, f"se filtró «{rastro}» al navegador"


# ---------------------------------------------------------------------------
# El adaptador, que es el que conoce el límite
# ---------------------------------------------------------------------------

def test_el_adaptador_mide_antes_de_salir_a_la_red(monkeypatch):
    """Ni en sandbox pasa: lo que falla en producción debe fallar en demo."""
    from app.services.messaging import twilio_adapter

    def _no_deberia_llamarse(*a, **k):  # pragma: no cover
        raise AssertionError("no se debe llamar a la API de Twilio")

    monkeypatch.setattr(twilio_adapter, "_post_message", _no_deberia_llamarse)

    cuenta = models.MetaAccount(provider="twilio")
    # 1.600 pasa por el sandbox sin problema…
    sid, _ = twilio_adapter.send_text(cuenta, NUMERO_DE_PRUEBA, "a" * MAX)
    assert sid.startswith("SM.local-")

    # …y 1.601 levanta el error tipado, sin tocar la red.
    with pytest.raises(messaging.TextoMuyLargoError) as err:
        twilio_adapter.send_text(cuenta, NUMERO_DE_PRUEBA, "a" * (MAX + 1))
    assert err.value.largo == MAX + 1
    assert err.value.retryable is False


def test_si_twilio_rebota_con_21617_igual_se_traduce(db_session, equipo, conversacion, monkeypatch):
    """Red de seguridad: el 21617 que llegue de la API también termina en 400.

    Cubre el texto que crece después del chequeo (una plantilla con variables,
    un caption armado); y acá el mensaje SÍ se persiste como `failed`, porque
    se intentó enviar de verdad.
    """
    def _rebota(account, to_wa_id, body):
        raise messaging.TextoMuyLargoError(len(body), provider="twilio")

    monkeypatch.setattr(messaging, "send_text", _rebota)

    with pytest.raises(HTTPException) as err:
        _enviar(db_session, equipo, conversacion, "hola")

    assert err.value.status_code == 400
    assert "Pártelo en dos" in err.value.detail
    fallidos = db_session.query(models.Message).filter_by(status="failed").all()
    assert len(fallidos) == 1


def test_otros_errores_del_proveedor_siguen_siendo_502(db_session, equipo, conversacion, monkeypatch):
    """El 400 es sólo para el largo; lo demás no cambió de comportamiento."""
    def _rebota(account, to_wa_id, body):
        raise messaging.MessagingError(
            "Twilio rechazó el envío", provider="twilio", status_code=400, provider_code=21211,
        )

    monkeypatch.setattr(messaging, "send_text", _rebota)

    with pytest.raises(HTTPException) as err:
        _enviar(db_session, equipo, conversacion, "hola")

    assert err.value.status_code == 502
    assert "21211" not in err.value.detail


# ---------------------------------------------------------------------------
# El hilo entre los dos lados
# ---------------------------------------------------------------------------

def test_el_frontend_declara_el_mismo_limite():
    """El contador del compositor y esta validación son el mismo número.

    El límite vive en dos archivos a propósito (el navegador tiene que avisar
    sin preguntarle al servidor), y esto es lo que impide que se separen — que
    fue exactamente lo que pasó con el tope de los videos, en `LIMITES` del
    backend y en `REGLAS` del frontend.
    """
    ts = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "mensajeTexto.ts"
    assert ts.exists(), f"falta {ts}: el compositor se quedó sin su copia del límite"

    declarado = re.search(r"MAX_TEXTO_WHATSAPP\s*=\s*(\d+)", ts.read_text(encoding="utf-8"))
    assert declarado, "no se encontró `MAX_TEXTO_WHATSAPP` en mensajeTexto.ts"
    assert int(declarado.group(1)) == MAX, (
        f"el frontend dice {declarado.group(1)} y el backend {MAX}. "
        "Son el mismo límite: cámbialos juntos."
    )


def test_el_texto_del_backend_y_el_del_frontend_dicen_lo_mismo():
    """Palabra por palabra: la asesora no puede leer dos versiones del problema."""
    ts = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "mensajeTexto.ts"
    fuente = ts.read_text(encoding="utf-8")
    for pedazo in ("El mensaje es muy largo para WhatsApp", "Pártelo en dos y vuelve a enviarlo"):
        assert pedazo in fuente, f"el frontend ya no dice «{pedazo}»"
        assert pedazo in messaging_base.mensaje_texto_muy_largo(9999)
