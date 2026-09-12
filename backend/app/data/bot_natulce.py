"""Catálogo de medios y configuración LLM del bot de Natulcé (demo).

Vive dentro de `app/` y no en `scripts/` por la misma razón que
`bot_viajes.py`: el script que actualiza la configuración en producción viaja a
ECS como el cuerpo de un `python -c` (ver `scripts/rds_exec.sh`), así que solo
puede importar de `app.*`. Si el catálogo viviera en el seed, el actualizador
tendría que llevar su propia copia — y dos copias de una tabla de precios e
imágenes terminan en desacuerdo.

Lo importan:
  - `scripts/seed_bot_natulce.py`  (crea la cuenta y el bot desde cero)

Natulcé es una **cuenta de demostración**: no tiene WhatsApp conectado y se
prueba desde la ventana "Probar Chatbot" de la app.
"""
from __future__ import annotations

import os

# Local: los assets los sirve Next desde `frontend/public/demo_natulce/`.
# Producción: Amplify sirve esa misma carpeta bajo el dominio de la app.
M = os.environ.get("MEDIA_BASE", "https://glomacx.com").rstrip("/")

# Catálogo de medios. Cambiar una imagen es cambiar este dict.
MEDIA = {
    "promo": {
        "url": f"{M}/demo_natulce/info_general.jpeg",
        "media_type": "image",
        "descripcion": "imagen de la promo: comparativo gaseosa tradicional vs. "
                       "sirope Natulcé (100% fruta, 90% menos calorías, stevia). "
                       "Va con el mensaje de bienvenida",
        "camino": "info_general",
    },
    "video_promo": {
        "url": f"{M}/demo_natulce/info_general.mp4",
        "media_type": "video",
        "descripcion": "video de la marca con la preparación de la soda "
                       "italiana. Va con el mensaje de bienvenida, junto a la "
                       "imagen `promo`",
        "camino": "info_general",
    },
    "precios": {
        "url": f"{M}/demo_natulce/precios_porciones.jpeg",
        "media_type": "image",
        "descripcion": "imagen con el precio ($29.000 los 250 ml), el "
                       "rendimiento (30 vasos de 22 oz), el envío nacional "
                       "($8.000) y el listado de sabores. Va cuando preguntan "
                       "cuánto vale, qué presentación hay o cuánto rinde",
        "camino": "precios_porciones",
    },
}

# #255 observabilidad: clasificador del camino por lo que PREGUNTÓ la persona,
# para los turnos que no llaman herramientas (las tools SON la decisión y
# tienen prioridad). El orden del dict es la prioridad de matcheo: lo
# específico va ANTES que lo genérico.
CAMINOS = {
    # Primero el pedido: "quiero dos de frutos rojos" trae el nombre de un
    # sabor, y sin esta entrada caería en `sabores` en vez de en la compra.
    "pedido": ["quiero pedir", "hacer el pedido", "hacer un pedido", "pedido",
                "pedir", "comprar", "compro", "lo quiero", "la quiero",
                "los quiero", "me lo llevo", "me los llevo", "mis datos",
                "direccion", "dirección", "como pido", "cómo pido",
                "donde compro", "dónde compro"],
    "precios_porciones": ["precio", "precios", "cuanto vale", "cuánto vale",
                           "cuanto cuesta", "cuánto cuesta", "cuanto sale",
                           "cuánto sale", "cuesta", "valor", "vale",
                           "presentacion", "presentación", "tamaño", "tamano",
                           "250", "ml", "rinde", "rendimiento", "porciones",
                           "preparaciones", "alcanza", "dura", "descuento",
                           "promo", "promocion", "promoción", "oferta",
                           "dsct", "envio", "envío", "domicilio", "flete"],
    "sabores": ["sabor", "sabores", "frutos rojos", "frutos amarillos",
                 "jamaica", "maracuya", "maracuyá", "limoncillo", "neutro",
                 "endulzante", "endulzantes", "stevia", "cuales tienen",
                 "cuáles tienen", "que sabores", "qué sabores"],
    # Frases, no palabras sueltas: "persona" a secas marcaba como `asesor` un
    # "¿eres una persona real?", que no es una petición de humano.
    "asesor": ["hablar con una persona", "con una persona", "un asesor",
                "una asesora", "asesor humano", "un humano", "con alguien",
                "atencion humana", "atención humana", "al por mayor",
                "por mayor", "mayorista", "distribuir", "distribucion",
                "distribución"],
    "info_general": ["hola", "buenas", "informacion", "información", "info",
                      "natulce", "natulcé", "sirope", "siropes", "soda",
                      "sodas", "coctel", "cóctel", "cocteleria", "coctelería",
                      "calorias", "calorías", "azucar", "azúcar", "natural"],
}


