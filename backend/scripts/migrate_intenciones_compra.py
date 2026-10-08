"""Migración: tabla `intenciones_compra` (Interesados, estrategia #22).

Un *interesado* es un episodio de conversación (una fila de `bot_sessions`) en
el que el cliente mostró intención de compra y que sigue abierto 6 h después de
su primer mensaje. El bot hace upsert de una fila por sesión; la ventana
/agendamientos (pestaña Interesados) las lista. Ver `models.IntencionCompra`.

Crea:
  - tabla `intenciones_compra` con FKs:
      team_id                → teams(id)        ON DELETE CASCADE
      conversation_id        → conversations(id) ON DELETE CASCADE
      session_id             → bot_sessions(id) ON DELETE CASCADE  (UNIQUE)
      bot_id                 → bots(id)         ON DELETE CASCADE
      gestionado_por_user_id → users(id)        ON DELETE SET NULL
      tomado_por_user_id     → users(id)        ON DELETE SET NULL
  - `uq_intenciones_compra_session` (session_id)  → una fila por episodio
  - `ix_intenciones_compra_team_visible` (team_id, visible_desde)
  - `ix_intenciones_compra_conversation_id`, `ix_intenciones_compra_id`
    (los que `create_all()` crea por `index=True`)

Defaults: `tipos` = '[]'::jsonb y `estado` = 'por_contactar'. Están TAMBIÉN
como `server_default` en el modelo, así que una base donde `create_all()` creó
la tabla primero (gotcha del 17-sep-2026) queda igual que una migrada. Por si
la tabla nació de otra forma sin ellos, el script los fija con
`ALTER COLUMN ... SET DEFAULT`, que es idempotente. La verificación final
revisa columna por columna tipo, nulabilidad y default.

Los nombres de constraints e índices son los que pone Postgres cuando
`create_all()` crea la tabla (`<tabla>_<col>_fkey`, `<tabla>_pkey`), para que
una base nueva y una migrada queden idénticas.

No toca filas: la tabla nace vacía y se llena sola con los turnos del bot 2
(solo los bots con `llm_config.intencion_compra` escriben aquí).

100% idempotente: `CREATE TABLE IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`,
`SET DEFAULT`. Se puede correr las veces que sea.

`lock_timeout`: crear la tabla con FKs pide SHARE ROW EXCLUSIVE sobre
`conversations`, `bot_sessions`, `bots`, `teams` y `users`. Si una transacción
larga las tiene tomadas, en vez de quedarse esperando (y encolar detrás a los
webhooks y al tick de bots) falla a los 10 s; basta con volver a correrlo.

Uso:
    # Local (el proyecto de compose se llama `wati`; el contenedor no monta
    # `scripts/`, por eso va por stdin)
    docker compose -p wati exec -T backend python - < backend/scripts/migrate_intenciones_compra.py

    # Producción (RDS, sa-east-1)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_intenciones_compra.py

OJO (gotcha histórico): migrar la base NO basta, hay que desplegar el modelo.
Orden: migración → imagen. Al revés, `create_all()` de la imagen nueva crearía
la tabla por su cuenta (con los mismos defaults, así que tampoco rompe), pero
la evidencia de la migración en RDS es parte del PR (paridad local ↔ AWS).
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


TABLA = "intenciones_compra"

CREAR_TABLA = """
CREATE TABLE IF NOT EXISTS intenciones_compra (
    id SERIAL NOT NULL,
    team_id INTEGER NOT NULL,
    conversation_id INTEGER NOT NULL,
    session_id INTEGER NOT NULL,
    bot_id INTEGER NOT NULL,
    tipos JSONB DEFAULT '[]' NOT NULL,
    origen VARCHAR(16) NOT NULL,
    fragmento VARCHAR(160),
    resumen VARCHAR(300),
    primera_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    ultima_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    visible_desde TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    estado VARCHAR(16) DEFAULT 'por_contactar' NOT NULL,
    gestionado_por_user_id INTEGER,
    gestionado_at TIMESTAMP WITHOUT TIME ZONE,
    motivo_descarte VARCHAR(120),
    tomado_por_user_id INTEGER,
    tomado_at TIMESTAMP WITHOUT TIME ZONE,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    CONSTRAINT intenciones_compra_pkey PRIMARY KEY (id),
    CONSTRAINT uq_intenciones_compra_session UNIQUE (session_id),
    CONSTRAINT intenciones_compra_team_id_fkey
        FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE,
    CONSTRAINT intenciones_compra_conversation_id_fkey
        FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE,
    CONSTRAINT intenciones_compra_session_id_fkey
        FOREIGN KEY (session_id) REFERENCES bot_sessions (id) ON DELETE CASCADE,
    CONSTRAINT intenciones_compra_bot_id_fkey
        FOREIGN KEY (bot_id) REFERENCES bots (id) ON DELETE CASCADE,
    CONSTRAINT intenciones_compra_gestionado_por_user_id_fkey
        FOREIGN KEY (gestionado_por_user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT intenciones_compra_tomado_por_user_id_fkey
        FOREIGN KEY (tomado_por_user_id) REFERENCES users (id) ON DELETE SET NULL
);
"""

# Columnas que llegaron después de la primera versión de la tabla (revisión de
# seguridad S4: auditoría de quién tomó la conversación). En una base nueva ya
# vienen en el CREATE; en una que tuviera la tabla sin ellas, se agregan.
COLUMNAS_TARDIAS = [
    "ALTER TABLE intenciones_compra ADD COLUMN IF NOT EXISTS tomado_por_user_id INTEGER NULL;",
    "ALTER TABLE intenciones_compra ADD COLUMN IF NOT EXISTS tomado_at TIMESTAMP WITHOUT TIME ZONE NULL;",
]

# Postgres no tiene `ADD CONSTRAINT IF NOT EXISTS`: se pregunta a `pg_constraint`
# por CUALQUIER FK sobre la columna, no solo por nombre, para no duplicarla.
FK_TOMADO_POR = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_constraint c
          JOIN pg_attribute a
            ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
         WHERE c.contype = 'f'
           AND c.conrelid = 'intenciones_compra'::regclass
           AND a.attname = 'tomado_por_user_id'
    ) THEN
        ALTER TABLE intenciones_compra
            ADD CONSTRAINT intenciones_compra_tomado_por_user_id_fkey
            FOREIGN KEY (tomado_por_user_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;
"""

# Reparación idempotente del gotcha `create_all()` vs DEFAULT.
DEFAULTS = [
    "ALTER TABLE intenciones_compra ALTER COLUMN tipos SET DEFAULT '[]';",
    "ALTER TABLE intenciones_compra ALTER COLUMN estado SET DEFAULT 'por_contactar';",
]

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_intenciones_compra_id "
    "ON intenciones_compra (id);",
    "CREATE INDEX IF NOT EXISTS ix_intenciones_compra_conversation_id "
    "ON intenciones_compra (conversation_id);",
    "CREATE INDEX IF NOT EXISTS ix_intenciones_compra_team_visible "
    "ON intenciones_compra (team_id, visible_desde);",
]

