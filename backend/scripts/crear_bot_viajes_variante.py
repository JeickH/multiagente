"""Crea (o pone al día) una variante del bot de viajes y ajusta el reparto A/B/C.

Generaliza `crear_bot_viajes_b.py` (que sigue sirviendo para el bot 2 solo,
con su 50/50) a cualquier variante registrada en `VARIANTES` y a un reparto de
varios bots. Es la herramienta para el bot 3 (variante C, «embudo guiado») y
el reparto final 34 / 33 / 33 entre el bot 1, el bot 2 y el bot 3.

**Por defecto simula**: imprime lo que haría y no escribe nada. `APLICAR=1`
escribe. Idempotente: la segunda corrida no cambia nada y **no reinicia
`reparto_desde`** si el reparto ya es el pedido.

Qué hace, en orden:
  1. Dueño (`BOT_OWNER_EMAIL`, obligatoria y sin valor por defecto) y su
     membresía de owner; el team sale de ahí y de nada más.
  2. Bot A = el **único** bot LLM `default` y activo del dueño con
     `context_key == "demo_viajes"` y sin `variante`. Si hay 0 o varios, aborta.
  3. Bot de la variante pedida (`VARIANTE=B|C`) = el del dueño con esa
     `variante`; si no existe se crea con `crud.duplicar_bot` (copia pasos,
     productos y recordatorios de A).
  4. Su `llm_config` = exactamente la config de la variante (`VARIANTES`) +
     la lista blanca de llaves operativas de A (`LLAVES_DE_A`). Nada más de A
     pasa: ni credenciales ni banderas encendidas a mano.
  5. Instrucciones = el `.md` de la variante validado con
     `crud.validar_instrucciones`. Si en la base hay otro texto (editado desde
     la app), no se pisa sin `FORZAR=1`. La versión sube solo si cambia.
  6. Verifica que la variante vea los mismos productos que A, con los mismos
     recordatorios propios y los mismos minutos de reenganche. Si no, aborta
     antes de darle tráfico.
  7. Backfill: las conversaciones del team sin bot asignado quedan con A, con
     `bot_asignado_at = created_at` (contactos que ya hablaron con el bot 1).
  8. Reparto (`REPARTO`, p. ej. `"A=34,B=33,C=33"`), con `crud.guardar_reparto`
     en la misma transacción que el backfill y **solo si cambia**. Las letras
     son A (bot 1) y las variantes; cada variante con porcentaje > 0 tiene que
     existir. Si el reparto vigente incluye bots que no son A ni una variante
     de viajes, no se pisa sin `FORZAR=1`.

Vuelta atrás: `REPARTO="A=50,B=50,C=0"` (o `A=100,B=0,C=0`). La variante en 0
deja de recibir conversaciones nuevas, y las que tenía vuelven a repartirse en
su siguiente mensaje. No se borra nada.

La salida no lleva correos completos ni teléfonos, y de `llm_config` solo
imprime nombres de llaves, nunca valores (en RDS queda en CloudWatch).

Corre vía `rds_exec.sh`, que manda el archivo como cuerpo de un `python -c`:
por eso solo importa de `app.*` y busca `/app`. **Nunca correr un
`seed_bot_*` contra RDS**: borran todos los bots del dueño.

Uso:
    # Local (proyecto de compose `wati`; el contenedor no monta `scripts/`)
    docker compose -p wati exec -T -e BOT_OWNER_EMAIL='<correo del dueño>' \\
        -e VARIANTE=C -e REPARTO='A=34,B=33,C=33' \\
        backend python - < backend/scripts/crear_bot_viajes_variante.py
    # ... y para escribir, agregar -e APLICAR=1

    # Producción (RDS): la imagen desplegada tiene que traer ya
    # `app/data/bot_viajes_c.py` y `app/bot_contexts/demo_viajes_c.md`.
    ./backend/scripts/rds_exec.sh backend/scripts/crear_bot_viajes_variante.py \\
        BOT_OWNER_EMAIL='<correo del dueño>' VARIANTE=C REPARTO='A=34,B=33,C=33'
    # ... revisar la simulación y repetir con APLICAR=1

Variables:
    BOT_OWNER_EMAIL     obligatoria.
    VARIANTE            obligatoria: B o C.
    REPARTO             default: "A=34,B=33,C=33" para C, "A=50,B=50" para B.
    APLICAR=1           escribe (sin ella, solo simula).
    FORZAR=1            pisa instrucciones editadas en la app o un reparto ajeno.
    BOT_NOMBRE          nombre del bot nuevo al crearlo (default: A + " · <letra>").
"""
from __future__ import annotations

