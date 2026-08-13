"""Migración sprint "Ayuda a Cali" (2ª parte): reportes importados de otras
plataformas.

Añade a `mascotas`:
  - `origen_url`  → link a la ficha original (mascotasporcolombia.com u otra).
  - `origen_id`   → identificador en el sitio de origen, para deduplicar entre
                    corridas del importador.
  - `contacto_telefono` pasa a ser NULLABLE: los reportes importados no traen
    teléfono y el contacto se resuelve mandando a la ficha original. La regla
    "teléfono **o** origen_url" se valida en `services/mascotas`, no en la BD.

Más el índice único `(source, origen_id)` para que el importador pueda
re-ejecutarse sin duplicar.

Idempotente. Se corre en local y en RDS en el mismo PR (convención #1).

Uso:
    docker compose -p wati exec -T backend python scripts/migrate_ayuda_cali_origen.py
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


SENTENCIAS = [
    "ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS origen_url VARCHAR(500);",
    "ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS origen_id VARCHAR(120);",
    "ALTER TABLE mascotas ALTER COLUMN contacto_telefono DROP NOT NULL;",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_origen_id ON mascotas (origen_id);",
    # Índice único parcial: solo aplica a las filas importadas (las que tienen
    # `origen_id`). Los reportes propios lo dejan en NULL y no chocan entre sí.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_mascota_origen "
    "ON mascotas (source, origen_id) WHERE origen_id IS NOT NULL;",
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
        filas = conn.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'mascotas' "
                "AND column_name IN ('origen_url','origen_id','contacto_telefono') "
                "ORDER BY column_name"
            )
        ).fetchall()
        print()
        for nombre, nullable in filas:
            print(f"  {nombre}: nullable={nullable}")
        columnas = {f[0] for f in filas}
        if not {"origen_url", "origen_id"} <= columnas:
            return 1
        if dict(filas).get("contacto_telefono") != "YES":
            print("ERROR: contacto_telefono debería quedar nullable")
            return 1
    print('\nMigración "Ayuda a Cali" (origen) OK.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
