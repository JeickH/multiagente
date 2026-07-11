"""Tests del motor de bots LLM (Sprint 19) con Bedrock mockeado.

No requieren red ni credenciales AWS: se parchea `llm_engine._invoke_model`.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services import llm_engine


class FakeBot:
    id = 99
    engine = "llm"

    def __init__(self, llm_config: dict | None = None):
        self.llm_config = json.dumps(llm_config or {"context_key": "demo_viajes"})


def _resp(content, stop_reason="end_turn"):
    return {"content": content, "stop_reason": stop_reason}


class LlmEngineTests(unittest.TestCase):
    def test_texto_simple_produce_say_y_estado(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp([{"type": "text", "text": "¡Hola! ¿Tu nombre?"}])
            out = llm_engine.advance(FakeBot(), None, None)
        self.assertEqual(out["actions"], [
            {"type": "say", "payload": {"text": "¡Hola! ¿Tu nombre?"}}
        ])
        self.assertFalse(out["finished"])
        history = out["next_state"]["history"]
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertIn("Hola", history[-1]["content"])

    def test_tool_escalar_produce_handoff_y_finaliza(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp(
                [
                    {"type": "text", "text": "Te comunico con una asesora 🌿"},
                    {"type": "tool_use", "id": "t1", "name": "escalar_a_asesor",
                     "input": {"motivo": "pide humano"}},
                ],
                stop_reason="tool_use",
            )
            out = llm_engine.advance(
                FakeBot({"context_key": "talulah", "assignee": "asesor_1"}),
                {"history": []}, "quiero un asesor",
            )
        types = [a["type"] for a in out["actions"]]
        self.assertEqual(types, ["say", "handoff"])
        self.assertEqual(out["actions"][1]["payload"]["assignee"], "asesor_1")
        self.assertTrue(out["finished"])
        self.assertIsNone(out["next_state"])
        # Solo una llamada al modelo: el handoff corta el loop de tools.
        self.assertEqual(mock.call_count, 1)

    def test_tool_media_emite_say_media_y_sigue_el_loop(self):
        cfg = {
            "context_key": "demo_viajes",
            "media": {"tarifario1": {"url": "https://x/t1.jpeg",
                                      "media_type": "image"}},
        }
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.side_effect = [
                _resp(
                    [{"type": "tool_use", "id": "t1", "name": "enviar_media",
                      "input": {"claves": ["tarifario1", "inexistente"]}}],
                    stop_reason="tool_use",
                ),
                _resp([{"type": "text", "text": "Ahí van los precios ✨"}]),
            ]
            out = llm_engine.advance(FakeBot(cfg), {"history": []}, "precios?")
        types = [a["type"] for a in out["actions"]]
        self.assertEqual(types, ["say_media", "say"])
        self.assertEqual(out["actions"][0]["payload"]["url"], "https://x/t1.jpeg")
        self.assertEqual(mock.call_count, 2)
        # El tool_result le informó al modelo la clave inexistente.
        second_call_messages = mock.call_args_list[1][0][2]
        self.assertIn("inexistente", json.dumps(second_call_messages))
        # La marca de media queda en el historial aplanado.
        self.assertIn("tarifario1", out["next_state"]["history"][-1]["content"])

    def test_error_del_proveedor_activa_failsafe_handoff(self):
        with patch.object(llm_engine, "_invoke_model", side_effect=RuntimeError("boom")):
            out = llm_engine.advance(FakeBot(), None, "hola")
        types = [a["type"] for a in out["actions"]]
        self.assertEqual(types, ["say", "handoff"])
        self.assertTrue(out["finished"])

    def test_historial_se_recorta_al_maximo(self):
        long_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"}
            for i in range(60)
        ]
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp([{"type": "text", "text": "ok"}])
            out = llm_engine.advance(FakeBot(), {"history": long_history}, "hola")
        self.assertLessEqual(
            len(out["next_state"]["history"]), llm_engine._MAX_HISTORY_MESSAGES
        )

    def test_context_key_sanitizado_no_escapa_del_directorio(self):
        self.assertEqual(llm_engine._load_context("../../etc/passwd"), "")

    def test_contextos_empaquetados_existen(self):
        self.assertIn("Talulah", llm_engine._load_context("talulah"))
        self.assertIn("Coveñas", llm_engine._load_context("demo_viajes"))


if __name__ == "__main__":
    unittest.main()