import copy
import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

_CANDIDATOS = ["/app"]
if "__file__" in globals():  # no existe vía `python -c` (rds_exec.sh) ni por stdin
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app import crud, models  # type: ignore  # noqa: E402
from app.data import bot_viajes_b, bot_viajes_c  # type: ignore  # noqa: E402


CONTEXT_KEY_A = "demo_viajes"

#: Variantes conocidas: letra → (config, función que lee su guion).
VARIANTES: Dict[str, Tuple[Dict[str, Any], Callable[[], str]]] = {
    "B": (bot_viajes_b.LLM_CONFIG_B, bot_viajes_b.instrucciones_b),
    "C": (bot_viajes_c.LLM_CONFIG_C, bot_viajes_c.instrucciones_c),
}

REPARTO_DEFAULT = {"B": "A=50,B=50", "C": "A=34,B=33,C=33"}

#: Las ÚNICAS llaves de la config de A que pasan a la variante (revisión de
#: seguridad S7 del bot 2). Dicen cómo opera el bot en esa base: de dónde
#: saca los precios y qué modelo usa. Ninguna credencial.
LLAVES_DE_A: Tuple[str, ...] = ("fuente_datos", "model_id")

for _letra, (_cfg, _) in VARIANTES.items():
    assert _cfg.get("variante") == _letra, f"la config de {_letra} no dice variante={_letra}"
    assert not set(LLAVES_DE_A) & set(_cfg), f"{_letra} ya declara una llave de la lista blanca"


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


def config_variante(letra: str, cfg_a: Dict[str, Any]) -> Dict[str, Any]:
    """La config de la variante + la lista blanca de A. Exactamente eso."""
    nueva = copy.deepcopy(VARIANTES[letra][0])
    for clave in LLAVES_DE_A:
        if clave in cfg_a:
            nueva[clave] = copy.deepcopy(cfg_a[clave])
    return nueva


def llaves_distintas(antes: Dict[str, Any], despues: Dict[str, Any]) -> List[str]:
    return sorted(k for k in set(antes) | set(despues) if antes.get(k) != despues.get(k))


def minutos_seguimiento(cfg: Dict[str, Any]) -> Tuple[Any, ...]:
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


def parsear_reparto(texto: str) -> Dict[str, int]:
    """`"A=34,B=33,C=33"` → `{"A": 34, "B": 33, "C": 33}`. Lanza ValueError
    si una letra no es A ni una variante conocida, se repite, el porcentaje
    no es un entero de 0 a 100, falta A, o no suma 100."""
    salida: Dict[str, int] = {}
    for parte in (texto or "").split(","):
        if not parte.strip():
            continue
        letra, sep, valor = parte.partition("=")
        letra = letra.strip().upper()
        if not sep or (letra != "A" and letra not in VARIANTES):
            raise ValueError(f"letra desconocida en REPARTO: {letra or parte.strip()!r}")
        if letra in salida:
            raise ValueError(f"letra repetida en REPARTO: {letra}")
        try:
            pct = int(valor.strip())
        except ValueError:
            raise ValueError(f"porcentaje inválido para {letra}") from None
        if not 0 <= pct <= 100:
            raise ValueError(f"porcentaje fuera de 0..100 para {letra}")
        salida[letra] = pct
    if "A" not in salida:
        raise ValueError("REPARTO tiene que incluir A (el bot 1)")
    if sum(salida.values()) != 100:
        raise ValueError("los porcentajes de REPARTO deben sumar 100")
    return salida


