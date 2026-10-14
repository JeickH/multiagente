"""Configuración LLM del bot 3 (variante C, «embudo guiado») de Arranquemos Pues.

El bot 3 vende el mismo plan que los bots 1 y 2, con los mismos productos,
medios y tiempos de reenganche, y se reparte con ellos las conversaciones
nuevas (34 / 33 / 33). Cambia la **forma de vender**: la metodología del
curso *Ventas con WhatsApp* (notas en `curso_ventas_whatsapp/`), con
respuestas cerradas, una biblioteca de bloques y un embudo por etapas. El
guion vive en `bot_contexts/demo_viajes_c.md`.

Igual que en el bot 2, todo lo nuevo va detrás de banderas que solo tiene
este bot: sin la bandera, el motor hace lo de siempre y los bots 1 y 2 no
cambian.

**Ninguna cifra de precio está escrita aquí.** Los recordatorios por etapa
no llevan montos porque el runner no tiene la cotización a mano; el único
monto es el de la promoción que NO existe (heredado del bot 2), que es lo
que hay que detectar.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List

from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import FLAGS_VARIANTE as FLAGS_VARIANTE_B

#: Clave del contexto: `bot_contexts/<CONTEXT_KEY_C>.md`.
CONTEXT_KEY_C = "demo_viajes_c"

RUTA_MD_C = Path(__file__).resolve().parent.parent / "bot_contexts" / f"{CONTEXT_KEY_C}.md"


def instrucciones_c() -> str:
    """El texto del guion del bot 3, tal como se guarda en `bots.instrucciones`."""
    return RUTA_MD_C.read_text(encoding="utf-8").strip()


#: Banderas del bot 2 que el bot 3 reutiliza tal cual (calidad de plataforma:
#: guardarraíles, anticipo como dato, nombre una vez…). Se copian del bot 2 y
#: no se reescriben, para que un ajuste allá llegue igual acá.
REUTILIZADAS_DE_B = (
    "guardarrail_precio",
    "cargos_ninos",
    "anticipo_en_sistema",
    "correcciones_silenciosas",
    "marcas_a_medios",
    "consulta_obligatoria_por_mes",
    "duracion_por_plan",
    "filtrar_nombres_genericos",
    "nombre_una_vez",
    "presentacion_una_vez",
    "promo_inexistente",
    "intencion_compra",
    "no_cerrar_aplazadas",
)

#: Las del bot 2 que el bot 3 NO lleva, a propósito:
#:   - `apertura_vitrina`: la bienvenida del bot 3 es el menú de meses, no la
#:     vitrina con el «desde» y el flyer.
#:   - `una_pregunta_por_turno`: cortaría las opciones numeradas, que van
#:     debajo de la pregunta.
#:   - `recordatorios_con_contexto`: lo reemplaza `recordatorios_por_etapa`.
NO_VAN_EN_C = ("apertura_vitrina", "una_pregunta_por_turno", "recordatorios_con_contexto")

#: Horario de los asesores (decisión del CEO): lunes a viernes de 8:00 a.m. a
#: 6:00 p.m. y sábados de 8:00 a.m. a 1:00 p.m., hora de Colombia. Días sin
#: entrada = cerrado. Los festivos no se contemplan (`services/horario.py`).
HORARIO_ASESORES: Dict[str, Any] = {
    "tz": "America/Bogota",
    "dias": {
        "lun": ["08:00", "18:00"],
        "mar": ["08:00", "18:00"],
        "mie": ["08:00", "18:00"],
        "jue": ["08:00", "18:00"],
        "vie": ["08:00", "18:00"],
        "sab": ["08:00", "13:00"],
    },
}

#: Aviso de ausencia (curso: «mensaje de ausencia con llamada a la acción»).
#: El motor lo agrega a todo traspaso fuera de horario y cambia {cuando} por
#: «mañana a partir de las 8:00 a.m.», «el lunes a partir…», etc. Las horas
#: escritas tienen que coincidir con `HORARIO_ASESORES` (lo verifica un test).
MENSAJE_AUSENCIA = (
    "Nuestros asesores atienden de *lunes a viernes de 8:00 a.m. a 6:00 p.m.* "
    "y *sábados de 8:00 a.m. a 1:00 p.m.* 🕗 Te escriben {cuando}. Mientras "
    "tanto, déjame por aquí la fecha que te sirve, cuántas personas viajan y "
    "tus datos (*nombre completo* y *cédula*), y te escriben con todo listo 🙌"
)

#: El comprobante en la etapa `pago`: el motor traspasa antes de llamar al
#: modelo, con este texto ({cuando} según el horario) y este motivo.
COMPROBANTE_A_ASESOR: Dict[str, str] = {
    "texto": (
        "¡Gracias! 🙌 Recibimos tu comprobante. Un compañero verifica el pago "
        "y te confirma la reserva por aquí {cuando} ✨"
    ),
    "motivo": "comprobante de pago",
}

#: Si el modelo pasa la conversación a un asesor sin escribirle nada al
#: cliente, el sistema pone esto (y, fuera de horario, el aviso de ausencia).
#: Neutro: no sabe el motivo. En el bot 3 los datos de reserva NO traspasan
#: (llevan a /pago), así que no habla de «tus datos».
AVISO_EN_TRASPASO = (
    "Te paso con un compañero del equipo para que te ayude con eso 🙌 Te "
    "escribe por aquí 💬"
)

#: Recordatorios por etapa del embudo: [15 min, 5 h, 23 h], los mismos tiempos
#: del bot 1. El runner toma el de la etapa en que quedó la sesión; si falta,
#: el texto fijo de siempre. Cortos, sin montos (el runner no tiene la
#: cotización) y, salvo cuando se piden datos o el comprobante, con opciones
#: numeradas: el recordatorio queda en el historial y `respuesta_por_numero`
#: resuelve el «2» contra él. `comprobante` y `asesor` no llevan: ahí la
#: conversación ya está con una persona.
RECORDATORIOS_POR_ETAPA: Dict[str, List[str]] = {
    "bienvenida": [
        "¿Te ayudo a elegir? 😊 👇\n1️⃣ Ver precios por mes 📅\n"
        "2️⃣ Ver los hoteles 🏨\n3️⃣ Hablar con un asesor",
        "¡Hola de nuevo! 👋 El *Plan Tolú & Coveñas* sigue disponible 🌴 "
        "¿Te muestro los precios? 👇\n1️⃣ Sí, muéstrame\n2️⃣ Más adelante",
        "Última razón por hoy 🌴 Si quieres retomar, respóndeme con un "
        "número 👇\n1️⃣ Ver precios\n2️⃣ Hablar con un asesor\n"
        "3️⃣ Ya no me interesa",
    ],
    # Ya vio las salidas del mes con su precio (bloque /fechas).
    "mes": [
        "¿Ya elegiste tu salida? 📅 👇\n1️⃣ Sí, ya sé cuál\n"
        "2️⃣ Quiero ver otras fechas\n3️⃣ Tengo una pregunta 🤔",
        "¡Hola de nuevo! 👋 ¿Seguimos con tu plan a Coveñas? 🌴 👇\n"
        "1️⃣ Sí, sigamos\n2️⃣ Prefiero otro mes\n3️⃣ Tengo una pregunta 🤔",
        "Última razón por hoy 🌴 Si te animas, te ayudo a elegir la salida 👇\n"
        "1️⃣ Sí, sigamos\n2️⃣ Hablar con un asesor\n3️⃣ Ya no me interesa",
    ],
    # Eligió salida y se le mostraron los hoteles (bloque /hotel), o ya
    # eligió hotel y falta cuántos van.
    "fecha": [
        "¿Cuál hotel te gustó más? 🏨 👇\n1️⃣ Amor de Dios\n2️⃣ Bohíos\n"
        "3️⃣ Piedra Mar\n4️⃣ Ver fotos y videos 🎥",
        "¡Hola de nuevo! 👋 ¿Cuántas personas viajarían? Así te doy el "
        "total 👇\n1️⃣ 1 persona\n2️⃣ 2 personas\n3️⃣ 3 o más\n"
        "4️⃣ Vamos con niños 👧",
        "Última razón por hoy 🌴 ¿Seguimos con tu cotización? 👇\n"
        "1️⃣ Sí, sigamos\n2️⃣ Hablar con un asesor\n3️⃣ Ya no me interesa",
    ],
    "cotizacion": [
        "¿Te aparto el cupo? 🙌 👇\n1️⃣ Sí, quiero reservar ✅\n"
        "2️⃣ Tengo una pregunta 🤔\n3️⃣ Lo voy a consultar 💬",
        "¡Hola de nuevo! 👋 Apartas tu cupo con un anticipo y el resto lo "
        "pagas antes del viaje 🙌 ¿Seguimos? 👇\n1️⃣ Sí, quiero reservar ✅\n"
        "2️⃣ Tengo una pregunta 🤔",
        "Última razón por hoy 🌴 Si ya lo hablaron y se animan, aquí estoy 😊 👇\n"
        "1️⃣ Quiero reservar ✅\n2️⃣ Hablar con un asesor\n3️⃣ Ya no me interesa",
    ],
    "reserva": [
        "Para apartar tu cupo solo me faltan tu *nombre completo* y tu "
        "*cédula* 📝 ¿Me los compartes por aquí?",
        "¡Hola de nuevo! 👋 Tu reserva sigue pendiente: me faltan tu *nombre "
        "completo* y tu *cédula* 📝 👇\n1️⃣ Ya te los mando\n"
        "2️⃣ Tengo una pregunta 🤔",
        "Última razón por hoy 🌴 Si quieres seguir con la reserva, mándame tu "
        "*nombre completo* y tu *cédula* y la dejamos lista 🙌",
    ],
    # /pago_seguimiento
    "pago": [
        "¿Pudiste hacer el pago? 👇\n1️⃣ Ya pagué ✅\n2️⃣ Tuve un problema 😕\n"
        "3️⃣ Lo hago más tarde",
        "¡Hola de nuevo! 👋 Para confirmar tu reserva solo falta el anticipo 💳 "
        "¿Cómo vas? 👇\n1️⃣ Ya pagué, te mando el comprobante 📎\n"
        "2️⃣ Tuve un problema 😕\n3️⃣ Lo hago más tarde",
        "Última razón por hoy 🌴 Cuando hagas el anticipo, mándame el "
        "*comprobante* por aquí 📎 y un compañero te confirma la reserva ✨",
    ],
    "cliente": [
        "¿Te ayudo con algo más de tu viaje? 😊 👇\n1️⃣ Hora y punto de salida 🚌\n"
        "2️⃣ Qué llevar 🎒\n3️⃣ Hablar con un asesor\n4️⃣ Nada más, gracias",
        "Aquí sigo por si necesitas algo de tu viaje 🌴 👇\n"
        "1️⃣ Hablar con un asesor\n2️⃣ Todo bien, gracias",
        "¡Que disfrutes mucho tu viaje! 🌴 Si necesitas algo, escríbeme por "
        "aquí 😊",
    ],
}

#: Saludo para quien vuelve en una conversación nueva (ya habló antes con el
#: bot): el motor lo manda sin llamar al modelo. Dos textos:
#:   - `con_contexto`: si el runner trae el mes o el hotel de la última vez.
#:     `{mes_hotel}` lo arma el motor ya formateado para WhatsApp, p. ej.
#:     «*diciembre* en *Amor de Dios*», «*diciembre*» o «*Piedra Mar*».
#:   - `sin_contexto`: si no hay nada que recordar.
#: NOTA para el motor: el placeholder es `{mes_hotel}` (str.format); si el
#: motor prefiere otro formato, se cambia aquí y en su test.
BIENVENIDA_REGRESO: Dict[str, str] = {
    "con_contexto": (
        "¡Hola de nuevo! 😊 La última vez miraste {mes_hotel}. ¿Seguimos? 👇\n"
        "1️⃣ Seguir con esa cotización\n2️⃣ Ver otras fechas 📅\n"
        "3️⃣ Tengo una pregunta 🤔"
    ),
    "sin_contexto": (
        "¡Hola de nuevo! 😊 ¿Seguimos con tu plan a Coveñas? 👇\n"
        "1️⃣ Ver salidas y precios 📅\n2️⃣ Seguir donde íbamos\n"
        "3️⃣ Tengo una pregunta 🤔"
    ),
}

#: Lo que el bot 3 enciende por encima del bot 1, con su valor.
FLAGS_VARIANTE_C: Dict[str, Any] = {
    # Identidad. El actualizador del bot 1 se salta todo bot con `variante`.
    "variante": "C",
    **{clave: copy.deepcopy(FLAGS_VARIANTE_B[clave]) for clave in REUTILIZADAS_DE_B},
    # Propio: en el bot 3 los datos de reserva no traspasan.
    "aviso_en_traspaso": AVISO_EN_TRASPASO,
    # Menú de bienvenida con los meses que tienen salidas (del tarifario).
    "menu_meses": True,
    # «2» → la opción 2 del último mensaje, como dato del sistema.
    "respuesta_por_numero": True,
    # Cada mensaje cierra con opciones numeradas o sí/no (una corrección).
    "opciones_cerradas": True,
    # Etapa del embudo por turno → recordatorios y medición.
    "etapas_funnel": True,
    "horario_asesores": HORARIO_ASESORES,
    "mensaje_ausencia": MENSAJE_AUSENCIA,
    "comprobante_a_asesor": COMPROBANTE_A_ASESOR,
    "recordatorios_por_etapa": RECORDATORIOS_POR_ETAPA,
    # Camino de atención al cliente: herramienta `marcar_cliente(tema)`.
    "cliente_con_reserva": True,
    # Saludo de regreso (lo manda el motor sin modelo).
    "bienvenida_regreso": BIENVENIDA_REGRESO,
    # Quien vuelve en una sesión nueva recibe «Ya hablaron antes» (no se
    # presenta otra vez), y el saludo sale de la franja del día en Colombia
    # (mañana / tarde / noche; sólo la franja, para no romper la caché).
    "contexto_de_regreso_y_hora": True,
    # ── Arreglos de motor tras QA contra Bedrock (2026-10-10) ──────────────
    # A2: la duración se valida contra todo el turno y lo consultado antes.
    "duracion_con_sesion": True,
    # A3: «un compañero te lo confirma» sin pasar la conversación → corrección
    # y, si persiste, traspaso de verdad («pregunta sin respuesta»).
    "escalar_si_promete": True,
    # M0: quien vuelve y sólo saluda recibe `bienvenida_regreso` sin modelo.
    "regreso_sin_modelo": True,
    # M1: «Déjame consultar…», «Ahora sí.», «Tienes razón.» no le llegan.
    "recortar_narracion": True,
    # M2: eligió salida u hotel → precios sólo tras consultar esa salida.
    "consulta_obligatoria_por_salida": True,
    # M3: lo que cambia por turno va en un segundo bloque del system, sin caché.
    "system_en_dos_bloques": True,
    # M4: la burbuja que sólo trae las opciones se pega a su pregunta.
    "unir_opciones": True,
    # R3: el menú de edades de niños sale de los extras del tarifario.
    "menu_edades_ninos": True,
    # Si una corrección se come la última ronda, el turno no queda a medias:
    # texto fijo y asesor.
    "turno_nunca_vacio": True,
    # El mismo adjunto no sale dos veces en un turno.
    "media_sin_repetir": True,
}


LLM_CONFIG_C: Dict[str, Any] = {
    **copy.deepcopy(LLM_CONFIG),
    "context_key": CONTEXT_KEY_C,
    **copy.deepcopy(FLAGS_VARIANTE_C),
    # Mismos minutos, cadena y etiqueta de abandono que el bot 1, por
    # construcción: el texto lo cambia `recordatorios_por_etapa`, no esto.
    "seguimiento": copy.deepcopy(LLM_CONFIG["seguimiento"]),
}
