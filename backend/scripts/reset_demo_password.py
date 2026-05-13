"""Reset idempotente de la password de `demo@gmail.com` a `Demo2026!`.

Sprint 13 #169 — el password documentado en CREDENCIALES.txt no funcionaba
(reportado en #164). Este script fija un password conocido y estable para
la cuenta demo del entorno local.

Comportamiento:
  - Si el user `demo@gmail.com` no existe → aborta con código 1.
  - Si existe → actualiza `hashed_password` con bcrypt(`Demo2026!`).
  - Idempotente: re-ejecutar deja la misma password (sólo refresca el hash).

Uso:
    docker compose exec -T backend python scripts/reset_demo_password.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud  # type: ignore


DEMO_EMAIL = "demo@gmail.com"
DEMO_PASSWORD = "Demo2026!"


def main() -> int:
    db = SessionLocal()
    try:
        user = crud.get_user_by_email(db, DEMO_EMAIL)
        if user is None:
            print(f"ERROR: usuario {DEMO_EMAIL} no existe. Crea la cuenta primero.")
            return 1

        user.hashed_password = crud.pwd_context.hash(DEMO_PASSWORD)
        db.add(user)
        db.commit()
        # Verificar
        ok = crud.pwd_context.verify(DEMO_PASSWORD, user.hashed_password)
        print(f"Password reset OK para {DEMO_EMAIL}. Verify={ok}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
