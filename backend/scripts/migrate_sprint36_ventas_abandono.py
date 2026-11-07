"""Migración Sprint 36 — ventas por conversación, reenganche y agenda de llamadas.

Qué deja en la base (todo declarado TAMBIÉN en `models.py`, por el gotcha de
`create_all()` del 17-sep-2026):

conversations
  + abandono_at TIMESTAMP NULL, abandono_asesor VARCHAR(64) NULL,
    reclamos_abandono INTEGER NOT NULL DEFAULT 0,
    ultimo_mensaje_humano_at TIMESTAMP NULL, cerrada_por_inactividad_at TIMESTAMP NULL,
    marcador_consumido VARCHAR(16) NULL
  + CHECK ck_conversations_marcador_consumido  (volvio | humano)
  + UNIQUE uq_conversations_id_team (id, team_id) — índice CONCURRENTLY y luego
    constraint USING INDEX; es el destino de la FK compuesta de las ventas.

conversation_sales (tabla nueva, modelo `ConversationSale`)
  + FK compuesta fk_conversation_sales_conv_team (conversation_id, team_id)
    → conversations (id, team_id) ON DELETE CASCADE  (diseño de seguridad 0.2)
  + FK team_id → teams CASCADE; bot_id → bots SET NULL (0.7);
    registrada_por_user_id / anulada_por_user_id → users SET NULL
  + CHECK ck_conversation_sales_valor (0 < valor ≤ 500.000.000)
  + CHECK ck_conversation_sales_anulacion (anular es todo o nada, 0.5)
  + UNIQUE parcial uq_conversation_sales_activa (conversation_id) WHERE anulada_at IS NULL
  + ix_conversation_sales_{id, conversation_id, team_conv, bot_id}
  + created_at DEFAULT now()

bots
  + es_reenganche BOOLEAN NOT NULL DEFAULT false
  + UNIQUE parcial uq_bot_reenganche_por_owner (user_id) WHERE es_reenganche

agendamientos
  + franja_inicio TIMESTAMP, puesto SMALLINT, origen VARCHAR(16),
    resultado VARCHAR(16), resultado_por_user_id INTEGER (FK users SET NULL),
    resultado_at, aviso_inicio_at, alerta_fin_at TIMESTAMP, cotizacion TEXT
  + CHECK ck_agendamientos_puesto (puesto >= 1)
  + CHECK ck_agendamientos_franja_con_puesto (franja y puesto, los dos o ninguno:
    sin esto una franja sin puesto se saltaría el cupo)
  + CHECK ck_agendamientos_origen (abandono | bot_llamada)
  + CHECK ck_agendamientos_resultado (vendida | lo_pensara | no_contesto)
  + CHECK ck_agendamientos_cotizacion_largo (length ≤ 1000)
  + UNIQUE parcial uq_agendamientos_franja_puesto (team_id, franja_inicio, puesto)
    WHERE franja_inicio IS NOT NULL AND estado = 'pendiente'

Cómo cuida los bloqueos
  - `lock_timeout` 10 s en cada sentencia DDL: si una transacción larga tiene
    la tabla, falla en vez de encolar detrás a los webhooks y al tick. Se
    vuelve a correr y ya.
  - Una transacción corta por tabla; ningún backfill dentro del DDL.
  - ADD COLUMN con DEFAULT constante no reescribe la tabla (PG ≥ 11).
  - CHECK y FK sobre tablas que ya existen se agregan NOT VALID (instantáneo) y
    se validan después en su propia transacción (VALIDATE toma SHARE UPDATE
    EXCLUSIVE: no frena lecturas ni escrituras).
  - El índice de `conversations` va CONCURRENTLY en autocommit. Si una corrida
    anterior lo dejó INVÁLIDO (CONCURRENTLY cortado a mitad), se borra y se
    rehace: `IF NOT EXISTS` solo no lo repararía nunca.

Idempotente y reparadora: cada pieza se crea solo si falta; los DEFAULT y el
NOT NULL se reponen solo si el real difiere, y lo dice («N reparados»). La FK
simple `conversation_sales_conversation_id_fkey` del borrador `370f4f9`, si
existiera, se reemplaza por la compuesta. La segunda corrida dice «0 cambios,
0 reparados».

El verificador compara DEFINICIONES (tipo, nulabilidad, default, largo; texto
de cada CHECK, índice y FK; que estén validados), no solo nombres, y sale con
código 1 listando lo que no cuadra.

BACKFILL (solo columnas nuevas, solo donde siguen en NULL; nunca borra). Por
defecto SOLO cuenta. Escribe con `BACKFILL=1` (todos) o con una lista:
`BACKFILL=origen,humano`. Va por lotes de `LOTE` ids (1000 por defecto), cada
lote en su transacción con `lock_timeout` 5 s y `statement_timeout` 60 s.
  humano       conversations.ultimo_mensaje_humano_at = último saliente humano
               real (outbound, sent_by_user_id no nulo, no nota, no failed).
  inactividad  conversations.cerrada_por_inactividad_at = fecha de la nota
               «🔒 *Cerrada por inactividad*», en las que siguen cerradas.
  abandono     conversations.abandono_at / abandono_asesor en las hoy
               abandonadas (pending + etiqueta) = nota «🕒 *…*» del sistema y
               el `assigned_to` actual. reclamos_abandono queda en 0.
  origen       agendamientos.origen = 'abandono' (antes del Sprint 36 todas
               las llamadas salían del abandono).
OJO: `inactividad` y `abandono` dejan esas conversaciones históricas
RECLAMABLES por el bot de reenganche cuando el cliente vuelva. Es decisión de
producto correrlos en RDS.

Uso:
    # Local (proyecto compose `wati`; el contenedor no monta `scripts/`)
    docker compose -p wati exec -T backend python - < backend/scripts/migrate_sprint36_ventas_abandono.py
    docker compose -p wati exec -T -e BACKFILL=1 backend python - < backend/scripts/migrate_sprint36_ventas_abandono.py

    # Producción (RDS sa-east-1): ecs run-task con la task-def NUEVA,
    # command=["python","scripts/migrate_sprint36_ventas_abandono.py"]
    # ANTES del update-service: la imagen nueva hace create_all() al arrancar
    # y su FK compuesta necesita `uq_conversations_id_team` ya creado.

OJO (gotcha histórico): migrar la base NO basta, hay que desplegar el modelo.
"""
from __future__ import annotations

