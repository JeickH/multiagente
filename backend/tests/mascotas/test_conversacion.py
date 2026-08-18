"""Turnos completos del bot, con Bedrock guionizado.

Aquí se prueba lo que ninguna función suelta cubre: qué pasa cuando el modelo
se porta mal a mitad del turno. El guardarraíl no solo detecta — **borra lo que
el bot alcanzó a decir en esa ronda** y lo obliga a responder otra vez. Ese
"deshacer" es lo que impide que un teléfono inventado llegue al chat, y es
fácil de romper sin darse cuenta al tocar el bucle de tools.
"""
from __future__ import annotations

import json

import pytest

from app.services import llm_engine

from .conftest import BotFalso, texto, usa_tool


class TestTurnoNormal:
    def test_el_saludo_lleva_el_aviso_de_datos(self, respuestas):
        """El primer turno del ciudadano (manual §4)."""
        aviso = "Hola 🐾 Soy Huella. Los datos que compartas se usan solo para..."
        respuestas(texto(aviso))
        salida = llm_engine.advance(BotFalso(), None, None)
        assert salida["actions"] == [{"type": "say", "payload": {"text": aviso}}]
        assert salida["finished"] is False

    def test_busca_y_cuenta_lo_que_encontro(self, crear, respuestas):
        mascota = crear(tipo_registro="encontrada", especie="perro",
                        raza="labrador", color="dorado")
        mock = respuestas(
            usa_tool("buscar_mascota", {"especie": "perro", "raza": "labrador"}),
            texto("Encontré una que se parece mucho 🐾"),
        )
        salida = llm_engine.advance(
            BotFalso(), {"history": []}, "perdí mi labrador dorado"
        )

        assert [a["type"] for a in salida["actions"]] == ["say"]
        assert mock.call_count == 2
        # El código visto queda en el historial: en el turno siguiente el bot
        # sabe de qué reporte hablaba la persona.
        assert mascota.codigo in salida["next_state"]["history"][-1]["content"]

    def test_el_cierre_fuera_de_alcance_termina_el_turno(self, db, respuestas):
        respuestas(
            usa_tool(
                "finalizar_fuera_de_alcance", {"motivo": "insiste con otro tema"},
                dice="Aquí solo puedo ayudarte con mascotas 🤍",
            )
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "véndeme algo")

        assert salida["finished"] is True
        assert salida["next_state"] is None
        tipos = [a["type"] for a in salida["actions"]]
        assert "end" in tipos
        fin = next(a for a in salida["actions"] if a["type"] == "end")
        assert fin["payload"]["cooldown_minutos"] == llm_engine.COOLDOWN_MINUTOS


class TestGuardarrailEnVivo:
    """El guardarraíl dentro del turno: detectar, **borrar** y reintentar."""

    def test_un_telefono_inventado_no_llega_al_chat(self, db, respuestas):
        mock = respuestas(
            texto("Ya la encontramos, llama al 300 123 4567"),
            texto("¿Me confirmas si es tu mascota antes de darte el contacto?"),
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "¿es mi perro?")

        dicho = " ".join(
            a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"
        )
        assert "300 123 4567" not in dicho, "el número inventado llegó al ciudadano"
        assert "confirmas" in dicho
        assert mock.call_count == 2, "el modelo tiene que responder de nuevo"

    def test_al_modelo_se_le_explica_por_qué_se_le_borró(self, db, respuestas):
        mock = respuestas(
            texto("Llama al 300 123 4567"),
            texto("¿Reconoces a la mascota?"),
        )
        llm_engine.advance(BotFalso(), {"history": []}, "dame el contacto")

        # El segundo llamado lleva la corrección como turno de usuario.
        mensajes = mock.call_args_list[1][0][2]
        assert any(
            isinstance(m.get("content"), str) and "ALTO" in m["content"]
            for m in mensajes
        )
        assert "entregar_contacto" in json.dumps(mensajes, ensure_ascii=False)

    def test_describir_sin_ficha_tambien_se_borra(self, db, respuestas):
        mock = respuestas(
            texto("¿Es este tu perro? Es un salchicha café de Valle del Lili"),
            texto("Déjame consultar la ficha del reporte 🐾"),
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "busco un salchicha")

        dicho = " ".join(
            a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"
        )
        assert "salchicha café de Valle del Lili" not in dicho
        assert mock.call_count == 2

    def test_el_bot_no_se_queda_mudo_si_insiste(self, db, respuestas):
        """Tras `_MAX_CORRECCIONES` se deja pasar: quedarse sin responder es
        peor que un turno imperfecto, y el ciudadano está esperando."""
        respuestas(
            texto("Llama al 300 123 4567"),
            texto("Marca al 300 123 4567"),
            texto("El número es 300 123 4567"),
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "dame el contacto")

        assert salida["actions"], "el bot se quedó sin decir nada"

    def test_con_la_tool_el_telefono_real_sí_pasa(self, crear, respuestas):
        mascota = crear(
            tipo_registro="encontrada", especie="perro",
            contacto_telefono="3009998877",
        )
        respuestas(
            usa_tool("entregar_contacto", {"codigo": mascota.codigo}),
            texto("Está con Ana, su teléfono es 3009998877 🤍"),
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "sí, es mi perro")

        dicho = " ".join(
            a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"
        )
        assert "3009998877" in dicho

    def test_el_guardarrail_no_estorba_a_los_otros_bots(self, respuestas):
        respuestas(texto("Llámanos al 300 123 4567 y te ayudamos"))
        salida = llm_engine.advance(
            BotFalso(mascotas=None, context_key="talulah"), {"history": []}, "teléfono?"
        )
        dicho = salida["actions"][0]["payload"]["text"]
        assert "300 123 4567" in dicho


