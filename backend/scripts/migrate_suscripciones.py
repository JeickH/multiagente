"""Migración: suscripción mensual con cobro automático por Wompi.

Añade dos tablas:
  - `subscriptions`        → una fila por team, con la tarjeta guardada en
                             Wompi (`payment_source_id`) y la fecha del
                             próximo cobro.
  - `subscription_charges` → un intento de cobro por fila. Los reintentos de
                             un mismo mes comparten `scheduled_for` y se
                             distinguen por `attempt`.

100% idempotente (`CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`).
Sólo añade: no borra ni reescribe nada.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_suscripciones.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_suscripciones.py

OJO (gotcha histórico): migrar la base NO basta. Si la imagen de ECS lleva un
`models.py` viejo, el ORM ni ve las tablas nuevas y los scripts que las
escriben reportan cero filas en vez de fallar. Esta migración va con su
despliegue.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

# Se puede invocar de tres formas: `python scripts/x.py` desde `backend/`,
# copiado a cualquier ruta del contenedor, o como cuerpo de un `python -c`
# (rds_exec.sh) donde `__file__` ni existe. Probamos los candidatos y nos
# quedamos con el primero que tenga el paquete `app`.
_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Se busca el archivo, no la carpeta: desde `/` el directorio `/app` parece el
# paquete `app` (namespace package de Python 3) y el import se va por ahí, para
# fallar después con "No module named 'app.database'".
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


# `team_id` es UNIQUE: una fila por cuenta, para siempre. Cancelar cambia el
# `status`, no borra la fila ni crea otra — así el estado de una cuenta se lee
# sin desempatar entre filas viejas. El historial vive en la otra tabla.
TABLA_SUSCRIPCIONES = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id                  SERIAL PRIMARY KEY,
    team_id             INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    plan_key            VARCHAR(40) NOT NULL,
    status              VARCHAR(20) NOT NULL DEFAULT 'pending',
    amount_cents        INTEGER     NOT NULL,
    currency            VARCHAR(8)  NOT NULL DEFAULT 'COP',
    provider            VARCHAR(20) NOT NULL DEFAULT 'wompi',
    payment_source_id   INTEGER,
    card_brand          VARCHAR(20),
    card_last_four      VARCHAR(4),
    customer_email      VARCHAR(255),
    billing_day         INTEGER,
    next_charge_at      TIMESTAMP,
    last_charge_at      TIMESTAMP,
    activated_at        TIMESTAMP,
    canceled_at         TIMESTAMP,
    attempts            INTEGER     NOT NULL DEFAULT 0,
    created_by_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    canceled_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subscriptions_team UNIQUE (team_id),
    CONSTRAINT ck_subscriptions_status
        CHECK (status IN ('pending','active','past_due','canceled')),
    CONSTRAINT ck_subscriptions_amount CHECK (amount_cents > 0),
    CONSTRAINT ck_subscriptions_billing_day
        CHECK (billing_day IS NULL OR (billing_day >= 1 AND billing_day <= 31))
);
"""

# `reference` UNIQUE es el candado contra el webhook repetido de Wompi, que
# reintenta hasta 3 veces en 24 h. Es el mismo mecanismo de `credit_purchases`.
TABLA_COBROS = """
CREATE TABLE IF NOT EXISTS subscription_charges (
    id              SERIAL PRIMARY KEY,
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(id) ON DELETE CASCADE,
    team_id         INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    reference       VARCHAR(80) NOT NULL,
    amount_cents    INTEGER     NOT NULL,
    currency        VARCHAR(8)  NOT NULL DEFAULT 'COP',
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
    provider_tx_id  VARCHAR(80),
    scheduled_for   TIMESTAMP   NOT NULL,
    attempt         INTEGER     NOT NULL DEFAULT 1,
    failure_code    VARCHAR(40),
    paid_at         TIMESTAMP,
    created_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_subscription_charges_reference UNIQUE (reference),
    CONSTRAINT ck_subscription_charges_status
        CHECK (status IN ('pending','approved','declined','error','voided')),
    CONSTRAINT ck_subscription_charges_amount CHECK (amount_cents > 0)
);
"""

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_subscriptions_team_id ON subscriptions (team_id);",
    # El índice que usa el tick para encontrar a quién le toca cobrar hoy.
    "CREATE INDEX IF NOT EXISTS ix_subscriptions_next_charge_at ON subscriptions (next_charge_at);",
    "CREATE INDEX IF NOT EXISTS ix_subscription_charges_subscription_id ON subscription_charges (subscription_id);",
    "CREATE INDEX IF NOT EXISTS ix_subscription_charges_team_id ON subscription_charges (team_id);",
    "CREATE INDEX IF NOT EXISTS ix_subscription_charges_team_created ON subscription_charges (team_id, created_at);",
    "CREATE INDEX IF NOT EXISTS ix_subscription_charges_provider_tx_id ON subscription_charges (provider_tx_id);",
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
        conn.execute(text(TABLA_SUSCRIPCIONES))
        print("  ✓ tabla subscriptions")
        conn.execute(text(TABLA_COBROS))
        print("  ✓ tabla subscription_charges")
        for sql in INDICES:
            conn.execute(text(sql))
        print(f"  ✓ {len(INDICES)} índices")

    # Verificación: que quedó lo que decimos que quedó.
    with engine.connect() as conn:
        subs = conn.execute(text("SELECT to_regclass('public.subscriptions')")).scalar()
        cobros = conn.execute(
            text("SELECT to_regclass('public.subscription_charges')")
        ).scalar()
        columnas = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name='subscriptions'"
                )
            )
        }

    esperadas = {"payment_source_id", "next_charge_at", "billing_day", "attempts"}
    faltan = sorted(esperadas - columnas)
    if subs is None or cobros is None or faltan:
        print(
            f"ERROR: subscriptions={subs} subscription_charges={cobros} faltan={faltan}"
        )
        return 1
    print("OK: migración aplicada y verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
