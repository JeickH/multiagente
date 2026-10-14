"""Horario de atención de los asesores (bot 3 de Arranquemos Pues).

Puro: no toca la base ni la red. Lo usa el motor para decirle al cliente, en
cada traspaso, si lo atienden ya o cuándo («Te escriben {cuando}»).

Config (`llm_config.horario_asesores`)::

    {"tz": "America/Bogota",
     "dias": {"lun": ["08:00", "18:00"], "mar": [...], "mie": [...],
              "jue": [...], "vie": [...], "sab": ["08:00", "13:00"]}}

- Días: ``lun mar mie jue vie sab dom`` (se aceptan también con tilde y con
  la palabra completa: «miércoles», «sábado»). Un día sin entrada está cerrado.
- Cada día es ``[apertura, cierre)``: a las 18:00 en punto ya está cerrado.
  Un rango mal escrito (hora inválida, cierre <= apertura) cuenta como cerrado:
  mejor decir «mañana» de más que prometer a alguien que lo atienden ya.
- **Festivos: no se contemplan.** Un lunes festivo cuenta como lunes hábil. Si
  el CEO quiere festivos, van como lista de fechas en la config; hoy no.
- Zona horaria: `zoneinfo`. Si el sistema no trae la base de zonas (la imagen
  `python:3.11-slim` puede no tener `tzdata`), «America/Bogota» cae a UTC−5
  fijo, que es exacto: Colombia no tiene horario de verano. Otra zona que no
  se encuentre también cae a UTC−5 (es la única que usa este negocio).
- ``ahora_utc`` sin zona se toma como UTC (así guarda las fechas el backend).
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Dict, Optional, Tuple

try:  # pragma: no cover - depende del sistema
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment]

__all__ = ["en_horario", "cuando_atienden"]

_TZ_POR_DEFECTO = "America/Bogota"
_UTC_MENOS_5 = timezone(timedelta(hours=-5), "COT")

#: weekday() de Python → clave de la config.
_CLAVES = ("lun", "mar", "mie", "jue", "vie", "sab", "dom")
_NOMBRES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_ALIAS = {
    "lunes": "lun", "martes": "mar", "miercoles": "mie", "jueves": "jue",
    "viernes": "vie", "sabado": "sab", "domingo": "dom",
}
_HORA_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def _sin_tildes(texto: str) -> str:
    base = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _zona(cfg: dict) -> tzinfo:
    nombre = str((cfg or {}).get("tz") or _TZ_POR_DEFECTO)
    if ZoneInfo is not None:
        try:
            return ZoneInfo(nombre)
        except Exception:
            # ZoneInfoNotFoundError, ValueError, KeyError… y también OSError
            # (`IsADirectoryError` con «America» en una imagen sin tzdata).
            # Colombia no tiene horario de verano: UTC−5 es exacto.
            pass
    return _UTC_MENOS_5


def _hora(texto: object) -> Optional[time]:
    m = _HORA_RE.match(str(texto or ""))
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h == 24 and mi == 0:
        return time.max
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return None
    return time(h, mi)


def _dias(cfg: dict) -> Dict[str, Tuple[time, time]]:
    """{clave_dia: (apertura, cierre)} solo con los días bien escritos."""
    fuera: Dict[str, Tuple[time, time]] = {}
    crudos = (cfg or {}).get("dias")
    if not isinstance(crudos, dict):
        return fuera
    for nombre, rango in crudos.items():
        clave = _sin_tildes(str(nombre))
        clave = _ALIAS.get(clave, clave[:3])
        if clave not in _CLAVES:
            continue
        if not isinstance(rango, (list, tuple)) or len(rango) != 2:
            continue
        abre, cierra = _hora(rango[0]), _hora(rango[1])
        if abre is None or cierra is None or cierra <= abre:
            continue
        fuera[clave] = (abre, cierra)
    return fuera


def _local(ahora_utc: datetime, cfg: dict) -> datetime:
    if ahora_utc.tzinfo is None:
        ahora_utc = ahora_utc.replace(tzinfo=timezone.utc)
    return ahora_utc.astimezone(_zona(cfg))


def _formato_hora(t: time) -> str:
    """08:00 → «8:00 a.m.», 13:00 → «1:00 p.m.», 12:00 → «12:00 m.»."""
    if t.hour == 12 and t.minute == 0:
        return "12:00 m."
    sufijo = "a.m." if t.hour < 12 else "p.m."
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {sufijo}"


def en_horario(ahora_utc: datetime, cfg_horario: dict) -> bool:
    """¿Hay asesores atendiendo en este instante?"""
    local = _local(ahora_utc, cfg_horario)
    rango = _dias(cfg_horario).get(_CLAVES[local.weekday()])
    if rango is None:
        return False
    abre, cierra = rango
    return abre <= local.time() < cierra


def cuando_atienden(ahora_utc: datetime, cfg_horario: dict) -> str:
    """Cuándo lo atienden, listo para «Te escriben {cuando}».

    - En horario: «en un momento».
    - Hoy todavía no abren: «hoy a partir de las 8:00 a.m.».
    - El próximo día con horario es mañana: «mañana a partir de las 8:00 a.m.».
    - Más adelante: «el lunes a partir de las 8:00 a.m.» (día en español).
    - Sin ningún día configurado: «en el próximo horario de atención».
    """
    if en_horario(ahora_utc, cfg_horario):
        return "en un momento"
    local = _local(ahora_utc, cfg_horario)
    dias = _dias(cfg_horario)
    hoy_rango = dias.get(_CLAVES[local.weekday()])
    if hoy_rango is not None and local.time() < hoy_rango[0]:
        return f"hoy a partir de las {_formato_hora(hoy_rango[0])}"
    for delta in range(1, 8):
        dia: date = local.date() + timedelta(days=delta)
        rango = dias.get(_CLAVES[dia.weekday()])
        if rango is None:
            continue
        cuando = "mañana" if delta == 1 else f"el {_NOMBRES[dia.weekday()]}"
        return f"{cuando} a partir de las {_formato_hora(rango[0])}"
    return "en el próximo horario de atención"
