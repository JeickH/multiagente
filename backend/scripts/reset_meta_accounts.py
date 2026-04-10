"""Resetea la tabla meta_accounts cuando el schema cambia incompatiblemente.

Uso:
    python backend/scripts/reset_meta_accounts.py

Guardarraíles:
- Rehúsa ejecutarse si DATABASE_URL apunta a un host distinto de localhost/127.0.0.1/db
  salvo que se pase --force-production explícito.
- Pide que el usuario escriba literalmente el nombre de la base de datos para confirmar.
- Imprime un SELECT * previo (con el ciphertext) a stdout para auditoría — inútil sin
  la clave, pero deja evidencia.

IMPORTANTE: ejecutar este script borra TODAS las cuentas de Meta registradas. Solo es
seguro en desarrollo local o cuando aún no hay registros reales en producción.
"""

import argparse
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

# Añadir el backend al sys.path para poder importar app.database
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# database.py expone SQLALCHEMY_DATABASE_URL construida a partir de las env vars
# POSTGRES_*. Lo aliasamos a DATABASE_URL para uso local en este script.
from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


LOCAL_HOSTS = {"localhost", "127.0.0.1", "db", "postgres", ""}


def _parse_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _parse_dbname(url: str) -> str:
    try:
        path = urlparse(url).path or ""
        return path.lstrip("/")
    except Exception:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset meta_accounts table")
    parser.add_argument(
        "--force-production",
        action="store_true",
        help="Permite ejecutar contra un host no-local (PELIGROSO).",
    )
    args = parser.parse_args()

    host = _parse_host(DATABASE_URL)
    dbname = _parse_dbname(DATABASE_URL)

    print()
    print(f"DATABASE_URL host:    {host or '(desconocido)'}")
    print(f"DATABASE_URL dbname:  {dbname or '(desconocido)'}")
    print()

    if host not in LOCAL_HOSTS and not args.force_production:
        print(
            f"ABORTADO: el host '{host}' no parece local. "
            "Pasa --force-production solo si sabes lo que haces."
        )
        return 2

    if host not in LOCAL_HOSTS:
        print("AVISO: Estas ejecutando contra un host NO-local. ESTO ES DESTRUCTIVO EN PRODUCCION.")
        print()

    print("Este script va a ejecutar:")
    print("    DROP TABLE IF EXISTS meta_accounts CASCADE;")
    print()
    print(f"Para confirmar, escribe el nombre de la base de datos ({dbname!r}):")
    confirmation = input("> ").strip()

    if confirmation != dbname or not dbname:
        print("Confirmacion no coincide. Abortado.")
        return 3

    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Auditoría: snapshot del contenido antes de borrar
        try:
            rows = conn.execute(text("SELECT * FROM meta_accounts")).fetchall()
            print()
            print(f"=== Snapshot de auditoria: {len(rows)} filas ===")
            for r in rows:
                print(dict(r._mapping))
            print("=== Fin snapshot ===")
            print()
        except Exception as exc:
            print(f"(No se pudo leer el snapshot: {type(exc).__name__})")

        conn.execute(text("DROP TABLE IF EXISTS meta_accounts CASCADE"))
        conn.commit()

    print("OK: meta_accounts eliminada. Reinicia el backend para que SQLAlchemy la recree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
