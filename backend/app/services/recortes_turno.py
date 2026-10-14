"""Recortes deterministas del turno ya redactado (bot 2 de Arranquemos Pues).

Operan sobre la lista de `actions` que devuelve `llm_engine` (`say`,
`say_media`, `say_catalog`, `handoff`, `end`, `perfil`…) y sobre el texto de
cada mensaje. Son puras: no llaman al modelo ni tocan la BD, y se prueban sin
Bedrock. `llm_engine` las engancha detrás de flags de `llm_config`.

Lo que resuelven (estrategias del informe del 10-sep-2026):

- **#10 / #17 — una pregunta por turno.** El bot preguntaba y en el mismo
  segundo mandaba otro mensaje respondiéndose solo («¿Con quién tengo el
  gusto?» + los precios de diciembre). Regla: si un mensaje del bot termina en
  pregunta, el turno se cierra ahí. Los textos de después se descartan; los
  adjuntos de después se mueven antes de la pregunta, para que lo último que
  vea la persona sea la pregunta.
- **#21 — no interrogar al cliente por un precio nuestro** («¿de dónde sacaste
  esa cifra?»): el patrón vive aquí; el recorte lo hace `llm_engine` con su
  maquinaria de frases (`_sin_la_frase`).
- **#4 — el flyer del mes en el primer mensaje**, como pie de foto si cabe.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

__all__ = [
    "PREGUNTA_ORIGEN_PRECIO",
    "MAX_PIE_DE_FOTO",
    "termina_en_pregunta",
    "pide_respuesta",
    "una_sola_pregunta_al_final",
    "cortar_tras_pregunta",
    "poner_flyer",
    "sin_disculpa_inicial",
    "partir_por_marcas",
    "opciones_numeradas",
    "cierra_con_opciones",
    "promete_respuesta_de_otro",
    "es_narracion",
    "sin_narracion",
    "solo_opciones",
    "unir_opciones",
    "sin_pregunta_repetida",
    "adjuntos_antes_de_la_pregunta",
]

#: Tope de WhatsApp para el pie de una imagen o video. Por encima, Meta lo
#: rechaza; Twilio lo trunca. Ver `messaging/twilio_adapter.send_media`.
MAX_PIE_DE_FOTO = 1024

_ADJUNTOS = ("say_media", "say_catalog")

#: Preguntarle al cliente de dónde sacó un precio que publica la propia agencia
#: (conversación 543: «¿De dónde sacaste esa cifra?»). Se usa con
#: `solo_preguntas=True`: «lo vi en el flyer» dicho por el bot no se toca, la
#: pregunta sí.
_PRECIO = (
    r"(?:precio|valor|cifra|tarifa|promo\w*|oferta|monto|\$\s*\d|"
    r"\d{3}\s*(?:mil|k)\b|\d{1,3}[.,]\d{3}|eso\b|esa\s+info\w*|ese\s+dato)"
)
_FUENTE = (
    r"(?:d[oó]nde|en\s+qu[eé]\s+(?:publicaci[oó]n|anuncio|p[aá]gina|red|post|"
    r"flyer|imagen|sitio|parte))\s+(?:\w+\s+){0,3}?"
    r"(?:sacaste|sac[oó]|viste|vio|vieron|encontraste|encontr[oó]|le[ií]ste|"
    r"ley[oó]|sali[oó]|obtuviste|conseguiste|apareci[oó]|aparece|sale|viene|vino)"
    r"|qui[eé]n\s+te\s+(?:dio|pas[oó]|dijo|cotiz[oó])"
)
PREGUNTA_ORIGEN_PRECIO = re.compile(
    # «¿De dónde sacaste esa cifra?» / «¿Ese precio dónde lo viste?»
    rf"{_PRECIO}[^.?!¿\n]{{0,80}}(?:{_FUENTE})"
    rf"|(?:{_FUENTE})(?=[^.?!\n]{{0,80}}{_PRECIO})"
    # «¿Dónde lo viste?», «¿De dónde lo sacaste?»: el pronombre ya apunta al
    # precio del que se está hablando.
    r"|d[oó]nde\s+(?:lo|la|los|las)\s+(?:viste|sacaste|le[ií]ste|encontraste|"
    r"obtuviste|conseguiste)"
    r"|de\s+d[oó]nde\s+(?:sacaste|sac[oó]|sali[oó])"
    # «¿Me mandas el pantallazo?»
    r"|captura|pantallazo|screenshot",
    re.IGNORECASE,
)

#: Lo que puede cerrar un mensaje después de la pregunta sin que deje de ser
#: «termina en pregunta»: emojis, espacios, la negrilla de WhatsApp.
# Tope {1,40}: sin él, `+$` sobre una serie larga de espacios es cuadrático.
_COLA_DECORATIVA_RE = re.compile(r"[^\w?¿.!…)\]»\"']{1,40}$")
#: Entre dos preguntas seguidas sólo puede haber esto para considerarlas una
#: tanda: espacios, emojis o un «y» suelto.
_ENTRE_PREGUNTAS_RE = re.compile(r"^[^\w]*(?:y\s*)?$", re.IGNORECASE)


def _sin_cola(texto: str) -> str:
    return _COLA_DECORATIVA_RE.sub("", (texto or "").rstrip())


def termina_en_pregunta(texto: str) -> bool:
    """¿El mensaje cierra con una pregunta (ignorando emojis y adornos)?"""
    return _sin_cola(texto).endswith("?")


#: Pedir respuesta sin signo de pregunta: «Y me dices si prefieres múltiple o
#: doble 🏨» (conversación 543, el caso que originó #10).
_PIDE_RESPUESTA_RE = re.compile(
    r"\bme\s+(?:dices|cuentas|confirmas|avisas|regalas|compartes|escribes|"
    r"indicas)\b|\b(?:dime|cu[eé]ntame|conf[ií]rmame|av[ií]same|ind[ií]came)\b",
    re.IGNORECASE,
)


def pide_respuesta(texto: str) -> bool:
    """¿El mensaje le deja la pelota a la persona?

    Sí si termina en pregunta, si su último renglón trae una pregunta («¿Cuál
    te funciona mejor? Y me dices si prefieres doble 🏨») o si cierra pidiendo
    algo sin signo («me cuentas qué mes»). Es el disparador del corte: después
    de un mensaje así, el bot no puede seguir hablando solo.
    """
    if termina_en_pregunta(texto):
        return True
    lineas = [l for l in (texto or "").split("\n") if l.strip()]
    if not lineas:
        return False
    ultima = lineas[-1]
    if "?" in ultima:
        return True
    frases = [f for f in re.split(r"(?<=[.!?…])\s+", ultima.strip()) if f.strip()]
    return bool(frases) and bool(_PIDE_RESPUESTA_RE.search(frases[-1]))


def _inicio_de_pregunta(texto: str, cierre: int) -> int:
    """Dónde arranca la pregunta que cierra en `cierre` (índice del `?`)."""
    abre = texto.rfind("¿", 0, cierre)
    # Un `?` anterior entre medio significa que ese `¿` era de otra pregunta.
    previo = texto.rfind("?", 0, cierre)
    if abre != -1 and abre > previo:
        return abre
    # Sin `¿`: desde el último fin de frase o salto de línea.
    corte = max(texto.rfind(c, 0, cierre) for c in ".!?\n…")
    return corte + 1


def una_sola_pregunta_al_final(texto: str) -> str:
    """Si el mensaje termina en una tanda de preguntas seguidas, deja la primera.

    «Perfecto 🌴 ¿Para qué mes? ¿Y cuántas personas viajan? 😊» →
    «Perfecto 🌴 ¿Para qué mes? 😊». Sólo mira la **tanda final**: una pregunta
    retórica en mitad del mensaje («¿Sabías que incluye tours? Te cuento…») no
    se toca, porque detrás viene texto y no otra pregunta.
    """
    if not termina_en_pregunta(texto):
        return texto
    cuerpo = _sin_cola(texto)
    cola = texto.rstrip()[len(cuerpo):]
    preguntas = []                      # (inicio, fin) desde el final
    fin = len(cuerpo)
    while fin > 0 and cuerpo[:fin].rstrip().endswith("?"):
        cierre = len(cuerpo[:fin].rstrip()) - 1
        inicio = _inicio_de_pregunta(cuerpo, cierre)
        preguntas.append((inicio, cierre + 1))
        antes = cuerpo[:inicio]
        # ¿Lo que queda antes termina en otra pregunta pegada a esta?
        sin_adorno = _COLA_DECORATIVA_RE.sub("", antes.rstrip())
        separador = antes[len(sin_adorno):]
        if not sin_adorno.endswith("?") or not _ENTRE_PREGUNTAS_RE.match(separador):
            break
        fin = len(sin_adorno)
    if len(preguntas) < 2:
        return texto
    primera = preguntas[-1]
    return (cuerpo[:primera[1]] + cola).rstrip()


def cortar_tras_pregunta(actions: List[Dict[str, Any]]) -> bool:
    """El turno se cierra en el primer mensaje que pide respuesta
    (`pide_respuesta`: termina en pregunta, o su último renglón pregunta o pide
    algo).

    - Los `say` posteriores se descartan (el bot no se responde solo).
    - Los adjuntos posteriores (`say_media`, `say_catalog`) se mueven justo
      antes de la pregunta: el flyer se manda igual, pero lo último que ve la
      persona es lo que tiene que contestar.
    - Lo que no es mensaje (`handoff`, `end`, `perfil`, `pause`) conserva su
      orden, al final.
    - La pregunta misma se deja con una sola pregunta en su tanda final.

    Modifica `actions` en sitio. Devuelve si cambió algo.
    """
    idx = next(
        (
            i for i, a in enumerate(actions)
            if a.get("type") == "say"
            and pide_respuesta((a.get("payload") or {}).get("text") or "")
        ),
        None,
    )
    if idx is None:
        return False
    pregunta = actions[idx]
    payload = pregunta.get("payload") or {}
    texto = payload.get("text") or ""
    nuevo = una_sola_pregunta_al_final(texto)
    cambio = nuevo != texto
    if cambio:
        payload["text"] = nuevo

    posteriores = actions[idx + 1:]
    adjuntos = [a for a in posteriores if a.get("type") in _ADJUNTOS]
    textos = [a for a in posteriores if a.get("type") == "say"]
    resto = [
        a for a in posteriores
        if a.get("type") not in _ADJUNTOS and a.get("type") != "say"
    ]
    if not adjuntos and not textos:
        return cambio
    actions[:] = actions[:idx] + adjuntos + [pregunta] + resto
    return True


def poner_flyer(
    actions: List[Dict[str, Any]], item: Dict[str, Any]
) -> Optional[str]:
    """Agrega el flyer del mes al primer mensaje. Devuelve cómo lo puso.

    - `"pie"`: el turno es un solo texto de ≤1024 caracteres y sin otros
      adjuntos → el texto viaja como pie de la imagen (un solo mensaje en
      WhatsApp, que es lo que se ve como vitrina).
    - `"antes"`: en cualquier otro caso, la imagen va justo antes del mensaje
      que termina en pregunta (o del último texto, si no hay pregunta).
    - `None`: no había URL, o el flyer ya iba en el turno.
    """
    url = str((item or {}).get("url") or "").strip()
    if not url:
        return None
    if any(
        a.get("type") == "say_media"
        and (a.get("payload") or {}).get("url") == url
        for a in actions
    ):
        return None                     # el modelo ya lo mandó

    media_type = item.get("media_type", "image")
    pie_propio = str(item.get("caption") or "")
    says = [i for i, a in enumerate(actions) if a.get("type") == "say"]
    hay_adjuntos = any(a.get("type") in _ADJUNTOS for a in actions)
    if len(says) == 1 and not hay_adjuntos and not pie_propio.strip():
        texto = (actions[says[0]].get("payload") or {}).get("text") or ""
        if texto.strip() and len(texto) <= MAX_PIE_DE_FOTO:
            actions[says[0]] = {
                "type": "say_media",
                "payload": {"caption": texto, "media_type": media_type, "url": url},
            }
            return "pie"

    flyer = {
        "type": "say_media",
        "payload": {"caption": pie_propio, "media_type": media_type, "url": url},
    }
    destino = next(
        (
            i for i in says
            if pide_respuesta((actions[i].get("payload") or {}).get("text") or "")
        ),
        says[-1] if says else None,
    )
    if destino is None:
        # Sin texto: antes del cierre del turno (handoff/end) o al final.
        destino = next(
            (i for i, a in enumerate(actions) if a.get("type") in ("handoff", "end")),
            len(actions),
        )
    actions.insert(destino, flyer)
    return "antes"


# ---------------------------------------------------------------------------
# Lo que el modelo arrastra de las correcciones y del historial (QA 2026-10-07)
# ---------------------------------------------------------------------------

#: La disculpa al sistema que el modelo escribe en la ronda que sigue a una
#: corrección: «Tienes razón, disculpa. Vuelvo a responder bien:». El cliente
#: nunca vio la corrección, así que la disculpa le llega sin contexto (56 % de
#: los turnos corregidos en la corrida contra Bedrock).
_DISCULPA_INICIAL_RE = re.compile(
    r"^\s*(?:tienes\s+(?:toda\s+la\s+)?raz[oó]n|disculpa|disculpas|perd[oó]n|"
    r"me\s+disculpo|me\s+equivoqu\w*|vuelvo\s+a\s+(?:responder|intentar|"
    r"escribir)\w*|voy\s+a\s+responder\s+(?:bien|correctamente)|"
    r"reescrito\s+correctamente|corrijo)"
    # Hasta su punto (o el fin del renglón): «Disculpa la demora 🙏 Te
    # cuento…» no termina en signo y no es la disculpa al sistema.
    r"[^.:!\n]{0,80}(?:[.:!]+[ \t]*|[ \t]*(?=\n))\n*",
    re.IGNORECASE,
)


def sin_disculpa_inicial(texto: str) -> str:
    """El mensaje sin las frases de disculpa con que arranca (pueden ser
    varias seguidas: «Tienes razón, me disculpo. Vuelvo a intentar:»)."""
    nuevo = texto or ""
    for _ in range(4):
        recortado = _DISCULPA_INICIAL_RE.sub("", nuevo, count=1)
        if recortado == nuevo:
            break
        nuevo = recortado
    nuevo = nuevo.strip()
    if nuevo != (texto or "").strip() and nuevo[:1].islower():
        nuevo = nuevo[:1].upper() + nuevo[1:]      # «Corrijo: son 2…» → «Son 2…»
    return nuevo


#: Las marcas del historial aplanado (`[enviaste: tours]`, `[guardaste que…]`)
#: que el modelo imita y escribe como texto. Una línea entera, o pegadas al
#: final de una.
_MARCA_RE = re.compile(
    r"\[\s*(?:enviaste|guardaste|pedido|anotado|demo\s+registrada)\b[^\]\n]*\]",
    re.IGNORECASE,
)
_ENVIASTE_RE = re.compile(r"\[\s*enviaste\s*:\s*([^\]\n]*)\]", re.IGNORECASE)


def partir_por_marcas(texto: str) -> List[tuple]:
    """El texto partido en `("texto", str)` y `("media", clave)`, en orden.

    Cada `[enviaste: a, b]` se vuelve un `("media", "a")`, `("media", "b")`
    en su lugar (quien llama decide si la clave existe); las demás marcas se
    borran. Los trozos de texto salen sin renglones vacíos de sobra.
    """
    salida: List[tuple] = []
    pos = 0
    for m in _MARCA_RE.finditer(texto or ""):
        antes = texto[pos:m.start()]
        if antes.strip():
            if salida and salida[-1][0] == "texto":
                # La marca iba en mitad del renglón: el texto sigue siendo uno.
                salida[-1] = ("texto", salida[-1][1].rstrip() + " " + antes.lstrip())
            else:
                salida.append(("texto", antes))
        enviada = _ENVIASTE_RE.match(m.group(0))
        if enviada:
            for clave in enviada.group(1).split(","):
                clave = clave.strip(" `'\"")
                if clave:
                    salida.append(("media", clave))
        pos = m.end()
    resto = (texto or "")[pos:]
    if resto.strip():
        if salida and salida[-1][0] == "texto":
            salida[-1] = ("texto", salida[-1][1].rstrip() + " " + resto.lstrip())
        else:
            salida.append(("texto", resto))
    return [
        (clase, re.sub(r"\n{3,}", "\n\n", valor).strip()) if clase == "texto"
        else (clase, valor)
        for clase, valor in salida
    ]


# ---------------------------------------------------------------------------
# Opciones numeradas (bot 3: `respuesta_por_numero`, `opciones_cerradas`)
# ---------------------------------------------------------------------------

#: «1️⃣ Amor de Dios» en cualquier parte del renglón (las opciones del bot 3
#: van a veces en un solo renglón: «1️⃣ Sí 2️⃣ No»).
_OPCION_KEYCAP_RE = re.compile(r"([0-9])️?⃣")
#: «1. Amor de Dios», «2) Piedra Mar», «3 - Bohíos»: sólo al inicio del renglón,
#: para no leer como opción un «$459.000» o un «16 al 19».
_OPCION_LINEA_RE = re.compile(r"^\s*[*_]*([1-9])[*_]*\s*(?:[.)]|\s-|-\s)\s*(.+)$")


def _limpia_opcion(texto: str) -> str:
    texto = re.sub(r"[*_~]", "", texto)
    return " ".join(texto.split()).strip(" -–—:·|")


def opciones_numeradas(texto: str) -> Dict[int, str]:
    """`{n: etiqueta}` de las opciones del mensaje. Si el mensaje trae dos
    menús, gana el último (es el que la persona tiene a la vista)."""
    opciones: Dict[int, str] = {}
    for linea in (texto or "").split("\n"):
        marcas = list(_OPCION_KEYCAP_RE.finditer(linea))
        if marcas:
            for i, m in enumerate(marcas):
                fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(linea)
                etiqueta = _limpia_opcion(linea[m.end():fin])
                if etiqueta:
                    opciones[int(m.group(1))] = etiqueta
            continue
        m = _OPCION_LINEA_RE.match(linea)
        if m:
            etiqueta = _limpia_opcion(m.group(2))
            if etiqueta:
                opciones[int(m.group(1))] = etiqueta
    return opciones


_SI_NO_RE = re.compile(r"\bs[ií]\b[^?\n]{0,12}\bno\b", re.IGNORECASE)
#: Una pregunta abierta: la que lleva un interrogativo con tilde. «¿Te aparto
#: el cupo?» es de sí o no; «¿Para qué mes?» no.
_INTERROGATIVO_RE = re.compile(
    r"\b(?:qué|cuál|cuáles|cuándo|cuánto|cuánta|cuántos|cuántas|cómo|dónde|"
    r"quién|quiénes|adónde)\b",
    re.IGNORECASE,
)


def cierra_con_opciones(texto: str) -> bool:
    """¿El mensaje cierra con opciones numeradas (dos o más) o con una
    pregunta de sí o no?"""
    if len(opciones_numeradas(texto)) >= 2:
        return True
    cuerpo = _sin_cola(texto or "")
    if not cuerpo.endswith("?"):
        return False
    pregunta = cuerpo[_inicio_de_pregunta(cuerpo, len(cuerpo) - 1):]
    if _SI_NO_RE.search(pregunta):
        return True
    return not _INTERROGATIVO_RE.search(pregunta)


# ---------------------------------------------------------------------------
# Bot 3 — QA contra Bedrock (2026-10-10)
# ---------------------------------------------------------------------------

#: A3: el bot promete que «un compañero te lo confirma» (o te lo responde, o te
#: lo averigua) — una promesa que sólo se cumple si de verdad lo pasa a un
#: asesor. Los verbos van acotados a **darle un dato** (auditoría D1): «el
#: equipo te escribe para recordártelo» o «nuestro equipo de guías te cuenta
#: todo en el bus» no prometen nada.
_QUIEN = r"(?:compa[nñ]er[oa]s?|asesor[ae]?s?|equipo|colega)"
_DATO_VERBO = r"(?:confirm|averigu|respond|contest|resuelv|verific)\w*"
_PROMESA_RE = re.compile(
    # «te lo confirma un compañero», «eso te lo responde el equipo»
    rf"\b(?:te\s+)?(?:lo|la|los|las|eso)\s+(?:te\s+)?{_DATO_VERBO}\s+"
    rf"(?:un|una|el|la|mi|nuestro|nuestra)\s+{_QUIEN}"
    # «eso lo confirmo con un compañero»
    rf"|\b(?:lo|la|eso)\s+(?:lo\s+)?(?:confirmo|consulto|averiguo|verifico|pregunto|reviso)"
    rf"\s+con\s+(?:un|una|el|la|mi|mis)?\s*{_QUIEN}"
    # «un compañero te lo confirma»
    rf"|{_QUIEN}\b[^.!?\n]{{0,30}}?\b(?:te\s+)?(?:lo|la|los|las)\s+{_DATO_VERBO}"
    # «el equipo te confirma si…», «un asesor te responde eso»
    rf"|{_QUIEN}\b[^.!?\n]{{0,30}}?\b(?:te\s+)?{_DATO_VERBO}\s+"
    r"(?:si|qu[eé]|cu[aá]l|cu[aá]nto|cu[aá]ntos|cu[aá]ntas|c[oó]mo|d[oó]nde|cu[aá]ndo|"
    r"eso|ese\s+dato|esa\s+info\w*|el\s+dato|tu\s+pregunta|el\s+valor|ese\s+valor)\b"
    # «un compañero te ayuda con eso / con tu pregunta»
    rf"|{_QUIEN}\b[^.!?\n]{{0,40}}?\b(?:te\s+)?ayud\w*\s+con\s+"
    r"(?:eso|tu\s+pregunta|esa\s+duda|tu\s+duda|ese\s+tema)",
    re.IGNORECASE,
)
#: Lo que NO es una promesa de dato aunque nombre a un compañero: confirmar la
#: reserva al verificar el pago es el paso normal de /pago y del comprobante.
_NO_ES_PROMESA_RE = re.compile(
    r"confirm\w*\s+(?:la\s+|tu\s+)?reserva|verific\w*\s+(?:el\s+|tu\s+)?pago",
    re.IGNORECASE,
)
_HABLA_DE_RESERVA_RE = re.compile(r"reserva|pago|anticipo|comprobante|cupo", re.IGNORECASE)


def _frase_que_contiene(texto: str, inicio: int, fin: int) -> str:
    desde = max(texto.rfind(c, 0, inicio) for c in ".!?\n") + 1
    hasta = min((i for i in (texto.find(c, fin) for c in ".!?\n") if i != -1),
                default=len(texto))
    return texto[desde:hasta]


def promete_respuesta_de_otro(texto: str, *, etapa: Optional[str] = None) -> bool:
    """¿El texto promete que otra persona del equipo le va a dar un dato?

    No cuenta (auditoría D1) la frase que habla de confirmar la reserva o de
    verificar el pago, ni —en las etapas `reserva` y `pago`— la que habla de
    la reserva, el pago, el anticipo o el cupo: ahí «un compañero te confirma»
    es el paso normal, y corregirlo empujaba al bot a traspasar antes del pago.
    """
    texto = texto or ""
    for m in _PROMESA_RE.finditer(texto):
        frase = _frase_que_contiene(texto, m.start(), m.end())
        if _NO_ES_PROMESA_RE.search(frase):
            continue
        if etapa in ("reserva", "pago") and _HABLA_DE_RESERVA_RE.search(frase):
            continue
        return True
    return False


#: M1: frases de narración o de meta-texto que no son para el cliente.
_NARRACION_RE = re.compile(
    r"^\W*(?:"
    r"(?:d[eé]jame|perm[ií]teme|voy\s+a|vamos\s+a|necesito|tengo\s+que|primero\s+voy\s+a)"
    r"\s+(?:\w+\s+)?(?:consultar|revisar|verificar|mirar|buscar|confirmar|chequear)"
    r"|(?:consulto|reviso|verifico|busco)\b[^.!?\n]*"
    r"|(?:ya\s+)?(?:te\s+)?(?:consulto|reviso)\b"
    r"|un\s+(?:momento|segundo|momentico|ratico)|dame\s+un\s+(?:momento|segundo)"
    r"|ahora\s+s[ií]\b|perfect\b|ok(?:ay)?\s*[,!.]*$"
    r"|acabo\s+de\s+(?:consultar|revisar|verificar)|ya\s+consult[eé]|ya\s+revis[eé]"
    r"|(?:respondo|contesto)\s+correctamente"
    r"|tienes\s+(?:toda\s+la\s+)?raz[oó]n|me\s+disculpo|disculpa\s*[.!]?$|perd[oó]n\s*[.!]?$"
    # R1: la conversación con el sistema que se cuela tras una corrección.
    r"|no\s+deber[ií]a\s+haber|voy\s+a\s+hacerlo\s+(?:ahora|bien|de\s+nuevo)"
    r"|d[eé]jame\s+corregir|(?:lo\s+)?corrijo\b|reescrib\w*"
    r")",
    re.IGNORECASE,
)


def _frases_de(linea: str) -> List[str]:
    frases, actual = [], ""
    for i, ch in enumerate(linea):
        actual += ch
        if ch in ".!?…" and (i + 1 == len(linea) or linea[i + 1] not in ".!?…"):
            frases.append(actual)
            actual = ""
    if actual:
        frases.append(actual)
    return frases


def es_narracion(frase: str) -> bool:
    return bool(_NARRACION_RE.search((frase or "").strip()))


#: R1: la muletilla con que arranca un renglón reescrito («Reescribiendo:»,
#: «Como te decía,», «Déjame corregir:»). Se va el prefijo, no lo que sigue.
_PREFIJO_META_RE = re.compile(
    r"^(\s*)(?:reescribiendo|reescribo|lo\s+reescribo|corrijo|corrigiendo|"
    r"como\s+te\s+(?:dec[ií]a|comentaba)|d[eé]jame\s+corregir(?:lo)?|"
    r"aqu[ií]\s+va\s+(?:corregido|bien)|versi[oó]n\s+corregida)\s*[:,.\-–—]+\s*",
    re.IGNORECASE | re.MULTILINE,
)


#: Anunciar que va a consultar, en cualquier parte de la frase («Antes de
#: apartar tu cupo, déjame consultar los precios…»). Sólo se usa en rondas que
#: terminaron consultando: ahí la consulta ya ocurrió y la frase sobra.
_ANUNCIA_CONSULTA_RE = re.compile(
    r"d[eé]jame\s+(?:\w+\s+)?(?:consultar|revisar|verificar|mirar|confirmar)"
    r"|(?:voy|vamos)\s+a\s+(?:consultar|revisar|verificar|mirar)"
    r"|perm[ií]teme\s+(?:consultar|revisar|verificar)",
    re.IGNORECASE,
)


def sin_narracion(texto: str, *, solo_bordes: bool, ronda_consulta: bool = False) -> str:
    """El texto sin las frases de narración («Déjame consultar los precios…»,
    «Ahora sí.», «Un momento»).

    `solo_bordes`: sólo las del inicio y del final del mensaje (rondas que
    terminaron consultando: lo del medio suele ser contenido). Si no, todas
    (la ronda que sigue a una corrección).
    """
    if not solo_bordes:
        renglones = []
        for renglon in (texto or "").split("\n"):
            nuevo = _PREFIJO_META_RE.sub(r"\1", renglon)
            if nuevo != renglon:
                sangria = len(nuevo) - len(nuevo.lstrip())
                nuevo = nuevo[:sangria] + nuevo[sangria:sangria + 1].upper() + nuevo[sangria + 1:]
            renglones.append(nuevo)
        texto = "\n".join(renglones).strip()
    piezas = []                      # (renglón, frase)
    lineas = (texto or "").split("\n")
    for n, linea in enumerate(lineas):
        for frase in _frases_de(linea) or [""]:
            piezas.append((n, frase))
    utiles = [i for i, (_, f) in enumerate(piezas) if f.strip()]
    quitar = set()
    if solo_bordes:
        # Bordes de cada PÁRRAFO, no sólo de la burbuja: una narración que
        # cierra el primer párrafo también sobra.
        parrafos: List[List[int]] = [[]]
        for i, (n, frase) in enumerate(piezas):
            if not lineas[n].strip():
                if parrafos[-1]:
                    parrafos.append([])
                continue
            if frase.strip():
                parrafos[-1].append(i)
        for grupo in parrafos:
            for i in grupo:
                if not es_narracion(piezas[i][1]):
                    break
                quitar.add(i)
            for i in reversed(grupo):
                if i in quitar or not es_narracion(piezas[i][1]):
                    break
                quitar.add(i)
    else:
        quitar = {i for i in utiles if es_narracion(piezas[i][1])}
    if ronda_consulta:
        quitar |= {i for i in utiles if _ANUNCIA_CONSULTA_RE.search(piezas[i][1])}
    if not quitar:
        return texto
    salida = [""] * len(lineas)
    for i, (n, frase) in enumerate(piezas):
        if i not in quitar:
            salida[n] += frase
    limpio = "\n".join(l.strip() if not l.strip() else l.rstrip() for l in salida)
    return re.sub(r"\n{3,}", "\n\n", limpio).strip()


def solo_opciones(texto: str) -> bool:
    """¿El mensaje es sólo una lista de opciones numeradas (sin pregunta)?"""
    lineas = [l for l in (texto or "").split("\n") if l.strip()]
    if not lineas or len(opciones_numeradas(texto)) < 2:
        return False
    return all(
        _OPCION_KEYCAP_RE.search(l) or _OPCION_LINEA_RE.match(l) for l in lineas
    )


#: Acciones que no se ven en el chat: no separan una burbuja de la siguiente.
_INVISIBLES = frozenset({"perfil"})


def unir_opciones(actions: List[Dict[str, Any]]) -> bool:
    """M4: una burbuja que sólo trae las opciones se pega a la anterior del
    mismo turno si esa termina en pregunta (o en 👇), aunque vengan de rondas
    distintas y haya en medio una acción que no se ve (`perfil`). Modifica en
    sitio."""
    cambio = False
    i = 1
    while i < len(actions):
        b = actions[i]
        tb = ((b.get("payload") or {}).get("text") or "") if b.get("type") == "say" else ""
        if not tb or not solo_opciones(tb):
            i += 1
            continue
        j = i - 1
        while j >= 0 and actions[j].get("type") in _INVISIBLES:
            j -= 1
        a = actions[j] if j >= 0 else {}
        ta = ((a.get("payload") or {}).get("text") or "") if a.get("type") == "say" else ""
        if ta and (pide_respuesta(ta) or ta.rstrip().endswith("👇")):
            a["payload"]["text"] = ta.rstrip() + "\n" + tb.strip()
            del actions[i]
            cambio = True
            continue
        i += 1
    return cambio


def _pregunta_normalizada(frase: str) -> str:
    sin_formato = re.sub(r"[*_~]", "", frase.lower())
    return " ".join(re.findall(r"[0-9a-záéíóúüñ]+", sin_formato))


def _preguntas(texto: str) -> List[str]:
    return [
        f for linea in (texto or "").split("\n") for f in _frases_de(linea)
        if "?" in f
    ]


def sin_pregunta_repetida(actions: List[Dict[str, Any]]) -> bool:
    """Si dos burbujas del turno traen la misma pregunta (sin contar negritas,
    emojis ni espacios), queda sólo la que trae las opciones: de la otra se va
    la pregunta, y si no le queda nada que decir, la burbuja entera."""
    says = [a for a in actions if a.get("type") == "say"]
    con_opciones = [a for a in says if len(opciones_numeradas((a.get("payload") or {}).get("text") or "")) >= 2]
    vistas = {
        _pregunta_normalizada(f)
        for a in con_opciones
        for f in _preguntas((a.get("payload") or {}).get("text") or "")
    }
    vistas.discard("")
    if not vistas:
        return False
    cambio = False
    for accion in says:
        if accion in con_opciones:
            continue
        texto = (accion.get("payload") or {}).get("text") or ""
        nuevo = texto
        for frase in _preguntas(texto):
            if _pregunta_normalizada(frase) in vistas:
                nuevo = nuevo.replace(frase, "", 1)
        if nuevo == texto:
            continue
        cambio = True
        resto = re.sub(r"\n{3,}", "\n\n", nuevo).strip()
        # Lo que queda («¡Perfecto!», un emoji) no justifica una burbuja.
        palabras = re.findall(r"[0-9a-záéíóúüñ]+", resto.lower())
        accion["payload"]["text"] = resto if len(palabras) >= 4 else ""
    if cambio:
        actions[:] = [
            a for a in actions
            if a.get("type") != "say" or ((a.get("payload") or {}).get("text") or "").strip()
        ]
    return cambio


def adjuntos_antes_de_la_pregunta(actions: List[Dict[str, Any]]) -> bool:
    """Los adjuntos que el modelo mandó después de la primera burbuja con
    pregunta u opciones suben a justo antes de ella, en su mismo orden. Los
    que ya iban antes no se tocan. Así lo último que ve la persona es lo que
    tiene que contestar (smoke final del bot 3: `medios_pago` salía después de
    las opciones, o entre la pregunta y las opciones)."""
    idx = next(
        (
            i for i, a in enumerate(actions)
            if a.get("type") == "say" and (
                pide_respuesta((a.get("payload") or {}).get("text") or "")
                or len(opciones_numeradas((a.get("payload") or {}).get("text") or "")) >= 2
                or ((a.get("payload") or {}).get("text") or "").rstrip().endswith("👇")
            )
        ),
        None,
    )
    if idx is None:
        return False
    despues = [a for a in actions[idx + 1:] if a.get("type") in _ADJUNTOS]
    if not despues:
        return False
    resto = [a for a in actions[idx + 1:] if a.get("type") not in _ADJUNTOS]
    actions[:] = actions[:idx] + despues + [actions[idx]] + resto
    return True
