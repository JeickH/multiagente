"""Piezas compartidas de las pruebas del bot de viajes (Arranquemos Pues).

El bot vive en producción como el id 12 de `arranquemospues.marketing@gmail.com`
(engine `llm`, contexto `demo_viajes`). Su `llm_config` NO se copia aquí: se
importa de `app/data/bot_viajes.py`, que es la fuente de verdad que usan tanto
el seed como el actualizador de producción. Si alguien cambia los caminos o el
catálogo de medios allá y rompe algo, estos tests se enteran; con una copia
pegada, no.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import pytest

from app.data.bot_viajes import CAMINOS, LLM_CONFIG, MEDIA  # noqa: F401

#: Doble corrida de la fase 5: los mismos guiones contra el motor viejo (el
#: JSON del tarifario) y contra el catálogo de la base, sin tocar ni un guion.
#: **Sin estas variables puestas no cambia absolutamente nada** — el bot de las
#: pruebas es el de siempre, con `fuente_datos` en su valor por defecto.
#:
#: `BOT_VIAJES_TEAM_ID` y `BOT_VIAJES_BOT_ID` existen porque el catálogo se
#: consulta filtrando por cuenta y por bot: el bot de estas pruebas no sale de
#: la base (es un objeto en memoria) y sin esos dos números `catalogos_de_bot`
#: no encontraría el producto — que es justo el aislamiento que se quiere.
_FUENTE = (os.getenv("BOT_VIAJES_FUENTE") or "").strip().lower()
_TEAM_ID = os.getenv("BOT_VIAJES_TEAM_ID")
_BOT_ID = os.getenv("BOT_VIAJES_BOT_ID")


class BotViajes:
    """El bot de viajes sin base de datos, para los tests del motor."""

    id = 12
    engine = "llm"
    status = "active"

    def __init__(self, **extra: Any) -> None:
        cfg: Dict[str, Any] = dict(LLM_CONFIG)
        if _FUENTE:
            cfg["fuente_datos"] = _FUENTE
        cfg.update(extra)
        self.llm_config = json.dumps(cfg, ensure_ascii=False)
        if _TEAM_ID:
            self.team_id = int(_TEAM_ID)
        if _BOT_ID:
            self.id = int(_BOT_ID)

    @property
    def cfg(self) -> Dict[str, Any]:
        return json.loads(self.llm_config)


@pytest.fixture
def bot() -> BotViajes:
    return BotViajes()
