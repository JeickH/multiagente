"""Carga a la base el payload que aprobó el CEO en la revisión de una fuente.

El payload lo produce `actualizar_fuente.py <fuente> --revisar`:

    pendientes.json    registros ya mapeados a los campos de `models.Mascota`
    fotos/<archivo>    las fotos, bajadas durante la revisión

De dónde lo lee (el mismo script sirve en los dos entornos):

    IMPORT_DIR=/app/import                      carpeta local (docker-compose)
    IMPORT_BUCKET=... IMPORT_PREFIX=import/...  S3 (producción, vía rds_exec.sh)

Y siempre `SOURCE=<fuente>`, que es lo que deduplica.

Es idempotente: salta lo que ya existe con ese `(source, origen_id)`. Correrlo
dos veces no duplica nada.

    docker compose -p wati exec -T -e SOURCE=petsearch -e IMPORT_DIR=/app/import \
        -w /app -e PYTHONPATH=/app backend python scripts/import_fuente.py

    TASKDEF=multiagente-backend:NN ./backend/scripts/rds_exec.sh \
        backend/scripts/import_fuente.py SOURCE=petsearch \
        IMPORT_BUCKET=gloma-mascotas-747456040509 IMPORT_PREFIX=import/petsearch
"""
import json
import os

from app.database import SessionLocal
from app import models
from app.services import mascotas as svc

SOURCE = os.environ["SOURCE"]
CAMPOS = (
    "tipo_registro", "especie", "raza", "color", "nombre", "sexo", "edad",
    "tamano", "senas", "ubicacion", "maps_url", "barrio", "contacto_nombre",
    "contacto_telefono", "fecha_evento", "notas", "origen_url", "origen_id",
)


def _lector():
    """Devuelve (registros, leer_foto) según de dónde venga el payload."""
    carpeta = os.getenv("IMPORT_DIR")
    if carpeta:
        with open(os.path.join(carpeta, "pendientes.json"), encoding="utf-8") as fh:
            registros = json.load(fh)

        def leer(nombre):
            with open(os.path.join(carpeta, "fotos", nombre), "rb") as fh:
                return fh.read()

        return registros, leer

    import boto3

    bucket = os.environ["IMPORT_BUCKET"]
    prefijo = os.environ["IMPORT_PREFIX"].rstrip("/")
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "sa-east-1"))
    cuerpo = s3.get_object(Bucket=bucket, Key=f"{prefijo}/pendientes.json")["Body"].read()

    def leer(nombre):
        return s3.get_object(Bucket=bucket, Key=f"{prefijo}/fotos/{nombre}")["Body"].read()

    return json.loads(cuerpo), leer


def main() -> None:
    registros, leer_foto = _lector()
    db = SessionLocal()
    creados = repetidos = fallidos = fotos_ok = 0
    try:
        for reg in registros:
            origen_id = reg["origen_id"]
            existe = (
                db.query(models.Mascota)
                .filter(models.Mascota.source == SOURCE,
                        models.Mascota.origen_id == origen_id)
                .first()
            )
            if existe:
                repetidos += 1
                continue

            mascota, problema = svc.crear_reporte(
                db, {c: reg.get(c) for c in CAMPOS}, source=SOURCE
            )
            if mascota is None:
                fallidos += 1
                print(f"! {origen_id} rechazado: {problema}")
                continue
            creados += 1

            for foto in reg.get("fotos", []):
                try:
                    svc.guardar_foto(
                        db, leer_foto(foto["archivo"]),
                        foto.get("content_type") or "image/jpeg", mascota=mascota,
                    )
                    fotos_ok += 1
                except Exception as exc:   # una foto perdida no aborta la carga
                    print(f"! {mascota.codigo} sin foto ({foto['archivo']}): {exc}")
            print(f"+ {mascota.codigo} {mascota.nombre or '(sin nombre)'} "
                  f"[{mascota.tipo_registro}] ({origen_id})")
    finally:
        db.close()

    print(f"\nRESUMEN {SOURCE}: creados={creados} fotos={fotos_ok} "
          f"ya_estaban={repetidos} fallidos={fallidos} total={len(registros)}")


main()
