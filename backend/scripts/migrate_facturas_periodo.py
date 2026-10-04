"""Migración: periodo de cobertura de las facturas (`invoices`).

Añade dos columnas DATE nulables, `periodo_desde` y `periodo_hasta`, y un
CHECK que impide un periodo al revés. No toca ninguna fila: las facturas que ya
existen quedan con el periodo en NULL hasta que alguien lo ponga.

Por qué dos fechas y no un texto ("septiembre 2026"): una mensualidad que se
activa el 2 cubre del 2 al 1 del mes siguiente, que no es un mes calendario.
Con texto libre no se puede validar ni ordenar, y el PDF y la pantalla lo
pintarían cada uno a su manera.

100% idempotente: `ADD COLUMN IF NOT EXISTS` y el CHECK se crea solo si no
está. Solo añade — no borra ni reescribe nada. Se puede correr dos veces.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_facturas_periodo.py

    # Producción (RDS): run-task con la task-def nueva y
    # command=["python","scripts/migrate_facturas_periodo.py"]

OJO (gotcha histórico): migrar la base NO basta. Si la imagen de ECS lleva un
`models.py` sin estas columnas, el ORM ni las ve y los scripts que les
escriben reportan cero filas en vez de fallar. Esta migración va con su
despliegue — y el despliegue va DESPUÉS de ella, o el ORM pide columnas que no
existen.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


COLUMNAS = [
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS periodo_desde DATE;",
    "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS periodo_hasta DATE;",
]

# Postgres no tiene `ADD CONSTRAINT IF NOT EXISTS`: se pregunta antes.
CHECK_PERIODO = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ck_invoices_periodo'
    ) THEN
        ALTER TABLE invoices ADD CONSTRAINT ck_invoices_periodo CHECK (
            periodo_desde IS NULL OR periodo_hasta IS NULL
            OR periodo_desde <= periodo_hasta
        );
    END IF;
END $$;
"""


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def main() -> int:
    print(f"Conectando a host: {_host(DATABASE_URL) or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for sql in COLUMNAS:
            conn.execute(text(sql))
        print(f"  ✓ {len(COLUMNAS)} columnas")
        conn.execute(text(CHECK_PERIODO))
        print("  ✓ check ck_invoices_periodo")

    with engine.connect() as conn:
        columnas = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='invoices'"
                )
            )
        }
        check = conn.execute(
            text("SELECT 1 FROM pg_constraint WHERE conname='ck_invoices_periodo'")
        ).scalar()

    faltan = sorted({"periodo_desde", "periodo_hasta"} - columnas)
    if faltan or not check:
        print(f"ERROR: faltan={faltan} check={'sí' if check else 'no'}")
        return 1
    print("OK: migración aplicada y verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
