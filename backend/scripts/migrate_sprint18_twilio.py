"""Migración Sprint 18: generaliza `meta_accounts` a multi-proveedor (Meta/Twilio)
y añade `campaign_recipients.provider_message_id`.

Diseño:
  - 100% idempotente (`ADD COLUMN IF NOT EXISTS`, `DROP NOT NULL`, backfill
    condicional). Re-ejecutable sin efectos secundarios.
  - Sin pérdida de datos: sólo añade columnas y relaja NOT NULL de las columnas
    Meta (porque una fila 'twilio' no las usa).
  - Backfill de `provider_message_id` desde `meta_message_id` para no perder la
    correlación de campañas ya enviadas.

Uso:
    # Local
    docker compose exec backend python scripts/migrate_sprint18_twilio.py

    # RDS (vía ECS run-task override, ver BITACORA Sprint 15 #195 / Sprint 18 #223)

Follow-up: migrar a Alembic (abierto desde Sprint 7).
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


# (tabla, columna, tipo)
ADD_COLUMNS: list[tuple[str, str, str]] = [
    ("meta_accounts", "provider", "VARCHAR(16) NOT NULL DEFAULT 'meta'"),
    ("meta_accounts", "twilio_account_sid", "VARCHAR(64)"),
    ("meta_accounts", "encrypted_twilio_auth_token", "TEXT"),
    ("meta_accounts", "twilio_messaging_service_sid", "VARCHAR(64)"),
    ("meta_accounts", "twilio_from", "VARCHAR(32)"),
    ("campaign_recipients", "provider_message_id", "VARCHAR(128)"),
]

# Columnas Meta que pasan a nullable (una cuenta 'twilio' no las usa).
DROP_NOT_NULL: list[tuple[str, str]] = [
    ("meta_accounts", "phone_number_id"),
    ("meta_accounts", "waba_id"),
    ("meta_accounts", "encrypted_access_token"),
]


def _parse_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _existing_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = :t"
        ),
        {"t": table},
    ).fetchall()
    return {r[0] for r in rows}


def main() -> int:
    host = _parse_host(DATABASE_URL)
    print(f"Conectando a host: {host or '(desconocido)'}")

    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        # 1) Añadir columnas nuevas.
        for table, column, col_type in ADD_COLUMNS:
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type};"
            print(f"  -> {sql}")
            conn.execute(text(sql))

        # 2) Relajar NOT NULL de columnas Meta (idempotente).
        for table, column in DROP_NOT_NULL:
            sql = f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL;"
            print(f"  -> {sql}")
            conn.execute(text(sql))

        # 3) Backfill de provider_message_id desde meta_message_id.
        res = conn.execute(
            text(
                "UPDATE campaign_recipients SET provider_message_id = meta_message_id "
                "WHERE provider_message_id IS NULL AND meta_message_id IS NOT NULL;"
            )
        )
        print(f"  -> backfill provider_message_id: {res.rowcount} filas")

        # 4) Índice para correlación de callbacks por provider_message_id.
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_recipients_provider_message_id "
                "ON campaign_recipients (provider_message_id);"
            )
        )
        print("  -> CREATE INDEX IF NOT EXISTS ix_recipients_provider_message_id")

    # 5) Verificación.
    with engine.connect() as conn:
        ma_cols = _existing_columns(conn, "meta_accounts")
        cr_cols = _existing_columns(conn, "campaign_recipients")
        print()
        print(f"meta_accounts: {sorted(ma_cols)}")
        print(f"campaign_recipients provider_message_id: {'provider_message_id' in cr_cols}")

        missing = [
            f"{t}.{c}"
            for t, c, _ in ADD_COLUMNS
            if c not in (ma_cols if t == "meta_accounts" else cr_cols)
        ]
        if missing:
            print(f"ERROR: siguen faltando columnas: {missing}")
            return 1

    print()
    print("OK: migración Sprint 18 aplicada (o ya estaba aplicada).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
