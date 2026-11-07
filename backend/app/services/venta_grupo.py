"""Lo que los tres bots de Arranquemos Pues hacen igual al vender (Sprint 36).

Pedido del CEO del 7-nov-2026, tras leer las conversaciones de los bots 12, 21
y 22: «para todos los bots hay que mejorarle esos mismos puntos». Todo lo de
aquí lo usa `llm_engine` solo con bots que tienen `tarifario` en su
`llm_config` (los tres de Arranquemos y nadie más), y es **puro**: no toca la
base, no llama al modelo y las únicas cifras salen del resultado de la consulta
de precios y de `tarifario_covenas_extras.json`.

  1. **El total del grupo** (`bloque_total`). El bot cotizaba «$459.000 por
     persona» a quien había dicho «somos 2 con un niño de 3»: la cuenta la hacía
     la persona, y la hacía con la múltiple, que a 2 no se le vende. Ahora la
     herramienta de precios recibe `adultos` y `ninos` y devuelve el total ya
     calculado con la acomodación correcta, por salida.
  2. **Pedir la venta** (`con_la_venta_pedida`). Después del total el bot 1
     preguntaba «¿te sirve?» o nada. Si en el turno se dijo un total del grupo y
     no se ofreció apartar, se agrega «¿Te aparto los N cupos?» con el anticipo
     (o el pago total, si la salida sale muy pronto). Determinista y no otra
     regla del prompt: el modelo no se olvida, **elige** otra pregunta, y
     repetírselo empata con el baseline (gotcha del 27-ago).
  3. **«Sale de Medellín»** en el primer mensaje (`con_salida_de_medellin`) y
     ninguna salida inventada desde otra ciudad (`afirma_salida_otra_ciudad`).
  4. **Fuera «todo incluido» / «incluye todo»** (`sin_todo_incluido`): es falso
     (la alimentación arranca el sábado y hay opcionales) y el reclamo llega en
     el destino. Se reescribe la frase, no se descarta el turno: descartarlo
     costaría el flyer que el bot acababa de mandar.
  5. **Listo para reservar con nombre completo y cédula de quien paga**
     (`trae_datos_de_quien_paga`): la asesora pide después los de los demás.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import guardarrail_precio, senales, tarifario

# ---------------------------------------------------------------------------
# 1. El total del grupo
# ---------------------------------------------------------------------------

#: Las propiedades que se le agregan a la herramienta de precios de los bots
#: con `tarifario` (`consultar_tarifario` y `consultar_precios`). Opcionales:
#: sin ellas la herramienta responde exactamente lo de siempre.
PROPIEDADES_GRUPO: Dict[str, Dict[str, str]] = {
    "adultos": {
        "type": "string",
        "description": (
            "Cuántos adultos viajan, si ya lo sabes (ej. '2'). Con esto te "
            "devuelvo el TOTAL del grupo por salida, con la acomodación "
            "correcta y el anticipo: úsalo para dar el total, no solo el "
            "precio por persona."
        ),
    },
    "ninos": {
        "type": "string",
        "description": (
            "Edades de los niños que viajan, separadas por coma (ej. '3, 7'; "
            "un bebé de meses es '0'). Omítelo si no van niños. Si van niños "
            "y no sabes la edad, pregúntala antes de consultar el total."
        ),
    },
}

#: Personas por cotización: más que esto es un grupo y lo atiende un asesor
#: (el mismo tope del guardarraíl de precio).
_MAX_PERSONAS = 15
#: Salidas con total por hotel. Una consulta de un mes trae hasta ~6 filas por
#: hotel; más que esto ya no es una cotización sino un listado, y alarga el
#: resultado en cada ronda. Si pidió una fecha, solo va esa.
_MAX_FILAS_POR_HOTEL = 4
#: La múltiple es para 3 o más personas del mismo grupo o familia (regla de la
#: agencia, CEO 2026-10-21). Cuentan todos los que viajan, niños incluidos:
#: es la misma lectura del guardarraíl de precio («dos adultos en múltiple
#: solo con al menos un niño: la habitación queda con 3 o más personas»).
_MIN_MULTIPLE = 3
#: Una salida que arranca en menos de esto se paga completa al reservar (las
#: asesoras, CEO 2026-10-21). El mismo umbral de `llm_engine._notas_de_precios`.
_DIAS_PAGO_TOTAL = 5

_NUMERO_RE = re.compile(r"\d{1,2}")
_EDAD_RE = re.compile(r"(\d{1,2})\s*(mes(?:es)?|a[nñ]os?|a[nñ]itos?)?", re.IGNORECASE)
_PALABRAS_NUMERO = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
    "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
}


@dataclass(frozen=True)
class Grupo:
    adultos: int
    edades: Tuple[int, ...] = ()

    @property
    def personas(self) -> int:
        return self.adultos + len(self.edades)


@dataclass(frozen=True)
class Total:
    """El total de UNA salida para el grupo, como se le dice al cliente."""

    etiqueta: str
    hotel: str
    acomodacion: str          # "doble" | "múltiple"
    total: int
    a_pagar: int              # anticipo, o el total si es pago total
    pago_total: bool
    personas: int


def _entero(valor: Any) -> Optional[int]:
    """Lo que el modelo manda como cantidad: '2', 2, 'dos', '2 adultos'."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    texto = senales.normalizar(valor)
    if not texto:
        return None
    m = _NUMERO_RE.search(texto)
    if m:
        return int(m.group())
    for palabra in texto.split():
        if palabra in _PALABRAS_NUMERO:
            return _PALABRAS_NUMERO[palabra]
    return None


