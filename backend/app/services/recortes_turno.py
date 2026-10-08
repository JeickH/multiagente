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
    return nuevo.strip()


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
