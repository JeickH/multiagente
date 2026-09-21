"""Deja las filas de `bot_recordatorios` de una cuenta, con revisión antes.

    python backend/scripts/configurar_recordatorios.py <cuenta> --team-id N --revisar
    python backend/scripts/configurar_recordatorios.py <cuenta> --team-id N --aplicar

Los tiempos y los textos están en `productos_fuentes/datos/_recordatorios.json`,
que es el archivo que se edita: acá no hay ni un minuto ni una frase escrita.

Tres cosas que conviene saber antes de correrlo
-----------------------------------------------
1. **Esto NO enciende el reenganche.** La política la sigue decidiendo
   `llm_config.seguimiento` del bot (ver `llm_engine.seguimiento_de`): si ese
   bloque no existe, el bot nunca agenda un seguimiento y estas filas se quedan
   quietas. La tabla decide **con qué tiempos y con qué textos**, no **si**.
   Es a propósito: cargar los datos de una cuenta no puede cambiarle el
   comportamiento a un bot que ya está atendiendo clientes.
2. **Por defecto las filas quedan a nombre de toda la cuenta** (`bot_id = 0`),
   no de un bot concreto. Los ids de los bots no son los mismos en local y en
   RDS, y una fila apuntando al bot equivocado es una cadena que no corre.
   `--bot-id` está para cuando una cuenta tenga dos bots con políticas
   distintas: las filas del bot le ganan a las de la cuenta.
3. **Es idempotente y no borra.** Cada fila se busca por
   `(team_id, bot_id, orden)`, que es el UNIQUE de la tabla; las que sobran de
   una corrida anterior se marcan `activo = false` en vez de borrarse, igual
   que en el importador de productos.

Se corre contra el compose local:

    docker compose -p wati exec -T backend \\
        python scripts/configurar_recordatorios.py natulce --team-id 15 --revisar
"""
from __future__ import annotations

import argparse
import json
import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _ruta in (BACKEND, os.path.join(BACKEND, "scripts")):
    if _ruta not in sys.path:
        sys.path.insert(0, _ruta)

from productos_fuentes import json_generico  # noqa: E402

ARCHIVO = os.path.join(json_generico.DATOS, "_recordatorios.json")


def catalogo() -> dict:
    with open(ARCHIVO, encoding="utf-8") as fh:
        return json.load(fh)["cuentas"]


def filas_de(cuenta: dict) -> list:
    """Los recordatorios de la cuenta, con su `omitir_si` ya puesto.

    `omitir_si` se declara una vez por cuenta y se copia a cada fila: la
    condición ("no le insistas a quien ya compró") es de la cadena entera, y
    repetirla tres veces en el archivo es tres oportunidades de que una quede
    distinta. La tabla sí la guarda por fila, porque cada recordatorio se juzga
    solo.
    """
    comun = cuenta.get("omitir_si") or {}
    fuera = []
    for fila in cuenta["recordatorios"]:
        fuera.append({**fila, "omitir_si": fila.get("omitir_si", comun)})
    return fuera


def _describir(nombre: str, cuenta: dict, filas: list, team_id: int, bot_id: int) -> None:
    print(f"[{nombre}] cuenta team_id={team_id} · bot_id={bot_id} "
          f"({'toda la cuenta' if bot_id == 0 else 'ese bot'})")
    print(f"[{nombre}] por qué: {cuenta.get('por_que', '—')}")
    if cuenta.get("omitir_si_nota"):
        print(f"[{nombre}] OJO: {cuenta['omitir_si_nota']}")
    previo = 0
    for fila in filas:
        minutos = int(fila["minutos"])
        horas = minutos / 60
        print(
            f"  {fila['orden']}. a los {minutos} min ({horas:.1f} h) desde que "
            f"empezó el silencio — {minutos - previo} min después del anterior · "
            f"franja {fila['hora_min']}-{fila['hora_max']} · "
            f"omitir_si={json.dumps(fila['omitir_si'], ensure_ascii=False)}"
        )
        print(f"     «{fila['texto']}»")
        previo = minutos


def aplicar(db, nombre: str, filas: list, *, team_id: int, bot_id: int) -> None:
    from app import models

    existentes = {
        f.orden: f
        for f in db.query(models.BotRecordatorio)
        .filter(
            models.BotRecordatorio.team_id == team_id,
            models.BotRecordatorio.bot_id == bot_id,
        )
        .all()
    }
    nuevas = cambiadas = 0
    for fila in filas:
        registro = existentes.get(int(fila["orden"]))
        if registro is None:
            registro = models.BotRecordatorio(
                team_id=team_id, bot_id=bot_id, orden=int(fila["orden"]),
                minutos=int(fila["minutos"]), texto=fila["texto"],
            )
            db.add(registro)
            nuevas += 1
        else:
            antes = (
                registro.minutos, registro.texto, registro.omitir_si,
                registro.hora_min, registro.hora_max, registro.activo,
            )
            despues = (
                int(fila["minutos"]), fila["texto"], fila["omitir_si"],
                int(fila["hora_min"]), int(fila["hora_max"]), True,
            )
            if antes != despues:
                cambiadas += 1
        registro.minutos = int(fila["minutos"])
        registro.texto = fila["texto"]
        registro.omitir_si = fila["omitir_si"]
        registro.hora_min = int(fila["hora_min"])
        registro.hora_max = int(fila["hora_max"])
        registro.activo = True

    ordenes = {int(f["orden"]) for f in filas}
    retiradas = 0
    for orden, registro in existentes.items():
        if orden not in ordenes and registro.activo:
            registro.activo = False   # se retira, no se borra
            retiradas += 1
    db.commit()
    print(
        f"[{nombre}] listo: +{nuevas} nuevas · ~{cambiadas} cambiadas · "
        f"-{retiradas} retiradas (activo=false, no se borran)"
    )
    print(
        f"[{nombre}] recuerda: esto NO enciende nada. Mientras el bot no tenga "
        "`llm_config.seguimiento`, la cadena no corre."
    )


def main(argv=None) -> int:
    cuentas = catalogo()
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("cuenta", choices=sorted(cuentas))
    p.add_argument("--team-id", type=int, required=True)
    p.add_argument(
        "--bot-id", type=int, default=0,
        help="bot concreto. Por defecto 0 = toda la cuenta (ver la cabecera)",
    )
    grupo = p.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--revisar", action="store_true", help="solo imprime, no escribe")
    grupo.add_argument("--aplicar", action="store_true")
    args = p.parse_args(argv)

    cuenta = cuentas[args.cuenta]
    filas = filas_de(cuenta)
    _describir(args.cuenta, cuenta, filas, args.team_id, args.bot_id)
    if args.revisar:
        print(f"[{args.cuenta}] revisión: no se escribió nada.")
        return 0

    from app.database import SessionLocal

    db = SessionLocal()
    try:
        aplicar(db, args.cuenta, filas, team_id=args.team_id, bot_id=args.bot_id)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
