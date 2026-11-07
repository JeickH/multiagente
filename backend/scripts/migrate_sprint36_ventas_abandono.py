"""Migración Sprint 36 — ventas por conversación y marcadores en `conversations`.

Crea:
  - tabla `conversation_sales` (modelo `models.ConversationSale`) con FKs:
      team_id                → teams(id)         ON DELETE CASCADE
      conversation_id        → conversations(id) ON DELETE CASCADE
      registrada_por_user_id → users(id)         ON DELETE SET NULL
      anulada_por_user_id    → users(id)         ON DELETE SET NULL
  - CHECK `ck_conversation_sales_valor`: valor_cop > 0 AND valor_cop <= 500000000
  - `uq_conversation_sales_activa` UNIQUE (conversation_id) WHERE anulada_at IS NULL
    → a lo sumo UNA venta activa por conversación; anulada, se puede registrar otra
  - `ix_conversation_sales_team_conv` (team_id, conversation_id)
  - `ix_conversation_sales_conversation_id`, `ix_conversation_sales_id`
    (los que `create_all()` crea por `index=True`)

Agrega a `conversations`:
  abandono_at                 TIMESTAMP NULL
  abandono_asesor             VARCHAR(64) NULL
  reclamos_abandono           INTEGER NOT NULL DEFAULT 0
  ultimo_mensaje_humano_at    TIMESTAMP NULL
  cerrada_por_inactividad_at  TIMESTAMP NULL

El CHECK, el índice parcial y el DEFAULT de `reclamos_abandono` están TAMBIÉN
declarados en el modelo, así que una base donde `create_all()` creó la tabla
primero (gotcha del 17-sep-2026) queda igual que una migrada. Aun así el script
repara: agrega el CHECK si falta y pone el DEFAULT con `ALTER COLUMN SET
DEFAULT` solo cuando el real difiere, y lo dice («N reparados»). El verificador
compara definiciones (tipo, nulabilidad, default, largo, WHERE del índice,
texto del CHECK, ondelete de las FKs), no solo nombres, y sale con 1 si algo
no cuadra.

BACKFILL (solo columnas nuevas, solo donde siguen en NULL; nunca borra ni toca
otras columnas). Por defecto SOLO muestra conteos; escribe con `BACKFILL=1`:
  a) ultimo_mensaje_humano_at = último mensaje saliente humano real
     (direction='outbound', sent_by_user_id NOT NULL, message_type <>
     'nota_interna', status <> 'failed').
  b) cerrada_por_inactividad_at = fecha de la nota interna «🔒 *Cerrada por
     inactividad*» (la de `cerrar_inactivas_arranquemos.py`), en conversaciones
     con status 'closed'.
  c) abandono_at / abandono_asesor, en las hoy abandonadas (status 'pending',
     etiqueta no nula) = fecha de la nota del abandono que escribe
     `bot_runner._marcar_abandonada` (nota interna «🕒 *<Etiqueta>*» con
     sent_by_user_id nulo) y el `assigned_to` actual. `reclamos_abandono` se
     queda en 0.

100% idempotente: CREATE ... IF NOT EXISTS, ADD COLUMN IF NOT EXISTS, CHECK
por `pg_constraint`, backfill sobre NULL. Se puede correr las veces que sea.

`lock_timeout` 10 s: el ALTER sobre `conversations` pide ACCESS EXCLUSIVE (es
instantáneo: ADD COLUMN con DEFAULT constante no reescribe la tabla desde PG
11). Si una transacción larga la tiene tomada, falla en vez de encolar detrás
a los webhooks y al tick; basta con volver a correrlo.

Uso:
    # Local (proyecto compose `wati`; el contenedor no monta `scripts/`)
    docker compose -p wati exec -T backend python - < backend/scripts/migrate_sprint36_ventas_abandono.py
    docker compose -p wati exec -T -e BACKFILL=1 backend python - < backend/scripts/migrate_sprint36_ventas_abandono.py

    # Producción (RDS, sa-east-1), con la imagen nueva por ecs run-task:
    python scripts/migrate_sprint36_ventas_abandono.py
    BACKFILL=1 python scripts/migrate_sprint36_ventas_abandono.py

OJO (gotcha histórico): migrar la base NO basta, hay que desplegar el modelo.
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


BACKFILL = os.environ.get("BACKFILL", "").strip() not in ("", "0", "false", "no")

TABLA = "conversation_sales"

# Foto del modelo a la fecha de esta migración. No se importa de models.py a
# propósito: una migración es una foto del pasado.
VALOR_MAX = 500000000

CREAR_TABLA = """
CREATE TABLE IF NOT EXISTS conversation_sales (
    id SERIAL NOT NULL,
    team_id INTEGER NOT NULL,
    conversation_id INTEGER NOT NULL,
    valor_cop BIGINT NOT NULL,
    nota VARCHAR(280),
    vendida_por VARCHAR(64),
    registrada_por_user_id INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    anulada_at TIMESTAMP WITHOUT TIME ZONE,
    anulada_por_user_id INTEGER,
    motivo_anulacion VARCHAR(280),
    CONSTRAINT conversation_sales_pkey PRIMARY KEY (id),
    CONSTRAINT ck_conversation_sales_valor
        CHECK (valor_cop > 0 AND valor_cop <= 500000000),
    CONSTRAINT conversation_sales_team_id_fkey
        FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE,
    CONSTRAINT conversation_sales_conversation_id_fkey
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    CONSTRAINT conversation_sales_registrada_por_user_id_fkey
        FOREIGN KEY (registrada_por_user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT conversation_sales_anulada_por_user_id_fkey
        FOREIGN KEY (anulada_por_user_id) REFERENCES users (id) ON DELETE SET NULL
);
"""

# Postgres no tiene `ADD CONSTRAINT IF NOT EXISTS`.
CHECK_VALOR = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'conversation_sales'::regclass
           AND conname = 'ck_conversation_sales_valor'
    ) THEN
        ALTER TABLE conversation_sales
            ADD CONSTRAINT ck_conversation_sales_valor
            CHECK (valor_cop > 0 AND valor_cop <= 500000000);
    END IF;
END $$;
"""

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_conversation_sales_id "
    "ON conversation_sales (id);",
    "CREATE INDEX IF NOT EXISTS ix_conversation_sales_conversation_id "
    "ON conversation_sales (conversation_id);",
    "CREATE INDEX IF NOT EXISTS ix_conversation_sales_team_conv "
    "ON conversation_sales (team_id, conversation_id);",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_sales_activa "
    "ON conversation_sales (conversation_id) WHERE anulada_at IS NULL;",
]

