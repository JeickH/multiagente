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

POR QUÉ ESTA MIGRACIÓN REPARA Y NO SÓLO CREA (incidente del 2026-09-16)
    Se corrió contra RDS, salió exit 0 y reportó "8 tablas, 3 columnas, 19
    índices"... sobre ocho tablas que ya existían. Las había creado el
    `create_all()` del arranque del backend durante un despliegue fallido de
    cinco minutos, antes de que el script llegara.

    Y `create_all()` no crea lo mismo que este DDL: pone los `DEFAULT` que
    declara `models.py`, donde las columnas cuyo default es de Python
    (`default=datetime.utcnow`, `default=FILA_TIPO_PRECIO`) y no tienen
    `server_default` se crean SIN `DEFAULT` en la base.

    Como las tablas ya estaban, el `CREATE TABLE IF NOT EXISTS` fue un no-op:
    no reparó nada y no dijo nada, porque `IF NOT EXISTS` no compara la
    definición — mira si existe el nombre. RDS quedó con 21 columnas sin
    default (los 16 `created_at`/`updated_at`, más `bot_productos.tipo`,
    `bot_producto_filas.tipo`, `bot_producto_medios.tipo`,
    `bot_producto_alias.nivel` y `bot_recordatorios.orden`) y el verificador
    dio verde, porque sólo miraba nombres de tabla y de columna.

    De ahí las dos secciones que este script tiene de más:
      · `ALTER TABLE ... ALTER COLUMN ... SET DEFAULT` sobre toda columna con
        default (§ DEFAULTS). `SET DEFAULT` no distingue entre poner y
        corregir, así que es idempotente por naturaleza y corre igual sobre
        una base bien creada; sólo se emite cuando el default real difiere.
      · el verificador compara el `column_default` de esas columnas y los
        CHECK/UNIQUE esperados, no sólo que el nombre exista.

    Dos lecciones, escritas acá para que no se vuelvan a aprender:
    en una base que ya tiene las tablas, `IF NOT EXISTS` no es idempotencia,
    es ceguera; y un verificador que pasa con la base mal es peor que no tener
    verificador, porque deja seguir el despliegue.

    Raíz que NO se arregla acá: `models.py` no declara `server_default` en esas
    21 columnas (sí lo hace en las otras 25 de estas mismas tablas). Mientras
    siga así, cualquier `create_all()` que se adelante deja la base sin
    defaults y esta migración es la que lo repara.