#: (tipo, nullable, default esperado o None)
ESPERADAS = {
    "id": ("integer", "NO", "nextval('intenciones_compra_id_seq'::regclass)"),
    "team_id": ("integer", "NO", None),
    "conversation_id": ("integer", "NO", None),
    "session_id": ("integer", "NO", None),
    "bot_id": ("integer", "NO", None),
    "tipos": ("jsonb", "NO", "'[]'::jsonb"),
    "origen": ("character varying", "NO", None),
    "fragmento": ("character varying", "YES", None),
    "resumen": ("character varying", "YES", None),
    "primera_at": ("timestamp without time zone", "NO", None),
    "ultima_at": ("timestamp without time zone", "NO", None),
    "visible_desde": ("timestamp without time zone", "NO", None),
    "estado": ("character varying", "NO", "'por_contactar'::character varying"),
    "gestionado_por_user_id": ("integer", "YES", None),
    "gestionado_at": ("timestamp without time zone", "YES", None),
    "motivo_descarte": ("character varying", "YES", None),
    "tomado_por_user_id": ("integer", "YES", None),
    "tomado_at": ("timestamp without time zone", "YES", None),
    "created_at": ("timestamp without time zone", "NO", None),
    "updated_at": ("timestamp without time zone", "NO", None),
}

