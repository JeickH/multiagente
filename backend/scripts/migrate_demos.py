"""Migración Sprint 32 #610 — tabla `demos` (demo interactiva de glomacx.com/demo).

Una fila por demo que arma un prospecto. El prospecto en sí (nombre, correo,
teléfono, empresa, autorización de datos) va a `leads` con
`source='gloma_demo'`; aquí va lo propio de la demo: bot, tipo de empresa,
consentimientos, estado de la generación, mensaje sugerido, el estado del chat
para el motor y la transcripción legible para ventas.

CREA Y ADEMÁS REPARA (gotcha del 2026-09-16, ver `migrate_sprint31_productos`)
    El backend corre `create_all()` al arrancar. Si la imagen nueva bota antes
    que esta migración, la tabla nace del modelo y el `CREATE TABLE IF NOT
    EXISTS` es un no-op ciego. Por eso, después de crear, el script:
      · agrega las columnas que falten (`ADD COLUMN IF NOT EXISTS`, con su
        DEFAULT si lo tiene) y les pone NOT NULL si no hay NULLs; si los hay,
        no inventa valores (un `consent_version` inventado no prueba nada): lo
        reporta y sale con 1;
      · repone el `DEFAULT` de cada columna cuando el real difiere;
      · agrega los CHECK y las FK que falten (Postgres no tiene
        `ADD CONSTRAINT IF NOT EXISTS`: se pregunta a `pg_constraint`);
      · verifica DEFINICIÓN, no solo nombres: tipos, NOT NULL, defaults,
        CHECK, FK con su ON DELETE e índices (el de `public_id` UNIQUE).
    `models.py` declara `server_default` en las mismas columnas, así que los
    dos caminos convergen. Los nombres de FK e índices son los que pone
    `create_all()` (`demos_lead_id_fkey`, `ix_demos_<col>`).

DECISIONES
    · `public_id` UUID nativo, `DEFAULT gen_random_uuid()` (nativo desde PG 13;
      local y RDS en 15.17). Es lo que viaja al navegador; el `id` serial no
      sale porque es enumerable. Índice ÚNICO, que es lo que crea el modelo.
    · Sin índice sobre `id`: la PK ya lo es.
    · `tipo_empresa` SIN CHECK de lista: crecerá y cada cambio sería una
      migración; la valida el backend.
    · `consent_version` NOT NULL y sin default: lo escribe el endpoint.
    · CHECK que no dependen de la lista: estado, origen_productos,
      `turnos >= 0`, `tipo_otro` solo con tipo 'otro', y promociones
      aceptadas ⇒ `acepta_promociones_at`.
    · Índices: (ip_address, created_at) para el tope por IP/día, created_at
      para el techo global y para los topes por correo/teléfono (que salen de
      las demos de las últimas 24 h unidas a `leads` por PK, así que `leads`
      no necesita índice nuevo); lead_id y bot_id para los JOIN y para que el
      ON DELETE SET NULL no recorra la tabla.
    · #626 (Sprint 32, 17-oct): `clics_whatsapp` y `aperturas_llamada`
      (INTEGER NOT NULL DEFAULT 0, CHECK >= 0; el techo de 100 lo pone el
      backend) y cuatro fechas NULL: `primer_clic_whatsapp_at`,
      `primer_apertura_llamada_at`, `llamada_agendada_at`, `traspaso_at`.
      Agregarlas con DEFAULT constante no reescribe la tabla (PG 11+) y un
      backend con el `models.py` anterior sigue funcionando: no las nombra.
      SIN índice nuevo: el panel lista por `created_at DESC` con filtro de
      fechas, que ya cubre `ix_demos_created_at`, y el resumen
      (COUNT/SUM con FILTER sobre esas columnas) recorre solo las filas de ese
      rango, que el tope global por día mantiene en cientos. Un índice por
      contador además se tocaría en cada clic sin que ninguna consulta lo use.
    · #637 (Sprint 33, 21-oct): limpieza de los bots de demo inactivos.
      Cuatro columnas NULL y sin default: `ultima_actividad_at`,
      `productos_snapshot` (JSONB), `uso_resumen` (JSONB) y
      `bot_eliminado_at`. `ultima_actividad_at` va SIN default a propósito:
      `DEFAULT now()` en un ADD COLUMN se evalúa una vez y le pone la hora de
      la migración a todas las filas viejas (y entonces el relleno, que solo
      toca NULLs, no haría nada). Las filas existentes se rellenan con la
      mejor estimación (ver `RELLENO_ACTIVIDAD`), solo donde está en NULL: la
      segunda corrida no toca nada, y correrla de nuevo DESPUÉS del deploy
      rellena las demos que el backend viejo haya creado entre la migración y
      el despliegue (esas no se limpian mientras sigan en NULL: `NULL < x` no
      es verdadero, así que el limpiador falla hacia conservar).
      Índice PARCIAL `ix_demos_bot_vivo_actividad (ultima_actividad_at)
      WHERE bot_id IS NOT NULL` para la consulta del limpiador: al borrar el
      bot la FK deja `bot_id` en NULL y la fila sale del índice, así que pesa
      lo que pesan los bots vivos (decenas) y no las demos históricas, que
      crecen sin techo. Mismo nombre y predicado en `models.py`.
      Sin CHECK sobre la forma del JSON (`jsonb_typeof`): la suite corre en
      SQLite, que no tiene esa función, y el CHECK de `models.py` la rompería.

No borra ni reescribe datos. Correrla dos veces no cambia nada la segunda.

Uso:
    # Local (el compose se llama `wati`; el contenedor no monta `scripts/`,
    # por eso va por stdin)
    docker compose -p wati exec -T backend python - < backend/scripts/migrate_demos.py
    docker compose -p wati exec -T backend python - --verificar < backend/scripts/migrate_demos.py

    # Producción (RDS): pesa más de 8 KB y `rds_exec.sh` no lo acepta (límite
    # de overrides de ECS). Va como run-task sobre la task-def NUEVA, cuya
    # imagen ya trae `scripts/migrate_demos.py` (deploy #617).

OJO: migrar no basta; si la imagen de ECS lleva un `models.py` sin `Demo`, el
ORM ni ve la tabla. Esta migración va con su despliegue.
"""
from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