def _edades(valor: Any) -> Optional[Tuple[int, ...]]:
    """Las edades de los niños. `None` si dijo que van niños pero no cuántos
    años tienen: sin la edad no hay tramo y no se adivina."""
    if valor is None:
        return ()
    if isinstance(valor, (list, tuple)):
        valor = ", ".join(str(v) for v in valor)
    texto = str(valor).strip()
    if not texto or senales.normalizar(texto) in ("0 ninos", "ninguno", "no", "sin ninos"):
        return ()
    edades: List[int] = []
    for m in _EDAD_RE.finditer(texto):
        n = int(m.group(1))
        unidad = (m.group(2) or "").lower()
        if unidad.startswith("mes"):
            n = 0
        if n > 17:
            continue
        edades.append(n)
    return tuple(edades) if edades else None


def composicion(tool_input: Dict[str, Any]) -> Tuple[Optional[Grupo], str]:
    """El grupo que el modelo le pasó a la herramienta de precios.

    Devuelve ``(grupo, aviso)``: sin `adultos` no hay grupo y no hay aviso (la
    consulta es la de siempre). Con un dato que no se puede usar, el aviso le
    dice al modelo qué preguntar, en vez de calcular un total que no es.
    """
    tool_input = tool_input or {}
    crudo_adultos = tool_input.get("adultos")
    crudo_ninos = tool_input.get("ninos")
    if crudo_adultos in (None, "") and crudo_ninos in (None, ""):
        return None, ""
    adultos = _entero(crudo_adultos)
    if not adultos or adultos < 1:
        return None, (
            "TOTAL DEL GRUPO: no me dijiste cuántos adultos viajan. Pregúntalo "
            "antes de dar un total."
        )
    edades = _edades(crudo_ninos)
    if edades is None:
        return None, (
            "TOTAL DEL GRUPO: van niños pero no sé sus edades, y lo que paga "
            "cada niño depende de la edad. Pregúntala antes de dar el total."
        )
    grupo = Grupo(adultos=adultos, edades=edades)
    if grupo.personas > _MAX_PERSONAS:
        return None, (
            f"TOTAL DEL GRUPO: {grupo.personas} personas ya es un grupo grande: "
            "lo cotiza un compañero del equipo (pásalo con `escalar_a_asesor`)."
        )
    return grupo, ""


