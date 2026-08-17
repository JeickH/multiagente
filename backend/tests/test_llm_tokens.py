"""El consumo de cada turno viaja en la telemetría (#366).

Sin esto, lo que cuesta una conversación solo se sabía corriendo un benchmark
aparte. `cache_read` es además el termómetro del prompt caching: si se va a cero
de forma sostenida, el prefijo dejó de ser estable y el ahorro se perdió.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services import llm_engine


class FakeBot:
    id = 77
    engine = "llm"
    status = "active"

    def __init__(self):
        self.llm_config = json.dumps(
            {"context_key": "gloma", "assignee": "asesor_1"}
        )


def _resp(texto, usage, stop_reason="end_turn"):
    return {
        "content": [{"type": "text", "text": texto}],
        "stop_reason": stop_reason,
        "usage": usage,
    }


class TokensEnTelemetriaTests(unittest.TestCase):
    def test_una_ronda_reporta_su_consumo(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp("Hola", {
                "input_tokens": 120, "output_tokens": 30,
                "cache_read_input_tokens": 6000, "cache_creation_input_tokens": 0,
            })
            tel = llm_engine.advance(FakeBot(), None, "hola")["telemetry"]

        self.assertEqual(tel["tokens_in"], 120)
        self.assertEqual(tel["tokens_out"], 30)
        self.assertEqual(tel["cache_read"], 6000)
        self.assertEqual(tel["cache_write"], 0)

    def test_varias_rondas_se_suman(self):
        """Un turno con tool son dos llamadas al modelo: el costo es la suma.

        Es el caso que más importa medir: los turnos que buscan una mascota
        cuestan el doble que los de solo texto, y son justo los que definen el
        costo de una conversación.
        """
        respuestas = [
            {
                "content": [{"type": "tool_use", "id": "t1",
                             "name": "una_tool", "input": {}}],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 100, "output_tokens": 10,
                          "cache_read_input_tokens": 6000,
                          "cache_creation_input_tokens": 0},
            },
            _resp("Listo", {
                "input_tokens": 150, "output_tokens": 20,
                "cache_read_input_tokens": 6000, "cache_creation_input_tokens": 0,
            }),
        ]
        with patch.object(llm_engine, "_invoke_model", side_effect=respuestas), \
             patch.object(llm_engine, "_run_tool", return_value=("ok", False)):
            tel = llm_engine.advance(FakeBot(), None, "busco algo")["telemetry"]

        self.assertEqual(tel["tokens_in"], 250)
        self.assertEqual(tel["tokens_out"], 30)
        self.assertEqual(tel["cache_read"], 12000)

    def test_sin_usage_no_revienta(self):
        """Bedrock siempre lo manda, pero un turno sin `usage` no puede tumbar
        la conversación: el costo se reporta en cero, no explota."""
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = {"content": [{"type": "text", "text": "Hola"}],
                                 "stop_reason": "end_turn"}
            tel = llm_engine.advance(FakeBot(), None, "hola")["telemetry"]

        self.assertEqual(tel["tokens_in"], 0)
        self.assertEqual(tel["cache_read"], 0)


if __name__ == "__main__":
    unittest.main()
