"""Agrega a `bot_llm_decisions` el consumo de tokens de cada turno.

La tabla guardaba rondas y latencia pero no lo que costó el turno, así que el
gasto real solo se podía saber corriendo un benchmark aparte (ver
`RESULTADOS_PRUEBAS_MODELO_MASCOTAS.html`). Con estas cuatro columnas el panel
puede decir lo que costó de verdad cada conversación.

`cache_read` es además el termómetro del prompt caching activado en #363: si se
va a cero de forma sostenida, el prefijo dejó de ser estable y el ahorro del
~68% se perdió sin que nadie se entere.

Todas nullable: las filas viejas no tienen de dónde sacar el dato y un 0 mentiría
(diría "costó cero", no "no se sabe").

Idempotente (`ADD COLUMN IF NOT EXISTS`): se puede correr las veces que sea.
Hay que aplicarlo en los DOS entornos en el mismo PR — regla de paridad del CEO.

    # local
    docker compose -p wati exec -T -w /app -e PYTHONPATH=/app backend \
        python scripts/migrate_tokens_llm_decisions.py
    # producción
    TASKDEF=multiagente-backend:NN ./backend/scripts/rds_exec.sh \
        backend/scripts/migrate_tokens_llm_decisions.py
"""
from sqlalchemy import text

from app.database import SessionLocal

COLUMNAS = [
    ("tokens_in", "INTEGER"),
    ("tokens_out", "INTEGER"),
    ("cache_read", "INTEGER"),
    ("cache_write", "INTEGER"),
]


def main() -> int:
    db = SessionLocal()
    try:
        for nombre, tipo in COLUMNAS:
            db.execute(text(
                f"ALTER TABLE bot_llm_decisions ADD COLUMN IF NOT EXISTS {nombre} {tipo}"
            ))
            print(f"  -> {nombre} {tipo}")
        db.commit()

        presentes = db.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'bot_llm_decisions' "
            "AND column_name IN ('tokens_in','tokens_out','cache_read','cache_write') "
            "ORDER BY column_name"
        )).scalars().all()
        print(f"Verificación: {len(presentes)}/4 columnas presentes -> {presentes}")
        return 0 if len(presentes) == 4 else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
