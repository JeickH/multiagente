"""Migración idempotente del Sprint 8: crea las tablas `bots` y `bot_steps`.

Diseño:
  - `CREATE TABLE IF NOT EXISTS` para ambas tablas.
  - `CREATE INDEX IF NOT EXISTS` para los índices.
  - Sin guardarraíl anti-producción (no destructivo).

Uso:
    # Local (docker-compose)
    docker compose exec backend python backend/scripts/migrate_sprint8_add_bots.py

    # RDS (vía ECS run-task override, ver BITACORA Sprint 7)
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS bots (
        id SERIAL PRIMARY KEY,
        team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        name VARCHAR(120) NOT NULL,
        description VARCHAR(512),
        is_premium BOOLEAN NOT NULL DEFAULT FALSE,
        status VARCHAR(32) NOT NULL DEFAULT 'active',
        channels VARCHAR(255) NOT NULL DEFAULT 'whatsapp',
        triggered_count INTEGER NOT NULL DEFAULT 0,
        completed_steps_count INTEGER NOT NULL DEFAULT 0,
        finished_count INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_bots_team_id ON bots(team_id);",
    "CREATE INDEX IF NOT EXISTS ix_bots_team_updated ON bots(team_id, updated_at);",
    """
    CREATE TABLE IF NOT EXISTS bot_steps (
        id SERIAL PRIMARY KEY,
        bot_id INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        position INTEGER NOT NULL,
        step_type VARCHAR(32) NOT NULL,
        label VARCHAR(255) NOT NULL,
        config TEXT,
        next_step_id INTEGER REFERENCES bot_steps(id) ON DELETE SET NULL,
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_bot_step_position UNIQUE (bot_id, position)
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_bot_steps_bot_id ON bot_steps(bot_id);",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for sql in STATEMENTS:
            clean = " ".join(sql.split())
            print(f"  -> {clean[:80]}{'...' if len(clean) > 80 else ''}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        for tbl in ("bots", "bot_steps"):
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t ORDER BY ordinal_position"
                ),
                {"t": tbl},
            ).fetchall()
            print(f"Columnas de {tbl}: {[r[0] for r in rows]}")

    print("\nOK: migración Sprint 8 aplicada (o ya estaba aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
