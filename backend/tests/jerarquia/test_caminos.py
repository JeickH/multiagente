"""Los chips de camino del bot de Jerarquía.

`_classify_camino` es determinista y no llama al modelo: estos tests no cuestan
un centavo. Lo que fijan es que el panel del tenant diga la verdad sobre qué le
pregunta la gente — que es la métrica por la que se juzga un bot de ventas.
"""
from __future__ import annotations

from app.services import llm_engine


def camino(bot, pregunta, tools=()):
    return llm_engine._classify_camino(
        bot.cfg, pregunta, [{"tool": t} for t in tools], [], False
    )


class TestLasHerramientasSonLaDecision:
    """Cuando el turno llama una tool, esa ES la decisión: manda sobre las
    keywords de la pregunta."""

    def test_registrar_venta_marca_venta_registrada(self, bot):
        assert camino(
            bot, "Julián Restrepo, CC 1017234567, 3104567890, j@c.com, Cra 45",
            tools=["registrar_venta"],
        ) == "venta_registrada"

    def test_escalar_marca_escalar(self, bot):
        assert camino(
            bot, "¿tienen chaquetas?", tools=["escalar_a_asesor"]
        ) == "escalar_a_asesor"

    def test_despedida_marca_fin(self, bot):
        assert camino(
            bot, "listo, gracias", tools=["finalizar_conversacion"]
        ) == "fin"


class TestLaPreguntaClasificaElTurno:
    def test_precio(self, bot):
        assert camino(bot, "¿cuánto vale la promo?") == "precio"

    def test_regateo_sigue_siendo_precio(self, bot):
        assert camino(bot, "¿me las dejas más baratas?") == "precio"

    def test_tallas_y_colores(self, bot):
        assert camino(bot, "¿qué colores manejan? ¿tienen talla XL?") == "tallas_colores"

    def test_envio(self, bot):
        assert camino(bot, "¿hacen envíos a Barranquilla? ¿cuánto demora?") == "envio"

    def test_medios_de_pago(self, bot):
        assert camino(bot, "¿puedo pagar contra entrega?") == "pago"

    def test_intencion_de_compra(self, bot):
        assert camino(bot, "listo, las quiero comprar") == "venta"

    def test_cambios_y_garantia(self, bot):
        assert camino(bot, "¿y si no me sirve la talla me la cambian?") == "cambios_garantia"

    def test_otros_productos(self, bot):
        assert camino(bot, "¿tienen chaquetas o gorras?") == "otros_productos"

    def test_saludo_sin_texto(self, bot):
        assert camino(bot, None) == "saludo"


class TestPedirHumano:
    def test_pedir_una_persona_es_asesor(self, bot):
        assert camino(bot, "quiero hablar con una persona") == "asesor"

    def test_preguntar_si_es_un_bot_no_es_pedir_asesor(self, bot):
        """`asesor` por frases y no por la palabra suelta "persona" (lección
        del bot de viajes, #372)."""
        assert camino(bot, "¿tú eres una persona real o un bot?") == "respuesta_libre"


class TestConfigDelBot:
    """La config del seed es la que se despliega: si alguien la rompe, el bot
    se queda sin la herramienta de venta y nadie se entera hasta la demo."""

    def test_tiene_config_de_venta_con_link_https(self, bot):
        venta = bot.cfg["venta"]
        assert venta["prefijo"] == "JRQ"
        assert venta["link_pago"].startswith("https://")
        assert "{ref}" in venta["link_pago"]

    def test_el_bot_expone_las_tres_salidas_y_ninguna_mas(self, bot):
        nombres = {t["name"] for t in llm_engine._tools_for(bot.cfg)}
        assert nombres == {
            "registrar_venta", "escalar_a_asesor", "finalizar_conversacion",
        }

    def test_el_contexto_no_trae_datos_que_el_bot_pueda_repartir(self, bot):
        """Regla #8 (repo público) y sentido común: lo que esté escrito en el
        contexto, el bot lo puede copiar. No puede haber ni un teléfono
        marcable ni una URL — el único link que existe lo entrega
        `registrar_venta`, y el guardarraíl descarta cualquier otro."""
        texto = llm_engine._load_context(bot.cfg["context_key"])
        assert "Jerarquía" in texto and "160.000" in texto
        # Los números de los ejemplos son placeholders inequívocos.
        assert set(llm_engine._digitos_de_telefonos(texto)) <= {
            "1000000000", "3000000000",
        }
        assert "http" not in texto and "wa.me" not in texto
