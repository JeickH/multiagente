"""Migración idempotente Sprint 13: módulo Campañas + Plantillas WhatsApp + Contactos/Grupos.

Crea 7 tablas nuevas (en orden de dependencias FK):
  1. contacts
  2. contact_groups
  3. contact_group_members            (FK -> contact_groups, contacts)
  4. whatsapp_templates               (FK -> meta_accounts)
  5. campaigns                        (FK -> teams, meta_accounts, whatsapp_templates, users)
  6. campaign_recipients              (FK -> campaigns, contacts)
  7. campaign_events                  (FK -> campaigns, campaign_recipients)

Todo el DDL es idempotente (`IF NOT EXISTS`) y se aplica dentro de una sola
transacción (`engine.begin()`). Si algo falla, la transacción se aborta y se
imprime un error sanitizado (no PII, no secretos).

Contrato: refleja exactamente el DDL del documento
    backend/docs/sprint13_schema.md  (tarea #156, aprobado por Seguridad en #157).

Uso:
    # Local (docker-compose, recomendado — usa el mismo .env del backend):
    docker compose exec backend python scripts/migrate_sprint13_campanas.py

    # O directamente con env propio:
    DATABASE_URL=postgresql://multiagente_user:***@localhost:5432/multiagente_db \\
        python backend/scripts/migrate_sprint13_campanas.py
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Permite ejecutar como `python scripts/migrate_sprint13_campanas.py`
# desde el directorio backend/ o como `python backend/scripts/...` desde la raíz.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# DATABASE_URL: env var explícita tiene prioridad; fallback al builder del backend
# que ya carga `.env` vía python-dotenv (mismo patrón que migrate_sprint*).
_DATABASE_URL_FROM_ENV = os.environ.get("DATABASE_URL")
if _DATABASE_URL_FROM_ENV:
    DATABASE_URL = _DATABASE_URL_FROM_ENV
else:
    from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


# Lista de (nombre_tabla, statement). Las tablas se aplican primero, luego los
# índices. Mantener el orden por FKs.
TABLE_STATEMENTS: list[tuple[str, str]] = [
    (
        "contacts",
        """
        CREATE TABLE IF NOT EXISTS contacts (
            id              SERIAL       PRIMARY KEY,
            team_id         INTEGER      NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            phone_e164      VARCHAR(20)  NOT NULL,
            name            VARCHAR(120),
            email           VARCHAR(255),
            attributes      JSONB        NOT NULL DEFAULT '{}'::jsonb,
            opt_in          BOOLEAN      NOT NULL DEFAULT TRUE,
            opt_in_source   VARCHAR(50),
            created_at      TIMESTAMP    NOT NULL DEFAULT now(),
            updated_at      TIMESTAMP    NOT NULL DEFAULT now(),
            CONSTRAINT uq_contacts_team_phone UNIQUE (team_id, phone_e164),
            CONSTRAINT ck_contacts_phone_e164 CHECK (phone_e164 ~ '^\\+[1-9][0-9]{6,18}$')
        );
        """,
    ),
    (
        "contact_groups",
        """
        CREATE TABLE IF NOT EXISTS contact_groups (
            id           SERIAL       PRIMARY KEY,
            team_id      INTEGER      NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            name         VARCHAR(120) NOT NULL,
            description  TEXT,
            created_at   TIMESTAMP    NOT NULL DEFAULT now(),
            CONSTRAINT uq_contact_groups_team_name UNIQUE (team_id, name)
        );
        """,
    ),
    (
        "contact_group_members",
        """
        CREATE TABLE IF NOT EXISTS contact_group_members (
            group_id    INTEGER     NOT NULL REFERENCES contact_groups(id) ON DELETE CASCADE,
            contact_id  INTEGER     NOT NULL REFERENCES contacts(id)       ON DELETE CASCADE,
            added_at    TIMESTAMP   NOT NULL DEFAULT now(),
            PRIMARY KEY (group_id, contact_id)
        );
        """,
    ),
    (
        "whatsapp_templates",
        """
        CREATE TABLE IF NOT EXISTS whatsapp_templates (
            id                 SERIAL       PRIMARY KEY,
            meta_account_id    INTEGER      NOT NULL REFERENCES meta_accounts(id) ON DELETE CASCADE,
            meta_template_id   VARCHAR(64),
            name               VARCHAR(120) NOT NULL,
            category           VARCHAR(40),
            language           VARCHAR(20)  NOT NULL,
            status             VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
            components_json    JSONB        NOT NULL,
            rejection_reason   TEXT,
            last_synced_at     TIMESTAMP,
            created_at         TIMESTAMP    NOT NULL DEFAULT now(),
            CONSTRAINT uq_templates_account_name_lang UNIQUE (meta_account_id, name, language),
            CONSTRAINT ck_templates_status CHECK (
                status IN ('PENDING','APPROVED','REJECTED','DISABLED','PAUSED','DELETED')
            ),
            CONSTRAINT ck_templates_category CHECK (
                category IS NULL OR category IN ('MARKETING','UTILITY','AUTHENTICATION')
            )
        );
        """,
    ),
    (
        "campaigns",
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id                        SERIAL       PRIMARY KEY,
            team_id                   INTEGER      NOT NULL REFERENCES teams(id)              ON DELETE CASCADE,
            meta_account_id           INTEGER      NOT NULL REFERENCES meta_accounts(id)      ON DELETE RESTRICT,
            template_id               INTEGER      NOT NULL REFERENCES whatsapp_templates(id) ON DELETE RESTRICT,
            name                      VARCHAR(120) NOT NULL,
            status                    VARCHAR(20)  NOT NULL DEFAULT 'draft',
            scheduled_at              TIMESTAMP,
            started_at                TIMESTAMP,
            completed_at              TIMESTAMP,
            template_variables_json   JSONB        NOT NULL DEFAULT '{}'::jsonb,
            created_by_user_id        INTEGER      REFERENCES users(id) ON DELETE SET NULL,
            created_at                TIMESTAMP    NOT NULL DEFAULT now(),
            CONSTRAINT ck_campaigns_status CHECK (
                status IN ('draft','scheduled','running','completed','failed','cancelled')
            )
        );
        """,
    ),
    (
        "campaign_recipients",
        """
        CREATE TABLE IF NOT EXISTS campaign_recipients (
            id                SERIAL       PRIMARY KEY,
            campaign_id       INTEGER      NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            contact_id        INTEGER      NOT NULL REFERENCES contacts(id)  ON DELETE RESTRICT,
            phone_e164        VARCHAR(20)  NOT NULL,
            meta_message_id   VARCHAR(80),
            status            VARCHAR(20)  NOT NULL DEFAULT 'queued',
            error_code        VARCHAR(40),
            sent_at           TIMESTAMP,
            delivered_at      TIMESTAMP,
            read_at           TIMESTAMP,
            failed_at         TIMESTAMP,
            CONSTRAINT uq_recipients_campaign_contact   UNIQUE (campaign_id, contact_id),
            CONSTRAINT uq_recipients_meta_message_id    UNIQUE (meta_message_id),
            CONSTRAINT ck_recipients_status CHECK (
                status IN ('queued','sending','sent','delivered','read','failed','skipped')
            )
        );
        """,
    ),
    (
        "campaign_events",
        """
        CREATE TABLE IF NOT EXISTS campaign_events (
            id                SERIAL       PRIMARY KEY,
            campaign_id       INTEGER      NOT NULL REFERENCES campaigns(id)            ON DELETE CASCADE,
            recipient_id      INTEGER               REFERENCES campaign_recipients(id)  ON DELETE CASCADE,
            event_type        VARCHAR(30)  NOT NULL,
            payload_json      JSONB,
            meta_message_id   VARCHAR(80),
            created_at        TIMESTAMP    NOT NULL DEFAULT now(),
            CONSTRAINT ck_events_type CHECK (
                event_type IN ('queued','sent','delivered','read','failed','clicked','sync_warning')
            )
        );
        """,
    ),
]


