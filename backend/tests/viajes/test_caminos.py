"""Los chips de camino del bot de viajes, fijados contra turnos reales.

Los casos NO son inventados: son los 25 turnos de la corrida de 10 guiones
contra producción del 2026-08-18, con el camino que *debía* haber salido. En
esa corrida cuatro de ellos salieron mal porque el medio adjunto pesaba más que
la pregunta de la persona, y el panel del tenant terminaba mintiendo sobre qué
le pregunta la gente.

Estos tests no cuestan un centavo: `_classify_camino` es determinista y no
llama al modelo.
"""
from __future__ import annotations

import pytest

from app.services import llm_engine


def camino(bot, pregunta, tools=(), media=()):
    return llm_engine._classify_camino(
        bot.cfg,
        pregunta,
        [{"tool": t} for t in tools],
        list(media),
        False,
    )


class TestLaPreguntaMandaSobreElAdjunto:
    """Los cuatro chips que salieron mal en la corrida del 2026-08-18."""

    def test_itinerario_no_es_tours_por_traer_el_video(self, bot):
        """El bot contestó el itinerario y de paso mandó el video de los tours;
        el chip decía `tours` y la persona había preguntado por el itinerario."""
        assert camino(
            bot,
            "¿Cómo es el itinerario del viaje? ¿qué hacemos cada día?",
            media=["tours", "tour_video"],
        ) == "itinerario"

    def test_el_hotel_tiene_camino_propio(self, bot):
        """`hotel_video` estaba mapeado a `precios_condiciones`, así que
        preguntar por el hotel se registraba como una consulta de precios."""
        assert camino(bot, "¿y el hotel cómo es?", media=["hotel_video"]) == "hotel"

    def test_preguntar_si_es_un_bot_no_es_pedir_asesor(self, bot):
        """`asesor` matcheaba la palabra suelta "persona"."""
        assert camino(bot, "¿tú eres una persona real o un bot?") == "respuesta_libre"

    def test_otro_destino_no_es_info_general(self, bot):
        """Caía en `info_general` por la palabra "plan", y es justo el caso que
        tiene que terminar en un asesor humano."""
        assert camino(
            bot, "¿Tienen plan a San Andrés para diciembre?", media=["info_general"]
        ) == "otros_destinos"


class TestPedirHumanoSigueSiendoAsesor:
    """Afinar las keywords no puede costarnos el caso que sí importa."""

    @pytest.mark.parametrize("frase", [
        "ok, prefiero hablar con una persona por favor",
        "quiero que me atienda un asesor",
        "¿me pueden pasar con un humano?",
        "necesito hablar con alguien de la agencia",
    ])
    def test_frases_que_piden_humano(self, bot, frase):
        assert camino(bot, frase) == "asesor"


class TestElRestoDeLaCorrida:
    """Los turnos que ya salían bien: acá para que sigan saliendo bien."""

    @pytest.mark.parametrize("pregunta,media,esperado", [
        ("Hola, soy Camilo, vi la publicidad del viaje a Coveñas, cuéntame más",
         ["info_general"], "info_general"),
        ("¿Cuánto cuesta el plan por persona?",
         ["tarifario1", "tarifario2", "tarifario3"], "precios_condiciones"),
        ("¿Qué tours incluye el plan?", ["tours", "tour_video"], "tours"),
        ("¿Cómo puedo pagar? ¿reciben PSE?", ["medios_pago"], "pagos"),
        ("¿Y puedo pagar con Nequi o contraentrega?", [], "pagos"),
        ("Hola, quiero reservar para ir con mi esposa", ["info_general"], "reserva"),
        ("¿Qué incluye el plan?", ["tours", "tour_video"], "tours"),
        ("Buenas tardes", [], "respuesta_libre"),
    ])
    def test_turno(self, bot, pregunta, media, esperado):
        assert camino(bot, pregunta, media=media) == esperado

    def test_la_herramienta_le_gana_a_todo(self, bot):
        """Si el turno escaló, el chip es `escalar_a_asesor` aunque la persona
        hubiera preguntado por precios."""
        assert camino(
            bot, "¿cuánto cuesta?", tools=["escalar_a_asesor"], media=["tarifario1"]
        ) == "escalar_a_asesor"

    def test_sin_texto_es_saludo(self, bot):
        assert camino(bot, None) == "saludo"

    def test_el_adjunto_sigue_siendo_el_desempate(self, bot):
        """Cuando la persona no dice nada clasificable, el medio enviado sigue
        siendo la mejor pista disponible."""
        assert camino(bot, "listo, muéstrame",
                      media=["tarifario_amordios_ago_nov"]) == \
            "precios_condiciones"


class TestConfigDelBot:
    """La config que este test asume es la que el seed va a escribir."""

    def test_el_hotel_apunta_a_su_propio_camino(self, bot):
        assert bot.cfg["media"]["video_amordios"]["camino"] == "hotel"

    def test_todo_camino_de_un_medio_existe_en_la_tabla(self, bot):
        """Un medio que apunte a un camino que no existe deja un chip huérfano
        en el panel, sin que nada falle."""
        declarados = {m.get("camino") for m in bot.cfg["media"].values()}
        assert declarados <= set(bot.cfg["caminos"]), (
            f"caminos declarados por medios que no están en la tabla: "
            f"{declarados - set(bot.cfg['caminos'])}"
        )
