"""Qué pasa cuando el cliente manda algo que no es texto.

Todavía no sabemos transcribir audio ni leer imágenes. Antes eso entraba a la
conversación como un `[audio]` o un `[image]` secos: el asesor humano no sabía
qué había pasado y el bot lo leía como un tema fuera de su alcance, así que
respondía cualquier cosa o escalaba. Ahora entran como `[nota de voz]` y
`[imagen]`, y el bot tiene instrucciones de pedir con amabilidad que se lo
escriban.

Dónde vive cada regla, que no es lo mismo:
  - **Notas de voz** → `llm_engine._system_prompt`, para **todos** los bots:
    ninguno oye.
  - **Imágenes** → solo en el contexto de Arranquemos Pues
    (`bot_contexts/demo_viajes.md`). Global sería mentira: el bot de mascotas sí
    trabaja con fotos, aunque le llegan por otro camino (`_bloque_mascotas`).

Estos tests son gratis (no llaman al modelo): cubren los marcadores y que las
reglas viajen en el prompt. Que el bot *de verdad* conteste bien vive en
`tests/viajes/costo/test_guiones.py`, que sí cuesta plata.
"""
from __future__ import annotations

import pytest

from app.services import llm_engine
from app.services.messaging import twilio_adapter
from app.services.messaging.base import (
    MARCADOR_IMAGEN,
    MARCADOR_NOTA_DE_VOZ,
    es_audio,
    es_imagen,
    marcador_inbound,
)


class TestMarcador:
    @pytest.mark.parametrize("tipo", ["audio", "voice", "ptt", "AUDIO", " Voice "])
    def test_los_audios_llevan_marcador_en_español(self, tipo):
        assert es_audio(tipo)
        assert marcador_inbound(tipo) == MARCADOR_NOTA_DE_VOZ

    @pytest.mark.parametrize("tipo", ["image", "photo", "IMAGE", " imagen "])
    def test_las_fotos_llevan_marcador_en_español(self, tipo):
        assert es_imagen(tipo)
        assert marcador_inbound(tipo) == MARCADOR_IMAGEN

    @pytest.mark.parametrize("tipo", ["sticker", "document", "video"])
    def test_el_resto_conserva_el_marcador_histórico(self, tipo):
        """Solo audio e imagen cambian de forma: son los dos que el bot tiene
        que contestar. Lo demás se deja como la bandeja ya lo muestra."""
        assert not es_audio(tipo) and not es_imagen(tipo)
        assert marcador_inbound(tipo) == f"[{tipo}]"

    def test_los_marcadores_se_leen_como_lo_que_son(self):
        """Los ve el asesor en la bandeja y el bot como turno del cliente, así
        que tienen que decir qué pasó — no un `[audio]` críptico."""
        assert MARCADOR_NOTA_DE_VOZ == "[nota de voz]"
        assert MARCADOR_IMAGEN == "[imagen]"


class TestElBotDeViajesAvisaQueNoVeFotos:
    """La regla de imágenes es de este bot, no de todos."""

    def _contexto(self) -> str:
        return llm_engine._load_context("demo_viajes")

    def test_sabe_qué_significa_el_marcador(self):
        contexto = self._contexto()
        assert MARCADOR_IMAGEN in contexto
        assert "no puedo ver el contenido de las imágenes" in contexto

    def test_los_chats_viejos_con_image_también_están_cubiertos(self):
        assert "`[image]`" in self._contexto()

    def test_no_se_le_promete_al_bot_de_mascotas_que_no_ve_fotos(self):
        """El de mascotas vive de las fotos: si esta regla se hubiera puesto en
        `_system_prompt` le estaría diciendo lo contrario de lo que hace."""
        prompt = llm_engine._system_prompt(object(), {"context_key": "mascotas_cali"})
        assert MARCADOR_IMAGEN not in prompt


class TestTwilioDistingueElAdjunto:
    def _form(self, mime: str, body: str = "") -> dict:
        return {
            "MessageSid": "SM" + "0" * 30,
            "From": "whatsapp:+573001112233",
            "To": "whatsapp:+573009998877",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/media/abc",
            "MediaContentType0": mime,
            "Body": body,
        }

    def test_una_nota_de_voz_llega_como_audio(self):
        """Twilio no dice "audio": lo dice el MIME del adjunto."""
        norm = twilio_adapter.parse_inbound(self._form("audio/ogg"))
        assert norm.message_type == "audio"
        assert marcador_inbound(norm.message_type) == MARCADOR_NOTA_DE_VOZ

    def test_una_foto_llega_como_imagen(self):
        norm = twilio_adapter.parse_inbound(self._form("image/jpeg"))
        assert norm.message_type == "image"
        assert marcador_inbound(norm.message_type) == MARCADOR_IMAGEN

    def test_un_adjunto_de_otro_tipo_sigue_siendo_media(self):
        norm = twilio_adapter.parse_inbound(self._form("application/pdf"))
        assert norm.message_type == "media"

    def test_una_foto_con_texto_conserva_el_texto(self):
        """El marcador solo aplica cuando no hay nada que leer."""
        norm = twilio_adapter.parse_inbound(self._form("image/jpeg", body="miren esto"))
        assert (norm.text or marcador_inbound(norm.message_type)) == "miren esto"

    def test_un_mensaje_de_texto_no_es_media(self):
        norm = twilio_adapter.parse_inbound({
            "MessageSid": "SM" + "1" * 30,
            "From": "whatsapp:+573001112233",
            "To": "whatsapp:+573009998877",
            "NumMedia": "0",
            "Body": "hola",
        })
        assert norm.message_type == "text"


class TestLaReglaViajaEnElPrompt:
    """Vale para todos los bots LLM, no solo el de viajes: la regla vive en
    `_system_prompt`, que es lo que comparten todos."""

    def _prompt(self) -> str:
        from app.services import llm_engine

        return llm_engine._system_prompt(object(), {"context_key": "demo_viajes"})

    def test_el_bot_sabe_qué_significa_el_marcador(self):
        prompt = self._prompt()
        assert MARCADOR_NOTA_DE_VOZ in prompt
        assert "no puedes escuchar audios" in prompt

    def test_los_chats_viejos_con_audio_también_están_cubiertos(self):
        """Lo que ya está guardado en la base dice `[audio]`, no `[nota de voz]`."""
        assert "`[audio]`" in self._prompt()

    def test_la_regla_va_en_su_propia_sección(self):
        """Regresión medida, no estética: cuando esto vivía como un bullet más
        dentro de "Reglas operativas", le robaba atención a la regla de escalar
        y el bot pasó de escalar un tema ajeno 4 de 4 veces a 1 de 4. Aparte,
        cada bloque se mantiene corto y la regla de escalar queda de última."""
        prompt = self._prompt()
        reglas = prompt.split("## Reglas operativas")[1].split("##")[0]
        assert MARCADOR_NOTA_DE_VOZ not in reglas
        assert reglas.rstrip().endswith("usa `escalar_a_asesor`.")
        assert "## Notas de voz" in prompt
