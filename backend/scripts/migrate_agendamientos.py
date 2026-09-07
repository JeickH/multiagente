"""Migración: tabla `agendamientos` (llamadas de rescate de chats abandonados).

Una fila por cliente potencial que dejó la conversación a medias **después de
haber recibido información**. La escribe el bot solo, desde
`app/services/agendamientos.py`, cuando da la conversación por abandonada; la
lee la ventana `/agendamientos`.

Idempotente (`CREATE TABLE/INDEX IF NOT EXISTS`). Se corre en local y en RDS en
el mismo PR (convención #1 de paridad de esquemas).

Ojo con el índice `uq_agendamientos_conv_pendiente`: es **parcial**. Impide que
un mismo chat tenga dos llamadas pendientes a la vez (dos ticks simultáneos, o
una persona que vuelve, se calla y el bot la vuelve a abandonar), pero deja
pasar una nueva cuando la anterior ya está cerrada — eso es una oportunidad
nueva, no un duplicado.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_agendamientos.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_agendamientos.py
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


DDL = """
CREATE TABLE IF NOT EXISTS agendamientos (
    id SERIAL PRIMARY KEY,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    nivel_interes VARCHAR(24) NOT NULL DEFAULT 'con_informacion',
    fecha_llamada DATE NOT NULL,
    estado VARCHAR(16) NOT NULL DEFAULT 'pendiente',
    asesor VARCHAR(64),
    cerrado_at TIMESTAMP,
    cerrado_por_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_agendamientos_team_id "
    "ON agendamientos (team_id);",
    "CREATE INDEX IF NOT EXISTS ix_agendamientos_conversation_id "
    "ON agendamientos (conversation_id);",
    "CREATE INDEX IF NOT EXISTS ix_agendamientos_fecha_llamada "
    "ON agendamientos (fecha_llamada);",
    "CREATE INDEX IF NOT EXISTS ix_agendamientos_estado "
    "ON agendamientos (estado);",
    # El que usa la pantalla: "lo de este team, por fecha de llamada".
    "CREATE INDEX IF NOT EXISTS ix_agendamientos_team_fecha "
    "ON agendamientos (team_id, fecha_llamada);",
    # Parcial: una sola llamada PENDIENTE por conversación (ver encabezado).
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_agendamientos_conv_pendiente "
    "ON agendamientos (conversation_id) WHERE estado = 'pendiente';",
]

COLUMNAS_ESPERADAS = {
    "id", "team_id", "conversation_id", "nivel_interes", "fecha_llamada",
    "estado", "asesor", "cerrado_at", "cerrado_por_user_id",
    "created_at", "updated_at",
}


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        print("  -> CREATE TABLE IF NOT EXISTS agendamientos")
        conn.execute(text(DDL))
        for sql in INDEXES:
            print(f"  -> {sql.split(' ON ')[0]}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'agendamientos'"
                )
            )
        }
        faltan = COLUMNAS_ESPERADAS - cols
        if faltan:
            print(f"\nFALTAN columnas en agendamientos: {', '.join(sorted(faltan))}")
            return 1
        print(f"\nagendamientos columnas: {', '.join(sorted(cols))}")

        indices = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'agendamientos' ORDER BY indexname"
                )
            )
        ]
        print(f"agendamientos índices: {', '.join(indices)}")
        if "uq_agendamientos_conv_pendiente" not in indices:
            print("FALTA el índice único parcial de una llamada por conversación.")
            return 1

    print("\nMigración `agendamientos` OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
