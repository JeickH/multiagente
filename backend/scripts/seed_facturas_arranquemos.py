"""Carga las facturas iniciales de Arranquemos Pues. Solo esa cuenta.

Qué deja (pedido del CEO, 16-sep-2026):

  · $1.000.000 — Implementación de la plataforma · vence el 2-sep-2026
  · $350.000   — Suscripción mensual              · vence el 2-sep-2026
  · próxima factura: 2-oct-2026 por $350.000

El millón es de una sola vez: es el cobro de la implementación y no se repite.
De octubre en adelante la cuenta solo ve los $350.000 del mes.

**A ninguna otra cuenta se le carga nada.** El script busca la cuenta por
correo y si no la encuentra se sale sin tocar la base; no recorre teams.

Idempotente: cada factura se reconoce por `(team_id, numero)` y por su
concepto, así que correrlo dos veces no duplica nada ni pisa una factura que
ya se pagó. Lo mismo con la próxima fecha: no se toca una suscripción que ya
esté activa, porque ahí la fecha la manda el ciclo de cobro real.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/seed_facturas_arranquemos.py

    # Producción (RDS) — lo corre el CEO, después de migrar y desplegar
    ./backend/scripts/rds_exec.sh backend/scripts/seed_facturas_arranquemos.py

Requiere `migrate_facturas.py` aplicado y la imagen desplegada con el
`models.py` que trae `Invoice`: sin eso el ORM no ve la tabla y esto reporta
cero en vez de fallar (gotcha conocido).
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime

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
from app.services import facturas as svc_facturas  # type: ignore
from app.services import suscripciones as svc_suscripciones  # type: ignore

#: El correo del administrador de la cuenta. Es el mismo que ya usa
#: `configurar_arranquemos_pues.py` — no se inventa uno nuevo (regla 8: este
#: repo es público y los correos de personas reales no se escriben acá).
CORREO_ADMIN = "arranquemospues.marketing@gmail.com"

VENCIMIENTO = date(2026, 9, 2)
PROXIMA = date(2026, 10, 2)

#: Las dos facturas a emitir. En centavos, que es como los quiere Wompi y como
#: los guarda la tabla.
FACTURAS = [
    {
        "concepto": "Implementación de la plataforma",
        "detalle": (
            "Puesta en marcha de la cuenta: conexión de WhatsApp, montaje del "
            "bot de atención y capacitación del equipo. Cobro por una sola vez."
        ),
        "amount_cents": 1_000_000 * 100,
    },
    {
        "concepto": "Suscripción mensual Gloma",
        "detalle": "Acceso a la plataforma. Se factura cada mes.",
        "amount_cents": 350_000 * 100,
    },
]


def main() -> int:
    db = SessionLocal()
    try:
        admin = crud.get_user_by_email(db, CORREO_ADMIN)
        if admin is None:
            print(f"No existe {CORREO_ADMIN} en esta base. No se tocó nada.")
            return 0

        membresia = crud.get_membership_for_user(db, admin)
        if membresia is None:
            print("El administrador no pertenece a ningún equipo. No se tocó nada.")
            return 1

        team_id = membresia.team_id
        team = db.query(models.Team).filter(models.Team.id == team_id).first()
        print(f"Cuenta: {team.nombre if team else team_id} (team_id={team_id})")

        # --- Las dos facturas pendientes -----------------------------------
        for datos in FACTURAS:
            ya = (
                db.query(models.Invoice)
                .filter(
                    models.Invoice.team_id == team_id,
                    models.Invoice.concepto == datos["concepto"],
                )
                .first()
            )
            if ya is not None:
                print(f"  · ya existía: {ya.numero} — {ya.concepto} ({ya.status})")
                continue

            factura = svc_facturas.emitir(
                db,
                team_id,
                concepto=datos["concepto"],
                detalle=datos["detalle"],
                amount_cents=datos["amount_cents"],
                issued_on=VENCIMIENTO,
                due_date=VENCIMIENTO,
            )
            db.commit()
            print(
                f"  ✓ {factura.numero} — {factura.concepto} "
                f"{svc_facturas.pesos(factura.amount_cents)} "
                f"vence {factura.due_date}"
            )

        # --- La próxima factura --------------------------------------------
        # Vive en `subscriptions`, que ya tiene `next_charge_at` y
        # `amount_cents`: no hizo falta columna nueva. La fila queda en
        # `pending` (sin tarjeta registrada), y el tick de cobro solo mira las
        # `active`/`past_due` — así se anuncia la fecha sin disparar un cobro.
        sub = svc_suscripciones.obtener_o_crear(db, team_id)
        if sub.status in (models.SUBSCRIPTION_ACTIVE, models.SUBSCRIPTION_PAST_DUE):
            print(
                f"  · la suscripción ya está {sub.status}: la fecha del próximo "
                "cobro la manda el ciclo real, no este script."
            )
        else:
            sub.billing_day = PROXIMA.day
            # 9 a. m. hora de Colombia: una hora del día laboral, para que al
            # pasarla a UTC no se corra de día en ninguna dirección.
            sub.next_charge_at = svc_suscripciones._a_utc_naive(
                datetime(
                    PROXIMA.year, PROXIMA.month, PROXIMA.day, 9, 0,
                    tzinfo=svc_suscripciones.ZONA_COLOMBIA,
                )
            )
            db.commit()
            print(
                f"  ✓ próxima factura: {PROXIMA} por "
                f"{svc_facturas.pesos(sub.amount_cents)}"
            )

        # --- Verificación ---------------------------------------------------
        pendientes = svc_facturas.pendientes(db, team_id)
        total = sum(f.amount_cents for f in pendientes)
        print(
            f"\nPendientes: {len(pendientes)} por {svc_facturas.pesos(total)}. "
            f"Aviso de mora: {'sí' if svc_facturas.debe_avisar(db, team_id) else 'no'}."
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
