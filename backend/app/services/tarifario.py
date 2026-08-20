"""Consulta del tarifario de Coveñas — precios exactos, no recordados.

El bot de Arranquemos Pues vende un plan cuyo precio cambia por hotel, por mes
y por fecha de salida. Pedirle al modelo que se aprenda 102 filas de precios y
las recite es la forma más rápida de que invente una: por eso los precios NO
viven en el contexto a priori sino en `app/data/tarifario_covenas.json`
(generado desde el Excel del CEO con `scripts/generar_tarifario_covenas.py`) y
el modelo los pide con la herramienta `consultar_tarifario`.

Dos reglas del negocio que están cableadas aquí y no en el prompt, porque son
las que más caro cuestan si el modelo las olvida:

  1. **Nunca se ofrece una fecha que ya pasó.** El tarifario arranca en julio y
     el bot sigue vivo en agosto: sin este filtro le vendería a un cliente la
     salida del 06 de agosto en septiembre.
  2. **Cada mes tiene su imagen.** Qué flyer corresponde a qué mes no se
     adivina: sale del propio catálogo de medios del bot (`llm_config.media`),
     donde cada tarifario declara `hotel` y `meses`. Así el tenant puede cambiar
     una imagen sin tocar código.

Bohíos comparte tarifa con Amor de Dios y no tiene flyer propio: se le manda el
de Amor de Dios avisando que la imagen dice otro nombre pero el precio aplica.
"""
from __future__ import annotations

import json
import logging
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Colombia, sin horario de verano. El backend corre en UTC (ECS), así que
# `date.today()` se adelanta un día entre las 7 pm y la medianoche de allá — y
# el bot dejaría de ofrecer una salida que todavía se puede vender hoy.
_TZ_CO = timezone(timedelta(hours=-5))


def hoy_colombia() -> date:
    return datetime.now(_TZ_CO).date()


_DATA = Path(__file__).resolve().parent.parent / "data" / "tarifario_covenas.json"

# Nombres que puede escribir el modelo (o el cliente) -> clave interna.
_HOTELES = {
    "amor_de_dios": "amor_de_dios",
    "amor de dios": "amor_de_dios",
    "el amor de dios": "amor_de_dios",
    "hotel amor de dios": "amor_de_dios",
    "hotel el amor de dios": "amor_de_dios",
    "amordios": "amor_de_dios",
    "bohios": "bohios",
    "hotel bohios": "bohios",
    "los bohios": "bohios",
    "piedra_mar": "piedra_mar",
    "piedra mar": "piedra_mar",
    "piedramar": "piedra_mar",
    "hotel piedra mar": "piedra_mar",
}

_NOMBRE_HOTEL = {
    "amor_de_dios": "Amor de Dios",
    "bohios": "Bohíos",
    "piedra_mar": "Piedra Mar",
}

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_NOMBRE_MES = {v: k.capitalize() for k, v in _MESES.items() if k != "setiembre"}


def _sin_tildes(texto: str) -> str:
    base = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=1)
def _datos() -> Dict[str, Any]:
    try:
        return json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("tarifario: no se pudo leer %s", _DATA.name)
        return {"planes": [], "notas": []}


def normalizar_hotel(texto: str) -> Optional[str]:
    """Clave interna del hotel, o None si no se reconoce."""
    limpio = _sin_tildes(texto)
    if not limpio:
        return None
    if limpio in _HOTELES:
        return _HOTELES[limpio]
    # Búsqueda por contención: "en el hotel piedra mar", "bohíos por favor".
    for alias, clave in _HOTELES.items():
        if alias in limpio:
            return clave
    return None


def normalizar_mes(texto: str) -> Optional[int]:
    """Número de mes (1-12) a partir de un nombre, un número o AAAA-MM-DD."""
    limpio = _sin_tildes(texto)
    if not limpio:
        return None
    for nombre, num in _MESES.items():
        if nombre in limpio:
            return num
    # "2026-09-15", "09/2026", "9"
    digitos = [d for d in "".join(c if c.isdigit() else " " for c in limpio).split()]
    for d in digitos:
        if len(d) <= 2 and 1 <= int(d) <= 12:
            return int(d)
    for d in digitos:
        if len(d) == 6 and 1 <= int(d[4:]) <= 12:   # AAAAMM
            return int(d[4:])
    return None


