"""Migración Sprint 31 — lo que vende cada cuenta, en la base.

Crea las ocho tablas del modelo de `docs/bots_productos_modelo.puml` y agrega
tres columnas a tablas existentes. Hoy el catálogo de un cliente vive en un
`.md` del repo y en JSON sueltos, así que cambiarle un precio es un despliegue;
esto lo mueve a la base, aislado por cuenta.

TABLAS NUEVAS
  bot_productos            → un plan, un SKU o una ficha de una cuenta
  bot_producto_variantes   → la habitación, el sabor, la talla
  bot_producto_filas       → la salida con fecha, el precio, la sede, el envío
  bot_producto_medios      → foto/video/PDF que ilustra
  bot_producto_alias       → cómo le dice la gente ("el de cove")
  bot_producto_bots        → qué productos ve cada bot
  bot_producto_cargas      → bitácora de cada carga de archivo del cliente
  bot_recordatorios        → cadena de reenganche configurable por cuenta

COLUMNAS NUEVAS
  bots.instrucciones            TEXT NULL     → instrucciones de negocio (nivel 2)
  bots.instrucciones_version    INT NOT NULL DEFAULT 0
  bot_llm_decisions.fuente_datos VARCHAR(16) NULL

    OJO con `fuente_datos`, que se parece peligrosamente a la columna `source`
    que ya existe en esa misma tabla y significan cosas distintas:
      `source`       → por dónde ENTRÓ el turno: 'whatsapp' | 'simulador'.
      `fuente_datos` → de dónde salieron los DATOS con los que el bot
                       respondió: 'db' (estas tablas nuevas), 'prompt' (venían
                       escritos en el contexto) o 'json' (`app/data/`).
    Es NULLABLE y SIN default a propósito: así un turno anterior a esta
    migración (NULL) no se confunde con un turno nuevo que no consultó
    ninguna fuente. Mismo criterio que se usó en `conversations.etiqueta`.

DECISIÓN: CENTINELA `0` EN VEZ DE NULL
    `bot_producto_filas.variante_id`, `bot_producto_medios.variante_id` y
    `bot_recordatorios.bot_id` son NOT NULL DEFAULT 0, donde `0` significa
    "aplica a todas/todos". No son NULL y no llevan FK.

    El motivo es que en Postgres `NULL <> NULL`, así que un UNIQUE que incluya
    una columna nullable NO impide duplicados cuando esa columna viene vacía.
    Con `variante_id` nullable, el UNIQUE (producto_id, variante_id,
    externo_id) dejaría pasar la misma fila sin variante en cada corrida del
    importador. Ya lo mordimos en este repo con `uq_mascota_origen`
    (`source`, `origen_id`), donde `origen_id` nullable dejó entrar repetidos
    de las fuentes que no traen id. Con `0`, que es un valor real, el UNIQUE sí
    muerde. Por lo mismo `externo_id` es `''` y no NULL.

    `bot_recordatorios` lleva además `team_id` dentro de su UNIQUE, que el
    .puml omite: sin él, dos cuentas que configuren "todos los bots"
    (`bot_id = 0`) chocarían en el recordatorio 1.

A VERIFICAR EN EL PR DE DESPLIEGUE (no se toca aquí)
    `models.py` declara `bots.team_id` como `nullable=True`, pero la base local
    lo tiene NOT NULL. Todo este modelo se aísla por cuenta vía `teams.id`, así
    que la discrepancia importa. Hay que confirmar cómo está en RDS antes de
    apoyarse en `bots.team_id` para filtrar. Esta migración NO lo modifica.

100% idempotente (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`). Sólo añade: no borra ni reescribe nada. Correrla
dos veces seguidas no cambia nada la segunda vez.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_sprint31_productos.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_sprint31_productos.py

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


# ── Tablas ────────────────────────────────────────────────────────────────

TABLAS: list[tuple[str, str]] = [
    (
        "bot_productos",
        """
