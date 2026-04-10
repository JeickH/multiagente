"""Migración idempotente del Sprint 7: añade columnas nuevas que `create_all()`
no puede aplicar a tablas ya existentes.

Problema que resuelve:
  SQLAlchemy.Base.metadata.create_all() sólo crea tablas inexistentes; NO aplica
  ALTER TABLE. El Sprint 7 añadió columnas a tablas que ya existían en producción
  (principalmente `users.created_at`), lo que hace que cualquier SELECT del ORM
  crashee con `column users.created_at does not exist`.

Alcance actual:
  - users.created_at  (TIMESTAMP NOT NULL DEFAULT NOW())

Diseño:
  - 100% idempotente (ADD COLUMN IF NOT EXISTS).
  - Sin guardarraíl anti-producción: esta migración es NO destructiva.
  - Imprime cada paso y el conteo de filas afectadas.
  - Se puede ejecutar tanto local (docker-compose) como en RDS (vía ECS run-task).

Uso:
    # Local
    source backend/.venv/bin/activate
    POSTGRES_HOST=localhost python backend/scripts/migrate_sprint7_add_columns.py

    # Docker compose
    docker compose exec backend python backend/scripts/migrate_sprint7_add_columns.py

    # RDS (vía ECS run-task override, ver BITACORA Sprint 7)

Follow-up: migrar a Alembic para versionado formal de schema.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


# (tabla, columna, tipo SQL incluyendo NOT NULL/DEFAULT si aplica)
MIGRATIONS: list[tuple[str, str, str]] = [
    ("users", "created_at", "TIMESTAMP NOT NULL DEFAULT NOW()"),
]


def _parse_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def main() -> int:
    host = _parse_host(DATABASE_URL)
    print(f"Conectando a host: {host or '(desconocido)'}")

    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        for table, column, col_type in MIGRATIONS:
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type};"
            print(f"  -> {sql}")
            conn.execute(text(sql))
        conn.commit()

    # Verificación: leer el nombre de las columnas de users
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'users' ORDER BY ordinal_position"
            )
        ).fetchall()
        cols = [r[0] for r in rows]
        print()
        print(f"Columnas actuales de users: {cols}")
        missing = [c for _, c, _ in MIGRATIONS if c not in cols]
        if missing:
            print(f"ERROR: siguen faltando columnas: {missing}")
            return 1

    print()
    print("OK: migración Sprint 7 aplicada (o ya estaba aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
