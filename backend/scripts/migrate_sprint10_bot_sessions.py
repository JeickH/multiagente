"""Migración idempotente Sprint 10: ejecución real de bots contra Meta.

Crea:
  - bot_sessions       (una conversación activa entre un bot y un contacto)
  - bot_pending_actions (acciones diferidas para pasos `delay`)

Uso:
    docker compose exec backend python scripts/migrate_sprint10_bot_sessions.py
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
    CREATE TABLE IF NOT EXISTS bot_sessions (
        id SERIAL PRIMARY KEY,
        bot_id INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
        conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
        state TEXT,
        status VARCHAR(32) NOT NULL DEFAULT 'running',
        started_at TIMESTAMP NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_bot_sessions_bot_id ON bot_sessions(bot_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_sessions_conversation_id ON bot_sessions(conversation_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_sessions_conv_status ON bot_sessions(conversation_id, status);",
    """
    CREATE TABLE IF NOT EXISTS bot_pending_actions (
        id SERIAL PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES bot_sessions(id) ON DELETE CASCADE,
        scheduled_at TIMESTAMP NOT NULL,
        action_type VARCHAR(32) NOT NULL DEFAULT 'resume_session',
        payload TEXT,
        status VARCHAR(16) NOT NULL DEFAULT 'pending',
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error VARCHAR(512),
        created_at TIMESTAMP NOT NULL DEFAULT NOW(),
        processed_at TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_pending_actions_session ON bot_pending_actions(session_id);",
    "CREATE INDEX IF NOT EXISTS ix_pending_actions_scheduled ON bot_pending_actions(scheduled_at);",
    "CREATE INDEX IF NOT EXISTS ix_pending_actions_due ON bot_pending_actions(status, scheduled_at);",
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
        for tbl in ("bot_sessions", "bot_pending_actions"):
            rows = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t ORDER BY ordinal_position"
                ),
                {"t": tbl},
            ).fetchall()
            print(f"Columnas de {tbl}: {[r[0] for r in rows]}")

    print("\nOK: migración Sprint 10 aplicada (o ya estaba aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
