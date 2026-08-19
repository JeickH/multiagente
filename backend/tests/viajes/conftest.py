"""Piezas compartidas de las pruebas del bot de viajes (Arranquemos Pues).

El bot vive en producción como el id 12 de `arranquemospues.contacto@gmail.com`
(engine `llm`, contexto `demo_viajes`). Su `llm_config` NO se copia aquí: se
carga del propio `backend/scripts/seed_bot_viajes_llm.py`, que es la fuente de
verdad. Si alguien cambia los caminos o el catálogo de medios allá y rompe algo,
estos tests se enteran; con una copia pegada, no.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

import pytest

_SEED = Path(__file__).resolve().parents[2] / "scripts" / "seed_bot_viajes_llm.py"


def _cargar_seed():
    """Importa el seed por ruta: `backend/scripts/` no es un paquete."""
    spec = importlib.util.spec_from_file_location("_seed_viajes", _SEED)
    assert spec and spec.loader, f"no se pudo cargar {_SEED}"
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


_seed = _cargar_seed()
CAMINOS: Dict[str, list] = _seed.CAMINOS
MEDIA: Dict[str, dict] = _seed.MEDIA


class BotViajes:
    """El bot de viajes sin base de datos, para los tests del motor."""

    id = 12
    engine = "llm"
    status = "active"

    def __init__(self, **extra: Any) -> None:
        cfg: Dict[str, Any] = {
            "context_key": "demo_viajes",
            "assignee": "asesor_1",
            "media": MEDIA,
            "caminos": CAMINOS,
        }
        cfg.update(extra)
        self.llm_config = json.dumps(cfg, ensure_ascii=False)

    @property
    def cfg(self) -> Dict[str, Any]:
        return json.loads(self.llm_config)


@pytest.fixture
def bot() -> BotViajes:
    return BotViajes()
