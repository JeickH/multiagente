"""Reescribe la configuración del bot de viajes SIN borrar el bot.

El seed (`seed_bot_viajes_llm.py`) crea el bot desde cero y para eso **borra**
los bots previos de la cuenta. Contra producción eso no se puede: se llevaría
por delante las sesiones abiertas y el historial de decisiones del bot
(`bot_llm_decisions`), que es la telemetría con la que se mide si responde bien.

Este script solo pisa `llm_config` y los pasos visuales del bot que ya existe:
  1. Catálogo de medios nuevo (3 hoteles) + `tarifario: covenas`, importados de
     `app/data/bot_viajes.py`, la misma fuente que usa el seed.
  2. Quita `assignee` de `llm_config` y de los pasos `handoff`. Mientras esté
     puesto gana sobre el reparto por turnos y TODOS los chats caen en la misma
     persona — que es justo lo que estaba pasando.

**Lo que NO toca**: cualquier llave de `llm_config` que el archivo de datos no
declare se conserva tal cual (`fusionar`). El archivo manda sobre cómo habla el
bot; cómo está operando —`fuente_datos`, un `model_id` fijado a mano— vive solo
en la fila y correr esto no puede apagarlo.

**Solo toca el bot 1** (`context_key == "demo_viajes"` y sin `variante`). La
cuenta tiene además el bot 2 (variante B, `crear_bot_viajes_b.py`) y antes este
script recorría TODOS los bots LLM del dueño: correrlo le pisaba al bot 2 su
guion y sus banderas con la config del bot 1, y el A/B dejaba de comparar nada.
Si no hay exactamente un bot 1, aborta sin escribir.

Idempotente: se puede correr las veces que haga falta.

`BOT_OWNER_EMAIL` es **obligatoria** y no tiene valor por defecto: el repo es
público y el correo de un cliente no va en un archivo versionado (CLAUDE.md
#8). El correo vive en el gestor del CEO.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T -e BOT_OWNER_EMAIL='<correo del dueño>' \\
        backend python scripts/actualizar_bot_viajes.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/actualizar_bot_viajes.py \\
        BOT_OWNER_EMAIL='<correo del dueño>'
"""
from __future__ import annotations

import json
import os
import sys

# Se busca el archivo y no la carpeta: desde `/` el directorio `/app` parece el
# paquete `app` (namespace package) y el import se iría por ahí.
_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app import models  # type: ignore
from app.data.bot_viajes import LLM_CONFIG  # type: ignore
from app.database import SessionLocal  # type: ignore


#: El `context_key` del bot 1. El bot 2 tiene otro (`demo_viajes_b`) y además
#: la llave `variante`; cualquiera de las dos basta para dejarlo fuera.
CONTEXT_KEY_BOT_1 = "demo_viajes"

#: Lo único que este script **borra** a propósito de la config que ya estaba.
#: Todo lo demás que no venga del archivo de datos se conserva (ver `fusionar`).
#: `assignee` fijo gana sobre el reparto por turnos y manda todos los chats a la
#: misma persona, que es la razón por la que este script existe.
A_BORRAR = ("assignee",)


def fusionar(anterior: dict) -> dict:
    """La config nueva: el archivo de datos manda, pero **solo sobre lo suyo**.

    `app/data/bot_viajes.py` es la fuente de verdad de cómo habla el bot —sus
    caminos, su catálogo de medios, sus textos—. No es la fuente de verdad de
    cómo está **operando** ese bot en esa base: `fuente_datos` (el interruptor
    de la capa de productos), un `model_id` fijado a mano y cualquier bandera
    que se encienda desde la app viven solo en la fila, y el archivo no los
    conoce.

    Antes se conservaba una lista blanca de una sola llave (`model_id`), así
    que correr esto contra producción durante la ventana de observación del
    piloto **apagaba `fuente_datos` sin decir nada**: el bot volvía al motor
    viejo, el script imprimía su resumen de siempre y nadie se enteraba. Ahora
    la regla es al revés y no hay que acordarse de nada: se conserva todo lo
    que el archivo de datos no declara, salvo lo que este script borra a
    propósito.
    """
    nueva = dict(LLM_CONFIG)
    for clave, valor in (anterior or {}).items():
        if clave in LLM_CONFIG or clave in A_BORRAR:
            continue
        nueva[clave] = valor
    return nueva


