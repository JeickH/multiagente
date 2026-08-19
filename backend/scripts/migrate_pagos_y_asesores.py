"""Migración: créditos de mensajes, pagos por Wompi y rotación de asesores.

Añade:
  - `teams.message_credits`     → saldo de mensajes para envíos masivos.
  - `teams.handoff_turno`       → turno del round-robin entre asesores.
  - `teams.asesores_rotacion`   → nombres de los asesores, en orden de turno.
  - tabla `credit_purchases`    → compras de paquetes de mensajes.

100% idempotente (`ADD COLUMN IF NOT EXISTS`, `CREATE TABLE IF NOT EXISTS`).
Sólo añade: no borra ni reescribe nada.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_pagos_y_asesores.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_pagos_y_asesores.py

OJO (gotcha histórico): migrar la base NO basta. Si la imagen de ECS lleva un
`models.py` viejo, el ORM ni ve las columnas nuevas y los scripts que las
escriben reportan cero filas en vez de fallar. Esta migración va con su
despliegue.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

# Se puede invocar de tres formas: `python scripts/x.py` desde `backend/`,
# copiado a cualquier ruta del contenedor, o como cuerpo de un `python -c`
# (rds_exec.sh) donde `__file__` ni existe. Probamos los candidatos y nos
# quedamos con el primero que tenga el paquete `app`.
_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Se busca el archivo, no la carpeta: desde `/` el directorio `/app` parece el
# paquete `app` (namespace package de Python 3) y el import se va por ahí, para
# fallar después con "No module named 'app.database'".
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


COLUMNAS: list[tuple[str, str, str]] = [
    ("teams", "message_credits", "INTEGER NOT NULL DEFAULT 0"),
    ("teams", "handoff_turno", "INTEGER NOT NULL DEFAULT 0"),
    ("teams", "asesores_rotacion", "JSONB NOT NULL DEFAULT '[]'::jsonb"),
]

TABLA_COMPRAS = """
CREATE TABLE IF NOT EXISTS credit_purchases (
    id                 SERIAL PRIMARY KEY,
    team_id            INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    package_key        VARCHAR(40)  NOT NULL,
    messages           INTEGER      NOT NULL,
    amount_cents       INTEGER      NOT NULL,
    currency           VARCHAR(8)   NOT NULL DEFAULT 'COP',
    reference          VARCHAR(80)  NOT NULL,
    provider           VARCHAR(20)  NOT NULL DEFAULT 'wompi',
    provider_tx_id     VARCHAR(80),
    status             VARCHAR(20)  NOT NULL DEFAULT 'pending',
    credited_at        TIMESTAMP,
    created_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_credit_purchases_reference UNIQUE (reference),
    CONSTRAINT ck_credit_purchases_status
        CHECK (status IN ('pending','approved','declined','error','voided')),
    CONSTRAINT ck_credit_purchases_messages CHECK (messages > 0),
    CONSTRAINT ck_credit_purchases_amount   CHECK (amount_cents > 0)
);
"""

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_credit_purchases_team_id ON credit_purchases (team_id);",
    "CREATE INDEX IF NOT EXISTS ix_credit_purchases_team_created ON credit_purchases (team_id, created_at);",
    "CREATE INDEX IF NOT EXISTS ix_credit_purchases_provider_tx_id ON credit_purchases (provider_tx_id);",
]


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def main() -> int:
    print(f"Conectando a host: {_host(DATABASE_URL) or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for tabla, columna, tipo in COLUMNAS:
            conn.execute(
                text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {columna} {tipo};")
            )
            print(f"  ✓ {tabla}.{columna}")

        conn.execute(text(TABLA_COMPRAS))
        print("  ✓ tabla credit_purchases")
        for sql in INDICES:
            conn.execute(text(sql))
        print(f"  ✓ {len(INDICES)} índices")

    # Verificación: que quedó lo que decimos que quedó.
    with engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='teams'"
                )
            )
        }
        faltan = [c for _, c, _ in COLUMNAS if c not in cols]
        existe_tabla = conn.execute(
            text("SELECT to_regclass('public.credit_purchases')")
        ).scalar()

    if faltan or existe_tabla is None:
        print(f"ERROR: faltan columnas={faltan} tabla_compras={existe_tabla}")
        return 1
    print("OK: migración aplicada y verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
