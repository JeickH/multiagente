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
  6. Enciende en los bots LLM de la cuenta los flags de continuidad (#377):
     `seguimiento`, `recordar_nombre` y `retomar`. Sólo agrega las claves que
     falten — si alguien ajustó los minutos desde el panel, no se los pisa.

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
from app.data.bot_viajes import LLM_CONFIG  # type: ignore
from app.database import SessionLocal  # type: ignore


CORREO_VIEJO = "arranquemospues.contacto@gmail.com"
CORREO_ADMIN = "arranquemospues.marketing@gmail.com"
# Un solo login para los tres asesores, por decisión del CEO (19-ago-2026): se
# conectan a la vez desde esa cuenta y a veces el admin también. El JWT no
# guarda estado en el servidor, así que N sesiones simultáneas del mismo correo
# conviven sin pisarse — no hay nada que habilitar para eso.
CORREO_ASESOR = "arranquemospues.ventas@outlook.com"
NOMBRE_ASESOR = "Asesores Arranquemos Pues"
DOCUMENTO_ASESOR = "ASESORAP02"
# Cuenta de asesor anterior. Se deja viva a propósito: desactivarla sin avisar
# dejaría por fuera a quien la esté usando ahora mismo. El script solo la
# reporta para que el CEO decida.
CORREO_ASESOR_PREVIO = "arranquemospues.asesor@gmail.com"
# A quién le caen los chats que el bot escala. Con un solo nombre no hay turnos:
# `crud.siguiente_asesor` corta en el `len(asesores) == 1` y devuelve siempre a
# Alexandra, sin tocar `handoff_turno`.
#
# Antes eran ["Camila", "Julián", "Alexandra"] repartiendo por turnos. Lo cambió
# el CEO el 29-ago-2026: la atención quedó en una sola persona. Volver a repartir
# es agregar los nombres acá y correr el script; los chats YA asignados no se
# mueven solos, para eso está `reasignar_asesores_arranquemos.py`.
ASESORES = ["Alexandra"]

# Flags de continuidad (#377). Los valores se importan de la fuente de verdad
# del bot de viajes para que no puedan quedar en desacuerdo con lo que despacha
# el actualizador: dos copias de la misma política terminan en desacuerdo.
FLAGS_CONTINUIDAD = {
    clave: LLM_CONFIG[clave]
    for clave in ("seguimiento", "recordar_nombre", "retomar")
    if clave in LLM_CONFIG
}


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
                documento=DOCUMENTO_ASESOR,
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

        # ── 6. Flags de continuidad del bot LLM (#377) ──────────────────
        # Por qué acá y no sólo en `app/data/bot_viajes.py`: ese módulo es la
        # fuente de verdad del bot de viajes, pero sólo se aplica cuando se
        # corre el seed o el actualizador (que reescriben `llm_config` entera).
        # Este script se puede correr sobre la cuenta tal como está, sin tocar
        # medios ni caminos, que es lo que se quiere para encender un flag.
        encendidos = 0
        for bot in bots:
            if getattr(bot, "engine", "flow") != "llm":
                continue
            try:
                cfg_llm = json.loads(bot.llm_config or "{}")
            except (ValueError, TypeError):
                print(f"  ⚠ el bot {bot.id} tiene llm_config ilegible: no se toca")
                continue
            if not isinstance(cfg_llm, dict):
                continue
            faltantes = [k for k in FLAGS_CONTINUIDAD if k not in cfg_llm]
            if not faltantes:
                continue
            for clave in faltantes:
                cfg_llm[clave] = FLAGS_CONTINUIDAD[clave]
            bot.llm_config = json.dumps(cfg_llm, ensure_ascii=False)
            db.add(bot)
            encendidos += 1
            print(f"  ✓ bot {bot.id}: {', '.join(faltantes)}")
        if encendidos:
            db.commit()
        else:
            print("  · los bots LLM ya tenían los flags de continuidad")

        # ── 7. Aviso sobre la cuenta de asesor anterior ─────────────────
        previo = crud.get_user_by_email(db, CORREO_ASESOR_PREVIO)
        if previo is not None and previo.id != asesor.id:
            print(
                f"\n  ⚠ OJO: sigue activa la cuenta de asesor anterior "
                f"{CORREO_ASESOR_PREVIO}. Este script NO la toca. Si ya nadie "
                f"la usa, pídele al equipo que la desactive."
            )

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
