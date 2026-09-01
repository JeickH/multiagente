"""Catálogo de medios y configuración LLM del bot de viajes (Arranquemos Pues).

Vive dentro de `app/` y no en `scripts/` por una razón operativa: el script que
actualiza la configuración en producción viaja a ECS como el cuerpo de un
`python -c` (ver `scripts/rds_exec.sh`), así que solo puede importar de `app.*`.
Si el catálogo viviera en el seed, el actualizador tendría que llevar su propia
copia — y dos copias de una tabla de precios e imágenes terminan en desacuerdo.

Lo importan:
  - `scripts/seed_bot_viajes_llm.py`  (crea el bot desde cero: demo y local)
  - `scripts/actualizar_bot_viajes.py` (reescribe `llm_config` sin borrar el bot)
"""
from __future__ import annotations

import os

M = os.environ.get("MEDIA_BASE", "https://app.glomabeauty.com").rstrip("/")

# Catálogo de medios. Los flyers de tarifario llevan además `hotel` y `meses`:
# de ahí saca `services/tarifario.py` qué imagen corresponde al mes que pidió el
# cliente, para que esa decisión no dependa de que el modelo elija bien ni de
# una tabla cableada en el código. Cambiar una imagen es cambiar este dict.
MEDIA = {
    "info_amordios": {
        "url": f"{M}/demo_viajes/hotel_amordios.jpeg", "media_type": "image",
        "descripcion": "info del plan en el hotel Amor de Dios: qué incluye, "
                       "qué no, condiciones y política de niños. Es también la "
                       "info de Bohíos, que no tiene flyer propio: el plan es "
                       "el mismo y el precio también",
        "camino": "hotel",
    },
    "info_piedramar": {
        "url": f"{M}/demo_viajes/hotel_piedramar.jpeg", "media_type": "image",
        "descripcion": "info del plan en el hotel Piedra Mar: qué incluye, "
                       "qué no, condiciones y política de niños",
        "camino": "hotel",
    },
    "video_amordios": {
        "url": f"{M}/demo_viajes/hotel_amor_dios.mp4", "media_type": "video",
        "descripcion": "video del hotel Amor de Dios",
        "camino": "hotel",
    },
    "video_piedramar": {
        "url": f"{M}/demo_viajes/hotel_piedramar.mp4", "media_type": "video",
        "descripcion": "video del hotel Piedra Mar",
        "camino": "hotel",
    },
    "video_bohios": {
        "url": f"{M}/demo_viajes/hotel_bohios.mp4", "media_type": "video",
        "descripcion": "video del hotel Bohíos (cada hotel tiene el suyo; la "
                       "info general de Bohíos es la de Amor de Dios)",
        "camino": "hotel",
    },
    "tarifario_amordios_ago_nov": {
        "url": f"{M}/demo_viajes/tarifario_amordios2.jpeg", "media_type": "image",
        "descripcion": "tarifario Amor de Dios / Bohíos — agosto a noviembre",
        "camino": "precios_condiciones",
        "hotel": "amor_de_dios", "meses": [8, 9, 10, 11],
    },
    "tarifario_amordios_dic_ene": {
        "url": f"{M}/demo_viajes/tarifario_amordios1.jpeg", "media_type": "image",
        "descripcion": "tarifario Amor de Dios / Bohíos — diciembre y enero",
        "camino": "precios_condiciones",
        "hotel": "amor_de_dios", "meses": [12, 1],
    },
    "tarifario_piedramar_jul_oct": {
        "url": f"{M}/demo_viajes/tarifario_piedramar2.jpeg", "media_type": "image",
        "descripcion": "tarifario Piedra Mar — julio a octubre",
        "camino": "precios_condiciones",
        "hotel": "piedra_mar", "meses": [7, 8, 9, 10],
    },
    "tarifario_piedramar_nov_ene": {
        "url": f"{M}/demo_viajes/tarifario_piedramar1.jpeg", "media_type": "image",
        "descripcion": "tarifario Piedra Mar — noviembre, diciembre y enero",
        "camino": "precios_condiciones",
        "hotel": "piedra_mar", "meses": [11, 12, 1],
    },
    "tours": {
        "url": f"{M}/demo_viajes/tours.jpeg", "media_type": "image",
        "descripcion": "imagen con los tours incluidos en el plan",
        "camino": "tours",
    },
    "tour_video": {
        "url": f"{M}/demo_viajes/tour.mp4", "media_type": "video",
        "descripcion": "video adelanto de los tours",
        "camino": "tours",
    },
    "medios_pago": {
        "url": f"{M}/demo_viajes/medios_pago.jpeg", "media_type": "image",
        "descripcion": "imagen con los métodos de pago (Bre-B, bancos, efectivo, tarjetas)",
        "camino": "pagos",
    },
    "formulario_reserva": {
        "url": f"{M}/demo_viajes/fomulario_reserva.jpeg", "media_type": "image",
        "descripcion": "imagen con los datos que se piden para reservar",
        "camino": "reserva",
    },
}

