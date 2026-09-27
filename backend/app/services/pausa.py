"""Pausa del servicio por falta de pago.

La cuenta pausada sigue entrando a la plataforma, sigue viendo su bandeja y
sigue pudiendo pagar. Lo que se le corta es lo que le cuesta plata a Gloma y
lo que el cliente usa para vender:

- el **envío manual** desde `/mensajes` (texto, adjuntos, plantillas),
- las **campañas**: no se crean nuevas y las ya programadas no salen,
- el **bot**: los mensajes entrantes se guardan en la bandeja —son del
  cliente y no se pierden— pero el bot no les responde, y sus recordatorios
  agendados no se mandan.

El aviso rojo lo pinta el frontend a partir de `GET /pagos/aviso`.

Cuándo está pausada
-------------------
Lo decide `teams.pausa_servicio` (ver `PAUSA_*` en `models.py`):

- `nunca`: no se pausa. Es el default de todas las cuentas.
- `por_mora`: se pausa sola cuando la factura pendiente más vieja cumple **un
  mes** de vencida. Mes de calendario, en fecha de Colombia, y contado igual
  que el aviso amarillo: el día que vence todavía se puede pagar. Una factura
  vencida el 2 de septiembre pausa la cuenta desde el 3 de octubre. Se
  reanuda sola en cuanto la factura queda pagada o anulada.
- `pausada`: pausada ya, por orden manual, deba o no deba.

Todo se calcula al momento y no se guarda: no hay un job que "pause" cuentas
y que pueda quedarse atrás o fallar a medias. La consulta es una sola fila
(`MIN(due_date)`) por cuenta.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models
# Por el módulo y no `from .facturas import hoy_colombia`: así el "hoy" que
# congelan los tests en `facturas` es el mismo que ve la pausa.
from . import facturas as svc_facturas

logger = logging.getLogger(__name__)

#: Lo que ve quien intenta enviar con la cuenta pausada. Es el mismo texto del
#: aviso rojo, para que el error y el recuadro digan lo mismo.
TEXTO_PAUSADO = (
    "Tus servicios están pausados. Por favor realiza el pago de las facturas "
    "pendientes para reanudar el servicio."
)

#: 402 Payment Required: es exactamente el caso, y lo distingue de un 403 de
#: permisos (que el frontend trata distinto) y de un 409 de cuenta de WhatsApp
#: sin conectar.
STATUS_PAUSADO = 402


def sumar_un_mes(d: date) -> date:
    """El mismo día del mes siguiente, o el último si ese mes es más corto.

    31 de enero → 28 (o 29) de febrero. Sin `dateutil`, que no está en las
    dependencias y no vale la pena sumarla por esto.
    """
    anio, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(d.day, ultimo))


def pausa_por_mora(db: Session, team_id: int, *, hoy: Optional[date] = None) -> bool:
    """¿Hay alguna factura pendiente con un mes o más de mora?"""
    mas_vieja = (
        db.query(func.min(models.Invoice.due_date))
        .filter(
            models.Invoice.team_id == team_id,
            models.Invoice.status == models.INVOICE_PENDIENTE,
        )
        .scalar()
    )
    if mas_vieja is None:
        return False
    return (hoy or svc_facturas.hoy_colombia()) > sumar_un_mes(mas_vieja)


def servicio_pausado(
    db: Session, team_id: Optional[int], *, hoy: Optional[date] = None
) -> bool:
    """¿Esta cuenta tiene el servicio pausado ahora mismo?

    Un valor que no se reconoce cuenta como `nunca`. No debería existir —el
    CHECK de la tabla lo impide—, y si llegara a pasar, cortarle el servicio a
    un cliente por un dato corrupto es peor que dejárselo un rato más.
    """
    if team_id is None:
        return False
    modo = (
        db.query(models.Team.pausa_servicio)
        .filter(models.Team.id == team_id)
        .scalar()
    )
    if modo == models.PAUSA_PAUSADA:
        return True
    if modo == models.PAUSA_POR_MORA:
        return pausa_por_mora(db, team_id, hoy=hoy)
    return False


def exigir_servicio_activo(db: Session, team_id: int) -> None:
    """Portero de los envíos: 402 si la cuenta está pausada."""
    if servicio_pausado(db, team_id):
        logger.info("envío bloqueado: servicio pausado team_id=%s", team_id)
        raise HTTPException(status_code=STATUS_PAUSADO, detail=TEXTO_PAUSADO)
