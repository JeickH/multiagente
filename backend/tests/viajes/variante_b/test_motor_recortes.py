"""Recortes del turno (`services/recortes_turno.py`): pruebas puras, sin modelo."""
from __future__ import annotations

from app.services import llm_engine, recortes_turno as rt


def say(texto):
    return {"type": "say", "payload": {"text": texto}}


def media(url="https://x/flyer.jpeg", caption=""):
    return {"type": "say_media", "payload": {"caption": caption,
                                             "media_type": "image", "url": url}}


def tipos(actions):
    return [a["type"] for a in actions]


class TestTerminaEnPregunta:
    def test_con_emoji_y_negrilla_al_final(self):
        assert rt.termina_en_pregunta("¿Para qué mes lo estás pensando? 😊")
        assert rt.termina_en_pregunta("¿Te sirve *doble*?*")

    def test_afirmacion(self):
        assert not rt.termina_en_pregunta("Te dejo el tarifario 👇")
        assert not rt.termina_en_pregunta("¿Sabías que incluye tours? Te cuento.")


class TestUnaSolaPreguntaAlFinal:
    def test_tanda_final_queda_en_la_primera(self):
        assert rt.una_sola_pregunta_al_final(
            "Perfecto 🌴 ¿Para qué mes? ¿Y cuántas personas viajan? 😊"
        ) == "Perfecto 🌴 ¿Para qué mes? 😊"

    def test_pregunta_retorica_en_mitad_no_se_toca(self):
        texto = "¿Sabías que incluye tours? Te cuento. ¿Para qué mes?"
        assert rt.una_sola_pregunta_al_final(texto) == texto

    def test_una_sola_pregunta_no_cambia(self):
        texto = "Hola. ¿Para qué mes lo estás pensando? 😊"
        assert rt.una_sola_pregunta_al_final(texto) == texto


class TestCortarTrasPregunta:
    def test_los_textos_de_despues_se_descartan(self):
        acciones = [say("¿Cuál de las dos te funciona mejor? 🏨"),
                    say("Perfecto 🌴 Mira las opciones para septiembre 👇")]
        assert rt.cortar_tras_pregunta(acciones)
        assert acciones == [say("¿Cuál de las dos te funciona mejor? 🏨")]

    def test_los_adjuntos_de_despues_van_antes_de_la_pregunta(self):
        acciones = [say("Claro 😊"), say("¿Para qué mes?"), media(),
                    say("Ahí va"), {"type": "perfil", "payload": {"nombre": "Ana"}}]
        assert rt.cortar_tras_pregunta(acciones)
        assert tipos(acciones) == ["say", "say_media", "say", "perfil"]
        assert acciones[2]["payload"]["text"] == "¿Para qué mes?"

    def test_handoff_y_end_conservan_su_lugar(self):
        acciones = [say("¿Te paso con una asesora?"),
                    {"type": "handoff", "payload": {}}]
        assert not rt.cortar_tras_pregunta(acciones)
        assert tipos(acciones) == ["say", "handoff"]

    def test_sin_pregunta_no_hace_nada(self):
        acciones = [say("Te dejo el tarifario"), media(), say("Cualquier duda me dices")]
        copia = [dict(a) for a in acciones]
        assert not rt.cortar_tras_pregunta(acciones)
        assert acciones == copia


class TestPonerFlyer:
    ITEM = {"url": "https://x/flyer_oct.jpeg", "media_type": "image"}

    def test_un_solo_texto_corto_va_como_pie(self):
        acciones = [say("¡Hola! ¿Para qué mes lo estás pensando? 😊")]
        assert rt.poner_flyer(acciones, self.ITEM) == "pie"
        assert acciones == [{
            "type": "say_media",
            "payload": {"caption": "¡Hola! ¿Para qué mes lo estás pensando? 😊",
                        "media_type": "image", "url": self.ITEM["url"]},
        }]

    def test_texto_largo_va_aparte_antes_del_texto(self):
        largo = "x" * (rt.MAX_PIE_DE_FOTO + 1)
        acciones = [say(largo)]
        assert rt.poner_flyer(acciones, self.ITEM) == "antes"
        assert tipos(acciones) == ["say_media", "say"]

    def test_con_dos_textos_va_antes_de_la_pregunta(self):
        acciones = [say("¡Hola! Soy Luisa 🌴"), say("¿Para qué mes?")]
        assert rt.poner_flyer(acciones, self.ITEM) == "antes"
        assert tipos(acciones) == ["say", "say_media", "say"]

    def test_con_otro_adjunto_no_se_vuelve_pie(self):
        acciones = [media("https://x/otro.jpeg"), say("¿Para qué mes?")]
        assert rt.poner_flyer(acciones, self.ITEM) == "antes"
        assert tipos(acciones) == ["say_media", "say_media", "say"]

    def test_no_se_duplica(self):
        acciones = [media(self.ITEM["url"]), say("¿Para qué mes?")]
        assert rt.poner_flyer(acciones, self.ITEM) is None
        assert len(acciones) == 2

    def test_sin_url_no_hace_nada(self):
        acciones = [say("hola")]
        assert rt.poner_flyer(acciones, {"url": ""}) is None


class TestPreguntaPorElOrigenDelPrecio:
    """#21: se quita la pregunta, no la frase entera ni otras preguntas."""

    def test_caso_real_de_la_conversacion_543(self):
        texto = ("Para las salidas de lunes a jueves déjame revisar con un "
                 "compañero 🤔 ¿De dónde sacaste esa cifra?")
        salida = llm_engine._sin_pregunta_por_el_origen(texto)
        assert "sacaste" not in salida
        assert salida.startswith("Para las salidas de lunes a jueves")

    def test_otras_formas(self):
        for pregunta in ("¿Dónde lo viste?", "¿Ese precio dónde lo viste?",
                         "¿Me mandas un pantallazo del anuncio?",
                         "¿En qué publicación viste ese valor?"):
            salida = llm_engine._sin_pregunta_por_el_origen(f"Claro 😊 {pregunta}")
            assert salida == "Claro 😊", pregunta

    def test_preguntas_legitimas_no_se_tocan(self):
        for texto in ("¿Desde dónde viajan? 😊", "¿Para qué mes lo estás pensando?",
                      "¿De dónde nos escribes?", "Lo viste en el flyer, ¿cierto que sí?"):
            assert llm_engine._sin_pregunta_por_el_origen(texto) == texto, texto


class TestPideRespuesta:
    def test_pregunta_en_el_ultimo_renglon_aunque_no_cierre_con_signo(self):
        assert rt.pide_respuesta(
            "¿Cuál de las dos te funciona mejor? Y me dices si prefieres múltiple o doble 🏨")

    def test_peticion_sin_signo_al_final(self):
        assert rt.pide_respuesta("Te dejo las fechas 🌴 Me cuentas cuál te sirve")

    def test_informacion_sin_pedir_nada(self):
        assert not rt.pide_respuesta("Te dejo el tarifario 👇")
        assert not rt.pide_respuesta("¿Qué incluye? Hotel, transporte y comidas.\nTodo pago.")

    def test_corte_en_el_caso_de_la_conversacion_543(self):
        acciones = [say("¿Cuál de las dos te funciona mejor? Y me dices si prefieres múltiple o doble 🏨"),
                    say("Perfecto 🌴 Mira las opciones para septiembre 👇")]
        assert rt.cortar_tras_pregunta(acciones)
        assert len(acciones) == 1
