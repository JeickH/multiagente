"""Migración: facturas de la cuenta (`invoices`).

Añade UNA tabla. No toca `subscriptions` ni `subscription_charges`: la fecha
y el valor de la próxima factura se leen de `subscriptions.next_charge_at` y
`subscriptions.amount_cents`, que ya existen.

Por qué tabla nueva y no reusar `subscription_charges`, en corto: esa tabla
guarda INTENTOS de cobro atados a una suscripción (`subscription_id` NOT NULL)
y no tiene dónde decir qué se cobra. La factura de implementación no pertenece
a ninguna suscripción, y una factura tiene que sobrevivir a varios intentos de
pago. El razonamiento largo está en el docstring de `models.Invoice`.

100% idempotente: `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`.
Solo añade — no borra ni reescribe nada. Se puede correr dos veces seguidas.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_facturas.py

    # Producción (RDS) — lo corre el CEO
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_facturas.py

OJO (gotcha histórico): migrar la base NO basta. Si la imagen de ECS lleva un
`models.py` sin `Invoice`, el ORM ni ve la tabla y los scripts que le escriben
reportan cero filas en vez de fallar. Esta migración va con su despliegue.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

# Se puede invocar de tres formas: `python scripts/x.py` desde `backend/`,
# copiado a cualquier ruta del contenedor, o como cuerpo de un `python -c`
# (rds_exec.sh) donde `__file__` ni existe.
_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Se busca el archivo y no la carpeta: desde `/` el directorio `/app` parece el
# paquete `app` (namespace package de Python 3) y el import se va por ahí.
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


# `reference` UNIQUE es el candado contra el webhook repetido de Wompi, igual
# que en `credit_purchases` y `subscription_charges`. Es NULL hasta el primer
# intento de pago, y en Postgres los NULL no chocan entre sí en un índice
# único: pueden convivir mil facturas sin referencia.
#
# `issued_on` y `due_date` son DATE y no TIMESTAMP a propósito: una factura se
# vence un día, no a una hora. Guardar la hora obligaría a decidir en qué zona
# vence, que es de donde salen los "se venció un día antes" cuando el servidor
# está en UTC y el cliente en Colombia.
TABLA_FACTURAS = """
CREATE TABLE IF NOT EXISTS invoices (
    id              SERIAL PRIMARY KEY,
    team_id         INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    numero          VARCHAR(40)  NOT NULL,
    concepto        VARCHAR(160) NOT NULL,
    detalle         TEXT,
    amount_cents    INTEGER      NOT NULL,
    currency        VARCHAR(8)   NOT NULL DEFAULT 'COP',
    status          VARCHAR(20)  NOT NULL DEFAULT 'pendiente',
    issued_on       DATE         NOT NULL,
    due_date        DATE         NOT NULL,
    paid_at         TIMESTAMP,
    reference       VARCHAR(80),
    provider_tx_id  VARCHAR(80),
    intentos        INTEGER      NOT NULL DEFAULT 0,
    subscription_id INTEGER REFERENCES subscriptions(id) ON DELETE SET NULL,
    charge_id       INTEGER REFERENCES subscription_charges(id) ON DELETE SET NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_invoices_reference UNIQUE (reference),
    CONSTRAINT uq_invoices_team_numero UNIQUE (team_id, numero),
    CONSTRAINT ck_invoices_status
        CHECK (status IN ('pendiente','pagada','anulada')),
    CONSTRAINT ck_invoices_amount CHECK (amount_cents > 0)
);
"""

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_invoices_team_id ON invoices (team_id);",
    "CREATE INDEX IF NOT EXISTS ix_invoices_due_date ON invoices (due_date);",
    "CREATE INDEX IF NOT EXISTS ix_invoices_provider_tx_id ON invoices (provider_tx_id);",
    # El índice que sostiene las dos consultas de la pantalla: el listado del
    # administrador y el aviso de los 7 días, que ambas preguntan por las
    # pendientes de un team ordenadas por vencimiento.
    "CREATE INDEX IF NOT EXISTS ix_invoices_team_status_due "
    "ON invoices (team_id, status, due_date);",
]


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def main() -> int:
    print(f"Conectando a host: {_host(DATABASE_URL) or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text(TABLA_FACTURAS))
        print("  ✓ tabla invoices")
        for sql in INDICES:
            conn.execute(text(sql))
        print(f"  ✓ {len(INDICES)} índices")

    # Verificación: que quedó lo que decimos que quedó. Un script de migración
    # que solo imprime "listo" no distingue entre haber corrido y haber
    # funcionado.
    with engine.connect() as conn:
        tabla = conn.execute(text("SELECT to_regclass('public.invoices')")).scalar()
        columnas = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='invoices'"
                )
            )
        }

    esperadas = {
        "team_id", "numero", "concepto", "detalle", "amount_cents",
        "status", "issued_on", "due_date", "paid_at", "reference", "intentos",
    }
    faltan = sorted(esperadas - columnas)
    if tabla is None or faltan:
        print(f"ERROR: invoices={tabla} faltan={faltan}")
        return 1
    print("OK: migración aplicada y verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
