"""Migración Sprint "Ayuda a Cali": tablas `mascotas` y `mascota_fotos`.

Un reporte por fila. `tipo_registro` distingue las dos naturalezas que el bot
cruza entre sí:
  'perdida'    → alguien busca a su mascota.
  'encontrada' → alguien halló una mascota y quiere devolverla.

Casi todo el detalle descriptivo es NULL-able (quien reporta rara vez sabe raza,
edad y nombre a la vez). Obligatorios: `ubicacion` y `contacto_telefono`.
`maps_url` es opcional a propósito — mucha gente da la dirección pero no sabe
compartir una ubicación de Google Maps.

Idempotente (`CREATE TABLE/INDEX IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
Se corre en local y en RDS en el mismo PR (convención #1 de paridad).

Uso:
    docker compose -p wati exec -T backend python scripts/migrate_ayuda_cali_mascotas.py
    # RDS: aws ecs run-task con command override (ver BITACORA)

Consulta de monitoreo:
    SELECT codigo, tipo_registro, especie, raza, color, nombre, ubicacion, estado, created_at
    FROM mascotas ORDER BY created_at DESC;
"""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SQLALCHEMY_DATABASE_URL as DATABASE_URL  # type: ignore


DDL_MASCOTAS = """
CREATE TABLE IF NOT EXISTS mascotas (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(16) NOT NULL UNIQUE,
    tipo_registro VARCHAR(16) NOT NULL,
    especie VARCHAR(24) NOT NULL,
    especie_otra VARCHAR(60),
    raza VARCHAR(80),
    color VARCHAR(80),
    nombre VARCHAR(80),
    sexo VARCHAR(16),
    edad VARCHAR(40),
    tamano VARCHAR(24),
    senas TEXT,
    ubicacion VARCHAR(255) NOT NULL,
    maps_url VARCHAR(500),
    barrio VARCHAR(120),
    contacto_nombre VARCHAR(120),
    contacto_telefono VARCHAR(32) NOT NULL,
    fecha_evento DATE,
    estado VARCHAR(24) NOT NULL DEFAULT 'activo',
    notas TEXT,
    bot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
    source VARCHAR(24) NOT NULL DEFAULT 'web',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_mascotas_tipo CHECK (tipo_registro IN ('perdida','encontrada')),
    CONSTRAINT ck_mascotas_estado CHECK (estado IN ('activo','reunida','cerrado'))
);
"""

DDL_FOTOS = """
CREATE TABLE IF NOT EXISTS mascota_fotos (
    id SERIAL PRIMARY KEY,
    mascota_id INTEGER REFERENCES mascotas(id) ON DELETE CASCADE,
    upload_session VARCHAR(64),
    storage_key VARCHAR(400) NOT NULL,
    content_type VARCHAR(60) NOT NULL DEFAULT 'image/jpeg',
    bytes_size INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
"""

DDL_COINCIDENCIAS = """
CREATE TABLE IF NOT EXISTS mascota_coincidencias (
    id SERIAL PRIMARY KEY,
    perdida_id INTEGER NOT NULL REFERENCES mascotas(id) ON DELETE CASCADE,
    encontrada_id INTEGER NOT NULL REFERENCES mascotas(id) ON DELETE CASCADE,
    score INTEGER NOT NULL DEFAULT 0,
    detalle JSONB,
    estado VARCHAR(16) NOT NULL DEFAULT 'nueva',
    notas TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_mascota_par UNIQUE (perdida_id, encontrada_id),
    CONSTRAINT ck_match_estado CHECK (estado IN ('nueva','revisada','confirmada','descartada'))
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS ix_mascotas_codigo ON mascotas (codigo);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_tipo_registro ON mascotas (tipo_registro);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_especie ON mascotas (especie);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_estado ON mascotas (estado);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_barrio ON mascotas (barrio);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_bot_id ON mascotas (bot_id);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_source ON mascotas (source);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_created_at ON mascotas (created_at);",
    "CREATE INDEX IF NOT EXISTS ix_mascotas_tipo_estado ON mascotas (tipo_registro, estado);",
    "CREATE INDEX IF NOT EXISTS ix_mascota_fotos_mascota_id ON mascota_fotos (mascota_id);",
    "CREATE INDEX IF NOT EXISTS ix_mascota_fotos_upload_session ON mascota_fotos (upload_session);",
    "CREATE INDEX IF NOT EXISTS ix_match_perdida ON mascota_coincidencias (perdida_id);",
    "CREATE INDEX IF NOT EXISTS ix_match_encontrada ON mascota_coincidencias (encontrada_id);",
    "CREATE INDEX IF NOT EXISTS ix_match_score ON mascota_coincidencias (score);",
    "CREATE INDEX IF NOT EXISTS ix_match_estado ON mascota_coincidencias (estado);",
    "CREATE INDEX IF NOT EXISTS ix_match_created_at ON mascota_coincidencias (created_at);",
    "CREATE INDEX IF NOT EXISTS ix_match_estado_score ON mascota_coincidencias (estado, score);",
]

# Columnas que podrían faltar si la tabla se creó con una versión anterior del
# script (el patrón del proyecto: sin Alembic, todo ALTER es IF NOT EXISTS).
ADD_COLUMNS = [
    "ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS maps_url VARCHAR(500);",
    "ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS barrio VARCHAR(120);",
    "ALTER TABLE mascotas ADD COLUMN IF NOT EXISTS notas TEXT;",
    "ALTER TABLE mascota_fotos ADD COLUMN IF NOT EXISTS upload_session VARCHAR(64);",
]


def main() -> int:
    host = (urlparse(DATABASE_URL).hostname or "").lower()
    print(f"Conectando a host: {host or '(desconocido)'}")
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        print("  -> CREATE TABLE IF NOT EXISTS mascotas")
        conn.execute(text(DDL_MASCOTAS))
        print("  -> CREATE TABLE IF NOT EXISTS mascota_fotos")
        conn.execute(text(DDL_FOTOS))
        print("  -> CREATE TABLE IF NOT EXISTS mascota_coincidencias")
        conn.execute(text(DDL_COINCIDENCIAS))
        for sql in ADD_COLUMNS:
            print(f"  -> {sql}")
            conn.execute(text(sql))
        for sql in INDEXES:
            print(f"  -> {sql}")
            conn.execute(text(sql))

    with engine.connect() as conn:
        for tabla in ("mascotas", "mascota_fotos", "mascota_coincidencias"):
            cols = [
                r[0]
                for r in conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :t ORDER BY ordinal_position"
                    ),
                    {"t": tabla},
                )
            ]
            print(f"\n{tabla} columnas: {', '.join(cols) or '(no existe)'}")
            if not cols:
                return 1
    print('\nMigración "Ayuda a Cali" OK.')
    return 0


if __name__ == "__main__":
    sys.exit(main())
