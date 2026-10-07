"""Migración: reparto A/B de conversaciones nuevas entre varios bots `default`.

Una cuenta puede tener varios bots `default` (mismos productos, distinto guion)
y repartir por porcentaje las conversaciones NUEVAS entre ellos.

Añade:
  - `bots.reparto_pct`              INTEGER NULL   (NULL o 0 = no entra al reparto)
  - `bots.reparto_desde`            TIMESTAMP NULL (naive UTC; desde cuándo se
                                    cuenta el reparto vigente)
  - `conversations.bot_asignado_id` INTEGER NULL, FK → bots(id) ON DELETE SET NULL
  - `conversations.bot_asignado_at` TIMESTAMP NULL (naive UTC)
  - índice compuesto `ix_conversations_bot_asignado_at (bot_asignado_id,
    bot_asignado_at)` para el conteo del reparto:
        WHERE bot_asignado_id IN (...) AND bot_asignado_at >= :desde
        GROUP BY bot_asignado_id
    Declarado en `Conversation.__table_args__`. Como `bot_asignado_id` es su
    columna líder, también cubre el ON DELETE SET NULL de la FK; por eso NO hay
    índice de una sola columna. Si una corrida anterior de este script dejó
    `ix_conversations_bot_asignado_id`, se borra (no está en el modelo).

Quita:
  - `uq_one_default_bot_per_user` (índice único parcial sobre bots(user_id)
    WHERE trigger_type = 'default', creado en el Sprint 9 y nunca declarado en
    el modelo). Es justo lo que impedía tener varios bots `default` por
    cuenta. Sin él, elegir entre varios defaults es trabajo del reparto.

La FK se llama `conversations_bot_asignado_id_fkey`, que es el nombre que
Postgres le pone cuando `create_all()` crea la tabla desde cero: así una base
nueva y una migrada quedan iguales.

Ninguna columna lleva DEFAULT, a propósito (NULL = "nunca entró a un reparto").
Por eso el gotcha de `create_all()` (tablas nacidas sin DEFAULT que el
`IF NOT EXISTS` ya no repara) no aplica aquí; el script igual verifica que las
cuatro columnas queden sin default y nulables.

No toca filas: no hay backfill ni UPDATE. Las conversaciones existentes quedan
con `bot_asignado_id` NULL y los bots con `reparto_pct` NULL, que es
exactamente el comportamiento de hoy (gana el `default` de menor id).

100% idempotente: `ADD COLUMN IF NOT EXISTS`, la FK se crea solo si no hay ya
una FK sobre esa columna (se pregunta a `pg_constraint`, Postgres no tiene
`ADD CONSTRAINT IF NOT EXISTS`), `CREATE INDEX IF NOT EXISTS` y
`DROP INDEX IF EXISTS`. Se puede correr las veces que sea.

`lock_timeout`: el ALTER sobre `conversations` pide ACCESS EXCLUSIVE. Si una
transacción larga la tiene tomada, en vez de quedarse esperando (y encolar
detrás a webhooks y al tick de bots) falla a los 10 s; basta con volver a
correrlo.

Uso:
    # Local (el proyecto de compose se llama `wati`; el contenedor no monta
    # `scripts/`, por eso va por stdin)
    docker compose -p wati exec -T backend python - < backend/scripts/migrate_reparto_bots.py

    # Producción (RDS, sa-east-1)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_reparto_bots.py

OJO (gotcha histórico): migrar la base NO basta. Si la imagen de ECS lleva un
`models.py` sin estas columnas, el ORM ni las ve. Y al revés: si sale la imagen
nueva ANTES que la migración, el ORM pide columnas que no existen y se cae
cualquier SELECT sobre `bots` o `conversations`. Orden: migración → imagen.
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

_CANDIDATOS = ["/app"]
if "__file__" in globals():  # no existe vía `python -c` (rds_exec.sh) ni por stdin
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


COLUMNAS = [
    "ALTER TABLE bots ADD COLUMN IF NOT EXISTS reparto_pct INTEGER NULL;",
    "ALTER TABLE bots ADD COLUMN IF NOT EXISTS reparto_desde TIMESTAMP WITHOUT TIME ZONE NULL;",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS bot_asignado_id INTEGER NULL;",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS bot_asignado_at TIMESTAMP WITHOUT TIME ZONE NULL;",
]

# Se busca CUALQUIER FK sobre conversations.bot_asignado_id hacia bots, no solo
# por nombre: si alguien la creó a mano con otro nombre, no se duplica.
FK_BOT_ASIGNADO = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.contype = 'f'
           AND c.conrelid = 'conversations'::regclass
           AND c.confrelid = 'bots'::regclass
           AND a.attname = 'bot_asignado_id'
    ) THEN
        ALTER TABLE conversations
            ADD CONSTRAINT conversations_bot_asignado_id_fkey
            FOREIGN KEY (bot_asignado_id) REFERENCES bots(id) ON DELETE SET NULL;
    END IF;
END $$;
"""

INDICES = [
    # Conteo del reparto: igualdad en bot_asignado_id + rango en bot_asignado_at.
    "CREATE INDEX IF NOT EXISTS ix_conversations_bot_asignado_at "
    "ON conversations (bot_asignado_id, bot_asignado_at);",
]

