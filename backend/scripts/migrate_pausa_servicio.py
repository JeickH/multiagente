"""Migración: `teams.pausa_servicio` — pausar el servicio por falta de pago.

Idempotente (`ADD COLUMN IF NOT EXISTS` y el CHECK solo si no existe): se puede
correr las veces que haga falta, en local y en RDS. Todas las cuentas quedan en
`nunca`, así que aplicarla **no pausa a nadie**: la pausa se enciende después,
cuenta por cuenta, con un UPDATE que ordena el CEO.

    -- pausar ya (orden manual)
    UPDATE teams SET pausa_servicio = 'pausada'  WHERE id = <team_id>;
    -- que se pause sola al cumplir un mes de mora
    UPDATE teams SET pausa_servicio = 'por_mora' WHERE id = <team_id>;
    -- reanudar / nunca pausar
    UPDATE teams SET pausa_servicio = 'nunca'    WHERE id = <team_id>;

El DEFAULT va en la base y no solo en el modelo, por el gotcha de
`create_all()`: una tabla creada sin él haría fallar los INSERT de equipos
nuevos por el NOT NULL.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_pausa_servicio.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_pausa_servicio.py
"""
from __future__ import annotations

import os
import sys

# Se busca el archivo y no la carpeta: desde `/` el directorio `/app` parece el
# paquete `app` (namespace package) y el import se iría por ahí.
_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from sqlalchemy import text  # type: ignore

from app.database import SessionLocal  # type: ignore


SENTENCIAS = [
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS pausa_servicio VARCHAR(16) "
    "NOT NULL DEFAULT 'nunca'",
    # Por si la columna ya existía sin DEFAULT (create_all de una imagen nueva).
    "ALTER TABLE teams ALTER COLUMN pausa_servicio SET DEFAULT 'nunca'",
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'ck_teams_pausa_servicio'
        ) THEN
            ALTER TABLE teams ADD CONSTRAINT ck_teams_pausa_servicio
                CHECK (pausa_servicio IN ('nunca', 'por_mora', 'pausada'));
        END IF;
    END $$;
    """,
]


def main() -> int:
    db = SessionLocal()
    try:
        for sql in SENTENCIAS:
            db.execute(text(sql))
        db.commit()

        filas = db.execute(text(
            "SELECT pausa_servicio, count(*) AS n FROM teams "
            "GROUP BY pausa_servicio ORDER BY pausa_servicio"
        )).all()
        resumen = ", ".join(f"{f.pausa_servicio}={f.n}" for f in filas)
        default = db.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name = 'teams' AND column_name = 'pausa_servicio'"
        )).scalar()
        check = db.execute(text(
            "SELECT count(*) FROM pg_constraint WHERE conname = 'ck_teams_pausa_servicio'"
        )).scalar()
        print(
            f"OK: teams.pausa_servicio aplicada — {resumen} · "
            f"default={default} · check={'sí' if check else 'NO'}"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