import os
import re
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


# Foto del esquema a la fecha de esta migración. No se importa de models.py a
# propósito: una migración es una foto del pasado (lo vigila
# tests/test_conversation_sales_schema.py, comparando en las dos direcciones).

LOCK_TIMEOUT = "10s"
LOTE = max(1, int(os.environ.get("LOTE", "1000") or 1000))

# ---------------------------------------------------------------------------
# 1. DDL
# ---------------------------------------------------------------------------

COLUMNAS: dict[str, list[tuple[str, str]]] = {
    "conversations": [
        ("abandono_at", "TIMESTAMP WITHOUT TIME ZONE NULL"),
        ("abandono_asesor", "VARCHAR(64) NULL"),
        ("reclamos_abandono", "INTEGER NOT NULL DEFAULT 0"),
        ("ultimo_mensaje_humano_at", "TIMESTAMP WITHOUT TIME ZONE NULL"),
        ("cerrada_por_inactividad_at", "TIMESTAMP WITHOUT TIME ZONE NULL"),
        ("marcador_consumido", "VARCHAR(16) NULL"),
    ],
    "bots": [
        ("es_reenganche", "BOOLEAN NOT NULL DEFAULT false"),
    ],
    "agendamientos": [
        ("franja_inicio", "TIMESTAMP WITHOUT TIME ZONE NULL"),
        ("puesto", "SMALLINT NULL"),
        ("origen", "VARCHAR(16) NULL"),
        ("resultado", "VARCHAR(16) NULL"),
        ("resultado_por_user_id", "INTEGER NULL"),
        ("resultado_at", "TIMESTAMP WITHOUT TIME ZONE NULL"),
        ("aviso_inicio_at", "TIMESTAMP WITHOUT TIME ZONE NULL"),
        ("alerta_fin_at", "TIMESTAMP WITHOUT TIME ZONE NULL"),
        ("cotizacion", "TEXT NULL"),
    ],
    # Por si la tabla existiera de un borrador anterior sin esta columna.
    "conversation_sales": [
        ("bot_id", "INTEGER NULL"),
    ],
}

CREAR_VENTAS = """
CREATE TABLE IF NOT EXISTS conversation_sales (
    id SERIAL NOT NULL,
    team_id INTEGER NOT NULL,
    conversation_id INTEGER NOT NULL,
    bot_id INTEGER,
    valor_cop BIGINT NOT NULL,
    nota VARCHAR(280),
    vendida_por VARCHAR(64),
    registrada_por_user_id INTEGER,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
    anulada_at TIMESTAMP WITHOUT TIME ZONE,
    anulada_por_user_id INTEGER,
    motivo_anulacion VARCHAR(280),
    CONSTRAINT conversation_sales_pkey PRIMARY KEY (id),
    CONSTRAINT fk_conversation_sales_conv_team
        FOREIGN KEY (conversation_id, team_id)
        REFERENCES conversations (id, team_id) ON DELETE CASCADE,
    CONSTRAINT ck_conversation_sales_valor
        CHECK (valor_cop > 0 AND valor_cop <= 500000000),
    CONSTRAINT ck_conversation_sales_anulacion
        CHECK ((anulada_at IS NULL AND motivo_anulacion IS NULL AND anulada_por_user_id IS NULL)
            OR (anulada_at IS NOT NULL AND motivo_anulacion IS NOT NULL)),
    CONSTRAINT conversation_sales_team_id_fkey
        FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE,
    CONSTRAINT conversation_sales_bot_id_fkey
        FOREIGN KEY (bot_id) REFERENCES bots (id) ON DELETE SET NULL,
    CONSTRAINT conversation_sales_registrada_por_user_id_fkey
        FOREIGN KEY (registrada_por_user_id) REFERENCES users (id) ON DELETE SET NULL,
    CONSTRAINT conversation_sales_anulada_por_user_id_fkey
        FOREIGN KEY (anulada_por_user_id) REFERENCES users (id) ON DELETE SET NULL
)
"""

