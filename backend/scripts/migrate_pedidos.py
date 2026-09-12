"""Migración idempotente: tabla `pedidos`.

Los pedidos que cierra el bot cuando el cliente manda nombre, dirección y
pedido. Van a la hoja de cálculo del equipo y también aquí, que es de donde los
lee la ventana de Pedidos de la app.

Idempotente (`IF NOT EXISTS` en todo): se puede correr las veces que sea.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_pedidos.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_pedidos.py

Paridad local ↔ RDS (regla permanente del CEO): se aplica en los dos entornos
en el mismo PR, y el despliegue de la imagen va junto — una tabla nueva que el
`models.py` desplegado no conoce es peor que no tenerla, porque los scripts que
la escriben no fallan, reportan cero.
"""
from __future__ import annotations

import os
import sys

_RAIZ = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "__file__" in globals()
    else "/app"
)
sys.path.insert(0, _RAIZ)

from sqlalchemy import text  # type: ignore

from app.database import SessionLocal  # type: ignore


DDL = [
    """
    CREATE TABLE IF NOT EXISTS pedidos (
        id              SERIAL PRIMARY KEY,
        team_id         INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
        nombre          VARCHAR(120) NOT NULL,
        direccion       VARCHAR(250) NOT NULL,
        detalle         TEXT NOT NULL,
        total           VARCHAR(40),
        telefono        VARCHAR(32),
        origen          VARCHAR(24) NOT NULL DEFAULT 'whatsapp',
        estado          VARCHAR(16) NOT NULL DEFAULT 'pendiente',
        en_hoja         BOOLEAN NOT NULL DEFAULT FALSE,
        created_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
        updated_at      TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
        CONSTRAINT ck_pedidos_estado
            CHECK (estado IN ('pendiente','despachado','cancelado'))
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_pedidos_team_id ON pedidos (team_id)",
    "CREATE INDEX IF NOT EXISTS ix_pedidos_conversation_id ON pedidos (conversation_id)",
    "CREATE INDEX IF NOT EXISTS ix_pedidos_estado ON pedidos (estado)",
    "CREATE INDEX IF NOT EXISTS ix_pedidos_created_at ON pedidos (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_pedidos_team_creado ON pedidos (team_id, created_at)",
]


def main() -> int:
    db = SessionLocal()
    try:
        for sentencia in DDL:
            db.execute(text(sentencia))
        db.commit()

        columnas = db.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'pedidos' ORDER BY ordinal_position"
            )
        ).scalars().all()
        filas = db.execute(text("SELECT COUNT(*) FROM pedidos")).scalar()
        print(f"OK: tabla `pedidos` con {len(columnas)} columnas, {filas} fila(s)")
        print("    " + ", ".join(columnas))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
