"""Carga el reporte de mascotas de RoyiPets (Cali) como reportes 'encontrada'.

El payload (metadatos + fotos) lo produce `testdata/royipets_import/extraer.py`
a partir del PDF que manda la fundación.

    registros.json     lista de dicts con los campos de `models.Mascota`
    fotos/<ref>.png    una foto por registro

De dónde lo lee:
    IMPORT_DIR=/app/import                       carpeta local (docker-compose)
    IMPORT_BUCKET=... IMPORT_PREFIX=import/...   S3 (producción, vía rds_exec.sh)

Idempotente: deduplica por `(source, origen_id)`, así que se puede volver a
correr sin duplicar. Los registros que ya existen no se tocan.

    docker compose -p wati exec -T backend python scripts/import_royipets.py
    TASKDEF=multiagente-backend:NN ./backend/scripts/rds_exec.sh \
        backend/scripts/import_royipets.py IMPORT_BUCKET=... IMPORT_PREFIX=...
"""
import json
import os

from app.database import SessionLocal
from app import models
from app.services import mascotas as svc

SOURCE = "royipets"
CAMPOS = (
    "tipo_registro", "especie", "raza", "color", "nombre", "sexo", "edad",
    "tamano", "senas", "ubicacion", "maps_url", "barrio", "contacto_nombre",
    "contacto_telefono", "fecha_evento", "notas", "origen_id",
)


def _lector():
    """Devuelve (registros, leer_foto) según de dónde venga el payload."""
    carpeta = os.getenv("IMPORT_DIR")
    if carpeta:
        with open(os.path.join(carpeta, "registros.json"), encoding="utf-8") as fh:
            registros = json.load(fh)

        def leer(nombre):
            with open(os.path.join(carpeta, "fotos", nombre), "rb") as fh:
                return fh.read()

        return registros, leer

    import boto3

    bucket = os.environ["IMPORT_BUCKET"]
    prefijo = os.environ["IMPORT_PREFIX"].rstrip("/")
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "sa-east-1"))
    cuerpo = s3.get_object(Bucket=bucket, Key=f"{prefijo}/registros.json")["Body"].read()

    def leer(nombre):
        return s3.get_object(Bucket=bucket, Key=f"{prefijo}/fotos/{nombre}")["Body"].read()

    return json.loads(cuerpo), leer


def main() -> None:
    registros, leer_foto = _lector()
    db = SessionLocal()
    creados = repetidos = fallidos = con_foto = 0
    try:
        for reg in registros:
            origen_id = reg["origen_id"]
            existe = (
                db.query(models.Mascota)
                .filter(
                    models.Mascota.source == SOURCE,
                    models.Mascota.origen_id == origen_id,
                )
                .first()
            )
            if existe:
                repetidos += 1
                print(f"= {origen_id} ya estaba como {existe.codigo}")
                continue

            datos = {c: reg.get(c) for c in CAMPOS}
            mascota, problema = svc.crear_reporte(db, datos, source=SOURCE)
            if mascota is None:
                fallidos += 1
                print(f"! {origen_id} rechazado: {problema}")
                continue
            creados += 1

            nombre_foto = reg.get("foto")
            if nombre_foto:
                try:
                    data = leer_foto(nombre_foto)
                    tipo = "image/png" if nombre_foto.endswith(".png") else "image/jpeg"
                    svc.guardar_foto(db, data, tipo, mascota=mascota)
                    con_foto += 1
                except Exception as exc:   # una foto perdida no aborta la carga
                    print(f"! {mascota.codigo} sin foto ({nombre_foto}): {exc}")
            print(f"+ {mascota.codigo} {mascota.nombre} ({origen_id})")
    finally:
        db.close()

    print(
        f"\nRESUMEN creados={creados} con_foto={con_foto} "
        f"ya_estaban={repetidos} fallidos={fallidos} total={len(registros)}"
    )


main()