#: (tabla, nombre, cuerpo del ADD CONSTRAINT). Se agregan NOT VALID si faltan
#: (tabla vieja o borrador) y se validan aparte.
CONSTRAINTS: list[tuple[str, str, str]] = [
    ("conversations", "ck_conversations_marcador_consumido",
     "CHECK (marcador_consumido IN ('volvio', 'humano'))"),
    ("conversation_sales", "fk_conversation_sales_conv_team",
     "FOREIGN KEY (conversation_id, team_id) REFERENCES conversations (id, team_id) ON DELETE CASCADE"),
    ("conversation_sales", "conversation_sales_team_id_fkey",
     "FOREIGN KEY (team_id) REFERENCES teams (id) ON DELETE CASCADE"),
    ("conversation_sales", "conversation_sales_bot_id_fkey",
     "FOREIGN KEY (bot_id) REFERENCES bots (id) ON DELETE SET NULL"),
    ("conversation_sales", "conversation_sales_registrada_por_user_id_fkey",
     "FOREIGN KEY (registrada_por_user_id) REFERENCES users (id) ON DELETE SET NULL"),
    ("conversation_sales", "conversation_sales_anulada_por_user_id_fkey",
     "FOREIGN KEY (anulada_por_user_id) REFERENCES users (id) ON DELETE SET NULL"),
    ("conversation_sales", "ck_conversation_sales_valor",
     "CHECK (valor_cop > 0 AND valor_cop <= 500000000)"),
    ("conversation_sales", "ck_conversation_sales_anulacion",
     "CHECK ((anulada_at IS NULL AND motivo_anulacion IS NULL AND anulada_por_user_id IS NULL)"
     " OR (anulada_at IS NOT NULL AND motivo_anulacion IS NOT NULL))"),
    ("agendamientos", "agendamientos_resultado_por_user_id_fkey",
     "FOREIGN KEY (resultado_por_user_id) REFERENCES users (id) ON DELETE SET NULL"),
    ("agendamientos", "ck_agendamientos_puesto", "CHECK (puesto >= 1)"),
    ("agendamientos", "ck_agendamientos_franja_con_puesto",
     "CHECK ((franja_inicio IS NULL) = (puesto IS NULL))"),
    ("agendamientos", "ck_agendamientos_origen",
     "CHECK (origen IN ('abandono', 'bot_llamada'))"),
    ("agendamientos", "ck_agendamientos_resultado",
     "CHECK (resultado IN ('vendida', 'lo_pensara', 'no_contesto'))"),
    ("agendamientos", "ck_agendamientos_cotizacion_largo",
     "CHECK (length(cotizacion) <= 1000)"),
]

#: Del borrador 370f4f9: la FK simple que la compuesta reemplaza.
CONSTRAINTS_SOBRANTES = [("conversation_sales", "conversation_sales_conversation_id_fkey")]

#: Índices normales (tablas chicas o nuevas), en la transacción de su tabla.
INDICES: dict[str, list[str]] = {
    "conversation_sales": [
        "CREATE INDEX IF NOT EXISTS ix_conversation_sales_id ON conversation_sales (id)",
        "CREATE INDEX IF NOT EXISTS ix_conversation_sales_conversation_id "
        "ON conversation_sales (conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_conversation_sales_team_conv "
        "ON conversation_sales (team_id, conversation_id)",
        "CREATE INDEX IF NOT EXISTS ix_conversation_sales_bot_id ON conversation_sales (bot_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_sales_activa "
        "ON conversation_sales (conversation_id) WHERE anulada_at IS NULL",
    ],
    "bots": [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_bot_reenganche_por_owner "
        "ON bots (user_id) WHERE es_reenganche",
    ],
    "agendamientos": [
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_agendamientos_franja_puesto "
        "ON agendamientos (team_id, franja_inicio, puesto) "
        "WHERE franja_inicio IS NOT NULL AND estado = 'pendiente'",
    ],
}

#: (tabla, columna) → (literal para SET DEFAULT, como lo devuelve information_schema)
DEFAULTS: dict[tuple[str, str], tuple[str, str]] = {
    ("conversations", "reclamos_abandono"): ("0", "0"),
    ("bots", "es_reenganche"): ("false", "false"),
    ("conversation_sales", "created_at"): ("now()", "now()"),
}
#: Columnas que deben ser NOT NULL aunque hayan nacido por otro camino.
NOT_NULL = {("conversations", "reclamos_abandono"): "0", ("bots", "es_reenganche"): "false"}