# `python scripts/x.py`, copiado a otra ruta, o por stdin (`python -`), donde
# `__file__` no existe. Se busca el archivo, no la carpeta (desde `/`, `/app`
# parece un namespace package y el import se va por ahí).
_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore

# ── Una sola fuente de verdad: el CREATE, el ADD COLUMN, la reparación y el
# verificador leen de aquí. Si cada parte escribiera los valores por su cuenta
# podrían divergir, que es el desastre que este script existe para no repetir.
#
# columna → (tipo SQL, tipo como lo devuelve information_schema, NOT NULL,
#            DEFAULT o None)
_TS = ("TIMESTAMP", "timestamp without time zone")
COLUMNAS: dict[str, tuple[str, str, bool, str | None]] = {
    "public_id": ("UUID", "uuid", True, "gen_random_uuid()"),
    "lead_id": ("INTEGER", "integer", False, None),
    "bot_id": ("INTEGER", "integer", False, None),
    "empresa": ("VARCHAR(120)", "character varying(120)", True, None),
    "tipo_empresa": ("VARCHAR(32)", "character varying(32)", True, None),
    "tipo_otro": ("VARCHAR(80)", "character varying(80)", False, None),
    "acepta_contacto_at": (*_TS, True, None),
    "consent_version": ("VARCHAR(32)", "character varying(32)", True, None),
    "acepta_promociones": ("BOOLEAN", "boolean", True, "false"),
    "acepta_promociones_at": (*_TS, False, None),
    "estado": ("VARCHAR(16)", "character varying(16)", True, "'generando'"),
    "origen_productos": ("VARCHAR(16)", "character varying(16)", False, None),
    "mensaje_sugerido": ("VARCHAR(500)", "character varying(500)", False, None),
    "turnos": ("INTEGER", "integer", True, "0"),
    "chat_state": ("JSONB", "jsonb", False, None),
    "transcripcion": ("JSONB", "jsonb", True, "'[]'::jsonb"),
    "ip_address": ("VARCHAR(64)", "character varying(64)", False, None),
    "user_agent": ("VARCHAR(512)", "character varying(512)", False, None),
    "created_at": (*_TS, True, "now()"),
    "updated_at": (*_TS, True, "now()"),
    "lista_at": (*_TS, False, None),
    # #626: seguimiento comercial (panel del admin).
    "clics_whatsapp": ("INTEGER", "integer", True, "0"),
    "aperturas_llamada": ("INTEGER", "integer", True, "0"),
    "primer_clic_whatsapp_at": (*_TS, False, None),
    "primer_apertura_llamada_at": (*_TS, False, None),
    "llamada_agendada_at": (*_TS, False, None),
    "traspaso_at": (*_TS, False, None),
    # #637: limpieza de los bots de demo inactivos.
    "ultima_actividad_at": (*_TS, False, None),
    "productos_snapshot": ("JSONB", "jsonb", False, None),
    "uso_resumen": ("JSONB", "jsonb", False, None),
    "bot_eliminado_at": (*_TS, False, None),
}

