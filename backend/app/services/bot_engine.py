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
            actions.append({"type": "say", "payload": {"text": cfg.get("text", "")}})
            current_id = step.next_step_id

        elif step.step_type == "send_template":
            name = cfg.get("template_name", "")
            actions.append(
                {"type": "say", "payload": {"text": f"[plantilla] {name}"}}
            )
            current_id = step.next_step_id

        elif step.step_type == "send_media":
            actions.append(
                {
                    "type": "say_media",
                    "payload": {
                        "caption": cfg.get("caption", ""),
                        "media_type": cfg.get("media_type", "image"),
                    },
                }
            )
            current_id = step.next_step_id

        elif step.step_type == "wait_input":
            if user_input is not None and not consumed_input:
                # Guardamos la respuesta y avanzamos
                variables[f"step_{step.id}_answer"] = user_input
                consumed_input = True
                current_id = step.next_step_id
            else:
                # Pedimos input y salimos
                actions.append(
                    {
                        "type": "ask",
                        "payload": {
                            "prompt": cfg.get("prompt", ""),
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
            actions.append(
                {"type": "end", "payload": {"text": cfg.get("text", "")}}
            )
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
