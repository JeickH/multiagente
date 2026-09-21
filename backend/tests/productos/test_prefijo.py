"""Cuánto pesa el prefijo de la capa nueva contra el del motor viejo.

Esto existe porque la medición de la fase 5 salió al revés de lo prometido:
69 guiones por lado contra Bedrock, y el motor con catálogo gastó **más** que
el viejo — `tokens_in` +3,2 %, `cache_write` +38,4 %, con los mismos 181
`rounds`. La causa no estaba en las respuestas sino en el prefijo, que creció
de 38.174 a 39.578 caracteres: `abrir_producto` y `fechas_disponibles` se
declaraban en las 181 llamadas y se usaron **cero** veces.

El prefijo se puede medir sin gastar un peso: es el bloque `system` más el JSON
de las herramientas, y los dos se arman sin hablar con el modelo. Así que esta
prueba pone el mismo bot en las dos fuentes y exige que la nueva **no** sea más
cara que la vieja. Es la prueba que le habría avisado antes de quemar la
corrida contra Bedrock.

El bot es el de viajes de verdad (su `llm_config` sale de `app/data/bot_viajes`)
y el catálogo entra como dato con el helper `covenas.py`, igual que en la prueba
de oro: medir con un producto de juguete y un prompt corto no diría nada, porque
lo que se compara son dos prefijos de ~38.000 caracteres.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Tuple

import pytest

from app.data.bot_viajes import LLM_CONFIG
from app.services import llm_engine, productos_bot

from tests.productos import covenas
from tests.productos.conftest import crear_cuenta


class BotDeViajes:
    """El bot de producción sin base: lo que cambia es de dónde saca los datos."""

    engine = "llm"
    status = "active"

    def __init__(self, team_id: int, bot_id: int, **extra: Any) -> None:
        cfg: Dict[str, Any] = dict(LLM_CONFIG)
        cfg.update(extra)
        self.llm_config = json.dumps(cfg, ensure_ascii=False)
        self.team_id = team_id
        self.id = bot_id

    @property
    def cfg(self) -> Dict[str, Any]:
        return json.loads(self.llm_config)


def _prefijo(bot: BotDeViajes, ctx) -> Tuple[str, List[Dict[str, Any]]]:
    """Lo que viaja en CADA llamada al modelo: el `system` y las herramientas.

    Se arma con las mismas dos funciones que usa el turno real. Si alguien
    cambia cómo se construye una de las dos, esto lo mide sin enterarse.
    """
    cfg = bot.cfg
    system = llm_engine._system_prompt(bot, cfg, [], "hola", ctx)
    return system, llm_engine._tools_for(cfg, ctx, system)


def _tamano(system: str, tools: List[Dict[str, Any]]) -> int:
    return len(system) + len(json.dumps(tools, ensure_ascii=False))


@pytest.fixture
def dos_fuentes(db_session):
    """El mismo bot medido con el tarifario viejo y con el catálogo."""
    team_id, bot_id = crear_cuenta(db_session, "prefijo")
    covenas.cargar(db_session, team_id=team_id, bot_id=bot_id)
    db_session.commit()

    viejo = _prefijo(BotDeViajes(team_id, bot_id), None)
    ctx = productos_bot.abrir(db_session, team_id=team_id, bot_id=bot_id)
    assert ctx is not None and ctx.unico is not None, (
        "el tarifario de Coveñas entra como UN producto; si ahora son varios, "
        "esta medición compara otra cosa"
    )
    nuevo = _prefijo(BotDeViajes(team_id, bot_id, fuente_datos="productos"), ctx)
    return viejo, nuevo


def test_el_prefijo_nuevo_no_puede_pesar_mas_que_el_viejo(dos_fuentes):
    """La regla, y el número que la corrida de Bedrock pagó por no tener.

    El margen es estrecho a propósito: el catálogo se gana su lugar por lo que
    ahorra en esquema de herramientas, no por poco. Si esta prueba se pone roja
    con un cambio de texto, el cambio está encareciendo cada ronda de cada turno
    de todos los clientes del piloto — no es la prueba la que hay que aflojar.
    """
    (sys_viejo, tools_viejo), (sys_nuevo, tools_nuevo) = dos_fuentes
    viejo = _tamano(sys_viejo, tools_viejo)
    nuevo = _tamano(sys_nuevo, tools_nuevo)

    assert nuevo <= viejo, (
        f"el prefijo de la capa nueva pesa {nuevo} caracteres "
        f"(~{int(nuevo / productos_bot.CARACTERES_POR_TOKEN)} tokens) contra "
        f"{viejo} (~{int(viejo / productos_bot.CARACTERES_POR_TOKEN)}) del "
        f"motor viejo: +{nuevo - viejo} caracteres en CADA llamada"
    )


def test_ninguna_herramienta_del_catalogo_se_declara_de_mas(dos_fuentes):
    """El defecto concreto que se pagó: dos esquemas que nadie llamó.

    Con un solo producto y sin ficha, la única herramienta del catálogo con algo
    que hacer es la de precios. `abrir_producto` no tiene ficha que abrir y las
    fechas ya salen de `consultar_precios` —lo dice el propio pie del índice—,
    así que declararlas era contradecir el prompt y pagarlo por ronda.
    """
    _, (_, tools_nuevo) = dos_fuentes
    del_catalogo = [t["name"] for t in tools_nuevo if t["name"] in productos_bot.TOOLS]

    assert del_catalogo == [productos_bot.PRECIOS]


def test_el_catalogo_cuesta_menos_esquema_que_el_tarifario(dos_fuentes):
    """De dónde sale el ahorro, para que se vea si mañana se lo comen.

    El bloque `system` de la capa nueva es un poco más grande (le entra el pie
    que manda los precios a la herramienta nueva, porque el `.md` del piloto
    todavía nombra `consultar_tarifario`). Lo que compensa es el JSON de
    herramientas.
    """
    (sys_viejo, tools_viejo), (sys_nuevo, tools_nuevo) = dos_fuentes
    esquema_viejo = len(json.dumps(tools_viejo, ensure_ascii=False))
    esquema_nuevo = len(json.dumps(tools_nuevo, ensure_ascii=False))

    assert esquema_nuevo < esquema_viejo
    assert len(tools_nuevo) <= len(tools_viejo)
