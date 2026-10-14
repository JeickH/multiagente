"""Smoke final contra Bedrock del bot 3 (2026-10-14), C11 r01: tres defectos de
presentación multi-ronda, con los textos reales de la transcripción
(`entregables/transcripciones_c/2026-10-14/smoke_final/C11_tarjeta__r01.txt`).
"""
from __future__ import annotations

from app.services import recortes_turno
from tests.viajes.variante_c.test_motor_embudo import (  # noqa: F401 (fixture)
    Bot, dichos, dobles, estado, herramienta, jugar, resp, texto, tipos,
)

PREGUNTA_T1 = ("¡Qué bien! 🙌 Para apartar tu cupo necesito que confirmes:\n\n"
               "¿Viajan *2 personas adultas* o hay *niños* en el grupo?")
OPCIONES_T1 = "1️⃣ 2 adultos, sin niños\n2️⃣ Viajan niños con nosotros 👧"
SOLA_T2 = "¡Perfecto! ¿Cuántos adultos van y cuál es la edad de cada niño? 👇"
CON_OPCIONES_T2 = ("¿Cuántos *adultos* van y cuál es la edad de cada *niño*? 👇\n\n"
                   "1️⃣ 1 adulto\n2️⃣ 2 adultos\n3️⃣ 3 adultos\n4️⃣ 4 o más")
NARRACION_T0 = ("¡Buenos días! 👋 Soy *Luisa*, de *Arranquemos Pues* 🌴\n\n"
                "Te veo decidido. Antes de apartar tu cupo, déjame consultar los precios "
                "de esa fecha para darte el valor exacto.")


class TestBurbujaDuplicada:
    def test_queda_solo_la_que_trae_opciones(self):
        salida, _ = jugar(Bot(unir_opciones=True), [
            resp(texto(SOLA_T2), herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto(CON_OPCIONES_T2)),
        ], mensaje="2", estado=estado(("hola", "¡Hola!")))
        assert dichos(salida) == [CON_OPCIONES_T2]

    def test_si_a_la_otra_le_queda_algo_que_decir_se_conserva(self):
        acciones = [
            {"type": "say", "payload": {"text": "Te cuento que el plan incluye desayuno y cena. "
                                                "¿Cuántos adultos van?"}},
            {"type": "say", "payload": {"text": "¿Cuántos *adultos* van? 👇\n1️⃣ 1\n2️⃣ 2"}},
        ]
        assert recortes_turno.sin_pregunta_repetida(acciones)
        assert acciones[0]["payload"]["text"] == "Te cuento que el plan incluye desayuno y cena."

    def test_sin_flag(self):
        salida, _ = jugar(Bot(), [
            resp(texto(SOLA_T2), herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto(CON_OPCIONES_T2)),
        ], mensaje="2", estado=estado(("hola", "¡Hola!")))
        assert len(dichos(salida)) == 2


class TestOpcionesDeOtraRonda:
    def test_se_unen_aunque_haya_un_perfil_en_medio(self):
        salida, _ = jugar(Bot(unir_opciones=True, recordar_nombre=True), [
            resp(texto(PREGUNTA_T1), herramienta("registrar_nombre", {"nombre": "Laura"})),
            resp(texto(OPCIONES_T1)),
        ], mensaje="Laura Restrepo Gil, CC 1234567", estado=estado(("hola", "¡Hola!")))
        assert dichos(salida) == [PREGUNTA_T1 + "\n" + OPCIONES_T1]
        assert "perfil" in tipos(salida)

    def test_un_adjunto_en_medio_si_separa(self):
        acciones = [
            {"type": "say", "payload": {"text": "¿Te sirve? 👇"}},
            {"type": "say_media", "payload": {"url": "https://x/flyer.jpeg"}},
            {"type": "say", "payload": {"text": "1️⃣ Sí\n2️⃣ No"}},
        ]
        assert not recortes_turno.unir_opciones(acciones)