def _tramo_nino(edad: int, extras: Dict[str, Any]) -> Optional[Tuple[str, int]]:
    """(concepto, valor) del niño, o None si paga el plan como un adulto."""
    for tramo in extras.get("ninos") or []:
        try:
            if int(tramo["edad_min"]) <= edad <= int(tramo["edad_max"]):
                return str(tramo.get("concepto") or ""), int(tramo["valor"])
        except (KeyError, TypeError, ValueError):
            continue
    return None


def _anticipo_pct(extras: Dict[str, Any]) -> Optional[int]:
    try:
        pct = int(extras.get("anticipo_pct"))
    except (TypeError, ValueError):
        return None
    return pct if 0 < pct < 100 else None


def _sale_muy_pronto(etiqueta: str, hoy: date) -> bool:
    """¿La salida de esta fila arranca en menos de `_DIAS_PAGO_TOTAL` días?

    Se busca la fila del tarifario por su etiqueta («OCTUBRE 16 AL 19»), igual
    que `llm_engine._notas_de_precios`: es la etiqueta lo que comparten el JSON
    y las filas importadas a la base.
    """
    plano = (etiqueta or "").upper()
    for plan in (tarifario._datos() or {}).get("planes", []):
        fecha = str(plan.get("fecha") or "").upper()
        if not fecha or fecha not in plano:
            continue
        try:
            inicio = date.fromisoformat(plan["inicio"])
        except (KeyError, ValueError):
            continue
        if 0 <= (inicio - hoy).days < _DIAS_PAGO_TOTAL:
            return True
    return False


def _pesos(valor: int) -> str:
    return f"${int(valor):,}".replace(",", ".")


def _filas_a_totalizar(resultado: str) -> List[guardarrail_precio.Fila]:
    """Las filas del resultado; si la persona pidió una fecha, solo esa."""
    filas = guardarrail_precio.filas_de_resultados([resultado or ""])
    marcadas = [
        linea for linea in (resultado or "").splitlines() if "<--" in linea
    ]
    if marcadas:
        elegidas = [f for f in filas if any(f.etiqueta in linea for linea in marcadas)]
        if elegidas:
            filas = elegidas
    vistas = set()
    por_hotel: Dict[str, int] = {}
    unicas = []
    for f in filas:
        clave = (f.hotel, f.etiqueta)
        if clave in vistas or por_hotel.get(f.hotel, 0) >= _MAX_FILAS_POR_HOTEL:
            continue
        vistas.add(clave)
        por_hotel[f.hotel] = por_hotel.get(f.hotel, 0) + 1
        unicas.append(f)
    return unicas


def _cuenta(fila, grupo: Grupo, acomodacion: str, extras: Dict[str, Any]) -> Tuple[int, str]:
    """(total, cuenta en una línea) del grupo en esa acomodación."""
    precio = fila.doble if acomodacion == "doble" else fila.multiple
    pagan_plan = grupo.adultos
    ninos: List[Tuple[int, str, int]] = []
    for edad in grupo.edades:
        tramo = _tramo_nino(edad, extras)
        if tramo is None:
            pagan_plan += 1
        else:
            ninos.append((edad, tramo[0], tramo[1]))
    total = pagan_plan * precio + sum(v for _, _, v in ninos)
    partes = [f"{pagan_plan} × {_pesos(precio)} ({acomodacion})"]
    for edad, _concepto, valor in ninos:
        anios = "año" if edad == 1 else "años"
        quien = f"niño de {edad} {anios}" if edad else "bebé"
        partes.append(f"{quien} {_pesos(valor)}")
    return total, " + ".join(partes) + f" = {_pesos(total)} total"


