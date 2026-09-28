"""Migración 2026-09-27: `leads` califica al prospecto y guarda la autorización.

El formulario de la landing de Gloma ahora pide, además de nombre, correo y
teléfono:

- `agencia`               VARCHAR(120) — nombre de la agencia.
- `chats_mes`             VARCHAR(16)  — rango de chats al mes, alineado con
                                         los paquetes (600 / 2.000 / 6.000).
- `acepto_privacidad_at`  TIMESTAMP    — cuándo aceptó la política de
                                         tratamiento de datos (Ley 1581).

Las tres son nullable: la landing de Gorvek usa el mismo endpoint sin ellas y
las filas viejas no las tienen.

Idempotente (`ADD COLUMN IF NOT EXISTS`). Se corre en local y en RDS en el
mismo PR (convención #1 de paridad), y **va con el despliegue del modelo**:
sin el `models.py` nuevo en la imagen, el ORM no ve las columnas.

Uso:
    docker compose -p wati exec backend python scripts/migrate_leads_calificacion.py
    # RDS: aws ecs run-task con command override (ver procedimiento de deploy)
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


ALTERS = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS agencia VARCHAR(120);",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS chats_mes VARCHAR(16);",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS acepto_privacidad_at TIMESTAMP;",
]
NUEVAS = ("agencia", "chats_mes", "acepto_privacidad_at")


def _columnas(conn) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'leads' ORDER BY ordinal_position"
            )
        )
    ]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)

    with engine.begin() as conn:
        if not _columnas(conn):
            print("ERROR: la tabla `leads` no existe.")
            return 1
        for sql in ALTERS:
            print(f"  -> {sql}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        cols = _columnas(conn)
        print(f"\nleads columnas: {', '.join(cols)}")
        faltan = [c for c in NUEVAS if c not in cols]
        if faltan:
            print(f"ERROR: faltan columnas: {', '.join(faltan)}")
            return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