class TestNarracionAMitad:
    def test_cierre_de_parrafo_en_ronda_de_consulta(self):
        assert recortes_turno.sin_narracion(NARRACION_T0, solo_bordes=True, ronda_consulta=True) == (
            "¡Buenos días! 👋 Soy *Luisa*, de *Arranquemos Pues* 🌴\n\nTe veo decidido.")

    def test_en_el_turno(self):
        salida, _ = jugar(Bot(recortar_narracion=True), [
            resp(texto(NARRACION_T0), herramienta("consultar_tarifario", {"mes": "octubre"})),
            resp(texto("Para *2 personas* del *23 al 26*: *$918.000 total* 👇\n1️⃣ Sí\n2️⃣ No")),
        ], mensaje="quiero reservar la del 23 al 26")
        assert not any("déjame consultar" in d for d in dichos(salida))

    def test_fuera_de_una_ronda_de_consulta_la_frase_del_medio_se_queda(self):
        frase = "Te cuento: para apartar, déjame consultar con tu cupo. ¿Seguimos?"
        assert recortes_turno.sin_narracion(frase, solo_bordes=True) == frase

    def test_narracion_que_cierra_un_parrafo(self):
        assert recortes_turno.sin_narracion(
            "Mira, en octubre tenemos 4 salidas. Un momento.\n\n¿Cuál te sirve? 👇",
            solo_bordes=True) == "Mira, en octubre tenemos 4 salidas.\n\n¿Cuál te sirve? 👇"


# ---------------------------------------------------------------------------
# smoke_final2 — `medios_pago` después de las opciones (r01) o entre la
# pregunta y las opciones (r02)
# ---------------------------------------------------------------------------

PAGO = ("¡Listo, recibí tus datos! ✅ El anticipo para apartar tu cupo es *$275.400* 💳\n"
        "Con el anticipo queda apartado tu cupo, y un compañero te confirma la reserva al "
        "verificar el pago.")
OPCIONES_PAGO = ("1️⃣ Transferencia o llave Bre-B\n2️⃣ Tarjeta de crédito o débito\n"
                 "3️⃣ En la oficina\n4️⃣ Crédito Fácil Codensa")


def _media(salida):
    return [a["type"] for a in salida["actions"] if a["type"] in ("say", "say_media")]


class TestAdjuntosAntesDeLaPregunta:
    def test_r01_media_despues_de_las_opciones(self):
        salida, _ = jugar(Bot(unir_opciones=True), [
            resp(texto(f"{PAGO}\n¿Cómo vas a pagar? 👇\n{OPCIONES_PAGO}"),
                 herramienta("enviar_media", {"claves": ["medios_pago"]})),
            resp(),
        ], mensaje="Laura Restrepo Gil, CC 1234567", estado=estado(("hola", "¡Hola!")))
        assert _media(salida) == ["say_media", "say"]

    def test_r02_media_entre_la_pregunta_y_las_opciones(self):
        salida, _ = jugar(Bot(unir_opciones=True), [
            resp(texto(f"{PAGO}\n\n¿Cómo vas a pagar? 👇"),
                 herramienta("enviar_media", {"claves": ["medios_pago"]})),
            resp(texto(OPCIONES_PAGO)),
        ], mensaje="Laura Restrepo Gil, CC 1234567", estado=estado(("hola", "¡Hola!")))
        assert _media(salida) == ["say_media", "say"]
        assert dichos(salida) == [f"{PAGO}\n\n¿Cómo vas a pagar? 👇\n{OPCIONES_PAGO}"]

    def test_los_adjuntos_que_ya_iban_antes_no_se_mueven_y_se_conserva_el_orden(self):
        acciones = [
            {"type": "say_media", "payload": {"url": "https://x/a.jpeg"}},
            {"type": "say", "payload": {"text": "Te cuento del plan 🌴"}},
            {"type": "say", "payload": {"text": "¿Cuál te sirve? 👇\n1️⃣ Sí\n2️⃣ No"}},
            {"type": "say_media", "payload": {"url": "https://x/b.jpeg"}},
            {"type": "say_media", "payload": {"url": "https://x/c.jpeg"}},
            {"type": "handoff", "payload": {}},
        ]
        assert recortes_turno.adjuntos_antes_de_la_pregunta(acciones)
        assert [a["payload"].get("url") or a["type"] for a in acciones] == [
            "https://x/a.jpeg", "say", "https://x/b.jpeg", "https://x/c.jpeg", "say", "handoff"]

    def test_sin_flag_queda_como_hoy(self):
        salida, _ = jugar(Bot(), [
            resp(texto(f"{PAGO}\n\n¿Cómo vas a pagar? 👇"),
                 herramienta("enviar_media", {"claves": ["medios_pago"]})),
            resp(texto(OPCIONES_PAGO)),
        ], mensaje="Laura Restrepo Gil, CC 1234567", estado=estado(("hola", "¡Hola!")))
        assert _media(salida) == ["say", "say_media", "say"]
