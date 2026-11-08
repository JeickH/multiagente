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
- **Festivos: `en_horario` y `cuando_atienden` no los contemplan** (un lunes
  festivo cuenta como lunes hábil para el aviso de ausencia del bot 3). Las
  **franjas de llamada** del bot D sí: ver abajo.
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
import logging
from dataclasses import dataclass
from typing import Dict, FrozenSet, Iterable, List, Mapping, Optional, Tuple

logger = logging.getLogger(__name__)

try:  # pragma: no cover - depende del sistema
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment]

__all__ = [
    "en_horario", "cuando_atienden", "Franja", "festivo",
    "proximas_franjas_llamada", "franja_de_llamada_valida", "cuando_de_la_franja",
]

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


# ---------------------------------------------------------------------------
# Franjas de llamada del bot D (Sprint 36, puerta 2; diseño de seguridad 3.2)
# ---------------------------------------------------------------------------
#
# Las arma SIEMPRE el servidor, nunca el guion ni el modelo: el modelo solo ve
# la lista ya escrita y elige un número (1..5). Reglas del CEO (spec del bot D):
#
#   - Bloques de 2 horas desde la apertura de cada día del horario; el último
#     se corta en el cierre. Con L–V 8–18 y sábado 8–13: 8–10, 10–12, 12–2,
#     2–4 y 4–6 (sábado 8–10, 10–12 y 12–1). Domingo cerrado.
#   - Se ofrecen las 5 siguientes a las que les quede al menos 1 hora por
#     delante. Además el inicio tiene que estar a más de 30 minutos (el mismo
#     margen con que el handler revalida): así lo que se ofrece y lo que se
#     acepta son la misma regla y una franja nunca rebota en bucle.
#   - Nunca en festivo; un año sin lista de festivos no ofrece nada ese día
#     (y deja un warning, una vez por año).
#   - Nunca entre las 11 p.m. y las 5 a.m. de Colombia, aunque la config del
#     horario lo permitiera.
#   - Una franja llena (tantas llamadas pendientes como cupo) no se ofrece.
#
# Todo entra y sale en UTC sin zona, como lo guarda la base.

BLOQUE_LLAMADA = timedelta(hours=2)
#: El inicio de la franja tiene que estar a más de esto de ahora.
MARGEN_INICIO = timedelta(minutes=30)
#: Y al final de la franja le tiene que quedar al menos esto por delante.
MARGEN_FIN = timedelta(hours=1)
FRANJAS_POR_DEFECTO = 5
#: Hasta dónde se busca (un festivo largo no deja al bot sin franjas, y un año
#: sin festivos no lo pone a recorrer el calendario).
DIAS_DE_BUSQUEDA = 14
_SILENCIO_DESDE = 23
_SILENCIO_HASTA = 5

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
)

#: Años sin festivos ya avisados en el log (un warning por año y proceso).
_ANIOS_AVISADOS: set = set()


@dataclass(frozen=True)
class Franja:
    """Una franja de llamada. `inicio`/`fin` en UTC sin zona."""

    inicio: datetime
    fin: datetime


def _festivos_por_defecto() -> Mapping[int, FrozenSet[date]]:
    from app.data.festivos_colombia import FESTIVOS

    return FESTIVOS


def festivo(dia: date, festivos: Optional[Mapping[int, Iterable[date]]] = None) -> Optional[bool]:
    """¿`dia` es festivo? None si su año no tiene lista (no se sabe)."""
    tabla = _festivos_por_defecto() if festivos is None else festivos
    del_anio = tabla.get(dia.year)
    if del_anio is None:
        if dia.year not in _ANIOS_AVISADOS:
            _ANIOS_AVISADOS.add(dia.year)
            logger.warning(
                "horario: sin festivos configurados para %s; ese año no se "
                "ofrecen franjas de llamada", dia.year,
            )
        return None
    return dia in set(del_anio)


def _a_utc(local: datetime) -> datetime:
    return local.astimezone(timezone.utc).replace(tzinfo=None)


def _como_utc(valor: datetime) -> datetime:
    """UTC con zona, venga con zona o sin ella (sin zona = UTC)."""
    if valor.tzinfo is None:
        return valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc)


