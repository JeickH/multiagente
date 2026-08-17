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


# Columnas multi-fuente. El backfill solo escribe estas, y solo donde están en
# NULL: un dato que el equipo corrigió a mano no lo pisa una corrida del script.
CAMPOS_MULTIFUENTE = (
    "ciudad", "departamento", "esterilizado", "vacunado", "desparasitado",
    "peso_kg", "salud", "resguardo", "resguardo_nombre", "rescatado_por",
    "rescatado_por_telefono", "recompensa", "estado_origen", "publicado_origen_at",
)


def backfill(mod, escribir_json: str | None) -> None:
    """Rellena las columnas multi-fuente de lo que ya está cargado.

    Los registros que entraron antes de que existieran esas columnas tienen los
    15 campos en NULL. Se vuelve a bajar la fuente (sin fotos) y se completa lo
    que falte, emparejando por `origen_id`.

    Con `--json <archivo>` no toca la base: deja los valores en un archivo para
    aplicarlos en producción, donde la base no es accesible desde aquí.
    """
    from app.database import SessionLocal
    from app import models
    from app.services import mascotas as svc

    print(f"[{mod.FUENTE}] bajando para completar campos ...")
    registros, _ = mod.bajar()
    valores = {
        r["origen_id"]: {c: r.get(c) for c in CAMPOS_MULTIFUENTE if r.get(c) is not None}
        for r in registros
    }
    valores = {k: v for k, v in valores.items() if v}
    print(f"[{mod.FUENTE}] {len(valores)} fichas con algo que completar")

    if escribir_json:
        with open(escribir_json, "w", encoding="utf-8") as fh:
            json.dump({"source": mod.FUENTE, "valores": valores}, fh,
                      ensure_ascii=False, default=str)
        print(f"[{mod.FUENTE}] valores guardados en {escribir_json}")
        return

    db = SessionLocal()
    tocados = campos_escritos = 0
    try:
        for origen_id, campos in valores.items():
            m = (db.query(models.Mascota)
                 .filter(models.Mascota.source == mod.FUENTE,
                         models.Mascota.origen_id == origen_id).first())
            if m is None:
                continue
            cambio = False
            for campo, valor in campos.items():
                if getattr(m, campo) is not None:
                    continue          # ya tiene dato: no se pisa
                if campo in ("esterilizado", "vacunado", "desparasitado", "recompensa"):
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
                campos_escritos += 1
                cambio = True
            if cambio:
                m.sincronizado_at = __import__("datetime").datetime.utcnow()
                tocados += 1
        db.commit()
    finally:
        db.close()
    print(f"RESUMEN backfill {mod.FUENTE}: fichas_tocadas={tocados} "
          f"campos_escritos={campos_escritos}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("fuente", choices=sorted(FUENTES) + ["todas"])
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--revisar", action="store_true",
                       help="baja la fuente y arma el HTML de revisión (no toca la base)")
    grupo.add_argument("--cargar", action="store_true",
                       help="carga lo aprobado en la revisión anterior")
    grupo.add_argument("--backfill", action="store_true",
                       help="completa las columnas multi-fuente de lo ya cargado")
    p.add_argument("--solo", help="cargar solo estos origen_id, separados por coma")
    p.add_argument("--json", help="con --backfill: escribe los valores a un archivo "
                                  "en vez de tocar la base (para producción)")
    args = p.parse_args()

    nombres = sorted(FUENTES) if args.fuente == "todas" else [args.fuente]
    solo = set(args.solo.split(",")) if args.solo else None
    for nombre in nombres:
        mod = FUENTES[nombre]
        if args.revisar:
            revisar(mod)
        elif args.backfill:
            destino = args.json.replace("FUENTE", nombre) if args.json else None
            backfill(mod, destino)
        else:
            cargar(mod, solo)


if __name__ == "__main__":
    main()
