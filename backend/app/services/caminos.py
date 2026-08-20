"""Cómo se le nombra a cada `camino` de un bot cuando se muestra a una persona.

`bot_llm_decisions.camino` es un slug que produce el motor LLM (`llm_engine`) a
partir de las herramientas que llamó el bot o del clasificador por keywords de
`llm_config.caminos`. Sirve para responder de un vistazo "¿a qué vino esta
persona?": buscó su mascota, pidió precios, agendó una demo.

El catálogo es **por cuenta** porque el mismo slug no significa lo mismo en dos
negocios: `reserva` en la agencia de viajes es un cupo apartado, y no existe en
el bot de mascotas. Por eso `etiqueta()` recibe el bot y busca primero en el
catálogo de esa cuenta, después en los genéricos y, si el slug es nuevo, lo
vuelve legible en vez de esconderlo — un camino sin etiqueta es un camino que
alguien agregó al bot y todavía no documentamos aquí, no un error.

Nota: el panel de mascotas (`routers/mascotas.py`) mantiene su propia copia de
las etiquetas, que es la que gobierna ESA pantalla. Este módulo nació después,
para la ventana de supervisión que mira varias cuentas a la vez, y no se
entromete con ella.
"""
from __future__ import annotations

from typing import Dict, Optional

# Caminos que emite cualquier bot LLM, sin importar el negocio.
GENERICOS: Dict[str, str] = {
    "saludo": "👋 Saludo",
    "fin": "👋 Cierre",
    "respuesta_libre": "💬 Conversación",
    "failsafe": "⚠️ Error del motor",
    "escalar_a_asesor": "🙋 Pidió un asesor",
    "escalamiento": "🙋 Pidió un asesor",
    "handoff": "🙋 Pasó a un asesor",
}

# Bot "Huella" de `recuperatumascota@gmail.com`.
MASCOTAS: Dict[str, str] = {
    "busqueda_mascota": "🔎 Buscó su mascota",
    "buscar_mascota": "🔎 Buscó su mascota",
    "ficha_mascota": "🐾 Vio una ficha",
    "mascota_reconocida": "🎉 Reconoció a su mascota",
    "reportar_encontrada": "🐾 Reportó una encontrada",
    "reporte_registrado": "📝 Registró un caso",
    "descarga_listado": "📊 Descargó el listado",
    "terremoto": "🌎 Preguntó por la emergencia",
    "agradecimiento": "🤍 Agradeció",
}

# Bot "Plan Tolú & Coveñas" de `arranquemospues.marketing@gmail.com`.
VIAJES: Dict[str, str] = {
    "info_general": "ℹ️ Preguntó por el plan",
    "hotel": "🏨 Preguntó por el hotel",
    "tours": "🏝️ Preguntó por los tours",
    "itinerario": "🗺️ Pidió el itinerario",
    "precios_condiciones": "💲 Preguntó precios",
    "precios": "💲 Preguntó precios",
    "reserva": "✅ Apartó un cupo",
    "pagos": "💳 Preguntó cómo pagar",
    "pago_registrado": "💰 Pagó",
}

# Bot institucional "Lía" de `gloma@glomabeauty.com` (landing y demo).
GLOMA: Dict[str, str] = {
    "que_es_gloma": "❓ Qué es Gloma",
    "demo_inicio": "🎬 Empezó la demo",
    "demo_agendada": "📅 Agendó una demo",
    "ventas": "🛒 Interés comercial",
    "integraciones": "🔌 Preguntó por integraciones",
    "personalidad_marca": "🎨 Personalidad de marca",
}

# Bot "Jerarquía IA" de `jerarquia@demo.com` (demo de cierre de venta).
JERARQUIA: Dict[str, str] = {
    "venta": "🛒 Negoció la compra",
    "venta_registrada": "💰 Cerró la venta",
    "catalogo": "📖 Vio el catálogo",
}

# Bot "Talulah IA" de `talulah@gloma.com`.
TALULAH: Dict[str, str] = {
    "catalogo": "📖 Vio el catálogo",
    "tallas": "📏 Preguntó por tallas",
    "estado_pedido": "📦 Preguntó por su pedido",
}

# Qué catálogo aplica a cada cuenta. La clave es el correo del dueño del bot.
POR_CUENTA: Dict[str, Dict[str, str]] = {
    "recuperatumascota@gmail.com": MASCOTAS,
    "arranquemospues.marketing@gmail.com": VIAJES,
    "gloma@glomabeauty.com": GLOMA,
    "jerarquia@demo.com": JERARQUIA,
    "talulah@gloma.com": TALULAH,
}

# Caminos que cuentan como "a esto vino la persona". El resto (saludo, cierre,
# charla suelta) es relleno: se ve al abrir el hilo, pero no se destaca en el
# resumen de la lista, que es donde el CEO barre de un vistazo.
_RELLENO = frozenset({"saludo", "fin", "respuesta_libre", "failsafe"})


def catalogo(correo: Optional[str]) -> Dict[str, str]:
    """Etiquetas que aplican a la cuenta `correo`, genéricos incluidos."""
    propias = POR_CUENTA.get((correo or "").lower(), {})
    return {**GENERICOS, **propias}


def _legible(camino: str) -> str:
    """Un slug sin etiqueta se muestra igual, pero como texto: `precios_iva` →
    "Precios iva". Preferimos mostrarlo feo a esconderlo."""
    return camino.replace("_", " ").strip().capitalize() or camino


def etiqueta(camino: str, correo: Optional[str] = None) -> str:
    """Nombre legible del camino para la cuenta `correo`."""
    return catalogo(correo).get(camino) or _legible(camino)


def es_relleno(camino: str) -> bool:
    """¿Este camino es de los que no se destacan en el resumen del hilo?"""
    return camino in _RELLENO
