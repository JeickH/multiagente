"""Refleja en `mascota_fotos` lo que hizo el optimizador de fotos.

El optimizador corre en el equipo del CEO (el bucket es privado y la BD vive
dentro de la VPC), así que deja el resultado en un manifiesto JSON y este
script —que sí corre dentro de la VPC— lo aplica:

  - `optimizada = TRUE` + `optimizada_at`
  - `bytes_size` nuevo y `bytes_original` (lo que pesaba antes)
  - `storage_key` / `content_type` cuando un PNG se convirtió a JPG

El manifiesto llega por S3 (`import/optimizacion_fotos.json`) porque los
overrides de ECS tienen un tope de 8 KB — el mismo camino que usa el importador
de patitasacasa.

Uso:
    aws s3 cp backend/scripts/registro_optimizacion_pendientes_bd.json \
        s3://gloma-mascotas-747456040509/import/optimizacion_fotos.json
    TASKDEF=multiagente-backend:15 ./backend/scripts/rds_exec.sh \
        backend/scripts/sync_fotos_bd_mascotas.py

Nunca borra el objeto viejo de S3: si un PNG pasó a JPG, el PNG queda ahí como
respaldo hasta que el CEO autorice limpiarlo (el bucket no tiene versionado).
"""

import json
import os
from datetime import datetime

import boto3
from sqlalchemy import text

from app.database import SessionLocal

BUCKET = os.getenv("MASCOTAS_BUCKET", "gloma-mascotas-747456040509")
MANIFIESTO = os.getenv("MANIFIESTO", "import/optimizacion_fotos.json")


def main() -> None:
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "sa-east-1"))
    cambios = json.loads(
        s3.get_object(Bucket=BUCKET, Key=MANIFIESTO)["Body"].read().decode("utf-8")
    )
    print(f"manifiesto: {len(cambios)} fotos")

    db = SessionLocal()
    aplicados = faltantes = 0
    try:
        for c in cambios:
            fila = db.execute(
                text("SELECT id, storage_key FROM mascota_fotos WHERE storage_key = :k"),
                {"k": c["key_vieja"]},
            ).mappings().first()
            if fila is None:
                # La foto pudo borrarse desde el panel entre una cosa y la otra.
                print(f"  – sin fila en BD: {c['key_vieja']}")
                faltantes += 1
                continue
            db.execute(
                text(
                    "UPDATE mascota_fotos SET storage_key = :nueva, content_type = :ct, "
                    "bytes_size = :peso, bytes_original = :antes, optimizada = TRUE, "
                    "optimizada_at = :cuando WHERE id = :id"
                ),
                {
                    "nueva": c["key_nueva"],
                    "ct": c["content_type"],
                    "peso": c["bytes_size"],
                    "antes": c["bytes_original"],
                    "cuando": datetime.utcnow(),
                    "id": fila["id"],
                },
            )
            aplicados += 1
        db.commit()

        resumen = db.execute(text(
            "SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE optimizada) AS ya, "
            "COALESCE(SUM(bytes_size), 0) AS peso, "
            "COALESCE(SUM(COALESCE(bytes_original, bytes_size)), 0) AS peso_antes "
            "FROM mascota_fotos"
        )).mappings().first()
        print(f"aplicados: {aplicados} | sin fila: {faltantes}")
        print(
            f"mascota_fotos: {resumen['ya']}/{resumen['total']} optimizadas | "
            f"{resumen['peso_antes']/1048576:.2f} MB → {resumen['peso']/1048576:.2f} MB"
        )
    finally:
        db.close()


main()
