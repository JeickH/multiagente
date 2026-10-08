"""Crea (o pone al día) el bot 2 de Arranquemos Pues y le da el 50 % del tráfico.

El bot 2 es la **variante B** del bot 1: mismo plan, mismos productos, mismos
medios y mismos reenganches, con otro guion (`bot_contexts/demo_viajes_b.md`)
y las banderas de `app/data/bot_viajes_b.py`. Las conversaciones nuevas se
reparten entre los dos (A/B) y cada contacto se queda con el bot que le tocó.

**Por defecto simula**: imprime lo que haría y no escribe nada. Para escribir,
`APLICAR=1`. Idempotente: la segunda corrida con `APLICAR=1` no cambia nada y
en particular **no reinicia `reparto_desde`** (el conteo del A/B sigue).

Qué hace, en orden:
  1. Encuentra al dueño (`BOT_OWNER_EMAIL`, obligatoria y sin valor por
     defecto) y su membresía de owner; de ahí sale el team, nunca de otro lado.
  2. Bot A = el **único** bot LLM `default` y activo del dueño con
     `context_key == "demo_viajes"` y sin `variante`. Si hay 0 o varios, aborta.
  3. Bot B = el del dueño con `variante == "B"`; si no existe se crea con
     `crud.duplicar_bot` (copia pasos, productos y recordatorios de A).
  4. `llm_config` de B = exactamente `LLM_CONFIG_B` + una **lista blanca** de
     llaves operativas de A (`LLAVES_DE_A`). Nada más de A pasa a B: ni
     credenciales ni banderas encendidas a mano.
  5. Instrucciones de B = el `.md` validado con `crud.validar_instrucciones`.
     Si en la base ya hay otro texto (alguien lo editó desde la app), no se
     pisa sin `FORZAR=1`. La versión sube solo si el texto cambia.
  6. Verifica que B vea los mismos productos que A y tenga los mismos minutos
     de recordatorios. Si no, aborta antes de darle tráfico.
  7. Backfill: las conversaciones del team que nunca entraron a un reparto
     (`bot_asignado_id IS NULL`) quedan con A, con `bot_asignado_at =
     created_at`. Son contactos que ya hablaron con el bot 1 y se quedan con
     él (decisión del CEO, 7-oct-2026). Como su `bot_asignado_at` es anterior
     al reparto, no cuentan en los porcentajes.
  8. Reparto con `crud.guardar_reparto`, en la misma transacción que el
     backfill, **solo si no está ya**: A 50 / B 50 por defecto.
     `REPARTO_B=0` es la vuelta atrás (A 100 / B 0): las conversaciones de B
     vuelven a A en su siguiente mensaje. Si la cuenta tiene otro reparto
     (lo cambió alguien desde la app), no se pisa sin `FORZAR=1`.

La salida no lleva correos completos ni teléfonos, y de `llm_config` solo
imprime nombres de llaves, nunca valores (en RDS esto queda en CloudWatch).

Corre vía `rds_exec.sh`, que manda el archivo como cuerpo de un `python -c`:
por eso solo importa de `app.*` y busca `/app`. **Nunca correr un `seed_bot_*`
contra RDS**: borran todos los bots del dueño.

Uso:
    # Local (el proyecto de compose se llama `wati`; el contenedor no monta
    # `scripts/`, por eso va por stdin)
    docker compose -p wati exec -T -e BOT_OWNER_EMAIL='<correo del dueño>' \\
        backend python - < backend/scripts/crear_bot_viajes_b.py
    # ... y para escribir, agregar -e APLICAR=1

    # Producción (RDS): la imagen desplegada tiene que traer ya
    # `app/data/bot_viajes_b.py` y `app/bot_contexts/demo_viajes_b.md`.
    ./backend/scripts/rds_exec.sh backend/scripts/crear_bot_viajes_b.py \\
        BOT_OWNER_EMAIL='<correo del dueño>'                 # simulación
    ./backend/scripts/rds_exec.sh backend/scripts/crear_bot_viajes_b.py \\
        BOT_OWNER_EMAIL='<correo del dueño>' APLICAR=1       # escribe

Variables:
    BOT_OWNER_EMAIL  obligatoria.
    APLICAR=1        escribe (sin ella, solo simula).
    FORZAR=1         pisa instrucciones editadas en la app o un reparto distinto.
    REPARTO_B=<0..100>  porcentaje de B (default 50; A recibe el resto).
    BOT_B_NOMBRE     nombre del bot B al crearlo (default: el de A + " · B").
"""
from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

