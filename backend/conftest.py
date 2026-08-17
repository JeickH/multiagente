"""Configuración común de la suite del backend.

Aquí viven las dos cosas que valen para todos los tests:

1. **La bandera `--con-costo`.** Las pruebas marcadas con `@pytest.mark.costo`
   gastan plata de verdad: invocan el modelo en Bedrock, tocan S3 o salen a la
   red contra el sitio público. Por eso NO corren por defecto — el CI de cada
   push tiene que poder correr la suite entera sin generar factura. Para
   incluirlas:

       pytest --con-costo                    # todo, incluidas las de costo
       pytest --con-costo -m costo           # SOLO las de costo
       pytest                                # el default: nada que cobre

   También se activa con `PYTEST_CON_COSTO=1`, que es más cómodo desde un job.

2. **El shim de SQLite.** Los tests montan la base en SQLite en memoria para no
   depender de Postgres, pero el modelo está escrito contra Postgres. Dos cosas
   no se traducen solas y se arreglan aquí, una sola vez para toda la suite.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles


# ---------------------------------------------------------------------------
# Compatibilidad SQLite ← Postgres
# ---------------------------------------------------------------------------

@compiles(JSONB, "sqlite")
def _jsonb_como_json(tipo, compilador, **kw) -> str:      # noqa: ANN001
    """`JSONB` es de Postgres; SQLite guarda lo mismo en una columna `JSON`.

    Sin esto, `create_all()` sobre SQLite revienta con "SQLiteTypeCompiler has
    no attribute visit_JSONB" en cuanto una tabla del subconjunto tiene una
    columna JSONB — y varias la tienen (`mascota_coincidencias.detalle`,
    `users.tutorials_completed`).
    """
    return "JSON"


def _quitar_checks_solo_de_postgres() -> None:
    """Descarta los CHECK que usan operadores que SQLite no entiende.

    Hoy es uno solo: `contacts.phone_e164 ~ '^\\+[1-9]...'` usa el operador de
    expresiones regulares de Postgres. SQLite no lo tiene y falla al crear la
    tabla, lo que tumbaba la colección entera de `test_meta_account_flow`.

    Se quita del metadata *del proceso de tests*, no del modelo: en producción
    la restricción sigue viva. Ningún test afirma nada sobre este CHECK; el
    formato del teléfono se valida además en la capa de aplicación.
    """
    from app import models  # noqa: F401  (importarlo es lo que puebla el metadata)
    from app.database import Base

    for tabla in Base.metadata.tables.values():
        solo_pg = [
            c for c in tabla.constraints
            if isinstance(c, CheckConstraint) and " ~ " in str(c.sqltext)
        ]
        for constraint in solo_pg:
            tabla.constraints.discard(constraint)


# ---------------------------------------------------------------------------
# La bandera de costo
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--con-costo",
        action="store_true",
        default=False,
        help=(
            "Incluye las pruebas marcadas `costo`, que hacen llamadas "
            "facturables (Bedrock, S3, red externa). Sin esta bandera se saltan."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "costo: hace llamadas facturables (Bedrock, S3 o el sitio público en "
        "producción). Se salta salvo que se pase --con-costo.",
    )
    config.addinivalue_line(
        "markers", "lento: tarda segundos, no milisegundos.",
    )
    # El modelo se importa aquí (no arriba) para que la clave de cifrado ya esté
    # puesta por quien la necesite y para no encarecer la carga del plugin.
    _asegurar_clave_de_cifrado()
    _quitar_checks_solo_de_postgres()


def _asegurar_clave_de_cifrado() -> None:
    """`services/crypto` hace fail-fast al importarse si no hay clave.

    En tests usamos una efímera, nunca una real. `setdefault` para no pisar la
    que algún test se haya puesto a propósito.
    """
    if not os.getenv("APP_ENCRYPTION_KEY"):
        from cryptography.fernet import Fernet

        os.environ["APP_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    # `app.database` arma la URL de Postgres al importarse. No se conecta, pero
    # sin estas variables la cadena queda con "None" y confunde cualquier error.
    os.environ.setdefault("POSTGRES_HOST", "localhost")
    os.environ.setdefault("POSTGRES_PORT", "5432")
    os.environ.setdefault("POSTGRES_DB", "test_db")
    os.environ.setdefault("POSTGRES_USER", "test_user")


def con_costo_activo(config: pytest.Config) -> bool:
    return bool(config.getoption("--con-costo")) or os.getenv("PYTEST_CON_COSTO") == "1"


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if con_costo_activo(config):
        return
    saltar = pytest.mark.skip(
        reason="prueba con costo: córrela con --con-costo (o PYTEST_CON_COSTO=1)"
    )
    for item in items:
        if "costo" in item.keywords:
            item.add_marker(saltar)


def pytest_report_header(config: pytest.Config) -> str:
    estado = "SÍ (se van a facturar)" if con_costo_activo(config) else "no"
    return f"pruebas con costo: {estado}"