COLUMNAS_CONVERSATIONS = [
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS abandono_at TIMESTAMP WITHOUT TIME ZONE NULL;",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS abandono_asesor VARCHAR(64) NULL;",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS reclamos_abandono INTEGER NOT NULL DEFAULT 0;",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS ultimo_mensaje_humano_at TIMESTAMP WITHOUT TIME ZONE NULL;",
    "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS cerrada_por_inactividad_at TIMESTAMP WITHOUT TIME ZONE NULL;",
]

#: (tabla, columna) → default esperado tal como lo devuelve information_schema.
DEFAULTS = {("conversations", "reclamos_abandono"): ("0", "0")}

#: (tipo, nullable, default esperado o None, largo o None)
ESPERADAS_VENTAS = {
    "id": ("integer", "NO", "nextval('conversation_sales_id_seq'::regclass)", None),
    "team_id": ("integer", "NO", None, None),
    "conversation_id": ("integer", "NO", None, None),
    "valor_cop": ("bigint", "NO", None, None),
    "nota": ("character varying", "YES", None, 280),
    "vendida_por": ("character varying", "YES", None, 64),
    "registrada_por_user_id": ("integer", "YES", None, None),
    "created_at": ("timestamp without time zone", "NO", None, None),
    "anulada_at": ("timestamp without time zone", "YES", None, None),
    "anulada_por_user_id": ("integer", "YES", None, None),
    "motivo_anulacion": ("character varying", "YES", None, 280),
}

