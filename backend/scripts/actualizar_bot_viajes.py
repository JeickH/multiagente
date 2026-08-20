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

Idempotente: se puede correr las veces que haga falta.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T backend python scripts/actualizar_bot_viajes.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/actualizar_bot_viajes.py \\
        BOT_OWNER_EMAIL='arranquemospues.marketing@gmail.com'
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


CORREO_OWNER = os.environ.get(
    "BOT_OWNER_EMAIL", "arranquemospues.marketing@gmail.com"
)


def main() -> int:
    db = SessionLocal()
    try:
        owner = (
            db.query(models.User)
            .filter(models.User.correo == CORREO_OWNER)
            .first()
        )
        if owner is None:
            print(f"ERROR: no existe el usuario {CORREO_OWNER} en esta base.")
            return 1

        bots = (
            db.query(models.Bot)
            .filter(models.Bot.user_id == owner.id, models.Bot.engine == "llm")
            .all()
        )
        if not bots:
            print(f"ERROR: {CORREO_OWNER} no tiene ningún bot con engine='llm'.")
            return 1

        for bot in bots:
            print(f"\nBot {bot.id} — {bot.name}")

            anterior = {}
            if bot.llm_config:
                try:
                    anterior = json.loads(bot.llm_config)
                except (ValueError, TypeError):
                    anterior = {}

            nueva = dict(LLM_CONFIG)
            # Se conservan las llaves propias del tenant que este script no
            # administra (ej. `model_id` si alguien fijó un override).
            for clave in ("model_id",):
                if anterior.get(clave) is not None:
                    nueva[clave] = anterior[clave]

            if anterior.get("assignee"):
                print(
                    f"  ✓ assignee '{anterior['assignee']}' eliminado de "
                    "llm_config → los chats entran al reparto por turnos"
                )

            claves_antes = sorted((anterior.get("media") or {}).keys())
            claves_ahora = sorted((nueva.get("media") or {}).keys())
            if claves_antes != claves_ahora:
                fuera = [k for k in claves_antes if k not in claves_ahora]
                entra = [k for k in claves_ahora if k not in claves_antes]
                if fuera:
                    print(f"  ✓ medios retirados: {', '.join(fuera)}")
                if entra:
                    print(f"  ✓ medios nuevos:    {', '.join(entra)}")
            else:
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
                  f"assignee={cfg.get('assignee') or '(por turno)'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
