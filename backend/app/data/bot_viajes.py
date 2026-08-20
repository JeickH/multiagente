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
                       "qué no, condiciones y política de niños",
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
        "descripcion": "video del hotel Bohíos (único material propio de este "
                       "hotel: no tiene imagen de info general)",
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
    "itinerario": ["itinerario", "agenda", "cronograma", "dia a dia", "día a día",
                    "actividades", "que hacemos", "qué hacemos", "a que hora",
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
}

