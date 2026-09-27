"""Cierra y marca las conversaciones asignadas que llevan una semana sin actividad.

Regla operativa de la cuenta de Arranquemos Pues (pedido del CEO, 25-sep-2026):
una conversación que está **asignada a un asesor**, en estado `pending` y sin un
solo mensaje desde hace más de una semana, ya no es un pendiente: es un caso
cerrado que ensucia la bandeja y esconde los que sí están vivos.

Qué hace:
  1. Pone `status='closed'` en las que cumplen la condición.
  2. Les deja una **nota interna** de cierre. La nota es el marcador con el que
     los reportes las distinguen de las que cerró el propio flujo del bot, y
     guarda quién había hablado de último — que es el dato que dice si alguien
     quedó esperando respuesta.

Qué NO hace, a propósito:
  · No toca `assigned_to` ni `etiqueta`. Son las dos señales con las que el
    asesor entiende por qué le llegó un chat frío, y borrarlas al cerrar
    convertiría el cierre en una pérdida de información.
  · No toca `last_message_at`. Esa columna es la que mide la antigüedad del
    abandono; si la nota de cierre la moviera, la conversación "rejuvenecería"
    y en la corrida siguiente ya no calificaría. La nota se inserta con su
    propio `created_at` y la columna se deja como estaba.

Idempotente: una conversación que ya tiene la nota de cierre no se vuelve a
tocar, así que se puede correr todos los días sin duplicar nada.

OJO (limitación conocida del motor, no de este script): una conversación en
manos de una persona ya no la vuelve a tomar el bot — `bot_runner
._reabrir_conversacion` corta en seco cuando `assigned_to != 'bot'`. Si uno de
estos clientes vuelve a escribir, el mensaje entra pero la conversación no
regresa sola a la bandeja de pendientes. Mientras eso siga así, conviene
revisar las cerradas con actividad reciente.

Uso:
    # Ver qué haría, sin escribir nada (por defecto)
    ./backend/scripts/rds_exec.sh backend/scripts/cerrar_inactivas_arranquemos.py

    # Aplicar
    ./backend/scripts/rds_exec.sh backend/scripts/cerrar_inactivas_arranquemos.py APLICAR=1

    # Cambiar el umbral (por defecto 7 días) o la cuenta
    ... APLICAR=1 DIAS=14 TEAM=5
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from sqlalchemy import text  # type: ignore
from app.database import SessionLocal  # type: ignore

TEAM = int(os.environ.get("TEAM", "5"))
DIAS = int(os.environ.get("DIAS", "7"))
APLICAR = os.environ.get("APLICAR", "").strip() not in ("", "0", "false", "no")

# Prefijo de la nota de cierre. Es el marcador que buscan los reportes: si
# cambia, hay que cambiarlo también en el generador de los dashboards.
MARCA = "🔒 *Cerrada por inactividad*"

db = SessionLocal()
ahora = datetime.utcnow()
limite = ahora - timedelta(days=DIAS)

# Candidatas: asignadas a una persona, pendientes, calladas hace más de N días
# y sin la nota de cierre puesta todavía.
candidatas = db.execute(text("""
    SELECT c.id, c.assigned_to, c.etiqueta, c.last_message_at
    FROM conversations c
    WHERE c.team_id = :team
      AND c.status = 'pending'
      AND c.assigned_to IS NOT NULL
      AND c.assigned_to <> 'bot'
      AND c.last_message_at < :limite
      AND NOT EXISTS (
          SELECT 1 FROM messages m
          WHERE m.conversation_id = c.id
            AND m.message_type = 'nota_interna'
            AND m.content LIKE :marca
      )
    ORDER BY c.last_message_at
"""), {"team": TEAM, "limite": limite, "marca": MARCA + "%"}).fetchall()

print(f"umbral: {DIAS} días (sin actividad desde antes de {limite:%Y-%m-%d %H:%M} UTC)")
print(f"candidatas: {len(candidatas)}")

if not candidatas:
    print("nada que hacer.")
    raise SystemExit(0)


def quien_hablo_ultimo(cid: int) -> str:
    """Quién dejó el último mensaje real (las notas internas no cuentan)."""
    fila = db.execute(text("""
        SELECT direction, sent_by_user_id FROM messages
        WHERE conversation_id = :cid AND message_type <> 'nota_interna'
        ORDER BY created_at DESC, id DESC LIMIT 1
    """), {"cid": cid}).fetchone()
    if not fila:
        return "sin mensajes"
    if fila[0] == "inbound":
        return "el cliente quedó esperando"
    return "el asesor" if fila[1] else "el bot"


resumen: dict[str, int] = {}
for cid, asignado, etiqueta, ultimo in candidatas:
    quien = quien_hablo_ultimo(cid)
    resumen[quien] = resumen.get(quien, 0) + 1
    dias = (ahora - ultimo).days
    if not APLICAR:
        continue
    nota = (f"{MARCA}\n"
            f"Sin actividad desde hace {dias} días. Último en escribir: {quien}.\n"
            f"Quedó asignada a {asignado} y conserva su etiqueta; se cerró para sacarla "
            f"de la bandeja de pendientes.")
    db.execute(text("""
        INSERT INTO messages (conversation_id, direction, content, message_type, status, created_at)
        VALUES (:cid, 'outbound', :nota, 'nota_interna', 'sent', :ahora)
    """), {"cid": cid, "nota": nota, "ahora": ahora})
    # `last_message_at` se deja intacto a propósito: mide la antigüedad del abandono.
    db.execute(text("UPDATE conversations SET status = 'closed' WHERE id = :cid"), {"cid": cid})

if APLICAR:
    db.commit()
    print(f"CERRADAS Y MARCADAS: {len(candidatas)}")
else:
    print("(simulacro: no se escribió nada; correr con APLICAR=1)")

print("quién había hablado de último:")
for k, v in sorted(resumen.items(), key=lambda kv: -kv[1]):
    print(f"   {k:32s} {v:4d}")
