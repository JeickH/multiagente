#!/usr/bin/env python
"""Borra del bucket los objetos que ya nadie usa, con red debajo.

"Residuo" es un objeto de `gloma-mascotas-747456040509` que **ninguna fila de
`mascota_fotos` referencia**. Aparecen sobre todo cuando el optimizador
convierte un PNG a JPG: la BD pasa a apuntar al `.jpg` y el `.png` queda ahí
ocupando espacio. También caen las copias sueltas (`comparacion/…`) y lo que
haya quedado de pruebas.

La regla 1 del módulo es que **nada se borra sin autorización explícita del
CEO** — ya se perdieron fotos irrecuperables por un borrado hecho sobre una
interpretación. Así que este script:

  1. Pide las claves vivas a la BD de producción y **se niega a seguir** si la
     lista llega vacía o sospechosamente corta: sin esa lista, todo parecería
     residuo.
  2. **Baja una copia de cada objeto** a `respaldos_fotos_mascotas/` antes de
     borrarlo. El bucket no tiene versionado: sin esto no hay vuelta atrás.
  3. Sin `--borrar` no borra nada, solo enumera.

Uso:
    ./backend/scripts/rds_query.sh "SELECT storage_key FROM mascota_fotos" \
        | tail -n +3 > /tmp/keys_bd.txt
    python backend/scripts/limpiar_residuo_fotos.py --claves /tmp/keys_bd.txt
    python backend/scripts/limpiar_residuo_fotos.py --claves /tmp/keys_bd.txt --borrar
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import boto3

BUCKET = "gloma-mascotas-747456040509"
REGION = "sa-east-1"
RAIZ = Path(__file__).resolve().parents[2]
RESPALDOS = RAIZ / "respaldos_fotos_mascotas"
# Por debajo de esto, la lista de claves vivas casi seguro salió mal (la task de
# ECS falló, el query devolvió el encabezado solo…). Mejor abortar que borrar.
MINIMO_CLAVES = 50


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--claves", required=True, type=Path,
                   help="archivo con las storage_key vivas, una por línea")
    p.add_argument("--borrar", action="store_true", help="sin esto, solo enumera")
    args = p.parse_args()

    vivas = {
        linea.strip() for linea in args.claves.read_text().splitlines() if linea.strip()
    }
    if len(vivas) < MINIMO_CLAVES:
        print(f"✗ solo {len(vivas)} claves vivas: la lista se ve incompleta, no sigo.")
        return 1

    cli = boto3.client("s3", region_name=REGION)
    objetos = []
    for pagina in cli.get_paginator("list_objects_v2").paginate(Bucket=BUCKET):
        objetos.extend(o for o in pagina.get("Contents", []) if not o["Key"].endswith("/"))

    residuo = sorted(
        (o for o in objetos if o["Key"] not in vivas), key=lambda o: -o["Size"]
    )
    peso = sum(o["Size"] for o in residuo)
    print(f"bucket: {len(objetos)} objetos | vivos en BD: {len(vivas)}")
    print(f"residuo: {len(residuo)} objetos, {peso/1048576:.1f} MB\n")
    for o in residuo[:10]:
        print(f"  {o['Size']/1024:8.0f} KB  {o['Key']}")
    if len(residuo) > 10:
        print(f"  … y {len(residuo)-10} más")

    if not args.borrar:
        print("\n(simulación: nada se borró. Agrega --borrar para hacerlo)")
        return 0

    print("\nrespaldando antes de borrar…")
    respaldados = 0
    for o in residuo:
        destino = RESPALDOS / o["Key"]
        if not destino.exists():
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(cli.get_object(Bucket=BUCKET, Key=o["Key"])["Body"].read())
        respaldados += 1
    print(f"  {respaldados} copias en {RESPALDOS.relative_to(RAIZ)}/")

    borrados = 0
    for i in range(0, len(residuo), 1000):   # la API borra de a 1000
        lote = [{"Key": o["Key"]} for o in residuo[i:i + 1000]]
        resp = cli.delete_objects(Bucket=BUCKET, Delete={"Objects": lote, "Quiet": True})
        for err in resp.get("Errors", []):
            print(f"  ✗ {err['Key']}: {err['Message']}")
        borrados += len(lote) - len(resp.get("Errors", []))
    print(f"✓ borrados {borrados} objetos ({peso/1048576:.1f} MB liberados)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
