"""Migración idempotente Sprint 11: tabla `leads` para la landing Gloma."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS leads (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        telefono VARCHAR(32) NOT NULL,
        source VARCHAR(64) NOT NULL DEFAULT 'gloma_landing',
        user_agent VARCHAR(512),
        ip_address VARCHAR(64),
        contacted BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    """,
    "CREATE INDEX IF NOT EXISTS ix_leads_email ON leads(email);",
    "CREATE INDEX IF NOT EXISTS ix_leads_source ON leads(source);",
    "CREATE INDEX IF NOT EXISTS ix_leads_created_at ON leads(created_at);",
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
    print("\nOK: migración Sprint 11 (leads) aplicada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
