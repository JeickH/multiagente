"""Motor de ejecución de bots (puro / stateless).

Responsabilidad única: dada una definición de bot + un estado + input
opcional del usuario, calcular la próxima tanda de acciones y el nuevo
estado. NO habla con Meta, NO habla con la DB, NO habla con el frontend.

Se invoca desde dos lugares:

  1) `POST /bots/{id}/simulate` (Sprint 9)
     El frontend mantiene `state` en memoria (pop-up de prueba) y envía
     `{state, user_input}` en cada turno. Las acciones devueltas se pintan
     como globos del chat.

  2) Futuro: webhook de Meta al recibir un mensaje entrante.
     El estado vivirá en tabla `bot_sessions` y las acciones se traducirán
     a `services.meta_whatsapp.send_text_message(...)`. El core del motor
     es el mismo para ambos casos — no reescribir lógica.

ESTADO (dict):
    {
        "current_step_id": int | None,   # None al inicio / final
        "variables": dict,               # respuestas acumuladas del user
    }

ACCIÓN (dict):
    {"type": "say",       "payload": {"text": "..."}}
    {"type": "say_media", "payload": {"caption": "...", "media_type": "image"}}
    {"type": "ask",       "payload": {"prompt": "...", "options": [...]}}
    {"type": "pause",     "payload": {"seconds": 30}}
    {"type": "end",       "payload": {"text": "..."}}

El motor consume pasos hasta encontrar uno que REQUIERE input del
usuario (`wait_input`) o un `end`. Cuando encuentra `wait_input`, emite
una acción `ask` y espera a ser invocado de nuevo con `user_input`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .. import models


# Tope defensivo: un bot con ciclos o mal configurado no debe colgar el servidor.
MAX_STEPS_PER_TURN = 50


def _new_state(first_step_id: Optional[int]) -> Dict[str, Any]:
    return {"current_step_id": first_step_id, "variables": {}}


def _step_map(bot: models.Bot) -> Dict[int, models.BotStep]:
    return {s.id: s for s in bot.steps}


def _config(step: models.BotStep) -> Dict[str, Any]:
    import json
    if not step.config:
        return {}
    try:
        data = json.loads(step.config)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_condition_next(
    step: models.BotStep, config: Dict[str, Any], user_input: Optional[str]
) -> Optional[int]:
    """Para un step de tipo `condition`, resuelve el próximo step_id según
    el `user_input`. MVP: matcheo por substrings simple con las keys de
    `config.branches`. Si nada matchea, avanza al `next_step_id` del paso.
    """
    branches = config.get("branches") or {}
    if isinstance(branches, dict) and user_input:
        low = user_input.lower()
        for key in branches.keys():
            if key.lower() in low:
                # La branch puede apuntar a un step_id explícito; si es texto
                # descriptivo, por ahora seguimos el flujo lineal.
                target = branches[key]
                if isinstance(target, int):
                    return target
    return step.next_step_id


def _fmt(text: Optional[str], variables: Dict[str, Any]) -> str:
    """Sustituye `{var}` por su valor en `variables`. Tolerante: si una llave
    no existe la deja tal cual (no usa str.format para no romper con `{` sueltos).
    """
    s = text or ""
    if not s or "{" not in s:
        return s
    for key, value in variables.items():
        s = s.replace("{" + str(key) + "}", str(value))
    return s


def _extract_value(var: str, text: str) -> str:
    """Demo de "extracción por LLM": saca un dato del mensaje libre del usuario.

    Hoy es heurística mínima (sin LLM). Para `nombre` intenta detectar marcadores
    típicos ("me llamo", "soy", ...) y si no, asume que el mensaje es el nombre.
    """
    t = (text or "").strip()
    if not t:
        return t
    if var == "nombre":
        low = t.lower()
        for marker in ("me llamo ", "mi nombre es ", "soy ", "nombre:", "nombre "):
            if marker in low:
                idx = low.index(marker) + len(marker)
                candidate = t[idx:].strip()
                candidate = candidate.split(",")[0].split(".")[0].strip()
                if candidate:
                    return candidate.split()[0].capitalize()
        # Sin marcador: tomamos la primera palabra como nombre.
        first = t.split()
        return first[0].capitalize() if first else t
    return t


def _resolve_llm_route(
    config: Dict[str, Any], user_input: Optional[str]
) -> Optional[int]:
    """Para un paso `llm` en modo route: decide el próximo step_id según las
    `intents` (cada una con `keywords` y un `step_id`). Primera intent cuyo
    keyword aparezca como substring del mensaje gana. None si nada matchea.
    """
    if not user_input:
        return None
    low = user_input.lower()
    for intent in config.get("intents") or []:
        if not isinstance(intent, dict):
            continue
        target = intent.get("step_id")
        if not isinstance(target, int):
            continue
        for kw in intent.get("keywords") or []:
            if isinstance(kw, str) and kw and kw.lower() in low:
                return target
    return None


def advance(
    bot: models.Bot,
    state: Optional[Dict[str, Any]],
    user_input: Optional[str] = None,
) -> Dict[str, Any]:
    """Avanza el bot desde `state` consumiendo `user_input` si aplica.

    Returns:
        {
            "actions":   [...],
            "next_state": {...} | None,
            "finished":   bool,
        }
    """
    actions: List[Dict[str, Any]] = []
    steps_by_id = _step_map(bot)

    # Inicialización: sin estado → empezar desde el primer paso
    if state is None or state.get("current_step_id") is None:
        if not bot.steps:
            return {"actions": [], "next_state": None, "finished": True}
        state = _new_state(bot.steps[0].id)
        # No consumimos user_input en el turno inicial
        user_input = None

    variables = dict(state.get("variables") or {})
    current_id: Optional[int] = state.get("current_step_id")
    consumed_input = False
    finished = False

    # Regla del CEO: entre un mensaje del bot y el siguiente, SIEMPRE debe
    # haber una respuesta del usuario (cada send_X = un "bloque" individual).
    # Tras emitir un mensaje, si el siguiente paso no es wait_input ni end,
    # detenemos el turno y esperamos input. Cuando llegue el próximo
    # turn() con user_input, simplemente procesaremos el siguiente paso.
    _STOP_AFTER_SEND_UNLESS = {"wait_input", "end"}

    def _should_break_after_send(next_id: Optional[int]) -> bool:
        if next_id is None:
            return False
        nxt = steps_by_id.get(next_id)
        if nxt is None:
            return False
        return nxt.step_type not in _STOP_AFTER_SEND_UNLESS

    for _ in range(MAX_STEPS_PER_TURN):
        if current_id is None:
            finished = True
            break

        step = steps_by_id.get(current_id)
        if step is None:
            # Step huérfano: terminamos limpio en vez de crashear.
            finished = True
            break

        cfg = _config(step)

        if step.step_type == "send_text":
            actions.append({"type": "say", "payload": {"text": _fmt(cfg.get("text", ""), variables)}})
            current_id = step.next_step_id
            if _should_break_after_send(current_id):
                break

        elif step.step_type == "send_template":
            name = cfg.get("template_name", "")
            actions.append(
                {"type": "say", "payload": {"text": f"[plantilla] {name}"}}
            )
            current_id = step.next_step_id
            if _should_break_after_send(current_id):
                break

        elif step.step_type == "send_media":
            # Un bloque puede enviar uno o VARIOS medios seguidos (ej. una
            # imagen + un video) en el mismo turno. Si `items` viene como lista
            # emitimos una acción por item; si no, fallback al medio único.
            items = cfg.get("items")
            if isinstance(items, list) and items:
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    actions.append(
                        {
                            "type": "say_media",
                            "payload": {
                                "caption": _fmt(it.get("caption", ""), variables),
                                "media_type": it.get("media_type", "image"),
                                "url": it.get("url", ""),
                            },
                        }
                    )
            else:
                actions.append(
                    {
                        "type": "say_media",
                        "payload": {
                            "caption": _fmt(cfg.get("caption", ""), variables),
                            "media_type": cfg.get("media_type", "image"),
                            "url": cfg.get("url", ""),
                        },
                    }
                )
            current_id = step.next_step_id
            if _should_break_after_send(current_id):
                break

        elif step.step_type == "llm":
            # Bloque "LLM" para la demo: el editor lo muestra como un bloque de
            # IA, pero por detrás corre lógica predefinida (sin LLM real todavía).
            #   mode="extract" → "extrae" un dato del último mensaje del usuario
            #                    y lo guarda en una variable.
            #   mode="route"   → interpreta el mensaje y decide el próximo paso
            #                    según keywords (incluye detectar datos de reserva).
            mode = cfg.get("mode", "route")
            if mode == "extract":
                var = cfg.get("variable") or "valor"
                if user_input is not None:
                    variables[var] = _extract_value(var, user_input)
                current_id = step.next_step_id
            else:  # route
                target = _resolve_llm_route(cfg, user_input)
                if target is None:
                    default_target = cfg.get("default_step_id")
                    target = default_target if isinstance(default_target, int) else None
                current_id = target if isinstance(target, int) else step.next_step_id

        elif step.step_type == "handoff":
            # Entrega el control a un asesor humano. El bot_runner traduce esta
            # acción a: conversation.status=pending + conversation.assigned_to.
            # Tras el handoff la sesión del bot termina (el humano toma el chat).
            actions.append(
                {
                    "type": "handoff",
                    "payload": {
                        "assignee": cfg.get("assignee", "asesor_1"),
                        "text": _fmt(cfg.get("text", ""), variables),
                    },
                }
            )
            current_id = None
            finished = True
            break

        elif step.step_type == "wait_input":
            if user_input is not None and not consumed_input:
                # Guardamos la respuesta y avanzamos
                variables[f"step_{step.id}_answer"] = user_input
                consumed_input = True
                # Branching por opción: si el config tiene `branches`
                # ({opcion_texto: step_id}), la opción elegida define el
                # próximo paso. Si no matchea, cae al `next_step_id` default.
                branches = cfg.get("branches") or {}
                target_id: Optional[int] = None
                if isinstance(branches, dict) and user_input:
                    low = user_input.strip().lower()
                    for key, target in branches.items():
                        if not isinstance(key, str):
                            continue
                        if key.lower() == low or key.lower() in low or low in key.lower():
                            if isinstance(target, int):
                                target_id = target
                                break
                current_id = target_id if target_id is not None else step.next_step_id
            else:
                # Pedimos input y salimos
                actions.append(
                    {
                        "type": "ask",
                        "payload": {
                            "prompt": _fmt(cfg.get("prompt", ""), variables),
                            "options": list(cfg.get("options") or []),
                        },
                    }
                )
                break

        elif step.step_type == "delay":
            actions.append(
                {"type": "pause", "payload": {"seconds": int(cfg.get("seconds") or 0)}}
            )
            current_id = step.next_step_id

        elif step.step_type == "condition":
            actions.append(
                {"type": "say", "payload": {"text": cfg.get("prompt", "")}}
            )
            current_id = _resolve_condition_next(step, cfg, user_input)
            if user_input is not None and not consumed_input:
                variables[f"step_{step.id}_answer"] = user_input
                consumed_input = True

        elif step.step_type == "end":
            # El nodo `end` NO envía mensaje al usuario: es solo un marcador
            # del fin del flujo. El frontend mostrará el botón de reinicio.
            current_id = None
            finished = True
            break

        else:
            # Tipo desconocido: saltamos sin crashear
            current_id = step.next_step_id

    else:
        # Safety: excedió MAX_STEPS_PER_TURN. Terminamos.
        finished = True
        current_id = None

    next_state: Optional[Dict[str, Any]]
    if finished:
        next_state = None
    else:
        next_state = {"current_step_id": current_id, "variables": variables}

    return {"actions": actions, "next_state": next_state, "finished": finished}
