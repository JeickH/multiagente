"""Migración: `users.activo` — poder apagar una cuenta sin borrarla.

Idempotente (`ADD COLUMN IF NOT EXISTS`): se puede correr las veces que haga
falta, en local y en RDS. Las filas existentes quedan en `true`, así que nadie
pierde el acceso por aplicarla.

Por qué una columna y no borrar el usuario: los mensajes, las conversaciones
atendidas y el historial cuelgan del usuario. Borrarlo se lleva por delante el
rastro de quién atendió qué; apagarlo no, y volver a prenderlo es un UPDATE.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_usuarios_activo.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_usuarios_activo.py
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
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS activo BOOLEAN NOT NULL DEFAULT true",
]


def main() -> int:
    db = SessionLocal()
    try:
        for sql in SENTENCIAS:
            db.execute(text(sql))
        db.commit()

        fila = db.execute(text(
            "SELECT count(*) AS total, count(*) FILTER (WHERE activo) AS activos "
            "FROM users"
        )).first()
        print(f"OK: users.activo aplicada — {fila.activos}/{fila.total} cuentas activas")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
