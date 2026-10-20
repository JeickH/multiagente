"""Calendario determinista para el bot de la demo pública (Sprint 32, #619).

QA #615 midió que 9 de 12 conversaciones de demo calculaban mal el día de la
semana («mañana es domingo» un viernes, «el próximo viernes 24», «el 20 de
noviembre ya pasó») y que a las herramientas les llegaban fechas ISO erradas.
El modelo no hace aritmética de calendario confiable; se le da hecha.

`bloque(hoy)` arma el texto que el motor agrega al bloque «Qué día es hoy»
**solo** para los bots con `llm_config.demo`: los próximos 21 días con el nombre
del día, «mañana», este fin de semana y el próximo, y los festivos de Colombia
(con sus puentes) de los próximos 90 días.

Festivos de Colombia (Ley 51 de 1983, «Ley Emiliani»):
  * fijos: 1 ene, 1 may, 20 jul, 7 ago, 8 dic, 25 dic;
  * trasladables al lunes siguiente: 6 ene, 19 mar, 29 jun, 15 ago, 12 oct,
    1 nov, 11 nov;
  * según la Pascua: Jueves y Viernes Santo (fijos) y Ascensión, Corpus
    Christi y Sagrado Corazón (trasladados al lunes).
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Dict, List, Tuple

DIAS_CORTOS = ("lun", "mar", "mié", "jue", "vie", "sáb", "dom")
DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
MESES_CORTOS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
                "oct", "nov", "dic")

VENTANA_DIAS = 21
VENTANA_FESTIVOS = 90


def pascua(anio: int) -> date:
    """Domingo de Pascua (algoritmo anónimo gregoriano)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return date(anio, mes, dia + 1)


def _al_lunes(d: date) -> date:
    return d + timedelta(days=(7 - d.weekday()) % 7)


@lru_cache(maxsize=16)
def festivos(anio: int) -> Dict[date, str]:
    """Los festivos de Colombia de ese año: {fecha: nombre}."""
    fijos = {
        date(anio, 1, 1): "Año Nuevo",
        date(anio, 5, 1): "Día del Trabajo",
        date(anio, 7, 20): "Día de la Independencia",
        date(anio, 8, 7): "Batalla de Boyacá",
        date(anio, 12, 8): "Inmaculada Concepción",
        date(anio, 12, 25): "Navidad",
    }
    trasladables = {
        date(anio, 1, 6): "Reyes Magos",
        date(anio, 3, 19): "San José",
        date(anio, 6, 29): "San Pedro y San Pablo",
        date(anio, 8, 15): "Asunción de la Virgen",
        date(anio, 10, 12): "Día de la Raza",
        date(anio, 11, 1): "Todos los Santos",
        date(anio, 11, 11): "Independencia de Cartagena",
    }
    p = pascua(anio)
    salida = dict(fijos)
    salida[p - timedelta(days=3)] = "Jueves Santo"
    salida[p - timedelta(days=2)] = "Viernes Santo"
    for d, nombre in trasladables.items():
        salida[_al_lunes(d)] = nombre
    salida[_al_lunes(p + timedelta(days=39))] = "Ascensión del Señor"
    salida[_al_lunes(p + timedelta(days=60))] = "Corpus Christi"
    salida[_al_lunes(p + timedelta(days=68))] = "Sagrado Corazón"
    return salida


def es_festivo(d: date) -> bool:
    return d in festivos(d.year)


def nombre_festivo(d: date) -> str:
    return festivos(d.year).get(d, "")


def etiqueta(d: date) -> str:
    """«vie 16 oct (2026-10-16)»."""
    return f"{DIAS_CORTOS[d.weekday()]} {d.day} {MESES_CORTOS[d.month - 1]} ({d.isoformat()})"


def _corta(d: date) -> str:
    return f"{DIAS_CORTOS[d.weekday()]} {d.day} {MESES_CORTOS[d.month - 1]}"