# Lo que NO debe quedar.
INDICES_A_QUITAR = [
    # Un solo bot `default` por usuario: el feature existe para levantarlo.
    "uq_one_default_bot_per_user",
    # Redundante con el compuesto (misma columna líder); no está en el modelo.
    "ix_conversations_bot_asignado_id",
]

ESPERADAS = {
    ("bots", "reparto_pct"): "integer",
    ("bots", "reparto_desde"): "timestamp without time zone",
    ("conversations", "bot_asignado_id"): "integer",
    ("conversations", "bot_asignado_at"): "timestamp without time zone",
}

INDICES_ESPERADOS = {
    "ix_conversations_bot_asignado_at": "(bot_asignado_id, bot_asignado_at)",
}


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def main() -> int:
    print(f"Conectando a host: {_host(DATABASE_URL) or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        for sql in COLUMNAS:
            conn.execute(text(sql))
        print(f"  ✓ {len(COLUMNAS)} columnas")
        conn.execute(text(FK_BOT_ASIGNADO))
        print("  ✓ FK conversations.bot_asignado_id → bots(id) ON DELETE SET NULL")
        for sql in INDICES:
            conn.execute(text(sql))
        print(f"  ✓ índices: {', '.join(INDICES_ESPERADOS)}")
        for nombre in INDICES_A_QUITAR:
            conn.execute(text(f"DROP INDEX IF EXISTS {nombre};"))
        print(f"  ✓ quitados (si estaban): {', '.join(INDICES_A_QUITAR)}")

    errores: list[str] = []
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                """
                SELECT table_name, column_name, data_type, is_nullable, column_default
                  FROM information_schema.columns
                 WHERE table_schema = current_schema()
                   AND (table_name, column_name) IN (
                        ('bots', 'reparto_pct'), ('bots', 'reparto_desde'),
                        ('conversations', 'bot_asignado_id'),
                        ('conversations', 'bot_asignado_at'))
                """
            )
        ).fetchall()
        vistas = {(f[0], f[1]): f for f in filas}
        for clave, tipo in ESPERADAS.items():
            f = vistas.get(clave)
            nombre = f"{clave[0]}.{clave[1]}"
            if f is None:
                errores.append(f"falta {nombre}")
                continue
            if f[2] != tipo:
                errores.append(f"{nombre} es {f[2]}, se esperaba {tipo}")
            if f[3] != "YES":
                errores.append(f"{nombre} quedó NOT NULL")
            if f[4] is not None:
                errores.append(f"{nombre} tiene default {f[4]!r} (no debe tener)")
            print(f"  {nombre}: {f[2]} nullable={f[3]} default={f[4]!r}")

        fks = conn.execute(
            text(
                """
                SELECT c.conname, c.confdeltype
                  FROM pg_constraint c
                  JOIN pg_attribute a
                    ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
                 WHERE c.contype = 'f'
                   AND c.conrelid = 'conversations'::regclass
                   AND c.confrelid = 'bots'::regclass
                   AND a.attname = 'bot_asignado_id'
                """
            )
        ).fetchall()
        if len(fks) != 1:
            errores.append(f"se esperaba 1 FK sobre bot_asignado_id, hay {len(fks)}")
        for nombre, deltype in fks:
            # confdeltype 'n' = ON DELETE SET NULL
            if deltype != "n":
                errores.append(f"FK {nombre} con ON DELETE={deltype!r}, se esperaba SET NULL")
            print(f"  FK {nombre} ondelete={'SET NULL' if deltype == 'n' else deltype}")

        indices = {
            r[0]: r[1]
            for r in conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'conversations' "
                    "AND indexname = ANY(:nombres)"
                ),
                {"nombres": list(INDICES_ESPERADOS)},
            )
        }
        for nombre, columnas in INDICES_ESPERADOS.items():
            definicion = indices.get(nombre)
            if definicion is None:
                errores.append(f"falta índice {nombre}")
            elif not definicion.endswith(columnas):
                errores.append(f"índice {nombre} distinto: {definicion}")
            else:
                print(f"  índice {nombre} {columnas}")

        sobrantes = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE schemaname = current_schema() "
                    "AND indexname = ANY(:nombres)"
                ),
                {"nombres": INDICES_A_QUITAR},
            )
        ]
        for nombre in sobrantes:
            errores.append(f"el índice {nombre} sigue existiendo")
        if not sobrantes:
            print(f"  sin {', '.join(INDICES_A_QUITAR)}")

        total_conv, asignadas = conn.execute(
            text("SELECT COUNT(*), COUNT(bot_asignado_id) FROM conversations")
        ).fetchone()
        total_bots, con_pct = conn.execute(
            text("SELECT COUNT(*), COUNT(reparto_pct) FROM bots")
        ).fetchone()
        print(f"  conversaciones={total_conv} con bot asignado={asignadas}")
        print(f"  bots={total_bots} con reparto_pct={con_pct}")
        varios = conn.execute(
            text(
                "SELECT COUNT(*) FROM (SELECT user_id FROM bots "
                "WHERE trigger_type = 'default' GROUP BY user_id "
                "HAVING COUNT(*) > 1) t"
            )
        ).scalar()
        print(f"  usuarios con más de un bot default={varios}")

    if errores:
        for e in errores:
            print(f"ERROR: {e}")
        return 1
    print("OK: migración aplicada y verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
