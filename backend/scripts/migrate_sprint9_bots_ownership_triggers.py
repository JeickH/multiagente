"""Migración idempotente Sprint 9: cambio de dueño del bot + triggers.

Cambios de schema:
  - bots.user_id (NUEVA COLUMNA, FK → users.id ON DELETE CASCADE)
    Backfill desde teams.owner_user_id para bots existentes.
  - bots.trigger_type  VARCHAR(32) NOT NULL DEFAULT 'manual'
    Valores válidos: 'default' | 'keyword' | 'manual'.
  - bots.trigger_config TEXT NULL (JSON serializado)
  - bots.is_premium → DROP COLUMN
  - UNIQUE parcial sobre (user_id) WHERE trigger_type='default'
    para garantizar un solo bot default por cuenta.

NOTA sobre team_id: se mantiene la columna por ahora (no rompe compatibilidad
con código viejo que aún la consulte). Se puede DROP en un sprint posterior
cuando todo el código use user_id.

Uso:
    docker compose exec backend python scripts/migrate_sprint9_bots_ownership_triggers.py
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


STATEMENTS: list[str] = [
    # 1) user_id nullable inicialmente para permitir backfill
    "ALTER TABLE bots ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;",

    # 2) trigger_type + trigger_config
    "ALTER TABLE bots ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(32) NOT NULL DEFAULT 'manual';",
    "ALTER TABLE bots ADD COLUMN IF NOT EXISTS trigger_config TEXT;",

    # 3) Backfill user_id desde el owner del team
    """
    UPDATE bots
       SET user_id = t.owner_user_id
      FROM teams t
     WHERE bots.team_id = t.id
       AND bots.user_id IS NULL;
    """,

    # 4) Hacer user_id NOT NULL ahora que está backfilled
    "ALTER TABLE bots ALTER COLUMN user_id SET NOT NULL;",

    # 5) Index por user_id para listados
    "CREATE INDEX IF NOT EXISTS ix_bots_user_id ON bots(user_id);",
    "CREATE INDEX IF NOT EXISTS ix_bots_user_updated ON bots(user_id, updated_at);",

    # 6) UNIQUE parcial: un solo bot con trigger_type='default' por usuario
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_one_default_bot_per_user ON bots(user_id) WHERE trigger_type = 'default';",

    # 7) Drop is_premium (ya no se usa)
    "ALTER TABLE bots DROP COLUMN IF EXISTS is_premium;",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        for sql in STATEMENTS:
            clean = " ".join(sql.split())
            print(f"  -> {clean[:90]}{'...' if len(clean) > 90 else ''}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        cols = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'bots' ORDER BY ordinal_position"
            )
        ).fetchall()
        print(f"\nColumnas finales de bots: {[r[0] for r in cols]}")

        idx = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'bots' ORDER BY indexname"
            )
        ).fetchall()
        print(f"Índices de bots: {[r[0] for r in idx]}")

    print("\nOK: migración Sprint 9 aplicada (o ya estaba aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
