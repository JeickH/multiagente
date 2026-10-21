"""Limpieza de los bots de demo inactivos (Sprint 33, #638).

Cada prospecto de `glomacx.com/demo` deja un `Bot` (y 3 `bot_productos`) en la
cuenta de demos. Con el CEO de acuerdo (#618 → Sprint 33), los bots que llevan
`DEMO_BOT_RETENCION_HORAS` (default 48) sin uso se borran; los datos del
prospecto **no**:

- `leads` no se toca nunca (nombre, correo, teléfono, autorización).
- La fila de `demos` se conserva entera; antes de borrar se le copian los
  productos (`productos_snapshot`) y el consumo (`uso_resumen`), porque
  `bot_llm_decisions` y las filas de precios se van en cascada con el bot. Se
  marca `bot_eliminado_at`; `demos.bot_id` queda en NULL por su `SET NULL`.

**Doble candado por bot** (si falla cualquiera, no se toca y queda un warning):
1. `bots.user_id` es el dueño de `DEMO_OWNER_EMAIL` (la cuenta de demos);
2. es del team de esa cuenta;
3. su `llm_config` tiene `demo: true`;
4. su canal es `demo` (nunca whatsapp/web de un cliente);
5. y está enlazado a ESA fila de `demos` (`demos.bot_id`).

La retención nunca baja de `MIN_RETENCION_HORAS` (6) y el lote va de 1 a 1.000.

Los productos que se borran son solo los enlazados a ese bot, del team de la
cuenta de demos y que no estén enlazados a ningún otro bot. Todo por demo en su
propia transacción; un lote acotado por corrida; logs con ids internos y
conteos, sin PII.

Orden por demo (acordado con experto-bd, #637), en UNA transacción con
`lock_timeout`:
1. re-lee la fila de `demos` con `FOR UPDATE` y vuelve a exigir que siga
   inactiva (pudo llegar un turno entre la selección y el borrado);
2. candados del bot (cuenta, team, `demo: true`, enlace);
3. snapshot de productos y `uso_resumen`;
4. guarda los ids de sus productos ANTES de borrar el bot (el vínculo cae en
   cascada con él);
5. UPDATE de `demos`;
6. borra `bot_recordatorios` del bot (no tiene FK: quedaría huérfana);
7. borra el bot (las cascadas hacen el resto; los hijos también se borran
   explícitos para que valga igual sin claves foráneas);
8. borra los productos guardados en 4 que ya no enlaza ningún bot.

`ultima_actividad_at` NULL no se limpia: falla hacia conservar. La migración
la rellena y el código la escribe al crear la demo, en cada turno y en cada
evento; `updated_at` NO sirve como actividad (este limpiador escribe la fila).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, func, text
from sqlalchemy.orm import Session

from .. import models

logger = logging.getLogger(__name__)

LOTE_POR_CORRIDA = 200
LOTE_MAXIMO = 1000
#: Piso de la retención (#642, M1): ni una env mal puesta ni un `--horas 0`
#: pueden borrar los bots de demos que se están usando ahora mismo.
MIN_RETENCION_HORAS = 6.0
_PROPIETARIO_DEFAULT = "demos@glomacx.com"

#: Precios de lista de Bedrock (USD por millón de tokens) para el costo
#: ESTIMADO del uso de una demo. Si el modelo no está en la tabla, el costo se
#: deja en None: mejor sin dato que con uno inventado.
_PRECIOS_USD_MTOK: Dict[str, Dict[str, float]] = {
    "haiku-4-5": {"in": 1.0, "out": 5.0, "cache_read": 0.10, "cache_write": 1.25},
    "sonnet-4-5": {"in": 3.0, "out": 15.0, "cache_read": 0.30, "cache_write": 3.75},
}


def retencion_horas() -> float:
    try:
        horas = float(os.getenv("DEMO_BOT_RETENCION_HORAS", "") or 48)
    except ValueError:
        return 48.0
    if horas != horas:          # NaN
        return 48.0
    return max(MIN_RETENCION_HORAS, horas)


def _correo_propietario() -> str:
    return (os.getenv("DEMO_OWNER_EMAIL") or _PROPIETARIO_DEFAULT).strip().lower()


@dataclass
class ResultadoLimpieza:
    candidatas: int = 0
    borradas: List[int] = field(default_factory=list)          # ids internos de demos
    saltadas: List[Tuple[int, str]] = field(default_factory=list)
    simular: bool = False

    def resumen(self) -> Dict[str, Any]:
        return {
            "candidatas": self.candidatas,
            "borradas": len(self.borradas),
            "saltadas": len(self.saltadas),
            "simular": self.simular,
            "demo_ids": self.borradas,
            "motivos_saltadas": [m for _, m in self.saltadas],
        }


def _precio_de(model_id: str) -> Optional[Dict[str, float]]:
    for clave, precio in _PRECIOS_USD_MTOK.items():
        if clave in (model_id or ""):
            return precio
    return None


def _uso_resumen(db: Session, bot_id: int, demo: models.Demo) -> Dict[str, Any]:
    """Consumo del bot desde `bot_llm_decisions`, por modelo, con costo estimado."""
    D = models.BotLlmDecision
    filas = (
        db.query(
            D.model_id,
            func.count(D.id),
            func.coalesce(func.sum(D.rounds), 0),
            func.coalesce(func.sum(D.tokens_in), 0),
            func.coalesce(func.sum(D.tokens_out), 0),
            func.coalesce(func.sum(D.cache_read), 0),
            func.coalesce(func.sum(D.cache_write), 0),
            func.sum(case((D.tokens_in.is_(None), 1), else_=0)),
            func.sum(case((D.failsafe.is_(True), 1), else_=0)),
            func.sum(case((D.escalated_to.isnot(None), 1), else_=0)),
            func.avg(D.latency_ms),
            func.min(D.created_at),
            func.max(D.created_at),
        )
        .filter(D.bot_id == bot_id)
        .group_by(D.model_id)
        .all()
    )
    por_modelo = []
    costo_total: Optional[float] = 0.0
    tot = {"decisiones": 0, "rondas": 0, "tokens_in": 0, "tokens_out": 0,
           "cache_read": 0, "cache_write": 0, "sin_tokens": 0, "failsafe": 0,
           "escalados": 0}
    suma_latencia, n_latencia = 0.0, 0
    primera: Optional[datetime] = None
    ultima: Optional[datetime] = None
    for (model_id, n, rondas, t_in, t_out, c_read, c_write,
         sin_tokens, failsafe, escalados, lat, desde, hasta) in filas:
        n, rondas, t_in, t_out, c_read, c_write = (
            int(n or 0), int(rondas or 0), int(t_in or 0), int(t_out or 0),
            int(c_read or 0), int(c_write or 0),
        )
        sin_tokens, failsafe, escalados = int(sin_tokens or 0), int(failsafe or 0), int(escalados or 0)
        if lat is not None:
            suma_latencia += float(lat) * n
            n_latencia += n
        desde, hasta = _como_fecha(desde), _como_fecha(hasta)
        if desde and (primera is None or desde < primera):
            primera = desde
        if hasta and (ultima is None or hasta > ultima):
            ultima = hasta
        precio = _precio_de(model_id or "")
        costo = None
        if precio is not None:
            costo = round(
                (t_in * precio["in"] + t_out * precio["out"]
                 + c_read * precio["cache_read"] + c_write * precio["cache_write"]) / 1e6,
                6,
            )
        if costo is None:
            costo_total = None
        elif costo_total is not None:
            costo_total += costo
        por_modelo.append({
            "modelo": model_id, "decisiones": n, "rondas": rondas,
            "tokens_in": t_in, "tokens_out": t_out,
            "cache_read": c_read, "cache_write": c_write, "sin_tokens": sin_tokens,
            "costo_usd_estimado": costo,
        })
        for k, v in (("decisiones", n), ("rondas", rondas), ("tokens_in", t_in),
                     ("tokens_out", t_out), ("cache_read", c_read), ("cache_write", c_write),
                     ("sin_tokens", sin_tokens), ("failsafe", failsafe), ("escalados", escalados)):
            tot[k] += v
    return {
        "turnos": int(demo.turnos or 0),
        **tot,
        "modelos": [m["modelo"] for m in por_modelo if m["modelo"]],
        "por_modelo": por_modelo,
        "latencia_ms_promedio": round(suma_latencia / n_latencia) if n_latencia else None,
        "primera_decision_at": primera.isoformat() if primera else None,
        "ultima_decision_at": ultima.isoformat() if ultima else None,
        # Las decisiones sin tokens registrados no suman al costo: si hay
        # alguna, el estimado se queda corto y `sin_tokens` lo dice.
        "costo_usd_estimado": round(costo_total, 6) if costo_total is not None else None,
        "nota_costo": "precios de lista de Bedrock; estimado, no facturado",
    }


def _como_fecha(v: Any) -> Optional[datetime]:
    if v is None or isinstance(v, datetime):
        return v
    try:  # SQLite devuelve texto en los agregados
        return datetime.fromisoformat(str(v))
    except ValueError:
        return None


def _productos_del_bot(db: Session, bot_id: int, team_id: int) -> List[models.BotProducto]:
    return (
        db.query(models.BotProducto)
        .join(models.BotProductoBot, models.BotProductoBot.producto_id == models.BotProducto.id)
        .filter(
            models.BotProductoBot.bot_id == bot_id,
            models.BotProducto.team_id == team_id,
        )
        .order_by(models.BotProductoBot.orden, models.BotProducto.id)
        .all()
    )


def productos_snapshot(db: Session, productos: List[models.BotProducto]) -> List[Dict[str, Any]]:
    """Lo que el panel muestra de cada producto: nombre, resumen, ficha y el
    precio plano de su primera fila."""
    if not productos:
        return []
    filas = (
        db.query(models.BotProductoFila)
        .filter(models.BotProductoFila.producto_id.in_([p.id for p in productos]))
        .order_by(models.BotProductoFila.producto_id, models.BotProductoFila.orden)
        .all()
    )
    primera: Dict[int, models.BotProductoFila] = {}
    for f in filas:
        primera.setdefault(f.producto_id, f)
    salida = []
    for p in productos:
        valores = (primera[p.id].valores or {}) if p.id in primera else {}
        precio = valores.get("precio")
        salida.append({
            "nombre": p.nombre,
            "resumen": p.resumen,
            "ficha": p.instrucciones,
            "precio_cop": int(precio) if isinstance(precio, (int, float))
            and not isinstance(precio, bool) else None,
            "unidad_precio": str(valores["unidad"]) if valores.get("unidad") else None,
        })
    return salida


def _es_bot_de_demo(
    bot: Optional[models.Bot], owner_id: int, team_id: Optional[int], demo: models.Demo
) -> Optional[str]:
    """None si pasa el doble candado; si no, el motivo (código, sin PII)."""
    if bot is None:
        return "bot_inexistente"
    if bot.user_id != owner_id:
        return "bot_de_otra_cuenta"
    if team_id is None or bot.team_id != team_id:
        return "bot_de_otro_team"
    try:
        cfg = json.loads(bot.llm_config or "{}")
    except (ValueError, TypeError):
        cfg = {}
    if not isinstance(cfg, dict) or cfg.get("demo") is not True:
        return "bot_sin_flag_demo"
    if bot.channels != "demo":
        return "bot_sin_canal_demo"
    if demo.bot_id != bot.id:
        return "bot_no_enlazado"
    return None


def _candidatas(db: Session, corte: datetime, lote: int) -> List[models.Demo]:
    D = models.Demo
    return (
        db.query(D)
        .filter(
            D.bot_id.isnot(None),
            D.bot_eliminado_at.is_(None),
            D.estado != models.DEMO_ESTADO_GENERANDO,
            # NULL no entra (falla hacia conservar) y así usa el índice
            # parcial `ix_demos_bot_vivo_actividad`.
            D.ultima_actividad_at < corte,
        )
        .order_by(D.id)
        .limit(lote)
        .all()
    )


def limpiar_bots_demo_inactivos(
    db: Session,
    ahora: Optional[datetime] = None,
    horas: Optional[float] = None,
    simular: bool = False,
    lote: int = LOTE_POR_CORRIDA,
) -> ResultadoLimpieza:
    ahora = ahora or datetime.utcnow()
    horas = retencion_horas() if horas is None else float(horas)
    if not horas >= MIN_RETENCION_HORAS:          # también atrapa NaN
        horas = MIN_RETENCION_HORAS
    lote = max(1, min(int(lote), LOTE_MAXIMO))
    corte = ahora - timedelta(hours=horas)
    resultado = ResultadoLimpieza(simular=simular)

    owner = (
        db.query(models.User)
        .filter(models.User.correo == _correo_propietario())
        .first()
    )
    if owner is None:
        logger.warning("limpieza_demos: no existe la cuenta dueña de las demos; no se borra nada")
        return resultado
    team = (
        db.query(models.Team)
        .filter(models.Team.owner_user_id == owner.id)
        .order_by(models.Team.id)
        .first()
    )

    candidatas = [(d.id, d.bot_id) for d in _candidatas(db, corte, lote)]
    db.rollback()          # suelta la lectura; cada demo va en su transacción
    resultado.candidatas = len(candidatas)
    for demo_id, bot_id in candidatas:
        try:
            motivo = _procesar(db, demo_id, bot_id, owner.id, team.id if team else None,
                               corte, ahora, simular)
            if simular:
                db.rollback()
            else:
                db.commit()
        except Exception:  # noqa: BLE001 — una demo que falla no frena el lote
            db.rollback()
            logger.exception("limpieza_demos: falló demo=%s bot=%s", demo_id, bot_id)
            motivo = "error"
        if motivo is None:
            resultado.borradas.append(demo_id)
        elif motivo == "ya_no_inactiva":
            resultado.saltadas.append((demo_id, motivo))
        else:
            if motivo != "error":
                logger.warning("limpieza_demos: demo=%s bot=%s no se toca motivo=%s",
                               demo_id, bot_id, motivo)
            resultado.saltadas.append((demo_id, motivo))

    logger.info(
        "limpieza_demos: candidatas=%s borradas=%s saltadas=%s simular=%s horas=%s demo_ids=%s",
        resultado.candidatas, len(resultado.borradas), len(resultado.saltadas),
        simular, horas, resultado.borradas[:50],
    )
    return resultado


def _procesar(
    db: Session, demo_id: int, bot_id: int, owner_id: int, team_id: Optional[int],
    corte: datetime, ahora: datetime, simular: bool,
) -> Optional[str]:
    """Una demo, en la transacción del caller. None = borrado (o borrable, si
    `simular`); si no, el motivo por el que no se tocó."""
    if not simular and db.get_bind().dialect.name == "postgresql":
        # Si un turno tiene la fila tomada, mejor saltarla que esperar.
        db.execute(text("SET LOCAL lock_timeout = '3s'"))
    D = models.Demo
    q = db.query(D).filter(
        D.id == demo_id,
        D.bot_id == bot_id,
        D.bot_eliminado_at.is_(None),
        D.estado != models.DEMO_ESTADO_GENERANDO,
        D.ultima_actividad_at < corte,
    )
    demo = (q if simular else q.with_for_update()).first()
    if demo is None:
        return "ya_no_inactiva"          # llegó un turno o ya la limpió otra corrida
    bot = db.query(models.Bot).filter(models.Bot.id == bot_id).first()
    motivo = _es_bot_de_demo(bot, owner_id, team_id, demo)
    if motivo is not None or simular:
        return motivo
    _borrar_bot_de_demo(db, demo, bot, team_id, ahora)
    return None


def _borrar_bot_de_demo(
    db: Session, demo: models.Demo, bot: models.Bot, team_id: int, ahora: datetime
) -> None:
    """Pasos 3 a 8 del orden del módulo, sin commit."""
    # 3 y 4. Snapshot, consumo y los ids de sus productos, antes de borrar nada.
    productos = _productos_del_bot(db, bot.id, team_id)
    ids_productos = [p.id for p in productos]
    snapshot = productos_snapshot(db, productos)
    uso = _uso_resumen(db, bot.id, demo)

    # 5. La fila de la demo (lo único que se escribe en `demos`).
    demo.productos_snapshot = snapshot
    demo.uso_resumen = uso
    demo.bot_eliminado_at = ahora
    demo.bot_id = None                  # lo mismo que hará el SET NULL
    db.flush()

    # 6. Sin FK a bots: si no se borra a mano queda huérfana.
    db.query(models.BotRecordatorio).filter(
        models.BotRecordatorio.team_id == team_id,
        models.BotRecordatorio.bot_id == bot.id,
    ).delete(synchronize_session=False)

    # 7. El bot. Sus hijos van en cascada; además se borran explícitos para que
    #    el resultado no dependa de que las FK estén activas.
    sesiones = [s for (s,) in db.query(models.BotSession.id)
                .filter(models.BotSession.bot_id == bot.id).all()]
    if sesiones:
        db.query(models.BotPendingAction).filter(
            models.BotPendingAction.session_id.in_(sesiones)
        ).delete(synchronize_session=False)
    for modelo in (models.BotLlmDecision, models.BotProductoBot, models.IntencionCompra):
        db.query(modelo).filter(modelo.bot_id == bot.id).delete(synchronize_session=False)
    for modelo in (models.BotSession, models.BotStep):
        db.query(modelo).filter(modelo.bot_id == bot.id).delete(synchronize_session=False)
    db.query(models.Demo).filter(models.Demo.bot_id == bot.id).update(
        {models.Demo.bot_id: None}, synchronize_session=False)
    db.query(models.Bot).filter(
        models.Bot.id == bot.id,
        models.Bot.team_id == team_id,
        models.Bot.user_id == bot.user_id,
    ).delete(synchronize_session=False)

    # 8. Sus productos que ya no enlaza ningún bot, del team de demos.
    if ids_productos:
        aun_enlazados = {
            pid for (pid,) in db.query(models.BotProductoBot.producto_id)
            .filter(models.BotProductoBot.producto_id.in_(ids_productos)).all()
        }
        huerfanos = [
            pid for (pid,) in db.query(models.BotProducto.id).filter(
                models.BotProducto.id.in_(ids_productos),
                models.BotProducto.team_id == team_id,
            ).all()
            if pid not in aun_enlazados
        ]
        if huerfanos:
            for modelo in (models.BotProductoFila, models.BotProductoVariante,
                           models.BotProductoMedio, models.BotProductoAlias,
                           models.BotProductoCarga):
                db.query(modelo).filter(modelo.producto_id.in_(huerfanos)).delete(
                    synchronize_session=False)
            db.query(models.BotProducto).filter(
                models.BotProducto.id.in_(huerfanos),
                models.BotProducto.team_id == team_id,
            ).delete(synchronize_session=False)