# Configuración completa del bot LLM.
#
# OJO con `assignee`: se deja puesto porque la cuenta demo tiene UNA sola
# asesora. Cuando hay varias, se quita para que `bot_runner` reparta por turnos
# con `crud.siguiente_asesor`.
LLM_CONFIG = {
    "context_key": "natulce",
    "assignee": "asesor_1",
    "media": MEDIA,
    "caminos": CAMINOS,
    # ── Pedidos a la hoja de Drive ──────────────────────────────────────────
    # Habilita la herramienta `registrar_pedido`: cuando el cliente manda
    # nombre, dirección y pedido, el bot escribe la fila en la hoja de cálculo
    # del equipo (ver `services/pedidos_sheet.py`).
    #
    # `encrypted_webhook_url` es la URL del Apps Script de la hoja, cifrada con
    # Fernet: quien la tenga puede escribir filas ahí, así que es un secreto
    # del tenant y va en la base cifrado, nunca en el repositorio (regla #3).
    # La escribe `configurar_pedidos_natulce.py`; mientras esté vacía, el bot
    # sigue funcionando igual y solo deja un warning en el log.
    "pedidos": {
        "hoja": "Pedidos Natulcé — WhatsApp",
        "encrypted_webhook_url": "",
    },
    # ── Continuidad de la conversación (#377) ───────────────────────────────
    # `seguimiento` es la política de cierre de este bot: cerrar cuando el bot
    # se despide, reenganchar mientras haya silencio y, si tampoco así
    # contesta, etiquetar la conversación y pasársela a la asesora sin
    # escribirle. Habilita además la herramienta `no_responder`.
    #
    # Los `minutos` de cada recordatorio se cuentan **desde que empezó el
    # silencio**, no desde el recordatorio anterior; `bot_runner` calcula la
    # diferencia.
    #
    # Las 3 horas del primero las pidió el CEO para esta demo, con ese texto
    # exacto. El segundo, a las 23 h, no es un número redondo por casualidad:
    # WhatsApp solo deja mandar texto libre dentro de las 24 horas siguientes
    # al último mensaje del cliente; a las 24 en punto ya haría falta una
    # plantilla aprobada por Meta y el mensaje saldría `failed`.
    "seguimiento": {
        "minutos": 180,
        "etiqueta_abandono": "conversación abandonada",
        "recordatorios": [
            {"minutos": 180, "texto": "Hola 👀 me dejaste en visto 🙊…"},
            {
                "minutos": 23 * 60,
                "texto": (
                    "Última razón por hoy 🍹 Si más adelante quieres probar los "
                    "siropes, aquí estoy. ¡Que estés muy bien! 😊"
                ),
            },
        ],
    },
    # Guarda el nombre en `conversations.contact_name` con `registrar_nombre`,
    # para no volver a preguntarlo aunque se acabe la sesión.
    "recordar_nombre": True,
    # Con el nombre ya sabido, el mensaje de apertura va **sin** su última
    # línea (la que pide el nombre) y cierra con esto en su lugar. Sin esta
    # frase el modelo copiaba la apertura entera y repreguntaba el nombre.
    "cierre_sin_nombre": "qué sabores te gustaría probar",
    # #379: si el primer mensaje sale sin pedir el nombre —pasa cuando la
    # persona abre con una pregunta concreta y el bot gasta su única pregunta
    # contestándola—, se manda esto como mensaje aparte.
    "pregunta_nombre": "¿Con quién tengo el gusto? 😊",
    # Si vuelve a escribir dentro de estas horas, se retoma la MISMA sesión
    # (con su historial) en vez de arrancar una nueva y saludar de cero. Es lo
    # que hace que quien contesta el recordatorio de las 3 horas no vuelva a
    # recibir la bienvenida.
    "retomar": {"horas": 24},
    # Palabras que el modelo elige por su cuenta y que en Colombia no se usan.
    # Vive en el tenant y no en el motor: `llm_engine` lo comparten otros bots.
    "reemplazos": {
        "zumo": "jugo", "zumos": "jugos",
        "refresco": "bebida", "refrescos": "bebidas",
        "vos": "tú",
        "pagás": "pagas", "tenés": "tienes", "querés": "quieres",
        "podés": "puedes", "sabés": "sabes", "hacés": "haces",
        "decís": "dices", "necesitás": "necesitas", "probás": "pruebas",
    },
}