LONGITUDES = {"origen": 16, "fragmento": 160, "resumen": 300, "estado": 16,
              "motivo_descarte": 120}

INDICES_ESPERADOS = {
    "intenciones_compra_pkey": "(id)",
    "uq_intenciones_compra_session": "(session_id)",
    "ix_intenciones_compra_id": "(id)",
    "ix_intenciones_compra_conversation_id": "(conversation_id)",
    "ix_intenciones_compra_team_visible": "(team_id, visible_desde)",
}

#: columna → (tabla referida, confdeltype) — 'c' CASCADE, 'n' SET NULL
FKS_ESPERADAS = {
    "team_id": ("teams", "c"),
    "conversation_id": ("conversations", "c"),
    "session_id": ("bot_sessions", "c"),
    "bot_id": ("bots", "c"),
    "gestionado_por_user_id": ("users", "n"),
    "tomado_por_user_id": ("users", "n"),
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
        existia = conn.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": TABLA}
        ).scalar()
        conn.execute(text(CREAR_TABLA))
        print(f"  ✓ tabla {TABLA} ({'ya existía' if existia else 'creada'})")
        for sql in COLUMNAS_TARDIAS:
            conn.execute(text(sql))
        conn.execute(text(FK_TOMADO_POR))
        print("  ✓ columnas tomado_por_user_id, tomado_at + FK → users ON DELETE SET NULL")
        for sql in DEFAULTS:
            conn.execute(text(sql))
        print("  ✓ defaults: tipos='[]', estado='por_contactar'")
        for sql in INDICES:
            conn.execute(text(sql))
        print("  ✓ índices: " + ", ".join(n for n in INDICES_ESPERADOS if n.startswith("ix_")))

    errores: list[str] = []
    with engine.connect() as conn:
        filas = conn.execute(
            text(
                """
                SELECT column_name, data_type, is_nullable, column_default,
                       character_maximum_length
                  FROM information_schema.columns
                 WHERE table_schema = current_schema() AND table_name = :t
                """
            ),
            {"t": TABLA},
        ).fetchall()
        vistas = {f[0]: f for f in filas}
        for col, (tipo, nulable, default) in ESPERADAS.items():
            f = vistas.get(col)
            if f is None:
                errores.append(f"falta {TABLA}.{col}")
                continue
            if f[1] != tipo:
                errores.append(f"{col} es {f[1]}, se esperaba {tipo}")
            if f[2] != nulable:
                errores.append(f"{col} nullable={f[2]}, se esperaba {nulable}")
            if f[3] != default:
                errores.append(f"{col} default={f[3]!r}, se esperaba {default!r}")
            if col in LONGITUDES and f[4] != LONGITUDES[col]:
                errores.append(f"{col} largo={f[4]}, se esperaba {LONGITUDES[col]}")
        sobrantes = sorted(set(vistas) - set(ESPERADAS))
        if sobrantes:
            errores.append(f"columnas que el modelo no tiene: {sobrantes}")
        print(f"  columnas: {len(vistas)} (esperadas {len(ESPERADAS)})")

        indices = {
            r[0]: r[1]
            for r in conn.execute(
                text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = :t"),
                {"t": TABLA},
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
        extra = sorted(set(indices) - set(INDICES_ESPERADOS))
        if extra:
            errores.append(f"índices que el modelo no declara: {extra}")
        unico = indices.get("uq_intenciones_compra_session", "")
        if unico and "UNIQUE" not in unico:
            errores.append("uq_intenciones_compra_session no es único")

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
                print(f"  FK {col} → {esperada[0]} ondelete={'CASCADE' if esperada[1] == 'c' else 'SET NULL'}")

        total = conn.execute(text(f"SELECT COUNT(*) FROM {TABLA}")).scalar()
        print(f"  filas en {TABLA}={total}")

    if errores:
        for e in errores:
            print(f"ERROR: {e}")
        return 1
    print("OK: migración aplicada y verificada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
