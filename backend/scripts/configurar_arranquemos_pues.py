"""Configura la cuenta de Arranquemos Pues: correo admin, asesores y permisos.

Qué hace (todo idempotente, se puede re-ejecutar):
  1. Cambia el correo de la cuenta ADMIN al nuevo, si todavía está el viejo.
  2. Le da al owner el permiso `can_manage_billing` (módulo de pagos).
  3. Deja la rotación de asesores en ["Julián", "Camila"], para que el bot
     reparta los chats por turnos.
  4. Crea (o actualiza) la cuenta de ASESOR con permisos restringidos:
     puede responder mensajes y ver reportes; NO puede tocar pagos, ni el
     equipo, ni los bots. Desconectar la cuenta de WhatsApp ya es owner-only
     por `get_current_owner_membership`, así que el rol `agent` lo cubre.
  5. Le quita al paso `handoff` del bot el asesor fijo, para que entre a
     repartir por turnos (`crud.siguiente_asesor`). Un paso que conserve su
     `assignee` sigue mandando sobre el turno: eso es a propósito.

La contraseña del asesor NO va en el código (este repo es PÚBLICO, regla 8):
se pasa por la variable de entorno `ASESOR_PASSWORD`.

Uso:
    # Local (el proyecto de compose se llama `wati`)
    docker compose -p wati exec -T -e ASESOR_PASSWORD='...' backend \\
        python scripts/configurar_arranquemos_pues.py

    # Producción (RDS). OJO: los overrides de ECS quedan en CloudTrail, así que
    # por ahí NUNCA viaja una contraseña en claro — se manda el hash bcrypt ya
    # calculado en ASESOR_PASSWORD_HASH.
    ./backend/scripts/rds_exec.sh backend/scripts/configurar_arranquemos_pues.py \\
        ASESOR_PASSWORD_HASH='$2b$12$...'
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

from sqlalchemy.orm.attributes import flag_modified  # type: ignore

from app import crud, models  # type: ignore
from app.database import SessionLocal  # type: ignore


CORREO_VIEJO = "arranquemospues.contacto@gmail.com"
CORREO_ADMIN = "arranquemospues.marketing@gmail.com"
CORREO_ASESOR = "arranquemospues.asesor@gmail.com"
NOMBRE_ASESOR = "Asesor Arranquemos Pues"
ASESORES = ["Julián", "Camila"]


def _password_hash() -> str:
    """El hash a guardar, venga de una contraseña en claro o ya hasheada."""
    ya_hasheada = os.environ.get("ASESOR_PASSWORD_HASH")
    if ya_hasheada:
        return ya_hasheada
    plana = os.environ.get("ASESOR_PASSWORD")
    if not plana:
        sys.exit(
            "Falta ASESOR_PASSWORD (o ASESOR_PASSWORD_HASH en producción): "
            "la contraseña se pasa por entorno, no va en el código."
        )
    return crud.pwd_context.hash(plana)


def main() -> int:
    db = SessionLocal()
    try:
        # ── 1. Correo de la cuenta admin ────────────────────────────────
        admin = crud.get_user_by_email(db, CORREO_ADMIN)
        if admin is None:
            admin = crud.get_user_by_email(db, CORREO_VIEJO)
            if admin is None:
                print(
                    f"ERROR: no existe ni {CORREO_ADMIN} ni {CORREO_VIEJO} en esta base."
                )
                return 1
            admin.correo = CORREO_ADMIN
            db.add(admin)
            db.commit()
            db.refresh(admin)
            print(f"  ✓ correo admin: {CORREO_VIEJO} → {CORREO_ADMIN}")
        else:
            print(f"  · correo admin ya era {CORREO_ADMIN}")

        membresia_admin = crud.get_membership_for_user(db, admin)
        if membresia_admin is None:
            print("ERROR: la cuenta admin no pertenece a ningún team.")
            return 1
        team = db.query(models.Team).get(membresia_admin.team_id)

        # ── 2. Permiso de pagos para el admin ───────────────────────────
        permisos_admin = crud.permissions_dict(membresia_admin)
        if not permisos_admin.get("can_manage_billing"):
            permisos_admin["can_manage_billing"] = True
            crud.set_member_permissions(db, membresia_admin, permisos_admin)
            print("  ✓ admin: permiso can_manage_billing")
        else:
            print("  · admin ya tenía can_manage_billing")

        # ── 3. Rotación de asesores ─────────────────────────────────────
        if list(team.asesores_rotacion or []) != ASESORES:
            team.asesores_rotacion = ASESORES
            flag_modified(team, "asesores_rotacion")
            db.add(team)
            db.commit()
            print(f"  ✓ rotación de asesores: {' → '.join(ASESORES)}")
        else:
            print(f"  · rotación ya era {' → '.join(ASESORES)}")

        # ── 4. Cuenta de asesor ─────────────────────────────────────────
        asesor = crud.get_user_by_email(db, CORREO_ASESOR)
        if asesor is None:
            asesor = models.User(
                nombre=NOMBRE_ASESOR,
                correo=CORREO_ASESOR,
                tipo_documento="CC",
                documento="ASESORAP01",
                hashed_password=_password_hash(),
            )
            db.add(asesor)
            db.commit()
            db.refresh(asesor)
            print(f"  ✓ usuario asesor creado: {CORREO_ASESOR}")
        else:
            asesor.hashed_password = _password_hash()
            db.add(asesor)
            db.commit()
            print(f"  · usuario asesor ya existía: contraseña actualizada")

        membresia_asesor = crud.get_membership_for_user(db, asesor)
        if membresia_asesor is None:
            membresia_asesor = crud.add_member_to_team(
                db, team, asesor,
                role="agent",
                permissions=models.ASESOR_DEFAULT_PERMISSIONS,
            )
            print(f"  ✓ asesor agregado al team {team.id} con rol agent")
        else:
            crud.set_member_permissions(
                db, membresia_asesor, models.ASESOR_DEFAULT_PERMISSIONS
            )
            print("  · permisos del asesor reaplicados")

        # ── 5. El handoff del bot deja de fijar un asesor ───────────────
        bots = (
            db.query(models.Bot).filter(models.Bot.user_id == admin.id).all()
        )
        tocados = 0
        for bot in bots:
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
                    tocados += 1
        if tocados:
            db.commit()
            print(f"  ✓ {tocados} paso(s) handoff sin asesor fijo → entran al turno")
        else:
            print("  · ningún paso handoff tenía asesor fijo")

        # ── Resumen ─────────────────────────────────────────────────────
        print("\nResumen del team:")
        for m in crud.get_team_members(db, team.id):
            permisos = crud.permissions_dict(m)
            activos = sorted(k for k, v in permisos.items() if v)
            print(f"  · {m.user.correo:<42} rol={m.role:<6} permisos={', '.join(activos) or '—'}")
        print(f"  · rotación de handoff: {' → '.join(team.asesores_rotacion or [])}")
        print(f"  · créditos de mensajes: {team.message_credits}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
