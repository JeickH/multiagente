"""Sprint 22 #318 — Columna `teams.modo`: demo vs producción.

Marca cada tenant como cuenta de **demostración** o cuenta **en producción**.
No es una etiqueta decorativa: los adaptadores de mensajería tratan a un team
`demo` como sandbox permanente, así que una cuenta de demostración nunca le
escribe a un número real ni consume cuota del WABA, aunque tenga credenciales
válidas y `TWILIO_SANDBOX=0`.

Idempotente: `ADD COLUMN IF NOT EXISTS` + backfill defensivo. El default es
`'demo'` a propósito — un tenant nuevo no envía hasta que se le promueva.

Para promover teams a producción, pasa sus ids separados por coma:
    PRODUCCION_TEAM_IDS=5

Uso local:
    docker compose exec -T -e PRODUCCION_TEAM_IDS=9 backend \
        python scripts/migrate_sprint22_team_modo.py

Uso en RDS:
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_sprint22_team_modo.py \
        PRODUCCION_TEAM_IDS=5
"""
from __future__ import annotations

import os
import sys

if "__file__" in globals():  # no existe cuando corre vía `python -c`
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import text  # type: ignore

from app.database import SessionLocal  # type: ignore

DDL = [
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS modo VARCHAR(16) NOT NULL DEFAULT 'demo'",
    # Backfill defensivo por si la columna existía como nullable de una corrida previa.
    "UPDATE teams SET modo = 'demo' WHERE modo IS NULL",
    "CREATE INDEX IF NOT EXISTS ix_teams_modo ON teams (modo)",
]


def main() -> int:
    db = SessionLocal()
    try:
        for sentencia in DDL:
            db.execute(text(sentencia))
        db.commit()

        crudos = (os.environ.get("PRODUCCION_TEAM_IDS") or "").strip()
        if crudos:
            ids = [int(x) for x in crudos.split(",") if x.strip().isdigit()]
            if ids:
                db.execute(
                    text("UPDATE teams SET modo='produccion' WHERE id = ANY(:ids)"),
                    {"ids": ids},
                )
                db.commit()

        filas = db.execute(
            text("SELECT id, nombre, modo FROM teams ORDER BY id")
        ).fetchall()
        print("teams tras la migración:")
        for f in filas:
            print(f"  id={f[0]:<3} modo={f[2]:<11} {f[1]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
