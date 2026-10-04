"""Factura de octubre de Arranquemos Pues y periodo de cobertura. Solo esa cuenta.

Qué pasó (2-oct-2026): ese día entraron DOS cobros de $350.000 por Wompi.

  · uno pagó FAC-2026-0002, la mensualidad de septiembre que estaba vencida;
  · el otro fue el primer cobro automático de la suscripción, al registrar la
    tarjeta (`subscription_charges`, referencia `glomasub-5-202610-…`): la
    mensualidad de octubre.

El ciclo de cobro no emite factura, así que el segundo quedó cobrado y sin
documento: en Pagos solo se veían la implementación y septiembre.

Qué deja (pedido del CEO, 4-oct-2026):

  · FAC-2026-0002 con periodo de cobertura 2-sep-2026 → 1-oct-2026;
  · FAC-2026-0003 «Suscripción mensual Gloma», $350.000, **pagada** el
    2-oct-2026, periodo 2-oct-2026 → 1-nov-2026, enlazada al cobro que la pagó.

**No cobra nada.** No llama a Wompi ni toca `subscriptions` ni
`subscription_charges`: solo lee el cobro aprobado y escribe en `invoices`.

Idempotente: el periodo solo se escribe si está vacío, y la factura de octubre
se reconoce por `charge_id`, así que correrlo dos veces no duplica nada.

Por defecto NO escribe: muestra lo que haría. Con `APLICAR=1` aplica.

Uso:
    # Local
    docker compose -p wati exec -T backend python scripts/facturas_arranquemos_octubre.py

    # Producción (RDS), después de migrar y desplegar el modelo con el periodo
    ./backend/scripts/rds_exec.sh backend/scripts/facturas_arranquemos_octubre.py
    ./backend/scripts/rds_exec.sh backend/scripts/facturas_arranquemos_octubre.py APLICAR=1
"""
from __future__ import annotations

import os
import sys
from datetime import date

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

#: El mismo correo que usa `seed_facturas_arranquemos.py`.
CORREO_ADMIN = "arranquemospues.marketing@gmail.com"

APLICAR = os.environ.get("APLICAR") == "1"

SEPTIEMBRE = ("FAC-2026-0002", date(2026, 9, 2), date(2026, 10, 1))
OCTUBRE_DESDE, OCTUBRE_HASTA = date(2026, 10, 2), date(2026, 11, 1)
MENSUALIDAD = 350_000 * 100


def main() -> int:
    print("Modo:", "APLICAR" if APLICAR else "simulación (APLICAR=1 para escribir)")
    db = SessionLocal()
    try:
        admin = crud.get_user_by_email(db, CORREO_ADMIN)
        if admin is None:
            print("No existe la cuenta en esta base. No se tocó nada.")
            return 0
        membresia = crud.get_membership_for_user(db, admin)
        if membresia is None:
            print("El administrador no pertenece a ningún equipo. No se tocó nada.")
            return 1
        team_id = membresia.team_id
        print(f"team_id={team_id}")

        # --- Septiembre: el periodo ---------------------------------------
        numero, desde, hasta = SEPTIEMBRE
        sep = (
            db.query(models.Invoice)
            .filter(models.Invoice.team_id == team_id, models.Invoice.numero == numero)
            .first()
        )
        if sep is None:
            print(f"ERROR: no está {numero}. No se tocó nada.")
            return 1
        if sep.amount_cents != MENSUALIDAD:
            print(f"ERROR: {numero} no es una mensualidad de $350.000. No se tocó nada.")
            return 1
        if sep.periodo_desde is None and sep.periodo_hasta is None:
            sep.periodo_desde, sep.periodo_hasta = desde, hasta
            print(f"  ✓ {numero}: periodo {desde} → {hasta}")
        else:
            print(f"  · {numero} ya tenía periodo {sep.periodo_desde} → {sep.periodo_hasta}")

        # --- Octubre: el cobro aprobado que no tiene factura ---------------
        sub = (
            db.query(models.Subscription)
            .filter(models.Subscription.team_id == team_id)
            .first()
        )
        cobros = (
            db.query(models.SubscriptionCharge)
            .filter(
                models.SubscriptionCharge.subscription_id == sub.id,
                models.SubscriptionCharge.status == models.SUBSCRIPTION_CHARGE_APPROVED,
                models.SubscriptionCharge.amount_cents == MENSUALIDAD,
                models.SubscriptionCharge.reference.like(f"glomasub-{team_id}-202610-%"),
            )
            .all()
        ) if sub else []
        if len(cobros) != 1:
            print(f"ERROR: se esperaba UN cobro aprobado de octubre y hay {len(cobros)}.")
            db.rollback()
            return 1
        cobro = cobros[0]
        print(
            f"  cobro de octubre: id={cobro.id} tx={cobro.provider_tx_id} "
            f"pagado={cobro.paid_at or cobro.updated_at}"
        )

        ya = (
            db.query(models.Invoice)
            .filter(models.Invoice.team_id == team_id, models.Invoice.charge_id == cobro.id)
            .first()
        )
        if ya is not None:
            print(f"  · ya existe {ya.numero} para ese cobro ({ya.status})")
        else:
            octubre = svc_facturas.emitir(
                db,
                team_id,
                concepto="Suscripción mensual Gloma",
                detalle="Acceso a la plataforma. Se factura cada mes.",
                amount_cents=MENSUALIDAD,
                issued_on=OCTUBRE_DESDE,
                due_date=OCTUBRE_DESDE,
                subscription_id=sub.id,
                periodo_desde=OCTUBRE_DESDE,
                periodo_hasta=OCTUBRE_HASTA,
            )
            # Pagada con el cobro que ya entró: mismo instante y misma
            # transacción de Wompi. No se cobra nada de nuevo.
            octubre.status = models.INVOICE_PAGADA
            octubre.paid_at = cobro.paid_at or cobro.updated_at
            octubre.provider_tx_id = cobro.provider_tx_id
            octubre.charge_id = cobro.id
            db.flush()
            print(
                f"  ✓ {octubre.numero} pagada el {octubre.paid_at} — periodo "
                f"{OCTUBRE_DESDE} → {OCTUBRE_HASTA}"
            )

        if APLICAR:
            db.commit()
            print("Cambios guardados.")
        else:
            db.rollback()
            print("Simulación: no se guardó nada.")

        for f in svc_facturas.listar(db, team_id):
            print(
                f"  {f.numero} | {f.concepto} | {svc_facturas.pesos(f.amount_cents)} | "
                f"{f.status} | pagada {f.paid_at} | periodo "
                f"{f.periodo_desde} → {f.periodo_hasta}"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