100% idempotente (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`,
`CREATE INDEX IF NOT EXISTS`, `SET DEFAULT`). No borra ni reescribe datos:
lo único que reescribe es la definición de un default que no coincide. Correrla
dos veces seguidas no cambia nada la segunda vez.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/migrate_sprint31_productos.py

    # Sólo verificar, sin tocar la base (auditar una base ya migrada)
    docker compose -p wati exec -T backend python \
        scripts/migrate_sprint31_productos.py --verificar

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/migrate_sprint31_productos.py

OJO (gotcha histórico): migrar la base NO basta. Si la imagen de ECS lleva un
`models.py` viejo, el ORM ni ve las tablas nuevas y los scripts que las
escriben reportan cero filas en vez de fallar. Esta migración va con su
despliegue.
"""
from __future__ import annotations

import os
import re
import sys
from string import Template
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


# ── Defaults: una sola fuente de verdad ───────────────────────────────────
# Los `DEFAULT` no se escriben dentro del DDL: se declaran acá una vez y las
# tres partes del script los leen de aquí — el `CREATE TABLE` (que los interpola
# donde dice `${columna}`), el `ALTER COLUMN ... SET DEFAULT` correctivo y el
# verificador. Si cada parte los escribiera por su cuenta podrían quedar en
# desacuerdo entre sí, que es exactamente el desastre que este script existe
# para no repetir (ver el docstring).
#
# El valor es la expresión SQL tal cual va después de `DEFAULT`. Postgres la
# guarda normalizada y con el cast del tipo de la columna
# (`'producto'` vuelve como `'producto'::character varying`), así que comparar
# con `==` pelado da falsos positivos: se compara con `_normalizar_default()`.

_AHORA = "NOW()"
_JSON_VACIO = "'{}'::jsonb"

DEFAULTS: dict[str, dict[str, str]] = {
    # Tabla que ya existía; la columna la agrega este mismo script (§ COLUMNAS).
    "bots": {
        "instrucciones_version": "0",
    },
    "bot_productos": {
        "tipo": "'producto'",
        "estado": "'borrador'",
        "atributos": _JSON_VACIO,
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
    "bot_producto_variantes": {
        "atributos": _JSON_VACIO,
        "activo": "TRUE",
        "orden": "0",
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
    "bot_producto_filas": {
        "variante_id": "0",
        "tipo": "'precio'",
        "valores": _JSON_VACIO,
        "orden": "0",
        "activo": "TRUE",
        "externo_id": "''",
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
    "bot_producto_medios": {
        "variante_id": "0",
        "tipo": "'image'",
        "aplica": _JSON_VACIO,
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
    "bot_producto_alias": {
        "nivel": "'producto'",
        "ref_id": "0",
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
    "bot_producto_bots": {
        "activo": "TRUE",
        "orden": "0",
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
    "bot_producto_cargas": {
        "filas_nuevas": "0",
        "filas_cambiadas": "0",
        "filas_retiradas": "0",
        "estado": "'revision'",
        "diff": _JSON_VACIO,
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
    "bot_recordatorios": {
        "bot_id": "0",
        "orden": "1",
        "omitir_si": _JSON_VACIO,
        "hora_min": "8",
        "hora_max": "20",
        "activo": "TRUE",
        "created_at": _AHORA,
        "updated_at": _AHORA,
    },
}


def _ddl(tabla: str, plantilla: str) -> str:
    """Mete los defaults de `DEFAULTS[tabla]` en el DDL de la tabla.

    Si el DDL nombra un `${columna}` que no está declarado arriba, revienta acá
    —al importar el módulo— y no a mitad de una migración en producción.
    """
    return Template(plantilla).substitute(DEFAULTS.get(tabla, {}))


# ── Tablas ────────────────────────────────────────────────────────────────

TABLAS: list[tuple[str, str]] = [
    (
        "bot_productos",
        _ddl(
            "bot_productos",
            """
CREATE TABLE IF NOT EXISTS bot_productos (
    id              SERIAL PRIMARY KEY,
    team_id         INTEGER      NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    slug            VARCHAR(80)  NOT NULL,
    tipo            VARCHAR(24)  NOT NULL DEFAULT ${tipo},
    nombre          VARCHAR(160) NOT NULL,
    estado          VARCHAR(16)  NOT NULL DEFAULT ${estado},
    resumen         VARCHAR(240),
    instrucciones   TEXT,
    atributos       JSONB        NOT NULL DEFAULT ${atributos},
    vigencia_desde  DATE,
    vigencia_hasta  DATE,
    created_at      TIMESTAMP    NOT NULL DEFAULT ${created_at},
    updated_at      TIMESTAMP    NOT NULL DEFAULT ${updated_at},
    CONSTRAINT uq_bot_productos_team_slug UNIQUE (team_id, slug),
    CONSTRAINT ck_bot_productos_tipo
        CHECK (tipo IN ('plan','producto','catalogo_externo','ficha')),
    CONSTRAINT ck_bot_productos_estado
        CHECK (estado IN ('borrador','publicado','archivado'))
);
""",
        ),
    ),
    (
        "bot_producto_variantes",
        _ddl(
            "bot_producto_variantes",
            """
CREATE TABLE IF NOT EXISTS bot_producto_variantes (
    id                     SERIAL PRIMARY KEY,
    producto_id            INTEGER      NOT NULL
                           REFERENCES bot_productos(id) ON DELETE CASCADE,
    slug                   VARCHAR(80)  NOT NULL,
    nombre                 VARCHAR(160) NOT NULL,
    instrucciones          TEXT,
    atributos              JSONB        NOT NULL DEFAULT ${atributos},
    precios_de_variante_id INTEGER
                           REFERENCES bot_producto_variantes(id) ON DELETE SET NULL,
    activo                 BOOLEAN      NOT NULL DEFAULT ${activo},
    orden                  INTEGER      NOT NULL DEFAULT ${orden},
    created_at             TIMESTAMP    NOT NULL DEFAULT ${created_at},
    updated_at             TIMESTAMP    NOT NULL DEFAULT ${updated_at},
    CONSTRAINT uq_bot_producto_variantes_slug UNIQUE (producto_id, slug)
);
""",
        ),
    ),
    (
        "bot_producto_filas",
        # `variante_id` y `externo_id` con centinela (0 / '') y NOT NULL: es lo
        # que hace que el UNIQUE sea de verdad un candado contra el importador
        # repetido. Ver el docstring.
        _ddl(
            "bot_producto_filas",
            """
CREATE TABLE IF NOT EXISTS bot_producto_filas (
    id          BIGSERIAL PRIMARY KEY,
    producto_id INTEGER      NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    variante_id INTEGER      NOT NULL DEFAULT ${variante_id},
    tipo        VARCHAR(16)  NOT NULL DEFAULT ${tipo},
    etiqueta    VARCHAR(160),
    inicio      DATE,
    fin         DATE,
    valores     JSONB        NOT NULL DEFAULT ${valores},
    nota        TEXT,
    orden       INTEGER      NOT NULL DEFAULT ${orden},
    activo      BOOLEAN      NOT NULL DEFAULT ${activo},
    externo_id  VARCHAR(120) NOT NULL DEFAULT ${externo_id},
    created_at  TIMESTAMP    NOT NULL DEFAULT ${created_at},
    updated_at  TIMESTAMP    NOT NULL DEFAULT ${updated_at},
    CONSTRAINT uq_bot_producto_filas_externo
        UNIQUE (producto_id, variante_id, externo_id),
    CONSTRAINT ck_bot_producto_filas_tipo
        CHECK (tipo IN ('salida','precio','sede','envio','faq'))
);
""",
        ),
    ),
    (
        "bot_producto_medios",
        _ddl(
            "bot_producto_medios",
            """
CREATE TABLE IF NOT EXISTS bot_producto_medios (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER       NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    variante_id INTEGER       NOT NULL DEFAULT ${variante_id},
    clave       VARCHAR(80)   NOT NULL,
    url         VARCHAR(1024) NOT NULL,
    tipo        VARCHAR(24)   NOT NULL DEFAULT ${tipo},
    descripcion VARCHAR(300),
    aplica      JSONB         NOT NULL DEFAULT ${aplica},
    created_at  TIMESTAMP     NOT NULL DEFAULT ${created_at},
    updated_at  TIMESTAMP     NOT NULL DEFAULT ${updated_at}
);
""",
        ),
    ),
    (
        "bot_producto_alias",
        _ddl(
            "bot_producto_alias",
            """
CREATE TABLE IF NOT EXISTS bot_producto_alias (
    id          SERIAL PRIMARY KEY,
    producto_id INTEGER      NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    nivel       VARCHAR(16)  NOT NULL DEFAULT ${nivel},
    ref_id      INTEGER      NOT NULL DEFAULT ${ref_id},
    alias       VARCHAR(160) NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT ${created_at},
    updated_at  TIMESTAMP    NOT NULL DEFAULT ${updated_at},
    CONSTRAINT uq_bot_producto_alias UNIQUE (producto_id, nivel, alias),
    CONSTRAINT ck_bot_producto_alias_nivel
        CHECK (nivel IN ('producto','variante'))
);
""",
        ),
    ),
    (
        "bot_producto_bots",
        _ddl(
            "bot_producto_bots",
            """
CREATE TABLE IF NOT EXISTS bot_producto_bots (
    id          SERIAL PRIMARY KEY,
    bot_id      INTEGER   NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    producto_id INTEGER   NOT NULL
                REFERENCES bot_productos(id) ON DELETE CASCADE,
    activo      BOOLEAN   NOT NULL DEFAULT ${activo},
    orden       INTEGER   NOT NULL DEFAULT ${orden},
    created_at  TIMESTAMP NOT NULL DEFAULT ${created_at},
    updated_at  TIMESTAMP NOT NULL DEFAULT ${updated_at},
    CONSTRAINT uq_bot_producto_bots UNIQUE (bot_id, producto_id)
);
""",
        ),
    ),
    (
        "bot_producto_cargas",
        _ddl(
            "bot_producto_cargas",
            """
CREATE TABLE IF NOT EXISTS bot_producto_cargas (
    id                   SERIAL PRIMARY KEY,
    producto_id          INTEGER      NOT NULL
                         REFERENCES bot_productos(id) ON DELETE CASCADE,
    archivo              VARCHAR(300) NOT NULL,
    hash_sha256          VARCHAR(64),
    filas_nuevas         INTEGER      NOT NULL DEFAULT ${filas_nuevas},
    filas_cambiadas      INTEGER      NOT NULL DEFAULT ${filas_cambiadas},
    filas_retiradas      INTEGER      NOT NULL DEFAULT ${filas_retiradas},
    estado               VARCHAR(16)  NOT NULL DEFAULT ${estado},
    diff                 JSONB        NOT NULL DEFAULT ${diff},
    aprobado_por_user_id INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    created_at           TIMESTAMP    NOT NULL DEFAULT ${created_at},
    updated_at           TIMESTAMP    NOT NULL DEFAULT ${updated_at},
    CONSTRAINT ck_bot_producto_cargas_estado
        CHECK (estado IN ('revision','aplicado','rechazado'))
);
""",
        ),
    ),
    (
        "bot_recordatorios",
        _ddl(
            "bot_recordatorios",
            """
CREATE TABLE IF NOT EXISTS bot_recordatorios (
    id         SERIAL PRIMARY KEY,
    team_id    INTEGER   NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    bot_id     INTEGER   NOT NULL DEFAULT ${bot_id},
    orden      INTEGER   NOT NULL DEFAULT ${orden},
    minutos    INTEGER   NOT NULL,
    texto      TEXT      NOT NULL,
    omitir_si  JSONB     NOT NULL DEFAULT ${omitir_si},
    hora_min   INTEGER   NOT NULL DEFAULT ${hora_min},
    hora_max   INTEGER   NOT NULL DEFAULT ${hora_max},
    activo     BOOLEAN   NOT NULL DEFAULT ${activo},
    created_at TIMESTAMP NOT NULL DEFAULT ${created_at},
    updated_at TIMESTAMP NOT NULL DEFAULT ${updated_at},
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
        _ddl(
            "bots",
            "ALTER TABLE bots ADD COLUMN IF NOT EXISTS instrucciones_version "
            "INTEGER NOT NULL DEFAULT ${instrucciones_version};",
        ),
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


# ── CHECK y UNIQUE esperados, leídos del propio DDL ───────────────────────
# Mismo criterio que con los defaults: no se escriben dos veces. Los nombres
# salen de los `CONSTRAINT ... CHECK` / `CONSTRAINT ... UNIQUE` del DDL de
# arriba, así que agregar una restricción al DDL la deja verificada sin tocar
# nada más. Sin esto, un `create_all()` adelantado podría dejar una tabla sin
# su CHECK y la migración saldría verde igual.

_RE_CONSTRAINT = re.compile(r"CONSTRAINT\s+(\w+)\s+(CHECK|UNIQUE)\s*\(", re.IGNORECASE)
_RE_CHECK_O_UNIQUE = re.compile(r"\b(?:CHECK|UNIQUE)\s*\(", re.IGNORECASE)


def _constraints_del_ddl() -> dict[str, dict[str, str]]:
    """`{tabla: {nombre_constraint: 'c'|'u'}}` tal como lo declara el DDL."""
    encontrados: dict[str, dict[str, str]] = {}
    for tabla, ddl in TABLAS:
        hallados = _RE_CONSTRAINT.findall(ddl)
        # Guardarraíl: si el DDL declara un CHECK/UNIQUE que la expresión de
        # arriba no supo leer, preferimos reventar al arrancar antes que
        # verificar de menos y no enterarnos.
        if len(hallados) != len(_RE_CHECK_O_UNIQUE.findall(ddl)):
            raise RuntimeError(
                f"{tabla}: hay CHECK/UNIQUE en el DDL que no quedaron con "
                "nombre o que `_RE_CONSTRAINT` no reconoce. Arregla el DDL o "
                "la expresión regular: si no, el verificador no los revisa."
            )
        encontrados[tabla] = {
            nombre: tipo[0].lower() for nombre, tipo in hallados
        }
    return encontrados


CONSTRAINTS = _constraints_del_ddl()


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _normalizar_default(expr: str | None) -> str:
    """Deja comparable lo que escribimos con lo que Postgres devuelve.

    Postgres guarda el default ya normalizado y con el cast del tipo de la
    columna: `'producto'` vuelve como `'producto'::character varying`, `TRUE`
    como `true` y `NOW()` como `now()`. Sin esta normalización el verificador
    marcaría como diferente todo lo que en realidad está bien.
    """
    if not expr:
        return ""
    texto = " ".join(expr.split()).lower()
    # Un único cast al final, que es como los escribe Postgres.
    texto = re.sub(r"::[a-z0-9_ \.\"\[\]]+$", "", texto)
    return texto.strip()


def _defaults_en_la_base(conn) -> dict[tuple[str, str], str | None]:
    """`{(tabla, columna): column_default}` para las tablas que nos importan.

    Una sola consulta y el filtro en Python: son pocas columnas y así no
    dependemos de cómo cada driver arma un `IN` con lista.
    """
    filas = conn.execute(
        text(
            "SELECT table_name, column_name, column_default "
            "FROM information_schema.columns WHERE table_schema='public'"
        )
    )
    return {
        (t, c): d for t, c, d in filas if t in DEFAULTS and c in DEFAULTS[t]
    }


def _constraints_en_la_base(conn) -> dict[str, dict[str, str]]:
    """`{tabla: {nombre: contype}}` con los CHECK y UNIQUE que existen hoy."""
    filas = conn.execute(
        text(
            "SELECT c.relname, con.conname, con.contype "
            "FROM pg_constraint con "
            "JOIN pg_class c ON c.oid = con.conrelid "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND con.contype IN ('c','u')"
        )
    )
    presentes: dict[str, dict[str, str]] = {}
    for tabla, nombre, tipo in filas:
        presentes.setdefault(tabla, {})[nombre] = tipo
    return presentes


def reparar_defaults(conn) -> list[str]:
    """Pone el `DEFAULT` que falta o que no coincide. Devuelve lo reparado.

    Existe porque el `CREATE TABLE IF NOT EXISTS` de arriba es un no-op cuando
    la tabla ya está —aunque esté mal—, y `create_all()` nos gana la carrera
    más seguido de lo que parece. Ver el docstring del módulo.

    Sólo emite el ALTER cuando el default real difiere del declarado: así la
    segunda corrida no sólo es inofensiva, sino que lo dice ("0 reparados").
    """
    actuales = _defaults_en_la_base(conn)
    reparados: list[str] = []
    for tabla, columnas in DEFAULTS.items():
        for columna, expr in columnas.items():
            if (tabla, columna) not in actuales:
                continue  # la columna no existe: lo grita la verificación
            if _normalizar_default(actuales[(tabla, columna)]) == _normalizar_default(
                expr
            ):
                continue
            # Identificadores y expresión salen de las constantes de este
            # archivo, no de entrada externa; el DDL no admite bind params.
            conn.execute(
                text(f"ALTER TABLE {tabla} ALTER COLUMN {columna} SET DEFAULT {expr}")
            )
            reparados.append(f"{tabla}.{columna} → {expr}")
    return reparados


def aplicar(engine) -> None:
    """Crea, agrega y repara. Todo en una transacción."""
    with engine.begin() as conn:
        for nombre, ddl in TABLAS:
            conn.execute(text(ddl))
            print(f"  ✓ tabla {nombre}")
        for tabla, columna, ddl in COLUMNAS:
            conn.execute(text(ddl))
            print(f"  ✓ columna {tabla}.{columna}")

        # Reparación de defaults. Va DESPUÉS de las dos secciones anteriores
        # porque repara columnas que quizá acaban de nacer ahí mismo.
        reparados = reparar_defaults(conn)
        total_defaults = sum(len(c) for c in DEFAULTS.values())
        for cambio in reparados:
            print(f"  ↻ default repuesto: {cambio}")
        print(
            f"  ✓ {total_defaults} defaults en su sitio "
            f"({len(reparados)} reparados)"
        )

        for sql in INDICES:
            conn.execute(text(sql))
        print(f"  ✓ {len(INDICES)} índices")


def verificar(engine) -> int:
    """Devuelve 1 si la base no es la que este script dice dejar.

    Mira nombres (tablas, columnas, índices) y —desde el incidente del
    2026-09-16— también DEFINICIÓN: el `column_default` real de cada columna
    con default y los CHECK/UNIQUE esperados. La versión anterior sólo miraba
    nombres y por eso dio exit 0 sobre una RDS a la que le faltaban los
    defaults de 21 columnas.
    """
    faltan_tablas: list[str] = []
    faltan_columnas: list[str] = []
    faltan_indices: list[str] = []
    defaults_mal: list[str] = []
    faltan_constraints: list[str] = []

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

        # ── Defaults: acá es donde se cayó el verificador viejo ────────────
        # Que la columna exista no dice nada sobre cómo quedó definida. Si
        # `create_all()` creó la tabla antes que esta migración, la columna
        # está —con el nombre y el tipo correctos— pero sin su DEFAULT.
        actuales = _defaults_en_la_base(conn)
        for tabla, columnas in DEFAULTS.items():
            for columna, expr in sorted(columnas.items()):
                if (tabla, columna) not in actuales:
                    continue  # ya se reporta como columna faltante
                real = actuales[(tabla, columna)]
                if _normalizar_default(real) != _normalizar_default(expr):
                    defaults_mal.append(
                        f"{tabla}.{columna}: esperado {expr}, "
                        f"encontrado {real if real is not None else 'SIN DEFAULT'}"
                    )

        # ── CHECK y UNIQUE ────────────────────────────────────────────────
        presentes_con = _constraints_en_la_base(conn)
        for tabla, esperados_con in CONSTRAINTS.items():
            if tabla in faltan_tablas:
                continue
            de_la_tabla = presentes_con.get(tabla, {})
            for nombre, tipo in sorted(esperados_con.items()):
                etiqueta = "CHECK" if tipo == "c" else "UNIQUE"
                if nombre not in de_la_tabla:
                    faltan_constraints.append(f"{tabla}.{nombre} ({etiqueta})")
                elif de_la_tabla[nombre] != tipo:
                    faltan_constraints.append(
                        f"{tabla}.{nombre}: se esperaba {etiqueta} y es "
                        f"contype={de_la_tabla[nombre]!r}"
                    )

    total_defaults = sum(len(c) for c in DEFAULTS.values())
    total_constraints = sum(len(c) for c in CONSTRAINTS.values())

    hallazgos = [
        ("tablas faltantes", faltan_tablas),
        ("columnas faltantes", faltan_columnas),
        ("índices faltantes", faltan_indices),
        ("defaults que no son", defaults_mal),
        ("CHECK/UNIQUE ausentes", faltan_constraints),
    ]
    if any(lista for _, lista in hallazgos):
        # Uno por línea: cuando falla de verdad son 21 renglones, y en una
        # sola línea de log no los lee nadie.
        print("ERROR: la base no quedó como dice este script.")
        for titulo, lista in hallazgos:
            print(f"  {titulo}: {len(lista)}")
            for item in lista:
                print(f"      - {item}")
        print(
            "Si lo que falla son defaults, la tabla probablemente la creó "
            "`create_all()` y no esta migración: correrla completa (sin "
            "--verificar) los repone. Un CHECK/UNIQUE ausente NO se repara "
            "solo — hay que agregarlo a mano con el DDL de este archivo."
        )
        return 1

    print(
        f"OK: verificado ({len(TABLAS)} tablas, {len(COLUMNAS)} columnas, "
        f"{len(INDICES)} índices, {total_defaults} defaults, "
        f"{total_constraints} CHECK/UNIQUE)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    solo_verificar = "--verificar" in argv

    print(f"Conectando a host: {_host(DATABASE_URL) or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)

    if solo_verificar:
        print("Modo --verificar: no se toca la base.")
    else:
        aplicar(engine)

    return verificar(engine)


if __name__ == "__main__":
    sys.exit(main())