def fines_de_semana(hoy: date) -> Tuple[Tuple[date, date], Tuple[date, date]]:
    """(este fin de semana, el próximo) como (sábado, domingo).

    Un sábado o domingo, «este fin de semana» es el que está corriendo."""
    if hoy.weekday() == 6:                      # domingo
        sabado = hoy - timedelta(days=1)
    else:
        sabado = hoy + timedelta(days=(5 - hoy.weekday()) % 7)
    este = (sabado, sabado + timedelta(days=1))
    proximo = (sabado + timedelta(days=7), sabado + timedelta(days=8))
    return este, proximo


def puentes(hoy: date, dias: int = VENTANA_FESTIVOS) -> List[Tuple[date, date, str]]:
    """Fines de semana largos por un festivo en lunes (o viernes) en la
    ventana: (primer día, último día, nombre del festivo)."""
    salida = []
    for n in range(dias + 1):
        d = hoy + timedelta(days=n)
        nombre = nombre_festivo(d)
        if not nombre:
            continue
        if d.weekday() == 0:
            salida.append((d - timedelta(days=2), d, nombre))
        elif d.weekday() == 4:
            salida.append((d, d + timedelta(days=2), nombre))
    return salida


def bloque(hoy: date) -> str:
    """El texto del calendario para el bloque `system` del bot de demo."""
    manana = hoy + timedelta(days=1)
    lineas = ["## Calendario (úsalo; no calcules fechas por tu cuenta)"]
    lineas.append(
        f"Hoy es {DIAS[hoy.weekday()]} {hoy.day} de "
        f"{MESES_CORTOS[hoy.month - 1]}; mañana es {DIAS[manana.weekday()]} "
        f"{manana.day} de {MESES_CORTOS[manana.month - 1]}."
    )
    este, proximo = fines_de_semana(hoy)
    lineas.append(
        f"Este fin de semana: {_corta(este[0])} – {_corta(este[1])}. "
        f"El próximo fin de semana: {_corta(proximo[0])} – {_corta(proximo[1])}."
    )
    dias = []
    for n in range(VENTANA_DIAS):
        d = hoy + timedelta(days=n)
        marca = []
        if n == 0:
            marca.append("hoy")
        elif n == 1:
            marca.append("mañana")
        if es_festivo(d):
            marca.append(f"festivo: {nombre_festivo(d)}")
        dias.append(etiqueta(d) + (f" [{', '.join(marca)}]" if marca else ""))
    lineas.append("Próximos días: " + "; ".join(dias) + ".")
    hasta = hoy + timedelta(days=VENTANA_FESTIVOS)
    proximos = [
        f"{_corta(d)} ({nombre})"
        for d, nombre in sorted(
            {**festivos(hoy.year), **festivos(hoy.year + 1)}.items()
        )
        if hoy <= d <= hasta
    ]
    if proximos:
        lineas.append("Festivos en Colombia (próximos 90 días): " + "; ".join(proximos) + ".")
    ps = puentes(hoy)
    if ps:
        lineas.append(
            "Puentes festivos: "
            + "; ".join(f"{_corta(a)} – {_corta(b)} ({n})" for a, b, n in ps)
            + "."
        )
    lineas.append(
        "Toda fecha posterior a hoy está en el futuro: «el 20 de noviembre» es el "
        "próximo 20 de noviembre, nunca uno que ya pasó. Para un día que no "
        "esté en la lista, nombra solo la fecha, sin el día de la semana."
    )
    lineas.append(
        "Si el cliente nombra un día y una fecha («el sábado 14 de noviembre»), "
        "créele: no le corrijas el día de la semana. Nunca le digas que una "
        "fecha cae otro día sin haberla mirado en esta lista. Un puente solo "
        "existe si está en «Puentes festivos». Las noches son los días menos "
        "uno: de sábado a lunes son 2 noches (sábado y domingo)."
    )
    return "\n".join(lineas)
