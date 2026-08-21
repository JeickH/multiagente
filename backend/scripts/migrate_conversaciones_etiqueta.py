"""Columna `conversations.etiqueta` — marca de sistema sobre la conversación.

Hoy la usa un solo caso: cuando el cliente deja de contestarle al bot, la acción
programada de abandono escribe "conversación abandonada" y cierra la
conversación. Nula = sin etiqueta; **no lleva default** a propósito, para que
"sin marcar" no se confunda con una marca vacía.

Sin índice a propósito: la bandeja pagina por `(team_id, last_message_at)` y
nadie filtra por etiqueta todavía. Cuando se filtre, se agrega ahí.

Idempotente: `ADD COLUMN IF NOT EXISTS`. Correrlo dos veces no falla ni pisa
etiquetas ya escritas (no hay backfill ni UPDATE).

Uso local (proyecto docker compose `wati`):
    docker compose -p wati exec -T backend \
        python scripts/migrate_conversaciones_etiqueta.py

Uso en RDS (sa-east-1):
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_conversaciones_etiqueta.py
"""
from __future__ import annotations

import os
import sys

if "__file__" in globals():  # no existe cuando corre vía `python -c` (rds_exec.sh)
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text  # type: ignore

from app.database import SessionLocal  # type: ignore

DDL = [
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS etiqueta VARCHAR NULL",
]


def main() -> int:
    db = SessionLocal()
    try:
        for sentencia in DDL:
            db.execute(text(sentencia))
        db.commit()

        fila = db.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_name = 'conversations' AND column_name = 'etiqueta'
                """
            )
        ).fetchone()
        if fila is None:
            print("ERROR: la columna conversations.etiqueta no existe tras la migración")
            return 1

        total, etiquetadas = db.execute(
            text(
                "SELECT COUNT(*), COUNT(etiqueta) FROM conversations"
            )
        ).fetchone()

        print("conversations.etiqueta OK")
        print(f"  data_type={fila[1]} is_nullable={fila[2]} default={fila[3]!r}")
        print(f"  conversaciones={total} con etiqueta={etiquetadas}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