CHECKS: dict[str, str] = {
    "ck_demos_estado": "estado IN ('generando','lista','error')",
    "ck_demos_origen_productos":
        "origen_productos IS NULL OR origen_productos IN ('modelo','respaldo')",
    "ck_demos_turnos": "turnos >= 0",
    "ck_demos_tipo_otro": "tipo_otro IS NULL OR tipo_empresa = 'otro'",
    "ck_demos_promociones_at":
        "NOT acepta_promociones OR acepta_promociones_at IS NOT NULL",
    "ck_demos_clics_whatsapp": "clics_whatsapp >= 0",
    "ck_demos_aperturas_llamada": "aperturas_llamada >= 0",
}

# nombre → (columna, tabla referida). ON DELETE SET NULL: borrar el lead o el
# bot (retención, #618) no se lleva el registro de la demo ni su consentimiento.
FKS: dict[str, tuple[str, str]] = {
    "demos_lead_id_fkey": ("lead_id", "leads"),
    "demos_bot_id_fkey": ("bot_id", "bots"),
}

# nombre → (columnas, único, predicado WHERE si es parcial)
INDICES: dict[str, tuple[str, bool, str | None]] = {
    "ix_demos_public_id": ("public_id", True, None),
    "ix_demos_lead_id": ("lead_id", False, None),
    "ix_demos_bot_id": ("bot_id", False, None),
    "ix_demos_created_at": ("created_at", False, None),
    "ix_demos_ip_created": ("ip_address, created_at", False, None),
    # #637: el limpiador. Parcial: solo las demos que aún tienen bot.
    "ix_demos_bot_vivo_actividad": ("ultima_actividad_at", False, "bot_id IS NOT NULL"),
}

