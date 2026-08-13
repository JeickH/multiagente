"""Job diario del sprint "Ayuda a Cali": cruce perdidas ↔ encontradas.

Corre todos los días a las **12:00 hora Colombia** (17:00 UTC) y compara cada
reporte de mascota perdida activo contra cada mascota encontrada activa, con el
mismo scoring que usa el bot en vivo. Las coincidencias por encima del umbral
quedan en `mascota_coincidencias` y se ven en el panel de la cuenta.

Existe porque la conversación no alcanza a ver el futuro: cuando una familia
escribe, su mascota puede no estar reportada todavía. Este cruce revisa cada día
todo contra todo, así que un hallazgo de mañana se conecta con una búsqueda de
la semana pasada.

Idempotente: un par ya registrado se actualiza (no se duplica) y **conserva el
estado** que le puso el equipo — una coincidencia descartada no vuelve a "nueva".

Uso:
    docker compose -p wati exec -T backend python scripts/job_coincidencias_mascotas.py

En producción lo dispara EventBridge Scheduler → ECS RunTask con este mismo
comando (ver BITACORA, sprint "Ayuda a Cali").

ENV opcionales:
    MASCOTAS_UMBRAL_COINCIDENCIA  (default 6)
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app.services import mascotas as svc  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("job_coincidencias")


def main() -> int:
    try:
        umbral = int(os.getenv("MASCOTAS_UMBRAL_COINCIDENCIA", "") or svc.UMBRAL_COINCIDENCIA)
    except ValueError:
        umbral = svc.UMBRAL_COINCIDENCIA

    inicio = datetime.utcnow()
    logger.info("cruce de mascotas iniciado (umbral=%s)", umbral)

    db = SessionLocal()
    try:
        stats = svc.cruzar_reportes(db, umbral=umbral)
    except Exception:
        # Detalle completo solo en el log (regla de seguridad #6). El job
        # termina en != 0 para que el fallo se vea en CloudWatch.
        logger.exception("cruce de mascotas falló")
        return 1
    finally:
        db.close()

    duracion = (datetime.utcnow() - inicio).total_seconds()
    logger.info(
        "cruce terminado en %.1fs: %s perdidas x %s encontradas = %s pares; "
        "%s coincidencias nuevas, %s actualizadas",
        duracion, stats["perdidas"], stats["encontradas"],
        stats["pares_evaluados"], stats["nuevas"], stats["actualizadas"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
