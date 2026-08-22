"""Lo que manda el CLIENTE se guarda y se ve en la bandeja.

Hasta ahora el webhook tiraba las `MediaUrl` de Twilio y dejaba solo el
marcador: el asesor veía "[imagen]" y no podía abrir la foto que le acababan de
mandar. El CEO lo reportó con una prueba en vivo — mandó una nota de voz y una
foto desde su celular y no apareció ninguna de las dos.

Lo que se fija acá:
  * el archivo se baja del proveedor y se guarda como nuestro;
  * el **bot** sigue leyendo el marcador (`[imagen]`), no la URL — si le
    llegara la URL en su turno, se pondría a hablar de un enlace;
  * si la descarga falla, el mensaje se guarda igual con su marcador: perder
    una foto es feo, perder el turno del bot es peor;
  * un reintento de Twilio no vuelve a bajar el archivo.
"""
from __future__ import annotations

import io

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models
from app.database import Base
from app.routers import twilio_webhook
from app.services import adjuntos
from app.services.messaging import twilio_adapter


@pytest.fixture
def db_session(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # Storage en disco temporal: sin bucket, `adjuntos` escribe local.
    monkeypatch.setenv("ADJUNTOS_BUCKET", "")
    monkeypatch.setenv("MASCOTAS_BUCKET", "")
    monkeypatch.setenv("ADJUNTOS_MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("ADJUNTOS_PUBLIC_BASE", "https://api.ejemplo.test")
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def cuenta(db_session):
    user = models.User(
        nombre="Dueña", correo="duena@test.com", tipo_documento="CC",
        documento="ENT001", hashed_password="x",
    )
    db_session.add(user)
    db_session.commit()
    team = models.Team(nombre="Agencia", owner_user_id=user.id)
    db_session.add(team)
    db_session.commit()
    cuenta = models.MetaAccount(
        team_id=team.id, phone_number_id="573001112233",
        display_phone="+573001112233", is_active=True,
        # El webhook resuelve la cuenta por `twilio_from`, que es el número de
        # la marca con el que Twilio entrega el mensaje.
        twilio_from="whatsapp:+573001112233",
        status="active", provider="twilio",
    )
    db_session.add(cuenta)
    db_session.commit()
    return cuenta


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), (10, 80, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def _form(sid: str, tipo: str = "image/jpeg", con_media: bool = True) -> dict:
    form = {
        "MessageSid": sid,
        "From": "whatsapp:+573001234567",
        "To": "whatsapp:+573001112233",
        "Body": "",
    }
    if con_media:
        form.update({
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/ME123",
            "MediaContentType0": tipo,
        })
    else:
        form["NumMedia"] = "0"
        form["Body"] = "Hola"
    return form


def _procesar(db, form, monkeypatch, *, descarga=None):
    """Corre el webhook con la descarga del proveedor simulada."""
    llamadas = []

    def _fake(account, url):
        llamadas.append(url)
        return descarga

    monkeypatch.setattr(twilio_adapter, "download_media", _fake)
    monkeypatch.setattr(twilio_webhook.messaging, "download_media", _fake)
    # El bot no es lo que se prueba acá.
    monkeypatch.setattr(
        twilio_webhook.bot_router_svc,
        "resolve_bot_for_incoming_message",
        lambda *a, **k: (None, None),
    )
    twilio_webhook.process_twilio_inbound(db, form)
    return llamadas


def _mensajes(db):
    return db.query(models.Message).order_by(models.Message.id).all()


class TestLaFotoDelClienteSeGuarda:
    def test_la_imagen_queda_con_su_url_y_el_marcador_delante(
        self, db_session, cuenta, monkeypatch
    ):
        _procesar(
            db_session, _form("MM1"), monkeypatch,
            descarga=(_jpeg(), "image/jpeg"),
        )

        msg = _mensajes(db_session)[-1]
        assert msg.direction == "inbound"
        assert msg.message_type == "image"
        marcador, url = msg.content.split("\n")
        # El marcador va primero porque es lo que lee el bot.
        assert marcador == "[imagen]"
        assert url.startswith("https://api.ejemplo.test/mensajes/adjunto/")
        # Y el archivo se puede volver a servir de verdad.
        carpeta, nombre = url.rsplit("/", 2)[-2:]
        guardado = adjuntos.leer(cuenta.team_id, carpeta, nombre)
        assert guardado is not None
        assert guardado[1] == "image/jpeg"

    def test_la_nota_de_voz_tambien(self, db_session, cuenta, monkeypatch):
        ogg = b"OggS" + b"\x00" * 4096
        _procesar(
            db_session, _form("MM2", "audio/ogg"), monkeypatch,
            descarga=(ogg, "audio/ogg"),
        )

        msg = _mensajes(db_session)[-1]
        assert msg.message_type == "audio"
        assert msg.content.startswith("[nota de voz]\n")

    def test_el_bot_recibe_el_marcador_y_no_la_url(
        self, db_session, cuenta, monkeypatch
    ):
        """Si al bot le llega la URL en su turno, se pone a hablar del enlace en
        vez de pedir que le escriban lo que decía el audio."""
        visto = {}

        def _resolver(db, *, team, conversation_id, message_text):
            visto["texto"] = message_text
            return None, None

        monkeypatch.setattr(twilio_adapter, "download_media",
                            lambda a, u: (_jpeg(), "image/jpeg"))
        monkeypatch.setattr(twilio_webhook.messaging, "download_media",
                            lambda a, u: (_jpeg(), "image/jpeg"))
        monkeypatch.setattr(
            twilio_webhook.bot_router_svc,
            "resolve_bot_for_incoming_message",
            _resolver,
        )
        twilio_webhook.process_twilio_inbound(db_session, _form("MM3"))

        assert visto["texto"] == "[imagen]"
        assert "http" not in visto["texto"]

    def test_si_la_descarga_falla_el_mensaje_igual_entra(
        self, db_session, cuenta, monkeypatch
    ):
        """Perder una foto es feo; perder el turno del bot, peor."""
        _procesar(db_session, _form("MM4"), monkeypatch, descarga=None)

        msg = _mensajes(db_session)[-1]
        assert msg.content == "[imagen]"
        assert msg.message_type == "image"

    def test_un_reintento_de_twilio_no_vuelve_a_bajar_el_archivo(
        self, db_session, cuenta, monkeypatch
    ):
        form = _form("MM5")
        _procesar(db_session, form, monkeypatch, descarga=(_jpeg(), "image/jpeg"))
        llamadas = _procesar(
            db_session, form, monkeypatch, descarga=(_jpeg(), "image/jpeg")
        )

        assert llamadas == [], "el dedupe tiene que cortar antes de descargar"
        assert len(_mensajes(db_session)) == 1

    def test_un_mensaje_de_texto_no_toca_el_storage(
        self, db_session, cuenta, monkeypatch
    ):
        llamadas = _procesar(db_session, _form("MM6", con_media=False), monkeypatch)

        assert llamadas == []
        assert _mensajes(db_session)[-1].content == "Hola"

    def test_un_archivo_que_no_aceptamos_se_descarta_sin_romper(
        self, db_session, cuenta, monkeypatch
    ):
        """Lo subió un desconocido desde su celular y lo terminaríamos sirviendo
        desde un endpoint público nuestro: pasa por la misma lista blanca."""
        _procesar(
            db_session, _form("MM7", "application/x-msdownload"), monkeypatch,
            descarga=(b"MZ\x90\x00" + b"\x00" * 2048, "application/x-msdownload"),
        )

        msg = _mensajes(db_session)[-1]
        assert "http" not in msg.content


class TestElNombreQuedaEnLaAgenda:
    def test_se_agenda_con_el_telefono(self, db_session, cuenta):
        contacto = crud.registrar_contacto_desde_bot(
            db_session, cuenta.team_id, "573001234567", "Marcela"
        )
        assert contacto is not None
        assert contacto.phone_e164 == "+573001234567"
        assert contacto.name == "Marcela"
        assert contacto.opt_in_source == "bot"

    def test_no_pisa_el_nombre_que_puso_una_persona(self, db_session, cuenta):
        crud.registrar_contacto_desde_bot(
            db_session, cuenta.team_id, "573001234567", "Marcela Ríos"
        )
        crud.registrar_contacto_desde_bot(
            db_session, cuenta.team_id, "573001234567", "marce"
        )
        contacto = db_session.query(models.Contact).one()
        assert contacto.name == "Marcela Ríos"

    def test_un_identificador_que_no_es_telefono_no_entra(self, db_session, cuenta):
        """En `conversations` hay cosas como `CO.98381…`: el CHECK de la tabla
        las rechaza y el INSERT reventaría dentro del webhook."""
        assert crud.registrar_contacto_desde_bot(
            db_session, cuenta.team_id, "CO.983817744674765", "Quien sea"
        ) is None
        assert db_session.query(models.Contact).count() == 0

    def test_la_bandeja_usa_el_nombre_de_la_agenda(self, db_session, cuenta):
        """La conversación puede no tener nombre y la agenda sí — por una
        importación de la agencia o porque el bot ya lo guardó."""
        crud.registrar_contacto_desde_bot(
            db_session, cuenta.team_id, "573001234567", "Marcela"
        )
        nombres = crud.nombres_de_agenda(
            db_session, cuenta.team_id, ["573001234567", "573009999999"]
        )
        assert nombres == {"573001234567": "Marcela"}

    def test_la_agenda_de_otro_team_no_se_cruza(self, db_session, cuenta):
        otro = models.Team(nombre="Otra", owner_user_id=cuenta.team.owner_user_id)
        db_session.add(otro)
        db_session.commit()
        crud.registrar_contacto_desde_bot(
            db_session, cuenta.team_id, "573001234567", "Marcela"
        )
        assert crud.nombres_de_agenda(db_session, otro.id, ["573001234567"]) == {}