def reparto_actual(bots: List[models.Bot]) -> Dict[int, int]:
    return {b.id: int(b.reparto_pct) for b in bots if int(b.reparto_pct or 0) > 0}


def reparto_ya_esta(actual: Dict[int, int], objetivo: List[Tuple[int, int]]) -> bool:
    return actual == {bid: pct for bid, pct in objetivo if pct > 0}


def _pcts(actual: Dict[int, int]) -> str:
    return ", ".join(f"bot {bid}: {pct} %" for bid, pct in sorted(actual.items()))


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def _productos(db, bot_id: int) -> List[Tuple[int, bool]]:
    return sorted(
        (int(e.producto_id), bool(e.activo))
        for e in db.query(models.BotProductoBot).filter(models.BotProductoBot.bot_id == bot_id)
    )


def _recordatorios(db, bot_id: int) -> List[Tuple[int, int, bool]]:
    return sorted(
        (int(r.orden or 0), int(r.minutos or 0), bool(r.activo))
        for r in db.query(models.BotRecordatorio).filter(models.BotRecordatorio.bot_id == bot_id)
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
    variante: str,
    reparto: Optional[str] = None,
    aplicar: bool,
    forzar: bool = False,
    nombre: Optional[str] = None,
    out: Callable[[str], None] = print,
) -> int:
    """Todo el trabajo, con la sesión inyectada (los tests usan SQLite).

    0 bien · 1 abortó (sin escribir lo que falta) · 2 mal invocado.
    """
    correo = (correo or "").strip()
    if not correo:
        out("ERROR: falta BOT_OWNER_EMAIL (el correo del dueño). No tiene valor por defecto.")
        return 2
    letra = (variante or "").strip().upper()
    if letra not in VARIANTES:
        out(f"ERROR: VARIANTE tiene que ser una de: {', '.join(sorted(VARIANTES))}.")
        return 2
    try:
        pedido = parsear_reparto(reparto or REPARTO_DEFAULT[letra])
    except ValueError as exc:
        out(f"ERROR: {exc}.")
        return 2
    if letra not in pedido:
        out(f"ERROR: REPARTO tiene que incluir la variante {letra} (aunque sea {letra}=0).")
        return 2

    modo = "APLICAR" if aplicar else "SIMULACIÓN (no se escribe nada; APLICAR=1 para escribir)"
    out(f"=== Variante {letra} del bot de viajes · {modo}")
    out(f"Cuenta: {enmascarar_correo(correo)}")
    out("Reparto pedido: " + ", ".join(f"{k} {v} %" for k, v in pedido.items()))

    # 1) Dueño y membresía de owner.
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

    # 2) y 3) Bots.
    bots = db.query(models.Bot).filter(models.Bot.user_id == owner.id).order_by(models.Bot.id).all()
    candidatos_a = [
        b for b in bots
        if b.engine == "llm" and b.trigger_type == models.BOT_TRIGGER_DEFAULT
        and b.status == "active" and es_bot_a(leer_config(b))
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

    por_letra: Dict[str, models.Bot] = {}
    for otra in VARIANTES:
        encontrados = [b for b in bots if leer_config(b).get("variante") == otra]
        if len(encontrados) > 1:
            out(
                f"ERROR: hay {len(encontrados)} bots con variante {otra} "
                f"({', '.join(str(b.id) for b in encontrados)}); debería haber uno."
            )
            return 1
        if encontrados:
            if encontrados[0].user_id != owner.id or encontrados[0].team_id != team_id:
                out(f"ERROR: el bot {otra} no pertenece a la cuenta de este dueño.")
                return 1
            por_letra[otra] = encontrados[0]
    v = por_letra.get(letra)
    for otra, pct in pedido.items():
        if otra not in ("A", letra) and pct > 0 and otra not in por_letra:
            out(f"ERROR: REPARTO le da {pct} % a la variante {otra}, que no existe en esta cuenta.")
            return 1
    if v is None and pedido[letra] == 0:
        out(f"ERROR: la variante {letra} no existe y REPARTO la deja en 0: no hay nada que hacer.")
        return 1

    out(f"Bot A: {a.id} · {a.name}")
    for otra, bot in sorted(por_letra.items()):
        out(f"Bot {otra}: {bot.id} · {bot.name}")
    if v is None:
        out(f"Bot {letra}: (no existe: se crea duplicando A)")

    # 5) Instrucciones.
    try:
        guion = crud.validar_instrucciones(VARIANTES[letra][1]())
    except crud.RepartoInvalido as exc:
        out(f"ERROR: el guion de la variante {letra} no es válido: {exc}")
        return 1
    bloqueos: List[str] = []
    cambia_guion = v is not None and (v.instrucciones or "").strip() != guion
    if cambia_guion:
        if (v.instrucciones or "").strip() and not forzar:
            bloqueos.append(
                f"las instrucciones de {letra} en la base difieren del archivo (¿se "
                "editaron desde la app?). Revisa y corre con FORZAR=1 para pisarlas."
            )
        out(f"· instrucciones: se actualizan al archivo ({len(guion)} caracteres)")
    elif v is None:
        out(f"· instrucciones: las del archivo ({len(guion)} caracteres), versión 1")
    else:
        out(f"· instrucciones: ya iguales al archivo (versión {v.instrucciones_version})")

    # 4) Config.
    objetivo = config_variante(letra, cfg_a)
    heredadas = [k for k in LLAVES_DE_A if k in cfg_a]
    out(f"· llaves heredadas de A: {', '.join(heredadas) if heredadas else '(ninguna)'}")
    cambian = llaves_distintas(leer_config(v), objetivo) if v is not None else []
    if v is not None:
        out(f"· llm_config: {'cambian ' + ', '.join(cambian) if cambian else 'ya al día'}")
    banderas = sorted(k for k in objetivo if k not in cfg_a or k == "variante")
    out(f"· banderas de {letra}: {', '.join(banderas)}")

    # 6) Lo que tiene que ser igual entre A y la variante.
    if minutos_seguimiento(cfg_a) != minutos_seguimiento(objetivo):
        bloqueos.append(
            "los minutos de los recordatorios de A (en la base) no coinciden "
            "con los del archivo: corre primero actualizar_bot_viajes.py."
        )
    if (cfg_a.get("media") or {}) != (objetivo.get("media") or {}):
        out(
            "AVISO: el catálogo de medios de A (en la base) no es el del archivo; "
            "la variante usa el del archivo. actualizar_bot_viajes.py los iguala."
        )
    prod_a, rec_a = _productos(db, a.id), _recordatorios(db, a.id)
    out(f"· productos de A: {len(prod_a)} · recordatorios propios de A: {len(rec_a)}")
    if v is not None:
        if _productos(db, v.id) != prod_a:
            bloqueos.append(f"{letra} no ve los mismos productos que A.")
        if _recordatorios(db, v.id) != rec_a:
            bloqueos.append(f"{letra} no tiene los mismos recordatorios propios que A.")
        if v.status != "active" or v.trigger_type != models.BOT_TRIGGER_DEFAULT:
            if pedido[letra] > 0:
                bloqueos.append(f"{letra} no está activo o no atiende por defecto: no puede entrar al reparto.")

    # 7) y 8) Backfill y reparto.
    out(f"· conversaciones sin bot asignado (van a A): {_sin_asignar(db, team_id).count()}")
    actual = reparto_actual(bots)
    gestionados = {a.id} | {b.id for b in por_letra.values()}
    ajenos = sorted(set(actual) - gestionados)
    if ajenos and not forzar:
        bloqueos.append(
            f"el reparto vigente incluye bots que no son de viajes "
            f"({', '.join(str(i) for i in ajenos)}); FORZAR=1 para reemplazarlo."
        )

    def _objetivo_reparto(id_v: int) -> List[Tuple[int, int]]:
        ids = {"A": a.id, letra: id_v, **{k: b.id for k, b in por_letra.items() if k != letra}}
        return [(ids[k], pct) for k, pct in pedido.items() if k in ids]

    ya_esta = v is not None and reparto_ya_esta(actual, _objetivo_reparto(v.id))
    if ya_esta:
        out(f"· reparto: ya está ({_pcts(actual)}); no se toca reparto_desde")
    else:
        out(
            f"· reparto: {_pcts(actual) or '(ninguno)'} → "
            + ", ".join(f"{k} {p} %" for k, p in pedido.items())
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
    if v is None:
        v = crud.duplicar_bot(
            db, miembro, a, name=(nombre or f"{a.name} · {letra}")[:120], instrucciones=guion,
        )
        # `duplicar_bot` copia la config de A tal cual; se reemplaza ENTERA.
        v.llm_config = json.dumps(objetivo, ensure_ascii=False)
        db.add(v)
        db.commit()
        out(f"✓ bot {letra} creado: {v.id}")
    else:
        if cambia_guion:
            v.instrucciones = guion
            v.instrucciones_version = int(v.instrucciones_version or 0) + 1
            out(f"✓ instrucciones actualizadas (versión {v.instrucciones_version})")
        if cambian:
            v.llm_config = json.dumps(objetivo, ensure_ascii=False)
            out(f"✓ llm_config actualizado ({', '.join(cambian)})")
        if cambia_guion or cambian:
            db.add(v)
            db.commit()

    if leer_config(v) != objetivo:
        out(f"ERROR: la config de {letra} no quedó igual al objetivo. No se toca el reparto.")
        return 1
    if _productos(db, v.id) != prod_a or _recordatorios(db, v.id) != rec_a:
        out(f"ERROR: {letra} no quedó con los mismos productos/recordatorios que A. No se toca el reparto.")
        return 1

    objetivo_reparto = _objetivo_reparto(v.id)
    todos = db.query(models.Bot).filter(models.Bot.user_id == owner.id).all()
    ya_esta = reparto_ya_esta(reparto_actual(todos), objetivo_reparto)
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
    if not ya_esta:
        tarde = _backfill(db, team_id, a.id, antes_de=a.reparto_desde)
        db.commit()
        if tarde:
            out(f"✓ backfill tardío: {tarde} conversación(es) más asignadas a A")
        out("✓ reparto guardado")

    out("\nResumen:")
    for etiqueta, bot in [("A", a)] + sorted({**por_letra, letra: v}.items()):
        db.refresh(bot)
        cfg = leer_config(bot)
        extra = (
            f", context_key={cfg.get('context_key')}, variante={cfg.get('variante')}, "
            f"instrucciones v{bot.instrucciones_version} ({len(bot.instrucciones or '')} car.)"
            if etiqueta != "A" else ""
        )
        out(f"  · {etiqueta} {bot.id}: reparto {bot.reparto_pct or 0} %, desde {bot.reparto_desde}{extra}")
    out(
        f"  · productos iguales ({len(prod_a)}), recordatorios iguales "
        f"(minutos {minutos_seguimiento(leer_config(v))[2]})"
    )
    out(f"  · conversaciones del team sin bot asignado: {_sin_asignar(db, team_id).count()}")
    return 0


def main() -> int:
    from app.database import SessionLocal  # type: ignore

    db = SessionLocal()
    try:
        return ejecutar(
            db,
            correo=os.environ.get("BOT_OWNER_EMAIL", ""),
            variante=os.environ.get("VARIANTE", ""),
            reparto=os.environ.get("REPARTO") or None,
            aplicar=os.environ.get("APLICAR") == "1",
            forzar=os.environ.get("FORZAR") == "1",
            nombre=os.environ.get("BOT_NOMBRE") or None,
        )
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