CREATE TABLE IF NOT EXISTS bot_productos (
    id              SERIAL PRIMARY KEY,
    team_id         INTEGER      NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    slug            VARCHAR(80)  NOT NULL,
    tipo            VARCHAR(24)  NOT NULL DEFAULT 'producto',
    nombre          VARCHAR(160) NOT NULL,
    estado          VARCHAR(16)  NOT NULL DEFAULT 'borrador',
    resumen         VARCHAR(240),
    instrucciones   TEXT,
    atributos       JSONB        NOT NULL DEFAULT '{}'::jsonb,
    vigencia_desde  DATE,
    vigencia_hasta  DATE,
    created_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bot_productos_team_slug UNIQUE (team_id, slug),
    CONSTRAINT ck_bot_productos_tipo
        CHECK (tipo IN ('plan','producto','catalogo_externo','ficha')),
    CONSTRAINT ck_bot_productos_estado
        CHECK (estado IN ('borrador','publicado','archivado'))
);
""",
    ),
    (
        "bot_producto_variantes",
        """
CREATE TABLE IF NOT EXISTS bot_producto_variantes (
    id                     SERIAL PRIMARY KEY,
    producto_id            INTEGER      NOT NULL
                           REFERENCES bot_productos(id) ON DELETE CASCADE,
    slug                   VARCHAR(80)  NOT NULL,
    nombre                 VARCHAR(160) NOT NULL,
    instrucciones          TEXT,
    atributos              JSONB        NOT NULL DEFAULT '{}'::jsonb,
    precios_de_variante_id INTEGER
                           REFERENCES bot_producto_variantes(id) ON DELETE SET NULL,
    activo                 BOOLEAN      NOT NULL DEFAULT TRUE,
    orden                  INTEGER      NOT NULL DEFAULT 0,
    created_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bot_producto_variantes_slug UNIQUE (producto_id, slug)
);
""",
    ),
    (
        "bot_producto_filas",
        # `variante_id` y `externo_id` con centinela (0 / '') y NOT NULL: es lo
        # que hace que el UNIQUE sea de verdad un candado contra el importador
        # repetido. Ver el docstring.
        """
CREATE TABLE IF NOT EXISTS bot_producto_filas (
    id          BIGSERIAL PRIMARY KEY,
    producto_id INTEGER      NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    variante_id INTEGER      NOT NULL DEFAULT 0,
    tipo        VARCHAR(16)  NOT NULL DEFAULT 'precio',
    etiqueta    VARCHAR(160),
    inicio      DATE,
    fin         DATE,
    valores     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    nota        TEXT,
    orden       INTEGER      NOT NULL DEFAULT 0,
    activo      BOOLEAN      NOT NULL DEFAULT TRUE,
    externo_id  VARCHAR(120) NOT NULL DEFAULT '',
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bot_producto_filas_externo
        UNIQUE (producto_id, variante_id, externo_id),
    CONSTRAINT ck_bot_producto_filas_tipo
        CHECK (tipo IN ('salida','precio','sede','envio','faq'))
);
""",
    ),
    (
        "bot_producto_medios",
        """
CREATE TABLE IF NOT EXISTS bot_producto_medios (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER       NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    variante_id INTEGER       NOT NULL DEFAULT 0,
    clave       VARCHAR(80)   NOT NULL,
    url         VARCHAR(1024) NOT NULL,
    tipo        VARCHAR(24)   NOT NULL DEFAULT 'image',
    descripcion VARCHAR(300),
    aplica      JSONB         NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMP     NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP     NOT NULL DEFAULT NOW()
);
""",
    ),
    (
        "bot_producto_alias",
        """
CREATE TABLE IF NOT EXISTS bot_producto_alias (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER      NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    nivel       VARCHAR(16)  NOT NULL DEFAULT 'producto',
    ref_id      INTEGER      NOT NULL DEFAULT 0,
    alias       VARCHAR(160) NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bot_producto_alias UNIQUE (producto_id, nivel, alias),
    CONSTRAINT ck_bot_producto_alias_nivel
        CHECK (nivel IN ('producto','variante'))
);
""",
    ),
    (
        "bot_producto_bots",
        """
CREATE TABLE IF NOT EXISTS bot_producto_bots (
    id          SERIAL PRIMARY KEY,
    bot_id      INTEGER   NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    producto_id INTEGER   NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    activo      BOOLEAN   NOT NULL DEFAULT TRUE,
    orden       INTEGER   NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bot_producto_bots UNIQUE (bot_id, producto_id)
);
""",
    ),
    (
        "bot_producto_cargas",
        """
