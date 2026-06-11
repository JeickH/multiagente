"""Migración idempotente: añade `conversations.assigned_to` (default 'bot').

Contexto (demo agencia de viajes Coveñas):
  Las conversaciones necesitan saber quién las atiende. Por defecto el bot;
  cuando el bot detecta datos de reserva hace handoff a un asesor humano
  (ej. "asesor_1"). `create_all()` no aplica ALTER a tablas existentes, así
  que esta columna debe agregarse manualmente en local Y en RDS (regla de
  paridad de schema del CEO).

Diseño:
  - 100% idempotente (ADD COLUMN IF NOT EXISTS, con DEFAULT 'bot').
  - No destructiva. Backfill implícito: las filas existentes toman 'bot'.

Uso:
    # Local (venv)
    source backend/.venv/bin/activate
    POSTGRES_HOST=localhost python backend/scripts/migrate_demo_assigned_to.py

    # Docker compose
    docker compose exec backend python backend/scripts/migrate_demo_assigned_to.py

    # RDS (vía ECS run-task override, región sa-east-1)
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
    ("conversations", "assigned_to", "VARCHAR NOT NULL DEFAULT 'bot'"),
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

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'conversations' ORDER BY ordinal_position"
            )
        ).fetchall()
        cols = [r[0] for r in rows]
        print()
        print(f"Columnas actuales de conversations: {cols}")
        missing = [c for _, c, _ in MIGRATIONS if c not in cols]
        if missing:
            print(f"ERROR: siguen faltando columnas: {missing}")
            return 1

    print()
    print("OK: migración assigned_to aplicada (o ya estaba aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
