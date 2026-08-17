"""Migración: marca de optimización en `mascota_fotos`.

Añade las columnas que dejan saber, sin salir de la BD, si el peso de una foto
ya fue optimizado (`scripts/optimizar_fotos_mascotas.py`):

  - `optimizada`      BOOLEAN NOT NULL DEFAULT FALSE
  - `optimizada_at`   TIMESTAMP
  - `bytes_original`  INTEGER   (lo que pesaba antes de comprimir)

Idempotente (`ADD COLUMN IF NOT EXISTS`): se puede correr las veces que sea.

Local:
    docker compose -p wati exec -T backend python scripts/migrate_optimizacion_fotos.py
Producción (RDS, dentro de la VPC):
    TASKDEF=multiagente-backend:15 ./backend/scripts/rds_exec.sh \
        backend/scripts/migrate_optimizacion_fotos.py
"""

from sqlalchemy import text

from app.database import SessionLocal

SENTENCIAS = [
    "ALTER TABLE mascota_fotos ADD COLUMN IF NOT EXISTS optimizada BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE mascota_fotos ADD COLUMN IF NOT EXISTS optimizada_at TIMESTAMP",
    "ALTER TABLE mascota_fotos ADD COLUMN IF NOT EXISTS bytes_original INTEGER",
    "CREATE INDEX IF NOT EXISTS ix_mascota_fotos_optimizada ON mascota_fotos (optimizada)",
]


def main() -> None:
    db = SessionLocal()
    try:
        for sql in SENTENCIAS:
            db.execute(text(sql))
            print(f"OK  {sql}")
        db.commit()
        fila = db.execute(text(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE optimizada) AS ya "
            "FROM mascota_fotos"
        )).mappings().first()
        print(f"mascota_fotos: {fila['total']} fotos, {fila['ya']} ya optimizadas")
    finally:
        db.close()


main()
