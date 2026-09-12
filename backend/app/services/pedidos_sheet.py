"""Los pedidos que cierra el bot, escritos en una hoja de cálculo de Drive.

Por qué existe: cuando el cliente manda nombre, dirección y pedido, esos datos
quedan dentro del chat. El equipo que despacha no trabaja en la bandeja — pide
"la lista de pedidos del día", y esa lista es una hoja de cálculo. Este módulo
es el puente.

Cómo escribe, que explica el resto del diseño: **no usamos la API de Google
Sheets**. Hacerlo exigiría una cuenta de servicio en Google Cloud, su archivo
JSON de credenciales y una librería más en la imagen. En su lugar, la hoja
publica un pequeño *Apps Script* como aplicación web y nosotros le hacemos un
`POST` con el pedido en JSON. Del lado de Google el script corre con los
permisos del dueño de la hoja, así que nadie tiene que compartir credenciales
con nosotros. El código del script está al final de este archivo, en un
comentario, para que se pueda volver a crear la hoja sin buscarlo en otro lado.

Tres cosas que no son obvias:

  1. **La URL del script es un secreto de tenant**, no de la plataforma: quien
     la tenga puede escribir filas en la hoja de ese cliente. Por eso viaja
     cifrada con Fernet dentro de `bots.llm_config` (regla de seguridad #3) y
     nunca se loggea (regla #1), ni siquiera recortada.
  2. **El envío es fail-soft.** Si Google no responde, el turno del bot NO se
     cae: el cliente ya vio su pedido confirmado en el chat y ahí sigue
     estando, que es la copia que de verdad importa. El fallo queda en el log
     sin un solo dato del cliente.
  3. **Ningún dato personal se loggea.** Nombre, dirección y teléfono son datos
     de un tercero (regla #8): en CloudWatch solo queda si la fila entró o no.

El `timeout` es corto a propósito: esto corre dentro del turno del bot, y un
cliente esperando en WhatsApp no puede pagar 30 segundos porque Google esté
lento.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: Colombia. La hoja la lee gente en Medellín: la fecha y la hora tienen que
#: ser las de allá, no las UTC del servidor.
_TZ_CO = timezone(timedelta(hours=-5))

#: Segundos. Corre dentro del turno del bot — ver el encabezado.
_TIMEOUT = float(os.getenv("PEDIDOS_SHEET_TIMEOUT", "6"))


def config_de(cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """El bloque `pedidos` de la `llm_config`, o None si el bot no lo tiene."""
    pedidos = (cfg or {}).get("pedidos")
    return pedidos if isinstance(pedidos, dict) else None


def _url_de(pedidos: Dict[str, Any]) -> str:
    """La URL del Apps Script, descifrada.

    Acepta `webhook_url` en claro para desarrollo local (donde la hoja es de
    pruebas y no hay nada que proteger); en producción se usa
    `encrypted_webhook_url`, que es lo que se guarda en la base.
    """
    cifrada = (pedidos.get("encrypted_webhook_url") or "").strip()
    if cifrada:
        try:
            from .crypto import decrypt_secret

            return decrypt_secret(cifrada).strip()
        except Exception:
            # Sin detalle del error hacia arriba ni la URL en el log (regla #1).
            logger.exception("pedidos_sheet: no se pudo descifrar la URL de la hoja")
            return ""
    return (pedidos.get("webhook_url") or "").strip()


def enviar(
    cfg: Dict[str, Any],
    pedido: Dict[str, Any],
    *,
    telefono: str = "",
    origen: str = "whatsapp",
) -> bool:
    """Escribe una fila en la hoja. Devuelve si quedó escrita.

    Nunca lanza: un pedido que no llega a la hoja es un problema, pero tumbar
    el turno del bot delante del cliente es uno peor.
    """
    pedidos_cfg = config_de(cfg)
    if not pedidos_cfg:
        return False
    url = _url_de(pedidos_cfg)
    if not url:
        logger.warning("pedidos_sheet: el bot tiene `pedidos` pero no una URL usable")
        return False

    ahora = datetime.now(_TZ_CO)
    fila = {
        "fecha": ahora.strftime("%Y-%m-%d"),
        "hora": ahora.strftime("%H:%M"),
        "nombre": str(pedido.get("nombre", ""))[:120],
        "direccion": str(pedido.get("direccion", ""))[:250],
        "pedido": str(pedido.get("pedido", ""))[:400],
        "total": str(pedido.get("total", ""))[:40],
        "telefono": str(telefono or "")[:32],
        "origen": origen[:24],
        # Lo usa el script para rechazar cualquier POST que no venga de aquí:
        # la URL sola es adivinable si alguien la ve pasar.
        "token": str(pedidos_cfg.get("token", ""))[:64],
    }

    try:
        import requests

        resp = requests.post(url, json=fila, timeout=_TIMEOUT)
        ok = 200 <= resp.status_code < 300
        if not ok:
            # El cuerpo de la respuesta puede traer de vuelta la fila: no se
            # loggea, solo el código.
            logger.warning("pedidos_sheet: la hoja respondió %s", resp.status_code)
        else:
            logger.info("pedidos_sheet: pedido escrito en la hoja (origen=%s)", origen)
        return ok
    except Exception:
        logger.exception("pedidos_sheet: no se pudo escribir el pedido en la hoja")
        return False


def registrar(
    db,
    bot,
    telemetry: Optional[Dict[str, Any]],
    *,
    source: str,
    telefono: str = "",
    team_id: Optional[int] = None,
    conversation_id: Optional[int] = None,
) -> int:
    """Guarda los pedidos de este turno: en la base **y** en la hoja.

    La llaman los dos canales del bot (el simulador y `bot_runner`) justo
    después de `advance()`, con la misma forma que `record_booking`.

    El orden importa: **primero la base**, después la hoja. La base es la copia
    que no depende de que Google conteste, y es la que lee la ventana de
    Pedidos; si el envío a la hoja falla, el pedido existe igual y queda
    marcado con `en_hoja = false` para que se vea cuál hay que copiar a mano.

    Nunca lanza: un pedido que no se pudo guardar es un problema, pero tumbar
    el turno del bot delante del cliente es uno peor.
    """
    pedidos = (telemetry or {}).get("pedidos") or []
    if not pedidos:
        return 0

    from . import llm_engine  # import perezoso: llm_engine importa este módulo

    cfg = llm_engine.config_de(bot)
    guardados = 0
    for pedido in pedidos:
        en_hoja = enviar(cfg, pedido, telefono=telefono, origen=source)
        if _guardar(
            db, bot, pedido,
            team_id=team_id, conversation_id=conversation_id,
            telefono=telefono, origen=source, en_hoja=en_hoja,
        ):
            guardados += 1
    if guardados < len(pedidos):
        logger.warning(
            "pedidos_sheet: %s de %s pedido(s) no se pudieron guardar (bot=%s)",
            len(pedidos) - guardados, len(pedidos), getattr(bot, "id", "?"),
        )
    return guardados


def _guardar(
    db,
    bot,
    pedido: Dict[str, Any],
    *,
    team_id: Optional[int],
    conversation_id: Optional[int],
    telefono: str,
    origen: str,
    en_hoja: bool,
) -> bool:
    """Escribe la fila en `pedidos`. Devuelve si quedó guardada."""
    try:
        from .. import models

        equipo = team_id
        if equipo is None:
            # El simulador no trae team: se saca del dueño del bot, que es el
            # mismo camino que usa el resto de la app para aislar tenants.
            dueño_id = getattr(bot, "user_id", None)
            membresia = (
                db.query(models.TeamMember)
                .filter(models.TeamMember.user_id == dueño_id)
                .first()
                if dueño_id
                else None
            )
            equipo = getattr(membresia, "team_id", None)
        if equipo is None:
            logger.warning(
                "pedidos_sheet: pedido sin team (bot=%s), no se guarda",
                getattr(bot, "id", "?"),
            )
            return False

        db.add(
            models.Pedido(
                team_id=equipo,
                conversation_id=conversation_id,
                nombre=str(pedido.get("nombre", ""))[:120],
                direccion=str(pedido.get("direccion", ""))[:250],
                detalle=str(pedido.get("pedido", ""))[:400],
                total=str(pedido.get("total", ""))[:40] or None,
                telefono=str(telefono or "")[:32] or None,
                origen=origen[:24],
                en_hoja=en_hoja,
            )
        )
        db.commit()
        logger.info(
            "pedido guardado bot=%s origen=%s en_hoja=%s",
            getattr(bot, "id", "?"), origen, en_hoja,
        )
        return True
    except Exception:
        # Sin PII en el log (regla #1): ni nombre, ni dirección, ni teléfono.
        logger.exception(
            "pedidos_sheet: no se pudo guardar el pedido (bot=%s)",
            getattr(bot, "id", "?"),
        )
        try:
            db.rollback()
        except Exception:
            pass
        return False


# ---------------------------------------------------------------------------
# El Apps Script que va del otro lado. Se pega en la hoja
# (Extensiones → Apps Script), se publica como aplicación web con acceso
# "cualquier usuario" y la URL resultante es la que se guarda cifrada.
#
#   const TOKEN = '...';   // el mismo que va en `pedidos.token`
#
#   function doPost(e) {
#     const d = JSON.parse(e.postData.contents);
#     if (d.token !== TOKEN) {
#       return ContentService.createTextOutput('no');
#     }
#     const hoja = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
#     hoja.appendRow([
#       d.fecha, d.hora, d.nombre, d.direccion,
#       d.pedido, d.total, d.telefono, d.origen,
#     ]);
#     return ContentService.createTextOutput('ok');
#   }
#
# El `doPost` no valida más porque no hace falta: escribe ocho celdas de texto
# en una hoja que no ejecuta fórmulas nuestras.
# ---------------------------------------------------------------------------
