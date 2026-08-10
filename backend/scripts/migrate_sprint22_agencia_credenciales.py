"""Sprint 22 — Reasigna correo y password de la cuenta demo de la agencia de viajes.

La cuenta `agencia@demo.com` (dueña del team "Agencia de Viajes Arranquemos
Pues") pasa a usar el buzón real del CEO para la demo comercial:
`arranquemospues.contacto@gmail.com`, con password nueva.

Comportamiento (idempotente):
  - Busca al usuario por el correo NUEVO; si ya existe, sólo refresca password.
  - Si no, lo busca por el correo VIEJO y le cambia el correo + password.
  - Si no encuentra ninguno de los dos → sale con código 1 sin tocar nada.
  - Nunca imprime la password (regla de seguridad #1); sólo confirma el verify.

La password se pasa por env var `AGENCIA_PWD`, o ya hasheada en
`AGENCIA_PWD_HASH` (preferido para RDS: los overrides de ECS quedan en
CloudTrail, así que allí nunca viaja el plaintext). Los correos se pueden
sobrescribir con `AGENCIA_EMAIL_OLD` / `AGENCIA_EMAIL_NEW`.

Uso local:
    docker compose exec -T -e AGENCIA_PWD='...' backend \
        python scripts/migrate_sprint22_agencia_credenciales.py

Uso en RDS (el script aún no está en la imagen de ECR, así que va inline):
    ./backend/scripts/rds_exec.sh \
        backend/scripts/migrate_sprint22_agencia_credenciales.py \
        AGENCIA_PWD_HASH='$2b$12$...'
"""
from __future__ import annotations

import os
import sys

if "__file__" in globals():  # no existe cuando corre vía `python -c`
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud  # type: ignore

EMAIL_OLD = os.environ.get("AGENCIA_EMAIL_OLD", "agencia@demo.com")
EMAIL_NEW = os.environ.get("AGENCIA_EMAIL_NEW", "arranquemospues.contacto@gmail.com")


def main() -> int:
    pwd = os.environ.get("AGENCIA_PWD")
    pwd_hash = os.environ.get("AGENCIA_PWD_HASH")
    if not pwd and not pwd_hash:
        print("ERROR: falta la env var AGENCIA_PWD (o AGENCIA_PWD_HASH).")
        return 1

    db = SessionLocal()
    try:
        user = crud.get_user_by_email(db, EMAIL_NEW)
        accion = "password-refresh"
        if user is None:
            user = crud.get_user_by_email(db, EMAIL_OLD)
            accion = "rename+password"
        if user is None:
            print(f"ERROR: no existe ni {EMAIL_OLD} ni {EMAIL_NEW}.")
            return 1

        user.correo = EMAIL_NEW
        user.hashed_password = pwd_hash or crud.pwd_context.hash(pwd)
        db.add(user)
        db.commit()
        db.refresh(user)

        # Con hash precalculado no tenemos el plaintext para verificar; nos
        # basta con confirmar que quedó guardado un hash bcrypt válido.
        ok = (
            crud.pwd_context.verify(pwd, user.hashed_password)
            if pwd
            else crud.pwd_context.identify(user.hashed_password) == "bcrypt"
        )
        print(
            f"OK ({accion}) user_id={user.id} nombre={user.nombre!r} "
            f"correo={user.correo} verify={ok}"
        )
        return 0 if ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