def bloque_total(
    resultado: str,
    tool_input: Dict[str, Any],
    *,
    hoy: Optional[date] = None,
    extras: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Total]]:
    """El TOTAL DEL GRUPO que se pega al resultado de la consulta de precios.

    Devuelve ``(texto, totales)``. Texto vacío si el modelo no pasó el grupo o
    el resultado no trae filas con precio (un error, un mes sin salidas).
    `totales` es lo que el motor usa después para pedir la venta con la cifra
    exacta, sin volver a calcular nada.
    """
    grupo, aviso = composicion(tool_input)
    if grupo is None:
        return aviso, []
    filas = _filas_a_totalizar(resultado)
    if not filas:
        return "", []
    hoy = hoy or tarifario.hoy_colombia()
    extras = extras if extras is not None else tarifario.extras()
    pct = _anticipo_pct(extras)

    quienes = f"{grupo.adultos} adulto" + ("s" if grupo.adultos != 1 else "")
    if grupo.edades:
        quienes += " y " + ", ".join(
            "bebé" if e == 0 else f"niño de {e}" for e in grupo.edades
        )
    multiple = grupo.personas >= _MIN_MULTIPLE
    if multiple:
        regla = (
            f"Son {grupo.personas}, del mismo grupo: va en MÚLTIPLE (la más "
            "económica); la doble va al lado por si la prefieren."
        )
    else:
        regla = (
            f"Son {grupo.personas}: va en DOBLE (a 1 o 2 personas nunca se les "
            "cotiza múltiple)."
        )
    lineas = [
        f"TOTAL DEL GRUPO (calculado por el sistema para {quienes}). {regla} "
        "Dale este TOTAL, no solo el precio por persona, y copia la cifra tal "
        "cual:",
    ]
    totales: List[Total] = []
    for fila in filas:
        nombre_hotel = guardarrail_precio._NOMBRE_HOTEL.get(fila.hotel, fila.hotel)
        pronto = _sale_muy_pronto(fila.etiqueta, hoy)
        opciones = ["múltiple", "doble"] if multiple else ["doble"]
        piezas = []
        for acom in opciones:
            total, cuenta = _cuenta(fila, grupo, "doble" if acom == "doble" else "múltiple", extras)
            if pronto or pct is None:
                a_pagar = total
            else:
                a_pagar = int(round(total * pct / 100))
            if pronto:
                pago = f"PAGO TOTAL al reservar: {_pesos(total)} (sale muy pronto)"
            elif pct is not None:
                pago = f"anticipo del {pct}%: {_pesos(a_pagar)}"
            else:
                pago = "anticipo para apartar"
            piezas.append(f"{cuenta} · {pago}")
            totales.append(Total(
                etiqueta=fila.etiqueta, hotel=nombre_hotel, acomodacion=acom,
                total=total, a_pagar=a_pagar, pago_total=pronto,
                personas=grupo.personas,
            ))
        lineas.append(f"  · {nombre_hotel} — {fila.etiqueta}: " + " | ".join(piezas))
    lineas.append(
        "Después del total, en ese mismo mensaje, pide la venta con el valor "
        "para apartar: «" + frase_pedir_venta(totales[0], con_valor=False) + "»."
    )
    return "\n".join(lineas), totales


# ---------------------------------------------------------------------------
# 2. Pedir la venta
# ---------------------------------------------------------------------------