# Se busca el archivo y no la carpeta: desde `/` el directorio `/app` parece el
# paquete `app` (namespace package) y el import se iría por ahí.
_CANDIDATOS = ["/app"]
if "__file__" in globals():  # no existe vía `python -c` (rds_exec.sh) ni por stdin
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app import crud, models  # type: ignore  # noqa: E402
from app.data.bot_viajes_b import (  # type: ignore  # noqa: E402
    CONTEXT_KEY_B,
    FLAGS_VARIANTE,
    LLM_CONFIG_B,
    instrucciones_b,
)


CONTEXT_KEY_A = "demo_viajes"
VARIANTE_B = FLAGS_VARIANTE["variante"]

#: Las ÚNICAS llaves de la config de A que pasan a B (revisión de seguridad
#: S7). Son las que dicen cómo está *operando* el bot en esa base y que el
#: archivo de datos no conoce: de dónde saca los precios y qué modelo usa. Para
#: que el A/B compare guiones, B tiene que operar igual que A. Una credencial
#: de A NO pasa: el bot de viajes no necesita ninguna, y si algún día la
#: necesita, se agrega aquí con su nombre, a propósito.
LLAVES_DE_A: Tuple[str, ...] = ("fuente_datos", "model_id")

assert not set(LLAVES_DE_A) & set(LLM_CONFIG_B), (
    "Una llave de la lista blanca ya la declara LLM_CONFIG_B"
)


# ---------------------------------------------------------------------------
# Piezas puras
# ---------------------------------------------------------------------------

def leer_config(bot) -> Dict[str, Any]:
    try:
        cfg = json.loads(getattr(bot, "llm_config", None) or "{}")
    except (ValueError, TypeError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def es_bot_a(cfg: Dict[str, Any]) -> bool:
    return cfg.get("context_key") == CONTEXT_KEY_A and not cfg.get("variante")


def es_bot_b(cfg: Dict[str, Any]) -> bool:
    return cfg.get("variante") == VARIANTE_B


def config_b(cfg_a: Dict[str, Any]) -> Dict[str, Any]:
    """`LLM_CONFIG_B` + la lista blanca de A. Exactamente eso, nada más."""
    nueva = copy.deepcopy(LLM_CONFIG_B)
    for clave in LLAVES_DE_A:
        if clave in cfg_a:
            nueva[clave] = copy.deepcopy(cfg_a[clave])
    return nueva


def llaves_distintas(antes: Dict[str, Any], despues: Dict[str, Any]) -> List[str]:
    """Nombres de las llaves que cambian (entran, salen o cambian de valor)."""
    return sorted(
        k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k)
    )


def minutos_seguimiento(cfg: Dict[str, Any]) -> Tuple[Any, ...]:
    """Lo que tiene que coincidir entre A y B para que el reenganche no sea una
    diferencia más del experimento: minutos de cada recordatorio, el silencio
    inicial y la etiqueta de abandono."""
    seg = cfg.get("seguimiento") or {}
    if not isinstance(seg, dict):
        return ()
    return (
        seg.get("minutos"),
        seg.get("etiqueta_abandono"),
        tuple((r or {}).get("minutos") for r in (seg.get("recordatorios") or [])),
    )


def enmascarar_correo(correo: str) -> str:
    usuario, _, dominio = (correo or "").partition("@")
    tld = dominio.rsplit(".", 1)[-1] if "." in dominio else ""
    return f"{usuario[:2]}***@***.{tld}" if tld else f"{usuario[:2]}***"


def reparto_objetivo(a_id: int, b_id: int, pct_b: int) -> List[Tuple[int, int]]:
    return [(a_id, 100 - pct_b), (b_id, pct_b)]


def reparto_actual(bots: List[models.Bot]) -> Dict[int, int]:
    """{bot_id: pct} de los bots del dueño que hoy entran al reparto."""
    return {b.id: int(b.reparto_pct) for b in bots if int(b.reparto_pct or 0) > 0}


def reparto_ya_esta(actual: Dict[int, int], objetivo: List[Tuple[int, int]]) -> bool:
    return actual == {bid: pct for bid, pct in objetivo if pct > 0}


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def _productos(db, bot_id: int) -> List[Tuple[int, bool]]:
    return sorted(
        (int(e.producto_id), bool(e.activo))
        for e in db.query(models.BotProductoBot)
        .filter(models.BotProductoBot.bot_id == bot_id)
        .all()
    )


def _recordatorios(db, bot_id: int) -> List[Tuple[int, int, bool]]:
    return sorted(
        (int(r.orden or 0), int(r.minutos or 0), bool(r.activo))
        for r in db.query(models.BotRecordatorio)
        .filter(models.BotRecordatorio.bot_id == bot_id)
        .all()
    )


