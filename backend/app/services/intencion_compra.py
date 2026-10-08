"""Detección determinista de intención de compra (estrategia #22).

`detectar(texto)` mira **solo lo que escribió el cliente** y devuelve cuáles de
los cuatro tipos de señal aparecen:

  - `anticipo`        pregunta cómo pagar, cuánto se abona o cómo separar.
  - `reservar`        pide reservar / apartar / "me lo llevo".
  - `fecha_concreta`  da un día concreto ("el 16 de diciembre", "del 16 al 19",
                      "16/12"); un mes suelto NO cuenta: "en diciembre" es
                      curiosidad, "el 16 de diciembre" ya es un plan.
  - `datos`           deja datos de la reserva: cuántos son, edades de los
                      niños, nombre completo, documento o correo.

Es la mitad determinista del registro; la otra mitad es la herramienta
`registrar_intencion` del motor, que el modelo llama cuando *entiende* una
intención que estas expresiones no ven. `bot_runner` une las dos.

Se prefiere perder una señal a inventarla: un falso positivo le pone a la
asesora en la lista a alguien que solo saludaba. Por eso una negación justo
antes ("no quiero reservar todavía") apaga la señal.

Puro: sin BD, sin red, sin logs. `fragmento_seguro` es lo único que se guarda
del texto del cliente, y sale sin teléfonos ni correos (se ven en el chat, no
hace falta duplicarlos en una lista).
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional

TIPOS = ("anticipo", "reservar", "fecha_concreta", "datos")

#: Largo máximo del fragmento que se guarda (columna `fragmento`).
MAX_FRAGMENTO = 160

_MESES = (
    r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre"
    r"|octubre|noviembre|diciembre)"
)
_DIAS = r"(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo)"
_NUM_PALABRA = (
    r"(?:dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|trece"
    r"|catorce|quince)"
)

#: Patrones sobre el texto ya normalizado (minúsculas, sin tildes).
_PATRONES = {
    "anticipo": [
        r"\banticipo\b",
        r"\babon(?:o|ar|amos|a|an|e|arle|ar\s+algo)\b",
        r"\bsepar(?:ar|a|an|e|o|amos|en|arlo|arla|arnos|arme)\b",
        r"\bconsign(?:ar|o|amos|acion|arles?)\b",
        r"\btransferencia\b",
        r"\b(?:numero\s+de\s+)?cuenta\s+(?:para|donde|a\s+la\s+que)\s+"
        r"(?:pagar|consignar|transferir)\b",
        r"\bmedios?\s+de\s+pago\b",
        r"\bcomo\s+(?:te|les|le)?\s*(?:pago|pagamos|puedo\s+pagar|se\s+paga|hago\s+el\s+pago)\b",
        r"\b(?:nequi|daviplata)\b",
        r"\bcuanto\s+(?:hay\s+que|toca|tengo\s+que|debo)\s+(?:dar|pagar|abonar|consignar)\b",
    ],
    "reservar": [
        r"\breserv(?:ar|o|amos|emos|en|arlo|arla|arnos|arme|ame|anos|alo|ala)\b",
        r"\b(?:hacer|hagamos|hago|hacemos)\s+(?:la|una)\s+reserva\b",
        r"\bapart(?:ar|o|amos|en|arlo|arla|arnos|arme|ame|anos)\b",
        r"\bme\s+(?:lo|la)\s+llevo\b",
        r"\bnos\s+(?:lo|la)\s+llevamos\b",
        r"\bquiero\s+(?:ese|este|el)\s+plan\b",
        r"\bqueremos\s+(?:ese|este|el)\s+plan\b",
        r"\b(?:nos|me)\s+anot(?:o|amos|as|an)\b",
        r"\bconfirm(?:o|amos)\s+(?:la\s+)?(?:reserva|el\s+viaje|el\s+plan|que\s+vamos)\b",
    ],
    "fecha_concreta": [
        rf"\b\d{{1,2}}\s+de\s+{_MESES}\b",
        # "del 16 al 19" — no "de 3 a 4", que suele ser cuántas personas.
        r"\bdel\s+\d{1,2}\s+al\s+\d{1,2}\b",
        r"\bentre\s+el\s+\d{1,2}\s+y\s+el\s+\d{1,2}\b",
        r"\b\d{1,2}\s*/\s*\d{1,2}(?:\s*/\s*\d{2,4})?\b",
        rf"\b{_DIAS}\s+\d{{1,2}}\b",
        r"\b20\d\d-\d{2}-\d{2}\b",
    ],
    "datos": [
        rf"\bsomos\s+(?:\d{{1,2}}|{_NUM_PALABRA})\b",
        rf"\b(?:\d{{1,2}}|{_NUM_PALABRA})\s+(?:adultos|personas|pasajeros|ninos|nin[ao]s?)\b",
        r"\bnin[oa]s?\s+de\s+\d{1,2}\s+anos?\b",
        r"\bmi\s+(?:nombre\s+(?:completo\s+)?es|cedula|documento|correo|email)\b",
        r"\ba\s+nombre\s+de\s+[a-zñ]+",
        r"\b(?:c\.?\s?c\.?|cedula|documento)\s*(?:es|:|#|no\.?)?\s*\d[\d.\s]{5,}",
        r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}",
    ],
}

_COMPILADOS = {
    tipo: [re.compile(p) for p in pats] for tipo, pats in _PATRONES.items()
}

#: "no quiero reservar", "todavía no vamos a separar": una negación hasta dos
#: palabras antes de la señal la apaga.
_NEGACION_ANTES = re.compile(r"\b(?:no|ni|nunca|tampoco)\b(?:\s+\S+){0,2}\s*$")

#: Teléfonos y documentos (≥7 dígitos con espacios o guiones) y correos. Los
#: precios usan puntos ("$1.200.000") y no caen aquí.
_TELEFONO = re.compile(r"\+?\d(?:[ \-]?\d){6,}")
_CORREO = re.compile(r"[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"(?i)\b(?:https?://|www\.)\S+")

#: Largo máximo del resumen que redacta el bot (columna `resumen`).
MAX_RESUMEN = 300


def _normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def detectar(texto_cliente: Optional[str]) -> List[str]:
    """Los tipos de intención que aparecen en el mensaje, en el orden de `TIPOS`.

    Lista vacía si no hay texto o no hay señal.
    """
    texto = _normalizar(texto_cliente or "")
    if not texto:
        return []
    encontrados: List[str] = []
    for tipo in TIPOS:
        for patron in _COMPILADOS[tipo]:
            if any(
                not _NEGACION_ANTES.search(texto[: m.start()])
                for m in patron.finditer(texto)
            ):
                encontrados.append(tipo)
                break
    return encontrados


def tipos_validos(tipos) -> List[str]:
    """Filtra y ordena una lista cualquiera a los cuatro tipos conocidos."""
    vistos = {str(t).strip() for t in (tipos or []) if isinstance(t, str)}
    return [t for t in TIPOS if t in vistos]


def texto_seguro(texto: Optional[str], limite: int) -> Optional[str]:
    """Un texto de terceros (el cliente o el modelo) listo para guardarse y
    mostrarse en la lista de Interesados.

    - sin caracteres de control ni de formato Unicode (categorías Cc/Cf: saltos
      raros, marcas de dirección, ancho cero), que sirven para disfrazar texto;
    - en una sola línea, con los espacios colapsados;
    - sin teléfonos, correos ni enlaces (se ven en el chat, no hace falta
      duplicarlos en una lista);
    - cortado a `limite` caracteres con "…".

    None si no queda nada.
    """
    if not isinstance(texto, str):
        return None
    sin_control = "".join(
        " " if unicodedata.category(c) in ("Cc", "Cf") else c for c in texto
    )
    limpio = re.sub(r"\s+", " ", sin_control).strip()
    if not limpio:
        return None
    limpio = _URL.sub("[enlace]", limpio)
    limpio = _CORREO.sub("[correo]", limpio)
    limpio = _TELEFONO.sub("[número]", limpio)
    if len(limpio) > limite:
        limpio = limpio[: limite - 1].rstrip() + "…"
    return limpio


def fragmento_seguro(texto: Optional[str], limite: int = MAX_FRAGMENTO) -> Optional[str]:
    """Lo que escribió el cliente, como se guarda en `fragmento` (≤160)."""
    return texto_seguro(texto, limite)
