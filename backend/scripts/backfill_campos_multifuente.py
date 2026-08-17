"""Completa las columnas multi-fuente de los reportes que ya estaban cargados.

Los 320 reportes que entraron antes de `migrate_campos_multifuente.py` tienen
las 15 columnas nuevas en NULL. Este script las rellena con lo que ya publica
cada fuente, emparejando por `(source, origen_id)`.

El payload lo produce:
    python backend/scripts/actualizar_fuente.py todas --backfill --json <dir>/FUENTE.json
y para RoyiPets, `backend/scripts/extraer_royipets_pdf.py` (sale del PDF).

Formato: {"source": "petsearch", "valores": {"<origen_id>": {"campo": valor}}}

**Solo escribe donde hay NULL.** Un dato que el equipo corrigió a mano en el
panel no lo pisa una corrida del script, y correrlo dos veces no cambia nada la
segunda vez.

    IMPORT_DIR=/app/backfill    carpeta local
    IMPORT_BUCKET / IMPORT_PREFIX   S3 (producción)
"""
import json
import os
from datetime import datetime

from app.database import SessionLocal
from app import models
from app.services import mascotas as svc

BOOLEANOS = ("esterilizado", "vacunado", "desparasitado", "recompensa")
FUENTES = ("royipets", "petsearch", "encontradogs", "proteccionanimal")


def _payloads():
    carpeta = os.getenv("IMPORT_DIR")
    if carpeta:
        for fuente in FUENTES:
            ruta = os.path.join(carpeta, f"{fuente}.json")
            if os.path.exists(ruta):
                with open(ruta, encoding="utf-8") as fh:
                    yield json.load(fh)
        return

    import boto3

    bucket = os.environ["IMPORT_BUCKET"]
    prefijo = os.environ["IMPORT_PREFIX"].rstrip("/")
    s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "sa-east-1"))
    for fuente in FUENTES:
        try:
            cuerpo = s3.get_object(
                Bucket=bucket, Key=f"{prefijo}/{fuente}.json")["Body"].read()
        except Exception:
            continue
        yield json.loads(cuerpo)


def main() -> None:
    db = SessionLocal()
    total_fichas = total_campos = 0
    try:
        for payload in _payloads():
            source, valores = payload["source"], payload["valores"]
            fichas = campos = sin_match = 0
            for origen_id, nuevos in valores.items():
                m = (db.query(models.Mascota)
                     .filter(models.Mascota.source == source,
                             models.Mascota.origen_id == origen_id).first())
                if m is None:
                    sin_match += 1
                    continue
                cambio = False
                for campo, valor in nuevos.items():
                    if getattr(m, campo, "__falta__") is None:
                        if campo in BOOLEANOS:
                            valor = svc._booleano(valor)
                        elif campo == "peso_kg":
                            valor = svc._decimal(valor)
                        elif campo == "publicado_origen_at":
                            valor = svc._parse_datetime(valor)
                        else:
                            valor = svc._limpiar(valor, svc._LIMITES.get(campo, 255))
                        if valor is None:
                            continue
                        setattr(m, campo, valor)
                        campos += 1
                        cambio = True
                if cambio:
                    m.sincronizado_at = datetime.utcnow()
                    fichas += 1
            db.commit()
            print(f"{source:18} fichas_tocadas={fichas:4} campos_escritos={campos:4} "
                  f"sin_match={sin_match}")
            total_fichas += fichas
            total_campos += campos
    finally:
        db.close()
    print(f"\nRESUMEN backfill: fichas={total_fichas} campos={total_campos}")


main()
