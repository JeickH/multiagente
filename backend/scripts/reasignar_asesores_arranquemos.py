"""Saca `asesor_1` de la bandeja de Arranquemos Pues: los chats viejos pasan a
Camila, Julián o Alexandra.

Contexto (#376 → #377). El reparto por turnos (`teams.asesores_rotacion`) ya
quedó bien y los chats nuevos caen con nombre propio, pero los que se entregaron
ANTES de la corrección quedaron guardados con el handle histórico `asesor_1` —
que no es una persona— y así se siguen viendo en la etiqueta 👤 de Mensajes.
El CEO pidió (20-ago-2026) que en esa cuenta no aparezca ningún `asesor_1`.

Qué hace:
  1. Ubica el team de Arranquemos Pues por el correo de su cuenta admin.
     **Solo toca ese team**: es un pedido de esa cuenta, no un cambio global.
  2. Busca sus conversaciones cuyo `assigned_to` sea un placeholder
     (`asesor_1`, `asesor_2`, …) y las reparte entre los asesores configurados,
     en orden de id y arrancando desde el turno que lleve el team, de forma que
     el reparto quede parejo y el turno siga corriendo desde donde queda.
  3. Deja el turno persistido para que el próximo chat nuevo continúe la ronda.

Es idempotente: en la segunda corrida ya no hay placeholders y no toca nada.

Ojo con la atribución: nadie registró quién atendió esos chats (los tres
asesores comparten un solo login), así que el nombre que queda es el del reparto
por turnos, no una constancia de quién respondió. Fue decisión explícita del CEO
preferir eso a seguir mostrando `asesor_1`.

Uso:
    # Ver qué haría, sin escribir
    docker compose -p wati exec -T -e DRY_RUN=1 backend \\
        python scripts/reasignar_asesores_arranquemos.py

    # Local
    docker compose -p wati exec -T backend \\
        python scripts/reasignar_asesores_arranquemos.py

    # Producción (RDS)
    ./backend/scripts/rds_exec.sh backend/scripts/reasignar_asesores_arranquemos.py
"""
from __future__ import annotations

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

from app import crud, models  # type: ignore
from app.database import SessionLocal  # type: ignore


CORREOS_ADMIN = [
    "arranquemospues.marketing@gmail.com",
    "arranquemospues.contacto@gmail.com",  # correo anterior, por si no migró
]


def _team_de_arranquemos(db) -> models.Team | None:
    for correo in CORREOS_ADMIN:
        admin = crud.get_user_by_email(db, correo)
        if admin is None:
            continue
        membresia = crud.get_membership_for_user(db, admin)
        if membresia is None:
            continue
        return db.query(models.Team).get(membresia.team_id)
    return None


def main() -> int:
    seco = os.environ.get("DRY_RUN") == "1"
    db = SessionLocal()
    try:
        team = _team_de_arranquemos(db)
        if team is None:
            print("ERROR: no se encontró el team de Arranquemos Pues en esta base.")
            return 1

        asesores = [n for n in (team.asesores_rotacion or []) if n]
        if not asesores:
            print(
                f"ERROR: el team {team.id} ({team.nombre}) no tiene "
                "`asesores_rotacion` configurado. Corre antes "
                "`configurar_arranquemos_pues.py`: sin esa lista no hay entre "
                "quiénes repartir y volveríamos a escribir un placeholder."
            )
            return 1

        print(f"Team {team.id} · {team.nombre}")
        print(f"  asesores: {' → '.join(asesores)} (turno actual: {team.handoff_turno})")

        pendientes = [
            c
            for c in (
                db.query(models.Conversation)
                .filter(models.Conversation.team_id == team.id)
                .order_by(models.Conversation.id)
                .all()
            )
            if crud.es_handle_placeholder(c.assigned_to)
        ]
        if not pendientes:
            print("\n  · no quedan chats con handle placeholder. Nada que hacer.")
            return 0

        turno = int(team.handoff_turno or 0)
        print(f"\n  {len(pendientes)} chat(s) con placeholder:")
        for conv in pendientes:
            nuevo = asesores[turno % len(asesores)]
            turno = (turno + 1) % len(asesores)
            # El teléfono es dato de un tercero: en el log va enmascarado.
            wa = (conv.contact_wa_id or "")[:3] + "X" * max(0, len(conv.contact_wa_id or "") - 3)
            print(f"    · conv {conv.id:<4} {wa:<16} {conv.assigned_to} → {nuevo}")
            if not seco:
                conv.assigned_to = nuevo
                db.add(conv)

        if seco:
            print(f"\n  DRY_RUN=1: no se escribió nada (el turno quedaría en {turno}).")
            return 0

        team.handoff_turno = turno
        db.add(team)
        db.commit()
        print(f"\n  ✓ {len(pendientes)} chat(s) reasignados. Próximo turno: "
              f"{asesores[turno % len(asesores)]}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