ESPERADAS_CONVERSATIONS = {
    "abandono_at": ("timestamp without time zone", "YES", None, None),
    "abandono_asesor": ("character varying", "YES", None, 64),
    "reclamos_abandono": ("integer", "NO", "0", None),
    "ultimo_mensaje_humano_at": ("timestamp without time zone", "YES", None, None),
    "cerrada_por_inactividad_at": ("timestamp without time zone", "YES", None, None),
}

#: nombre → (fragmento final de indexdef, único)
INDICES_ESPERADOS = {
    "conversation_sales_pkey": ("(id)", True),
    "ix_conversation_sales_id": ("(id)", False),
    "ix_conversation_sales_conversation_id": ("(conversation_id)", False),
    "ix_conversation_sales_team_conv": ("(team_id, conversation_id)", False),
    "uq_conversation_sales_activa": ("(conversation_id) WHERE (anulada_at IS NULL)", True),
}

#: columna → (tabla referida, confdeltype) — 'c' CASCADE, 'n' SET NULL
FKS_ESPERADAS = {
    "team_id": ("teams", "c"),
    "conversation_id": ("conversations", "c"),
    "registrada_por_user_id": ("users", "n"),
    "anulada_por_user_id": ("users", "n"),
}

CHECK_ESPERADO = "CHECK (((valor_cop > 0) AND (valor_cop <= 500000000)))"

# ---- Backfill -------------------------------------------------------------

MARCA_INACTIVIDAD = "🔒 *Cerrada por inactividad*"
MARCA_ABANDONO = "🕒 *"

_HUMANO = """
    SELECT m.conversation_id, MAX(m.created_at) AS at
      FROM messages m
     WHERE m.direction = 'outbound'
       AND m.sent_by_user_id IS NOT NULL
       AND m.message_type <> 'nota_interna'
       AND m.status <> 'failed'
     GROUP BY m.conversation_id
"""
_INACTIVIDAD = """
    SELECT m.conversation_id, MAX(m.created_at) AS at
      FROM messages m
     WHERE m.message_type = 'nota_interna'
       AND m.content LIKE :marca_inactividad
     GROUP BY m.conversation_id
"""
_ABANDONO = """
    SELECT m.conversation_id, MAX(m.created_at) AS at
      FROM messages m
     WHERE m.message_type = 'nota_interna'
       AND m.sent_by_user_id IS NULL
       AND m.content LIKE :marca_abandono
     GROUP BY m.conversation_id
"""

#: nombre → (conteo, update). Ambos filtran por la columna en NULL.
BACKFILLS = {
    "ultimo_mensaje_humano_at": (
        f"WITH n AS ({_HUMANO}) SELECT COUNT(*) FROM conversations c "
        "JOIN n ON n.conversation_id = c.id WHERE c.ultimo_mensaje_humano_at IS NULL",
        f"WITH n AS ({_HUMANO}) UPDATE conversations c "
        "SET ultimo_mensaje_humano_at = n.at FROM n "
        "WHERE n.conversation_id = c.id AND c.ultimo_mensaje_humano_at IS NULL",
    ),
    "cerrada_por_inactividad_at": (
        f"WITH n AS ({_INACTIVIDAD}) SELECT COUNT(*) FROM conversations c "
        "JOIN n ON n.conversation_id = c.id "
        "WHERE c.status = 'closed' AND c.cerrada_por_inactividad_at IS NULL",
        f"WITH n AS ({_INACTIVIDAD}) UPDATE conversations c "
        "SET cerrada_por_inactividad_at = n.at FROM n "
        "WHERE n.conversation_id = c.id AND c.status = 'closed' "
        "AND c.cerrada_por_inactividad_at IS NULL",
    ),
    "abandono_at/abandono_asesor": (
        f"WITH n AS ({_ABANDONO}) SELECT COUNT(*) FROM conversations c "
        "JOIN n ON n.conversation_id = c.id "
        "WHERE c.status = 'pending' AND c.etiqueta IS NOT NULL AND c.abandono_at IS NULL",
        f"WITH n AS ({_ABANDONO}) UPDATE conversations c "
        "SET abandono_at = n.at, "
        "    abandono_asesor = NULLIF(LEFT(c.assigned_to, 64), 'bot') "
        "FROM n WHERE n.conversation_id = c.id AND c.status = 'pending' "
        "AND c.etiqueta IS NOT NULL AND c.abandono_at IS NULL",
    ),
}

