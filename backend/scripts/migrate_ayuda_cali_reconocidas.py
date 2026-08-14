"""Migración sprint "Ayuda a Cali" (4ª parte): estados de reconocimiento.

Cuando alguien dice en el chat "esa es mi mascota" y el bot le entrega el
contacto, el caso deja de estar simplemente activo — pero tampoco está resuelto:
es una afirmación sin verificar. Hasta ahora eso no quedaba en ningún lado y el
equipo no sabía a quién llamar para confirmar.

Añade:
  - Estado `reconocida` ("reconocido, por confirmar"), entre `activo` y
    `reunida` (que pasa a significar "reencuentro confirmado por el equipo").
  - `reconocida_at` / `reconocida_chat` → cuándo y desde qué conversación.

Idempotente. Se corre en local y en RDS en el mismo PR (convención #1).

Uso:
    docker compose -p wati exec -T backend python scripts/migrate_ayuda_cali_reconocidas.py
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


SENTENCIAS = [
    "ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS reconocida_at TIMESTAMP;",
    "ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS reconocida_chat VARCHAR(64);",
    # El CHECK viejo no admite el estado nuevo: se reemplaza.
    "ALTER TABLE mascotas DROP CONSTRAINT IF EXISTS ck_mascotas_estado;",
    "ALTER TABLE mascotas ADD CONSTRAINT ck_mascotas_estado "
    "CHECK (estado IN ('activo','reconocida','reunida','cerrado'));",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_reconocida_at ON mascotas (reconocida_at);",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        for sql in SENTENCIAS:
            print(f"  -> {sql}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        cols = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='mascotas' "
                    "AND column_name IN ('reconocida_at','reconocida_chat')"
                )
            )
        ]
        print(f"\ncolumnas nuevas: {', '.join(sorted(cols)) or '(ninguna)'}")
        if len(cols) != 2:
            return 1
        # El CHECK debe aceptar el estado nuevo.
        conn.execute(text("SELECT 1 FROM mascotas WHERE estado = 'reconocida' LIMIT 1"))
    print('\nMigración "Ayuda a Cali" (reconocidas) OK.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