# ---------------------------------------------------------------------------
# 2. Lo que el verificador espera
# ---------------------------------------------------------------------------

_TS = "timestamp without time zone"
_VC = "character varying"

#: tabla → columna → (tipo, nullable, default normalizado o None, largo o None)
ESPERADAS: dict[str, dict[str, tuple]] = {
    "conversations": {
        "abandono_at": (_TS, "YES", None, None),
        "abandono_asesor": (_VC, "YES", None, 64),
        "reclamos_abandono": ("integer", "NO", "0", None),
        "ultimo_mensaje_humano_at": (_TS, "YES", None, None),
        "cerrada_por_inactividad_at": (_TS, "YES", None, None),
        "marcador_consumido": (_VC, "YES", None, 16),
    },
    "bots": {
        "es_reenganche": ("boolean", "NO", "false", None),
    },
    "agendamientos": {
        "franja_inicio": (_TS, "YES", None, None),
        "puesto": ("smallint", "YES", None, None),
        "origen": (_VC, "YES", None, 16),
        "resultado": (_VC, "YES", None, 16),
        "resultado_por_user_id": ("integer", "YES", None, None),
        "resultado_at": (_TS, "YES", None, None),
        "aviso_inicio_at": (_TS, "YES", None, None),
        "alerta_fin_at": (_TS, "YES", None, None),
        "cotizacion": ("text", "YES", None, None),
    },
    "conversation_sales": {
        "id": ("integer", "NO", "nextval('conversation_sales_id_seq'::regclass)", None),
        "team_id": ("integer", "NO", None, None),
        "conversation_id": ("integer", "NO", None, None),
        "bot_id": ("integer", "YES", None, None),
        "valor_cop": ("bigint", "NO", None, None),
        "nota": (_VC, "YES", None, 280),
        "vendida_por": (_VC, "YES", None, 64),
        "registrada_por_user_id": ("integer", "YES", None, None),
        "created_at": (_TS, "NO", "now()", None),
        "anulada_at": (_TS, "YES", None, None),
        "anulada_por_user_id": ("integer", "YES", None, None),
        "motivo_anulacion": (_VC, "YES", None, 280),
    },
}
#: En la tabla nueva, cualquier columna, índice o constraint de más es error.
TABLAS_EXACTAS = {"conversation_sales"}

#: tabla → nombre → definición tal como la devuelve pg_get_constraintdef
CONSTRAINTS_ESPERADAS: dict[str, dict[str, str]] = {
    "conversations": {
        "uq_conversations_id_team": "UNIQUE (id, team_id)",
        "ck_conversations_marcador_consumido": (
            "CHECK (((marcador_consumido)::text = ANY ((ARRAY['volvio'::character varying, "
            "'humano'::character varying])::text[])))"
        ),
    },
    "conversation_sales": {
        "conversation_sales_pkey": "PRIMARY KEY (id)",
        "fk_conversation_sales_conv_team": (
            "FOREIGN KEY (conversation_id, team_id) REFERENCES conversations(id, team_id) "
            "ON DELETE CASCADE"
        ),
        "conversation_sales_team_id_fkey": (
            "FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE"
        ),
        "conversation_sales_bot_id_fkey": (
            "FOREIGN KEY (bot_id) REFERENCES bots(id) ON DELETE SET NULL"
        ),
        "conversation_sales_registrada_por_user_id_fkey": (
            "FOREIGN KEY (registrada_por_user_id) REFERENCES users(id) ON DELETE SET NULL"
        ),
        "conversation_sales_anulada_por_user_id_fkey": (
            "FOREIGN KEY (anulada_por_user_id) REFERENCES users(id) ON DELETE SET NULL"
        ),
        "ck_conversation_sales_valor": "CHECK (((valor_cop > 0) AND (valor_cop <= 500000000)))",
        "ck_conversation_sales_anulacion": (
            "CHECK ((((anulada_at IS NULL) AND (motivo_anulacion IS NULL) AND "
            "(anulada_por_user_id IS NULL)) OR ((anulada_at IS NOT NULL) AND "
            "(motivo_anulacion IS NOT NULL))))"
        ),
    },
    "agendamientos": {
        "agendamientos_resultado_por_user_id_fkey": (
            "FOREIGN KEY (resultado_por_user_id) REFERENCES users(id) ON DELETE SET NULL"
        ),
        "ck_agendamientos_puesto": "CHECK ((puesto >= 1))",
        "ck_agendamientos_franja_con_puesto": "CHECK (((franja_inicio IS NULL) = (puesto IS NULL)))",
        "ck_agendamientos_origen": (
            "CHECK (((origen)::text = ANY ((ARRAY['abandono'::character varying, "
            "'bot_llamada'::character varying])::text[])))"
        ),
        "ck_agendamientos_resultado": (
            "CHECK (((resultado)::text = ANY ((ARRAY['vendida'::character varying, "
            "'lo_pensara'::character varying, 'no_contesto'::character varying])::text[])))"
        ),
        "ck_agendamientos_cotizacion_largo": "CHECK ((length(cotizacion) <= 1000))",
    },
}

