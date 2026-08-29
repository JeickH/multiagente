"""La palabra "seña" no se dice en Colombia (29-ago-2026).

Pedido del CEO: el dato es correcto —el cupo se aparta con el 30%— pero el bot
lo estaba llamando *una seña del 30%*, y aquí esa palabra no se entiende. Va
*anticipo*, *adelanto* o *cuota inicial*.

Lo particular de este caso, y por lo que hay dos arreglos y no uno: **la palabra
nunca estuvo en el prompt**. El documento siempre dijo "se aparta el cupo con el
30%"; "seña" la elige el modelo por su cuenta, porque es la palabra de otros
países para el pago inicial. Contra eso el prompt sirve —no hay ninguna regla
rival empujando en la otra dirección, que es cuando insistir no sirve de nada—
pero no es determinista, y una palabra que se escapa una vez de cada veinte
igual le llega a un cliente. Así que:

1. El documento la prohíbe por su nombre y modela la frase buena.
2. `llm_engine._con_reemplazos` la cambia a la salida, que es por donde pasan
   los tres canales.

Se afirma sobre el prompt renderizado y sobre el filtro, que son deterministas
y no cuestan un centavo. Que no llegue al cliente en una conversación de verdad
lo vigila el guardarraíl global de `costo/test_guiones.py`.
"""
from __future__ import annotations

import re

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine


def _prompt(bot) -> str:
    return llm_engine._system_prompt(bot, llm_engine.config_de(bot))


def _plano(texto: str) -> str:
    """Colapsa saltos de línea: una frase partida a 79 columnas debe matchear."""
    return re.sub(r"\s+", " ", texto)


