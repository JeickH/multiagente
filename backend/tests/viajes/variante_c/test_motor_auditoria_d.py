"""Auditoría del delta del bot 3 (D1, D2) y verificación contra Bedrock (R1, R3,
C10, enmascarado de montos). D2 y C10 viven en `test_motor_qa_c.py` y
`test_motor_embudo.py`; aquí, lo demás. Sin datos reales.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine, recortes_turno, tarifario

GUION = (Path(llm_engine.__file__).resolve().parent.parent / "bot_contexts"
         / "demo_viajes_c.md").read_text(encoding="utf-8")


class Bot:
    id = 80
    engine = "llm"
    status = "active"

    def __init__(self, **flags):
        self.llm_config = json.dumps({**LLM_CONFIG, **flags}, ensure_ascii=False)


def texto(t):
    return {"type": "text", "text": t}


def resp(*bloques):
    con_tool = any(b["type"] == "tool_use" for b in bloques)
    return {"content": list(bloques), "stop_reason": "tool_use" if con_tool else "end_turn"}


def jugar(bot, respuestas, mensaje="ok", estado=None, **runtime):
    with patch.object(llm_engine, "_invoke_model", side_effect=list(respuestas)) as mock:
        salida = llm_engine.advance(bot, estado, mensaje, runtime=dict(runtime))
    return salida, mock


def dichos(salida):
    return [a["payload"]["text"] for a in salida["actions"] if a["type"] == "say"]


def _secciones(nivel: str):
    """{título: cuerpo} de las secciones `### /…` (o `## …`) del guion."""
    partes = re.split(rf"^{nivel} ", GUION, flags=re.M)[1:]
    return {p.split("\n", 1)[0].strip(): p.split("\n", 1)[1] for p in partes}


def _literales(cuerpo: str):
    """Los renglones que el bot reproduce: ni viñetas ni su continuación."""
    for linea in cuerpo.split("\n"):
        if not linea.strip() or linea.startswith(("-", "  ", "#")):
            continue
        yield linea


# ---------------------------------------------------------------------------
# D1 — `_PROMESA_RE` no dispara con el propio guion ni con frases normales
# ---------------------------------------------------------------------------

class TestD1Promesa:
    def test_cada_bloque_literal_del_guion(self):
        """Todo lo que el bot dice tal cual, salvo /asesor (que escala en el
        mismo turno), no es una promesa sin escalar."""
        bloques = {k: v for k, v in _secciones("###").items() if k.startswith("/")}
        assert "/pago" in bloques and "/apartar" in bloques
        for nombre, cuerpo in bloques.items():
            if nombre == "/asesor":
                continue
            for linea in _literales(cuerpo):
                for etapa in (None, "reserva", "pago"):
                    assert not recortes_turno.promete_respuesta_de_otro(linea, etapa=etapa), (
                        nombre, linea)

    def test_conocimiento_del_plan_y_comprobante(self):
        secciones = _secciones("##")
        for titulo in ("Conocimiento del plan Tolú & Coveñas", "El comprobante"):
            for linea in _literales(secciones[titulo]):
                assert not recortes_turno.promete_respuesta_de_otro(linea), (titulo, linea)
        assert "te lo confirma un compañero" not in GUION

    @pytest.mark.parametrize("frase", [
        "Nuestro equipo te ayuda a elegir la mejor fecha",
        "el equipo te escribe para recordártelo",
        "Tu asesora te pasa el itinerario el día antes",
        "Nuestro equipo de guías te cuenta todo en el bus",
        "Con el anticipo queda apartado tu cupo, y un compañero te confirma la reserva al verificar el pago.",
        "¡Gracias! 🙌 Un compañero verifica el pago y te confirma la reserva por aquí",
    ])
    def test_frases_normales(self, frase):
        assert not recortes_turno.promete_respuesta_de_otro(frase)

    @pytest.mark.parametrize("frase", [
        "Eso lo confirmo con un compañero para darte el dato exacto 🙌",
        "Esos detalles del bus te los confirma un compañero.",
        "Un compañero te confirma si el bus tiene baño",
        "el valor exacto te lo confirma un compañero",
    ])
    def test_las_promesas_de_verdad(self, frase):
        assert recortes_turno.promete_respuesta_de_otro(frase)

    def test_en_reserva_o_pago_hablar_del_cupo_no_es_promesa(self):
        frase = "Un compañero te confirma el cupo apenas llegue el anticipo"
        assert not recortes_turno.promete_respuesta_de_otro(frase, etapa="pago")

    def test_pago_en_el_turno_no_corrige_ni_traspasa(self):
        pago = ("¡Listo, recibí tus datos! ✅ El anticipo para apartar tu cupo es *$330.000* 💳\n"
                "Con el anticipo queda apartado tu cupo, y un compañero te confirma la reserva "
                "al verificar el pago.\n¿Cómo vas a pagar? 👇\n1️⃣ Transferencia\n2️⃣ Tarjeta")
        salida, mock = jugar(Bot(escalar_si_promete=True), [resp(texto(pago))],
                             mensaje="Ana Pérez, CC 1234567",
                             estado={"history": [{"role": "user", "content": "1"},
                                                 {"role": "assistant", "content": "Tus datos"}],
                                     "etapa": "reserva"})
        assert mock.call_count == 1
        assert "handoff" not in [a["type"] for a in salida["actions"]]


# ---------------------------------------------------------------------------
# R1 — meta-texto tras CUALQUIER corrección
# ---------------------------------------------------------------------------

class TestR1MetaTexto:
    @pytest.mark.parametrize("meta,limpio", [
        ("Tienes razón. Reescribiendo:\n\n¡Listo, recibí tus datos! ✅", "¡Listo, recibí tus datos! ✅"),
        ("Déjame corregir: no debería haber prometido eso. ¿Cómo vas a pagar? 👇",
         "¿Cómo vas a pagar? 👇"),
        ("Como te decía, el plan incluye desayuno. ¿Seguimos?",
         "El plan incluye desayuno. ¿Seguimos?"),
        ("Voy a hacerlo ahora. Total $918.000", "Total $918.000"),
        ("Corrijo: son 2 noches. ¿Seguimos?", "Son 2 noches. ¿Seguimos?"),
    ])
    def test_tras_correccion(self, meta, limpio):
        assert recortes_turno.sin_narracion(
            recortes_turno.sin_disculpa_inicial(meta), solo_bordes=False) == limpio

    def test_en_el_turno(self):
        salida, _ = jugar(Bot(recortar_narracion=True, correcciones_silenciosas=True,
                              opciones_cerradas=True), [
            resp(texto("¿Para qué mes lo estás pensando?")),
            resp(texto("Tienes razón. Reescribiendo:\n\n¿Para qué mes? 👇\n1️⃣ Octubre\n2️⃣ Noviembre")),
        ], estado={"history": [{"role": "user", "content": "hola"},
                               {"role": "assistant", "content": "¡Hola!"}]})
        assert dichos(salida) == ["¿Para qué mes? 👇\n1️⃣ Octubre\n2️⃣ Noviembre"]

    def test_sin_correccion_reescribir_no_se_toca_en_mitad(self):
        texto_ = "Te ayudo a reescribir la fecha si te equivocaste 😊 ¿Seguimos?"
        assert recortes_turno.sin_narracion(texto_, solo_bordes=True) == texto_


# ---------------------------------------------------------------------------
# R3 — menú de edades de niños desde los extras
# ---------------------------------------------------------------------------

class TestR3EdadesNinos:
    def _system(self, bot):
        cfg = {**llm_engine.config_de(bot), "_runtime": {}}
        return llm_engine._system_prompt(bot, cfg, [])

    def test_el_menu_sale_de_los_extras(self, monkeypatch):
        monkeypatch.setattr(tarifario, "extras", lambda: {"ninos": [
            {"edad_min": 3, "edad_max": 4, "etiqueta": "De 3 a 4 años"},
            {"edad_min": 0, "edad_max": 2, "etiqueta": "Menores de 2 años"},
        ]})
        system = self._system(Bot(menu_edades_ninos=True))
        assert ("## Edades de niños (datos del sistema)" in system and
                "1️⃣ Menores de 2 años\n2️⃣ De 3 a 4 años\n3️⃣ Paga el plan completo (desde 5 años)"
                in system)
        assert system.index("Edades de niños") < system.index("## Qué día es hoy")

    def test_con_los_extras_reales(self):
        assert "Paga el plan completo (desde 5 años)" in llm_engine._bloque_edades_ninos({})

    def test_sin_tramos_no_hay_bloque(self, monkeypatch):
        monkeypatch.setattr(tarifario, "extras", lambda: {})
        assert "Edades de niños" not in self._system(Bot(menu_edades_ninos=True))

    def test_sin_flag(self):
        assert "Edades de niños" not in self._system(Bot())


# ---------------------------------------------------------------------------
# Enmascarado de `registrar_intencion`: los montos no son datos personales
# ---------------------------------------------------------------------------

def test_los_montos_no_se_tapan_y_las_cedulas_si():
    limpio, _ = llm_engine._intencion_limpia({
        "tipo": "datos",
        "resumen": "Ana, CC 1234567, cel 300 000 0011. Total $1.100.000, anticipo $ 330.000",
    })
    assert limpio["resumen"] == (
        "Ana, CC [número], cel [número]. Total $1.100.000, anticipo $ 330.000")


@pytest.mark.parametrize("texto", [
    "C.C.1000000011", "cc.1000000011", "Cel.3000000011", "No.1000000011",
    "ced.1.000.000.011", "Tel.300 000 0011", "$1000000011", "$ 3000000011",
    "cédula $1.000.000.011", "+57 300 000 0011",
])
def test_cedulas_y_telefonos_se_tapan_en_cualquier_formato(texto):
    """Auditoría E1: el cambio que respeta los montos no puede destapar
    cédulas ni teléfonos escritos de forma común (ni con «$» delante)."""
    limpio, _ = llm_engine._intencion_limpia({"tipo": "datos", "resumen": f"Ana, {texto}"})
    assert not re.search(r"\d{4}", limpio["resumen"]), limpio["resumen"]


@pytest.mark.parametrize("monto", ["$1.100.000", "$ 459.000", "$999.999.999", "$918,000"])
def test_los_montos_con_forma_de_plata_se_respetan(monto):
    limpio, _ = llm_engine._intencion_limpia({"tipo": "datos", "resumen": f"Total {monto}"})
    assert limpio["resumen"] == f"Total {monto}"


def test_tapar_series_es_lineal():
    import time
    for t in ("9" * 20000, "$1." * 7000, "$" + "1.000" * 4000, ". 1" * 7000):
        inicio = time.perf_counter()
        llm_engine._tapar_series(t)
        assert time.perf_counter() - inicio < 0.05