#: tabla → índice → indexdef sin el esquema (`ON public.x` → `ON x`)
INDICES_ESPERADOS: dict[str, dict[str, str]] = {
    "conversations": {
        "uq_conversations_id_team": (
            "CREATE UNIQUE INDEX uq_conversations_id_team ON conversations USING btree (id, team_id)"
        ),
    },
    "conversation_sales": {
        "conversation_sales_pkey": (
            "CREATE UNIQUE INDEX conversation_sales_pkey ON conversation_sales USING btree (id)"
        ),
        "ix_conversation_sales_id": (
            "CREATE INDEX ix_conversation_sales_id ON conversation_sales USING btree (id)"
        ),
        "ix_conversation_sales_conversation_id": (
            "CREATE INDEX ix_conversation_sales_conversation_id ON conversation_sales "
            "USING btree (conversation_id)"
        ),
        "ix_conversation_sales_team_conv": (
            "CREATE INDEX ix_conversation_sales_team_conv ON conversation_sales "
            "USING btree (team_id, conversation_id)"
        ),
        "ix_conversation_sales_bot_id": (
            "CREATE INDEX ix_conversation_sales_bot_id ON conversation_sales USING btree (bot_id)"
        ),
        "uq_conversation_sales_activa": (
            "CREATE UNIQUE INDEX uq_conversation_sales_activa ON conversation_sales "
            "USING btree (conversation_id) WHERE (anulada_at IS NULL)"
        ),
    },
    "bots": {
        "uq_bot_reenganche_por_owner": (
            "CREATE UNIQUE INDEX uq_bot_reenganche_por_owner ON bots USING btree (user_id) "
            "WHERE es_reenganche"
        ),
    },
    "agendamientos": {
        "uq_agendamientos_franja_puesto": (
            "CREATE UNIQUE INDEX uq_agendamientos_franja_puesto ON agendamientos USING btree "
            "(team_id, franja_inicio, puesto) WHERE ((franja_inicio IS NOT NULL) AND "
            "((estado)::text = 'pendiente'::text))"
        ),
    },
}

# ---------------------------------------------------------------------------
# 3. Backfill
# ---------------------------------------------------------------------------

MARCA_INACTIVIDAD = "🔒 *Cerrada por inactividad*%"
MARCA_ABANDONO = "🕒 *%"

_RANGO_M = "m.conversation_id > :desde AND m.conversation_id <= :hasta"

_HUMANO = (
    "SELECT m.conversation_id, MAX(m.created_at) AS at FROM messages m "
    "WHERE m.direction = 'outbound' AND m.sent_by_user_id IS NOT NULL "
    "AND m.message_type <> 'nota_interna' AND m.status <> 'failed' AND {r} "
    "GROUP BY m.conversation_id"
)
_INACTIVIDAD = (
    "SELECT m.conversation_id, MAX(m.created_at) AS at FROM messages m "
    "WHERE m.message_type = 'nota_interna' AND m.content LIKE :marca AND {r} "
    "GROUP BY m.conversation_id"
)
_ABANDONO = (
    "SELECT m.conversation_id, MAX(m.created_at) AS at FROM messages m "
    "WHERE m.message_type = 'nota_interna' AND m.sent_by_user_id IS NULL "
    "AND m.content LIKE :marca AND {r} GROUP BY m.conversation_id"
)
_TODO = "TRUE"

#: nombre → (tabla cuyos ids se recorren, params, conteo, update por lote)
BACKFILLS: dict[str, tuple[str, dict, str, str]] = {
    "humano": (
        "conversations", {},
        f"WITH n AS ({_HUMANO.format(r=_TODO)}) SELECT COUNT(*) FROM conversations c "
        "JOIN n ON n.conversation_id = c.id WHERE c.ultimo_mensaje_humano_at IS NULL",
        f"WITH n AS ({_HUMANO.format(r=_RANGO_M)}) UPDATE conversations c "
        "SET ultimo_mensaje_humano_at = n.at FROM n "
        "WHERE n.conversation_id = c.id AND c.ultimo_mensaje_humano_at IS NULL",
    ),
    "inactividad": (
        "conversations", {"marca": MARCA_INACTIVIDAD},
        f"WITH n AS ({_INACTIVIDAD.format(r=_TODO)}) SELECT COUNT(*) FROM conversations c "
        "JOIN n ON n.conversation_id = c.id "
        "WHERE c.status = 'closed' AND c.cerrada_por_inactividad_at IS NULL",
        f"WITH n AS ({_INACTIVIDAD.format(r=_RANGO_M)}) UPDATE conversations c "
        "SET cerrada_por_inactividad_at = n.at FROM n "
        "WHERE n.conversation_id = c.id AND c.status = 'closed' "
        "AND c.cerrada_por_inactividad_at IS NULL",
    ),
    "abandono": (
        "conversations", {"marca": MARCA_ABANDONO},
        f"WITH n AS ({_ABANDONO.format(r=_TODO)}) SELECT COUNT(*) FROM conversations c "
        "JOIN n ON n.conversation_id = c.id "
        "WHERE c.status = 'pending' AND c.etiqueta IS NOT NULL AND c.abandono_at IS NULL",
        f"WITH n AS ({_ABANDONO.format(r=_RANGO_M)}) UPDATE conversations c "
        "SET abandono_at = n.at, abandono_asesor = NULLIF(LEFT(c.assigned_to, 64), 'bot') "
        "FROM n WHERE n.conversation_id = c.id AND c.status = 'pending' "
        "AND c.etiqueta IS NOT NULL AND c.abandono_at IS NULL",
    ),
    "origen": (
        "agendamientos", {},
        "SELECT COUNT(*) FROM agendamientos WHERE origen IS NULL",
        "UPDATE agendamientos SET origen = 'abandono' "
        "WHERE origen IS NULL AND id > :desde AND id <= :hasta",
    ),
}


