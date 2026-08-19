"""Piezas compartidas de las pruebas del bot de Jerarquía (Promo Manada).

La `llm_config` NO se copia aquí: se carga del propio
`backend/scripts/seed_bot_jerarquia.py`, que es la fuente de verdad. Si alguien
cambia los caminos o la config de venta allá y rompe algo, estos tests se
enteran; con una copia pegada, no.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

import pytest

_SEED = Path(__file__).resolve().parents[2] / "scripts" / "seed_bot_jerarquia.py"


def _cargar_seed():
    """Importa el seed por ruta: `backend/scripts/` no es un paquete."""
    spec = importlib.util.spec_from_file_location("_seed_jerarquia", _SEED)
    assert spec and spec.loader, f"no se pudo cargar {_SEED}"
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


_seed = _cargar_seed()
LLM_CONFIG: Dict[str, Any] = _seed._llm_config()
CAMINOS: Dict[str, list] = LLM_CONFIG["caminos"]


class BotJerarquia:
    """El bot de Jerarquía sin base de datos, para los tests del motor."""

    id = 90
    engine = "llm"
    status = "active"

    def __init__(self, **extra: Any) -> None:
        cfg = dict(LLM_CONFIG)
        cfg.update(extra)
        self.llm_config = json.dumps(cfg, ensure_ascii=False)

    @property
    def cfg(self) -> Dict[str, Any]:
        return json.loads(self.llm_config)


@pytest.fixture
def bot() -> BotJerarquia:
    return BotJerarquia()
