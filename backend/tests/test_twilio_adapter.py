"""Tests del adaptador Twilio del puerto de mensajería.

Cubre la normalización de destinatarios (#317): WhatsApp no siempre entrega un
E.164 — cuando el usuario no comparte su número llega una **identidad opaca**
tipo `CO.3371971396308694`, y anteponerle '+' hacía que Twilio rechazara todo
envío con 21211 (bot mudo en producción).
"""
from __future__ import annotations

import pytest

from app.services.messaging.twilio_adapter import _as_whatsapp, _TWILIO_TO_INTERNAL
from app.services.messaging import twilio_adapter


class TestNormalizacionDestinatario:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            # E.164 en sus variantes: se normaliza con '+'
            ("573150764000", "whatsapp:+573150764000"),
            ("+573150764000", "whatsapp:+573150764000"),
            ("whatsapp:+573150764000", "whatsapp:+573150764000"),
            ("  573150764000  ", "whatsapp:+573150764000"),
        ],
    )
    def test_numeros_e164_llevan_mas(self, entrada, esperado):
        assert _as_whatsapp(entrada) == esperado

    @pytest.mark.parametrize(
        "identidad",
        ["CO.3371971396308694", "MX.1234567890", "US.99887766554433"],
    )
    def test_identidades_opacas_no_llevan_mas(self, identidad):
        """Regresión #317: un '+' aquí produce Twilio 21211 y el bot queda mudo."""
        assert _as_whatsapp(identidad) == f"whatsapp:{identidad}"
        assert "+" not in _as_whatsapp(identidad)

    def test_prefijo_existente_se_respeta(self):
        assert _as_whatsapp("whatsapp:CO.3371971396308694") == "whatsapp:CO.3371971396308694"


class TestSandbox:
    def test_sandbox_por_defecto_simula_envio(self, monkeypatch):
        monkeypatch.setenv("TWILIO_SANDBOX", "1")
        sid, payload = twilio_adapter.send_text(object(), "573150764000", "hola")
        assert sid.startswith("SM.local-")
        assert payload["sandbox"] is True

    def test_sandbox_tambien_simula_media(self, monkeypatch):
        monkeypatch.setenv("TWILIO_SANDBOX", "1")
        sid, payload = twilio_adapter.send_media(
            object(), "573150764000", "https://ejemplo.com/x.jpg", caption="pie"
        )
        assert sid.startswith("MM.local-")
        assert payload["sandbox"] is True


class TestSendMediaValidacion:
    def test_url_no_https_falla_sin_reintento(self, monkeypatch):
        """WhatsApp rechaza media no-HTTPS: fallamos temprano y no-retryable
        para que el caller haga fallback a texto en vez de reintentar en vano."""
        monkeypatch.setenv("TWILIO_SANDBOX", "0")

        class _Cuenta:
            twilio_account_sid = "ACxxx"
            encrypted_twilio_auth_token = None
            twilio_from = "whatsapp:+573334324954"
            twilio_messaging_service_sid = None

        monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token-de-prueba")
        with pytest.raises(Exception) as exc:
            twilio_adapter.send_media(
                _Cuenta(), "573150764000", "http://inseguro.com/x.jpg"
            )
        assert getattr(exc.value, "retryable", None) is False


class TestMapeoDeEstados:
    @pytest.mark.parametrize(
        "twilio,interno",
        [
            ("queued", "queued"),
            ("sent", "sent"),
            ("delivered", "delivered"),
            ("read", "read"),
            ("undelivered", "failed"),
            ("failed", "failed"),
        ],
    )
    def test_estados_se_mapean_al_funnel_interno(self, twilio, interno):
        assert _TWILIO_TO_INTERNAL[twilio] == interno
