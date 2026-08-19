"""Reinicia las guías interactivas (tutoriales) de una cuenta por su correo.

Las guías de la app (`TutorialOverlay`) se muestran una sola vez por módulo:
al terminarlas u omitirlas, el frontend hace
`PATCH /usuario/me/tutorials/{modulo}` y el estado queda guardado en
`users.tutorials_completed` (JSONB). Este script borra ese estado para que al
usuario le vuelvan a aparecer, que es lo que se necesita al entregar la cuenta
a una persona nueva o al hacer una demo.

Módulos con guía: mi_plan, mensajes, bots, campanas
(whitelist en `app.schemas.ALLOWED_TUTORIAL_MODULES`).

Uso:
    # Local — OJO: el proyecto de compose se llama `wati` (es el que tiene el
    # volumen con la base local). Sin `-p wati`, docker busca contenedores del
    # proyecto `gloma_software`, que no existen, y responde
    # "service backend is not running".
    docker compose -p wati exec -T backend python scripts/reset_tutoriales.py correo@dominio.com

    # Solo algunos módulos
    docker compose -p wati exec -T backend python scripts/reset_tutoriales.py correo@dominio.com --modulos mensajes,campanas

    # Ver el estado actual sin modificar nada
    docker compose -p wati exec -T backend python scripts/reset_tutoriales.py correo@dominio.com --ver

    # Producción (RDS), vía ECS run-task. `rds_exec.sh` manda este archivo como
    # cuerpo de un `python -c`, así que no hay argv: los datos van en env vars.
    ./backend/scripts/rds_exec.sh backend/scripts/reset_tutoriales.py CORREO=correo@dominio.com
    ./backend/scripts/rds_exec.sh backend/scripts/reset_tutoriales.py CORREO=correo@dominio.com MODULOS=mensajes,campanas
    ./backend/scripts/rds_exec.sh backend/scripts/reset_tutoriales.py CORREO=correo@dominio.com VER=1

    El correo no es un secreto, así que puede viajar en el override de ECS
    (que queda en CloudTrail); una contraseña no podría.

Idempotente: re-ejecutarlo deja el mismo resultado (estado vacío = guías
pendientes). No toca ninguna otra columna del usuario.
"""
from __future__ import annotations

import argparse
import os
import sys

# `rds_exec.sh` manda este archivo como el cuerpo de un `python -c`, donde
# `__file__` no existe; ahí el código ya corre desde /app dentro del contenedor.
_RAIZ = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "__file__" in globals()
    else "/app"
)
sys.path.insert(0, _RAIZ)

from sqlalchemy.orm.attributes import flag_modified  # type: ignore

from app import crud  # type: ignore
from app.database import SessionLocal  # type: ignore
from app.schemas import ALLOWED_TUTORIAL_MODULES  # type: ignore


MODULOS = sorted(ALLOWED_TUTORIAL_MODULES)


def _estado(valor: dict | None) -> str:
    """Describe en una línea el estado de un módulo."""
    if not valor:
        return "pendiente (la guía se mostrará)"
    if valor.get("done"):
        return f"completada el {valor.get('completed_at') or '?'}"
    if valor.get("skipped"):
        return f"omitida el {valor.get('completed_at') or '?'}"
    return "pendiente (la guía se mostrará)"


def _imprimir_estado(titulo: str, actual: dict) -> None:
    print(f"\n{titulo}")
    for modulo in MODULOS:
        print(f"  · {modulo:<9} → {_estado(actual.get(modulo))}")


def _opciones() -> tuple[str, str, bool]:
    """(correo, modulos, ver) desde la línea de comandos o desde el entorno.

    En local se corre con argumentos. En producción va por `rds_exec.sh`, que
    lo ejecuta como `python -c` sin argv: ahí los datos llegan por env vars
    (`CORREO`, `MODULOS`, `VER`). El correo no es un secreto, así que puede
    viajar en el override de ECS sin problema.
    """
    if len(sys.argv) > 1:
        parser = argparse.ArgumentParser(
            description="Reinicia las guías interactivas de una cuenta para que vuelvan a aparecer.",
        )
        parser.add_argument("correo", help="Correo de la cuenta (ej: usuario@dominio.com)")
        parser.add_argument(
            "--modulos",
            default="",
            help=f"Lista separada por comas. Por defecto, todos: {','.join(MODULOS)}",
        )
        parser.add_argument(
            "--ver",
            action="store_true",
            help="Solo muestra el estado actual, sin modificar nada.",
        )
        args = parser.parse_args()
        return args.correo, args.modulos, args.ver

    correo = os.environ.get("CORREO", "")
    if not correo:
        sys.exit(
            "Falta el correo: pásalo como argumento (uso local) o en la env var "
            "CORREO (uso vía rds_exec.sh)."
        )
    return correo, os.environ.get("MODULOS", ""), os.environ.get("VER", "") == "1"


def main() -> int:
    correo_in, modulos_in, solo_ver = _opciones()

    correo = correo_in.strip().lower()

    if modulos_in.strip():
        pedidos = [m.strip() for m in modulos_in.split(",") if m.strip()]
        desconocidos = [m for m in pedidos if m not in ALLOWED_TUTORIAL_MODULES]
        if desconocidos:
            print(f"ERROR: módulo(s) no válido(s): {', '.join(desconocidos)}")
            print(f"Válidos: {', '.join(MODULOS)}")
            return 2
        objetivo = pedidos
    else:
        objetivo = MODULOS

    db = SessionLocal()
    try:
        user = crud.get_user_by_email(db, correo)
        if user is None:
            # Sin filtrar si el correo existe o no en otra forma: mensaje simple.
            print(f"ERROR: no existe una cuenta con el correo {correo}.")
            return 1

        actual = dict(user.tutorials_completed or {})
        _imprimir_estado(f"Estado actual de {correo} (user_id={user.id}):", actual)

        if solo_ver:
            print("\n(--ver: no se modificó nada)")
            return 0

        nuevos = {k: v for k, v in actual.items() if k not in objetivo}
        if nuevos == actual:
            print(f"\nNada que reiniciar: {', '.join(objetivo)} ya estaban pendientes.")
            return 0

        user.tutorials_completed = nuevos
        flag_modified(user, "tutorials_completed")
        db.add(user)
        db.commit()
        db.refresh(user)

        _imprimir_estado("Estado después del reinicio:", dict(user.tutorials_completed or {}))
        print(
            "\nListo. La próxima vez que "
            f"{correo} abra esos módulos, la guía interactiva arrancará sola."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
