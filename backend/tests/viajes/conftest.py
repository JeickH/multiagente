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
from typing import Any, Dict

import pytest

from app.data.bot_viajes import CAMINOS, LLM_CONFIG, MEDIA  # noqa: F401


class BotViajes:
    """El bot de viajes sin base de datos, para los tests del motor."""

    id = 12
    engine = "llm"
    status = "active"

    def __init__(self, **extra: Any) -> None:
        cfg: Dict[str, Any] = dict(LLM_CONFIG)
        cfg.update(extra)
        self.llm_config = json.dumps(cfg, ensure_ascii=False)

    @property
    def cfg(self) -> Dict[str, Any]:
        return json.loads(self.llm_config)


@pytest.fixture
def bot() -> BotViajes:
    return BotViajes()
