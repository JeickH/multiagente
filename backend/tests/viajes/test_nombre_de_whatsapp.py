"""El nombre se pide al reservar, y de entrada sale del perfil de WhatsApp.

Cambio del 25-sep-2026, pedido por el CEO. Sale de una medición, no de un
gusto: en la ventana del 11 al 25 de septiembre, **178 de 366 conversaciones
(49%) murieron sin que la persona contestara una sola vez**, y en 117 de los
abandonos el último mensaje del bot era la pregunta del nombre. La persona
llega de un anuncio de Meta —que le escribe solo "¡Hola! Quiero más
información."— y lo primero que recibe es un trámite.

Tres piezas, y las tres se prueban acá:

  1. **El webhook de Twilio guarda `ProfileName`.** Hasta ahora lo tiraba
     (`contact_name=None`) y por eso sólo el 20% de las conversaciones tenía
     nombre. El de Meta sí lo guardaba: esta era la mitad que faltaba.
  2. **El saludo ya no pregunta el nombre**, ni el documento ni el motor.
  3. **El formulario de reserva sí lo pide**, y el recorte no lo toca.

Los guiones de más abajo son sintéticos pero calcados de las conversaciones
reales de la cuenta: el texto del anuncio palabra por palabra, la persona que
llega preguntando por las salidas entre semana, la que se presenta sola y la
que llega hasta la reserva. Los números de teléfono van inventados (regla #8).
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models
from app.data.bot_viajes import LLM_CONFIG
from app.routers import twilio_webhook
from app.services import llm_engine

from .test_continuidad import (  # noqa: F401 — fixtures de pytest
    _respuesta, _texto, _tool, agencia, db_session, entra_mensaje, modelo,
    salientes,
)

#: El texto exacto con el que el anuncio de Meta abre la conversación. 173 de
#: las 178 que no arrancaron en septiembre empezaron con esto, sin una palabra
#: más.
DEL_ANUNCIO = "¡Hola! Quiero más información."


# ===========================================================================
# 1 · El webhook de Twilio guarda el nombre del perfil
# ===========================================================================
#: Números y correos **inventados** (regla #8: este repo es público y los de los
#: clientes son datos de terceros). El de la marca y el del cliente son
#: distintos a propósito: el webhook resuelve la cuenta por el `To`.
@pytest.fixture
def cuenta_twilio():
    from app.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = models.User(nombre="Agencia", correo="wa@test.com", tipo_documento="CC",
                       documento="WA0001", hashed_password="x")
    db.add(user); db.commit()
    team = models.Team(nombre="Arranquemos Pues", owner_user_id=user.id)
    db.add(team); db.commit()
    db.add(models.MetaAccount(
        team_id=team.id, phone_number_id="573001112233",
        display_phone="+573001112233", is_active=True,
        twilio_from="whatsapp:+573001112233", status="active", provider="twilio",
    ))
    db.commit()
    yield db, team
    db.close(); engine.dispose()


def _entrante(monkeypatch, db, *, perfil=None, sid="SM1", cuerpo="Hola"):
    """Un webhook de entrada de Twilio, con el bot apagado."""
    form = {"MessageSid": sid, "From": "whatsapp:+573009998877",
            "To": "whatsapp:+573001112233", "Body": cuerpo, "NumMedia": "0"}
    if perfil is not None:
        form["ProfileName"] = perfil
    monkeypatch.setattr(twilio_webhook.bot_router_svc,
                        "resolve_bot_for_incoming_message", lambda *a, **k: (None, None))
    twilio_webhook.process_twilio_inbound(db, form)
    return db.query(models.Conversation).order_by(models.Conversation.id.desc()).first()


class TestElPerfilDeWhatsappSeGuarda:
    def test_el_nombre_del_perfil_queda_en_la_conversacion(self, cuenta_twilio, monkeypatch):
        """Lo que hacía falta para no tener que preguntarlo."""
        db, _ = cuenta_twilio
        conv = _entrante(monkeypatch, db, perfil="Marcela")

        assert conv.contact_name == "Marcela"

    def test_sin_perfil_la_conversacion_sigue_sin_nombre(self, cuenta_twilio, monkeypatch):
        """No todos los perfiles traen nombre; eso no puede romper el entrante."""
        db, _ = cuenta_twilio
        conv = _entrante(monkeypatch, db, perfil=None)

        assert conv.contact_name is None

    @pytest.mark.parametrize("basura", ["3001234567", "@juan", "  ", "x", "…"])
    def test_un_perfil_que_no_es_un_nombre_se_descarta(self, cuenta_twilio,
                                                       monkeypatch, basura):
        """Un perfil de WhatsApp es texto libre: llegan teléfonos, arrobas y
        cadenas de un carácter. Se sanea con la misma función que usa el motor,
        porque ese campo termina a la vista del asesor."""
        db, _ = cuenta_twilio
        conv = _entrante(monkeypatch, db, perfil=basura)

        assert conv.contact_name is None

    def test_lo_que_el_saneador_NO_atrapa(self, cuenta_twilio, monkeypatch):
        """Límite conocido, escrito para que no sorprenda: `nombre_saneado`
        filtra dígitos, arrobas y cadenas muy cortas, pero una palabra corriente
        como "sin" o "pendiente" le pasa — y en la base de producción hay varias.

        No se endurece aquí a propósito: `nombre_saneado` la comparten cinco
        bots y una lista negra de palabras se le aplicaría a todos. El costo de
        dejarla pasar es un saludo raro ("¡Hola Sin!"); el de un filtro global
        mal puesto es rechazar nombres reales."""
        db, _ = cuenta_twilio
        conv = _entrante(monkeypatch, db, perfil="sin")

        assert conv.contact_name == "sin"

    def test_lo_que_la_persona_diga_despues_no_se_pisa(self, cuenta_twilio, monkeypatch):
        """`registrar_nombre` manda sobre el perfil: si dijo "soy Andrés", se
        llama Andrés aunque el perfil diga otra cosa."""
        db, _ = cuenta_twilio
        conv = _entrante(monkeypatch, db, perfil="Marcela", sid="SM1")
        conv.contact_name = "Andrés"
        db.commit()
        conv = _entrante(monkeypatch, db, perfil="Marcela", sid="SM2")

        assert conv.contact_name == "Andrés"


# ===========================================================================
# 2 · El saludo ya no pide el nombre (guiones calcados de los reales)
# ===========================================================================
def _dichos(db, conv):
    return [m.content for m in salientes(db, conv)]


class TestElSaludoNoPideElNombre:
    def test_el_caso_que_mas_pesa_el_texto_del_anuncio(self, db_session, agencia, modelo):
        """173 de las 178 que no arrancaron empezaron exactamente así."""
        team, _ = agencia
        modelo.guion = [_respuesta(_texto(
            "¡Hola, buen día! 😊 Soy *Luisa*, asesora de la *Agencia de Viajes "
            "Arranquemos Pues*. Te cuento de nuestro *Plan a Tolú & Coveñas* 🌴.\n\n"
            "¿Para qué mes lo estás pensando? 😊"
        ))]
        conv, _ = entra_mensaje(db_session, team, DEL_ANUNCIO)

        texto = " ".join(_dichos(db_session, conv))
        assert "¿Con quién tengo el gusto?" not in texto
        assert "Para qué mes" in texto

    def test_y_si_el_modelo_la_escribe_igual_no_le_llega_al_cliente(
        self, db_session, agencia, modelo
    ):
        """El documento ya no la trae, pero el modelo la tiene vista de miles
        de turnos. El recorte es determinista por eso mismo."""
        team, _ = agencia
        modelo.guion = [_respuesta(_texto(
            "¡Hola, buen día! 😊 Soy *Luisa* de *Arranquemos Pues* 🌴 "
            "Te cuento del plan.\n\n¿Con quién tengo el gusto? 😊"
        ))]
        conv, _ = entra_mensaje(db_session, team, DEL_ANUNCIO)

        texto = " ".join(_dichos(db_session, conv))
        assert "¿Con quién tengo el gusto?" not in texto
        assert "Te cuento del plan" in texto, "se llevó por delante el mensaje"

    def test_el_de_las_salidas_entre_semana(self, db_session, agencia, modelo):
        """Calcado de la conversación 960: llega del anuncio preguntando por las
        salidas entre semana. Lo que se cuida acá es sólo que no le pida el
        nombre — lo que el bot le conteste del tarifario es otro asunto."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Hola! 😊 Soy *Luisa* 🌴 ¿Para qué mes lo estás pensando?")),
            _respuesta(_texto("Las salidas entre semana están en diciembre y enero 🌴")),
        ]
        conv, _ = entra_mensaje(db_session, team, DEL_ANUNCIO)
        conv, _ = entra_mensaje(
            db_session, team, "Hola pero estaba interesado porque decía que entre semana")

        texto = " ".join(_dichos(db_session, conv))
        assert "tengo el gusto" not in texto.lower()
        assert "cómo te llamas" not in texto.lower()

    def test_si_se_presenta_sola_el_bot_la_saluda_por_su_nombre(
        self, db_session, agencia, modelo
    ):
        """No pedirlo no es ignorarlo: si lo da, se registra y se usa."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Un gusto, Andrés! 🌴 ¿Para qué mes lo estás pensando?"),
                       _tool("registrar_nombre", {"nombre": "Andrés"}), stop="tool_use"),
            _respuesta(_texto("¡Listo, Andrés! 🌴")),
        ]
        conv, _ = entra_mensaje(db_session, team, "Hola, soy Andrés")

        db_session.refresh(conv)
        assert conv.contact_name == "Andrés"
        assert "Andrés" in " ".join(_dichos(db_session, conv))


# ===========================================================================
# 3 · Al reservar sí se pide, y el recorte no lo toca
# ===========================================================================
class TestAlReservarSiSePide:
    FORMULARIO = (
        "¡Qué emoción! 🎉 Para apartar tu cupo necesito en *un solo mensaje*:\n"
        "📝 *Nombre completo*\n📝 *Cédula*\n📝 *Número de personas*\n"
        "📝 *Fecha de viaje*"
    )

    def test_el_formulario_llega_entero(self, db_session, agencia, modelo):
        """**La** excepción, y la razón de que el recorte mire "nombre completo"
        y "cédula": si esto se recortara, la reserva se queda sin datos."""
        team, _ = agencia
        modelo.guion = [
            _respuesta(_texto("¡Hola! 😊 ¿Para qué mes lo estás pensando?")),
            _respuesta(_texto(self.FORMULARIO)),
        ]
        entra_mensaje(db_session, team, DEL_ANUNCIO)
        conv, _ = entra_mensaje(db_session, team, "quiero reservar")

        assert self.FORMULARIO in _dichos(db_session, conv)

    def test_el_documento_dice_que_ese_es_el_unico_momento(self):
        """La regla vive en el .md, que es lo que lee el modelo."""
        from pathlib import Path
        doc = (Path(llm_engine.__file__).resolve().parents[1]
               / "bot_contexts" / "demo_viajes.md").read_text(encoding="utf-8")

        assert "Este es el único momento en que se pide el nombre" in doc
        assert "Ningún mensaje de apertura termina pidiendo el nombre" in doc


class TestLaConfigLoDejaExplicito:
    def test_el_flag_esta_puesto(self):
        assert LLM_CONFIG["nombre_al_reservar"] is True

    def test_la_frase_del_tenant_sigue_definida(self):
        """Se deja para poder volver atrás quitando una sola clave."""
        assert LLM_CONFIG["pregunta_nombre"] == "¿Con quién tengo el gusto? 😊"
