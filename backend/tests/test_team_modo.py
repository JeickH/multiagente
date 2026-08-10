"""Tests del modo operativo por tenant (#318): demo vs producción.

La garantía que importa: un team en `modo='demo'` NUNCA envía de verdad, ni
siquiera con credenciales válidas y los sandbox globales apagados.
"""
from __future__ import annotations

import pytest

from app.services.messaging.base import team_is_demo
from app.services.messaging import twilio_adapter, meta_adapter


class _Team:
    def __init__(self, modo):
        self.modo = modo


class _Cuenta:
    """MetaAccount mínima con credenciales Twilio completas y válidas."""

    def __init__(self, modo):
        self.team = _Team(modo) if modo is not None else None
        self.twilio_account_sid = "ACxxxxxxxx"
        self.encrypted_twilio_auth_token = None
        self.twilio_from = "whatsapp:+573334324954"
        self.twilio_messaging_service_sid = None
        self.encrypted_access_token = "cifrado"


@pytest.fixture(autouse=True)
def _sandboxes_apagados(monkeypatch):
    """Apaga los sandbox globales: así el único factor es el modo del team."""
    monkeypatch.setenv("TWILIO_SANDBOX", "0")
    monkeypatch.setenv("META_SANDBOX", "0")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token-de-prueba")


class TestTeamIsDemo:
    def test_produccion_no_es_demo(self):
        assert team_is_demo(_Cuenta("produccion")) is False

    def test_demo_es_demo(self):
        assert team_is_demo(_Cuenta("demo")) is True

    def test_modo_desconocido_se_trata_como_demo(self):
        """Cualquier valor que no sea 'produccion' no habilita envíos reales."""
        assert team_is_demo(_Cuenta("loquesea")) is True

    def test_cuenta_sin_team_no_se_bloquea(self):
        assert team_is_demo(_Cuenta(None)) is False


class TestGateEnLosAdaptadores:
    def test_twilio_demo_fuerza_sandbox(self):
        assert twilio_adapter.is_sandbox(_Cuenta("demo")) is True

    def test_twilio_produccion_envia_real(self):
        assert twilio_adapter.is_sandbox(_Cuenta("produccion")) is False

    def test_meta_demo_fuerza_sandbox(self):
        assert meta_adapter.is_sandbox(_Cuenta("demo")) is True

    def test_meta_produccion_envia_real(self):
        assert meta_adapter.is_sandbox(_Cuenta("produccion")) is False

    def test_demo_simula_el_envio_en_vez_de_llamar_a_twilio(self):
        """Regresión: un team demo no debe generar tráfico real a Twilio."""
        sid, payload = twilio_adapter.send_text(_Cuenta("demo"), "573150764000", "hola")
        assert sid.startswith("SM.local-")
        assert payload["sandbox"] is True

    def test_demo_tambien_simula_media(self):
        sid, payload = twilio_adapter.send_media(
            _Cuenta("demo"), "573150764000", "https://ejemplo.com/x.jpg"
        )
        assert sid.startswith("MM.local-")
        assert payload["sandbox"] is True