# #637: mejor estimación de la última actividad de una demo existente. Es el
# máximo de todo lo que el prospecto pudo haber hecho:
#   · created_at (siempre está) y lista_at (el bot quedó listo);
#   · el `at` más reciente de `transcripcion` (cada turno escribe dos entradas
#     con la hora UTC en ISO). Solo se toman los que parecen fecha, para que
#     una entrada rara no tumbe la migración con un error de cast;
#   · las fechas de los eventos (#626). Son la PRIMERA vez de cada uno (se
#     escriben con COALESCE), así que un clic posterior no queda; por eso
#     también entra
#   · updated_at, que hoy es confiable: solo lo mueven la creación, el «lista»
#     o «error» de la generación y cada turno (ORM con `onupdate`); ningún
#     panel ni script reescribe demos. Los eventos no lo tocan (SQL directo),
#     y eso es lo que lo deja abajo de la verdad, nunca arriba. OJO: desde
#     #637 la limpieza sí escribe la fila (snapshot, resumen), así que este
#     relleno vale UNA vez; por eso solo toca NULLs.
# GREATEST ignora NULLs. El techo `now()` en UTC (las fechas de esta tabla son
# UTC sin zona) evita que una hora corrida al futuro deje un bot vivo para
# siempre. El resultado nunca es NULL porque `created_at` es NOT NULL.
RELLENO_ACTIVIDAD = """
UPDATE demos d SET ultima_actividad_at = LEAST(
    GREATEST(
        d.created_at, d.lista_at, d.updated_at,
        d.primer_clic_whatsapp_at, d.primer_apertura_llamada_at,
        d.llamada_agendada_at, d.traspaso_at,
        (SELECT MAX((e->>'at')::timestamp)
           FROM jsonb_array_elements(
                CASE WHEN jsonb_typeof(d.transcripcion) = 'array'
                     THEN d.transcripcion ELSE '[]'::jsonb END) AS e
          WHERE jsonb_typeof(e) = 'object'
            AND e->>'at' ~ '^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])[T ]([01][0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9](\\.[0-9]+)?)?$')
    ),
    (now() AT TIME ZONE 'UTC')
)
WHERE d.ultima_actividad_at IS NULL
"""


def _normalizar_pred(expr: str | None) -> str:
    """`(bot_id IS NOT NULL)` → `bot_id is not null`."""
    if not expr:
        return ""
    return " ".join(expr.replace("(", " ").replace(")", " ").split()).lower()


def _def_columna(nombre: str) -> str:
    tipo, _, no_nulo, default = COLUMNAS[nombre]
    return (
        f"{nombre} {tipo}"
        + (" NOT NULL" if no_nulo else "")
        + (f" DEFAULT {default}" if default else "")
    )


DDL = (
    "CREATE TABLE IF NOT EXISTS demos (\n    id SERIAL PRIMARY KEY,\n    "
    + ",\n    ".join(_def_columna(c) for c in COLUMNAS)
    + "\n)"
)
# Los CHECK y las FK no van dentro del CREATE: los pone `reparar()`, que corre
# igual sobre una tabla recién creada que sobre una de `create_all()`.


def _normalizar(expr: str | None) -> str:
    """`'generando'::character varying` → `'generando'`; minúsculas."""
    if not expr:
        return ""
    texto = " ".join(expr.split()).lower()
    return re.sub(r"::[a-z0-9_ \.\"\[\]]+$", "", texto).strip()


def _columnas(conn) -> dict[str, tuple[str, bool, str | None]]:
    filas = conn.execute(text(
        "SELECT column_name, data_type, character_maximum_length, is_nullable, "
        "column_default FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='demos'"
    ))
    return {
        n: (f"{t}({l})" if l else t, nulo == "NO", d) for n, t, l, nulo, d in filas
    }


def _constraints(conn) -> dict[str, tuple[str, str | None, str | None]]:
    """`{nombre: (contype, confdeltype, tabla referida)}`."""
    filas = conn.execute(text(
        "SELECT con.conname, con.contype, con.confdeltype, ref.relname "
        "FROM pg_constraint con LEFT JOIN pg_class ref ON ref.oid = con.confrelid "
        "WHERE con.conrelid = to_regclass('public.demos')"
    ))
    return {n: (t, d, r) for n, t, d, r in filas}