INDEX_STATEMENTS: list[str] = [
    # contacts
    "CREATE INDEX IF NOT EXISTS ix_contacts_team_id        ON contacts(team_id);",
    "CREATE INDEX IF NOT EXISTS ix_contacts_team_name      ON contacts(team_id, name);",
    "CREATE INDEX IF NOT EXISTS ix_contacts_attributes_gin ON contacts USING GIN (attributes);",
    # contact_groups
    "CREATE INDEX IF NOT EXISTS ix_contact_groups_team_id ON contact_groups(team_id);",
    # contact_group_members
    "CREATE INDEX IF NOT EXISTS ix_contact_group_members_contact ON contact_group_members(contact_id);",
    # whatsapp_templates
    "CREATE INDEX IF NOT EXISTS ix_templates_account_status ON whatsapp_templates(meta_account_id, status);",
    "CREATE INDEX IF NOT EXISTS ix_templates_meta_template  ON whatsapp_templates(meta_template_id);",
    "CREATE INDEX IF NOT EXISTS ix_templates_pending_sync   ON whatsapp_templates(last_synced_at) "
    "WHERE status = 'PENDING';",
    # campaigns
    "CREATE INDEX IF NOT EXISTS ix_campaigns_team_status         ON campaigns(team_id, status);",
    "CREATE INDEX IF NOT EXISTS ix_campaigns_status_scheduled    ON campaigns(status, scheduled_at) "
    "WHERE status = 'scheduled';",
    "CREATE INDEX IF NOT EXISTS ix_campaigns_team_created        ON campaigns(team_id, created_at DESC);",
    # campaign_recipients
    "CREATE INDEX IF NOT EXISTS ix_recipients_meta_message_id ON campaign_recipients(meta_message_id);",
    "CREATE INDEX IF NOT EXISTS ix_recipients_campaign_status ON campaign_recipients(campaign_id, status);",
    # campaign_events
    "CREATE INDEX IF NOT EXISTS ix_events_campaign_type      ON campaign_events(campaign_id, event_type);",
    "CREATE INDEX IF NOT EXISTS ix_events_meta_message_id    ON campaign_events(meta_message_id);",
    "CREATE INDEX IF NOT EXISTS ix_events_campaign_created   ON campaign_events(campaign_id, created_at DESC);",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_events_dedupe "
    "ON campaign_events(meta_message_id, event_type) "
    "WHERE meta_message_id IS NOT NULL;",
]


