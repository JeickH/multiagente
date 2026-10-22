"""Horario de silencio de los recordatorios del bot (CEO, 2026-10-21).

Ningún recordatorio al cliente sale entre las 11:00 p.m. y las 5:00 a.m. de
Colombia. Se aplica al agendar (`bot_runner._programar`) y otra vez al enviar
(`bot_runner._procesar_silencio`), para lo agendado antes de la regla o con el
tick atrasado.

`ACTIVO` existe para las pruebas: la suite corre a cualquier hora (y el CI en
UTC), y una prueba que procesa un recordatorio no puede fallar por la hora del
reloj. `conftest.py` lo apaga para toda la suite; las pruebas del silencio lo
prenden con un reloj fijo.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

ACTIVO = True
DESDE = 23     # 11:00 p.m.
HASTA = 5      # 5:00 a.m.
_TZ_CO = timezone(timedelta(hours=-5))


def ahora() -> datetime:
    """UTC sin marcar, como lo guarda la tabla. Las pruebas lo reemplazan."""
    return datetime.utcnow()


def en_silencio(cuando: datetime) -> bool:
    """¿`cuando` (UTC sin marcar) cae en el horario de silencio de Colombia?"""
    if not ACTIVO:
        return False
    hora = (cuando + _TZ_CO.utcoffset(None)).hour
    return hora >= DESDE or hora < HASTA


def fuera_del_silencio(cuando: datetime, desde: Optional[datetime] = None) -> datetime:
    """Corre un recordatorio que cae entre las 11 p.m. y las 5 a.m. al borde
    permitido **más cercano**: las 10:59 p.m. de esa noche o las 5:00 a.m.
    siguientes. Nunca a una hora que ya pasó: si las 10:59 p.m. quedaron
    atrás, va a las 5:00 a.m. Fuera del silencio no se toca.
    """
    if not en_silencio(cuando):
        return cuando
    offset = _TZ_CO.utcoffset(None)
    local = cuando + offset
    if local.hour >= DESDE:
        antes = local.replace(hour=DESDE - 1, minute=59, second=0, microsecond=0)
        despues = (local + timedelta(days=1)).replace(hour=HASTA, minute=0, second=0, microsecond=0)
    else:
        antes = (local - timedelta(days=1)).replace(hour=DESDE - 1, minute=59, second=0, microsecond=0)
        despues = local.replace(hour=HASTA, minute=0, second=0, microsecond=0)
    minimo = (desde or ahora()) + offset + timedelta(minutes=1)
    validos = [c for c in (antes, despues) if c >= minimo] or [despues]
    elegido = min(validos, key=lambda c: abs((c - local).total_seconds()))
    return elegido - offset