# #255 observabilidad: clasificador de camino por la pregunta de la persona.
# Orden = prioridad de matcheo (el dict conserva el orden de escritura), así
# que lo específico va ANTES que lo genérico.
CAMINOS = {
    "reserva": ["reserva", "reservar", "apartar", "separar", "cedula", "cédula",
                 "cupo"],
    # Va de primero: "¿tienen plan a San Andrés?" caía en info_general por la
    # palabra "plan", y es justo el caso que debe ir a un asesor humano.
    "otros_destinos": ["san andres", "san andrés", "cartagena", "santa marta",
                        "guajira", "eje cafetero", "providencia", "otro destino",
                        "otros destinos", "otro plan", "otros planes",
                        "otro viaje", "otros viajes"],
    "hotel": ["hotel", "hospedaje", "alojamiento", "habitacion", "habitación",
               "amor de dios", "piedra mar", "piedramar", "bohios", "bohíos"],
    # "cada dia" / "que se hace" entraron con el primer mensaje unificado
    # (Sprint 24 F3): ahora el itinerario sale ya en la apertura, así que quien
    # lo vuelve a preguntar casi nunca usa la palabra "itinerario" — dice "¿qué
    # se hace cada día?". Sin estas frases ese turno se marcaba
    # `respuesta_libre` y el panel del tenant no veía que el camino se sigue
    # pidiendo después de la apertura.
    "itinerario": ["itinerario", "agenda", "cronograma", "dia a dia", "día a día",
                    "cada dia", "cada día", "actividades", "que hacemos",
                    "qué hacemos", "que se hace", "qué se hace", "a que hora",
                    "a qué hora"],
    "precios_condiciones": ["precio", "precios", "cuesta", "cuanto", "cuánto",
                             "valor", "tarifa", "condicion", "condición",
                             "descuento", "rebaja", "abono", "reembolso",
                             "cancelacion", "cancelación"],
    "pagos": ["pago", "pagar", "pse", "transferencia", "tarjeta", "nequi",
               "daviplata", "bre-b", "breb", "bancolombia", "davivienda",
               "bbva", "efectivo", "codensa", "metodo", "método"],
    "tours": ["tour", "tours", "caimanera", "cienaga", "ciénaga", "paseo",
               "incluye", "incluido", "playa"],
    # Frases, no palabras sueltas: "persona" a secas marcaba como `asesor` un
    # "¿eres una persona real o un bot?", que no es una petición de humano.
    "asesor": ["hablar con una persona", "con una persona", "asesor humano",
                "un asesor", "una asesora", "un humano", "con alguien",
                "atencion humana", "atención humana"],
    # La dirección de la oficina, que el bot pasó a saber (26-ago-2026). Va
    # después de `hotel` a propósito: "¿dónde queda el hotel?" es una pregunta
    # por el hotel, no por la agencia. Sin frases de salida ("de dónde sale el
    # bus") porque eso es itinerario, y el documento se lo dice al modelo.
    "ubicacion": ["direccion", "dirección", "ubicacion", "ubicación",
                   "ubicados", "donde queda", "dónde queda", "donde quedan",
                   "dónde quedan", "donde estan", "dónde están",
                   "donde los encuentro", "donde los ubico", "dónde los ubico",
                   "como llego", "cómo llego", "como llegar", "cómo llegar",
                   "oficina", "sede", "bosque plaza", "visitarlos"],
    "info_general": ["informacion", "información", "info", "plan", "covenas",
                      "coveñas", "tolu", "tolú", "promo"],
}