def _backfills_pedidos() -> set[str]:
    crudo = os.environ.get("BACKFILL", "").strip().lower()
    if crudo in ("", "0", "false", "no"):
        return set()
    if crudo in ("1", "true", "si", "sí", "all", "todos"):
        return set(BACKFILLS)
    pedidos = {p.strip() for p in crudo.split(",") if p.strip()}
    desconocidos = pedidos - set(BACKFILLS)
    if desconocidos:
        raise SystemExit(f"BACKFILL desconocido: {sorted(desconocidos)}; válidos: {sorted(BACKFILLS)}")
    return pedidos


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _normalizar_default(expr) -> str | None:
    """`'x'::character varying` → `'x'`, `NOW()` → `now()`; None queda None."""
    if expr is None:
        return None
    texto = " ".join(str(expr).split()).lower()
    if not texto.startswith("nextval("):
        texto = re.sub(r"::[a-z0-9_ \.\"\[\]]+$", "", texto)
    return texto


def _sin_esquema(indexdef: str) -> str:
    return re.sub(r" ON [^ ]+\.", " ON ", indexdef)


def _constraint_existe(conn, tabla: str, nombre: str) -> bool:
    return bool(
        conn.execute(
            text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conrelid = CAST(:t AS regclass) AND conname = :n"
            ),
            {"t": tabla, "n": nombre},
        ).scalar()
    )


def _lock(conn) -> None:
    conn.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'"))


# ---------------------------------------------------------------------------
# Aplicar
# ---------------------------------------------------------------------------

def _indice_concurrente(engine, cambios: list[str]) -> None:
    """`uq_conversations_id_team`: CONCURRENTLY (no frena escrituras) y luego
    se ata como constraint, que es como lo crea `create_all()`."""
    nombre = "uq_conversations_id_team"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f"SET lock_timeout = '{LOCK_TIMEOUT}'"))
        valido = conn.execute(
            text(
                "SELECT i.indisvalid FROM pg_class c JOIN pg_index i ON i.indexrelid = c.oid "
                "WHERE c.oid = to_regclass(:n)"
            ),
            {"n": nombre},
        ).fetchone()
        if valido is not None and not valido[0]:
            # Un CONCURRENTLY cortado deja el índice INVÁLIDO; IF NOT EXISTS lo
            # daría por bueno para siempre.
            conn.execute(text(f"DROP INDEX CONCURRENTLY IF EXISTS {nombre}"))
            cambios.append(f"índice {nombre} inválido: borrado para rehacerlo")
            valido = None
        if valido is None:
            conn.execute(
                text(f"CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS {nombre} "
                     "ON conversations (id, team_id)")
            )
            cambios.append(f"índice {nombre} creado (CONCURRENTLY)")

    with engine.begin() as conn:
        _lock(conn)
        if not _constraint_existe(conn, "conversations", nombre):
            conn.execute(
                text(f"ALTER TABLE conversations ADD CONSTRAINT {nombre} "
                     f"UNIQUE USING INDEX {nombre}")
            )
            cambios.append(f"constraint {nombre} atado al índice")