def _sin_asignar(db, team_id: int):
    return db.query(models.Conversation).filter(
        models.Conversation.team_id == team_id,
        models.Conversation.bot_asignado_id.is_(None),
    )


def _backfill(db, team_id: int, bot_a_id: int, antes_de=None) -> int:
    """Asigna a A las conversaciones del team sin bot. No hace commit."""
    q = _sin_asignar(db, team_id)
    if antes_de is not None:
        q = q.filter(models.Conversation.created_at < antes_de)
    return q.update(
        {
            models.Conversation.bot_asignado_id: bot_a_id,
            models.Conversation.bot_asignado_at: models.Conversation.created_at,
        },
        synchronize_session=False,
    )


# ---------------------------------------------------------------------------
# Programa
# ---------------------------------------------------------------------------

def ejecutar(
    db,
    *,
    correo: str,
    aplicar: bool,
    forzar: bool = False,
    pct_b: int = 50,
    nombre_b: Optional[str] = None,
    out: Callable[[str], None] = print,
) -> int:
    """Todo el trabajo, con la sesión inyectada (los tests usan SQLite).

    Devuelve el código de salida: 0 bien, 1 abortó (sin escribir lo que falta),
    2 mal invocado.
    """
    correo = (correo or "").strip()
    if not correo:
        out("ERROR: falta BOT_OWNER_EMAIL (el correo del dueño). No tiene valor por defecto.")
        return 2
    if not (0 <= int(pct_b) <= 100):
        out("ERROR: REPARTO_B tiene que ser un entero entre 0 y 100.")
        return 2

    modo = "APLICAR" if aplicar else "SIMULACIÓN (no se escribe nada; APLICAR=1 para escribir)"
    out(f"=== Bot 2 (variante {VARIANTE_B}) de viajes · {modo}")
    out(f"Cuenta: {enmascarar_correo(correo)}")

    # 1) Dueño y su membresía de owner: el team sale de aquí y de nada más.
    owner = db.query(models.User).filter(models.User.correo == correo).first()
    if owner is None:
        out("ERROR: no existe ese usuario en esta base.")
        return 1
    membresias = (
        db.query(models.TeamMember)
        .filter(models.TeamMember.user_id == owner.id, models.TeamMember.role == "owner")
        .all()
    )
    if len(membresias) != 1:
        out(f"ERROR: se esperaba una membresía de owner y hay {len(membresias)}.")
        return 1
    miembro = membresias[0]
    team_id = miembro.team_id
    if crud._resolve_owner_user_id(db, miembro) != owner.id:
        out("ERROR: el dueño del team no es este usuario.")
        return 1

    # 2) y 3) Bots A y B.
    bots = (
        db.query(models.Bot)
        .filter(models.Bot.user_id == owner.id)
        .order_by(models.Bot.id)
        .all()
    )
    candidatos_a = [
        b for b in bots
        if b.engine == "llm"
        and b.trigger_type == models.BOT_TRIGGER_DEFAULT
        and b.status == "active"
        and es_bot_a(leer_config(b))
    ]
    if len(candidatos_a) != 1:
        out(
            f"ERROR: se esperaba exactamente un bot A (LLM, default, activo, "
            f"context_key='{CONTEXT_KEY_A}' sin variante) y hay {len(candidatos_a)}"
            + (f": {', '.join(str(b.id) for b in candidatos_a)}" if candidatos_a else "")
            + "."
        )
        return 1
    a = candidatos_a[0]
    if a.user_id != owner.id or (a.team_id is not None and a.team_id != team_id):
        out("ERROR: el bot A no pertenece a la cuenta de este dueño.")
        return 1
    cfg_a = leer_config(a)

    candidatos_b = [b for b in bots if es_bot_b(leer_config(b))]
    if len(candidatos_b) > 1:
        out(
            f"ERROR: hay {len(candidatos_b)} bots con variante {VARIANTE_B} "
            f"({', '.join(str(b.id) for b in candidatos_b)}); debería haber uno."
        )
        return 1
    b = candidatos_b[0] if candidatos_b else None
    if b is not None and (b.user_id != owner.id or b.team_id != team_id):
        out("ERROR: el bot B no pertenece a la cuenta de este dueño.")
        return 1
    if b is None and pct_b == 0:
        out("ERROR: REPARTO_B=0 es la vuelta atrás y no hay bot B que sacar del reparto.")
        return 1

    out(f"Bot A: {a.id} · {a.name}")
    out(f"Bot B: {f'{b.id} · {b.name}' if b else '(no existe: se crea duplicando A)'}")

    # 5) Instrucciones.
    try:
        guion = crud.validar_instrucciones(instrucciones_b())
    except crud.RepartoInvalido as exc:
        out(f"ERROR: el guion {CONTEXT_KEY_B}.md no es válido: {exc}")
        return 1
    bloqueos: List[str] = []
    cambia_guion = b is not None and (b.instrucciones or "").strip() != guion
    if cambia_guion:
        if (b.instrucciones or "").strip() and not forzar:
            bloqueos.append(
                "las instrucciones de B en la base difieren del archivo (¿se "
                "editaron desde la app?). Revisa y corre con FORZAR=1 para pisarlas."
            )
        out(f"· instrucciones: se actualizan al archivo ({len(guion)} caracteres)")
    elif b is None:
        out(f"· instrucciones: las del archivo ({len(guion)} caracteres), versión 1")
    else:
        out(f"· instrucciones: ya iguales al archivo (versión {b.instrucciones_version})")

    # 4) Config.
    objetivo = config_b(cfg_a)
    heredadas = [k for k in LLAVES_DE_A if k in cfg_a]
    out(f"· llaves heredadas de A: {', '.join(heredadas) if heredadas else '(ninguna)'}")
    cfg_b_antes = leer_config(b) if b is not None else {}
    cambian = llaves_distintas(cfg_b_antes, objetivo) if b is not None else []
    if b is not None:
        out(f"· llm_config: {'cambian ' + ', '.join(cambian) if cambian else 'ya al día'}")
    out(f"· banderas de B: {', '.join(sorted(FLAGS_VARIANTE))}")

    # 6) Lo que tiene que ser igual entre A y B. La config se compara contra
    # el objetivo: es lo que B va a tener.
    if minutos_seguimiento(cfg_a) != minutos_seguimiento(objetivo):
        bloqueos.append(
            "los minutos de los recordatorios de A (en la base) no coinciden "
            "con los del archivo: corre primero actualizar_bot_viajes.py."
        )
    if (cfg_a.get("media") or {}) != (objetivo.get("media") or {}):
        out(
            "AVISO: el catálogo de medios de A (en la base) no es el del archivo; "
            "B usa el del archivo. actualizar_bot_viajes.py los iguala."
        )
    prod_a, rec_a = _productos(db, a.id), _recordatorios(db, a.id)
    out(f"· productos de A: {len(prod_a)} · recordatorios propios de A: {len(rec_a)}")
    if b is not None:
        if _productos(db, b.id) != prod_a:
            bloqueos.append("B no ve los mismos productos que A.")
        if _recordatorios(db, b.id) != rec_a:
            bloqueos.append("B no tiene los mismos recordatorios propios que A.")

    # 7) y 8) Backfill y reparto.
    pendientes = _sin_asignar(db, team_id).count()
    out(f"· conversaciones sin bot asignado (van a A): {pendientes}")
    actual = reparto_actual(bots)
    b_id_plan = b.id if b is not None else -1
    objetivo_reparto = reparto_objetivo(a.id, b_id_plan, int(pct_b))
    ya_esta = b is not None and reparto_ya_esta(actual, objetivo_reparto)
    # "Sin reparto" incluye A al 100 % solo: es como queda tras la vuelta atrás
    # (REPARTO_B=0), y volver al 50/50 desde ahí no es pisar el reparto de nadie.
    sin_reparto = actual in ({}, {a.id: 100})
    otro_reparto = not sin_reparto and not ya_esta and int(pct_b) != 0
    if b is not None and (b.status != "active" or b.trigger_type != models.BOT_TRIGGER_DEFAULT):
        bloqueos.append("B no está activo o no atiende por defecto: no puede entrar al reparto.")
    if otro_reparto and not forzar:
        bloqueos.append(
            f"la cuenta ya tiene otro reparto ({_pcts(actual)}); FORZAR=1 para "
            "reemplazarlo."
        )
    if ya_esta:
        out(f"· reparto: ya está ({_pcts(actual)}); no se toca reparto_desde")
    else:
        out(
            f"· reparto: {_pcts(actual) or '(ninguno)'} → A {100 - int(pct_b)} % / "
            f"B {int(pct_b)} %"
        )

    if bloqueos:
        for motivo in bloqueos:
            out(f"BLOQUEO: {motivo}")
        out("No se escribió nada.")
        return 1
    if not aplicar:
        out("Simulación terminada: no se escribió nada.")
        return 0

    # ---- Escritura ----
    if b is None:
        b = crud.duplicar_bot(
            db, miembro, a,
            name=(nombre_b or f"{a.name} · B")[:120],
            instrucciones=guion,
        )
        # `duplicar_bot` copia la config de A tal cual; se reemplaza ENTERA por
        # el objetivo, así que no queda nada de A fuera de la lista blanca.
        b.llm_config = json.dumps(objetivo, ensure_ascii=False)
        db.add(b)
        db.commit()
        out(f"✓ bot B creado: {b.id}")
    else:
        if cambia_guion:
            b.instrucciones = guion
            b.instrucciones_version = int(b.instrucciones_version or 0) + 1
            out(f"✓ instrucciones actualizadas (versión {b.instrucciones_version})")
        if cambian:
            b.llm_config = json.dumps(objetivo, ensure_ascii=False)
            out(f"✓ llm_config actualizado ({', '.join(cambian)})")
        if cambia_guion or cambian:
            db.add(b)
            db.commit()

    # Verificación después de escribir: con B recién creado es la primera vez
    # que se puede comparar.
    if leer_config(b) != objetivo:
        out("ERROR: la config de B no quedó igual al objetivo. No se toca el reparto.")
        return 1
    if _productos(db, b.id) != prod_a or _recordatorios(db, b.id) != rec_a:
        out("ERROR: B no quedó con los mismos productos/recordatorios que A. No se toca el reparto.")
        return 1

    # Backfill + reparto: una transacción. `guardar_reparto` hace el commit
    # (y el rollback si algo falla, que deshace también el backfill).
    objetivo_reparto = reparto_objetivo(a.id, b.id, int(pct_b))
    ya_esta = reparto_ya_esta(reparto_actual(_bots_del_dueño(db, owner.id)), objetivo_reparto)
    try:
        asignadas = _backfill(db, team_id, a.id)
        if ya_esta:
            db.commit()
        else:
            crud.guardar_reparto(db, miembro, objetivo_reparto)
    except crud.RepartoInvalido as exc:
        db.rollback()
        out(f"ERROR: el reparto no se pudo guardar: {exc}")
        return 1
    except Exception:
        db.rollback()
        raise
    out(f"✓ backfill: {asignadas} conversación(es) asignadas a A")

    db.refresh(a)
    db.refresh(b)
    if not ya_esta:
        # Las que entraron entre el backfill y el commit del reparto todavía
        # no tenían reparto: las atendió A y se quedan con A.
        tarde = _backfill(db, team_id, a.id, antes_de=a.reparto_desde)
        db.commit()
        if tarde:
            out(f"✓ backfill tardío: {tarde} conversación(es) más asignadas a A")
        out(f"✓ reparto guardado: A {a.reparto_pct or 0} % / B {b.reparto_pct or 0} %")

    out("\nResumen:")
    cfg_b = leer_config(b)
    out(f"  · A {a.id}: reparto {a.reparto_pct or 0} %, desde {a.reparto_desde}")
    out(
        f"  · B {b.id}: reparto {b.reparto_pct or 0} %, desde {b.reparto_desde}, "
        f"context_key={cfg_b.get('context_key')}, variante={cfg_b.get('variante')}, "
        f"instrucciones v{b.instrucciones_version} ({len(b.instrucciones or '')} car.)"
    )
    out(
        f"  · productos iguales ({len(prod_a)}), recordatorios iguales "
        f"(minutos {minutos_seguimiento(cfg_b)[2]})"
    )
    out(f"  · conversaciones del team sin bot asignado: {_sin_asignar(db, team_id).count()}")
    return 0


def _bots_del_dueño(db, owner_id: int) -> List[models.Bot]:
    return db.query(models.Bot).filter(models.Bot.user_id == owner_id).all()


def _pcts(actual: Dict[int, int]) -> str:
    return ", ".join(f"bot {bid}: {pct} %" for bid, pct in sorted(actual.items()))


def main() -> int:
    from app.database import SessionLocal  # type: ignore

    try:
        pct_b = int(os.environ.get("REPARTO_B", "50"))
    except ValueError:
        print("ERROR: REPARTO_B tiene que ser un entero entre 0 y 100.")
        return 2
    db = SessionLocal()
    try:
        return ejecutar(
            db,
            correo=os.environ.get("BOT_OWNER_EMAIL", ""),
            aplicar=os.environ.get("APLICAR") == "1",
            forzar=os.environ.get("FORZAR") == "1",
            pct_b=pct_b,
            nombre_b=os.environ.get("BOT_B_NOMBRE") or None,
        )
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