def _bloques_del_dia(dia: date, cfg: dict) -> List[Tuple[datetime, datetime]]:
    """Los bloques de 2 h de ese día, en hora local con zona."""
    rango = _dias(cfg).get(_CLAVES[dia.weekday()])
    if rango is None:
        return []
    zona = _zona(cfg)
    abre, cierra = rango
    inicio = datetime.combine(dia, abre).replace(tzinfo=zona)
    fin_dia = (
        datetime.combine(dia + timedelta(days=1), time(0, 0)).replace(tzinfo=zona)
        if cierra == time.max else datetime.combine(dia, cierra).replace(tzinfo=zona)
    )
    bloques = []
    while inicio < fin_dia:
        fin = min(inicio + BLOQUE_LLAMADA, fin_dia)
        bloques.append((inicio, fin))
        inicio = fin
    return bloques


def _toca_el_silencio(inicio_local: datetime, fin_local: datetime) -> bool:
    """¿La franja pisa algo de 11 p.m. a 5 a.m.? Se mira hora por hora."""
    cursor = inicio_local
    while cursor < fin_local:
        if cursor.hour >= _SILENCIO_DESDE or cursor.hour < _SILENCIO_HASTA:
            return True
        cursor = (cursor + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return False


def franja_de_llamada_valida(
    inicio_utc: datetime,
    fin_utc: datetime,
    ahora_utc: datetime,
    cfg_horario: dict,
    festivos: Optional[Mapping[int, Iterable[date]]] = None,
) -> Tuple[bool, str]:
    """La revalidación del handler (diseño 3.2), la misma regla con que se
    ofrecen: es exactamente un bloque del horario de ese día, no es festivo
    (ni de un año sin lista), no toca 23–05 h, empieza a más de 30 min y le
    queda al menos 1 h. Devuelve `(ok, motivo)`; el motivo es para el log y
    para el modelo, sin datos de nadie."""
    ini = _como_utc(inicio_utc)
    fin = _como_utc(fin_utc)
    ahora = _como_utc(ahora_utc)
    if fin <= ini:
        return False, "franja mal formada"
    zona = _zona(cfg_horario)
    ini_local, fin_local = ini.astimezone(zona), fin.astimezone(zona)
    es_festivo = festivo(ini_local.date(), festivos)
    if es_festivo is None:
        return False, "año sin festivos configurados"
    if es_festivo:
        return False, "festivo"
    if (ini_local, fin_local) not in _bloques_del_dia(ini_local.date(), cfg_horario):
        return False, "fuera del horario"
    if _toca_el_silencio(ini_local, fin_local):
        return False, "horario de silencio"
    if ini <= ahora + MARGEN_INICIO or fin - ahora < MARGEN_FIN:
        return False, "franja vencida"
    return True, ""


def proximas_franjas_llamada(
    ahora_utc: datetime,
    cfg_horario: dict,
    festivos: Optional[Mapping[int, Iterable[date]]] = None,
    ocupacion: Optional[Mapping[datetime, int]] = None,
    *,
    cupo: int = 1,
    cuantas: int = FRANJAS_POR_DEFECTO,
) -> List[Franja]:
    """Las próximas `cuantas` franjas que se le pueden ofrecer a alguien.

    `ocupacion`: inicio (UTC sin zona) → llamadas pendientes en esa franja. Con
    tantas como `cupo`, la franja está llena y no se ofrece.
    """
    ocupacion = ocupacion or {}
    cupo = max(1, int(cupo or 1))
    zona = _zona(cfg_horario)
    hoy = _como_utc(ahora_utc).astimezone(zona).date()
    salida: List[Franja] = []
    for delta in range(DIAS_DE_BUSQUEDA + 1):
        dia = hoy + timedelta(days=delta)
        for ini_local, fin_local in _bloques_del_dia(dia, cfg_horario):
            inicio, fin = _a_utc(ini_local), _a_utc(fin_local)
            ok, _ = franja_de_llamada_valida(inicio, fin, ahora_utc, cfg_horario, festivos)
            if not ok or int(ocupacion.get(inicio, 0)) >= cupo:
                continue
            salida.append(Franja(inicio=inicio, fin=fin))
            if len(salida) >= cuantas:
                return salida
    return salida


def _hora_corta(t: datetime) -> Tuple[str, str]:
    """(número, sufijo): 8:00 → ("8", "a.m."), 12:00 → ("12", "m."),
    14:30 → ("2:30", "p.m.")."""
    h = t.hour % 12 or 12
    numero = f"{h}" if t.minute == 0 else f"{h}:{t.minute:02d}"
    if t.hour == 12 and t.minute == 0:
        return numero, "m."
    return numero, "a.m." if t.hour < 12 else "p.m."


def _rango(ini: datetime, fin: datetime, de: str = "de", a: str = "a") -> str:
    """«de 8 a 10 a.m.», «de 10 a 12 m.», «de 12 a 2 p.m.», «de 11 a.m. a 1 p.m.»."""
    n1, s1 = _hora_corta(ini)
    n2, s2 = _hora_corta(fin)
    if s1 == s2 or (s1 == "m." and s2 == "p.m."):
        return f"{de} {n1} {a} {n2} {s2}"
    if s2 == "m.":
        return f"{de} {n1} {a} 12 m."
    return f"{de} {n1} {s1} {a} {n2} {s2}"


def _dia_largo(dia: date, hoy: date) -> str:
    if dia == hoy:
        return "hoy"
    nombre = _NOMBRES[dia.weekday()]
    if dia == hoy + timedelta(days=1):
        return f"mañana {nombre}"
    return f"el {nombre} {dia.day} de {_MESES[dia.month - 1]}"


def etiquetas_de_franjas(
    franjas: List[Franja], ahora_utc: datetime, cfg_horario: dict
) -> List[str]:
    """Cómo se le escribe cada franja en la lista, en orden. El día va completo
    la primera vez que aparece y corto las siguientes: «Hoy de 4 a 6 p.m.»,
    «Mañana miércoles de 8 a 10 a.m.», «Mañana de 10 a 12 m.», «Lunes 16 de
    noviembre de 8 a 10 a.m.», «Lunes de 10 a 12 m.»."""
    zona = _zona(cfg_horario)
    hoy = _como_utc(ahora_utc).astimezone(zona).date()
    vistos: set = set()
    salida = []
    for f in franjas:
        ini = _como_utc(f.inicio).astimezone(zona)
        fin = _como_utc(f.fin).astimezone(zona)
        dia = ini.date()
        if dia == hoy:
            nombre = "hoy"
        elif dia in vistos:
            nombre = "mañana" if dia == hoy + timedelta(days=1) else _NOMBRES[dia.weekday()]
        else:
            nombre = _dia_largo(dia, hoy)
            if nombre.startswith("el "):
                nombre = nombre[3:]
        vistos.add(dia)
        texto = f"{nombre} {_rango(ini, fin)}"
        salida.append(texto[:1].upper() + texto[1:])
    return salida


def cuando_de_la_franja(franja: Franja, ahora_utc: datetime, cfg_horario: dict) -> str:
    """Para la confirmación: «mañana miércoles entre 8 y 10 a.m.», «hoy entre
    4 y 6 p.m.», «el lunes 16 de noviembre entre 8 y 10 a.m.»."""
    zona = _zona(cfg_horario)
    hoy = _como_utc(ahora_utc).astimezone(zona).date()
    ini = _como_utc(franja.inicio).astimezone(zona)
    fin = _como_utc(franja.fin).astimezone(zona)
    return f"{_dia_largo(ini.date(), hoy)} {_rango(ini, fin, de='entre', a='y')}"


def rango_de_la_franja(franja: Franja, cfg_horario: dict) -> str:
    """Para la lista de la asesora y las notas internas: «mié 18 nov · de 8 a
    10 a.m.» (sin «hoy» ni «mañana», que dependen de cuándo se lea)."""
    zona = _zona(cfg_horario)
    ini = _como_utc(franja.inicio).astimezone(zona)
    fin = _como_utc(franja.fin).astimezone(zona)
    dia = ini.date()
    return f"{_NOMBRES[dia.weekday()]} {dia.day} de {_MESES[dia.month - 1]}, {_rango(ini, fin)}"