PARAMS_BACKFILL = {
    "marca_inactividad": MARCA_INACTIVIDAD + "%",
    "marca_abandono": MARCA_ABANDONO + "%",
}


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _columnas(conn, tabla: str) -> dict:
    filas = conn.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable, column_default,
                   character_maximum_length
              FROM information_schema.columns
             WHERE table_schema = current_schema() AND table_name = :t
            """
        ),
        {"t": tabla},
    ).fetchall()
    return {f[0]: f for f in filas}


def _comparar(tabla: str, esperadas: dict, vistas: dict, errores: list) -> None:
    for col, (tipo, nulable, default, largo) in esperadas.items():
        f = vistas.get(col)
        if f is None:
            errores.append(f"falta {tabla}.{col}")
            continue
        antes = len(errores)
        if f[1] != tipo:
            errores.append(f"{tabla}.{col} es {f[1]}, se esperaba {tipo}")
        if f[2] != nulable:
            errores.append(f"{tabla}.{col} nullable={f[2]}, se esperaba {nulable}")
        if f[3] != default:
            errores.append(f"{tabla}.{col} default={f[3]!r}, se esperaba {default!r}")
        if largo is not None and f[4] != largo:
            errores.append(f"{tabla}.{col} largo={f[4]}, se esperaba {largo}")
        if len(errores) == antes:
            print(f"  ✓ {tabla}.{col} {tipo} nullable={nulable} default={default}")


def main() -> int:
    print(f"Conectando a host: {_host(DATABASE_URL) or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)

    # ---- 1. Esquema --------------------------------------------------------
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        existia = conn.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": TABLA}
        ).scalar()
        conn.execute(text(CREAR_TABLA))
        print(f"  tabla {TABLA}: {'ya existía' if existia else 'creada'}")
        conn.execute(text(CHECK_VALOR))
        for sql in INDICES:
            conn.execute(text(sql))
        for sql in COLUMNAS_CONVERSATIONS:
            conn.execute(text(sql))

        # Reparación del gotcha create_all() vs DEFAULT: solo si difiere.
        reparados = 0
        for (tabla, col), (literal, esperado) in DEFAULTS.items():
            real = conn.execute(
                text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_schema = current_schema() "
                    "AND table_name = :t AND column_name = :c"
                ),
                {"t": tabla, "c": col},
            ).scalar()
            if real != esperado:
                conn.execute(
                    text(f"ALTER TABLE {tabla} ALTER COLUMN {col} SET DEFAULT {literal}")
                )
                reparados += 1
                print(f"  reparado: {tabla}.{col} default {real!r} → {esperado!r}")
        # Por si `reclamos_abandono` hubiera nacido nullable por otro camino.
        nulable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'conversations' "
                "AND column_name = 'reclamos_abandono'"
            )
        ).scalar()
        if nulable == "YES":
            conn.execute(
                text("UPDATE conversations SET reclamos_abandono = 0 WHERE reclamos_abandono IS NULL")
            )
            conn.execute(
                text("ALTER TABLE conversations ALTER COLUMN reclamos_abandono SET NOT NULL")
            )
            reparados += 1
            print("  reparado: conversations.reclamos_abandono → NOT NULL")
        print(f"  defaults/nulabilidad reparados: {reparados}")

    # ---- 2. Verificación ---------------------------------------------------
    errores: list[str] = []
    with engine.connect() as conn:
        print("Verificación:")
        vistas = _columnas(conn, TABLA)
        _comparar(TABLA, ESPERADAS_VENTAS, vistas, errores)
        sobrantes = sorted(set(vistas) - set(ESPERADAS_VENTAS))
        if sobrantes:
            errores.append(f"{TABLA}: columnas que el modelo no tiene: {sobrantes}")
        _comparar("conversations", ESPERADAS_CONVERSATIONS, _columnas(conn, "conversations"), errores)

        indices = {
            r[0]: r[1]
            for r in conn.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = current_schema() AND tablename = :t"
                ),
                {"t": TABLA},
            )
        }
        for nombre, (cola, unico) in INDICES_ESPERADOS.items():
            definicion = indices.get(nombre)
            if definicion is None:
                errores.append(f"falta índice {nombre}")
            elif not definicion.endswith(cola) or (("UNIQUE" in definicion) != unico):
                errores.append(f"índice {nombre} distinto: {definicion}")
            else:
                print(f"  ✓ índice {nombre} {'UNIQUE ' if unico else ''}{cola}")
        extra = sorted(set(indices) - set(INDICES_ESPERADOS))
        if extra:
            errores.append(f"índices que el modelo no declara: {extra}")

        checks = {
            r[0]: r[1]
            for r in conn.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
                    "WHERE conrelid = CAST(:t AS regclass) AND contype = 'c'"
                ),
                {"t": TABLA},
            )
        }
        real = checks.get("ck_conversation_sales_valor")
        if real != CHECK_ESPERADO:
            errores.append(f"CHECK ck_conversation_sales_valor = {real!r}, se esperaba {CHECK_ESPERADO!r}")
        else:
            print(f"  ✓ constraint ck_conversation_sales_valor {real}")

        fks = conn.execute(
            text(
                """
                SELECT a.attname, r.relname, c.confdeltype
                  FROM pg_constraint c
                  JOIN pg_attribute a
                    ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
                  JOIN pg_class r ON r.oid = c.confrelid
                 WHERE c.contype = 'f' AND c.conrelid = CAST(:t AS regclass)
                """
            ),
            {"t": TABLA},
        ).fetchall()
        vistas_fk: dict[str, list] = {}
        for col, ref, deltype in fks:
            vistas_fk.setdefault(col, []).append((ref, deltype))
        for col, esperada in FKS_ESPERADAS.items():
            hay = vistas_fk.get(col, [])
            if hay != [esperada]:
                errores.append(f"FK de {col}: {hay}, se esperaba [{esperada}]")
            else:
                accion = "CASCADE" if esperada[1] == "c" else "SET NULL"
                print(f"  ✓ FK {col} → {esperada[0]} ON DELETE {accion}")

        total = conn.execute(text(f"SELECT COUNT(*) FROM {TABLA}")).scalar()
        print(f"  filas en {TABLA}={total}")

    if errores:
        for e in errores:
            print(f"ERROR: {e}")
        return 1
    print("OK: esquema aplicado y verificado.")

    # ---- 3. Backfill -------------------------------------------------------
    print(f"Backfill ({'ESCRIBE' if BACKFILL else 'solo conteo; BACKFILL=1 para escribir'}):")
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        for nombre, (conteo, update) in BACKFILLS.items():
            pendientes = conn.execute(text(conteo), PARAMS_BACKFILL).scalar()
            if BACKFILL and pendientes:
                tocadas = conn.execute(text(update), PARAMS_BACKFILL).rowcount
                print(f"  {nombre}: {pendientes} por rellenar → {tocadas} rellenadas")
            else:
                print(f"  {nombre}: {pendientes} por rellenar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
