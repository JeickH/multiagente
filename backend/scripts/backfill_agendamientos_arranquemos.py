"""Backfill de agendamientos para Arranquemos Pues (pedido del CEO, 5-sep-2026).

El módulo de agendamientos empieza a agendar llamadas desde que se despliega,
pero la cuenta lleva desde el 21-ago-2026 acumulando conversaciones abandonadas
que nunca se trabajaron. Este script las rescata: por cada conversación que el
bot dio por abandonada **y que alcanzó a recibir información**, crea la llamada
pendiente que le habría creado el bot.

Dos decisiones del CEO, explícitas:
  - **Todas se citan el mismo día**, el 8-sep-2026, en vez de "3 días después
    de cuando se enfrió" (que para las de agosto ya estaría vencido y saldrían
    todas en rojo el primer día). De aquí en adelante sí manda la regla de los
    3 días, que vive en `services/agendamientos.fecha_tentativa()`.
  - **Todas quedan en Alexandra**: hoy la atención de esa cuenta es de una sola
    persona (la rotación del team quedó en un solo nombre el 29-ago-2026).

Qué NO entra: las que sólo recibieron el saludo y nunca volvieron a escribir.
La clasificación la hace `services/agendamientos.nivel_de_interes()` — la misma
función que usa el bot en vivo, a propósito: si el backfill clasificara por su
cuenta, la lista tendría dos criterios distintos conviviendo.

Idempotente: una conversación que ya tenga agendamiento (pendiente o cerrado)
se salta. Correrlo dos veces no duplica ni le reabre al asesor algo que cerró.

Uso:
    # Ver qué haría, sin escribir nada
    docker compose -p wati exec -T -e DRY_RUN=1 backend \\
        python scripts/backfill_agendamientos_arranquemos.py

    # Local
    docker compose -p wati exec -T backend \\
        python scripts/backfill_agendamientos_arranquemos.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh \\
        backend/scripts/backfill_agendamientos_arranquemos.py
"""
from __future__ import annotations

import os
import sys
from datetime import date

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
from app.database import SessionLocal  # type: ignore
from app.services import agendamientos as svc  # type: ignore


CORREO_OWNER = os.environ.get(
    "BOT_OWNER_EMAIL", "arranquemospues.marketing@gmail.com"
)
#: La fecha que pidió el CEO para todo lo viejo.
FECHA_LLAMADA = date.fromisoformat(os.environ.get("FECHA_LLAMADA", "2026-09-08"))
#: Hoy la atención de esta cuenta es de una sola persona.
ASESOR = os.environ.get("ASESOR", "Alexandra")
DRY_RUN = os.environ.get("DRY_RUN", "").strip() not in ("", "0", "false", "False")


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

        team = (
            db.query(models.Team)
            .filter(models.Team.owner_user_id == owner.id)
            .first()
        )
        if team is None:
            print(f"ERROR: {CORREO_OWNER} no tiene team.")
            return 1

        # Abandonadas = las que el bot etiquetó. Hoy `etiqueta` sólo la escribe
        # el abandono (ver el comentario del modelo `Conversation`), así que
        # "tiene etiqueta" y "fue abandonada" son lo mismo. Se filtra por eso y
        # no por el texto exacto para no depender de cómo esté redactada la
        # etiqueta en `llm_config`, que el tenant puede cambiar.
        abandonadas = (
            db.query(models.Conversation)
            .filter(
                models.Conversation.team_id == team.id,
                models.Conversation.etiqueta.isnot(None),
                models.Conversation.etiqueta != "",
            )
            .order_by(models.Conversation.id)
            .all()
        )

        print(f"Cuenta: {CORREO_OWNER} (team {team.id})")
        print(f"Conversaciones abandonadas: {len(abandonadas)}")
        print(f"Fecha de llamada a asignar: {FECHA_LLAMADA}  ·  asesor: {ASESOR}")
        if DRY_RUN:
            print(">>> DRY_RUN: no se escribe nada\n")

        creados = 0
        saltados_nivel = 0
        saltados_existentes = 0

        for conv in abandonadas:
            ya = (
                db.query(models.Agendamiento)
                .filter(models.Agendamiento.conversation_id == conv.id)
                .first()
            )
            if ya is not None:
                saltados_existentes += 1
                continue

            nivel = svc.nivel_de_interes(db, conv)
            if nivel != models.AGENDAMIENTO_NIVEL_CON_INFORMACION:
                saltados_nivel += 1
                continue

            if DRY_RUN:
                # Sin teléfono ni nombre en la salida: son datos de terceros y
                # esto se corre contra producción (regla 8).
                print(f"  + conv {conv.id} → llamada el {FECHA_LLAMADA}")
                creados += 1
                continue

            db.add(
                models.Agendamiento(
                    team_id=team.id,
                    conversation_id=conv.id,
                    nivel_interes=nivel,
                    fecha_llamada=FECHA_LLAMADA,
                    estado=models.AGENDAMIENTO_PENDIENTE,
                    asesor=ASESOR,
                )
            )
            creados += 1

        if not DRY_RUN:
            db.commit()

        print(
            f"\nAgendamientos creados: {creados}\n"
            f"Saltadas por sólo bienvenida: {saltados_nivel}\n"
            f"Saltadas porque ya tenían: {saltados_existentes}"
        )

        if not DRY_RUN:
            total = (
                db.query(models.Agendamiento)
                .filter(models.Agendamiento.team_id == team.id)
                .count()
            )
            pendientes = (
                db.query(models.Agendamiento)
                .filter(
                    models.Agendamiento.team_id == team.id,
                    models.Agendamiento.estado == models.AGENDAMIENTO_PENDIENTE,
                )
                .count()
            )
            print(f"Total en la cuenta: {total} ({pendientes} pendientes)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