def aplicar(engine) -> dict:
    """Crea lo que falte y repara defaults. Devuelve {'cambios', 'reparados'}."""
    cambios: list[str] = []
    reparados: list[str] = []

    # a) Columnas de tablas existentes, una transacción corta por tabla.
    for tabla in ("conversations", "bots", "agendamientos"):
        with engine.begin() as conn:
            _lock(conn)
            antes = {
                r[0] for r in conn.execute(
                    text("SELECT column_name FROM information_schema.columns "
                         "WHERE table_schema = current_schema() AND table_name = :t"),
                    {"t": tabla},
                )
            }
            for col, tipo in COLUMNAS[tabla]:
                if col not in antes:
                    conn.execute(text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col} {tipo}"))
                    cambios.append(f"columna {tabla}.{col}")

    # b) Destino de la FK compuesta (antes de crear la tabla de ventas).
    _indice_concurrente(engine, cambios)

    # c) Tabla de ventas.
    with engine.begin() as conn:
        _lock(conn)
        existia = conn.execute(text("SELECT to_regclass('conversation_sales') IS NOT NULL")).scalar()
        if not existia:
            conn.execute(text(CREAR_VENTAS))
            cambios.append("tabla conversation_sales")
        else:
            for col, tipo in COLUMNAS["conversation_sales"]:
                hay = conn.execute(
                    text("SELECT 1 FROM information_schema.columns WHERE table_schema = "
                         "current_schema() AND table_name = 'conversation_sales' AND column_name = :c"),
                    {"c": col},
                ).scalar()
                if not hay:
                    conn.execute(text(f"ALTER TABLE conversation_sales ADD COLUMN {col} {tipo}"))
                    cambios.append(f"columna conversation_sales.{col}")
            for tabla, nombre in CONSTRAINTS_SOBRANTES:
                if _constraint_existe(conn, tabla, nombre):
                    conn.execute(text(f"ALTER TABLE {tabla} DROP CONSTRAINT {nombre}"))
                    reparados.append(f"{tabla}: quitada FK simple {nombre} (la reemplaza la compuesta)")

    # d) CHECK y FK que falten, NOT VALID (instantáneo).
    for tabla, nombre, cuerpo in CONSTRAINTS:
        with engine.begin() as conn:
            _lock(conn)
            if not _constraint_existe(conn, tabla, nombre):
                conn.execute(text(f"ALTER TABLE {tabla} ADD CONSTRAINT {nombre} {cuerpo} NOT VALID"))
                cambios.append(f"constraint {tabla}.{nombre}")

    # e) Índices de tablas chicas o nuevas.
    for tabla, sentencias in INDICES.items():
        with engine.begin() as conn:
            _lock(conn)
            for sql in sentencias:
                nombre = sql.split(" EXISTS ", 1)[1].split()[0]
                if conn.execute(text("SELECT to_regclass(:n) IS NULL"), {"n": nombre}).scalar():
                    conn.execute(text(sql))
                    cambios.append(f"índice {nombre}")

    # f) Reparación de DEFAULT y NOT NULL (gotcha create_all), solo si difiere.
    with engine.begin() as conn:
        _lock(conn)
        for (tabla, col), (literal, esperado) in DEFAULTS.items():
            real = conn.execute(
                text("SELECT column_default FROM information_schema.columns "
                     "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"),
                {"t": tabla, "c": col},
            ).scalar()
            if _normalizar_default(real) != esperado:
                conn.execute(text(f"ALTER TABLE {tabla} ALTER COLUMN {col} SET DEFAULT {literal}"))
                reparados.append(f"{tabla}.{col} default {real!r} → {esperado!r}")
        for (tabla, col), relleno in NOT_NULL.items():
            nulable = conn.execute(
                text("SELECT is_nullable FROM information_schema.columns "
                     "WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c"),
                {"t": tabla, "c": col},
            ).scalar()
            if nulable == "YES":
                conn.execute(text(f"UPDATE {tabla} SET {col} = {relleno} WHERE {col} IS NULL"))
                conn.execute(text(f"ALTER TABLE {tabla} ALTER COLUMN {col} SET NOT NULL"))
                reparados.append(f"{tabla}.{col} → NOT NULL")

    # g) Validar lo que quedó NOT VALID, cada uno en su transacción.
    for tabla, nombre, _ in CONSTRAINTS:
        with engine.begin() as conn:
            _lock(conn)
            pendiente = conn.execute(
                text("SELECT NOT convalidated FROM pg_constraint "
                     "WHERE conrelid = CAST(:t AS regclass) AND conname = :n"),
                {"t": tabla, "n": nombre},
            ).scalar()
            if pendiente:
                conn.execute(text(f"ALTER TABLE {tabla} VALIDATE CONSTRAINT {nombre}"))
                cambios.append(f"validado {tabla}.{nombre}")

    return {"cambios": cambios, "reparados": reparados}


# ---------------------------------------------------------------------------
# Verificar
# ---------------------------------------------------------------------------

