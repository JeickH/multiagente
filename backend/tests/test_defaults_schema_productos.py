"""Que `models.py` y la migración de productos declaren los MISMOS defaults.

Por qué existe esta prueba y no un import compartido
----------------------------------------------------
El 2026-09-16 la migración `migrate_sprint31_productos.py` corrió contra RDS y
salió exit 0 sobre una base mal creada: el `create_all()` del arranque del
backend se le adelantó y creó las ocho tablas con los defaults que declaraba
`models.py`, que no eran los del DDL —21 columnas tenían `default=` de Python
y ningún `server_default`, así que nacieron sin `DEFAULT` en la base—. Como las
tablas ya existían, el `CREATE TABLE IF NOT EXISTS` fue un no-op.

El arreglo tiene dos mitades: la migración repara (`SET DEFAULT`) y el modelo
ya no crea tablas sin defaults. Pero eso deja el mismo valor escrito en dos
lados, y dos lados que se copian a mano divergen.

Compartirlos por import sería peor: una migración es una foto de cómo estaba el
esquema ese día, y si importara del modelo cambiaría sola cada vez que alguien
toque `models.py` — que es justo lo que una migración no puede hacer. Así que
se quedan separados y esta prueba es el contrato: si divergen, falla acá y no
en producción seis meses después.

Lo que NO comprueba: que la base real tenga esos defaults. Eso lo hace el
verificador de la propia migración (`--verificar`), que lee
`information_schema`.
"""
from __future__ import annotations

import pytest
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.elements import ClauseElement

from app.database import Base
from app import models  # noqa: F401  (importarlo puebla el metadata)
from scripts import migrate_sprint31_productos as migracion


TABLAS_NUEVAS = [nombre for nombre, _ in migracion.TABLAS]


def _canonico(expr: str) -> str:
    """Deja comparables `TRUE` con `'true'` y `0` con `'0'`.

    La migración escribe la expresión como va en el DDL (`TRUE`, `0`,
    `'producto'`); SQLAlchemy renderiza un `server_default` de texto como
    literal citado (`'true'`, `'0'`, `'producto'`). Postgres termina guardando
    lo mismo en ambos casos, así que para este contrato las comillas son ruido:
    se reusa el normalizador de la migración (que quita el cast final) y encima
    se quitan las comillas externas.
    """
    texto = migracion._normalizar_default(expr)
    if len(texto) >= 2 and texto.startswith("'") and texto.endswith("'"):
        texto = texto[1:-1]
    return texto


def _default_del_modelo(columna) -> str | None:  # noqa: ANN001
    """La expresión SQL del `server_default` de una columna del metadata."""
    server_default = columna.server_default
    if server_default is None:
        return None
    arg = server_default.arg
    if isinstance(arg, ClauseElement):
        # `func.now()` y compañía: se compila contra Postgres, que es el motor
        # al que apunta el DDL de la migración.
        return str(arg.compile(dialect=postgresql.dialect()))
    # Texto pelado: SQLAlchemy lo emite citado.
    return "'" + str(arg).replace("'", "''") + "'"


def _columnas_declaradas() -> list[tuple[str, str, str]]:
    return [
        (tabla, columna, expr)
        for tabla, columnas in migracion.DEFAULTS.items()
        for columna, expr in sorted(columnas.items())
    ]


@pytest.mark.parametrize(
    ("tabla", "columna", "esperado"),
    _columnas_declaradas(),
    ids=lambda v: v if isinstance(v, str) else str(v),
)
def test_el_modelo_declara_el_mismo_default_que_la_migracion(
    tabla: str, columna: str, esperado: str
) -> None:
    modelo = Base.metadata.tables[tabla].c[columna]
    real = _default_del_modelo(modelo)

    assert real is not None, (
        f"{tabla}.{columna} no tiene `server_default` en models.py, pero la "
        f"migración declara DEFAULT {esperado}. Un `default=` de Python no "
        "llega al DDL: si `create_all()` crea esta tabla, la columna nace sin "
        "default y la migración ya no la repara sola."
    )
    assert _canonico(real) == _canonico(esperado), (
        f"{tabla}.{columna} divergió: models.py dice {real}, la migración dice "
        f"{esperado}. Tienen que ser el mismo valor."
    )


@pytest.mark.parametrize("tabla", TABLAS_NUEVAS)
def test_la_migracion_conoce_todos_los_defaults_del_modelo(tabla: str) -> None:
    """La otra dirección: un default nuevo en el modelo y no en la migración.

    Sin esto, alguien agrega `server_default` a una columna, `create_all()` la
    crea con default, la migración no, y las dos bases vuelven a diferir — la
    regla de paridad local ↔ RDS rota por el otro lado.
    """
    declarados = set(migracion.DEFAULTS.get(tabla, {}))
    en_el_modelo = {
        c.name for c in Base.metadata.tables[tabla].c if c.server_default is not None
    }
    faltan = sorted(en_el_modelo - declarados)
    assert not faltan, (
        f"{tabla}: estas columnas tienen `server_default` en models.py pero no "
        f"están en DEFAULTS de la migración: {faltan}."
    )


def test_los_timestamps_se_compilan_en_sqlite() -> None:
    """`NOW()` no existe en SQLite y la suite crea el esquema ahí en cada test.

    Por eso los timestamps van con `func.now()`, que cada dialecto compila a lo
    suyo. Si alguien lo cambia por `text("NOW()")` porque "así está en el DDL",
    esto lo atrapa: en SQLite quedaría `DEFAULT (NOW())`, que crea la tabla y
    revienta recién al insertar.
    """
    tabla = Base.metadata.tables["bot_productos"]
    ddl_sqlite = str(CreateTable(tabla).compile(dialect=sqlite.dialect()))
    assert "CURRENT_TIMESTAMP" in ddl_sqlite
    assert "NOW()" not in ddl_sqlite.upper().replace("CURRENT_TIMESTAMP", "")

    ddl_pg = str(CreateTable(tabla).compile(dialect=postgresql.dialect()))
    assert "DEFAULT now()" in ddl_pg
