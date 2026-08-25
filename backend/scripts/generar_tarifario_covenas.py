"""Genera `app/data/tarifario_covenas.json` a partir del Excel del CEO.

El Excel (`demo_viajes/Tarifario_Covenas_Amor_de_Dios_y_Piedra_Mar.xlsx`) es la
fuente; el JSON es lo que va en la imagen y lo que consulta el bot. Se separan a
propósito: el Excel no se versiona (vive en la carpeta de material crudo, que
está git-ignorada) y **nunca** se le manda al cliente — el bot solo envía las
imágenes de los tarifarios.

Por qué un JSON generado y no leer el Excel en caliente:
  - `openpyxl` no está en el runtime del backend y no vale la pena meterlo.
  - El archivo queda versionado: si un precio cambia, se ve en el diff del PR.
  - La consulta del bot es determinista y testeable sin I/O de Excel.

El año NO está en el Excel (las filas dicen "AGOSTO 06 AL 09"), así que se
asigna por temporada: julio–diciembre son del año de inicio y enero del
siguiente. Eso queda escrito en `vigencia` dentro del JSON para que sea obvio
que este archivo hay que regenerarlo cuando salga el tarifario de la próxima
temporada.

Uso:
    conda activate multiagente   # o source backend/.venv/bin/activate
    python backend/scripts/generar_tarifario_covenas.py
    python backend/scripts/generar_tarifario_covenas.py --excel otra/ruta.xlsx
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXCEL_POR_DEFECTO = os.path.join(
    RAIZ, "demo_viajes", "Tarifario_Covenas_Amor_de_Dios_y_Piedra_Mar.xlsx"
)
DESTINO = os.path.join(
    RAIZ, "backend", "app", "data", "tarifario_covenas.json"
)

# Temporada que cubre el tarifario actual. Julio–diciembre caen en el primer
# año; enero, en el siguiente.
ANIO_INICIO = 2026

MESES = {
    "ENERO": 1, "FEBRERO": 2, "MARZO": 3, "ABRIL": 4, "MAYO": 5, "JUNIO": 6,
    "JULIO": 7, "AGOSTO": 8, "SEPTIEMBRE": 9, "OCTUBRE": 10, "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}

# Cómo se llama cada hotel en la columna HOTEL del Excel -> claves internas.
# "HOTEL AMOR DE DIOS y HOTEL BOHIOS" es una sola fila con dos hoteles porque
# comparten tarifa: Bohíos cobra exactamente lo mismo que Amor de Dios.
HOTELES = {
    "HOTEL AMOR DE DIOS Y HOTEL BOHIOS": ["amor_de_dios", "bohios"],
    "HOTEL PIEDRA MAR": ["piedra_mar"],
}

_RE_INICIO = re.compile(r"^\s*([A-ZÁÉÍÓÚÑ]+)\s+(\d{1,2})")

# Etiqueta y coletilla de cada tabla de precios. Bohíos no va aparte: comparte
# fila con Amor de Dios porque cobra exactamente lo mismo.
_TABLAS = (
    ("amor_de_dios", "Amor de Dios y Bohíos", ""),
    (
        "piedra_mar",
        "Piedra Mar",
        " En Piedra Mar, las salidas entre semana (lunes con jueves) no aplican "
        "para lunes festivos.",
    ),
)


def _pesos(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def _notas(planes: List[Dict[str, Any]]) -> List[str]:
    """Las notas del JSON, con los mínimos **calculados** de las filas.

    Antes las dos últimas iban escritas a mano, y decían «desde $350.000» para
    Amor de Dios. Ese valor no existía en ninguna fila del Excel: era de una
    temporada vieja que nadie volvió a revisar — el mínimo real es $369.000.
    Escribir aquí una cifra a mano garantiza que se desactualice en silencio la
    próxima vez que el CEO mande un Excel nuevo, así que se derivan de `planes`.

    Ojo: estas notas son documentación para quien abra el JSON. La respuesta que
    ve el bot NO las lee —`services/tarifario.py` calcula sus propios mínimos—,
    y así debe seguir: el bot habla del mes que pidió el cliente, y un mínimo de
    toda la temporada presentado junto a un mes es justo el bug del Sprint 24.
    """
    notas = [
        "Los valores son POR PERSONA y en pesos colombianos.",
        "VALOR MÚLTIPLE = acomodación múltiple; VALOR DOBLE = acomodación doble.",
        "Bohíos cobra exactamente la misma tarifa que Amor de Dios.",
    ]
    for clave, etiqueta, coletilla in _TABLAS:
        propios = [p for p in planes if clave in p["hoteles"]]
        if not propios:
            continue
        barato = min(propios, key=lambda p: (p["multiple"], p["inicio"]))
        notas.append(
            f"{etiqueta}: en toda la temporada, la salida más económica es "
            f"{_pesos(barato['multiple'])} por persona en múltiple "
            f"({barato['fecha']}). Es el mínimo de TODA la temporada: para "
            f"cotizarle a alguien que ya dijo un mes, va el mínimo de ESE mes."
            f"{coletilla}"
        )
    return notas


def _fecha_inicio(texto: str) -> tuple[int, int] | None:
    """(mes, día) de arranque del plan, leídos del texto de la columna FECHA."""
    m = _RE_INICIO.match((texto or "").upper())
    if not m:
        return None
    mes = MESES.get(m.group(1))
    if mes is None:
        return None
    return mes, int(m.group(2))


def _anio_de(mes: int) -> int:
    return ANIO_INICIO + 1 if mes == 1 else ANIO_INICIO


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--excel", default=EXCEL_POR_DEFECTO)
    parser.add_argument("--destino", default=DESTINO)
    args = parser.parse_args()

    try:
        import openpyxl  # type: ignore
    except ImportError:
        print(
            "Falta openpyxl. Instálalo en el ambiente del proyecto "
            "(conda activate multiagente && pip install openpyxl), "
            "NUNCA en el intérprete del sistema."
        )
        return 1

    if not os.path.isfile(args.excel):
        print(f"ERROR: no existe el Excel {args.excel}")
        return 1

    wb = openpyxl.load_workbook(args.excel, data_only=True)
    ws = wb["Tarifario"]

    planes: List[Dict[str, Any]] = []
    descartadas = 0
    for fila in ws.iter_rows(min_row=4, values_only=True):
        hotel_txt, mes_txt, fecha_txt, multiple, doble, noches, dias, plan = (
            list(fila) + [None] * 8
        )[:8]
        if not hotel_txt or not fecha_txt or multiple in (None, ""):
            continue
        clave_hotel = re.sub(r"\s+", " ", str(hotel_txt)).strip().upper()
        hoteles = HOTELES.get(clave_hotel)
        if hoteles is None:
            descartadas += 1
            continue
        inicio = _fecha_inicio(str(fecha_txt))
        if inicio is None:
            descartadas += 1
            continue
        mes, dia = inicio
        planes.append(
            {
                "hoteles": hoteles,
                "mes": mes,
                "inicio": f"{_anio_de(mes)}-{mes:02d}-{dia:02d}",
                "fecha": re.sub(r"\s+", " ", str(fecha_txt)).strip(),
                "multiple": int(multiple),
                "doble": int(doble),
                "noches": int(noches),
                "dias": int(dias),
                "plan": re.sub(r"\s+", " ", str(plan or "")).strip(),
            }
        )

    planes.sort(key=lambda p: (p["inicio"], p["hoteles"][0]))

    datos = {
        "_fuente": os.path.basename(args.excel),
        "_generado_por": "backend/scripts/generar_tarifario_covenas.py",
        "vigencia": (
            f"Temporada julio {ANIO_INICIO} – enero {ANIO_INICIO + 1}. "
            "Regenerar con el Excel de la próxima temporada."
        ),
        "notas": _notas(planes),
        "planes": planes,
    }

    os.makedirs(os.path.dirname(args.destino), exist_ok=True)
    with open(args.destino, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    por_hotel: Dict[str, int] = {}
    for p in planes:
        for h in p["hoteles"]:
            por_hotel[h] = por_hotel.get(h, 0) + 1
    print(f"OK: {len(planes)} planes -> {args.destino}")
    for hotel, n in sorted(por_hotel.items()):
        print(f"  · {hotel:<14} {n} planes")
    if descartadas:
        print(f"  · {descartadas} fila(s) ignorada(s) (notas al pie / hotel desconocido)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