def verificar(engine, *, decir=print) -> list[str]:
    """Compara definiciones contra lo esperado. Devuelve la lista de errores."""
    errores: list[str] = []
    with engine.connect() as conn:
        for tabla, esperadas in ESPERADAS.items():
            vistas = {
                f[0]: f
                for f in conn.execute(
                    text("SELECT column_name, data_type, is_nullable, column_default, "
                         "character_maximum_length FROM information_schema.columns "
                         "WHERE table_schema = current_schema() AND table_name = :t"),
                    {"t": tabla},
                )
            }
            if not vistas:
                errores.append(f"falta la tabla {tabla}")
                continue
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
                if _normalizar_default(f[3]) != default:
                    errores.append(f"{tabla}.{col} default={f[3]!r}, se esperaba {default!r}")
                if largo is not None and f[4] != largo:
                    errores.append(f"{tabla}.{col} largo={f[4]}, se esperaba {largo}")
                if len(errores) == antes:
                    decir(f"  ✓ {tabla}.{col} {tipo} nullable={nulable} default={default}")
            if tabla in TABLAS_EXACTAS:
                sobra = sorted(set(vistas) - set(esperadas))
                if sobra:
                    errores.append(f"{tabla}: columnas que el modelo no tiene: {sobra}")

        for tabla, esperadas in CONSTRAINTS_ESPERADAS.items():
            vistas = {
                r[0]: (r[1], r[2])
                for r in conn.execute(
                    text("SELECT conname, pg_get_constraintdef(oid), convalidated FROM pg_constraint "
                         "WHERE conrelid = to_regclass(:t)"),
                    {"t": tabla},
                )
            }
            for nombre, definicion in esperadas.items():
                real = vistas.get(nombre)
                if real is None:
                    errores.append(f"falta constraint {tabla}.{nombre}")
                elif real[0] != definicion:
                    errores.append(f"constraint {tabla}.{nombre} = {real[0]!r}, se esperaba {definicion!r}")
                elif not real[1]:
                    errores.append(f"constraint {tabla}.{nombre} sin validar (NOT VALID)")
                else:
                    decir(f"  ✓ constraint {tabla}.{nombre} {definicion}")
            if tabla in TABLAS_EXACTAS:
                sobra = sorted(set(vistas) - set(esperadas))
                if sobra:
                    errores.append(f"{tabla}: constraints que el modelo no declara: {sobra}")

        for tabla, esperados in INDICES_ESPERADOS.items():
            vistos = {
                r[0]: (r[1], r[2])
                for r in conn.execute(
                    text("SELECT c.relname, pg_get_indexdef(i.indexrelid), i.indisvalid "
                         "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                         "WHERE i.indrelid = to_regclass(:t)"),
                    {"t": tabla},
                )
            }
            for nombre, definicion in esperados.items():
                real = vistos.get(nombre)
                if real is None:
                    errores.append(f"falta índice {nombre}")
                elif _sin_esquema(real[0]) != definicion:
                    errores.append(f"índice {nombre} = {_sin_esquema(real[0])!r}, se esperaba {definicion!r}")
                elif not real[1]:
                    errores.append(f"índice {nombre} INVÁLIDO (CONCURRENTLY cortado)")
                else:
                    decir(f"  ✓ índice {nombre}")
            if tabla in TABLAS_EXACTAS:
                sobra = sorted(set(vistos) - set(esperados))
                if sobra:
                    errores.append(f"{tabla}: índices que el modelo no declara: {sobra}")
    return errores


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

def backfill(engine, pedidos: set[str], *, decir=print) -> dict[str, int]:
    """Cuenta todo; escribe solo los `pedidos`, por lotes de ids. → {nombre: filas}"""
    tocadas_por: dict[str, int] = {}
    for nombre, (tabla, params, conteo, update) in BACKFILLS.items():
        with engine.connect() as conn:
            pendientes = conn.execute(text(conteo), params).scalar() or 0
            tope = conn.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {tabla}")).scalar()
        if nombre not in pedidos or not pendientes:
            decir(f"  {nombre}: {pendientes} por rellenar")
            tocadas_por[nombre] = 0
            continue
        tocadas, desde = 0, 0
        while desde < tope:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                conn.execute(text("SET LOCAL statement_timeout = '60s'"))
                tocadas += conn.execute(
                    text(update), {**params, "desde": desde, "hasta": desde + LOTE}
                ).rowcount
            desde += LOTE
        tocadas_por[nombre] = tocadas
        decir(f"  {nombre}: {pendientes} por rellenar → {tocadas} rellenadas (lotes de {LOTE})")
    return tocadas_por


def main(engine=None) -> int:
    pedidos = _backfills_pedidos()
    if engine is None:
        print(f"Conectando a host: {_host(DATABASE_URL) or '(desconocido)'}")
        engine = create_engine(DATABASE_URL, hide_parameters=True)

    print("Esquema:")
    resultado = aplicar(engine)
    for c in resultado["cambios"]:
        print(f"  + {c}")
    for r in resultado["reparados"]:
        print(f"  reparado: {r}")
    print(f"  {len(resultado['cambios'])} cambios, {len(resultado['reparados'])} reparados")

    print("Verificación:")
    errores = verificar(engine)
    if errores:
        for e in errores:
            print(f"ERROR: {e}")
        return 1
    with engine.connect() as conn:
        ventas = conn.execute(text("SELECT COUNT(*) FROM conversation_sales")).scalar()
    print(f"  filas en conversation_sales={ventas}")
    print("OK: esquema aplicado y verificado.")

    print(f"Backfill ({'ESCRIBE ' + ','.join(sorted(pedidos)) if pedidos else 'solo conteo; BACKFILL=1 para escribir'}):")
    backfill(engine, pedidos)
    return 0


if __name__ == "__main__":
    sys.exit(main())
