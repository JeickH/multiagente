"""Migración Sprint 15: añade `users.tutorials_completed` (JSONB) para
persistir el estado de los tutoriales interactivos por usuario y por módulo.

Diseño:
  - 100% idempotente (`ADD COLUMN IF NOT EXISTS`) + backfill defensivo
    (`UPDATE ... SET tutorials_completed='{}'::jsonb WHERE ... IS NULL`).
  - Sin riesgo de pérdida de datos: sólo añade columna.
  - Mismo patrón que las migraciones de Sprints anteriores (engine.begin()).

Uso:
    # Local
    docker compose exec backend python scripts/migrate_sprint15_tutorials.py

    # RDS (vía ECS run-task override, ver BITACORA Sprint 15 #195)

Follow-up: migrar a Alembic (sigue abierto desde Sprint 7).
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


MIGRATIONS: list[tuple[str, str, str]] = [
    ("users", "tutorials_completed", "JSONB NOT NULL DEFAULT '{}'::jsonb"),
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
    with engine.begin() as conn:
        for table, column, col_type in MIGRATIONS:
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type};"
            print(f"  -> {sql}")
            conn.execute(text(sql))
        # Backfill defensivo: si quedó alguna fila con NULL (no debería con DEFAULT),
        # se normaliza a '{}'::jsonb.
        result = conn.execute(
            text(
                "UPDATE users SET tutorials_completed = '{}'::jsonb "
                "WHERE tutorials_completed IS NULL;"
            )
        )
        print(f"  -> backfill UPDATE users: {result.rowcount} filas normalizadas")

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
    print("OK: migración Sprint 15 aplicada (o ya estaba aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
