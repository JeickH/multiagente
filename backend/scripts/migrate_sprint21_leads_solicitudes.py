"""Migración Sprint 21 #297: `leads` pasa a ser "solicitudes de contacto".

El formulario de la landing ahora pide **nombre** y el CEO gestiona cada
solicitud desde `/citas` → subsección "Solicitudes de contacto", así que la
tabla necesita ciclo de vida además del registro:

- `nombre`      VARCHAR(120)  — lo que ahora pide el form.
- `estado`      VARCHAR(16)   — 'pendiente' | 'contactado' (default 'pendiente').
- `notas`       VARCHAR(500)  — anotaciones del equipo al hacer seguimiento.
- `updated_at`  TIMESTAMP     — última edición desde el panel.

El booleano `contacted` original se **backfillea** a `estado` y luego se
elimina: era exactamente la misma información y dejar los dos lleva a que se
desincronicen.

Idempotente (`ADD COLUMN IF NOT EXISTS` / `DROP COLUMN IF EXISTS`): correrlo
dos veces no cambia nada la segunda vez. Se corre en local y en RDS en el
mismo PR (convención #1 de paridad).

Uso:
    docker compose exec backend python scripts/migrate_sprint21_leads_solicitudes.py
    # RDS: aws ecs run-task con command override (ver BITACORA Sprint 21 #301)

Consulta de monitoreo para el CEO:
    SELECT created_at, nombre, email, telefono, estado, notas
    FROM leads ORDER BY created_at DESC;
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


ALTERS = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS nombre VARCHAR(120);",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS estado VARCHAR(16) "
    "NOT NULL DEFAULT 'pendiente';",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS notas VARCHAR(500);",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;",
]

# Backfill: solo tiene efecto mientras la columna vieja exista (primera corrida).
BACKFILL = """
UPDATE leads
   SET estado = CASE WHEN contacted THEN 'contactado' ELSE 'pendiente' END
 WHERE estado IS NULL OR estado = 'pendiente';
"""

DROP_CONTACTED = "ALTER TABLE leads DROP COLUMN IF EXISTS contacted;"

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_leads_estado ON leads (estado);",
]


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
        if "leads" not in [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'leads'"
                )
            )
        ]:
            print("ERROR: la tabla `leads` no existe. Corre antes "
                  "migrate_sprint11_leads.py")
            return 1

        for sql in ALTERS:
            print(f"  -> {sql}")
            conn.execute(text(sql))
        for sql in INDEXES:
            print(f"  -> {sql}")
            conn.execute(text(sql))

        if "contacted" in _columnas(conn):
            print("  -> backfill estado <- contacted")
            conn.execute(text(BACKFILL))
            print(f"  -> {DROP_CONTACTED}")
            conn.execute(text(DROP_CONTACTED))
        else:
            print("  -> `contacted` ya no existe (nada que backfillear)")

    with engine.connect() as conn:
        cols = _columnas(conn)
        print(f"\nleads columnas: {', '.join(cols) or '(no existe)'}")
        faltan = [c for c in ("nombre", "estado", "notas", "updated_at") if c not in cols]
        if faltan:
            print(f"ERROR: faltan columnas: {', '.join(faltan)}")
            return 1
        if "contacted" in cols:
            print("ERROR: la columna `contacted` sigue existiendo")
            return 1
        total, pendientes = conn.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE estado = 'pendiente') "
                "FROM leads"
            )
        ).one()
        print(f"leads: {total} filas, {pendientes} pendientes")

    print("Migración #297 OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
