"""Migración Sprint 19: motor de bots LLM (AWS Bedrock).

Añade a `bots`:
  - `engine`     VARCHAR(16) NOT NULL DEFAULT 'flow'  ('flow' | 'llm')
  - `llm_config` TEXT (JSON con context_key, assignee, media, shopify cifrado...)

Diseño:
  - 100% idempotente (`ADD COLUMN IF NOT EXISTS`). Re-ejecutable sin efectos.
  - Sin pérdida de datos: los bots existentes quedan con engine='flow' (default).

Uso:
    # Local
    docker compose exec backend python scripts/migrate_sprint19_llm_bots.py

    # RDS (vía ECS run-task override, ver BITACORA Sprint 19 #242)

Follow-up: migrar a Alembic (abierto desde Sprint 7).
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


# (tabla, columna, tipo)
ADD_COLUMNS: list[tuple[str, str, str]] = [
    ("bots", "engine", "VARCHAR(16) NOT NULL DEFAULT 'flow'"),
    ("bots", "llm_config", "TEXT"),
]


def _parse_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _existing_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"
        ),
        {"t": table},
    ).fetchall()
    return {r[0] for r in rows}


def main() -> int:
    host = _parse_host(DATABASE_URL)
    print(f"Conectando a host: {host or '(desconocido)'}")

    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for table, column, col_type in ADD_COLUMNS:
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type};"
            print(f"  -> {sql}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        cols = _existing_columns(conn, "bots")
        missing = [f"{t}.{c}" for t, c, _ in ADD_COLUMNS if c not in cols]
        print()
        print(f"bots: engine={'engine' in cols} llm_config={'llm_config' in cols}")
        if missing:
            print(f"ERROR: siguen faltando columnas: {missing}")
            return 1

    print("Migración Sprint 19 OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