#: Ya se ofreció apartar: «¿Te aparto el cupo?», «¿te los separo?», «¿quieres
#: reservar?», «1️⃣ Sí, quiero apartar». Se compara sin tildes.
_PIDE_LA_VENTA_RE = re.compile(
    r"\b(?:te\s+(?:lo|la|los|las)\s+)?(?:apart\w*|separ\w*|reserv\w*)\b"
    r"|\bte\s+(?:los|las|lo|la)\s+(?:aparto|separo)\b",
    re.IGNORECASE,
)
#: La pregunta del turno es por la acomodación: ahí todavía no se pide la venta
#: (el bot 3 muestra las dos y deja elegir).
_PREGUNTA_ACOMODACION_RE = re.compile(
    r"acomodaci[oó]n|m[uú]ltiple\s+o\s+(?:la\s+)?doble|doble\s+o\s+(?:la\s+)?m[uú]ltiple",
    re.IGNORECASE,
)
_KEYCAP_RE = re.compile(r"[0-9]️?⃣")
_OPCIONES_RESERVA = (
    "👇\n1️⃣ Sí, quiero reservar ✅\n2️⃣ Tengo una pregunta 🤔\n"
    "3️⃣ Lo voy a consultar 💬"
)


def frase_pedir_venta(total: Total, *, con_valor: bool = True) -> str:
    """«¿Te aparto los 2 cupos?», con el valor para apartar delante.

    La pregunta va de última (los bots 2 y 3 cortan el turno después de la
    pregunta) y el valor es el que ya calculó `bloque_total`.
    """
    pregunta = (
        "¿Te aparto tu cupo? 🙌" if total.personas <= 1
        else f"¿Te aparto los {total.personas} cupos? 🙌"
    )
    if not con_valor:
        return pregunta
    if total.pago_total:
        valor = (
            "Como la salida es muy pronto, se paga el *total de "
            f"{_pesos(total.a_pagar)}* para apartar."
        )
    elif total.a_pagar < total.total:
        valor = (
            f"Se aparta con un *anticipo de {_pesos(total.a_pagar)}* y el resto "
            "lo pagas antes del viaje."
        )
    else:
        valor = "Se aparta con un anticipo y el resto lo pagas antes del viaje."
    return f"{valor} {pregunta}"


def ya_pide_la_venta(texto: str) -> bool:
    return bool(_PIDE_LA_VENTA_RE.search(senales.normalizar(texto)))


def total_dicho(textos: Sequence[str], totales: Sequence[Total]) -> Optional[Total]:
    """El total del grupo que el bot le dijo al cliente en este turno, si dijo
    alguno (el último que aparece)."""
    if not totales:
        return None
    por_valor = {t.total: t for t in totales}
    dicho = None
    for texto in textos:
        for monto in guardarrail_precio.extraer_montos(texto or ""):
            if monto in por_valor:
                dicho = por_valor[monto]
    return dicho


def _inicio_ultima_pregunta(texto: str) -> Optional[int]:
    """Dónde empieza la pregunta con la que termina el texto, si termina en una."""
    cola = texto.rstrip()
    sin_emojis = re.sub(r"[\s\U0001F000-\U0001FAFF☀-➿️]+$", "", cola)
    if not sin_emojis.endswith("?"):
        return None
    abre = sin_emojis.rfind("¿")
    if abre == -1:
        return None
    return abre


def con_la_venta_pedida(
    actions: List[Dict[str, Any]],
    say_texts: List[str],
    totales: Sequence[Total],
    *,
    opciones_cerradas: bool = False,
) -> bool:
    """Si el turno dijo un total del grupo y no ofreció apartar, lo ofrece.

    La frase va en la **última burbuja de texto**, no en un mensaje aparte: si
    esa burbuja termina con otra pregunta («¿te sirve?»), se reemplaza por la
    de la venta, para no dejar dos preguntas seguidas. Con `opciones_cerradas`
    (bot 3) la pregunta lleva sus opciones; si la burbuja ya trae un menú, no
    se toca: el bot eligió otra cosa y reescribir un menú rompe su `1/2/3`.

    Devuelve si cambió algo.
    """
    dicho = total_dicho(say_texts, totales)
    if dicho is None:
        return False
    if any(ya_pide_la_venta(t) for t in say_texts):
        return False
    indice = next(
        (i for i in range(len(actions) - 1, -1, -1)
         if actions[i].get("type") == "say"
         and ((actions[i].get("payload") or {}).get("text") or "").strip()),
        None,
    )
    if indice is None:
        return False
    original = actions[indice]["payload"]["text"]
    if _PREGUNTA_ACOMODACION_RE.search(original):
        return False
    if _KEYCAP_RE.search(original):
        return False
    pide = frase_pedir_venta(dicho)
    if opciones_cerradas:
        pide = f"{pide} {_OPCIONES_RESERVA}"
    abre = _inicio_ultima_pregunta(original)
    if abre is not None:
        base = original[:abre].rstrip()
        sep = "\n\n" if "\n" in original[max(0, abre - 2):abre + 1] else " "
        nuevo = f"{base}{sep}{pide}" if base else pide
    else:
        nuevo = f"{original.rstrip()}\n\n{pide}"
    actions[indice]["payload"]["text"] = nuevo
    for i in range(len(say_texts) - 1, -1, -1):
        if say_texts[i] == original:
            say_texts[i] = nuevo
            break
    else:
        say_texts.append(pide)
    return True


