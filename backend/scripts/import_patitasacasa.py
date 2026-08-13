"""Importa los reportes de patitasacasa.com (línea de comandos).

Wrapper delgado: la lógica vive en `app/services/patitasacasa.py`, que también
usa el botón "Sincronizar lista" del panel.

Uso local:
    docker compose -p wati exec -T backend python scripts/import_patitasacasa.py --dry-run
    docker compose -p wati exec -T backend python scripts/import_patitasacasa.py

ENV / flags: ver el docstring del servicio (PAC_DESDE, PAC_DRY_RUN,
PAC_CIUDADES, PAC_PAUSA, PAC_SIN_FOTOS).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services import mascotas as svc  # type: ignore
from app.services import patitasacasa as pac  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("import_pac")


def main() -> int:
    parser = argparse.ArgumentParser(description="Importa reportes de patitasacasa.com")
    parser.add_argument("--dry-run", action="store_true",
                        default=os.getenv("PAC_DRY_RUN") == "1",
                        help="muestra qué importaría, sin escribir en la BD")
    parser.add_argument("--desde", default=os.getenv("PAC_DESDE", pac.DESDE_DEFAULT),
                        help=f"solo reportes desde esta fecha (default {pac.DESDE_DEFAULT})")
    parser.add_argument("--ciudades", default=os.getenv("PAC_CIUDADES", ""),
                        help="lista separada por comas (default: todas)")
    parser.add_argument("--pausa", type=float, default=os.getenv("PAC_PAUSA") or pac.PAUSA_DEFAULT,
                        help=f"segundos entre requests (default {pac.PAUSA_DEFAULT})")
    parser.add_argument("--sin-fotos", action="store_true",
                        default=os.getenv("PAC_SIN_FOTOS") == "1",
                        help="no descarga las imágenes")
    args = parser.parse_args()

    desde = svc._parse_fecha(args.desde)
    if desde is None:
        logger.error("--desde debe tener el formato AAAA-MM-DD")
        return 2
    ciudades = [c.strip() for c in args.ciudades.split(",") if c.strip()] or None

    inicio = datetime.utcnow()
    logger.info("importación de patitasacasa iniciada (desde=%s dry_run=%s)",
                desde.isoformat(), args.dry_run)
    try:
        conteo = pac.sincronizar(
            desde=desde, dry_run=args.dry_run, ciudades=ciudades,
            pausa=float(args.pausa), sin_fotos=args.sin_fotos,
        )
    except Exception:
        logger.exception("la importación falló")
        return 1

    duracion = (datetime.utcnow() - inicio).total_seconds()
    logger.info(
        "terminada en %.0fs — vistas=%s, descartadas por fecha=%s, %s=%s "
        "(perdidas=%s, encontradas=%s), actualizadas=%s, sin cambios=%s, "
        "fallidas=%s, fotos guardadas=%s",
        duracion, conteo["vistas"], conteo["filtradas"],
        "se crearían" if args.dry_run else "creadas", conteo["creadas"],
        conteo["perdidas"], conteo["encontradas"], conteo["actualizadas"],
        conteo["sin_cambios"], conteo["fallidas"], conteo["fotos"],
    )
    if args.dry_run:
        logger.info("dry-run: no se escribió nada en la base de datos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