SPRINT13_TABLES: list[str] = [name for name, _ in TABLE_STATEMENTS]


def _sanitize_error(exc: BaseException) -> str:
    """Recorta el mensaje de error para no filtrar URL completa con credenciales.

    El mensaje de SQLAlchemy puede incluir el DSN; nos quedamos sólo con la
    primera línea y eliminamos cualquier substring `:password@` por precaución.
    """
    msg = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    # Defensa-en-profundidad: nunca propagar credenciales en stdout.
    import re

    msg = re.sub(r"://[^/\s@]+:[^/\s@]+@", "://***:***@", msg)
    return msg[:300]


def main() -> int:
    print("[sprint13] Aplicando migración...")

    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"[sprint13] Host de conexión: {host or '(desconocido)'}")

    engine = create_engine(DATABASE_URL)

    try:
        with engine.begin() as conn:
            # 1) Snapshot de tablas existentes para reportar created/skipped.
            existing_before: set[str] = set(
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = current_schema() "
                        "  AND table_name = ANY(:names)"
                    ),
                    {"names": SPRINT13_TABLES},
                ).fetchall()
            )

            # 2) Tablas (en orden de FKs).
            for table_name, ddl in TABLE_STATEMENTS:
                if table_name in existing_before:
                    print(f"[sprint13]   - {table_name:24s}  ya existía → skip")
                else:
                    print(f"[sprint13]   - {table_name:24s}  CREATE TABLE")
                conn.execute(text(ddl))

            # 3) Índices (al final, después de todos los CREATE TABLE).
            print(f"[sprint13] Creando {len(INDEX_STATEMENTS)} índices (idempotente)...")
            for stmt in INDEX_STATEMENTS:
                conn.execute(text(stmt))

    except SQLAlchemyError as exc:
        print(f"[sprint13] ERROR: fallo en la migración: {_sanitize_error(exc)}")
        print("[sprint13] Transacción abortada. Ningún cambio aplicado.")
        return 1
    except Exception as exc:  # noqa: BLE001 — queremos catch-all sanitizado.
        print(f"[sprint13] ERROR inesperado: {_sanitize_error(exc)}")
        return 2

    # 4) Verificación post-aplicación: las 7 tablas deben existir.
    try:
        with engine.connect() as conn:
            present = set(
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema = current_schema() "
                        "  AND table_name = ANY(:names)"
                    ),
                    {"names": SPRINT13_TABLES},
                ).fetchall()
            )
        missing = [t for t in SPRINT13_TABLES if t not in present]
        if missing:
            print(f"[sprint13] ERROR: tablas no presentes tras migración: {missing}")
            return 3
        print(f"[sprint13] Verificación OK: {len(present)}/7 tablas presentes "
              f"({sorted(present)}).")
    except SQLAlchemyError as exc:
        print(f"[sprint13] ADVERTENCIA: verificación falló: {_sanitize_error(exc)}")
        # No revertimos — la migración ya commiteó. Pero salimos != 0 para visibilidad.
        return 4

    print("[sprint13] Migración aplicada exitosamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
