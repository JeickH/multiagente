"""Festivos de Colombia, por año (Sprint 36, agenda de llamadas del bot D).

Es configuración y no cálculo: la lista la publica el Gobierno cada año y un
festivo trasladado por decreto no sale de ninguna fórmula. Se verifica contra
la Ley Emiliani (Ley 51 de 1983) en `tests/viajes/variante_d/test_franjas.py`,
para que un error de dedo no pase.

**Un año que no está aquí no tiene festivos conocidos**, y por eso ese día no
se ofrecen franjas de llamada (`services/horario.py`, diseño de seguridad 3.7):
prometer una llamada en un festivo es una promesa rota. Cuando se acerque el
año siguiente, se agrega su lista y listo.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, FrozenSet

_CRUDOS: Dict[int, tuple] = {
    2026: (
        "2026-01-01",  # Año Nuevo
        "2026-01-12",  # Reyes Magos (trasladado)
        "2026-03-23",  # San José (trasladado)
        "2026-04-02",  # Jueves Santo
        "2026-04-03",  # Viernes Santo
        "2026-05-01",  # Día del Trabajo
        "2026-05-18",  # Ascensión del Señor
        "2026-06-08",  # Corpus Christi
        "2026-06-15",  # Sagrado Corazón
        "2026-06-29",  # San Pedro y San Pablo
        "2026-07-20",  # Independencia
        "2026-08-07",  # Batalla de Boyacá
        "2026-08-17",  # Asunción de la Virgen (trasladado)
        "2026-10-12",  # Día de la Raza
        "2026-11-02",  # Todos los Santos (trasladado)
        "2026-11-16",  # Independencia de Cartagena (trasladado)
        "2026-12-08",  # Inmaculada Concepción
        "2026-12-25",  # Navidad
    ),
    2027: (
        "2027-01-01",  # Año Nuevo
        "2027-01-11",  # Reyes Magos (trasladado)
        "2027-03-22",  # San José (trasladado)
        "2027-03-25",  # Jueves Santo
        "2027-03-26",  # Viernes Santo
        "2027-05-01",  # Día del Trabajo
        "2027-05-10",  # Ascensión del Señor
        "2027-05-31",  # Corpus Christi
        "2027-06-07",  # Sagrado Corazón
        "2027-07-05",  # San Pedro y San Pablo (trasladado)
        "2027-07-20",  # Independencia
        "2027-08-07",  # Batalla de Boyacá
        "2027-08-16",  # Asunción de la Virgen (trasladado)
        "2027-10-18",  # Día de la Raza (trasladado)
        "2027-11-01",  # Todos los Santos
        "2027-11-15",  # Independencia de Cartagena (trasladado)
        "2027-12-08",  # Inmaculada Concepción
        "2027-12-25",  # Navidad
    ),
}

#: año → festivos de ese año.
FESTIVOS: Dict[int, FrozenSet[date]] = {
    anio: frozenset(date.fromisoformat(d) for d in dias) for anio, dias in _CRUDOS.items()
}
