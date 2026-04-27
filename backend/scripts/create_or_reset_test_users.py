"""Crea o resetea credenciales de cuentas de prueba.

Idempotente:
  - Si el user no existe → lo crea con un password aleatorio.
  - Si ya existe → resetea su `hashed_password` y conserva el resto de
    su data (teams, bots, meta accounts, conversaciones, leads, etc.).
  - Asegura que tenga un team owner (si no, lo provisiona).

Override de password: si la env var `OVERRIDE_<EMAIL_KEY>_PWD` está
seteada, usa ese password en vez de generar uno aleatorio. Útil para
re-aplicar el mismo password si te lo perdiste.

Uso (local):
    docker compose exec backend python backend/scripts/create_or_reset_test_users.py

Uso (RDS): se ejecuta dentro de un task ECS one-off con la imagen del
backend (ver docs de despliegue).

Salida: imprime una tabla por stdout con "correo<TAB>password<TAB>nuevo|reset".
"""
from __future__ import annotations

import os
import secrets
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import crud, models  # type: ignore


# Las cuentas a (re)crear. `documento` solo se usa al crear; si ya existe,
# se respeta el que tenga la BD.
ACCOUNTS = [
    {"correo": "prueba@gmail.com", "nombre": "Usuario Prueba",  "tipo_documento": "CC", "documento": "PRUEBA001"},
    {"correo": "test2@gmail.com",  "nombre": "Tenant Sin Meta", "tipo_documento": "CC", "documento": "TEST0002"},
    {"correo": "otro@test.com",    "nombre": "Otro Test",       "tipo_documento": "CC", "documento": "OTRO0001"},
    {"correo": "demo@gmail.com",   "nombre": "Demo Gloma",      "tipo_documento": "CC", "documento": "DEMO0001"},
]


def _gen_password() -> str:
    """14 chars URL-safe (a-z, A-Z, 0-9, -, _). Fuerte y escribible."""
    return secrets.token_urlsafe(10)[:14]


def _ensure_team(db, user: models.User) -> None:
    if crud.get_membership_for_user(db, user) is None:
        crud.create_team(db, nombre=f"Equipo de {user.nombre}", owner=user)


def upsert(db, account: dict) -> tuple[str, str, str]:
    """Devuelve (correo, password_plano, accion)."""
    correo = account["correo"]
    env_key = f"OVERRIDE_{correo.replace('@', '_AT_').replace('.', '_DOT_').upper()}_PWD"
    password = os.environ.get(env_key) or _gen_password()

    existing = crud.get_user_by_email(db, correo)
    if existing:
        existing.hashed_password = crud.pwd_context.hash(password)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        _ensure_team(db, existing)
        return (correo, password, "reset")

    # Crea con UserCreate-like dict
    from app import schemas  # type: ignore
    new_user = crud.create_user(
        db,
        schemas.UserCreate(
            nombre=account["nombre"],
            tipo_documento=account["tipo_documento"],
            documento=account["documento"],
            correo=correo,
            password=password,
        ),
    )
    _ensure_team(db, new_user)
    return (correo, password, "nuevo")


def main() -> int:
    db = SessionLocal()
    try:
        results = [upsert(db, acc) for acc in ACCOUNTS]
        print("\n=== CREDENCIALES ===")
        print(f"{'correo':<28}{'password':<20}accion")
        for correo, pwd, action in results:
            print(f"{correo:<28}{pwd:<20}{action}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
