"""Migración Sprint 21 #275: tabla `demo_bookings`.

Una fila por demo que el bot de Gloma agenda con un prospecto (la escribe la
herramienta `registrar_demo` del motor LLM, desde landing / simulador /
WhatsApp). Es la tabla que el CEO monitorea.

Idempotente (`CREATE TABLE/INDEX IF NOT EXISTS`). Se corre en local y en RDS
en el mismo PR (convención #1 de paridad).

Uso:
    docker compose exec backend python scripts/migrate_sprint21_demo_bookings.py
    # RDS: aws ecs run-task con command override (ver BITACORA Sprint 21 #281)

Consulta de monitoreo para el CEO:
    SELECT created_at, nombre, empresa, correo, telefono, dia, hora, source, estado
    FROM demo_bookings ORDER BY created_at DESC;
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


DDL = """
CREATE TABLE IF NOT EXISTS demo_bookings (
    id SERIAL PRIMARY KEY,
    bot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
    source VARCHAR(16) NOT NULL DEFAULT 'landing',
    nombre VARCHAR(120),
    empresa VARCHAR(160),
    correo VARCHAR(255) NOT NULL,
    telefono VARCHAR(32),
    dia VARCHAR(16),
    hora VARCHAR(16),
    notas VARCHAR(500),
    estado VARCHAR(24) NOT NULL DEFAULT 'solicitada',
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_demo_bookings_bot_id ON demo_bookings (bot_id);",
    "CREATE INDEX IF NOT EXISTS ix_demo_bookings_correo ON demo_bookings (correo);",
    "CREATE INDEX IF NOT EXISTS ix_demo_bookings_source ON demo_bookings (source);",
    "CREATE INDEX IF NOT EXISTS ix_demo_bookings_estado ON demo_bookings (estado);",
    "CREATE INDEX IF NOT EXISTS ix_demo_bookings_created_at ON demo_bookings (created_at);",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        print("  -> CREATE TABLE IF NOT EXISTS demo_bookings")
        conn.execute(text(DDL))
        for sql in INDEXES:
            print(f"  -> {sql}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'demo_bookings' ORDER BY ordinal_position"
                )
            )
        ]
        print(f"\ndemo_bookings columnas: {', '.join(cols) or '(no existe)'}")
        if "correo" not in cols:
            return 1
    print("Migración #275 OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
