"""Actualiza una fuente de mascotas, en dos pasos y con un humano en el medio.

    python backend/scripts/actualizar_fuente.py <fuente> --revisar
        Baja la fuente, descarta lo que ya está en la base y arma un HTML con
        las fichas nuevas. NO escribe nada en la base.

    python backend/scripts/actualizar_fuente.py <fuente> --cargar
        Carga lo que quedó aprobado en la revisión anterior. Vuelve a verificar
        contra la base, así que aunque se corra dos veces no duplica nada.

Fuentes: petsearch · encontradogs · proteccionanimal

El flujo completo, tal como se opera:

    python backend/scripts/actualizar_fuente.py petsearch --revisar
    open testdata/fuentes_import/petsearch/revision.html      # ← lo revisa el CEO
    python backend/scripts/actualizar_fuente.py petsearch --cargar

Para descartar fichas puntuales antes de cargar, se borran del
`pendientes.json` que dejó la revisión (o se corre `--cargar --solo id1,id2`).

Se ejecuta desde el equipo, no desde ECS: varios de estos sitios bloquean las
IPs de AWS (la lección de patitasacasa, ver MANUAL_RECUPERA_TU_MASCOTA.md §6).
La carga a producción va con `rds_exec.sh` + el payload en S3, igual que
`import_royipets.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(RAIZ, "backend"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fuentes import base, encontradogs, petsearch, proteccionanimal  # noqa: E402

FUENTES = {
    petsearch.FUENTE: petsearch,
    encontradogs.FUENTE: encontradogs,
    proteccionanimal.FUENTE: proteccionanimal,
}
SALIDA = os.path.join(RAIZ, "testdata", "fuentes_import")


def revisar(mod) -> None:
    base.ejecutar(
        fuente=mod.FUENTE,
        titulo=mod.TITULO,
        url_fuente=mod.URL,
        bajar=mod.bajar,
        como_se_lleno=mod.COMO_SE_LLENO,
        derivados=mod.DERIVADOS,
        carpeta=os.path.join(SALIDA, mod.FUENTE),
    )


def cargar(mod, solo: set | None) -> None:
    from app.database import SessionLocal
    from app import models
    from app.services import mascotas as svc

    carpeta = os.path.join(SALIDA, mod.FUENTE)
    ruta = os.path.join(carpeta, "pendientes.json")
    if not os.path.exists(ruta):
        sys.exit(f"No hay revisión pendiente para {mod.FUENTE}. Corre primero --revisar.")
    with open(ruta, encoding="utf-8") as fh:
        pendientes = json.load(fh)
    if solo:
        pendientes = [p for p in pendientes if p["origen_id"] in solo]

    campos = ("tipo_registro", "especie", "raza", "color", "nombre", "sexo", "edad",
              "tamano", "senas", "ubicacion", "maps_url", "barrio", "contacto_nombre",
              "contacto_telefono", "fecha_evento", "notas", "origen_url", "origen_id")

    db = SessionLocal()
    creados = repetidos = fallidos = con_foto = 0
    try:
        for reg in pendientes:
            existe = (
                db.query(models.Mascota)
                .filter(models.Mascota.source == mod.FUENTE,
                        models.Mascota.origen_id == reg["origen_id"])
                .first()
            )
            if existe:
                repetidos += 1
                continue
            mascota, problema = svc.crear_reporte(
                db, {c: reg.get(c) for c in campos}, source=mod.FUENTE
            )
            if mascota is None:
                fallidos += 1
                print(f"! {reg['origen_id']} rechazado: {problema}")
                continue
            creados += 1
            for foto in reg.get("fotos", []):
                ruta_foto = os.path.join(carpeta, "fotos", foto["archivo"])
                try:
                    with open(ruta_foto, "rb") as fh:
                        svc.guardar_foto(db, fh.read(), foto["content_type"], mascota=mascota)
                    con_foto += 1
                except Exception as exc:
                    print(f"! {mascota.codigo} sin foto ({foto['archivo']}): {exc}")
            print(f"+ {mascota.codigo} {mascota.nombre or '(sin nombre)'} "
                  f"[{mascota.tipo_registro}] ({reg['origen_id']})")
    finally:
        db.close()

    print(f"\nRESUMEN {mod.FUENTE}: creados={creados} fotos={con_foto} "
          f"ya_estaban={repetidos} fallidos={fallidos} total={len(pendientes)}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fuente", choices=sorted(FUENTES) + ["todas"])
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--revisar", action="store_true",
                       help="baja la fuente y arma el HTML de revisión (no toca la base)")
    grupo.add_argument("--cargar", action="store_true",
                       help="carga lo aprobado en la revisión anterior")
    p.add_argument("--solo", help="cargar solo estos origen_id, separados por coma")
    args = p.parse_args()

    nombres = sorted(FUENTES) if args.fuente == "todas" else [args.fuente]
    solo = set(args.solo.split(",")) if args.solo else None
    for nombre in nombres:
        mod = FUENTES[nombre]
        if args.revisar:
            revisar(mod)
        else:
            cargar(mod, solo)


if __name__ == "__main__":
    main()
