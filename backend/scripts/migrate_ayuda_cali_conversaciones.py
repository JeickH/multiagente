"""Migración sprint "Ayuda a Cali" (3ª parte): registro de conversaciones.

Añade a `bot_llm_decisions`:
  - `chat_ref`      → agrupa los turnos de una misma conversación en los canales
                      sin `conversation_id` (el chat web es anónimo). Hoy es un
                      uuid de la sesión; con WhatsApp conectado será el número.
  - `chat_contacto` → nombre o teléfono que la persona dio, si lo dio.

Con eso el panel puede listar las conversaciones del bot, mostrar de un vistazo
qué caminos tomó (buscar / reportar / descargar) y desplegar el detalle solo
cuando alguien lo pide.

Idempotente. Se corre en local y en RDS en el mismo PR (convención #1).

Uso:
    docker compose -p wati exec -T backend python scripts/migrate_ayuda_cali_conversaciones.py
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


SENTENCIAS = [
    "ALTER TABLE bot_llm_decisions ADD COLUMN IF NOT EXISTS chat_ref VARCHAR(64);",
    "ALTER TABLE bot_llm_decisions ADD COLUMN IF NOT EXISTS chat_contacto VARCHAR(120);",
    "CREATE INDEX IF NOT EXISTS ix_llm_decisions_chat_ref "
    "ON bot_llm_decisions (chat_ref, created_at);",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            print(f"  -> {sql}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'bot_llm_decisions' "
                    "AND column_name IN ('chat_ref','chat_contacto')"
                )
            )
        ]
        print(f"\ncolumnas nuevas: {', '.join(sorted(cols)) or '(ninguna)'}")
        if len(cols) != 2:
            return 1
    print('\nMigración "Ayuda a Cali" (conversaciones) OK.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
