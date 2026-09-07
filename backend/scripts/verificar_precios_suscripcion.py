"""Qué precio de suscripción le corresponde hoy a cada cuenta.

Lee la base, resuelve el precio con la MISMA función que usa el cobro
(`suscripciones.precio_para`) y deja la fila creada/actualizada para las que
todavía están en `pending`. No cobra nada ni toca una suscripción activa.

Sirve para dos cosas:
  * comprobar, antes de que alguien le dé al botón, que a cada cuenta se le va
    a cobrar lo que se acordó — un typo en el correo de `PRECIO_POR_CUENTA`
    haría que la cuenta pagara el precio de lista sin que nadie se entere
    hasta ver el cobro;
  * dejar lista la fila de una cuenta que aún no ha abierto la pantalla.

Uso:
    ./backend/scripts/rds_exec.sh backend/scripts/verificar_precios_suscripcion.py

No usa `__file__` a propósito: `rds_exec.sh` manda el archivo como cuerpo de un
`python -c`, donde `__file__` no existe.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/app")

from app.database import SessionLocal  # type: ignore  # noqa: E402
from app import models  # type: ignore  # noqa: E402
from app.services import suscripciones as svc  # type: ignore  # noqa: E402


def main() -> int:
    db = SessionLocal()
    try:
        filas = (
            db.query(models.Team.id, models.Team.nombre, models.User.correo)
            .join(models.User, models.User.id == models.Team.owner_user_id)
            .order_by(models.Team.id)
            .all()
        )

        print(f"{'team':>4}  {'cuenta':38} {'precio/mes':>12}  {'estado':10} fuente")
        print("-" * 92)

        problemas = 0
        for team_id, nombre, correo in filas:
            esperado = svc.precio_para(correo)
            especial = (correo or "").strip().lower() in svc.PRECIO_POR_CUENTA
            fuente = "OVERRIDE" if especial else "lista"

            sub = svc.obtener_o_crear(db, team_id)
            real = sub.amount_cents

            # Una activa conserva su precio a propósito: no se le cambia por
            # detrás. Se reporta la diferencia en vez de "corregirla".
            if real != esperado and sub.status != models.SUBSCRIPTION_PENDING:
                fuente += f" (activa, conserva {real // 100:,})"
            elif real != esperado:
                fuente += " ¡NO CUADRA!"
                problemas += 1

            print(
                f"{team_id:>4}  {(correo or '?')[:38]:38} "
                f"${real // 100:>10,}  {sub.status:10} {fuente}"
            )

        print()
        if problemas:
            print(f"ERROR: {problemas} cuenta(s) con un precio que no cuadra.")
            return 1
        print("OK: cada cuenta tiene el precio que le corresponde.")
        return 0
    finally:
        db.close()


sys.exit(main())
