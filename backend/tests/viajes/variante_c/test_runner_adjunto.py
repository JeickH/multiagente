"""Bot 3: `runtime["adjunto"]` para que el comprobante con pie no se pierda.

Por Twilio una foto CON pie («te mando el comprobante») entra al motor como el
texto del pie, sin el marcador `[imagen]`. Con `comprobante_a_asesor`, el
runner mira el entrante que guardó el webhook y le avisa al motor que hubo
adjunto; en etapa `pago` eso es traspaso por comprobante ANTES del modelo.

Se prueba de punta a punta por `twilio_webhook.process_twilio_inbound` (lo que
de verdad corre en producción), con la descarga del adjunto y el envío por
Twilio simulados y el modelo reemplazado por uno que no debe llamarse.

Y lo que no puede cambiar: sin el flag, el runtime de los bots 1 y 2 es el de
siempre. Números sintéticos, textos inventados (regla #8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app import models
from app.data.bot_viajes import LLM_CONFIG
from app.routers import twilio_webhook
from app.services import bot_runner, llm_engine
from app.services.messaging import twilio_adapter

from ..variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    crear_agencia,
    db,
)

WA_CLIENTE = "573000000701"
WA_MARCA = "573000000799"

#: Las llaves del runtime de los bots 1 y 2 sin flags del bot 3.
LLAVES_BOT1 = {"bot_id", "source", "conversation_id", "contact_name", "retomada", "desde"}


def cfg_bot3(**extra):
    cfg = json.loads(json.dumps(LLM_CONFIG))
    cfg["comprobante_a_asesor"] = {"texto": "¡Gracias! 🙌 Recibimos tu comprobante. Te confirmamos {cuando} ✨",
                                   "motivo": "comprobante de pago"}
    cfg.update(extra)
    return cfg


@pytest.fixture
def entorno(db, monkeypatch, tmp_path):
    monkeypatch.setenv("ADJUNTOS_BUCKET", "")
    monkeypatch.setenv("MASCOTAS_BUCKET", "")
    monkeypatch.setenv("ADJUNTOS_MEDIA_DIR", str(tmp_path))
    monkeypatch.setenv("ADJUNTOS_PUBLIC_BASE", "https://api.ejemplo.test")
    # Ni descarga real del adjunto ni envío real por Twilio.
    monkeypatch.setattr(twilio_adapter, "download_media", lambda *a, **k: None)
    monkeypatch.setattr(twilio_webhook.messaging, "download_media", lambda *a, **k: None)
    enviados = []

    def _enviar(account, to, text):
        enviados.append(text)
        return f"SM{len(enviados)}", {}

    monkeypatch.setattr(bot_runner.messaging, "send_text", _enviar)
    llamadas_modelo = []
    monkeypatch.setattr(
        llm_engine, "_invoke_model",
        lambda *a, **k: llamadas_modelo.append(1) or {
            "content": [{"type": "text", "text": "respuesta del modelo"}],
            "stop_reason": "end_turn", "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    )
    runtimes = []
    real_advance = llm_engine.advance

    def _advance(bot, state, user_input, runtime=None):
        runtimes.append(dict(runtime or {}))
        return real_advance(bot, state, user_input, runtime=runtime)

    monkeypatch.setattr(llm_engine, "advance", _advance)
    return {"enviados": enviados, "modelo": llamadas_modelo, "runtimes": runtimes}


def _montar(db, *, cfg, sufijo, etapa="pago"):
    ag = crear_agencia(db, sufijo=sufijo, cfg=cfg)
    cuenta = models.MetaAccount(
        team_id=ag["team"].id, phone_number_id=WA_MARCA + sufijo[-1],
        display_phone="+" + WA_MARCA, is_active=True,
        twilio_from=f"whatsapp:+{WA_MARCA}", status="active", provider="twilio",
    )
    db.add(cuenta)
    conv = models.Conversation(team_id=ag["team"].id, contact_wa_id=WA_CLIENTE,
                               contact_name="Valentina", status="open", assigned_to="bot",
                               bot_asignado_id=ag["bot"].id, bot_asignado_at=datetime.utcnow())
    db.add(conv)
    db.commit()
    hace_rato = datetime.utcnow() - timedelta(minutes=10)
    estado = {"history": [
        {"role": "user", "content": "Ana Pérez, 2 adultos, salida del 16"},
        {"role": "assistant", "content": "¡Listo! Te paso los medios de pago 💳"},
    ], "etapa": etapa}
    s = models.BotSession(bot_id=ag["bot"].id, conversation_id=conv.id,
                          status=models.BOT_SESSION_WAITING, state=json.dumps(estado),
                          started_at=hace_rato, updated_at=hace_rato)
    db.add(s)
    db.commit()
    return ag, conv, s


def _foto(sid: str, pie: str = "", tipo: str = "image/jpeg") -> dict:
    return {
        "MessageSid": sid, "From": f"whatsapp:+{WA_CLIENTE}",
        "To": f"whatsapp:+{WA_MARCA}", "Body": pie,
        "NumMedia": "1", "MediaUrl0": "https://api.twilio.com/media/ME1",
        "MediaContentType0": tipo,
    }


class TestComprobanteConPie:
    def test_foto_con_pie_en_etapa_pago_es_traspaso_por_comprobante(self, db, entorno):
        ag, conv, s = _montar(db, cfg=cfg_bot3(), sufijo="AD1")
        twilio_webhook.process_twilio_inbound(db, _foto("MMa1", "te mando el comprobante"))

        assert entorno["runtimes"][-1]["adjunto"] == "imagen"
        assert entorno["modelo"] == []                    # traspaso ANTES del modelo
        db.expire_all()
        conv = db.query(models.Conversation).get(conv.id)
        assert conv.assigned_to in ("Camila", "Julián") and conv.status == "pending"
        assert any("Recibimos tu comprobante" in t for t in entorno["enviados"])
        nota = db.query(models.Message).filter(
            models.Message.conversation_id == conv.id,
            models.Message.message_type == "nota_interna").one()
        assert "comprobante de pago" in nota.content

    def test_pdf_con_pie_tambien(self, db, entorno):
        ag, conv, s = _montar(db, cfg=cfg_bot3(), sufijo="AD2")
        twilio_webhook.process_twilio_inbound(
            db, _foto("MMa2", "ahí va el soporte", tipo="application/pdf"))
        assert entorno["runtimes"][-1]["adjunto"] == "documento"
        db.expire_all()
        assert db.query(models.Conversation).get(conv.id).assigned_to != "bot"

    def test_texto_sin_adjunto_no_lleva_la_llave(self, db, entorno):
        ag, conv, s = _montar(db, cfg=cfg_bot3(), sufijo="AD3")
        form = _foto("MMa3", "ya casi te mando el comprobante")
        form.update({"NumMedia": "0"})
        form.pop("MediaUrl0")
        form.pop("MediaContentType0")
        twilio_webhook.process_twilio_inbound(db, form)
        assert "adjunto" not in entorno["runtimes"][-1]
        db.expire_all()
        assert db.query(models.Conversation).get(conv.id).assigned_to == "bot"

    def test_nota_de_voz_no_es_comprobante(self, db, entorno):
        ag, conv, s = _montar(db, cfg=cfg_bot3(), sufijo="AD4")
        twilio_webhook.process_twilio_inbound(db, _foto("MMa4", "", tipo="audio/ogg"))
        assert "adjunto" not in entorno["runtimes"][-1]


class TestSinFlagNadaCambia:
    @pytest.mark.parametrize("extra", [{}, {"recordatorios_con_contexto": True,
                                            "intencion_compra": {"horas_para_interesado": 6}}])
    def test_runtime_de_bots_1_y_2(self, db, entorno, extra):
        cfg = json.loads(json.dumps(LLM_CONFIG))
        cfg.update(extra)
        ag, conv, s = _montar(db, cfg=cfg, sufijo="SF" + str(len(extra)))
        twilio_webhook.process_twilio_inbound(db, _foto("MMs" + str(len(extra)), "te mando el comprobante"))
        assert set(entorno["runtimes"][-1]) == LLAVES_BOT1
        db.expire_all()
        assert db.query(models.Conversation).get(conv.id).assigned_to == "bot"


class TestAdjuntoDelTurno:
    def test_una_foto_vieja_no_se_atribuye_al_texto_nuevo(self, db):
        from app import crud

        ag = crear_agencia(db, sufijo="AV")
        conv = models.Conversation(team_id=ag["team"].id, contact_wa_id=WA_CLIENTE)
        db.add(conv)
        db.commit()
        crud.add_message(db, conv, direction="inbound", message_type="image",
                         content="[imagen]\nhttps://api.ejemplo.test/a.jpg", status="received")
        assert bot_runner._adjunto_del_turno(db, conv, "[imagen]") == "imagen"
        assert bot_runner._adjunto_del_turno(db, conv, "hola otra vez") is None
        crud.add_message(db, conv, direction="inbound", message_type="text",
                         content="hola otra vez", status="received")
        assert bot_runner._adjunto_del_turno(db, conv, "hola otra vez") is None


class TestEmparejamientoEstricto:
    """Auditoría de seguridad B2: el texto del turno tiene que ser el del
    entrante COMPLETO; un texto vacío o un prefijo no emparejan."""

    @pytest.fixture
    def conv_con_foto(self, db):
        from app import crud

        ag = crear_agencia(db, sufijo="B2")
        conv = models.Conversation(team_id=ag["team"].id, contact_wa_id=WA_CLIENTE)
        db.add(conv)
        db.commit()
        crud.add_message(db, conv, direction="inbound", message_type="image",
                         content="te mando el comprobante\nhttps://api.ejemplo.test/a.jpg",
                         status="received")
        return conv

    @pytest.mark.parametrize("texto", ["", "   ", "\n", "te", "te mando", "te mando el comprobantes"])
    def test_vacio_o_prefijo_no_cuenta(self, db, conv_con_foto, texto):
        assert bot_runner._adjunto_del_turno(db, conv_con_foto, texto) is None

    @pytest.mark.parametrize("texto", ["te mando el comprobante", "  te mando el comprobante  "])
    def test_el_texto_completo_si(self, db, conv_con_foto, texto):
        assert bot_runner._adjunto_del_turno(db, conv_con_foto, texto) == "imagen"

    def test_texto_crudo_con_espacios_tal_cual_lo_guardo_el_webhook(self, db):
        from app import crud

        ag = crear_agencia(db, sufijo="B2b")
        conv = models.Conversation(team_id=ag["team"].id, contact_wa_id=WA_CLIENTE)
        db.add(conv)
        db.commit()
        crud.add_message(db, conv, direction="inbound", message_type="image",
                         content="ahí va \nhttps://api.ejemplo.test/a.jpg", status="received")
        assert bot_runner._adjunto_del_turno(db, conv, "ahí va ") == "imagen"
