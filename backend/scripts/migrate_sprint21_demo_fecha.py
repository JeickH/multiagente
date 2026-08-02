"""Migración Sprint 21 #293: `demo_bookings.fecha` (fecha real de la cita).

Hasta ahora la cita solo guardaba el día de la semana ("martes") y la hora.
Con la política de agenda nueva (+3 días hábiles, L-V, 10:00-16:00) el motor
resuelve la **fecha exacta**, así que se persiste.

Idempotente (`ADD COLUMN IF NOT EXISTS`). Correr en local y en RDS en el mismo
PR (convención #1 de paridad).

Uso:
    docker compose exec backend python scripts/migrate_sprint21_demo_fecha.py
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


STATEMENTS = [
    "ALTER TABLE demo_bookings ADD COLUMN IF NOT EXISTS fecha DATE;",
    "CREATE INDEX IF NOT EXISTS ix_demo_bookings_fecha ON demo_bookings (fecha);",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for sql in STATEMENTS:
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
        print(f"\ndemo_bookings columnas: {', '.join(cols)}")
        if "fecha" not in cols:
            return 1
    print("Migración #293 OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
