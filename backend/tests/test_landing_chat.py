"""Tests del chat público de la landing (Sprint 20 #269) y del formato WhatsApp.

No requieren red ni credenciales AWS: se parchea `llm_engine._invoke_model` y
`llm_engine.record_decision` (la telemetría necesita BD).
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

# El módulo de cifrado hace fail-fast al importarse: en tests usamos una clave
# efímera (nunca una real).
os.environ.setdefault("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())

from app.routers import landing  # noqa: E402
from app.services import llm_engine  # noqa: E402


class FakeBot:
    id = 77
    engine = "llm"
    status = "active"

    def __init__(self):
        self.llm_config = json.dumps(
            {"context_key": "gloma", "assignee": "asesor_1"}
        )


class FakeRequest:
    def __init__(self, ip="1.2.3.4"):
        self.headers = {"x-forwarded-for": ip}
        self.client = None


def _resp(content, stop_reason="end_turn"):
    return {"content": content, "stop_reason": stop_reason}


def _reset_rate_limit():
    landing._hits_by_ip.clear()
    landing._hits_global.clear()


class WhatsappFormatTests(unittest.TestCase):
    def test_negrilla_markdown_se_convierte_a_whatsapp(self):
        self.assertEqual(
            llm_engine._to_whatsapp_format("Somos **Gloma** y **vendemos** más"),
            "Somos *Gloma* y *vendemos* más",
        )

    def test_no_toca_asterisco_simple_ni_separadores(self):
        self.assertEqual(
            llm_engine._to_whatsapp_format("ya es *negrilla* y ** suelto"),
            "ya es *negrilla* y ** suelto",
        )


class RegistrarDemoTests(unittest.TestCase):
    """Sprint 21 #276: validación y telemetría de la tool `registrar_demo`."""

    CFG = {"context_key": "gloma", "assignee": "asesor_1", "agenda": {}}

    def test_la_tool_solo_existe_si_el_bot_tiene_agenda(self):
        con = {t["name"] for t in llm_engine._tools_for(self.CFG)}
        sin = {t["name"] for t in llm_engine._tools_for({"context_key": "gloma"})}
        self.assertIn("registrar_demo", con)
        self.assertNotIn("registrar_demo", sin)

    def test_datos_validos_producen_reserva_normalizada(self):
        booking, msg = llm_engine._clean_booking({
            "correo": "  Marcela@BellaModa.com ", "dia": "Miércoles",
            "hora": "4:00 p.m.", "nombre": "Marcela", "empresa": "Bella Moda",
        })
        self.assertEqual(msg, "")
        self.assertEqual(booking["correo"], "marcela@bellamoda.com")
        self.assertEqual(booking["dia"], "miércoles")

    def test_correo_invalido_no_registra_y_pide_de_nuevo(self):
        booking, msg = llm_engine._clean_booking(
            {"correo": "no-es-correo", "dia": "lunes", "hora": "3:00 p.m."}
        )
        self.assertIsNone(booking)
        self.assertIn("correo", msg)

    def test_fin_de_semana_no_registra(self):
        booking, msg = llm_engine._clean_booking(
            {"correo": "a@b.com", "dia": "sábado", "hora": "3:00 p.m."}
        )
        self.assertIsNone(booking)
        self.assertIn("lunes a viernes", msg)

    def test_la_reserva_viaja_en_telemetry_para_que_la_guarde_el_caller(self):
        bot = FakeBot()
        bot.llm_config = json.dumps(self.CFG)
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp(
                [{"type": "tool_use", "id": "t1", "name": "registrar_demo",
                  "input": {"correo": "juan@kinovet.com", "dia": "lunes",
                            "hora": "3:00 p.m.", "nombre": "Juan"}}],
                stop_reason="tool_use",
            )
            out = llm_engine.advance(bot, None, "quiero la demo el lunes 3pm")
        tel = out["telemetry"]
        self.assertEqual(tel["camino"], "demo_agendada")
        self.assertEqual(tel["bookings"][0]["correo"], "juan@kinovet.com")
        # La reserva NO se emite como acción: el runner y el simulador solo
        # conocen say/say_media/handoff/end.
        self.assertNotIn("demo_booking", {a["type"] for a in out["actions"]})


class LandingSessionTests(unittest.TestCase):
    def test_roundtrip_de_la_sesion_cifrada(self):
        history = [{"role": "user", "content": "hola"}]
        token = landing._dump_session(history, 3)
        self.assertNotIn("hola", token)  # el historial viaja cifrado
        sess = landing._load_session(token)
        self.assertEqual(sess["history"], history)
        self.assertEqual(sess["turns"], 3)

    def test_token_manipulado_no_rompe_y_arranca_sesion_nueva(self):
        for bad in ("gAAAAABtampered", "", None, "no-es-fernet"):
            sess = landing._load_session(bad)
            self.assertEqual(sess, {"history": [], "turns": 0})


class LandingChatTests(unittest.TestCase):
    def setUp(self):
        _reset_rate_limit()

    def _call(self, payload, ip="1.2.3.4"):
        with patch.object(landing, "_gloma_bot", return_value=FakeBot()), \
             patch.object(landing.llm_engine, "record_decision"):
            return landing.landing_chat(payload, FakeRequest(ip), db=None)

    def test_turno_normal_devuelve_texto_y_sesion(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp([{"type": "text", "text": "¡Hola! Soy Lía"}])
            out = self._call(landing.ChatIn(session=None, message=None))
        self.assertEqual(out.actions[0].text, "¡Hola! Soy Lía")
        self.assertFalse(out.finished)
        self.assertTrue(out.session)

    def test_handoff_ofrece_whatsapp_humano_y_cierra(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp(
                [{"type": "tool_use", "id": "t1", "name": "escalar_a_asesor",
                  "input": {"motivo": "pide cotización"}}],
                stop_reason="tool_use",
            )
            out = self._call(landing.ChatIn(session=None, message="quiero precio"))
        self.assertTrue(out.handoff)
        self.assertTrue(out.finished)
        self.assertIsNone(out.session)
        self.assertIn("300 318 7871", out.actions[-1].text)

    def test_tope_de_turnos_por_sesion_corta_la_conversacion(self):
        token = landing._dump_session([{"role": "user", "content": "x"}],
                                      landing._MAX_TURNS_PER_SESSION)
        out = self._call(landing.ChatIn(session=token, message="otra más"))
        self.assertTrue(out.finished)
        self.assertIn("WhatsApp", out.actions[0].text)

    def test_rate_limit_por_ip(self):
        for _ in range(landing._RATE_PER_IP_HOUR):
            self.assertTrue(landing._rate_ok("9.9.9.9"))
        self.assertFalse(landing._rate_ok("9.9.9.9"))
        self.assertTrue(landing._rate_ok("9.9.9.10"))  # otra IP sigue pasando

    def test_mensaje_se_limpia_de_caracteres_de_control(self):
        payload = landing.ChatIn(message="hola\x00\x07 mundo")
        self.assertEqual(payload.message, "hola mundo")


if __name__ == "__main__":
    unittest.main()
