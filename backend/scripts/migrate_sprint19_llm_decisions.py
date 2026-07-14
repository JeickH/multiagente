"""Migración Sprint 19 #255: tabla `bot_llm_decisions` (observabilidad del motor LLM).

Una fila por turno de conversación LLM: camino tomado, herramientas llamadas,
latencia, rondas, escalamiento y fail-safe. Idempotente (CREATE TABLE/INDEX
IF NOT EXISTS). Nota: `Base.metadata.create_all` del arranque también crea
tablas NUEVAS, pero este script existe para la evidencia de paridad local↔RDS
(convención #1) y para poder correrla sin reiniciar el backend.

Uso:
    docker compose exec backend python scripts/migrate_sprint19_llm_decisions.py
    # RDS: vía ECS run-task override (ver BITACORA Sprint 19 #255)
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


DDL = """
CREATE TABLE IF NOT EXISTS bot_llm_decisions (
    id SERIAL PRIMARY KEY,
    bot_id INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    session_id INTEGER REFERENCES bot_sessions(id) ON DELETE SET NULL,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'whatsapp',
    user_input TEXT,
    camino VARCHAR(64) NOT NULL DEFAULT 'respuesta_libre',
    tools_called TEXT,
    reply_preview VARCHAR(300),
    model_id VARCHAR(128),
    rounds INTEGER NOT NULL DEFAULT 1,
    latency_ms INTEGER,
    finished BOOLEAN NOT NULL DEFAULT FALSE,
    escalated_to VARCHAR(64),
    failsafe BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_bot_llm_decisions_bot_id ON bot_llm_decisions (bot_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_llm_decisions_conversation_id ON bot_llm_decisions (conversation_id);",
    "CREATE INDEX IF NOT EXISTS ix_llm_decisions_bot_created ON bot_llm_decisions (bot_id, created_at);",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        print("  -> CREATE TABLE IF NOT EXISTS bot_llm_decisions")
        conn.execute(text(DDL))
        for sql in INDEXES:
            print(f"  -> {sql}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        ok = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'bot_llm_decisions'"
            )
        ).scalar()
        print(f"\nbot_llm_decisions existe: {bool(ok)}")
        if not ok:
            return 1
    print("Migración #255 OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