def _config(bot) -> dict:
    try:
        cfg = json.loads(bot.llm_config or "{}")
    except (ValueError, TypeError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def es_bot_1(cfg: dict) -> bool:
    """¿Esta config es la del bot 1? `demo_viajes` y sin `variante`.

    Las dos condiciones a propósito: la variante se crea duplicando el bot 1,
    así que durante un instante tiene su `context_key`; y una variante futura
    podría reusar el contexto. Con `variante` puesta, no es el bot 1.
    """
    return (
        cfg.get("context_key") == CONTEXT_KEY_BOT_1
        and not cfg.get("variante")
    )


def enmascarar_correo(correo: str) -> str:
    """`ab***@***.com`: suficiente para saber a qué cuenta se le corrió, sin
    dejar el correo completo en la salida (que en RDS queda en CloudWatch)."""
    usuario, _, dominio = (correo or "").partition("@")
    tld = dominio.rsplit(".", 1)[-1] if "." in dominio else ""
    return f"{usuario[:2]}***@***.{tld}" if tld else f"{usuario[:2]}***"


def main(db=None, correo: str | None = None) -> int:
    correo = (correo if correo is not None else os.environ.get("BOT_OWNER_EMAIL", "")).strip()
    if not correo:
        print(
            "ERROR: falta BOT_OWNER_EMAIL (el correo del dueño de la cuenta). "
            "No tiene valor por defecto a propósito."
        )
        return 2

    propia = db is None
    if propia:
        db = SessionLocal()
    try:
        owner = (
            db.query(models.User)
            .filter(models.User.correo == correo)
            .first()
        )
        if owner is None:
            print(f"ERROR: no existe el usuario {enmascarar_correo(correo)} en esta base.")
            return 1

        todos = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id, models.Bot.engine == "llm")
            .order_by(models.Bot.id)
            .all()
        )
        bots = [b for b in todos if es_bot_1(_config(b))]
        for b in todos:
            if b not in bots:
                print(f"· bot {b.id} omitido: no es el bot 1 (variante u otro contexto)")
        if len(bots) != 1:
            print(
                f"ERROR: se esperaba exactamente un bot 1 (context_key="
                f"'{CONTEXT_KEY_BOT_1}' sin variante) y hay {len(bots)}"
                + (f": {', '.join(str(b.id) for b in bots)}" if bots else "")
                + ". No se escribió nada."
            )
            return 1

        for bot in bots:
            print(f"\nBot {bot.id} — {bot.name}")

            anterior = {}
            if bot.llm_config:
                try:
                    anterior = json.loads(bot.llm_config)
                except (ValueError, TypeError):
                    anterior = {}

            nueva = fusionar(anterior)
            conservadas = sorted(k for k in nueva if k not in LLM_CONFIG)
            if conservadas:
                # Se imprime siempre: si la corrida apagara el piloto, esta
                # línea es lo único que lo habría delatado a tiempo.
                # Solo los NOMBRES: un valor puede ser una credencial cifrada y
                # esta salida queda en CloudWatch cuando se corre contra RDS.
                print("  · llaves operativas conservadas: " + ", ".join(conservadas))

            if anterior.get("assignee"):
                print(
                    "  ✓ assignee eliminado de llm_config → los chats entran "
                    "al reparto por turnos"
                )

            # El reporte mira el catálogo COMPLETO, no solo las claves: la URL y
            # la descripción de un medio cambian sin que entre ni salga ninguna
            # clave, y comparando solo los nombres el script escribía los datos
            # nuevos mientras imprimía "ya estaba al día". Un mensaje así no es
            # cosmética: es lo único que se ve desde afuera para saber si la
            # corrida contra producción hizo algo.
            medios_antes = anterior.get("media") or {}
            medios_ahora = nueva.get("media") or {}
            fuera = [k for k in medios_antes if k not in medios_ahora]
            entra = [k for k in medios_ahora if k not in medios_antes]
            cambian = [
                k for k in medios_ahora
                if k in medios_antes and medios_antes[k] != medios_ahora[k]
            ]
            if fuera:
                print(f"  ✓ medios retirados: {', '.join(sorted(fuera))}")
            if entra:
                print(f"  ✓ medios nuevos:    {', '.join(sorted(entra))}")
            for k in sorted(cambian):
                campos = sorted(
                    c for c in set(medios_antes[k]) | set(medios_ahora[k])
                    if medios_antes[k].get(c) != medios_ahora[k].get(c)
                )
                print(f"  ✓ medio actualizado: {k} ({', '.join(campos)})")
            if not (fuera or entra or cambian):
                print("  · el catálogo de medios ya estaba al día")

            if not anterior.get("tarifario"):
                print("  ✓ herramienta consultar_tarifario habilitada")

            bot.llm_config = json.dumps(nueva, ensure_ascii=False)
            db.add(bot)

            # Los pasos `handoff` con asesor fijo también anulan el turno.
            sueltos = 0
            for paso in bot.steps:
                if paso.step_type != "handoff":
                    continue
                try:
                    cfg = json.loads(paso.config or "{}")
                except (ValueError, TypeError):
                    continue
                if cfg.pop("assignee", None) is not None:
                    paso.config = json.dumps(cfg, ensure_ascii=False)
                    db.add(paso)
                    sueltos += 1
            if sueltos:
                print(f"  ✓ {sueltos} paso(s) handoff sin asesor fijo")

        db.commit()

        print("\nResumen:")
        for bot in bots:
            cfg = json.loads(bot.llm_config or "{}")
            print(f"  · bot {bot.id}: {len(cfg.get('media') or {})} medios, "
                  f"tarifario={cfg.get('tarifario') or '—'}, "
                  f"fuente_datos={cfg.get('fuente_datos') or '(tarifario)'}, "
                  f"assignee={cfg.get('assignee') or '(por turno)'}")
        return 0
    finally:
        if propia:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
