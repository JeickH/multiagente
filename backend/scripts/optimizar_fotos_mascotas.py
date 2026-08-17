#!/usr/bin/env python
"""Aliviana las fotos de mascotasperdidascolombia.com guardadas en S3.

Hace lo mismo que TinyPNG / Squoosh, pero local y sin subirle las fotos de
nadie a un tercero: re-comprime cada imagen buscando el archivo más pequeño que
todavía se ve igual que el original, medido con SSIM (índice de similitud
estructural). Si ninguna calidad alcanza el umbral, la foto se deja intacta.

Se ejecuta SIEMPRE desde este equipo (el bucket es privado y la BD vive en la
VPC), y lleva su propio registro para no volver a procesar lo ya procesado:

    backend/scripts/registro_optimizacion_fotos.csv   <- se abre en Excel

Doble candado contra el reproceso:
  1. el CSV, con el ETag resultante de cada foto;
  2. la metadata `optimizado=v1` que queda en el objeto de S3.
Si una foto vuelve a subirse con la misma clave (ETag distinto al registrado),
se vuelve a procesar: es una foto nueva, no la misma.

Antes de sobreescribir nada, la original se copia a `respaldos_fotos_mascotas/`
(el bucket NO tiene versionado: lo que se pisa sin respaldo, se pierde).

Uso:
    conda activate multiagente
    python backend/scripts/optimizar_fotos_mascotas.py --dry-run
    python backend/scripts/optimizar_fotos_mascotas.py --solo mascotas/MC-00127/xxx.jpg
    python backend/scripts/optimizar_fotos_mascotas.py            # todo lo pendiente
    python backend/scripts/optimizar_fotos_mascotas.py --restaurar mascotas/MC-00127/xxx.jpg

Los PNG se convierten a JPEG (es donde está la mayor ganancia), lo que cambia
la clave del objeto: el script NO borra el PNG viejo ni toca la BD, sólo deja
el cambio anotado en `registro_optimizacion_pendientes_bd.json` para aplicarlo
con `sync_fotos_bd_mascotas.py` dentro de la VPC.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import boto3

# El algoritmo vive en el backend (`app/services/imagenes.py`) para que sea el
# mismo que comprime al subir una foto. Este script sólo pone el bucket, el
# registro y los respaldos.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services import imagenes  # noqa: E402

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

BUCKET = os.getenv("MASCOTAS_BUCKET", "gloma-mascotas-747456040509")
REGION = os.getenv("AWS_REGION", "sa-east-1")
PREFIJOS = ("mascotas/", "pendientes/")

RAIZ = Path(__file__).resolve().parents[2]
REGISTRO = Path(__file__).resolve().parent / "registro_optimizacion_fotos.csv"
PENDIENTES_BD = Path(__file__).resolve().parent / "registro_optimizacion_pendientes_bd.json"
RESPALDOS = RAIZ / "respaldos_fotos_mascotas"

MARCA = imagenes.MARCA  # la misma marca que pone el backend al comprimir al subir

# Calidades, umbral de SSIM y tamaño máximo salen del servicio compartido: son
# los mismos que aplica el backend cuando alguien sube una foto por el chat.
CALIDADES = imagenes.CALIDADES
SSIM_MIN = imagenes.SSIM_MIN
MAX_LADO = imagenes.MAX_LADO
AHORRO_MIN = 0.10    # si no baja al menos 10%, no vale la pena reescribir

COLUMNAS = [
    "key", "codigo", "fecha_utc", "estado", "bytes_antes", "bytes_despues",
    "ahorro_pct", "dim_antes", "dim_despues", "calidad_jpeg", "ssim",
    "key_nueva", "respaldo", "etag_despues", "nota",
]


# ---------------------------------------------------------------------------
# Registro local
# ---------------------------------------------------------------------------

def leer_registro() -> Dict[str, dict]:
    if not REGISTRO.exists():
        return {}
    with REGISTRO.open(newline="", encoding="utf-8") as fh:
        return {fila["key"]: fila for fila in csv.DictReader(fh)}


def anotar(fila: dict) -> None:
    nuevo = not REGISTRO.exists()
    with REGISTRO.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNAS)
        if nuevo:
            w.writeheader()
        w.writerow({c: fila.get(c, "") for c in COLUMNAS})


def anotar_pendiente_bd(cambio: dict) -> None:
    """Cambios que hay que reflejar en la tabla `mascota_fotos` (dentro de la VPC)."""
    datos = json.loads(PENDIENTES_BD.read_text()) if PENDIENTES_BD.exists() else []
    datos = [d for d in datos if d.get("key_vieja") != cambio["key_vieja"]]
    datos.append(cambio)
    PENDIENTES_BD.write_text(json.dumps(datos, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# S3
# ---------------------------------------------------------------------------

def s3():
    return boto3.client("s3", region_name=REGION)


def listar() -> List[dict]:
    cli, objetos = s3(), []
    for prefijo in PREFIJOS:
        for pagina in cli.get_paginator("list_objects_v2").paginate(
            Bucket=BUCKET, Prefix=prefijo
        ):
            for o in pagina.get("Contents", []):
                if not o["Key"].endswith("/"):
                    objetos.append(o)
    return sorted(objetos, key=lambda o: -o["Size"])


def respaldar(key: str, data: bytes) -> Path:
    destino = RESPALDOS / key
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(data)
    return destino


def presignar(key: str, segundos: int = 7 * 24 * 3600) -> str:
    return s3().generate_presigned_url(
        "get_object", Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=segundos
    )


# ---------------------------------------------------------------------------
# Proceso
# ---------------------------------------------------------------------------

def codigo_de(key: str) -> str:
    partes = key.split("/")
    return partes[1] if len(partes) > 2 else ""


def procesar(obj: dict, args) -> dict:
    key, cli = obj["Key"], s3()
    ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    # Se anota el ETag actual aunque la foto no se toque: así, si mañana alguien
    # sube otra foto con la misma clave, el ETag cambia y se vuelve a procesar.
    base = {"key": key, "codigo": codigo_de(key), "fecha_utc": ahora,
            "bytes_antes": obj["Size"], "etag_despues": obj["ETag"].strip('"')}

    resp = cli.get_object(Bucket=BUCKET, Key=key)
    data = resp["Body"].read()
    if resp.get("Metadata", {}).get("optimizado") == MARCA and not args.forzar:
        return {**base, "estado": "ya_optimizada", "nota": "marca en S3"}

    try:
        salida, info = imagenes.comprimir_buscando(data, args.max_lado, args.ssim)
    except Exception as exc:  # imagen corrupta o formato raro
        return {**base, "estado": "error", "nota": str(exc)[:120]}

    fila = {**base, **info, "bytes_despues": len(salida)}
    fila["ahorro_pct"] = round(100 * (1 - len(salida) / max(1, obj["Size"])), 1)

    def _dejar_como_esta(estado: str, nota: str) -> dict:
        """La foto no se toca, pero sí se da por evaluada: en la BD queda
        `optimizada=TRUE` con el mismo peso, para que el flujo no la vuelva a
        mirar en cada corrida."""
        if not args.dry_run:
            anotar_pendiente_bd({
                "key_vieja": key, "key_nueva": key,
                "content_type": resp.get("ContentType") or "image/jpeg",
                "bytes_size": obj["Size"], "bytes_original": obj["Size"],
                "ssim": info["ssim"], "calidad_jpeg": "", "fecha_utc": ahora,
            })
        return {**fila, "estado": estado, "nota": nota}

    if float(info["ssim"]) < args.ssim:
        return _dejar_como_esta(
            "omitida_calidad",
            f"SSIM {info['ssim']} < {args.ssim} ni en calidad {CALIDADES[-1]}")

    es_png = key.lower().endswith(".png")
    if not es_png and len(salida) > obj["Size"] * (1 - AHORRO_MIN):
        return _dejar_como_esta(
            "omitida_sin_ganancia", f"sólo bajaría {fila['ahorro_pct']}%")

    # Los PNG se guardan como .jpg: clave nueva, y la BD hay que avisarla.
    key_destino = key[:-4] + ".jpg" if es_png else key

    if args.dry_run:
        return {**fila, "estado": "simulada", "key_nueva":
                key_destino if key_destino != key else "", "nota": "dry-run"}

    fila["respaldo"] = str(respaldar(key, data).relative_to(RAIZ))
    put = cli.put_object(
        Bucket=BUCKET, Key=key_destino, Body=salida, ContentType="image/jpeg",
        Metadata={"optimizado": MARCA, "bytes-original": str(obj["Size"]),
                  "ssim": str(info["ssim"])},
    )
    # El ETag que se guarda es el del objeto que está EN LA CLAVE de esta fila:
    # si el PNG se convirtió a JPG, el PNG sigue ahí con su ETag de siempre, y
    # comparar contra el del JPG nuevo lo haría reprocesarse en cada corrida.
    if key_destino == key:
        fila["etag_despues"] = put["ETag"].strip('"')
    fila["estado"] = "optimizada"

    # Todo lo optimizado queda pendiente de reflejarse en `mascota_fotos`
    # (bandera `optimizada`, peso nuevo y, si el PNG pasó a JPG, la clave).
    anotar_pendiente_bd({
        "key_vieja": key,
        "key_nueva": key_destino,
        "content_type": "image/jpeg",
        "bytes_size": len(salida),
        "bytes_original": obj["Size"],
        "ssim": info["ssim"],
        "calidad_jpeg": info["calidad_jpeg"],
        "fecha_utc": ahora,
    })
    if key_destino != key:
        fila["key_nueva"] = key_destino
        fila["nota"] = "PNG→JPG: cambia la clave (el PNG viejo NO se borró)"
    return fila


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true", help="no escribe en S3")
    p.add_argument("--solo", action="append", default=[], metavar="KEY",
                   help="procesa sólo esta(s) clave(s)")
    p.add_argument("--limite", type=int, default=0, help="máximo de fotos a procesar")
    p.add_argument("--forzar", action="store_true", help="reprocesa aunque ya esté en el registro")
    p.add_argument("--ssim", type=float, default=SSIM_MIN)
    p.add_argument("--max-lado", type=int, default=MAX_LADO)
    p.add_argument("--restaurar", metavar="KEY", help="devuelve una foto a su original respaldada")
    p.add_argument("--link", metavar="KEY", help="imprime un link firmado (7 días) para revisar")
    args = p.parse_args()

    if args.link:
        print(presignar(args.link))
        return 0

    if args.restaurar:
        origen = RESPALDOS / args.restaurar
        if not origen.exists():
            print(f"✗ no hay respaldo de {args.restaurar}")
            return 1
        tipo = "image/png" if args.restaurar.lower().endswith(".png") else "image/jpeg"
        s3().put_object(Bucket=BUCKET, Key=args.restaurar,
                        Body=origen.read_bytes(), ContentType=tipo)
        print(f"✓ restaurada {args.restaurar} ({origen.stat().st_size:,} bytes)")
        print("  Quítala del CSV si quieres volver a optimizarla.")
        return 0

    registro = leer_registro()
    objetos = listar()
    if args.solo:
        objetos = [o for o in objetos if o["Key"] in args.solo]

    pendientes = []
    for o in objetos:
        prev = registro.get(o["Key"])
        etag = o["ETag"].strip('"')
        # Ya registrada y el objeto no cambió desde entonces -> nada que hacer.
        if prev and not args.forzar and prev.get("etag_despues") in (etag, "") \
                and prev.get("estado") in ("optimizada", "omitida_sin_ganancia",
                                           "omitida_calidad", "ya_optimizada"):
            continue
        pendientes.append(o)
    if args.limite:
        pendientes = pendientes[: args.limite]

    total_antes = total_despues = 0
    print(f"Bucket {BUCKET}: {len(objetos)} fotos, {len(pendientes)} sin optimizar\n")
    for i, o in enumerate(pendientes, 1):
        fila = procesar(o, args)
        if not args.dry_run:
            anotar(fila)
        antes, despues = fila["bytes_antes"], fila.get("bytes_despues") or fila["bytes_antes"]
        if fila["estado"] in ("optimizada", "simulada"):
            total_antes += antes
            total_despues += despues
        icono = {"optimizada": "✓", "simulada": "·", "error": "✗"}.get(fila["estado"], "–")
        print(f"{icono} [{i}/{len(pendientes)}] {o['Key']}")
        print(f"    {antes/1024:8.1f} KB → {despues/1024:8.1f} KB "
              f"({fila.get('ahorro_pct', 0)}%)  q={fila.get('calidad_jpeg', '-')} "
              f"ssim={fila.get('ssim', '-')}  {fila['estado']} {fila.get('nota', '')}")

    if total_antes:
        print(f"\nTotal: {total_antes/1024/1024:.2f} MB → {total_despues/1024/1024:.2f} MB "
              f"({100*(1-total_despues/total_antes):.1f}% menos)")
    if PENDIENTES_BD.exists() and not args.dry_run:
        print(f"\n⚠ Hay cambios de clave por aplicar en la BD: {PENDIENTES_BD.name}")
        print("  Corre: ./backend/scripts/rds_exec.sh backend/scripts/sync_fotos_bd_mascotas.py")
    print(f"\nRegistro: {REGISTRO}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
