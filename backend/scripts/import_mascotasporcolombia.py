"""Importa los reportes de mascotasporcolombia.com (línea de comandos).

Wrapper delgado: toda la lógica vive en `app/services/mascotasporcolombia.py`,
que también usa el botón "Sincronizar lista" del panel. Aquí solo se parsean los
flags, se llama a la importación y se imprimen los contadores.

Uso local:
    docker compose -p wati exec -T backend python \
        scripts/import_mascotasporcolombia.py --dry-run
    docker compose -p wati exec -T backend python \
        scripts/import_mascotasporcolombia.py

En RDS (misma imagen del backend, dentro de la VPC):
    aws ecs run-task --region sa-east-1 \
      --cluster multiagente-cluster \
      --task-definition multiagente-backend \
      --launch-type FARGATE \
      --network-configuration 'awsvpcConfiguration={subnets=[subnet-07829afbd13c5bb8f,subnet-00f56d6ce74d72a2e],securityGroups=[sg-0499ec72831ef7da9],assignPublicIp=ENABLED}' \
      --overrides '{"containerOverrides":[{"name":"multiagente-backend","command":["python","scripts/import_mascotasporcolombia.py"]}]}'

ENV / flags:
    MPC_DESDE     (--desde)    solo fichas publicadas desde esta fecha  [2026-08-10]
    MPC_DRY_RUN=1 (--dry-run)  muestra el mapeo sin escribir en la BD
    MPC_LIMITE    (--limite)   procesa como máximo N fichas (pruebas)
    MPC_PAUSA     (--pausa)    segundos entre requests                  [1.0]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services import mascotas as svc  # type: ignore
from app.services import mascotasporcolombia as mpc  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("import_mpc")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Importa reportes de mascotasporcolombia.com"
    )
    parser.add_argument("--dry-run", action="store_true",
                        default=os.getenv("MPC_DRY_RUN") == "1",
                        help="muestra qué importaría, sin escribir en la BD")
    parser.add_argument("--desde", default=os.getenv("MPC_DESDE", mpc.DESDE_DEFAULT),
                        help=f"solo fichas publicadas desde esta fecha (default {mpc.DESDE_DEFAULT})")
    parser.add_argument("--limite", type=int, default=os.getenv("MPC_LIMITE") or None,
                        help="procesa como máximo N fichas (pruebas)")
    parser.add_argument("--pausa", type=float, default=os.getenv("MPC_PAUSA") or mpc.PAUSA_DEFAULT,
                        help=f"segundos entre requests (default {mpc.PAUSA_DEFAULT})")
    args = parser.parse_args()

    desde = svc._parse_fecha(args.desde)
    if desde is None:
        logger.error("--desde debe tener el formato AAAA-MM-DD")
        return 2

    inicio = datetime.utcnow()
    logger.info(
        "importación de %s iniciada (desde=%s dry_run=%s limite=%s pausa=%ss)",
        mpc.SOURCE, desde.isoformat(), args.dry_run, args.limite, args.pausa,
    )
    try:
        conteo = mpc.sincronizar(
            desde=desde,
            dry_run=args.dry_run,
            limite=int(args.limite) if args.limite else None,
            pausa=float(args.pausa),
        )
    except Exception:
        logger.exception("la importación falló")
        return 1

    duracion = (datetime.utcnow() - inicio).total_seconds()
    logger.info(
        "importación terminada en %.0fs — fichas vistas=%s, descartadas por "
        "fecha=%s; registros %s=%s, actualizados=%s, sin cambios=%s, "
        "fallidos=%s; por tipo: perdidas=%s, encontradas=%s",
        duracion, conteo["vistas"], conteo["filtradas"],
        "que se importarían" if args.dry_run else "creados", conteo["creadas"],
        conteo["actualizadas"], conteo["sin_cambios"], conteo["fallidas"],
        conteo["perdidas"], conteo["encontradas"],
    )
    if args.dry_run:
        logger.info("dry-run: no se escribió nada en la base de datos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