CREATE TABLE IF NOT EXISTS bot_producto_cargas (
    id                   SERIAL PRIMARY KEY,
    producto_id          INTEGER      NOT NULL
                         REFERENCES bot_productos(id) ON DELETE CASCADE,
    archivo              VARCHAR(300) NOT NULL,
    hash_sha256          VARCHAR(64),
    filas_nuevas         INTEGER      NOT NULL DEFAULT 0,
    filas_cambiadas      INTEGER      NOT NULL DEFAULT 0,
    filas_retiradas      INTEGER      NOT NULL DEFAULT 0,
    estado               VARCHAR(16)  NOT NULL DEFAULT 'revision',
    diff                 JSONB        NOT NULL DEFAULT '{}'::jsonb,
    aprobado_por_user_id INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_bot_producto_cargas_estado
        CHECK (estado IN ('revision','aplicado','rechazado'))
);
""",
    ),
    (
        "bot_recordatorios",
        """
CREATE TABLE IF NOT EXISTS bot_recordatorios (
    id         SERIAL PRIMARY KEY,
    team_id    INTEGER   NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    bot_id     INTEGER   NOT NULL DEFAULT 0,
    orden      INTEGER   NOT NULL DEFAULT 1,
    minutos    INTEGER   NOT NULL,
    texto      TEXT      NOT NULL,
    omitir_si  JSONB     NOT NULL DEFAULT '{}'::jsonb,
    hora_min   INTEGER   NOT NULL DEFAULT 8,
    hora_max   INTEGER   NOT NULL DEFAULT 20,
    activo     BOOLEAN   NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_bot_recordatorios_orden UNIQUE (team_id, bot_id, orden),
    CONSTRAINT ck_bot_recordatorios_minutos
        CHECK (minutos > 0 AND minutos < 1440),
    CONSTRAINT ck_bot_recordatorios_orden CHECK (orden > 0),
    CONSTRAINT ck_bot_recordatorios_franja
        CHECK (hora_min >= 0 AND hora_min <= 23
               AND hora_max >= 0 AND hora_max <= 23
               AND hora_min <= hora_max)
);
""",
    ),
]


# ── Columnas nuevas en tablas existentes ──────────────────────────────────
# `(tabla, columna, DDL)`. Se verifican una por una al final.

COLUMNAS: list[tuple[str, str, str]] = [
    (
        "bots",
        "instrucciones",
        "ALTER TABLE bots ADD COLUMN IF NOT EXISTS instrucciones TEXT;",
    ),
    (
        "bots",
        "instrucciones_version",
        "ALTER TABLE bots ADD COLUMN IF NOT EXISTS instrucciones_version "
        "INTEGER NOT NULL DEFAULT 0;",
    ),
    (
        "bot_llm_decisions",
        "fuente_datos",
        "ALTER TABLE bot_llm_decisions ADD COLUMN IF NOT EXISTS "
        "fuente_datos VARCHAR(16);",
    ),
]


# ── Índices ───────────────────────────────────────────────────────────────

INDICES = [
    "CREATE INDEX IF NOT EXISTS ix_bot_productos_team_id "
    "ON bot_productos (team_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_productos_estado "
    "ON bot_productos (estado);",
    # "los publicados de esta cuenta", que es lo que arma el índice del prompt.
    "CREATE INDEX IF NOT EXISTS ix_bot_productos_team_estado "
    "ON bot_productos (team_id, estado);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_variantes_producto_id "
    "ON bot_producto_variantes (producto_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_filas_producto_id "
    "ON bot_producto_filas (producto_id);",
    # La consulta caliente del bot: "las próximas salidas vigentes de este
    # producto". Parcial sobre `activo` porque las retiradas no se consultan
    # nunca y tras unas temporadas son la mayoría de la tabla.
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_filas_prod_inicio "
    "ON bot_producto_filas (producto_id, inicio) WHERE activo;",
    # GIN: preguntar por dentro del JSONB ("las que tengan tarifa doble") sin
    # escanear la tabla. Va escrito a mano porque el `USING gin` no sale de un
    # CREATE INDEX normal.
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_filas_valores "
    "ON bot_producto_filas USING gin (valores);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_medios_producto_id "
    "ON bot_producto_medios (producto_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_medios_prod_clave "
    "ON bot_producto_medios (producto_id, clave);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_alias_producto_id "
    "ON bot_producto_alias (producto_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_bots_bot_id "
    "ON bot_producto_bots (bot_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_bots_producto_id "
    "ON bot_producto_bots (producto_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_cargas_producto_id "
    "ON bot_producto_cargas (producto_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_cargas_hash_sha256 "
    "ON bot_producto_cargas (hash_sha256);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_cargas_estado "
    "ON bot_producto_cargas (estado);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_cargas_created_at "
    "ON bot_producto_cargas (created_at);",
    "CREATE INDEX IF NOT EXISTS ix_bot_producto_cargas_prod_creado "
    "ON bot_producto_cargas (producto_id, created_at);",
    "CREATE INDEX IF NOT EXISTS ix_bot_recordatorios_team_id "
    "ON bot_recordatorios (team_id);",
    "CREATE INDEX IF NOT EXISTS ix_bot_recordatorios_team_bot "
    "ON bot_recordatorios (team_id, bot_id);",
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
        for nombre, ddl in TABLAS:
            conn.execute(text(ddl))
            print(f"  ✓ tabla {nombre}")
        for tabla, columna, ddl in COLUMNAS:
            conn.execute(text(ddl))
            print(f"  ✓ columna {tabla}.{columna}")
        for sql in INDICES:
            conn.execute(text(sql))
        print(f"  ✓ {len(INDICES)} índices")

    # ── Verificación: que quedó lo que decimos que quedó ──────────────────
    # Devuelve 1 si falta UNA sola tabla, columna o índice. Una migración que
    # siempre sale con 0 es peor que una que falla: el despliegue sigue.
    faltan_tablas: list[str] = []
    faltan_columnas: list[str] = []
    faltan_indices: list[str] = []

    with engine.connect() as conn:
        for nombre, _ in TABLAS:
            if conn.execute(
                text("SELECT to_regclass(:t)"), {"t": f"public.{nombre}"}
            ).scalar() is None:
                faltan_tablas.append(nombre)

        for tabla, columna, _ in COLUMNAS:
            existe = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t "
                    "AND column_name=:c"
                ),
                {"t": tabla, "c": columna},
            ).scalar()
            if not existe:
                faltan_columnas.append(f"{tabla}.{columna}")

        # Las columnas propias de las tablas nuevas también se revisan: si una
        # tabla ya existía de una corrida anterior incompleta, el
        # `CREATE TABLE IF NOT EXISTS` no la corrige y no dice nada.
        esperadas = {
            "bot_productos": {"team_id", "slug", "tipo", "estado", "instrucciones",
                              "atributos", "created_at", "updated_at"},
            "bot_producto_variantes": {"producto_id", "slug",
                                       "precios_de_variante_id", "updated_at"},
            "bot_producto_filas": {"producto_id", "variante_id", "valores",
                                   "externo_id", "activo", "inicio", "updated_at"},
            "bot_producto_medios": {"producto_id", "variante_id", "clave",
                                    "aplica", "updated_at"},
            "bot_producto_alias": {"producto_id", "nivel", "ref_id", "alias",
                                   "updated_at"},
            "bot_producto_bots": {"bot_id", "producto_id", "activo", "updated_at"},
            "bot_producto_cargas": {"producto_id", "hash_sha256", "diff",
                                    "aprobado_por_user_id", "estado", "updated_at"},
            "bot_recordatorios": {"team_id", "bot_id", "orden", "minutos",
                                  "omitir_si", "hora_min", "hora_max", "updated_at"},
        }
        for tabla, columnas in esperadas.items():
            if tabla in faltan_tablas:
                continue
            presentes = {
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=:t"
                    ),
                    {"t": tabla},
                )
            }
            faltan_columnas.extend(
                f"{tabla}.{c}" for c in sorted(columnas - presentes)
            )

        nombres_indices = {
            sql.split("IF NOT EXISTS ")[1].split(" ")[0] for sql in INDICES
        }
        presentes_idx = {
            r[0]
            for r in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname='public'")
            )
        }
        faltan_indices = sorted(nombres_indices - presentes_idx)

    if faltan_tablas or faltan_columnas or faltan_indices:
        print(
            "ERROR: la migración no quedó completa.\n"
            f"  tablas faltantes:   {faltan_tablas}\n"
            f"  columnas faltantes: {faltan_columnas}\n"
            f"  índices faltantes:  {faltan_indices}"
        )
        return 1

    print(
        f"OK: migración aplicada y verificada "
        f"({len(TABLAS)} tablas, {len(COLUMNAS)} columnas, {len(INDICES)} índices)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
