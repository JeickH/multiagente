"""Las piezas puras del bot D de Arranquemos Pues («Luisa conversa y te deja elegir»).

Sprint 36, release 2. El bot D cierra con dos puertas: **apartar** («¿Te los
aparto?») o **una llamada** con una asesora a la hora que la persona elija.
La segunda puerta va detrás de la bandera `llm_config["agenda_llamadas"]`, que
nace **apagada** hasta que el CEO confirme el acuerdo de tiempos con la agencia
(si nadie llama en la franja, es una promesa rota con el cliente en la mano).

Lo que vive aquí no toca la base ni el modelo:

  * la pregunta de cierre y la frase de la llamada, y el guardarraíl que la
    **quita** de todo lo que sale con la bandera apagada (`sin_frase_de_llamada`)
    o la **pone** al lado del «¿Te los aparto?» con la bandera encendida
    (`con_la_llamada`). Determinista: el guion no depende del modelo para
    omitirla;
  * la cotización que arma el servidor (plan, salida, cuántos, total, anticipo)
    sin nombres, edades, cédula ni teléfono (diseño de seguridad 3.6);
  * qué le falta a quien dijo «lo pienso» (la fecha, la plata o hablarlo);
  * los tres recordatorios (15 min / 5 h / 23 h) escritos con lo que la persona
    ya vio, sin repetir preguntas que contestó.

Ninguna cifra está escrita aquí: todas salen del total que calculó el sistema
(`venta_grupo.Total`) y que el motor guarda en el estado de la sesión.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import senales, tarifario

# ---------------------------------------------------------------------------
# Banderas
# ---------------------------------------------------------------------------


def es_d(cfg: Optional[Dict[str, Any]]) -> bool:
    """¿Es el bot D (o uno que cierra con dos puertas)?"""
    return bool((cfg or {}).get("dos_puertas"))


def agenda_activa(cfg: Optional[Dict[str, Any]]) -> bool:
    """La puerta 2. Solo con `agenda_llamadas` **exactamente** True (un "1" o
    un "sí" escritos a mano en la base no la prenden) y con el horario de la
    agencia configurado, que es de donde salen las franjas."""
    cfg = cfg or {}
    return (
        es_d(cfg)
        and cfg.get("agenda_llamadas") is True
        and isinstance(cfg.get("horario_asesores"), dict)
    )


def cupo_por_franja(cfg: Optional[Dict[str, Any]]) -> int:
    """Cuántas llamadas caben en una franja. 1 si no está o está mal escrito:
    es el valor que nunca rompe la promesa."""
    llamadas = (cfg or {}).get("llamadas")
    try:
        cupo = int((llamadas or {}).get("cupo_por_franja"))
    except (TypeError, ValueError, AttributeError):
        return 1
    return max(1, min(cupo, 20))


# ---------------------------------------------------------------------------
# La pregunta de cierre y la frase de la llamada
# ---------------------------------------------------------------------------

#: La segunda puerta, tal cual la aprobó el CEO. Solo sale con la bandera.
FRASE_LLAMADA = "Y si prefieres hablarlo, una asesora te llama a la hora que me digas."
#: La del último recordatorio (23 h), con la llamada como opción fácil.
FRASE_LLAMADA_RECORDATORIO = (
    "Si te queda más fácil hablarlo, una asesora te llama a la hora que me digas."
)


def pregunta_de_cierre(personas: int) -> str:
    """«¿Te los aparto? 🙌» (o «¿Te lo aparto? 🙌» si viaja una sola persona)."""
    return "¿Te lo aparto? 🙌" if personas == 1 else "¿Te los aparto? 🙌"


def cierre_completo(personas: int, cfg: Optional[Dict[str, Any]]) -> str:
    """La pregunta de cierre con la llamada solo si la bandera está encendida."""
    pregunta = pregunta_de_cierre(personas)
    return f"{pregunta} {FRASE_LLAMADA}" if agenda_activa(cfg) else pregunta


#: Lo que es hablar de una llamada. Ojo con «¿cómo te llamas?» (el nombre): el
#: verbo en segunda persona de *llamarse* no cuenta, por eso no hay un
#: `llam\w*` suelto. Se compara sin tildes (`senales.normalizar`).
_LLAMADA_RE = re.compile(
    r"\b(?:te|les?|lo|la|los|las|nos)\s+(?:podemos\s+|puede\s+|pueden\s+|va\s+a\s+|van\s+a\s+)?"
    r"(?:llama|llaman|llamo|llamamos|llamara|llamaran|llamaria|llamarian|llamaremos|"
    r"llamar|llame|llamen|llamemos)\b"
    r"|\bllamad[ao]s?\b|\bllamar(?:te|les|la|lo|nos)?\b|\bllamemos\b"
    r"|\bllamen(?:me|nos)?\b|\bllameme\b|\bllamame\b"
    r"|\bhablarlo\s+por\s+telefono\b|\bpor\s+telefono\b"
    r"|\ba\s+la\s+hora\s+que\s+(?:me\s+)?dig\w+",
    re.IGNORECASE,
)
_FRASES_RE = re.compile(r"[^.!?\n]*(?:[.!?]+|\n|$)")
_ADORNO_RE = re.compile(r"[ \t]*[\U0001F000-\U0001FAFF☀-➿️ \t]*")


def menciona_llamada(texto: Optional[str]) -> bool:
    """¿El texto ofrece, promete o nombra una llamada?"""
    return bool(_LLAMADA_RE.search(senales.normalizar(texto or "")))


def _frases(texto: str) -> List[str]:
    """Trozos que terminan en . ! ? o salto de línea (con su terminador)."""
    return [m.group(0) for m in _FRASES_RE.finditer(texto) if m.group(0)]


def sin_frase_de_llamada(texto: Optional[str]) -> str:
    """Quita del texto toda frase que hable de una llamada (bandera apagada).

    Se quita la frase entera, no la palabra: «Y si prefieres hablarlo, una
    asesora te llama a la hora que me digas.» se va completa y el «¿Te los
    aparto?» que va antes se queda. Si no queda nada con letras, devuelve "".
    """
    original = texto or ""
    if not menciona_llamada(original):
        return original
    partes = []
    for frase in _frases(original):
        cuerpo = frase.rstrip("\n")
        if menciona_llamada(cuerpo):
            # Los emojis que cerraban la frase anterior («¿Te los aparto? 🙌 Y
            # si prefieres…») quedan en este trozo: se le devuelven.
            adorno = _ADORNO_RE.match(frase)
            if adorno and adorno.group(0).strip():
                partes.append(adorno.group(0).rstrip())
            if frase.endswith("\n"):
                partes.append("\n")
            continue
        partes.append(frase)
    limpio = "".join(partes)
    limpio = re.sub(r"[ \t]{2,}", " ", limpio)
    limpio = re.sub(r"\n{3,}", "\n\n", limpio)
    limpio = "\n".join(l.strip() for l in limpio.split("\n")).strip()
    return limpio if re.search(r"[0-9A-Za-zÀ-ÿ]", limpio) else ""


_PIDE_APARTAR_RE = re.compile(
    r"¿\s*te\s+(?:lo|la|los|las)\s+(?:aparto|separo|reservo)\b[^?]*\?"
    r"|¿\s*te\s+(?:aparto|separo)\b[^?]*\?",
    re.IGNORECASE,
)


def con_la_llamada(texto: str) -> str:
    """Bandera encendida: después de la pregunta de apartar va la frase de la
    llamada, en la misma burbuja. Si ya está, no se toca."""
    if not texto or menciona_llamada(texto):
        return texto
    ultima = None
    for m in _PIDE_APARTAR_RE.finditer(texto):
        ultima = m
    if ultima is None:
        return texto
    corte = ultima.end()
    # Los emojis pegados a la pregunta («¿Te los aparto? 🙌») se quedan con ella.
    resto = texto[corte:]
    emojis = re.match(r"[ \t]*[\U0001F000-\U0001FAFF☀-➿️]+", resto)
    if emojis:
        corte += emojis.end()
    return f"{texto[:corte].rstrip()} {FRASE_LLAMADA}{texto[corte:]}".rstrip()


# ---------------------------------------------------------------------------
# La cotización (la arma el servidor; diseño 3.6)
# ---------------------------------------------------------------------------

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
)
_ETIQUETA_RE = re.compile(
    r"^\s*(?P<mes>[A-Za-zÁÉÍÓÚáéíóú]+)\s+(?P<d1>\d{1,2})\s+AL\s+(?P<d2>\d{1,2})"
    r"(?:\s+DE\s+(?P<mes2>[A-Za-zÁÉÍÓÚáéíóú]+))?",
    re.IGNORECASE,
)


def pesos(valor: int) -> str:
    return f"${int(valor):,}".replace(",", ".")


def salida_legible(etiqueta: str) -> str:
    """«NOVIEMBRE 20 AL 23» → «20 al 23 de noviembre»; «DICIEMBRE 30 AL 2 DE
    ENERO» → «30 de diciembre al 2 de enero». Si no se reconoce, la etiqueta en
    minúscula (nunca se inventa una fecha)."""
    m = _ETIQUETA_RE.match(etiqueta or "")
    if not m:
        return re.sub(r"\s+", " ", (etiqueta or "").strip().lower())
    mes = m.group("mes").lower()
    if m.group("mes2"):
        return f"{int(m.group('d1'))} de {mes} al {int(m.group('d2'))} de {m.group('mes2').lower()}"
    return f"{int(m.group('d1'))} al {int(m.group('d2'))} de {mes}"


def inicio_de_salida(etiqueta: str) -> Optional[date]:
    """La fecha en que arranca la salida, buscada en el tarifario por su
    etiqueta (como `venta_grupo._sale_muy_pronto`)."""
    plano = (etiqueta or "").upper()
    for plan in (tarifario._datos() or {}).get("planes", []):
        fecha = str(plan.get("fecha") or "").upper()
        if not fecha or fecha not in plano:
            continue
        try:
            return date.fromisoformat(plan["inicio"])
        except (KeyError, ValueError):
            continue
    return None


def cotizacion_de(total: Any, *, opciones: int = 1) -> Dict[str, Any]:
    """Lo que se guarda en el estado de la sesión de un `venta_grupo.Total`.
    Solo datos del plan: ni nombres, ni edades, ni documentos."""
    return {
        "etiqueta": str(getattr(total, "etiqueta", "") or "")[:60],
        "hotel": str(getattr(total, "hotel", "") or "")[:40],
        "acomodacion": str(getattr(total, "acomodacion", "") or "")[:12],
        "personas": int(getattr(total, "personas", 0) or 0),
        "total": int(getattr(total, "total", 0) or 0),
        "a_pagar": int(getattr(total, "a_pagar", 0) or 0),
        "pago_total": bool(getattr(total, "pago_total", False)),
        "opciones": max(1, int(opciones or 1)),
    }


def cotizacion_valida(cot: Any) -> Optional[Dict[str, Any]]:
    """La cotización del estado si tiene lo mínimo (total, personas, salida)."""
    if not isinstance(cot, dict):
        return None
    try:
        personas = int(cot.get("personas") or 0)
        total = int(cot.get("total") or 0)
    except (TypeError, ValueError):
        return None
    if not (1 <= personas <= 30) or total <= 0 or not str(cot.get("etiqueta") or "").strip():
        return None
    return cot


def texto_cotizacion(cot: Optional[Dict[str, Any]]) -> Optional[str]:
    """La cotización de la fila de la llamada (columna `cotizacion`, ≤ 1000).

    «Plan Tolú & Coveñas · 20 al 23 de noviembre · Amor de Dios (doble) · 2
    personas · total $918.000 · anticipo $275.400»."""
    cot = cotizacion_valida(cot)
    if cot is None:
        return None
    partes = ["Plan Tolú & Coveñas", salida_legible(cot["etiqueta"])]
    hotel = str(cot.get("hotel") or "").strip()
    acom = str(cot.get("acomodacion") or "").strip()
    if hotel:
        partes.append(f"{hotel} ({acom})" if acom else hotel)
    n = int(cot["personas"])
    partes.append(f"{n} persona" + ("s" if n != 1 else ""))
    partes.append(f"total {pesos(cot['total'])}")
    a_pagar = int(cot.get("a_pagar") or 0)
    if cot.get("pago_total"):
        partes.append("pago total al reservar (sale muy pronto)")
    elif 0 < a_pagar < int(cot["total"]):
        partes.append(f"anticipo {pesos(a_pagar)}")
    return " · ".join(partes)[:1000]


def resumen_para_el_cliente(cot: Optional[Dict[str, Any]]) -> Optional[str]:
    """«3 personas, del 20 al 23 de noviembre, $1.377.000»."""
    cot = cotizacion_valida(cot)
    if cot is None:
        return None
    n = int(cot["personas"])
    quien = "1 persona" if n == 1 else f"{n} personas"
    return f"{quien}, del {salida_legible(cot['etiqueta'])}, {pesos(cot['total'])}"


# ---------------------------------------------------------------------------
# La lista de franjas y la confirmación (las escribe el sistema)
# ---------------------------------------------------------------------------

INTRO_FRANJAS = "¿A qué hora te queda bien que te llamemos? Respóndeme con el número 👇"


def _keycap(n: int) -> str:
    return f"{n}️⃣"


def mensaje_franjas(etiquetas: Sequence[str]) -> str:
    lineas = [INTRO_FRANJAS]
    lineas.extend(f"{_keycap(i)} {e}" for i, e in enumerate(etiquetas, 1))
    return "\n".join(lineas)


def confirmacion(cuando: str, cot: Optional[Dict[str, Any]]) -> str:
    """«¡Listo! 📞 Una asesora te llama *mañana miércoles entre 8 y 10 a.m.* a
    este número. Ya va a tener tu cotización: 3 personas, del 20 al 23 de
    noviembre, $1.377.000.» + la puerta 1 abierta."""
    lineas = [f"¡Listo! 📞 Una asesora te llama *{cuando}* a este número."]
    resumen = resumen_para_el_cliente(cot)
    if resumen:
        lineas[0] += f" Ya va a tener tu cotización: {resumen}."
    lineas.append("Si antes quieres apartar, me escribes por aquí y lo hacemos 🙌")
    return "\n".join(lineas)


#: Una hora escrita por el modelo («a las 9», «de 8 a 10 a.m.», «3 p.m.»).
_HORA_RE = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?\s?m\.?|p\.?\s?m\.?|m\.)(?!\w)"
    r"|\ba\s+las\s+\d{1,2}\b|\bde\s+\d{1,2}\s+a\s+\d{1,2}\b",
    re.IGNORECASE,
)
_KEYCAP_RE = re.compile(r"[0-9]️?⃣")


def escribe_horarios(texto: Optional[str]) -> bool:
    """¿El modelo escribió horas o una lista numerada? (el horario lo da el
    sistema)."""
    return bool(_HORA_RE.search(texto or "") or _KEYCAP_RE.search(texto or ""))


# ---------------------------------------------------------------------------
# «Lo pienso»: qué le falta
# ---------------------------------------------------------------------------

FALTA_PLATA = "plata"
FALTA_FECHA = "fecha"
FALTA_HABLARLO = "hablarlo"

_FALTA = (
    (FALTA_PLATA, re.compile(
        r"\b(?:plata|platica|dinero|presupuesto|caro|cara|costoso|pagar|pago|"
        r"quincena|sueldo|lucas|billete|economic\w*|recursos)\b")),
    (FALTA_HABLARLO, re.compile(
        r"\b(?:hablar\w*|consult\w*|esposo|esposa|marido|mama|papa|mami|papi|"
        r"novio|novia|pareja|familia|hijos?|hijas?|amig[oa]s?|herman[oa]s?|"
        r"grupo|los\s+que\s+van|mi\s+gente|socios?)\b")),
    (FALTA_FECHA, re.compile(
        r"\b(?:fecha|fechas|dia|dias|vacaciones|permiso|trabajo|turno|agenda|"
        r"cuadrar|tiempo|mes)\b")),
)


def lo_que_falta(texto: Optional[str]) -> Optional[str]:
    """`plata`, `hablarlo` o `fecha` según lo que respondió; None si nada."""
    plano = senales.normalizar(texto or "")
    for clave, patron in _FALTA:
        if patron.search(plano):
            return clave
    return None


# ---------------------------------------------------------------------------
# Recordatorios (15 min / 5 h / 23 h) con lo que la persona ya vio
# ---------------------------------------------------------------------------


def _grupo(n: int) -> str:
    return "los dos" if n == 2 else f"los {n}"


def recordatorio(
    posicion: int,
    total_etapas: int,
    estado: Optional[Dict[str, Any]],
    *,
    llamada: bool,
    hoy: Optional[date] = None,
) -> Optional[str]:
    """El texto del recordatorio `posicion` (0 = el primero) o None para que
    salga el texto fijo de la config.

    Solo hay texto propio si la sesión guardó una cotización vigente (la
    salida no ha pasado). `llamada` = la puerta 2 encendida: solo entonces el
    último recordatorio la ofrece.
    """
    estado = estado if isinstance(estado, dict) else {}
    cot = cotizacion_valida(estado.get("cotizacion"))
    if cot is None:
        return None
    hoy = hoy or tarifario.hoy_colombia()
    inicio = inicio_de_salida(cot["etiqueta"])
    if inicio is not None and inicio < hoy:
        return None
    n = int(cot["personas"])
    salida = salida_legible(cot["etiqueta"])
    total = pesos(cot["total"])
    uno = n == 1
    ultimo = total_etapas > 0 and posicion >= total_etapas - 1
    if posicion == 0 and not ultimo:
        if int(cot.get("opciones") or 1) > 1:
            return (
                "¿Alguna de esas fechas te sirve, o miramos otro mes? 😊" if uno
                else "¿Alguna de esas fechas les sirve, o miramos otro mes? 😊"
            )
        return (
            f"¿Te sirve la del *{salida}*, o miramos otra fecha? 😊" if uno
            else f"¿Les sirve la del *{salida}*, o miramos otra fecha? 😊"
        )
    pregunta = pregunta_de_cierre(n)
    if not ultimo:
        a_pagar = int(cot.get("a_pagar") or 0)
        if (
            estado.get("lo_que_falta") == FALTA_PLATA
            and not cot.get("pago_total")
            and 0 < a_pagar < int(cot["total"])
        ):
            cupos = "tu cupo" if uno else f"los {n} cupos"
            return (
                f"Te cuento por si te ayuda: con un anticipo de *{pesos(a_pagar)}* "
                f"apartas {cupos} del *{salida}*, y el resto se paga antes del "
                f"viaje 🌴 {pregunta}"
            )
        if estado.get("lo_que_falta") == FALTA_FECHA:
            return (
                f"¿Pudiste mirar lo de la fecha? 😊 Del *{salida}*, "
                + ("" if uno else f"para {_grupo(n)}, ")
                + f"son *{total}* 🌴 {pregunta}"
            )
        if uno:
            return f"Te dejo el total para que lo tengas a mano: del *{salida}*, *{total}* 🌴 {pregunta}"
        return (
            "Te dejo el total por si lo estás hablando con los que van: del "
            f"*{salida}*, para {_grupo(n)}, *{total}* 🌴 {pregunta}"
        )
    cierre = "¿Te aparto el cupo?" if uno else "¿Te aparto los cupos?"
    medio = f" {FRASE_LLAMADA_RECORDATORIO}" if llamada else ""
    return f"Te escribo una última vez para no molestarte 😊{medio} {cierre}"


def textos_salientes(acciones: Iterable[Dict[str, Any]]) -> List[str]:
    return [
        str((a.get("payload") or {}).get("text") or "")
        for a in acciones if a.get("type") in ("say", "end")
    ]
