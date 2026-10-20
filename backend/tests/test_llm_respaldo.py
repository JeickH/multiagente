"""Reintentos y modelo de respaldo del motor LLM (caídas de Haiku, 19/20-oct-2026).

El cliente no debe ver la disculpa técnica mientras quede un intento: primero
`_INTENTOS_MODELO` llamadas al modelo del bot, luego `_INTENTOS_RESPALDO` al de
respaldo, y solo si todas fallan, el failsafe de siempre.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from botocore.exceptions import ClientError, ReadTimeoutError

from app.services import llm_engine

PRINCIPAL = llm_engine._DEFAULT_MODEL_ID
RESPALDO = llm_engine._DEFAULT_FALLBACK_MODEL_ID


class FakeBot:
    id = 99
    engine = "llm"

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = json.dumps(llm_config or {"context_key": "demo_viajes"})


def _resp(content, stop_reason="end_turn"):
    return {"content": content, "stop_reason": stop_reason}


def _error_aws(code="ServiceUnavailableException"):
    return ClientError({"Error": {"Code": code, "Message": "x"}}, "InvokeModel")


class FakeModelo:
    """Hace de `_invoke_model`: falla con el error que toque según el modelo y
    el número de llamada, y anota a quién llamaron."""

    def __init__(self, fallas_por_modelo: dict, respuestas=None):
        self.fallas = {m: list(f) for m, f in fallas_por_modelo.items()}
        self.respuestas = list(respuestas or [_resp([{"type": "text", "text": "¡Hola!"}])])
        self.llamadas: list[str] = []

    def __call__(self, model_id, system, messages, tools):
        self.llamadas.append(model_id)
        pendientes = self.fallas.get(model_id) or []
        if pendientes:
            raise pendientes.pop(0)
        return self.respuestas.pop(0) if len(self.respuestas) > 1 else self.respuestas[0]


class RespaldoTests(unittest.TestCase):
    def setUp(self):
        # Sin esperas reales entre intentos.
        p = patch.object(llm_engine.time, "sleep")
        self.sleep = p.start()
        self.addCleanup(p.stop)

    def _turno(self, fake, cfg=None):
        with patch.object(llm_engine, "_invoke_model", side_effect=fake):
            return llm_engine.advance(FakeBot(cfg), None, "hola")

    def test_dos_fallas_y_el_tercer_intento_responde_sin_respaldo(self):
        fake = FakeModelo({PRINCIPAL: [_error_aws(), _error_aws()]})
        out = self._turno(fake)
        self.assertEqual(fake.llamadas, [PRINCIPAL] * 3)
        self.assertFalse(out["telemetry"]["failsafe"])
        self.assertEqual(out["actions"], [{"type": "say", "payload": {"text": "¡Hola!"}}])
        self.assertEqual(out["telemetry"]["model_id"], PRINCIPAL)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1.0, 3.0])

    def test_tres_fallas_pasan_al_respaldo_y_el_cliente_no_ve_la_disculpa(self):
        fake = FakeModelo({PRINCIPAL: [_error_aws()] * 3})
        out = self._turno(fake)
        self.assertEqual(fake.llamadas, [PRINCIPAL] * 3 + [RESPALDO])
        self.assertFalse(out["telemetry"]["failsafe"])
        self.assertFalse(out["finished"])
        textos = json.dumps(out["actions"], ensure_ascii=False)
        self.assertNotIn("inconveniente técnico", textos)
        self.assertNotIn("handoff", [a["type"] for a in out["actions"]])
        # La telemetría registra el modelo que de verdad respondió.
        self.assertEqual(out["telemetry"]["model_id"], RESPALDO)

    def test_failsafe_solo_cuando_fallan_el_modelo_y_el_respaldo(self):
        fake = FakeModelo({PRINCIPAL: [_error_aws()] * 3, RESPALDO: [_error_aws()] * 2})
        out = self._turno(fake)
        self.assertEqual(fake.llamadas, [PRINCIPAL] * 3 + [RESPALDO] * 2)
        self.assertTrue(out["telemetry"]["failsafe"])
        self.assertEqual([a["type"] for a in out["actions"]], ["say", "handoff"])
        self.assertIn("inconveniente técnico", out["actions"][0]["payload"]["text"])

    def test_respaldo_que_falla_una_vez_y_luego_responde(self):
        fake = FakeModelo({PRINCIPAL: [_error_aws()] * 3, RESPALDO: [_error_aws()]})
        out = self._turno(fake)
        self.assertEqual(fake.llamadas, [PRINCIPAL] * 3 + [RESPALDO] * 2)
        self.assertFalse(out["telemetry"]["failsafe"])

    def test_timeout_sin_respuesta_del_servicio_tambien_se_reintenta(self):
        fake = FakeModelo({PRINCIPAL: [ReadTimeoutError(endpoint_url="https://x")]})
        out = self._turno(fake)
        self.assertEqual(fake.llamadas, [PRINCIPAL] * 2)
        self.assertFalse(out["telemetry"]["failsafe"])

    def test_error_no_transitorio_salta_directo_al_respaldo(self):
        fake = FakeModelo({PRINCIPAL: [_error_aws("AccessDeniedException")]})
        out = self._turno(fake)
        self.assertEqual(fake.llamadas, [PRINCIPAL, RESPALDO])
        self.assertFalse(out["telemetry"]["failsafe"])

    def test_error_nuestro_no_se_reintenta(self):
        # Un bug del motor no es culpa de Bedrock: repetirlo da lo mismo.
        fake = FakeModelo({PRINCIPAL: [RuntimeError("boom")]})
        out = self._turno(fake)
        self.assertEqual(fake.llamadas, [PRINCIPAL])
        self.assertTrue(out["telemetry"]["failsafe"])

    def test_bot_que_ya_usa_el_respaldo_no_lo_repite(self):
        fake = FakeModelo({RESPALDO: [_error_aws()] * 3})
        out = self._turno(fake, {"context_key": "demo_viajes", "model_id": RESPALDO})
        self.assertEqual(fake.llamadas, [RESPALDO] * 3)
        self.assertTrue(out["telemetry"]["failsafe"])

    def test_respaldo_propio_del_bot(self):
        otro = "global.anthropic.claude-opus-4-5-20251101-v1:0"
        fake = FakeModelo({PRINCIPAL: [_error_aws()] * 3})
        self._turno(fake, {"context_key": "demo_viajes", "fallback_model_id": otro})
        self.assertEqual(fake.llamadas[-1], otro)

    def test_tras_pasar_al_respaldo_el_resto_del_turno_sigue_en_el(self):
        # Ronda 1 con herramienta (respondida por el respaldo) y ronda 2 de
        # texto: la segunda va directo al respaldo, sin otros tres intentos.
        cfg = {
            "context_key": "demo_viajes",
            "media": {"tarifario1": {"url": "https://x/t1.jpeg", "media_type": "image"}},
        }
        fake = FakeModelo(
            {PRINCIPAL: [_error_aws()] * 3},
            respuestas=[
                _resp([{"type": "tool_use", "id": "t1", "name": "enviar_media",
                        "input": {"claves": ["tarifario1"]}}], stop_reason="tool_use"),
                _resp([{"type": "text", "text": "Ahí van los precios"}]),
            ],
        )
        out = self._turno(fake, cfg)
        self.assertEqual(fake.llamadas, [PRINCIPAL] * 3 + [RESPALDO] * 2)
        self.assertEqual([a["type"] for a in out["actions"]], ["say_media", "say"])
        # El medio salió una sola vez: no se repitió la ronda de la herramienta.
        self.assertEqual(sum(a["type"] == "say_media" for a in out["actions"]), 1)

    def test_cliente_de_bedrock_sin_reintentos_propios(self):
        llm_engine._bedrock_client.cache_clear()
        self.addCleanup(llm_engine._bedrock_client.cache_clear)
        cliente = llm_engine._bedrock_client()
        self.assertEqual(cliente.meta.config.retries.get("total_max_attempts"), 1)


if __name__ == "__main__":
    unittest.main()
