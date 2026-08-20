"""Apaga (o vuelve a prender) una cuenta, sin borrarla.

Apagar una cuenta hace dos cosas, y hacen falta las dos:
  1. `users.activo = false` — no entra, y el token que ya tenga deja de servir
     en el siguiente request (lo corta `dependencies.get_current_user`).
  2. Le quita todos los permisos de su membresía — para que si alguien la
     vuelve a prender, no reviva con los permisos de antes por descuido.

Nada se borra: el usuario, su membresía y el rastro de qué conversaciones
atendió quedan intactos. Volver a prenderla es `--activar` (los permisos se
vuelven a dar a mano, a propósito).

Uso:
    docker compose -p wati exec -T backend python scripts/desactivar_cuenta.py \\
        --correo arranquemospues.asesor@gmail.com

    ./backend/scripts/rds_exec.sh backend/scripts/desactivar_cuenta.py \\
        CORREO='arranquemospues.asesor@gmail.com'
"""
from __future__ import annotations

import argparse
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

from app import crud, models  # type: ignore
from app.database import SessionLocal  # type: ignore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--correo", default=os.environ.get("CORREO", ""))
    parser.add_argument(
        "--activar", action="store_true",
        help="vuelve a prender la cuenta (los permisos se dan aparte)",
    )
    args = parser.parse_args()
    if os.environ.get("ACTIVAR") == "1":
        args.activar = True

    if not args.correo:
        print("Falta --correo (o la variable CORREO).")
        return 1

    db = SessionLocal()
    try:
        user = crud.get_user_by_email(db, args.correo)
        if user is None:
            print(f"ERROR: no existe {args.correo} en esta base.")
            return 1

        objetivo = bool(args.activar)
        if user.activo == objetivo:
            print(f"  · {args.correo} ya estaba {'activa' if objetivo else 'desactivada'}")
        else:
            user.activo = objetivo
            db.add(user)
            print(f"  ✓ {args.correo} → {'ACTIVA' if objetivo else 'DESACTIVADA'}")

        if not objetivo:
            membresia = crud.get_membership_for_user(db, user)
            if membresia is not None:
                activos = [
                    k for k, v in crud.permissions_dict(membresia).items() if v
                ]
                if activos:
                    crud.set_member_permissions(
                        db, membresia, {k: False for k in models.AVAILABLE_PERMISSIONS}
                    )
                    print(f"  ✓ permisos revocados: {', '.join(sorted(activos))}")
                else:
                    print("  · no tenía permisos activos")

        db.commit()

        db.refresh(user)
        print(
            f"\nEstado final: {user.correo} activo={user.activo} "
            f"(id={user.id}, sus datos e historial siguen en la base)"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