# ---------------------------------------------------------------------------
# 3. Sale de Medellín
# ---------------------------------------------------------------------------

LINEA_MEDELLIN = "🚌 Sale desde *Medellín* (Estación Universidad)."

_MEDELLIN_RE = re.compile(r"medell[ií]n", re.IGNORECASE)

#: Ciudades desde donde la gente escribe y desde donde el bot podría inventar
#: una salida o una recogida. Sin Coveñas/Tolú (el destino) ni Medellín.
_CIUDADES = (
    "cali", "bogota", "pereira", "manizales", "armenia", "barranquilla",
    "cartagena", "bucaramanga", "monteria", "sincelejo", "cucuta", "ibague",
    "neiva", "pasto", "villavicencio", "santa marta", "tunja", "popayan",
    "valledupar", "rionegro", "envigado", "bello", "itagui", "caucasia",
    "apartado", "turbo", "quibdo", "palmira", "tulua", "buga", "yopal",
)
_CIUDAD_RE = "(?:" + "|".join(sorted(_CIUDADES, key=len, reverse=True)) + ")"
_SALIDA_OTRA_CIUDAD_RE = re.compile(
    r"\b(?:salimos|sale|salen|saldria|saldrian|salida|salidas|recogemos|recoge|"
    r"recogen|recogida|recogidas|recogerte|recogerlos|pasamos\s+por|pasa\s+por|"
    r"embarque|abordaje)\b"
    r"[^.!?\n]{0,30}?\b(?:desde|de|en|por)\s+" + _CIUDAD_RE + r"\b"
    r"|\b(?:desde|en)\s+" + _CIUDAD_RE + r"\s+(?:tambien\s+)?(?:sale|salen|salimos|"
    r"hay\s+salida|tenemos\s+salida|recogemos)\b",
)
_NIEGA_RE = re.compile(r"\b(?:no|solo|solamente|unicamente|ni)\b")

CORRECCION_OTRA_CIUDAD = (
    "ALTO: el plan sale SOLO desde Medellín (Estación Universidad – Calle "
    "Carabobo); no hay salidas ni recogidas en otras ciudades ni en el camino. "
    "Tu mensaje decía otra cosa y NO se le envió. Vuelve a responder: dile en "
    "una línea, con honestidad, que el plan sale de Medellín, y sigue con la "
    "venta. No lo pases a un asesor por esto."
)


#: La burbuja de apertura: la que presenta a la asesora («Soy *Luisa*»). Solo
#: ahí va la línea de Medellín — un primer turno que no se presenta (la QA, o
#: un bot que contesta de una lo que le preguntaron) no se toca.
_PRESENTACION_RE = re.compile(r"\bsoy\s+\*?luisa\b", re.IGNORECASE)


def es_apertura(texto: str) -> bool:
    return bool(_PRESENTACION_RE.search(texto or ""))