def _pesos(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def planes_de(hotel: str, mes: int, hoy: Optional[date] = None) -> List[Dict[str, Any]]:
    """Planes vigentes de ese hotel en ese mes, del más próximo al más lejano."""
    hoy = hoy or hoy_colombia()
    fuera = []
    for plan in _datos().get("planes", []):
        if hotel not in plan.get("hoteles", []) or plan.get("mes") != mes:
            continue
        if date.fromisoformat(plan["inicio"]) < hoy:
            continue
        fuera.append(plan)
    return sorted(fuera, key=lambda p: p["inicio"])


def clave_imagen(cfg: Dict[str, Any], hotel: str, mes: int) -> Optional[str]:
    """Clave del catálogo de medios con el flyer de ese hotel y ese mes.

    Bohíos no tiene flyer propio: usa el de Amor de Dios (misma tarifa).
    """
    objetivo = "amor_de_dios" if hotel == "bohios" else hotel
    media = cfg.get("media")
    if not isinstance(media, dict):
        return None
    for clave, item in media.items():
        if not isinstance(item, dict):
            continue
        if item.get("hotel") != objetivo:
            continue
        meses = item.get("meses")
        if isinstance(meses, list) and mes in meses:
            return str(clave)
    return None


def _bloque_hotel(
    cfg: Dict[str, Any],
    hotel: str,
    mes: int,
    fecha: Optional[date],
    hoy: date,
) -> List[str]:
    nombre = _NOMBRE_HOTEL[hotel]
    planes = planes_de(hotel, mes, hoy)
    lineas: List[str] = []

    if not planes:
        hay_otros = any(
            planes_de(hotel, m, hoy) for m in range(1, 13) if m != mes
        )
        lineas.append(
            f"{nombre} — {_NOMBRE_MES[mes]}: NO hay salidas publicadas para ese "
            "mes en este hotel."
        )
        if hay_otros:
            disponibles = [
                _NOMBRE_MES[m] for m in range(1, 13) if planes_de(hotel, m, hoy)
            ]
            lineas.append(
                f"  Meses con salidas en {nombre}: {', '.join(disponibles)}."
            )
        lineas.append(
            "  Dile con qué meses SÍ hay y ofrécele el otro hotel; no escales "
            "todavía."
        )
        return lineas

    lineas.append(f"{nombre} — {_NOMBRE_MES[mes]} ({len(planes)} salidas):")
    for plan in planes:
        marca = ""
        if fecha is not None and date.fromisoformat(plan["inicio"]) == fecha:
            marca = "  <-- la fecha que pidió"
        obs = f", {plan['plan']}" if plan.get("plan") else ""
        lineas.append(
            f"  · {plan['fecha']} — múltiple {_pesos(plan['multiple'])} · "
            f"doble {_pesos(plan['doble'])} "
            f"({plan['noches']} noches / {plan['dias']} días{obs}){marca}"
        )

    if fecha is not None and not any(
        date.fromisoformat(p["inicio"]) == fecha for p in planes
    ):
        cercanos = sorted(
            planes, key=lambda p: abs((date.fromisoformat(p["inicio"]) - fecha).days)
        )[:2]
        lineas.append(
            f"  OJO: no hay salida que arranque el {fecha.isoformat()} en "
            f"{nombre}. Las más cercanas son: "
            + " y ".join(p["fecha"] for p in cercanos)
            + ". Ofrécele esas con su precio — NO escales por esto."
        )

    clave = clave_imagen(cfg, hotel, mes)
    if clave:
        lineas.append(f"  Imagen para ese mes: envía `{clave}` con `enviar_media`.")
        if hotel == "bohios":
            lineas.append(
                "  IMPORTANTE: esa imagen dice 'Hotel amor de Dios'. Avísale al "
                "cliente que el flyer sale a nombre de Amor de Dios pero los "
                "precios aplican igual para Bohíos."
            )
    return lineas


def consultar(
    cfg: Dict[str, Any],
    *,
    hotel: str = "",
    mes: str = "",
    fecha: str = "",
    hoy: Optional[date] = None,
) -> str:
    """Resultado de `consultar_tarifario` que se le devuelve al modelo."""
    hoy = hoy or hoy_colombia()

    fecha_pedida: Optional[date] = None
    if fecha:
        try:
            fecha_pedida = date.fromisoformat(fecha.strip()[:10])
        except ValueError:
            fecha_pedida = None

    num_mes = normalizar_mes(mes) or (
        fecha_pedida.month if fecha_pedida is not None else None
    )
    if num_mes is None:
        return (
            "No entendí para qué mes. Pregúntale al cliente en qué mes piensa "
            "viajar y vuelve a consultar."
        )

    if fecha_pedida is not None and fecha_pedida < hoy:
        return (
            f"La fecha {fecha_pedida.isoformat()} ya pasó. Pregúntale al cliente "
            "para qué fecha nueva quiere viajar."
        )

    clave_hotel = normalizar_hotel(hotel) if hotel else None
    if hotel and clave_hotel is None:
        return (
            f"No reconozco el hotel '{hotel}'. Los hoteles del plan son: "
            "Amor de Dios, Piedra Mar y Bohíos."
        )

    # Sin hotel explícito se comparan los dos tarifarios: es justo lo que el
    # cliente quiere saber cuando pregunta "¿cuánto vale?" a secas, y ahorra un
    # ida y vuelta. Bohíos no se lista aparte porque cobra igual que Amor de Dios.
    hoteles = [clave_hotel] if clave_hotel else ["amor_de_dios", "piedra_mar"]

    partes: List[str] = [
        f"Tarifario de Coveñas — valores POR PERSONA (hoy es {hoy.isoformat()}; "
        "solo se listan salidas que todavía no han pasado)."
    ]
    for h in hoteles:
        partes.extend(_bloque_hotel(cfg, h, num_mes, fecha_pedida, hoy))

    if clave_hotel is None:
        partes.append(
            "Bohíos cobra exactamente lo mismo que Amor de Dios (misma tabla)."
        )
    if any(h in ("amor_de_dios", "bohios") for h in hoteles):
        partes.append(
            "Amor de Dios y Bohíos: todos los lunes con jueves hay salidas desde "
            "$350.000 por persona en múltiple."
        )
    if "piedra_mar" in hoteles:
        partes.append(
            "Piedra Mar: todos los lunes con jueves hay salidas desde $389.000 "
            "por persona en múltiple (no aplica para lunes festivos)."
        )
    partes.append(
        "Recuerda: NUNCA le mandes el Excel ni un archivo de datos al cliente, "
        "solo la imagen del tarifario que corresponde al mes."
    )
    return "\n".join(partes)
