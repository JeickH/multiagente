"""El camino del pedido: la herramienta, el guardarraíl y la hoja de Drive.

Lo que protege cada bloque:

  - `RegistrarPedidoTests`: que la tool exija los tres datos y que el pedido
    viaje en `telemetry` (es de ahí de donde lo toman los dos canales).
  - `ConfirmacionTests`: el guardarraíl que le confirma el pedido al cliente.
    Existe porque se midió: con la regla escrita en el documento del bot, el
    modelo registraba y escalaba bien y **se comía la confirmación 4 de 4
    veces**. La persona mandaba su nombre y su dirección y lo único que recibía
    era "te paso con un asesor".
  - `HojaTests`: que un fallo de Google no tumbe el turno ni pierda el pedido.

Bedrock va mockeado (`_invoke_model`): no hace falta red ni credenciales.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services import llm_engine, pedidos_sheet


CFG = {
    "context_key": "natulce",
    "assignee": "asesor_1",
    "pedidos": {"hoja": "Pedidos Natulcé — WhatsApp"},
}


class FakeBot:
    id = 77
    engine = "llm"
    user_id = 5

    def __init__(self, cfg: dict | None = None):
        self.llm_config = json.dumps(cfg or CFG)


def _resp(content, stop_reason="end_turn"):
    return {"content": content, "stop_reason": stop_reason}


def _tool(tool="registrar_pedido", **entrada):
    # El parámetro se llama `tool` y no `nombre` a propósito: `nombre` es un
    # campo del pedido, y con el mismo nombre las dos cosas chocan.
    return {"type": "tool_use", "id": "t1", "name": tool, "input": entrada}


DATOS = {
    "nombre": "Ana Ruiz",
    "direccion": "Cra 70 #45-12 Bogotá",
    "pedido": "2 flor de jamaica",
    "total": "$58.000",
}


class RegistrarPedidoTests(unittest.TestCase):
    def test_la_herramienta_solo_existe_si_el_bot_tiene_pedidos(self):
        con = [t["name"] for t in llm_engine._tools_for(CFG)]
        sin = [t["name"] for t in llm_engine._tools_for({"context_key": "natulce"})]
        self.assertIn("registrar_pedido", con)
        self.assertNotIn("registrar_pedido", sin)

    def test_el_pedido_viaja_en_telemetry(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.side_effect = [
                _resp([_tool(**DATOS)], stop_reason="tool_use"),
                _resp([{"type": "text", "text": "¡Listo, Ana! Confirmo tu pedido."}]),
            ]
            out = llm_engine.advance(FakeBot(), {"history": []}, "mis datos")
        pedidos = out["telemetry"]["pedidos"]
        self.assertEqual(len(pedidos), 1)
        self.assertEqual(pedidos[0]["nombre"], "Ana Ruiz")
        self.assertEqual(pedidos[0]["total"], "$58.000")

    def test_sin_direccion_no_registra_y_pide_lo_que_falta(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.side_effect = [
                _resp(
                    [_tool(nombre="Ana", pedido="2 maracuyá")],
                    stop_reason="tool_use",
                ),
                _resp([{"type": "text", "text": "¿Me confirmas la dirección?"}]),
            ]
            out = llm_engine.advance(FakeBot(), {"history": []}, "mis datos")
        self.assertEqual(out["telemetry"]["pedidos"], [])
        resultado = out["telemetry"]["tools"][0]["resultado"]
        self.assertIn("direccion", resultado)


class ConfirmacionTests(unittest.TestCase):
    def test_si_el_turno_no_escribe_nada_el_motor_confirma(self):
        """El caso medido: registra, escala y no le dice nada al cliente."""
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp(
                [
                    _tool(**DATOS),
                    _tool(tool="escalar_a_asesor", motivo="cerrar pedido"),
                ],
                stop_reason="tool_use",
            )
            out = llm_engine.advance(FakeBot(), {"history": []}, "mis datos")

        tipos = [a["type"] for a in out["actions"]]
        self.assertEqual(tipos, ["say", "handoff"], "la confirmación va ANTES del handoff")
        texto = out["actions"][0]["payload"]["text"]
        # Los tres datos que el cliente acaba de dar, de vuelta en su pantalla.
        self.assertIn("Ana Ruiz", texto)
        self.assertIn("Cra 70 #45-12 Bogotá", texto)
        self.assertIn("2 flor de jamaica", texto)
        self.assertIn("$58.000", texto)
        # Saludo con el primer nombre, no con nombre y apellido.
        self.assertTrue(texto.startswith("¡Listo, Ana!"), texto[:40])

    def test_si_el_modelo_ya_confirmo_no_se_duplica(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.return_value = _resp(
                [
                    {"type": "text", "text": "¡Listo Ana! Tu pedido quedó registrado ✅"},
                    _tool(**DATOS),
                    _tool(tool="escalar_a_asesor", motivo="cerrar pedido"),
                ],
                stop_reason="tool_use",
            )
            out = llm_engine.advance(FakeBot(), {"history": []}, "mis datos")
        says = [a for a in out["actions"] if a["type"] == "say"]
        self.assertEqual(len(says), 1)
        self.assertIn("quedó registrado", says[0]["payload"]["text"])

    def test_la_plantilla_del_tenant_manda(self):
        cfg = dict(CFG, pedidos={**CFG["pedidos"], "confirmacion": "OK {nombre}: {pedido}"})
        texto = llm_engine._texto_de_confirmacion(cfg, DATOS)
        self.assertEqual(texto, "OK Ana Ruiz: 2 flor de jamaica")

    def test_una_plantilla_rota_no_tumba_el_turno(self):
        cfg = dict(CFG, pedidos={**CFG["pedidos"], "confirmacion": "Hola {inexistente}"})
        texto = llm_engine._texto_de_confirmacion(cfg, DATOS)
        self.assertIn("Ana Ruiz", texto)


class HojaTests(unittest.TestCase):
    def test_sin_url_configurada_no_se_intenta_escribir(self):
        with patch("requests.post") as post:
            self.assertFalse(pedidos_sheet.enviar(CFG, DATOS))
        post.assert_not_called()

    def test_la_fila_lleva_los_datos_y_el_token(self):
        cfg = dict(
            CFG,
            pedidos={
                "hoja": "x",
                "webhook_url": "https://script.google.com/macros/s/abc/exec",
                "token": "secreto",
            },
        )
        with patch("requests.post") as post:
            post.return_value.status_code = 200
            self.assertTrue(pedidos_sheet.enviar(cfg, DATOS, telefono="573001112233"))
        fila = post.call_args.kwargs["json"]
        self.assertEqual(fila["nombre"], "Ana Ruiz")
        self.assertEqual(fila["telefono"], "573001112233")
        self.assertEqual(fila["token"], "secreto")
        self.assertEqual(fila["origen"], "whatsapp")

    def test_si_google_falla_no_lanza(self):
        cfg = dict(
            CFG,
            pedidos={"hoja": "x", "webhook_url": "https://script.google.com/s/abc/exec"},
        )
        with patch("requests.post", side_effect=RuntimeError("timeout")):
            self.assertFalse(pedidos_sheet.enviar(cfg, DATOS))


if __name__ == "__main__":
    unittest.main()
