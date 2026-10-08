"""Señales deterministas sobre lo que escribe el cliente (bot 2 de Arranquemos Pues).

Todo aquí es puro: texto entra, booleano o conjunto sale. Sin BD, sin modelo,
sin logs. `llm_engine` las usa detrás de flags de `llm_config`, así que el bot 1
(y los de mascotas, Gloma o Natulcé, que comparten el motor) no las ven.

Por qué en código y no en el prompt: es la lección de
`gotcha_insistir_en_el_prompt_no_sirve` — cuando el modelo no se olvida sino que
*elige* entre dos reglas, repetirle la instrucción empata con el baseline. Lo
que no puede fallar se decide aquí.

Tres familias:

- **Nombres genéricos** (#9): el bot llegó a guardar «Cliente» y «No
  proporcionado» como nombre de la persona, y el perfil de WhatsApp trae a veces
  «Casa» o el nombre de un negocio. Nada de eso es un nombre.
- **Decisión aplazada** (#14): «lo consulto con mi esposo» no es una despedida.
- **Montos** (#20): detectar que el cliente nombró una cifra concreta («350 mil»,
  «$350.000», «350k») y extraer las cifras que dijo, para que el guardarraíl de
  precio le permita al bot repetirlas.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Set

__all__ = [
    "normalizar",
    "es_nombre_generico",
    "es_aplazamiento",
    "mes_mencionado",
    "menciona_monto",
    "monto_mencionado",
    "es_presupuesto",
    "cifras",
    "NOMBRES_GENERICOS",
]


def normalizar(texto: object) -> str:
    """Minúsculas, sin tildes y con los espacios colapsados. Conserva `ñ`,
    dígitos y signos: los patrones de abajo los necesitan."""
    crudo = unicodedata.normalize("NFD", str(texto or "").lower())
    sin_tildes = "".join(
        c for c in crudo
        if unicodedata.category(c) != "Mn" or c == "̃"  # la virgulilla de ñ
    )
    sin_tildes = unicodedata.normalize("NFC", sin_tildes)
    return " ".join(sin_tildes.split())


# ---------------------------------------------------------------------------
# Nombres genéricos (#9)
# ---------------------------------------------------------------------------

#: Lo que el modelo escribe cuando NO sabe el nombre y llama `registrar_nombre`
#: igual, y lo que trae un perfil de WhatsApp que no es una persona. Se compara
#: el valor completo ya normalizado (sin tildes, minúsculas).
NOMBRES_GENERICOS = frozenset({
    # Rellenos del modelo (vistos en producción: «Cliente» ×4, «No
    # proporcionado» ×2).
    "cliente", "el cliente", "la cliente", "clienta", "usuario", "usuaria",
    "no proporcionado", "no proporcionada", "no proporciono", "no lo dio",
    "no lo dijo", "no dio su nombre", "no dijo su nombre", "no indicado",
    "no indicada", "no informado", "no especificado", "no especificada",
    "sin nombre", "sin especificar", "sin dato", "sin datos", "nombre",
    "su nombre", "tu nombre", "desconocido", "desconocida", "anonimo",
    "anonima", "pendiente", "por confirmar", "por definir", "ninguno",
    "ninguna", "n/a", "na", "nn", "x", "xx", "xxx", "prueba", "test",
    "contacto", "persona", "interesado", "interesada", "prospecto",
    "viajero", "viajera", "huesped",
    # Tratamientos sin nombre.
    "senor", "senora", "señor", "señora", "sr", "sra", "don", "dona", "doña",
    "caballero", "dama", "joven", "amigo", "amiga", "hermano", "hermana",
    "vecino", "vecina", "mi amor", "amor", "corazon", "reina", "rey",
    "mami", "papi", "mama", "papa", "mamá", "papá", "bebe", "bb",
    # Perfiles de WhatsApp que no son una persona.
    "casa", "hogar", "familia", "la familia", "mi familia", "oficina",
    "trabajo", "personal", "celular", "cel", "movil", "telefono", "whatsapp",
    "wa", "yo", "hola", "hi", "hello", "dios", "dios es amor",
    "dios te bendiga", "bendiciones", "feliz", "info", "informacion",
    "ventas", "admin", "administracion", "gerencia", "recepcion", "soporte",
})

#: Palabras que delatan un negocio o un rol, no una persona («Mecánica JR»,
#: «Tienda La 14», «Distribuidora X SAS»). Basta que aparezca una.
_PALABRAS_DE_NEGOCIO = frozenset({
    "mecanica", "taller", "tienda", "almacen", "ferreteria", "distribuidora",
    "distribuciones", "comercializadora", "inversiones", "sas", "s.a.s",
    "ltda", "s.a", "drogueria", "papeleria", "peluqueria", "barberia",
    "salon", "restaurante", "panaderia", "cafeteria", "minimercado",
    "supermercado", "agencia", "viajes", "tours", "turismo", "hotel",
    "inmobiliaria", "constructora", "servicios", "soluciones", "store",
    "shop", "boutique", "spa", "estetica", "consultorio", "clinica",
    "odontologia", "veterinaria", "motos", "repuestos", "importaciones",
    "empresa", "negocio", "cliente", "usuario", "proporcionado",
    "proporcionada", "desconocido", "desconocida",
})

_SOLO_LETRAS_RE = re.compile(r"[a-zñ]")


def es_nombre_generico(valor: object) -> bool:
    """¿El valor es un relleno, un tratamiento o un negocio en vez de un nombre?

    No decide si es un nombre *válido* (dígitos, largo): eso lo hace
    `llm_engine.nombre_saneado`. Esto es la capa de encima: «Cliente» pasa el
    saneado y aquí se cae.

    Conservador hacia el lado de **rechazar**: rechazar un nombre raro cuesta
    que el bot no lo guarde (y lo pida al reservar, como ya hace); guardarlo mal
    cuesta una ficha con «Cliente» que el asesor ve en la cola de llamadas.
    """
    texto = normalizar(valor).strip(" .,;:-_*\"'")
    if not texto or not _SOLO_LETRAS_RE.search(texto):
        return True
    if texto in NOMBRES_GENERICOS:
        return True
    palabras = re.findall(r"[a-zñ.]+", texto)
    return any(p.strip(".") in _PALABRAS_DE_NEGOCIO or p in _PALABRAS_DE_NEGOCIO
               for p in palabras)


# ---------------------------------------------------------------------------
# Decisión aplazada (#14)
# ---------------------------------------------------------------------------

_CON_QUIEN = (
    r"(?:mi|mis|el|la|los|las|nuestra|nuestro)\s+"
    r"(?:esposo|esposa|pareja|novio|novia|marido|mujer|mama|mami|papa|papi|"
    r"madre|padre|familia|hijos?|hijas?|amigos?|amigas?|grupo|jefe|jefa|"
    r"hermanos?|hermanas?|socio|socia|parceros?|parceras?|gente|"
    r"companer[oa]s?|primos?|primas?|acompanantes?|senora|senor|esposa)"
)
_VERBO_CONSULTA = (
    r"(?:consult|habl|valid|coment|cuadr|revis|mir|pens|organiz|program|"
    r"confirm|averigu|defin|decid|cotiz|cuadr|charl|analiz|pregunt|ver)\w*"
)

#: Formas en que una persona dice «todavía no», no «no». Sobre texto ya
#: normalizado (sin tildes, minúsculas). Frases reales del informe: «Voy a
#: validar con mi pareja y le comento», «Mil gracias, lo voy a consultar con mi
#: esposo», «Déjame cuadro unas cosas y te confirmo más tarde», «debo hablar
#: primero con mi pareja», «tengo que programar con la familia».
_APLAZAMIENTO_RE = re.compile(
    "|".join([
        # «lo consulto con mi esposo», «voy a hablar con mi madre»
        rf"\b{_VERBO_CONSULTA}\s+(?:\w+\s+){{0,3}}con\s+{_CON_QUIEN}\b",
        # «lo consulto», «lo pensamos», «lo hablo»
        r"\blo\s+(?:voy\s+a\s+|vamos\s+a\s+)?(?:pienso|pensamos|pensare|pensar|"
        r"consulto|consultamos|consultar|hablo|hablamos|hablar|reviso|revisamos|"
        r"revisar|miro|miramos|mirar|analizo|analizamos|analizar|cuadro|"
        r"cuadramos|cuadrar|valido|validamos|validar|organizo|organizamos)\b",
        # «déjame cuadrar unas cosas», «dame unos días y lo pienso»
        r"\b(?:dejame|dejeme|dejenme|permiteme|permitame|dame|deme)\s+"
        r"(?:\w+\s+){0,2}(?:cuadr|pens|mir|revis|consult|habl|organiz|valid|"
        r"analiz|verific|cheque|confirm|ver\b|unos\s+dias|un\s+tiempo|un\s+rato)",
        # «te confirmo más tarde», «le comento», «te estaré avisando»
        r"\b(?:te|le|les)\s+(?:confirmo|aviso|comento|cuento|escribo|digo|"
        r"respondo|contesto|confirmamos|avisamos|comentamos|escribimos)\b"
        r"(?!\s*(?:que\b|:|\d|el\b|la\b|los\b|las\b|una?\b|cuantos?\b|si\b))",
        r"\b(?:te|le|les)\s+(?:estare|estaremos|estoy)\s+"
        r"(?:avisando|escribiendo|confirmando|comentando|contando)\b",
        # «debo hablar primero con…», «tengo que programar…», «voy a pensarlo»
        r"\b(?:debo|debemos|tengo\s+que|tenemos\s+que|toca|me\s+toca|nos\s+toca|"
        r"necesito|necesitamos|voy\s+a|vamos\s+a)\s+(?:\w+\s+)?"
        r"(?:hablar|consultar|preguntar|revisar|cuadrar|organizar|programar|"
        r"validar|pensar|pensarlo|analizar|mirarlo|definir|decidir|cotizar|"
        r"confirmar)\b",
        # «todavía no sé», «aún no estamos seguros»
        r"\b(?:todavia|aun)\s+no\s+(?:se|sabemos|estoy|estamos|hemos|he|"
        r"tengo|tenemos|decid|defin)",
        # «más adelante te escribo», «luego le confirmo»
        r"\b(?:mas\s+tarde|mas\s+adelante|luego|despues|ahorita|en\s+estos\s+dias|"
        r"en\s+la\s+noche|esta\s+noche|en\s+la\s+tarde|manana|el\s+fin\s+de\s+"
        r"semana|la\s+otra\s+semana|la\s+proxima\s+semana)\s+"
        r"(?:te|le|les)\s+(?:escribo|confirmo|aviso|digo|cuento|comento|"
        r"contesto|respondo|hablo|marco)\b",
    ]),
)


def es_aplazamiento(texto: object) -> bool:
    """¿La persona dejó la decisión para después («lo consulto y te aviso»)?

    No es lo mismo que despedirse: quien aplaza sigue en la compra, y el
    reenganche de las próximas horas es justo para ella. Cerrar esa
    conversación con `finalizar_conversacion` o `no_responder` es lo que dejó
    17 decisiones aplazadas archivadas como despedidas en septiembre.

    Un falso positivo cuesta poco (la conversación queda abierta y la persona
    recibe un recordatorio); un falso negativo cuesta una venta. Por eso la red
    es ancha.
    """
    return bool(_APLAZAMIENTO_RE.search(normalizar(texto)))


# ---------------------------------------------------------------------------
# Mes mencionado (#4: flyer del primer mensaje)
# ---------------------------------------------------------------------------

_MESES = {
    "enero": 1, "ene": 1, "febrero": 2, "feb": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "ago": 8,
    "septiembre": 9, "setiembre": 9, "sept": 9, "sep": 9, "octubre": 10,
    "oct": 10, "noviembre": 11, "nov": 11, "diciembre": 12, "dic": 12,
}
_MES_RE = re.compile(r"\b(" + "|".join(sorted(_MESES, key=len, reverse=True)) + r")\b")


def mes_mencionado(texto: object) -> "int | None":
    """El primer mes que nombra el cliente («¿cuánto vale en diciembre?» → 12).

    Estricto a propósito, a diferencia de `tarifario.normalizar_mes` (pensado
    para lo que escribe el modelo en la herramienta): sólo nombres de mes como
    palabra completa. «Soy mayor de edad» no es mayo y «somos 4» no es abril.
    """
    m = _MES_RE.search(normalizar(texto))
    return _MESES[m.group(1)] if m else None


# ---------------------------------------------------------------------------
# Montos (#20)
# ---------------------------------------------------------------------------

_UNIDADES = ("", "un", "dos", "tres", "cuatro", "cinco", "seis", "siete",
             "ocho", "nueve")
_DIEZ_A_VEINTINUEVE = {
    10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce",
    15: "quince", 16: "dieciseis", 17: "diecisiete", 18: "dieciocho",
    19: "diecinueve", 20: "veinte", 21: "veintiun", 22: "veintidos",
    23: "veintitres", 24: "veinticuatro", 25: "veinticinco", 26: "veintiseis",
    27: "veintisiete", 28: "veintiocho", 29: "veintinueve",
}
_DECENAS = ("", "", "", "treinta", "cuarenta", "cincuenta", "sesenta",
            "setenta", "ochenta", "noventa")
_CENTENAS = ("", "ciento", "doscientos", "trescientos", "cuatrocientos",
             "quinientos", "seiscientos", "setecientos", "ochocientos",
             "novecientos")


def _en_letras(n: int) -> str:
    """1–999 en palabras, como se escribe antes de «mil» («trescientos
    cincuenta»). Sin tildes, porque se compara contra texto normalizado."""
    if not 0 < n < 1000:
        return ""
    if n == 100:
        return "cien"
    partes = []
    c, resto = divmod(n, 100)
    if c:
        partes.append(_CENTENAS[c])
    if resto:
        if resto < 10:
            partes.append(_UNIDADES[resto])
        elif resto < 30:
            partes.append(_DIEZ_A_VEINTINUEVE[resto])
        else:
            d, u = divmod(resto, 10)
            partes.append(_DECENAS[d] + (f" y {_UNIDADES[u]}" if u else ""))
    return " ".join(partes)


#: Antes y después de una cifra no puede haber otro dígito ni un separador
#: pegado a otro dígito: así «1.350.000» no cuenta como «350.000».
_ANTES = r"(?<![\d.,])(?<!\d\s)"
#: …ni un espacio y más dígitos: «mi cel es 350 000 1234» es un teléfono, no
#: la promo (auditoría B5).
_DESPUES = r"(?![\d]|[.,\s]\d)"


def _patron_monto(monto: int) -> "re.Pattern":
    """Todas las formas de escribir `monto` que se han visto en el chat."""
    opciones = []
    digitos = str(monto)
    # 350000 / 350.000 / 350,000 / 350 000 / $350.000
    grupos = []
    while digitos:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    opciones.append(_ANTES + r"\$?\s*" + r"[.,\s]?".join(grupos) + _DESPUES)
    if monto % 1000 == 0:
        miles = monto // 1000
        # 350 mil / 350mil / 350k / 350 lucas / $350 mil
        opciones.append(
            _ANTES + rf"\$?\s*{miles}\s*(?:mil\b|k\b|lucas\b|luks\b)"
        )
        # $350 (con el signo: sin él, «350» suelto es demasiado ambiguo)
        opciones.append(rf"\$\s*{miles}" + _DESPUES + r"(?!\s*(?:mil|k)\b)")
        letras = _en_letras(miles) if miles < 1000 else ""
        if letras:
            opciones.append(rf"\b{letras}\s+mil\b")
    if monto % 100_000 == 0 and monto >= 1_000_000:
        entero, decimal = divmod(monto, 1_000_000)
        num = str(entero) if not decimal else (
            f"{entero}[.,]{str(decimal).rstrip('0')[:1]}"
        )
        opciones.append(_ANTES + rf"{num}\s*(?:millones|millon|palos?)\b")
    return re.compile("|".join(f"(?:{o})" for o in opciones))


def monto_mencionado(texto: object, montos: Iterable[object]) -> "int | None":
    """El primero de estos montos que nombró el cliente, escrito como sea, o
    None.

    `montos` viene de la config (`promo_inexistente.montos`), nunca del código:
    el día que la agencia cambie el flyer, cambia la config.
    """
    normal = normalizar(texto)
    if not normal:
        return None
    for crudo in montos or ():
        try:
            monto = int(crudo)
        except (TypeError, ValueError):
            continue
        if monto <= 0:
            continue
        if _patron_monto(monto).search(normal):
            return monto
    return None


def menciona_monto(texto: object, montos: Iterable[object]) -> bool:
    """¿El cliente nombró alguno de estos montos? (ver `monto_mencionado`)"""
    return monto_mencionado(texto, montos) is not None


#: El cliente habla de lo que TIENE para gastar, no de algo que vio publicado.
_PRESUPUESTO_RE = re.compile(
    r"\b(?:tengo|tenemos|cuento\s+con|contamos\s+con|presupuesto|me\s+alcanza|"
    r"nos\s+alcanza|alcanza|puedo\s+gastar|podemos\s+gastar|quiero\s+gastar|"
    r"gastar|maximo|como\s+maximo|hasta|tope|dispongo|disponemos|ahorrado|"
    r"ahorre|ahorramos|pagar\s+maximo|plata|dinero)\b"
)
#: …o de algo que vio en la publicidad.
_PUBLICIDAD_RE = re.compile(
    r"\b(?:promo|promocion|promociones|oferta|ofertas|flyer|flayer|volante|"
    r"anuncio|publicidad|publicacion|post|imagen|lunes\s+a\s+jueves|"
    r"lunes\s+con\s+jueves|entre\s+semana|vi|vimos|dice|decia|aparece|"
    r"salia|salen\s+desde)\b"
)


def es_presupuesto(texto: object) -> bool:
    """¿El monto que nombró es su presupuesto («tengo 350 mil por persona»)
    y no la promoción del flyer? Ante la duda, NO es presupuesto: el texto
    de la promoción es el caso por defecto de #20."""
    normal = normalizar(texto)
    return bool(_PRESUPUESTO_RE.search(normal)) and not _PUBLICIDAD_RE.search(normal)


