"""Disparador del cobro mensual de suscripciones.

Lo invoca EventBridge Scheduler (`multiagente-suscripciones-tick`) y hace
`POST /internal/suscripciones/tick` contra el backend. Ese endpoint cobra las
suscripciones cuyo ciclo ya venció y reconcilia los cobros que quedaron
colgados porque el webhook no llegó.

**Gemela de `infra/bot_tick/lambda_function.py`**, con otro `TICK_URL`. Van
separadas a propósito: si un cobro revienta, el que se queda sin correr es
este tick, no el de los bots — que atiende conversaciones de clientes y falla
por motivos completamente distintos.

Cadencia: cada 5 minutos, no cada minuto. Una suscripción se cobra una vez al
mes; 5 minutos de desviación sobre la hora que eligió el cliente no los nota
nadie, y son 12 invocaciones por hora en vez de 60.

Reglas de seguridad que esta función respeta (CLAUDE.md #1 y #3):
  * El secreto NO está en el código ni en una variable de entorno en claro. Se
    lee de SSM SecureString en tiempo de ejecución.
  * El secreto NUNCA se loggea. Solo se loggea el status HTTP y los conteos
    que devuelve el tick, que no son PII.

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
# haríamos un GetParameter por invocación. Con TTL acotamos cuánto sobrevive un
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
            # El endpoint valida con `_require_internal_key`, que acepta
            # cualquiera de los dos nombres. Se mandan ambos por simetría con
            # el tick de bots.
            "X-Internal-Key": secreto,
            "X-Internal-Secret": secreto,
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
        datos = json.loads(cuerpo)
        cobradas = datos.get("cobradas")
        reconciliadas = datos.get("reconciliadas")
    except (ValueError, AttributeError):
        cobradas = reconciliadas = None

    logger.info(
        "tick ok status=%s cobradas=%s reconciliadas=%s",
        status,
        cobradas,
        reconciliadas,
    )
    return {"status": status, "cobradas": cobradas, "reconciliadas": reconciliadas}