def reparar(conn) -> list[str]:
    """Pone lo que `create_all()` o una corrida a medias pudo dejar sin poner.

    Identificadores y expresiones salen de las constantes de este archivo.
    """
    hechos: list[str] = []
    cols = _columnas(conn)
    for columna, (tipo, _, no_nulo, default) in COLUMNAS.items():
        if columna not in cols:
            # Con DEFAULT, las filas existentes lo toman; sin él quedan en NULL
            # y el NOT NULL se decide abajo.
            conn.execute(text(
                f"ALTER TABLE demos ADD COLUMN IF NOT EXISTS {columna} {tipo}"
                + (f" DEFAULT {default}" if default else "")
            ))
            hechos.append(f"columna {columna}")
        elif default and _normalizar(cols[columna][2]) != _normalizar(default):
            conn.execute(text(f"ALTER TABLE demos ALTER COLUMN {columna} SET DEFAULT {default}"))
            hechos.append(f"default {columna} → {default}")

    cols = _columnas(conn)
    for columna, (_, _, no_nulo, _) in COLUMNAS.items():
        if no_nulo and not cols[columna][1]:
            nulos = conn.execute(text(f"SELECT COUNT(*) FROM demos WHERE {columna} IS NULL")).scalar()
            if nulos:
                print(f"  ! {columna}: {nulos} fila(s) en NULL; no se inventa el valor")
                continue
            conn.execute(text(f"ALTER TABLE demos ALTER COLUMN {columna} SET NOT NULL"))
            hechos.append(f"NOT NULL {columna}")

    presentes = _constraints(conn)
    for nombre, expr in CHECKS.items():
        if nombre not in presentes:
            conn.execute(text(f"ALTER TABLE demos ADD CONSTRAINT {nombre} CHECK ({expr})"))
            hechos.append(f"CHECK {nombre}")
    for nombre, (columna, ref) in FKS.items():
        # Una FK sobre la columna con otro nombre también cuenta: no se duplica.
        ya = conn.execute(text(
            "SELECT 1 FROM pg_constraint con JOIN pg_attribute a "
            "ON a.attrelid = con.conrelid AND a.attnum = ANY(con.conkey) "
            "WHERE con.conrelid = to_regclass('public.demos') AND con.contype='f' "
            "AND a.attname = :c"
        ), {"c": columna}).scalar()
        if not ya:
            conn.execute(text(
                f"ALTER TABLE demos ADD CONSTRAINT {nombre} FOREIGN KEY ({columna}) "
                f"REFERENCES {ref}(id) ON DELETE SET NULL"
            ))
            hechos.append(f"FK {nombre}")
    return hechos


def aplicar(engine) -> None:
    with engine.begin() as conn:
        # Las FK piden un lock sobre `leads` y `bots`, que el tick y los
        # webhooks usan todo el tiempo: si una transacción larga lo tiene, se
        # falla a los 10 s (basta reintentar) en vez de encolar a todos detrás.
        conn.execute(text("SET LOCAL lock_timeout = '10s'"))
        conn.execute(text(DDL))
        print("  ✓ tabla demos")
        hechos = reparar(conn)
        for h in hechos:
            print(f"  + {h}")
        print(f"  ✓ columnas/defaults/CHECK/FK en su sitio ({len(hechos)} agregados o reparados)")
        rellenas = conn.execute(text(RELLENO_ACTIVIDAD)).rowcount
        print(f"  ✓ ultima_actividad_at rellenada en {rellenas} fila(s)")
        for nombre, (cols, unico, donde) in INDICES.items():
            conn.execute(text(
                f"CREATE {'UNIQUE ' if unico else ''}INDEX IF NOT EXISTS "
                f"{nombre} ON demos ({cols})" + (f" WHERE {donde}" if donde else "")
            ))
        print(f"  ✓ {len(INDICES)} índices")


