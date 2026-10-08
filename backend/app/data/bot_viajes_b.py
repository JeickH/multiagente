"""Configuración LLM del bot 2 (variante B) de Arranquemos Pues.

El bot 2 vende el mismo plan, con los mismos productos, medios y reenganches
que el bot 1 (`app/data/bot_viajes.py`), y se reparte con él las
conversaciones nuevas (A/B). Cambia el **guion** (`bot_contexts/demo_viajes_b.md`)
y un juego de banderas que encienden comportamientos nuevos del motor solo
para este bot. Sin la bandera, el motor hace exactamente lo de siempre: así el
bot 1 no cambia de comportamiento por nada de lo que se agregue aquí.

Vive en `app/` y no en `scripts/` por lo mismo que `bot_viajes.py`: el script
que crea el bot en producción (`scripts/crear_bot_viajes_b.py`) viaja a ECS
como el cuerpo de un `python -c` y solo puede importar de `app.*`.

**Ninguna cifra de precio está escrita aquí**: el «desde», los niños y el
anticipo salen del tarifario y de su archivo de extras. La única cifra es el
monto de la promoción que NO existe (`promo_inexistente.montos`), que es
justamente lo que hay que detectar y no vender.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

from app.data.bot_viajes import LLM_CONFIG

#: Clave del contexto: `bot_contexts/<CONTEXT_KEY_B>.md`.
CONTEXT_KEY_B = "demo_viajes_b"

#: El guion del bot 2. Se lee del paquete (no de `scripts/`) para que funcione
#: igual en local, en los tests y dentro de la imagen de ECS (`/app/app/...`).
RUTA_MD_B = Path(__file__).resolve().parent.parent / "bot_contexts" / f"{CONTEXT_KEY_B}.md"


def instrucciones_b() -> str:
    """El texto del guion del bot 2, tal como se guarda en `bots.instrucciones`."""
    return RUTA_MD_B.read_text(encoding="utf-8").strip()


#: Lo que el bot 2 enciende por encima del bot 1, con su valor. El nombre de
#: cada llave es el contrato con el motor (spec compartida del bot 2): si se
#: cambia aquí, el motor deja de verla sin avisar.
#:
#: Estrategias (informe del 10-sep-2026) entre corchetes.
FLAGS_VARIANTE: Dict[str, Any] = {
    # Identidad: es lo que distingue al bot 2 del bot 1 en la base. El
    # actualizador del bot 1 se salta todo bot que la tenga.
    "variante": "B",
    # [1, 3, 4, 5] Apertura corta con el «desde» de la temporada y el flyer del
    # mes en curso, ambos puestos por el código.
    "apertura_vitrina": True,
    # [10, 17] El turno se corta después de la pregunta; los adjuntos van antes.
    "una_pregunta_por_turno": True,
    # [11] Se presenta una sola vez por conversación.
    "presentacion_una_vez": True,
    # [8] El nombre no se pide dos veces.
    "nombre_una_vez": True,
    # [9 (+7)] `registrar_nombre` rechaza «Cliente», «No proporcionado», etc.
    "filtrar_nombres_genericos": True,
    # [14] «Lo consulto con mi esposo» no cierra la conversación.
    "no_cerrar_aplazadas": True,
    # [18] Cada precio del mensaje se valida contra la fila consultada.
    "guardarrail_precio": True,
    # [19] La línea de niños sale del tarifario, no del guion.
    "cargos_ninos": True,
    # [20, 21] La promo «de lunes a jueves» del pie de los flyers no existe en
    # el tarifario. Cualquier mención de ese monto por parte del CLIENTE pasa a
    # un asesor con nota interna. Los montos viven aquí (decisión del CEO del
    # 7-oct-2026), no en el motor.
    "promo_inexistente": {
        "montos": [350000],
        "texto": (
            "Déjame confirmarlo con un compañero para no darte un dato "
            "equivocado 🙌 En un momento te escriben por aquí 💬"
        ),
        "motivo": (
            "El cliente menciona la promoción de lunes a jueves de los flyers, "
            "que no está en el tarifario. Confirmarle si aplica antes de "
            "cotizarle."
        ),
    },
    # [22] Herramienta `registrar_intencion` + lista de interesados. Umbral
    # del CEO: la conversación aparece 6 h después de su primer mensaje.
    "intencion_compra": {"horas_para_interesado": 6},
    # [28] El 2.º y el 3.º recordatorio llevan el mes y las salidas que quedan
    # (ver `seguimiento` abajo). Si falta un dato, sale el texto fijo de siempre.
    "recordatorios_con_contexto": True,
    # --- Ajustes tras la QA contra Bedrock (7-oct-2026) ---
    # Si el modelo escala sin escribir nada (pasaba 12/12 al recibir los datos
    # de reserva), el sistema pone este aviso antes del traspaso. Neutro: no
    # sabe el nombre ni el motivo.
    "aviso_en_traspaso": (
        "¡Listo! 🙌 Ya tengo tus datos. Un compañero te confirma el cupo y el "
        "pago por aquí en un momento 💬"
    ),
    # Las correcciones del servidor piden no disculparse, y se recorta
    # «Tienes razón, disculpa…» que llegaba al cliente en 56 % de los casos.
    "correcciones_silenciosas": True,
    # El % de anticipo y el saldo van como dato fijo del sistema (inventó 50 %
    # y 40 % cuando no había consultado).
    "anticipo_en_sistema": True,
    # «[enviaste: x]» escrito por el modelo se vuelve el medio real.
    "marcas_a_medios": True,
    # La duración se valida contra el plan nombrado («Plan Estándar (2 noches
    # / 3 días)» daba falso positivo).
    "duracion_por_plan": True,
    # Si el cliente nombra un mes y el bot responde precios o salidas sin
    # consultar, se corrige.
    "consulta_obligatoria_por_mes": True,
}


#: Plantillas de los recordatorios 2.º (5 h) y 3.º (23 h). Variables que llena
#: `services/recordatorios_contexto.py` desde la última consulta de precios de
#: la conversación y el tarifario: {nombre} {mes} {salidas} {n_salidas}
#: {desde} {anticipo_pct}. Si falta cualquiera, se manda el `texto` fijo.
#:
#: Sin «cupo» a propósito: el tarifario no sabe de cupos, así que «las salidas
#: que quedan» es lo único que se puede afirmar. Y sin {nombre}: el bot 2 no lo
#: pide hasta la reserva, así que casi nunca está, y una plantilla que lo
#: necesite caería casi siempre al texto fijo.
#:
#: `{desde}` llega ya formateado como precio (con el signo y los puntos de
#: miles) — contrato con el servicio de recordatorios.
PLANTILLAS_RECORDATORIO = {
    1: (
        # Sin {n_salidas}: con una sola salida quedaba "quedan 1 salidas".
        "¡Hola de nuevo! 👋 Para {mes} todavía quedan estas salidas: "
        "{salidas}, desde {desde} por persona 🌴 ¿Te cuento los precios de "
        "alguna?"
    ),
    2: (
        "Última razón por hoy 🌴 Te dejo las salidas de {mes} que quedan: "
        "{salidas}, desde {desde} por persona. Si alguna te sirve, la apartas "
        "con el {anticipo_pct}% de anticipo 🙌 ¿Te sirve alguna?"
    ),
}


def _seguimiento_b() -> Dict[str, Any]:
    """El `seguimiento` del bot 1 con plantilla en el 2.º y el 3.º recordatorio.

    Se construye a partir del del bot 1 —copia profunda, para no escribirle
    encima a un módulo que se importa una vez por proceso— y no se reescribe a
    mano: así los minutos, la cantidad de recordatorios y la etiqueta de
    abandono son iguales **por construcción**, y la comparación A/B mide el
    guion y no un reenganche distinto. El `texto` fijo se conserva: es lo que
    sale cuando la plantilla no se puede llenar.
    """
    seg = copy.deepcopy(LLM_CONFIG["seguimiento"])
    for indice, plantilla in PLANTILLAS_RECORDATORIO.items():
        seg["recordatorios"][indice]["plantilla"] = plantilla
    return seg


LLM_CONFIG_B: Dict[str, Any] = {
    **copy.deepcopy(LLM_CONFIG),
    "context_key": CONTEXT_KEY_B,
    **copy.deepcopy(FLAGS_VARIANTE),
    "seguimiento": _seguimiento_b(),
}