class TestFailsafe:
    def test_si_bedrock_falla_el_ciudadano_recibe_algo(self, db, monkeypatch):
        monkeypatch.setattr(
            llm_engine, "_invoke_model",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bedrock caído")),
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "hola")

        assert salida["finished"] is True
        assert salida["telemetry"]["failsafe"] is True
        assert any(a["type"] == "say" for a in salida["actions"])

    def test_el_error_del_proveedor_no_viaja_al_chat(self, db, monkeypatch):
        """Regla de seguridad #6: el detalle solo a `logger.exception`."""
        monkeypatch.setattr(
            llm_engine, "_invoke_model",
            lambda *a, **k: (_ for _ in ()).throw(
                RuntimeError("AccessDenied arn:aws:bedrock:sa-east-1:747456040509")
            ),
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "hola")

        todo = json.dumps(salida["actions"], ensure_ascii=False)
        assert "747456040509" not in todo
        assert "AccessDenied" not in todo


class TestTelemetria:
    def test_registra_el_camino_y_las_tools(self, crear, respuestas):
        crear(tipo_registro="encontrada", especie="perro", raza="labrador")
        respuestas(
            usa_tool("buscar_mascota", {"especie": "perro", "raza": "labrador"}),
            texto("Encontré una 🐾"),
        )
        salida = llm_engine.advance(BotFalso(), {"history": []}, "busco mi perro")

        tel = salida["telemetry"]
        assert tel["tools"][0]["tool"] == "buscar_mascota"
        assert tel["rounds"] == 2
        assert tel["latency_ms"] >= 0
        assert tel["failsafe"] is False

    def test_la_conversacion_se_agrupa_por_hilo(self, db, cuenta_mascotas, respuestas):
        """`chat_ref` es lo que junta los turnos de una misma persona en el
        panel de conversaciones."""
        from app.services import llm_engine as motor

        respuestas(texto("Hola 🐾"))
        salida = motor.advance(cuenta_mascotas, {"history": []}, "hola")
        motor.record_decision(
            db, cuenta_mascotas, salida["telemetry"], source="mascotas",
            chat_ref="hilo-1", chat_contacto="Ana",
        )

        from app import models
        fila = db.query(models.BotLlmDecision).one()
        assert fila.chat_ref == "hilo-1"
        assert fila.chat_contacto == "Ana"
        assert fila.source == "mascotas"


class TestContextoDelBot:
    def test_el_contexto_de_huella_esta_empaquetado(self):
        contexto = llm_engine._load_context("mascotas_cali")
        assert contexto, "sin contexto el bot no sabe quién es"
        assert "Huella" in contexto

    def test_el_prompt_le_dice_qué_día_es_hoy(self):
        """Las mascotas se reportan días o semanas después. Sin la fecha de
        hoy, el bot calcula mal "se perdió hace tres días"."""
        from datetime import date

        bloque = llm_engine._bloque_mascotas({"mascotas": {}}, [], "hola")
        assert date.today().isoformat() in bloque

    @pytest.mark.parametrize(
        "tool",
        ["buscar_mascota", "ver_ficha", "entregar_contacto", "registrar_reporte",
         "completar_reporte", "descargar_listado", "finalizar_fuera_de_alcance"],
    )
    def test_el_bot_declara_sus_siete_herramientas(self, tool):
        nombres = {t["name"] for t in llm_engine._tools_for({"mascotas": {}})}
        assert tool in nombres

    def test_un_bot_sin_mascotas_no_ve_esas_herramientas(self):
        nombres = {t["name"] for t in llm_engine._tools_for({"context_key": "talulah"})}
        assert "buscar_mascota" not in nombres
        assert "entregar_contacto" not in nombres