_CIFRA_RE = re.compile(
    _ANTES
    + r"(\d{1,3}(?:[.,]\d{3}){1,4}|\d{1,15})(?![\d])(?:[.,](\d{1,2}))?"
    + r"\s*(millones|millon|palos?|mil\b|k\b|lucas\b)?"
)


def cifras(texto: object) -> Set[int]:
    """Las cifras de plata que aparecen en lo que escribió el cliente, en pesos.

    Para el guardarraíl de precio: si el cliente dijo «tengo 450 mil», el bot
    puede repetirle «$450.000» sin que eso cuente como un precio inventado.
    Un número sin unidad y por debajo de 10.000 se lee también en miles («tengo
    450» son 450 mil), igual que `tarifario.normalizar_presupuesto`. Lo que
    queda por debajo de 1.000 no es plata y no se devuelve.
    """
    salida: Set[int] = set()
    for m in _CIFRA_RE.finditer(normalizar(texto)):
        entero = int(re.sub(r"[.,]", "", m.group(1)))
        decimal = m.group(2)
        unidad = m.group(3) or ""
        if unidad.startswith(("millon", "palo")):
            valor = entero * 1_000_000
            if decimal:
                valor += int(decimal.ljust(2, "0")[:2]) * 10_000
            salida.add(valor)
            continue
        if unidad in ("mil", "k", "lucas"):
            salida.add(entero * 1_000)
            continue
        if entero >= 1_000:
            salida.add(entero)
        elif entero > 0:
            salida.add(entero * 1_000)
    return {v for v in salida if v >= 1_000}