def menciona_medellin(textos: Iterable[str]) -> bool:
    return any(_MEDELLIN_RE.search(t or "") for t in textos)


def con_salida_de_medellin(texto: str) -> str:
    """El primer mensaje con la línea de Medellín, antes de su pregunta."""
    if not (texto or "").strip() or _MEDELLIN_RE.search(texto):
        return texto
    abre = _inicio_ultima_pregunta(texto)
    if abre is None:
        # El bot 3 cierra con un menú debajo de la pregunta: la pregunta es la
        # última línea que tiene «¿».
        abre = texto.rfind("¿")
        if abre == -1:
            return f"{texto.rstrip()}\n\n{LINEA_MEDELLIN}"
    base = texto[:abre].rstrip()
    if not base:
        return f"{LINEA_MEDELLIN}\n\n{texto}"
    return f"{base}\n{LINEA_MEDELLIN}\n\n{texto[abre:]}"


def afirma_salida_otra_ciudad(textos: Iterable[str]) -> bool:
    """¿El bot dijo que el plan sale (o recoge) en una ciudad que no es
    Medellín? «No tenemos salida desde Cali» es la respuesta correcta y no
    cuenta: se mira si la frase niega antes de la mención."""
    for texto in textos:
        plano = senales.normalizar(texto)
        for m in _SALIDA_OTRA_CIUDAD_RE.finditer(plano):
            inicio = max(plano.rfind(".", 0, m.start()), plano.rfind("!", 0, m.start()),
                         plano.rfind("?", 0, m.start()), plano.rfind("\n", 0, m.start()))
            if _NIEGA_RE.search(plano[inicio + 1:m.end()]):
                continue
            return True
    return False


# ---------------------------------------------------------------------------
# 4. Fuera «todo incluido»
# ---------------------------------------------------------------------------

_INCLUIDO = "con hotel, transporte y alimentación"
#: Las formas en que sale: «todo incluido», «todo está incluido», «todo va
#: incluido», «incluye todo», «incluye absolutamente todo». Sin tildes en la
#: entrada del patrón porque se busca sobre el texto tal cual, con tildes.
_TODO_INCLUIDO_RE = re.compile(
    r"(?P<pre>\b(?:un|el|plan|es)\s+)?"
    r"(?:\btodo\s+(?:est[aá]\s+|va\s+|queda\s+)?inclu[ií]d[oa]s?\b"
    r"|\bincluye\s+(?:absolutamente\s+|de\s+)?todo\b(?!\s+(?:lo\s+que|el|la|los|las)\b))",
    re.IGNORECASE,
)
_NEGACION_ANTES_RE = re.compile(r"\b(?:no|tampoco|ni)\s+(?:\w+\s+){0,2}$", re.IGNORECASE)


def sin_todo_incluido(texto: str) -> str:
    """Reescribe «todo incluido» / «incluye todo» por lo que el plan sí trae.

    «No es todo incluido» se respeta: es justo la aclaración correcta.
    """
    if not texto:
        return texto

    def _reemplazo(m: "re.Match") -> str:
        antes = texto[:m.start()]
        if _NEGACION_ANTES_RE.search(antes + (m.group("pre") or "")):
            return m.group(0)
        frase = m.group(0)[len(m.group("pre") or ""):]
        pre = m.group("pre") or ""
        if frase.lower().startswith("incluye"):
            nuevo = "incluye hotel, transporte y alimentación"
        elif pre.strip().lower() in ("un", "el", "plan"):
            nuevo = _INCLUIDO
        else:
            nuevo = _INCLUIDO
        if frase[:1].isupper():
            nuevo = nuevo[:1].upper() + nuevo[1:]
        return pre + nuevo

    return _TODO_INCLUIDO_RE.sub(_reemplazo, texto)