# El mismo criterio del guardarraíl: la palabra suelta, no "diseña" ni "señor".
_SENA = re.compile(r"\bseñas?\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# El documento
# ---------------------------------------------------------------------------

class TestElPromptProhibeLaPalabra:
    def test_la_nombra_para_prohibirla(self, bot):
        """No alcanza con escribir bien la frase buena: el modelo no la estaba
        copiando de ningún lado, la ponía él. Hay que decirle cuál es la palabra
        que no se usa."""
        texto = _plano(_prompt(bot))
        assert "hay una palabra prohibida: *seña*" in texto

    @pytest.mark.parametrize("alternativa", ["anticipo", "adelanto", "cuota inicial"])
    def test_le_da_las_tres_alternativas(self, bot, alternativa):
        """Las tres que el CEO dio por buenas. Prohibir sin ofrecer reemplazo
        deja al modelo eligiendo solo, que es como llegamos aquí."""
        assert alternativa in _plano(_prompt(bot))

    def test_dice_que_es_por_colombia(self, bot):
        """El *por qué* es lo que hace que la regla aguante en un caso que no
        está escrito: sin él, "seña" cae pero "abono de arras" no."""
        assert "Escribes para Colombia" in _plano(_prompt(bot))

    def test_la_condicion_de_reserva_usa_la_palabra_buena(self, bot):
        """Donde vive el dato, para que la frase correcta esté a la mano en el
        turno en que la va a decir."""
        texto = _plano(_prompt(bot))
        assert "anticipo del 30% del valor total por persona" in texto

    def test_el_ejemplo_del_regateo_tambien(self, bot):
        """Es el turno donde más sale el 30%: "¿me lo dejas más barato?" →
        "el precio es el de los tarifarios, pero apartas con el 30%"."""
        assert "apartas el cupo con un *anticipo del 30%*" in _plano(_prompt(bot))

    def test_no_quedo_una_sola_ocurrencia_suelta(self, bot):
        """Las únicas apariciones legítimas son las que la prohíben. Una frase
        del tipo "se aparta con una seña" en cualquier otra sección le daría al
        modelo permiso para copiarla."""
        texto = _plano(_prompt(bot))
        sospechosas = [
            m.start() for m in _SENA.finditer(texto)
            if "prohibida" not in texto[max(0, m.start() - 120):m.start()]
            and "nunca" not in texto[max(0, m.start() - 40):m.start()].lower()
        ]
        assert not sospechosas, f"«seña» usada como vocabulario propio: {sospechosas}"


# ---------------------------------------------------------------------------
# El filtro de salida
# ---------------------------------------------------------------------------

class TestElFiltroCambiaLaPalabra:
    @pytest.mark.parametrize("dicho,esperado", [
        ("Apartas tu cupo con una seña del 30% 🌴",
         "Apartas tu cupo con una cuota inicial del 30% 🌴"),
        ("La seña es del *30%* del valor por persona.",
         "La cuota inicial es del *30%* del valor por persona."),
        ("Seña del 30% y el resto 8 días antes.",
         "Cuota inicial del 30% y el resto 8 días antes."),
        ("Se pagan dos señas.", "Se pagan dos cuotas iniciales."),
        ("SEÑA del 30%", "Cuota inicial del 30%"),
    ])
    def test_reemplaza(self, bot, dicho, esperado):
        assert llm_engine._con_reemplazos(dicho, bot.cfg) == esperado

    def test_la_concordancia_queda_bien(self, bot):
        """Por esto el reemplazo es *cuota inicial* y no *anticipo*: hereda el
        artículo que el modelo ya escribió, y "seña" es femenino. Con "anticipo"
        saldría "una anticipo del 30%", que es peor que el problema original."""
        salida = llm_engine._con_reemplazos("con una seña del 30%", bot.cfg)
        assert "una anticipo" not in salida
        assert salida == "con una cuota inicial del 30%"

    @pytest.mark.parametrize("texto", [
        "El señor Carlos ya reservó.",
        "Te doy una señal cuando salga el bus.",
        "Así se diseña el plan.",
        "Enseñamos el itinerario completo.",
    ])
    def test_no_toca_palabras_que_solo_empiezan_igual(self, bot, texto):
        assert llm_engine._con_reemplazos(texto, bot.cfg) == texto

    def test_sin_el_mapa_no_hace_nada(self):
        """`llm_engine` lo comparten mascotas, Gloma y Jerarquía. Para el bot de
        mascotas "señas particulares" es vocabulario central —el campo donde
        guarda el collar azul y la mancha en la pata—: si este reemplazo fuera
        global, le rompería las descripciones de las mascotas perdidas."""
        texto = "La encontré con un collar azul, esas son las señas."
        assert llm_engine._con_reemplazos(texto, {}) == texto
        assert llm_engine._con_reemplazos(texto, {"context_key": "mascotas_cali"}) == texto

    def test_el_mapa_es_el_del_bot_de_verdad(self):
        """La config no se copia en el test: se importa de `app/data/bot_viajes.py`,
        que es lo que el actualizador escribe en RDS."""
        assert LLM_CONFIG["reemplazos"]["seña"] == "cuota inicial"
        assert LLM_CONFIG["reemplazos"]["señas"] == "cuotas iniciales"


class TestElVoseoVuelveATuteo:
    """El otro desliz del mismo mensaje de producción: "el resto lo *pagás*".

    Y ojo con el diagnóstico, que es distinto al de "seña": el voseo paisa es
    español legítimo, y de Medellín, que es donde queda la agencia. Lo que no se
    puede es mezclarlo con el tuteo en el mismo mensaje. El documento ya eligió
    ("Trata de «tú»"), así que esto no agrega una regla: hace determinista una
    que ya existía y que el modelo se saltaba 2 veces de cada 2.675.
    """

    @pytest.mark.parametrize("dicho,esperado", [
        ("El resto lo pagás 8 días antes.", "El resto lo pagas 8 días antes."),
        ("¿Querés que te mande el tarifario?", "¿Quieres que te mande el tarifario?"),
        ("Si tenés dudas me escribís.", "Si tienes dudas me escribís."),
        ("Vos elegís el hotel.", "Tú elegís el hotel."),
    ])
    def test_reemplaza_las_formas_listadas(self, bot, dicho, esperado):
        """"Escribís" y "elegís" no están en el mapa a propósito: la lista es
        corta y explícita, no un intento de conjugar el idioma entero."""
        assert llm_engine._con_reemplazos(dicho, bot.cfg) == esperado

    def test_no_le_cambia_el_nombre_a_un_cliente_que_se_llame_tomas(self, bot):
        """Por esto "tomás" no está en el mapa aunque sea voseo de manual: el
        bot llama a la gente por su nombre en casi todos los mensajes, y
        "¡Listo, tomas!" es peor que cualquier voseo."""
        dicho = "¡Perfecto, Tomás! 🙌 Ya quedó apartado tu cupo."
        assert llm_engine._con_reemplazos(dicho, bot.cfg) == dicho

    def test_no_toca_el_tuteo_que_ya_estaba_bien(self, bot):
        dicho = "Ya tienes tu cupo, pagas el saldo 8 días antes y estás listo 🙌"
        assert llm_engine._con_reemplazos(dicho, bot.cfg) == dicho
