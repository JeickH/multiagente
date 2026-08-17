"""Agrega a `mascotas` los campos que traen las fuentes y no estábamos usando.

Hasta ahora todo lo que no tenía columna propia terminaba concatenado dentro de
`notas`: la esterilización del PDF de RoyiPets, el departamento de PetSearch, el
peso y las vacunas de Protección Animal, la recompensa de Mascotas por Colombia.
Ahí no se puede filtrar, ni contar, ni cruzar. Estas 15 columnas son la unión de
lo que publican las seis fuentes — ver `documentacion_bd/mapeo_fuentes.md`.

Todas nullable y sin `server_default`: NULL significa "esta fuente no lo dice",
que no es lo mismo que False. Por eso no hay backfill implícito.

Idempotente (`ADD COLUMN IF NOT EXISTS`): se puede correr las veces que sea.
Hay que aplicarlo en los DOS entornos en el mismo PR — regla de paridad del CEO.

    # local
    docker compose -p wati exec -T -w /app -e PYTHONPATH=/app backend \
        python scripts/migrate_campos_multifuente.py
    # producción
    TASKDEF=multiagente-backend:NN ./backend/scripts/rds_exec.sh \
        backend/scripts/migrate_campos_multifuente.py
"""
from sqlalchemy import text

from app.database import SessionLocal

COLUMNAS = [
    ("ciudad", "VARCHAR(120)"),
    ("departamento", "VARCHAR(120)"),
    ("esterilizado", "BOOLEAN"),
    ("vacunado", "BOOLEAN"),
    ("desparasitado", "BOOLEAN"),
    ("peso_kg", "NUMERIC(5,2)"),
    ("salud", "VARCHAR(255)"),
    ("resguardo", "VARCHAR(40)"),
    ("resguardo_nombre", "VARCHAR(120)"),
    ("rescatado_por", "VARCHAR(120)"),
    ("rescatado_por_telefono", "VARCHAR(32)"),
    ("recompensa", "BOOLEAN"),
    ("estado_origen", "VARCHAR(60)"),
    ("publicado_origen_at", "TIMESTAMP"),
    ("sincronizado_at", "TIMESTAMP"),
]

# Solo lo que el panel va a filtrar de verdad. Un índice por columna nueva
# costaría escritura en cada importación sin que nadie lo use.
INDICES = [
    ("ix_mascotas_ciudad", "ciudad"),
    ("ix_mascotas_departamento", "departamento"),
    ("ix_mascotas_resguardo", "resguardo"),
]


def main() -> None:
    db = SessionLocal()
    try:
        existentes = {
            f[0] for f in db.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'mascotas'"
            )).all()
        }
        nuevas = 0
        for nombre, tipo in COLUMNAS:
            if nombre in existentes:
                print(f"=  {nombre} ya existía")
                continue
            db.execute(text(
                f"ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS {nombre} {tipo}"))
            print(f"+  {nombre} {tipo}")
            nuevas += 1
        for indice, columna in INDICES:
            db.execute(text(
                f"CREATE INDEX IF NOT EXISTS {indice} ON mascotas ({columna})"))
        db.commit()

        total = db.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_name = 'mascotas'")).scalar()
        filas = db.execute(text("SELECT count(*) FROM mascotas")).scalar()
        print(f"\nRESUMEN columnas_nuevas={nuevas} columnas_en_la_tabla={total} "
              f"filas={filas} (ninguna fila se modificó)")
    finally:
        db.close()


main()