# Configuración completa del bot LLM. Vive aquí (y no repartida entre el seed y
# el script de actualización) para que no puedan quedar en desacuerdo: el
# actualizador la importa de este módulo.
#
# OJO con `assignee`: NO va. Cuando está puesto, gana sobre el reparto por
# turnos y todos los chats caen en la misma persona. Sin él, `bot_runner` llama
# a `crud.siguiente_asesor` y los reparte entre los asesores del team.
LLM_CONFIG = {
    "context_key": "demo_viajes",
    "media": MEDIA,
    "caminos": CAMINOS,
    "tarifario": "covenas",   # habilita la herramienta `consultar_tarifario`
    # ── Continuidad de la conversación (#377) ───────────────────────────────
    # Los tres flags viven aquí y no en el motor: `llm_engine.py` lo comparten
    # el bot de mascotas y el institucional, y una regla global les cambiaría
    # el comportamiento (ya pasó — commit 1a7d385).
    #
    # `seguimiento` es la política de cierre de este bot: cerrar la
    # conversación cuando el bot se despide, reenganchar mientras haya silencio
    # y, si tampoco así contesta, etiquetarla y pasársela a la asesora sin
    # escribirle. Habilita además la herramienta `no_responder`.
    #
    # Tres recordatorios en vez de uno (pedido del CEO, 31-ago-2026). Los
    # `minutos` de cada uno se cuentan **desde que empezó el silencio**, no
    # desde el recordatorio anterior; `bot_runner` calcula la diferencia.
    #
    # Por qué 23 h y no 24: WhatsApp solo deja mandar texto libre dentro de las
    # 24 horas siguientes al último mensaje del cliente. A las 24 en punto el
    # mensaje ya necesitaría una plantilla aprobada por Meta y saldría
    # `failed`; la hora de margen absorbe el retraso del tick.
    #
    # Los tres textos son distintos a propósito: el mismo párrafo calcado tres
    # veces en un día se lee como un bot trabado. El tercero además se despide,
    # porque es el último que sale.
    "seguimiento": {
        "minutos": 15,
        "etiqueta_abandono": "conversación abandonada",
        "recordatorios": [
            {
                "minutos": 15,
                "texto": (
                    "¿Te quedó alguna otra pregunta para seguir con la reserva? 😊 "
                    "Si prefieres lo dejamos hasta aquí y me escribes cuando "
                    "quieras 🌴"
                ),
            },
            {
                "minutos": 5 * 60,
                "texto": (
                    "¡Hola de nuevo! 👋 Te quedé debiendo la respuesta por acá. "
                    "Si quieres seguimos con el plan cuando tengas un momento, "
                    "o dime qué te gustaría saber 🌴"
                ),
            },
            {
                "minutos": 23 * 60,
                "texto": (
                    "Última razón por hoy 🌴 Si más adelante quieres retomar el "
                    "plan, aquí estoy y con gusto te ayudo. ¡Que estés muy bien! 😊"
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
    "cierre_sin_nombre": "para qué mes lo está pensando",
    # #379: si el primer mensaje sale sin pedir el nombre —pasa 1 de cada 5
    # veces, cuando la persona abre con una pregunta concreta y el bot gasta su
    # única pregunta contestándola—, se manda esto como mensaje aparte. La
    # frase la fija el tenant porque es su voz, no la del motor.
    "pregunta_nombre": "¿Con quién tengo el gusto? 😊",
    # Si vuelve a escribir dentro de estas horas, se retoma la MISMA sesión
    # (con su historial) en vez de arrancar una nueva y saludar de cero.
    "retomar": {"horas": 24},
    # Palabras que el modelo elige por su cuenta y que en Colombia no se
    # entienden (pedido del CEO, 29-ago-2026). El documento nunca escribe
    # "seña" —siempre "se aparta el cupo con el 30%"— pero el modelo la usa
    # igual: es la palabra de otros países para el pago inicial, y aquí el
    # cliente no sabe qué le están pidiendo. El prompt ya lo prohíbe; esto es
    # la red, porque una palabra que se escapa una vez de cada veinte igual
    # llega a un cliente real.
    #
    # El reemplazo es *cuota inicial* y no *anticipo* por concordancia: hereda
    # el artículo que el modelo ya escribió, y "seña" es femenino ("una seña
    # del 30%" → "una cuota inicial del 30%"). Con "anticipo" habría que tocar
    # también el artículo.
    #
    # Vive en el tenant y no en el motor: `llm_engine` lo comparte el bot de
    # mascotas, donde "señas" es vocabulario central ("señas particulares") y
    # este reemplazo le rompería las descripciones.
    #
    # Los verbos son otra cosa y conviene no confundirlas: "pagás", "tenés" y
    # "querés" son voseo **paisa**, español legítimo y de la ciudad donde queda
    # la agencia. Lo que no se puede es mezclarlo con el tuteo en el mismo
    # mensaje, y el documento ya eligió tutear ("Trata de tú"). Se listan sólo
    # formas que no chocan con un nombre propio: "tomás" queda fuera a
    # propósito, o el bot le escribiría "tomas" a un cliente llamado Tomás.
    "reemplazos": {
        "seña": "cuota inicial", "señas": "cuotas iniciales",
        "vos": "tú",
        "pagás": "pagas", "tenés": "tienes", "querés": "quieres",
        "podés": "puedes", "sabés": "sabes", "hacés": "haces",
        "decís": "dices", "venís": "vienes", "necesitás": "necesitas",
        "reservás": "reservas", "viajás": "viajas", "llegás": "llegas",
    },
}

