"""Tests del camino de venta con link de pago (#374, bot de Jerarquía).

Bedrock va mockeado: no requieren red ni credenciales AWS.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.services import llm_engine


VENTA_CFG = {
    "context_key": "jerarquia",
    "assignee": "asesor_1",
    "venta": {
        "producto": "Promo Manada — 3 camisetas tipo polo",
        "valor": "$160.000",
        "prefijo": "JRQ",
        "link_pago": "https://app.glomabeauty.com/pago-demo?ref={ref}&total=160000",
    },
}

DATOS_OK = {
    "nombre": "Julián Restrepo",
    "cedula": "1017234567",
    "telefono": "3104567890",
    "correo": "julian@correo.com",
    "direccion": "Cra 45 #12-30 apto 502, Medellín",
    "detalle": "2 negras L y una blanca M",
}


class FakeBot:
    id = 77
    engine = "llm"

    def __init__(self, llm_config: dict):
        self.llm_config = json.dumps(llm_config)


def _resp(content, stop_reason="end_turn"):
    return {"content": content, "stop_reason": stop_reason}


def _tool_use(name, tool_input, tid="t1"):
    return {"type": "tool_use", "id": tid, "name": name, "input": tool_input}


class ToolDisponibleTests(unittest.TestCase):
    def test_la_tool_solo_existe_si_hay_config_de_venta(self):
        nombres = {t["name"] for t in llm_engine._tools_for(VENTA_CFG)}
        self.assertIn("registrar_venta", nombres)

        otros = {t["name"] for t in llm_engine._tools_for({"context_key": "gloma"})}
        self.assertNotIn("registrar_venta", otros)


class ValidacionDatosTests(unittest.TestCase):
    def test_datos_completos_generan_referencia_y_link(self):
        venta, problema = llm_engine._clean_venta(dict(DATOS_OK), VENTA_CFG)
        self.assertEqual(problema, "")
        assert venta is not None
        self.assertTrue(venta["ref"].startswith("JRQ-"))
        self.assertIn(venta["ref"], venta["link"])
        self.assertTrue(venta["link"].startswith("https://app.glomabeauty.com/pago-demo"))
        # La cédula y el celular quedan normalizados a dígitos.
        self.assertEqual(venta["cedula"], "1017234567")

    def test_cada_referencia_es_distinta(self):
        a, _ = llm_engine._clean_venta(dict(DATOS_OK), VENTA_CFG)
        b, _ = llm_engine._clean_venta(dict(DATOS_OK), VENTA_CFG)
        assert a is not None and b is not None
        self.assertNotEqual(a["ref"], b["ref"])

    def test_cedula_con_puntos_se_acepta(self):
        datos = dict(DATOS_OK, cedula="1.017.234.567")
        venta, problema = llm_engine._clean_venta(datos, VENTA_CFG)
        self.assertEqual(problema, "")
        assert venta is not None
        self.assertEqual(venta["cedula"], "1017234567")

    def test_datos_invalidos_no_generan_link(self):
        casos = {
            "nombre": dict(DATOS_OK, nombre="Julián"),
            "cedula": dict(DATOS_OK, cedula="123"),
            "telefono": dict(DATOS_OK, telefono="12"),
            "correo": dict(DATOS_OK, correo="julian.correo"),
            "direccion": dict(DATOS_OK, direccion="pendiente"),
        }
        for campo, datos in casos.items():
            with self.subTest(campo=campo):
                venta, problema = llm_engine._clean_venta(datos, VENTA_CFG)
                self.assertIsNone(venta)
                self.assertTrue(problema)

    def test_el_modelo_recibe_la_instruccion_del_comprobante(self):
        """El resultado COMPLETO (el que ve el modelo) trae el guion del cierre."""
        actions: list = []
        resultado, terminado = llm_engine._run_tool(
            "registrar_venta", dict(DATOS_OK), VENTA_CFG, actions, [], None, [],
        )
        self.assertFalse(terminado)
        self.assertEqual(actions, [])       # la venta no emite acciones al canal
        self.assertIn("comprobante", resultado)
        self.assertIn("EXACTO", resultado)

    def test_link_no_https_cae_al_default(self):
        cfg = {"venta": {"link_pago": "http://inseguro/pago?ref={ref}"}}
        venta, _ = llm_engine._clean_venta(dict(DATOS_OK), cfg)
        assert venta is not None
        self.assertTrue(venta["link"].startswith("https://"))


class TurnoDeVentaTests(unittest.TestCase):
    def test_registrar_venta_devuelve_link_y_no_cierra_la_conversacion(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.side_effect = [
                _resp([_tool_use("registrar_venta", dict(DATOS_OK))],
                      stop_reason="tool_use"),
                # Sin URL propia: el link que se le pasa al cliente se prueba
                # en `test_el_link_de_la_herramienta_si_pasa`.
                _resp([{"type": "text", "text": "Pedido registrado ✅"}]),
            ]
            out = llm_engine.advance(
                FakeBot(VENTA_CFG), {"history": []},
                "Julián Restrepo, CC 1017234567, 3104567890, julian@correo.com, "
                "Cra 45 #12-30 apto 502, Medellín",
            )
        tel = out["telemetry"]
        self.assertEqual(tel["camino"], "venta_registrada")
        self.assertFalse(out["finished"])          # la venta no cierra el chat
        self.assertIsNotNone(out["next_state"])
        llamada = tel["tools"][0]
        self.assertEqual(llamada["tool"], "registrar_venta")
        # El link va al inicio del resultado a propósito: la telemetría recorta
        # a 300 caracteres y el guardarraíl compara contra ese recorte.
        self.assertIn("JRQ-", llamada["resultado"])
        self.assertIn("/pago-demo?ref=JRQ-", llamada["resultado"])
        # El pedido queda en el historial aplanado: el bot no lo olvida.
        self.assertIn("pedido JRQ-", out["next_state"]["history"][-1]["content"])

    def test_datos_incompletos_no_registran_y_el_modelo_recibe_el_motivo(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.side_effect = [
                _resp([_tool_use("registrar_venta", dict(DATOS_OK, correo="julian"))],
                      stop_reason="tool_use"),
                _resp([{"type": "text", "text": "Me falta tu correo 👊"}]),
            ]
            out = llm_engine.advance(
                FakeBot(VENTA_CFG), {"history": []}, "ahí van mis datos",
            )
        resultado = out["telemetry"]["tools"][0]["resultado"]
        self.assertIn("correo", resultado)
        self.assertNotIn("pago-demo", resultado)
        # Lo único que sale al cliente es el texto pidiendo el dato que falta.
        self.assertEqual([a["type"] for a in out["actions"]], ["say"])


class GuardarrailLinkTests(unittest.TestCase):
    def test_link_inventado_no_llega_al_cliente(self):
        """El modelo escribe una URL sin llamar la herramienta: se descarta."""
        with patch.object(llm_engine, "_invoke_model") as mock:
            mock.side_effect = [
                _resp([{"type": "text",
                        "text": "Paga aquí: https://jerarquia.com/pagos/123"}]),
                _resp([{"type": "text",
                        "text": "Mándame tus datos y te paso el link 👊"}]),
            ]
            out = llm_engine.advance(
                FakeBot(VENTA_CFG), {"history": []}, "quiero pagar",
            )
        textos = [a["payload"]["text"] for a in out["actions"] if a["type"] == "say"]
        self.assertEqual(textos, ["Mándame tus datos y te paso el link 👊"])
        self.assertEqual(mock.call_count, 2)

    def test_el_link_de_la_herramienta_si_pasa(self):
        with patch.object(llm_engine, "_invoke_model") as mock:
            def _responder(model_id, system, messages, tools):
                # 1ª ronda: llama la tool. 2ª: cita el link que ésta devolvió.
                ultimo = messages[-1]["content"]
                if isinstance(ultimo, list) and ultimo[0].get("type") == "tool_result":
                    link = ultimo[0]["content"].split("link de pago: ")[1].split(" ")[0]
                    return _resp([{"type": "text", "text": f"Págalo aquí: {link}"}])
                return _resp([_tool_use("registrar_venta", dict(DATOS_OK))],
                             stop_reason="tool_use")

            mock.side_effect = _responder
            out = llm_engine.advance(FakeBot(VENTA_CFG), {"history": []}, "mis datos")
        textos = [a["payload"]["text"] for a in out["actions"] if a["type"] == "say"]
        self.assertEqual(len(textos), 1)
        self.assertIn("/pago-demo?ref=JRQ-", textos[0])

    def test_sin_config_de_venta_el_guardarrail_no_aplica(self):
        """Otros bots (mascotas, viajes) sí escriben URLs legítimas."""
        self.assertFalse(
            llm_engine._viola_link(
                {"context_key": "gloma"}, ["mira https://glomabeauty.com"], []
            )
        )


if __name__ == "__main__":
    unittest.main()
