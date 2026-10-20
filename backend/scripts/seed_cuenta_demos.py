"""Seed idempotente: la cuenta dueña de las demos públicas (Sprint 32, #613).

Cada prospecto que arma una demo en `glomacx.com/demo` recibe un `Bot` nuevo,
y todos esos bots cuelgan de UNA sola cuenta: `demos@glomacx.com` (user + team).
No se crea un usuario por prospecto.

Qué crea / asegura:
  - El usuario `demos@glomacx.com` (o `DEMO_OWNER_EMAIL`), sin rol de admin:
    no es la cuenta de Gloma (`require_gloma_account`) ni está en
    `SUPERVISION_CUENTAS`, y este script no la agrega a ninguna.
  - Su team, en modo `demo` (el default: un envío a WhatsApp desde esta cuenta
    sería simulado siempre).

Qué NO crea, a propósito (#608 M6): ni `MetaAccount` ni sender de Twilio. Sin
canal conectado, ningún mensaje entrante puede llegar a un bot de demo; además
`bot_router` ignora los bots con `llm_config.demo`. Si el script encuentra un
canal conectado a la cuenta, lo reporta y sale con código 2.

Contraseña: nunca en el repo ni en un log (el repositorio es público).
  - `DEMOS_PWD_HASH='$2b$12$...'` → se usa ese hash bcrypt (la contraseña vive
    en el gestor del CEO).
  - Sin la variable → hash bcrypt de un secreto aleatorio que nadie conoce: la
    cuenta existe pero no se puede entrar con contraseña. Se habilita después
    con un UPDATE del hash, sin recrear nada.
  Si el usuario ya existía, su contraseña no se toca.

Este seed NO corre en el arranque del backend (ningún seed lo hace: el
Dockerfile solo levanta uvicorn). Se corre una vez por entorno, después de
`migrate_demos.py`.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/seed_cuenta_demos.py

    # Producción (RDS) vía ECS run-task. Solo el HASH, nunca la contraseña:
    # los overrides de ECS quedan en CloudTrail.
    ./backend/scripts/rds_exec.sh backend/scripts/seed_cuenta_demos.py \\
        DEMOS_PWD_HASH='$2b$12$...'

ENV:
    DEMO_OWNER_EMAIL   (default demos@glomacx.com; el router lee la misma)
    DEMOS_PWD_HASH     (opcional, solo al crear la cuenta)
"""
from __future__ import annotations

import os
import re
import secrets
import sys

# `rds_exec.sh` manda este archivo como el cuerpo de un `python -c`, donde
# `__file__` no existe; ahí el código ya corre desde /app dentro del contenedor.
_RAIZ = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "__file__" in globals()
    else "/app"
)
sys.path.insert(0, _RAIZ)

from app.database import SessionLocal  # type: ignore
from app import crud, models  # type: ignore

OWNER_EMAIL = (os.environ.get("DEMO_OWNER_EMAIL") or "demos@glomacx.com").strip().lower()
OWNER_NAME = "Gloma — Demos públicas"
DOCUMENTO = "GLOMADEMOS1"

_BCRYPT_RE = re.compile(r"^\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}$")


def _hash_inicial() -> str:
    """El hash con el que nace la cuenta. Nunca se imprime."""
    dado = (os.environ.get("DEMOS_PWD_HASH") or "").strip()
    if dado:
        if not _BCRYPT_RE.match(dado):
            sys.exit("DEMOS_PWD_HASH no tiene formato bcrypt ($2b$12$...).")
        print("OK: la cuenta nace con el hash de DEMOS_PWD_HASH")
        return dado
    print("OK: sin DEMOS_PWD_HASH → contraseña inutilizable (nadie la conoce)")
    return crud.pwd_context.hash(secrets.token_urlsafe(32))


def _asegurar_usuario(db) -> models.User:
    user = crud.get_user_by_email(db, OWNER_EMAIL)
    if user is not None:
        print("OK: la cuenta de demos ya existía (contraseña sin tocar)")
        return user
    user = models.User(
        nombre=OWNER_NAME,
        tipo_documento="NIT",
        documento=DOCUMENTO,
        correo=OWNER_EMAIL,
        hashed_password=_hash_inicial(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"OK: cuenta de demos creada user_id={user.id}")
    return user


def _canales_conectados(db, team: models.Team) -> int:
    """MetaAccount del team (Meta o Twilio). Debe ser cero."""
    return (
        db.query(models.MetaAccount)
        .filter(models.MetaAccount.team_id == team.id)
        .count()
    )


def main() -> int:
    db = SessionLocal()
    try:
        owner = _asegurar_usuario(db)
        team = crud.get_team_by_owner(db, owner)
        if team is None:
            team = crud.create_team(db, OWNER_NAME, owner)
            print(f"OK: team creado team_id={team.id} modo={team.modo}")
        else:
            print(f"OK: team ya existía team_id={team.id} modo={team.modo}")

        if team.modo != models.TEAM_MODO_DEMO:
            print(
                f"AVISO: el team está en modo {team.modo!r}; las demos esperan "
                f"{models.TEAM_MODO_DEMO!r}. No se cambia solo: revisar a mano."
            )
        canales = _canales_conectados(db, team)
        if canales:
            print(
                f"ERROR: la cuenta de demos tiene {canales} canal(es) conectado(s). "
                "Debe tener cero (#608 M6)."
            )
            return 2
        bots = db.query(models.Bot).filter(models.Bot.user_id == owner.id).count()
        print(f"OK: sin canales conectados; bots de demo existentes={bots}")
        print("=== Cuenta de demos lista ===")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
