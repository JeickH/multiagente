"""Borra a mano los bots de demo inactivos (Sprint 33, #638 / #642).

Lo mismo que hace el tick una vez por hora (`services/limpieza_demos.py`):
borra el `Bot` y los `bot_productos` de las demos sin uso en las últimas
`--horas` (default `DEMO_BOT_RETENCION_HORAS`, 48; nunca menos de 6), después
de copiar sus productos y su consumo a la fila de `demos`. Nunca toca `leads`
ni borra filas de `demos`.

**Por defecto SIMULA**: dice qué borraría (clave `borraria`) y no escribe nada.
Solo borra con `--ejecutar` o con la env `LIMPIEZA_EJECUTAR=1` (clave
`borradas`).

Opciones (o su env, para cuando no se pueden pasar argumentos):
    --ejecutar      LIMPIEZA_EJECUTAR=1   borra de verdad
    --horas N       LIMPIEZA_HORAS=N      horas sin uso; mínimo 6
    --lote N        LIMPIEZA_LOTE=N       demos por corrida; 1 a 1.000 (200)

Local (el proyecto de compose se llama `wati`):
    docker compose -p wati exec -T backend python scripts/limpiar_demos.py
    docker compose -p wati exec -T backend python scripts/limpiar_demos.py --ejecutar

Producción (RDS) con ECS run-task, siempre en sa-east-1. Con `rds_exec.sh`
(manda este archivo como `python -c` en la task-def del servicio; las opciones
van por env):
    # 1. simulación: revisar `candidatas`, `borraria` y `motivos_saltadas`
    ./backend/scripts/rds_exec.sh backend/scripts/limpiar_demos.py
    # 2. ejecución
    ./backend/scripts/rds_exec.sh backend/scripts/limpiar_demos.py LIMPIEZA_EJECUTAR=1
    # (opcional) LIMPIEZA_HORAS=72 LIMPIEZA_LOTE=500
La salida queda en CloudWatch (`/ecs/multiagente-backend`, stream de la task).
Si la imagen desplegada ya trae este script, también vale un run-task con
`command: ["python", "scripts/limpiar_demos.py"]` (y `"--ejecutar"` al final
para borrar).

Salida: una línea JSON con conteos e ids internos de demos. Sin PII.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# `rds_exec.sh` manda este archivo como el cuerpo de un `python -c`, donde
# `__file__` no existe; ahí el código ya corre desde /app dentro del contenedor.
_RAIZ = (
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if "__file__" in globals()
    else "/app"
)
sys.path.insert(0, _RAIZ)

from app.database import SessionLocal  # type: ignore  # noqa: E402
from app.services import limpieza_demos  # type: ignore  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Borra los bots de demo inactivos "
                                     "(por defecto solo simula).")
    parser.add_argument("--ejecutar", action="store_true",
                        default=os.getenv("LIMPIEZA_EJECUTAR") == "1",
                        help="borra de verdad (sin esto solo simula)")
    parser.add_argument("--horas", type=float,
                        default=float(os.getenv("LIMPIEZA_HORAS") or 0) or None,
                        help="horas sin uso, mínimo 6 (default DEMO_BOT_RETENCION_HORAS o 48)")
    parser.add_argument("--lote", type=int,
                        default=int(os.getenv("LIMPIEZA_LOTE") or limpieza_demos.LOTE_POR_CORRIDA),
                        help="demos por corrida, de 1 a 1.000")
    args = parser.parse_args(argv)
    if args.horas is not None and not args.horas >= limpieza_demos.MIN_RETENCION_HORAS:
        sys.exit("--horas mínimo 6")
    if not 1 <= args.lote <= limpieza_demos.LOTE_MAXIMO:
        sys.exit("--lote entre 1 y 1000")

    simular = not args.ejecutar
    db = SessionLocal()
    try:
        resultado = limpieza_demos.limpiar_bots_demo_inactivos(
            db, horas=args.horas, simular=simular, lote=args.lote,
        )
    finally:
        db.close()
    salida = resultado.resumen()
    if simular:
        salida = {"modo": "simulacion (no se borró nada; usa --ejecutar)",
                  "candidatas": salida["candidatas"], "borraria": salida["borradas"],
                  "saltadas": salida["saltadas"], "demo_ids": salida["demo_ids"],
                  "motivos_saltadas": salida["motivos_saltadas"]}
    else:
        salida = {"modo": "ejecucion", **{k: v for k, v in salida.items() if k != "simular"}}
    print(json.dumps(salida, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] if "__file__" in globals() else []))