#: «¡Sí! 🙌», «Sí,», «¡Claro que sí!», «Así es.» al arranque de la respuesta.
_SI_INICIAL_RE = re.compile(
    r"^\s*¡?\s*(?:claro\s+que\s+s[ií]|claro|por\s+supuesto|s[ií]\s+se[ñn]or[a]?|s[ií]"
    r"|as[ií]\s+es|exacto|correcto)\b"
    r"\s*[!.,:]*\s*(?:[\U0001F000-\U0001FAFF\u2600-\u27BF]\ufe0f?\s*)*",
    re.IGNORECASE,
)


def pregunta_por_todo_incluido(texto: str) -> bool:
    return bool(_TODO_INCLUIDO_RE.search(texto or ""))


def sin_si_a_todo_incluido(texto: str) -> str:
    """A «¿es todo incluido?» no se le contesta «¡Sí!»: el plan no lo es (la
    alimentación arranca el sábado y hay opcionales). Se quita la afirmación
    del arranque y queda lo que sí incluye, que es lo que el bot explica
    después (QA contra Bedrock, 7-nov: los bots 2 y 3 abrían con «¡Sí! 🙌»)."""
    m = _SI_INICIAL_RE.match(texto or "")
    if not m or m.end() >= len(texto):
        return texto
    resto = texto[m.end():]
    return resto[:1].upper() + resto[1:]


# ---------------------------------------------------------------------------
# 5. Listo para reservar con nombre completo y cédula de quien paga
# ---------------------------------------------------------------------------

#: Una cédula colombiana: 6 a 10 dígitos, con o sin puntos. Un celular (10
#: dígitos que empiezan por 3) no cuenta.
_CEDULA_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{3}){1,3}|\d{6,10})(?![\d.]*\d)")
_PALABRA_NOMBRE_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")
_NO_ES_NOMBRE = frozenset({
    "cc", "cedula", "c.c", "nombre", "completo", "mi", "es", "y", "de", "la",
    "el", "soy", "documento", "numero", "num", "no", "con", "para", "listo",
    "aqui", "van", "los", "datos", "hola", "ok", "dale", "si", "claro",
    "personas", "adultos", "nino", "ninos", "correo", "celular", "tel",
})
_PIDIO_DATOS_RE = re.compile(r"c[eé]dula|nombre\s+completo", re.IGNORECASE)

CORRECCION_CIERRE_CON_CEDULA = (
    "ALTO: la persona ya te mandó el nombre completo y la cédula de quien paga, "
    "y con eso basta para apartar: los datos de los demás viajeros los pide el "
    "compañero después. Tu mensaje NO se le envió. Responde en este turno: el "
    "valor a pagar ahora (el anticipo, o el total si la consulta marcó «PAGO "
    "TOTAL») y que haga la transferencia y mande el comprobante por aquí; y "
    "llama `listo_para_reservar`. No le pidas más datos."
)


def _cedula(texto: str) -> Optional[str]:
    for m in _CEDULA_RE.finditer(texto or ""):
        digitos = re.sub(r"\D", "", m.group(1))
        if not 6 <= len(digitos) <= 10:
            continue
        if len(digitos) == 10 and digitos.startswith("3"):
            continue          # celular
        return digitos
    return None


def trae_datos_de_quien_paga(texto: str) -> bool:
    """¿El mensaje trae un nombre completo (dos palabras o más) y una cédula?"""
    if not _cedula(texto):
        return False
    palabras = [
        p for p in _PALABRA_NOMBRE_RE.findall(texto or "")
        if senales.normalizar(p) not in _NO_ES_NOMBRE
    ]
    return len(palabras) >= 2


def ultimo_mensaje_pidio_datos(history: Sequence[Dict[str, str]]) -> bool:
    """¿El último mensaje del bot le pidió los datos de la reserva?"""
    for m in reversed(list(history or [])):
        if m.get("role") == "assistant":
            return bool(_PIDIO_DATOS_RE.search(str(m.get("content") or "")))
    return False
