"""Migración idempotente: índice `(conversation_id, created_at)` en `messages`.

Por qué: casi todo lo que se le pregunta a `messages` es "los mensajes de esta
conversación, por fecha" — la transcripción de un chat, el adelanto de la
bandeja, el conteo de la ventana de supervisión. La columna `conversation_id`
no tenía índice (el de `created_at` suelto no sirve para eso), así que cada una
de esas consultas barría la tabla completa. Con la bandeja refrescándose sola
cada 8 segundos, eso se paga muchas veces por minuto.

`create_all()` no crea índices sobre tablas que ya existen, así que hay que
aplicarlo a mano en local Y en RDS (regla de paridad de schema del CEO).

Diseño:
  - `CREATE INDEX CONCURRENTLY IF NOT EXISTS`: idempotente y sin bloquear las
    escrituras de la tabla. Construir un índice sin CONCURRENTLY toma un lock
    que deja a los webhooks de WhatsApp esperando, y esos no se pueden hacer
    esperar: del otro lado hay un cliente escribiendo.
  - CONCURRENTLY no puede correr dentro de una transacción, de ahí el
    AUTOCOMMIT.
  - No destructivo: no borra ni reescribe datos.

Ojo: si un intento previo falló a mitad de camino, Postgres deja el índice como
INVALID y el `IF NOT EXISTS` lo da por hecho sin que sirva para nada. El script
lo detecta y avisa qué hacer (`DROP INDEX` y volver a correr).

Uso:
    # Local (docker compose)
    docker compose exec backend python scripts/migrate_indice_mensajes.py

    # RDS (vía ECS run-task override, región sa-east-1)
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore

INDICE = "ix_messages_conversation_created"
TABLA = "messages"
COLUMNAS = "(conversation_id, created_at)"


def _parse_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _estado(conn) -> tuple[bool, bool]:
    """(existe, es_valido) del índice."""
    fila = conn.execute(
        text(
            "SELECT i.indisvalid FROM pg_class c "
            "JOIN pg_index i ON i.indexrelid = c.oid "
            "WHERE c.relname = :nombre"
        ),
        {"nombre": INDICE},
    ).fetchone()
    if fila is None:
        return False, False
    return True, bool(fila[0])


def main() -> int:
    host = _parse_host(DATABASE_URL)
    print(f"Conectando a host: {host or '(desconocido)'}")

    engine = create_engine(DATABASE_URL)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        existe, valido = _estado(conn)
        if existe and not valido:
            print(f"ERROR: el índice {INDICE} existe pero quedó INVALID.")
            print("       Un intento anterior se cortó a mitad. Para rehacerlo:")
            print(f"         DROP INDEX CONCURRENTLY {INDICE};")
            print("       y volver a correr este script.")
            return 1
        if existe:
            print(f"  -> {INDICE} ya existe y es válido, no hay nada que hacer.")
        else:
            sql = (
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDICE} "
                f"ON {TABLA} {COLUMNAS};"
            )
            print(f"  -> {sql}")
            conn.execute(text(sql))

        existe, valido = _estado(conn)
        filas = conn.execute(text(f"SELECT count(*) FROM {TABLA}")).scalar()

    print()
    if not (existe and valido):
        print(f"ERROR: el índice {INDICE} no quedó creado.")
        return 1
    print(f"OK: {INDICE} presente y válido sobre {TABLA} {COLUMNAS}.")
    print(f"    ({filas} filas en la tabla)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
