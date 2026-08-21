"""Disparador del scheduler de bots — cierra el gap G1 del Sprint 14.

Lo invoca EventBridge Scheduler (`multiagente-bot-tick`) cada 60 s y hace
`POST /internal/bot-scheduler/tick` contra el backend. Ese endpoint es el que
procesa las `BotPendingAction` vencidas: el seguimiento a los 15 min de silencio
y la etiqueta de "conversación abandonada" 15 min después. Sin este disparador
esas dos cosas no ocurren nunca en producción.

Reglas de seguridad que esta función respeta (CLAUDE.md #1 y #3):
  * El secreto NO está en el código ni en una variable de entorno en claro. Se
    lee de SSM SecureString en tiempo de ejecución.
  * El secreto NUNCA se loggea. Solo se loggea el status HTTP y el conteo de
    acciones procesadas, que no son PII.

Variables de entorno (ninguna es secreta):
  TICK_URL      URL completa del endpoint del tick.
  SECRET_PARAM  Nombre del parámetro SSM SecureString con el shared secret.
  HTTP_TIMEOUT  Segundos de espera de la respuesta del backend (default 45).
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TICK_URL = os.environ["TICK_URL"]
SECRET_PARAM = os.environ["SECRET_PARAM"]
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "45"))

# El contenedor de Lambda queda caliente entre ticks, así que sin caché
# haríamos un GetParameter por minuto. Con TTL acotamos cuánto sobrevive un
# secreto ya rotado: a los 15 min como máximo la función lee el nuevo valor.
_TTL_CACHE_SEGUNDOS = 900

_ssm = boto3.client("ssm")
_cache: dict[str, object] = {"valor": None, "vence_en": 0.0}


def _secreto() -> str:
    """Devuelve el shared secret desde SSM, con caché acotada por TTL."""
    ahora = time.monotonic()
    if _cache["valor"] is None or ahora >= float(_cache["vence_en"]):
        respuesta = _ssm.get_parameter(Name=SECRET_PARAM, WithDecryption=True)
        _cache["valor"] = respuesta["Parameter"]["Value"]
        _cache["vence_en"] = ahora + _TTL_CACHE_SEGUNDOS
    return str(_cache["valor"])


def lambda_handler(event, context):  # noqa: ARG001 - firma de Lambda
    secreto = _secreto()
    peticion = urllib.request.Request(
        TICK_URL,
        method="POST",
        data=b"{}",
        headers={
            "Content-Type": "application/json",
            # Se mandan los dos nombres a propósito. Hoy el endpoint valida con
            # `_require_internal_secret`, que lee la cabecera X-Internal-Secret;
            # la variante endurecida `_require_internal_key` acepta
            # X-Internal-Key o X-Internal-Secret. Mandando ambas, el día que el
            # endpoint se endurezca el tick sigue funcionando sin tener que
            # volver a desplegar esta Lambda.
            "X-Internal-Secret": secreto,
            "X-Internal-Key": secreto,
        },
    )

    try:
        with urllib.request.urlopen(peticion, timeout=HTTP_TIMEOUT) as respuesta:
            status = respuesta.status
            cuerpo = respuesta.read().decode("utf-8", "replace")[:1000]
    except urllib.error.HTTPError as error:
        # Se loggea recortado y solo para diagnóstico: un 403 aquí significa
        # "el secreto no coincide", que es justo lo que uno necesita saber.
        detalle = error.read().decode("utf-8", "replace")[:200]
        logger.error("tick rechazado: HTTP %s %s", error.code, detalle)
        raise RuntimeError(f"el tick devolvio HTTP {error.code}") from None
    except Exception as error:  # timeout, DNS, conexión rechazada
        logger.error("el tick no respondio: %s", type(error).__name__)
        raise

    try:
        procesadas = json.loads(cuerpo).get("processed")
    except (ValueError, AttributeError):
        procesadas = None

    logger.info("tick ok status=%s processed=%s", status, procesadas)
    return {"status": status, "processed": procesadas}
