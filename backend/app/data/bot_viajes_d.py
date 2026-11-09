"""Configuración LLM del bot D (estrategia D, «la asesora que conversa») de Arranquemos Pues.

Estrategia aprobada por el CEO el 7-nov-2026 (Sprint 36): une la A («total
primero») y la B («dos puertas») con una conversación **humana y guiada**, sin
menús numerados. Vende el mismo plan que los bots 1, 2 y 3, con los mismos
productos, medios y tiempos de reenganche. Reparto 25 / 25 / 50 con los bots 1
y 3, y es el **bot de reenganche** de la cuenta: atiende a los que vuelven a una
conversación abandonada o cerrada por inactividad (`services/reenganche.py`).

Como en los bots 2 y 3, todo lo nuevo va por banderas y el guion vive en
`bot_contexts/demo_viajes_d.md`. Lo que comparten los tres bots al vender (total
del grupo, pedir la venta, «sale de Medellín», sin «todo incluido», cierre con
nombre + cédula de quien paga) ya lo hace `services/venta_grupo.py` para todo bot
con `tarifario`.

**La puerta 2 (llamada en una de 5 franjas) está APAGADA** (`llamada_en_franja`
en False): el CEO la prende cuando la agencia confirme que llama dentro de la
franja. Con la bandera apagada el guion no ofrece llamadas con hora.

**Ninguna cifra de precio está escrita aquí.**
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict

from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import FLAGS_VARIANTE as FLAGS_VARIANTE_B
from app.data.bot_viajes_b import _seguimiento_b

#: Clave del contexto: `bot_contexts/<CONTEXT_KEY_D>.md`.
CONTEXT_KEY_D = "demo_viajes_d"

RUTA_MD_D = Path(__file__).resolve().parent.parent / "bot_contexts" / f"{CONTEXT_KEY_D}.md"


def instrucciones_d() -> str:
    """El texto del guion del bot D, tal como se guarda en `bots.instrucciones`."""
    return RUTA_MD_D.read_text(encoding="utf-8").strip()


#: Las del bot 2 que D NO lleva, a propósito:
#:   - `apertura_vitrina`: D abre con el plan en dos líneas y «¿Para cuántas
#:     personas sería?»; el «desde» de la temporada confundía (QA del 7-nov).
NO_VAN_EN_D = ("apertura_vitrina",)

FLAGS_VARIANTE_D: Dict[str, Any] = {
    **{k: copy.deepcopy(v) for k, v in FLAGS_VARIANTE_B.items() if k not in NO_VAN_EN_D},
    "variante": "D",
    # Puerta 2 (llamada en franja): apagada hasta el acuerdo con la agencia.
    "llamada_en_franja": False,
    # El que vuelve tras un abandono y solo saluda recibe un saludo fijo con lo
    # que estaba mirando (el modelo le repetía la bienvenida en la QA del 8-nov).
    "saludo_de_regreso": True,
}

LLM_CONFIG_D: Dict[str, Any] = {
    **copy.deepcopy(LLM_CONFIG),
    "context_key": CONTEXT_KEY_D,
    **copy.deepcopy(FLAGS_VARIANTE_D),
    # Recordatorios con el mes y las salidas (los del bot 2): sin menús.
    "seguimiento": _seguimiento_b(),
}
