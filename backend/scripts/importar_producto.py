"""Carga el catálogo de un cliente en `bot_productos`, con un humano en el medio.

    python backend/scripts/importar_producto.py <slug> --team-id N --revisar
        Lee el archivo del cliente, lo compara contra la base y escribe un diff
        en HTML: qué entra, qué cambia, qué se retira. NO toca la base.

    python backend/scripts/importar_producto.py <slug> --team-id N --cargar \\
        --aprobado-por <correo|id>
        Aplica lo que quedó aprobado en la revisión anterior y deja el rastro en
        `bot_producto_cargas`. Se niega si no hubo revisión, si el archivo
        cambió desde entonces o si la base se movió por debajo.

Catálogos disponibles: covenas_temporada

El flujo, tal como se opera:

    python backend/scripts/importar_producto.py covenas_temporada --team-id 3 --revisar
    open testdata/productos_import/team3/covenas_temporada/revision.html   # ← lo revisa el CEO
    python backend/scripts/importar_producto.py covenas_temporada --team-id 3 --cargar \\
        --aprobado-por duena@ejemplo.test

Las tres cosas que este script promete
--------------------------------------
* **Cargar dos veces el mismo archivo no duplica ni una fila.** Cada fila se
  busca por `(producto_id, variante_id, externo_id)`, que es el UNIQUE de la
  tabla; la segunda corrida la encuentra y la actualiza.
* **No borra nada.** Lo que desaparece del archivo queda `activo = false`, y
  aparece en el diff antes de que se aplique nada.
* **Avisa si la ventana de fallback sigue abierta.** Mientras los dos motores
  están vivos, cargar precios nuevos en la base significa que un turno que
  caiga al motor viejo cotice con los del JSON — y nadie se entera hasta que un
  cliente reclama. En ese caso pide confirmación explícita.

Se ejecuta en local contra el compose (`docker compose -p wati`). Para
producción va con `rds_exec.sh`, igual que los importadores de mascotas, y
**nunca** sin haber mirado el HTML antes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

#: La raíz del backend, sea el árbol de trabajo (`.../backend`) o la imagen
#: (`/app`, donde el Dockerfile copia el backend pelado). Se deduce del propio
#: archivo en vez de contar carpetas hacia arriba: dentro del contenedor no hay
#: una carpeta `backend/` que contar.
BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAIZ = os.path.dirname(BACKEND)
for _ruta in (BACKEND, os.path.join(BACKEND, "scripts")):
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

from productos_fuentes import base, covenas  # noqa: E402

RECETAS = {covenas.SLUG: covenas}
SALIDA = os.path.join(RAIZ, "testdata", "productos_import")


def abrir_sesion():
    """La sesión contra la base. Las pruebas la reemplazan por una de SQLite."""
    from app.database import SessionLocal

    return SessionLocal()


def carpeta_de(salida: str, *, team_id: int, slug: str) -> str:
    return os.path.join(salida, f"team{team_id}", slug)


# ---------------------------------------------------------------------------
# Paso 1: revisar
# ---------------------------------------------------------------------------

def revisar(db, receta, *, team_id: int, archivo: str, salida: str) -> dict:
    catalogo = receta.leer(archivo)
    huella = base.hash_archivo(archivo)
    actual = base.estado_actual(db, team_id=team_id, slug=catalogo.slug)
    diff = base.comparar(actual, catalogo)
    ventana = base.bots_en_ventana(db, team_id=team_id)

    carpeta = carpeta_de(salida, team_id=team_id, slug=catalogo.slug)
    os.makedirs(carpeta, exist_ok=True)
    html = os.path.join(carpeta, "revision.html")
    base.escribir_revision(
        diff,
        salida=html,
        titulo=getattr(receta, "TITULO", catalogo.nombre),
        archivo=archivo,
        hash_sha256=huella,
        team_id=team_id,
        como_se_lleno=getattr(receta, "COMO_SE_LLENO", ()),
        ventana=ventana,
        producto_existe=actual is not None,
    )
    pendiente = {
        "slug": catalogo.slug,
        "team_id": team_id,
        "archivo": archivo,
        "hash_sha256": huella,
        "generado_at": datetime.now().isoformat(timespec="seconds"),
        "firma": base.firma(diff),
        "diff": diff,
    }
    with open(os.path.join(carpeta, "pendiente.json"), "w", encoding="utf-8") as fh:
        json.dump(pendiente, fh, ensure_ascii=False, indent=1, default=str)

    t = diff["totales"]
    print(f"[{catalogo.slug}] archivo: {archivo}")
    print(f"[{catalogo.slug}] sha256:  {huella}")
    print(
        f"[{catalogo.slug}] filas: +{t['filas_nuevas']} nuevas · "
        f"~{t['filas_cambiadas']} cambiadas · -{t['filas_retiradas']} retiradas "
        f"(se marcan activo=false, no se borran) · "
        f"{t['filas_reordenadas']} solo se corrieron de lugar"
    )
    print(
        f"[{catalogo.slug}] variantes: +{t['variantes_nuevas']}/~{t['variantes_cambiadas']}"
        f"/-{t['variantes_retiradas']} · medios: +{t['medios_nuevos']}/~{t['medios_cambiados']}"
        f" · alias: +{t['alias_nuevos']}"
    )
    if ventana:
        cuales = ", ".join(f"#{b['bot_id']} {b['nombre']}" for b in ventana)
        print(
            f"[{catalogo.slug}] OJO: la ventana de observación sigue abierta ({cuales}). "
            "Cargar ahora deja la base y el JSON diciendo cosas distintas."
        )
    if not base.hay_algo_que_hacer(diff):
        print(f"[{catalogo.slug}] la base ya está igual al archivo: no hay nada que cargar.")
    print(f"[{catalogo.slug}] revisión lista: {html}")
    return pendiente


# ---------------------------------------------------------------------------
# Paso 2: cargar
# ---------------------------------------------------------------------------

def _usuario(db, quien: str):
    from app import models

    consulta = db.query(models.User)
    if quien.isdigit():
        user = consulta.filter(models.User.id == int(quien)).first()
    else:
        user = consulta.filter(models.User.correo == quien.strip().lower()).first()
    if user is None:
        raise SystemExit(
            f"No existe el usuario {quien!r}. `--aprobado-por` tiene que ser alguien "
            "real: la carga queda firmada con su id."
        )
    return user


def cargar(
    db,
    receta,
    *,
    team_id: int,
    archivo: str | None,
    salida: str,
    aprobado_por: str,
    acepto_ventana: bool = False,
) -> None:
    carpeta = carpeta_de(salida, team_id=team_id, slug=receta.SLUG)
    ruta = os.path.join(carpeta, "pendiente.json")
    if not os.path.exists(ruta):
        raise SystemExit(
            f"No hay revisión pendiente para {receta.SLUG} en la cuenta {team_id}. "
            "Corre primero --revisar y mira el HTML: sin eso no se carga."
        )
    with open(ruta, encoding="utf-8") as fh:
        pendiente = json.load(fh)

    archivo = archivo or pendiente["archivo"]
    if not os.path.exists(archivo):
        raise SystemExit(f"No encuentro el archivo revisado: {archivo}")
    huella = base.hash_archivo(archivo)
    if huella != pendiente["hash_sha256"]:
        raise SystemExit(
            "El archivo cambió después de la revisión (el sha256 no coincide). "
            "Vuelve a correr --revisar: lo que se aprueba es un archivo concreto, "
            "no un nombre de archivo."
        )

    user = _usuario(db, aprobado_por)

    catalogo = receta.leer(archivo)
    actual = base.estado_actual(db, team_id=team_id, slug=catalogo.slug)
    diff = base.comparar(actual, catalogo)

    if not base.hay_algo_que_hacer(diff):
        print(
            f"[{catalogo.slug}] la base ya dice exactamente lo que dice el archivo. "
            "No se escribió nada (y no se duplicó nada)."
        )
        return
    if base.firma(diff) != pendiente.get("firma"):
        raise SystemExit(
            "La base cambió desde la revisión: el diff que se aplicaría ya no es el "
            "que se aprobó. Corre --revisar otra vez y mira el HTML nuevo."
        )

    ventana = base.bots_en_ventana(db, team_id=team_id)
    if ventana and not acepto_ventana:
        cuales = ", ".join(
            f"#{b['bot_id']} {b['nombre']}"
            + (f" (hasta {b['hasta']})" if b["hasta"] else " (sin fecha de cierre anotada)")
            for b in ventana
        )
        raise SystemExit(
            "La ventana de observación del fallback sigue abierta para esta cuenta: "
            f"{cuales}.\n"
            "Mientras los dos motores están vivos, un turno puede caer al motor viejo y "
            "cotizar con los precios del JSON que va en la imagen: si cargas esto ahora, "
            "la base y el JSON dejan de decir lo mismo y nadie se entera hasta que un "
            "cliente reclame.\n"
            "Lo normal es congelar el tarifario hasta que cierre la ventana. Si el cambio "
            "no puede esperar, se hace en los dos lados (importador + regenerar el JSON y "
            "desplegar), se anota en la BITÁCORA, y se repite este comando con "
            "--acepto-ventana-abierta."
        )

    producto, carga = base.aplicar(
        db,
        team_id=team_id,
        deseado=catalogo,
        diff=diff,
        archivo=archivo,
        hash_sha256=huella,
        aprobado_por_user_id=user.id,
    )
    print(
        f"[{catalogo.slug}] cargado: producto_id={producto.id} · "
        f"+{carga.filas_nuevas} nuevas · ~{carga.filas_cambiadas} cambiadas · "
        f"-{carga.filas_retiradas} retiradas (activo=false) · carga_id={carga.id} · "
        f"aprobado_por_user_id={user.id}"
    )
    if ventana:
        print(
            f"[{catalogo.slug}] se cargó con la ventana abierta: hay que regenerar el "
            "JSON del motor viejo y desplegarlo, o el bot cotizará distinto según quién "
            "responda el turno."
        )


# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("slug", choices=sorted(RECETAS))
    p.add_argument("--team-id", type=int, required=True, help="cuenta dueña del producto")
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument(
        "--revisar", action="store_true",
        help="arma el diff en HTML y no toca la base (obligatorio antes de cargar)",
    )
    grupo.add_argument(
        "--cargar", action="store_true", help="aplica lo aprobado en la revisión anterior"
    )
    p.add_argument("--archivo", help="ruta del archivo del cliente (por defecto, el de la receta)")
    p.add_argument(
        "--aprobado-por",
        help="correo o id del usuario que aprueba la carga. Obligatorio con --cargar",
    )
    p.add_argument(
        "--acepto-ventana-abierta", action="store_true",
        help="cargar aunque la ventana de observación del fallback siga abierta",
    )
    p.add_argument("--salida", default=SALIDA, help="carpeta donde se deja la revisión")
    args = p.parse_args(argv)

    receta = RECETAS[args.slug]
    archivo = args.archivo or getattr(receta, "ARCHIVO_POR_DEFECTO", None)
    if args.revisar and not archivo:
        raise SystemExit("Falta --archivo: esta receta no tiene uno por defecto.")
    if args.revisar and not os.path.exists(archivo):
        raise SystemExit(f"No encuentro el archivo: {archivo}")
    if args.cargar and not args.aprobado_por:
        raise SystemExit(
            "Falta --aprobado-por: la carga queda firmada en bot_producto_cargas "
            "con el id de quien la aprobó."
        )

    db = abrir_sesion()
    try:
        if args.revisar:
            revisar(db, receta, team_id=args.team_id, archivo=archivo, salida=args.salida)
        else:
            cargar(
                db, receta,
                team_id=args.team_id,
                archivo=args.archivo,
                salida=args.salida,
                aprobado_por=args.aprobado_por,
                acepto_ventana=args.acepto_ventana_abierta,
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