def verificar(engine) -> int:
    mal: list[str] = []
    with engine.connect() as conn:
        if conn.execute(text("SELECT to_regclass('public.demos')")).scalar() is None:
            print("ERROR: no existe la tabla demos")
            return 1
        cols = _columnas(conn)
        esperadas = {"id": (None, "integer", True, None), **COLUMNAS}
        for columna, (_, tipo, no_nulo, default) in esperadas.items():
            if columna not in cols:
                mal.append(f"falta la columna {columna}")
                continue
            real_tipo, real_no_nulo, real_def = cols[columna]
            if real_tipo != tipo:
                mal.append(f"{columna}: tipo {real_tipo}, se esperaba {tipo}")
            if real_no_nulo != no_nulo:
                mal.append(f"{columna}: NOT NULL={real_no_nulo}, se esperaba {no_nulo}")
            if default and _normalizar(real_def) != _normalizar(default):
                mal.append(f"{columna}: default {real_def or 'NINGUNO'}, se esperaba {default}")
            if columna != "id" and not default and real_def:
                mal.append(f"{columna}: tiene default {real_def} y no debería")
        sobran = sorted(set(cols) - set(esperadas))
        if sobran:
            mal.append(f"columnas que este script no conoce: {', '.join(sobran)}")

        presentes = _constraints(conn)
        for nombre in CHECKS:
            if presentes.get(nombre, ("",))[0] != "c":
                mal.append(f"falta el CHECK {nombre}")
        for nombre, (columna, ref) in FKS.items():
            fk = presentes.get(nombre)
            if not fk or fk[0] != "f":
                mal.append(f"falta la FK {nombre}")
            elif fk[1] != "n" or fk[2] != ref:
                mal.append(f"{nombre}: ON DELETE={fk[1]!r} → {fk[2]}, se esperaba SET NULL → {ref}")

        idx = {
            n: (u, p) for n, u, p in conn.execute(text(
                "SELECT c.relname, i.indisunique, pg_get_expr(i.indpred, i.indrelid) "
                "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE i.indrelid = to_regclass('public.demos')"
            ))
        }
        for nombre, (_, unico, donde) in INDICES.items():
            if nombre not in idx:
                mal.append(f"falta el índice {nombre}")
                continue
            if idx[nombre][0] != unico:
                mal.append(f"{nombre}: único={idx[nombre][0]}, se esperaba {unico}")
            if _normalizar_pred(idx[nombre][1]) != _normalizar_pred(donde):
                mal.append(
                    f"{nombre}: WHERE {idx[nombre][1] or '(ninguno)'}, "
                    f"se esperaba {donde or '(ninguno)'}"
                )
        filas = conn.execute(text("SELECT COUNT(*) FROM demos")).scalar()
        sin_actividad = conn.execute(text(
            "SELECT COUNT(*) FROM demos WHERE ultima_actividad_at IS NULL"
        )).scalar() if "ultima_actividad_at" in cols else 0

    if mal:
        print("ERROR: la tabla demos no quedó como dice este script:")
        for m in mal:
            print(f"   - {m}")
        return 1
    if sin_actividad:
        # No es error: pasa entre la migración y el deploy, mientras el backend
        # viejo crea demos sin escribirla. Esas no se limpian; correr la
        # migración otra vez después del deploy las rellena.
        print(
            f"AVISO: {sin_actividad} demo(s) con ultima_actividad_at en NULL; "
            "vuelve a correr la migración (sin --verificar) después del deploy."
        )
    n_def = sum(1 for c in COLUMNAS.values() if c[3])
    print(
        f"OK: demos verificada ({len(esperadas)} columnas, {n_def} defaults, "
        f"{len(CHECKS)} CHECK, {len(FKS)} FK, {len(INDICES)} índices; {filas} fila(s))."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    print(f"Conectando a host: {(urlparse(DATABASE_URL).hostname or '?').lower()}")
    engine = create_engine(DATABASE_URL)
    if "--verificar" in argv:
        print("Modo --verificar: no se toca la base.")
    else:
        aplicar(engine)
    return verificar(engine)


if __name__ == "__main__":
    sys.exit(main())
