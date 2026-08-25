"""Consulta del tarifario de Coveñas — precios exactos, no recordados.

El bot de Arranquemos Pues vende un plan cuyo precio cambia por hotel, por mes
y por fecha de salida. Pedirle al modelo que se aprenda 102 filas de precios y
las recite es la forma más rápida de que invente una: por eso los precios NO
viven en el contexto a priori sino en `app/data/tarifario_covenas.json`
(generado desde el Excel del CEO con `scripts/generar_tarifario_covenas.py`) y
el modelo los pide con la herramienta `consultar_tarifario`.

Tres reglas del negocio que están cableadas aquí y no en el prompt, porque son
las que más caro cuestan si el modelo las olvida:

  1. **Nunca se ofrece una fecha que ya pasó.** El tarifario arranca en julio y
     el bot sigue vivo en agosto: sin este filtro le vendería a un cliente la
     salida del 06 de agosto en septiembre.
  2. **Cada mes tiene su imagen.** Qué flyer corresponde a qué mes no se
     adivina: sale del propio catálogo de medios del bot (`llm_config.media`),
     donde cada tarifario declara `hotel` y `meses`. Así el tenant puede cambiar
     una imagen sin tocar código.
  3. **Ninguna cifra de este módulo está escrita a mano.** Todo «desde», todo
     mínimo y todo precio sale de las filas de `tarifario_covenas.json`. Es la
     lección del bug del Sprint 24: la respuesta traía pegadas dos líneas con
     `$350.000` y `$389.000` constantes —el mínimo *global*— y el modelo se las
     citaba como el «desde» del mes que había pedido el cliente. Peor todavía:
     `$350.000` no existía en ninguna fila, era una cifra vieja que sobrevivió
     a varias temporadas. Si aquí aparece un número literal en un `str`, es un
     bug esperando fecha.

La herramienta responde en los dos sentidos: de mes/fecha a precios, y de
precio a fechas (`presupuesto=`), porque en la venta real el cliente entra por
donde le queda cómodo — «¿cuánto vale en septiembre?» tanto como «tengo 450
mil, ¿qué me alcanza?».

Bohíos comparte tarifa con Amor de Dios y no tiene flyer propio: se le manda el
de Amor de Dios avisando que la imagen dice otro nombre pero el precio aplica.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Colombia, sin horario de verano. El backend corre en UTC (ECS), así que
# `date.today()` se adelanta un día entre las 7 pm y la medianoche de allá — y
# el bot dejaría de ofrecer una salida que todavía se puede vender hoy.
_TZ_CO = timezone(timedelta(hours=-5))


def hoy_colombia() -> date:
    return datetime.now(_TZ_CO).date()


_DATA = Path(__file__).resolve().parent.parent / "data" / "tarifario_covenas.json"

# Nombres que puede escribir el modelo (o el cliente) -> clave interna.
_HOTELES = {
    "amor_de_dios": "amor_de_dios",
    "amor de dios": "amor_de_dios",
    "el amor de dios": "amor_de_dios",
    "hotel amor de dios": "amor_de_dios",
    "hotel el amor de dios": "amor_de_dios",
    "amordios": "amor_de_dios",
    "bohios": "bohios",
    "hotel bohios": "bohios",
    "los bohios": "bohios",
    "piedra_mar": "piedra_mar",
    "piedra mar": "piedra_mar",
    "piedramar": "piedra_mar",
    "hotel piedra mar": "piedra_mar",
}

_NOMBRE_HOTEL = {
    "amor_de_dios": "Amor de Dios",
    "bohios": "Bohíos",
    "piedra_mar": "Piedra Mar",
}

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_NOMBRE_MES = {v: k.capitalize() for k, v in _MESES.items() if k != "setiembre"}


def _sin_tildes(texto: str) -> str:
    base = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


@lru_cache(maxsize=1)
def _datos() -> Dict[str, Any]:
    try:
        return json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("tarifario: no se pudo leer %s", _DATA.name)
        return {"planes": [], "notas": []}


def normalizar_hotel(texto: str) -> Optional[str]:
    """Clave interna del hotel, o None si no se reconoce."""
    limpio = _sin_tildes(texto)
    if not limpio:
        return None
    if limpio in _HOTELES:
        return _HOTELES[limpio]
    # Búsqueda por contención: "en el hotel piedra mar", "bohíos por favor".
    for alias, clave in _HOTELES.items():
        if alias in limpio:
            return clave
    return None


def normalizar_mes(texto: str) -> Optional[int]:
    """Número de mes (1-12) a partir de un nombre, un número o AAAA-MM-DD."""
    limpio = _sin_tildes(texto)
    if not limpio:
        return None
    for nombre, num in _MESES.items():
        if nombre in limpio:
            return num
    # "2026-09-15", "09/2026", "9"
    digitos = [d for d in "".join(c if c.isdigit() else " " for c in limpio).split()]
    for d in digitos:
        if len(d) <= 2 and 1 <= int(d) <= 12:
            return int(d)
    for d in digitos:
        if len(d) == 6 and 1 <= int(d[4:]) <= 12:   # AAAAMM
            return int(d[4:])
    return None


def _pesos(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def _meses_por_cercania(hoy: date) -> List[int]:
    """Los 12 meses desde el actual hacia adelante, dando la vuelta.

    Recorrerlos de enero a diciembre ponía «Enero» de primero en agosto, como si
    fuera el mes más cercano cuando en realidad es el enero del año siguiente —
    y el bot lo leyó como un error y terminó omitiéndolo de la lista.
    """
    return [(hoy.month - 1 + i) % 12 + 1 for i in range(12)]


def _rango_temporada() -> Optional[tuple]:
    """(primera, última) fecha de salida publicada en todo el tarifario."""
    inicios = [date.fromisoformat(p["inicio"]) for p in _datos().get("planes", [])]
    return (min(inicios), max(inicios)) if inicios else None


def resolver_fecha(fecha: date, mes: Optional[int], hoy: date) -> date:
    """Corrige el año cuando el modelo manda una fecha que ya pasó.

    El modelo no sabe en qué año vive: al pedirle una fecha exacta escribía
    `2025-01-15` para «el 15 de enero», y la consulta respondía «esa fecha ya
    pasó» a un cliente que quería viajar en enero de 2027. Una fecha en el
    pasado nunca es una petición válida, así que se reinterpreta el año.

    Solo se toca lo que está demostrablemente mal: si la fecha que llega es
    futura, se respeta tal cual (el cliente pudo haber dicho el año a propósito).
    Y si ninguna reinterpretación cae dentro de la temporada publicada, se
    devuelve la original para que la consulta responda «ya pasó» — que en ese
    caso es la verdad, no un error de año.
    """
    if fecha >= hoy:
        return fecha

    dia, m = fecha.day, (mes or fecha.month)
    rango = _rango_temporada()
    for anio in (hoy.year, hoy.year + 1):
        try:
            cand = date(anio, m, dia)
        except ValueError:      # 29 de febrero en un año no bisiesto
            continue
        if cand < hoy:
            continue
        if rango is not None and not (rango[0] <= cand <= rango[1]):
            continue
        return cand
    return fecha


def planes_vigentes(
    hotel: str, hoy: Optional[date] = None, mes: Optional[int] = None
) -> List[Dict[str, Any]]:
    """Salidas del hotel que todavía se pueden vender, de la próxima a la lejana.

    `mes=None` recorre toda la temporada publicada. El filtro por `hoy` **no es
    opcional en ninguno de los dos casos**: un mínimo calculado sobre una salida
    que ya pasó es otra forma de citarle al cliente un precio que no se le puede
    vender, exactamente el problema que este módulo existe para evitar.
    """
    hoy = hoy or hoy_colombia()
    fuera = []
    for plan in _datos().get("planes", []):
        if hotel not in plan.get("hoteles", []):
            continue
        if mes is not None and plan.get("mes") != mes:
            continue
        if date.fromisoformat(plan["inicio"]) < hoy:
            continue
        fuera.append(plan)
    return sorted(fuera, key=lambda p: p["inicio"])


def planes_de(hotel: str, mes: int, hoy: Optional[date] = None) -> List[Dict[str, Any]]:
    """Planes vigentes de ese hotel en ese mes, del más próximo al más lejano."""
    return planes_vigentes(hotel, hoy, mes)


def _mas_barato(planes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """La salida más económica en **múltiple**, o None si la lista viene vacía.

    Múltiple y no doble porque es la acomodación más barata y la que el prompt
    manda cotizar por defecto («Precios y condiciones»): un «desde» en doble
    sería más caro que el que el cliente va a ver en el flyer.
    """
    if not planes:
        return None
    return min(planes, key=lambda p: (p["multiple"], p["inicio"]))


def _entre_semana(planes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Las salidas de «lunes con jueves» — las que no son de fin de semana.

    El JSON no trae una columna que lo diga: la etiqueta `plan` mezcla «Plan en
    semana», «Obsequio a Rincón del Mar» y hasta «Plan estándar» para salidas
    que arrancan el mismo lunes. Lo inequívoco es el día de arranque: el plan de
    fin de semana sale el **viernes** (78 de las 102 filas de la temporada), y
    el de entre semana arranca de lunes a jueves.
    """
    return [p for p in planes if date.fromisoformat(p["inicio"]).weekday() <= 3]


def clave_imagen(cfg: Dict[str, Any], hotel: str, mes: int) -> Optional[str]:
    """Clave del catálogo de medios con el flyer de ese hotel y ese mes.

    Bohíos no tiene flyer propio: usa el de Amor de Dios (misma tarifa).
    """
    objetivo = "amor_de_dios" if hotel == "bohios" else hotel
    media = cfg.get("media")
    if not isinstance(media, dict):
        return None
    for clave, item in media.items():
        if not isinstance(item, dict):
            continue
        if item.get("hotel") != objetivo:
            continue
        meses = item.get("meses")
        if isinstance(meses, list) and mes in meses:
            return str(clave)
    return None


def _bloque_hotel(
    cfg: Dict[str, Any],
    hotel: str,
    mes: int,
    fecha: Optional[date],
    hoy: date,
) -> List[str]:
    nombre = _NOMBRE_HOTEL[hotel]
    planes = planes_de(hotel, mes, hoy)
    lineas: List[str] = []

    if not planes:
        lineas.append(
            f"{nombre} — {_NOMBRE_MES[mes]}: NO hay NADA publicado para ese mes "
            f"en este hotel: ni fines de semana ni salidas entre semana. La "
            f"promoción de «lunes a jueves» NO aplica a un mes sin fechas "
            f"publicadas — no se la ofrezcas para {_NOMBRE_MES[mes]}."
        )
        disponibles = [_NOMBRE_MES[m] for m in _meses_por_cercania(hoy)
                       if planes_de(hotel, m, hoy)]
        if disponibles:
            lineas.append(
                f"  Meses que SÍ tienen salidas en {nombre}, del más próximo al "
                f"más lejano: {', '.join(disponibles)}."
            )
        lineas.append(
            "  Dile con qué meses SÍ hay y ofrécele el otro hotel; no escales "
            "todavía."
        )
        return lineas

    lineas.append(f"{nombre} — {_NOMBRE_MES[mes]} ({len(planes)} salidas):")
    for plan in planes:
        marca = ""
        if fecha is not None and date.fromisoformat(plan["inicio"]) == fecha:
            marca = "  <-- la fecha que pidió"
        obs = f", {plan['plan']}" if plan.get("plan") else ""
        lineas.append(
            f"  · {plan['fecha']} — múltiple {_pesos(plan['multiple'])} · "
            f"doble {_pesos(plan['doble'])} "
            f"({plan['noches']} noches / {plan['dias']} días{obs}){marca}"
        )

    if fecha is not None and not any(
        date.fromisoformat(p["inicio"]) == fecha for p in planes
    ):
        # Una por fecha de salida: varios planes arrancan el mismo día (el
        # estándar y el de Barú), y sin deduplicar las "dos más cercanas"
        # terminaban siendo el mismo día ofrecido dos veces.
        por_inicio: Dict[str, Dict[str, Any]] = {}
        for p in sorted(planes, key=lambda p: p["inicio"]):
            por_inicio.setdefault(p["inicio"], p)
        cercanos = sorted(
            por_inicio.values(),
            key=lambda p: abs((date.fromisoformat(p["inicio"]) - fecha).days),
        )[:2]
        lineas.append(
            f"  OJO: no hay salida que arranque el {fecha.isoformat()} en "
            f"{nombre}. Las más cercanas son: "
            + " y ".join(p["fecha"] for p in cercanos)
            + ". Ofrécele esas con su precio — NO escales por esto."
        )

    clave = clave_imagen(cfg, hotel, mes)
    if clave:
        # Imperativo y no "por si acaso": listar los precios en texto y no
        # mandar el flyer deja al cliente sin el documento que le sirve para
        # decidir, y es lo que pasó con Bohíos en la prueba del 19-ago-2026.
        lineas.append(
            f"  OBLIGATORIO: en esta misma respuesta envía `{clave}` con "
            "`enviar_media`. No basta con listar los precios en texto."
        )
        if hotel == "bohios":
            lineas.append(
                "  Y al mandarla, avísale que el flyer sale a nombre de *Amor de "
                "Dios* pero los precios aplican igual para Bohíos — si no se lo "
                "dices, va a creer que le mandaste el hotel equivocado."
            )
    return lineas


# (claves que cubre la línea, hotel del que se leen los precios, etiqueta,
# coletilla). Bohíos no va aparte porque cobra la misma tabla que Amor de Dios.
_GRUPOS_DESDE = (
    (("amor_de_dios", "bohios"), "amor_de_dios", "Amor de Dios y Bohíos", ""),
    (("piedra_mar",), "piedra_mar", "Piedra Mar", " No aplica para lunes festivos."),
)


def _lineas_desde(
    hotel: str,
    etiqueta: str,
    mes: Optional[int],
    hoy: date,
    coletilla: str = "",
) -> List[str]:
    """El «desde» del ámbito consultado, calculado de las salidas que aún se venden.

    Este es el arreglo del bug del Sprint 24. Antes aquí iban dos líneas fijas
    —«desde $350.000» para Amor de Dios y Bohíos, «desde $389.000» para Piedra
    Mar— que eran el mínimo de **todos** los meses. El modelo las recibía
    pegadas al bloque del mes que había pedido el cliente y las repetía como el
    «desde» de ese mes: a quien dijo *septiembre* (mínimo real $459.000) se le
    citó $350.000. Y $350.000 no aparecía en ninguna fila del tarifario, así que
    no era honrable en ningún mes: el mínimo real de Amor de Dios es $369.000.

    **Por qué el «desde» es el de todas las salidas del mes y no solo el de las
    de entre semana**, que era la otra lectura defendible: las dos líneas hablan
    de la promo de lunes con jueves, pero hay meses que solo publican viernes
    (septiembre, octubre). Con el criterio de «entre semana» esos meses se
    quedarían sin ningún «desde» real, y un modelo sin número a la mano vuelve a
    caer en el que tiene memorizado del prompt. Se escoge entonces el criterio
    que siempre le da al bot una cifra que la agencia sí puede honrar, con su
    fecha al lado para que no se pueda despegar del mes.

    La promo de entre semana se menciona aparte y solo con el mínimo de las
    salidas entre semana **de ese mismo ámbito**: si el mes no publica ninguna,
    se dice que no hay «desde» de entre semana y se acabó — nunca el de otro mes.
    """
    planes = planes_vigentes(hotel, hoy, mes)
    barato = _mas_barato(planes)
    if barato is None:
        return []

    if mes is not None:
        ambito = _NOMBRE_MES[mes]
        lineas = [
            f"{etiqueta} — «desde» de {ambito}: {_pesos(barato['multiple'])} por "
            f"persona en múltiple ({barato['fecha']}). Es el valor MÁS BAJO que "
            f"queda publicado en {ambito}: no cites un «desde» más barato para "
            f"ese mes, ni el de otro mes."
        ]
    else:
        ambito = "los meses publicados"
        lineas = [
            f"{etiqueta} — «desde» de TODOS {ambito} (ojo: NO es de un mes en "
            f"particular): {_pesos(barato['multiple'])} por persona en múltiple, "
            f"y cae en {barato['fecha']}. Si el cliente ya dijo un mes, este "
            f"valor NO le sirve: vuelve a consultar con ese mes, que tiene su "
            f"propio «desde»."
        ]

    semana = _entre_semana(planes)
    barato_semana = _mas_barato(semana)
    if barato_semana is not None:
        lineas.append(
            f"  Entre semana (lunes con jueves) en {ambito}: {len(semana)} "
            f"salida(s), desde {_pesos(barato_semana['multiple'])} por persona "
            f"en múltiple ({barato_semana['fecha']}).{coletilla}"
        )
    else:
        lineas.append(
            f"  Entre semana (lunes con jueves) en {ambito}: no hay ninguna "
            f"publicada. Sí existen salidas entre semana y puedes decirlo, pero "
            f"para {ambito} NO les pongas precio ni «desde»: el único valor que "
            f"puedes citar es el de la línea de arriba."
        )
    return lineas


_MULTIPLICADORES = (
    (("millon", "millones", "palo", "palos"), 1_000_000),
    (("mil", "lucas", "k"), 1_000),
)


def normalizar_presupuesto(texto: str) -> Optional[int]:
    """Pesos que el cliente dijo tener, de lo que sea que escriba el modelo.

    Casi nunca llega un número limpio: llega «450 mil», «$459.000», «menos de
    400», «un millón». Se resuelve aquí y no en el prompt para que el modelo no
    tenga que hacer aritmética — cuando la hace, la hace mal.
    """
    limpio = _sin_tildes(texto)
    if not limpio:
        return None
    # "450.000" y "450,000" son un solo número; el separador se cae solo si
    # parte grupos de tres dígitos, para no comerse el "1,5" de "1,5 millones".
    limpio = re.sub(r"(?<=\d)[.,\s](?=\d{3}(?!\d))", "", limpio)
    m = re.search(r"\d+", limpio)
    if not m:
        return None
    valor = int(m.group())
    cola = limpio[m.end():]
    for palabras, factor in _MULTIPLICADORES:
        if any(re.match(rf"\s*{p}\b", cola) for p in palabras):
            valor *= factor
            break
    else:
        # "tengo 450" son 450 mil, no 450 pesos. Nadie viaja con 450 pesos y
        # sin esto la búsqueda respondería "no alcanza para nada" a un cliente
        # con presupuesto de sobra.
        if valor < 10_000:
            valor *= 1_000
    return valor if 1_000 <= valor <= 100_000_000 else None


def _lista_meses(meses, hoy: date) -> str:
    """Nombres de mes del más próximo al más lejano, no de enero a diciembre.

    Mismo motivo que en `_meses_por_cercania`: ordenados por número, «Enero»
    sale antes que «Diciembre» y parece el más cercano cuando es el del año
    siguiente.
    """
    orden = {m: i for i, m in enumerate(_meses_por_cercania(hoy))}
    return ", ".join(_NOMBRE_MES[m] for m in sorted(set(meses), key=lambda m: orden[m]))


def _linea_salida(hotel: str, plan: Dict[str, Any], tope: Optional[int] = None) -> str:
    """Una salida con su precio. `fecha` ya arranca con el mes ("DICIEMBRE 08
    AL 11"), así que no hace falta repetirlo: es el dato que le permite al bot
    decir de qué mes es cada opción cuando la búsqueda cruzó varios meses."""
    doble = f"doble {_pesos(plan['doble'])}"
    if tope is not None:
        doble += (
            " (también cabe)" if plan["doble"] <= tope
            else " (se pasa del presupuesto)"
        )
    return (
        f"  · {_NOMBRE_HOTEL[hotel]} — {plan['fecha']}: múltiple "
        f"{_pesos(plan['multiple'])} · {doble} "
        f"({plan['noches']} noches / {plan['dias']} días)"
    )


# Cuántas salidas se listan antes de resumir. Un presupuesto holgado calza con
# casi las 102 filas y volcarlas todas ahoga el resto del resultado.
_TOPE_LISTADO = 8


def _bloque_presupuesto(
    hoteles: List[str],
    tope: int,
    mes: Optional[int],
    hoy: date,
) -> List[str]:
    """Búsqueda inversa: de un presupuesto a las fechas que caben en él.

    El sentido natural de la herramienta es mes -> precios, pero en la venta
    real la mitad de las preguntas van al revés («tengo 450 mil, ¿qué me
    alcanza?», «¿hay algo más económico?»). Casi ninguna es un precio exacto,
    así que se busca por techo (`multiple <= tope`) y no por igualdad.

    Si no cabe **nada**, no se responde con una lista vacía: se devuelve la
    salida más barata que sí existe para que el bot tenga algo que ofrecer. Es
    la misma filosofía que la fecha sin salida, que devuelve las cercanas en vez
    de mandar a escalar.
    """
    ambito = _NOMBRE_MES[mes] if mes is not None else "toda la temporada publicada"
    candidatos = [
        (h, p) for h in hoteles for p in planes_vigentes(h, hoy, mes)
    ]
    caben = sorted(
        [(h, p) for h, p in candidatos if p["multiple"] <= tope],
        key=lambda hp: (hp[1]["multiple"], hp[1]["inicio"]),
    )

    lineas = [
        f"PRESUPUESTO de {_pesos(tope)} por persona — búsqueda sobre {ambito} "
        f"(se compara contra la acomodación múltiple, que es la más económica)."
    ]

    if not caben:
        lineas.append(
            f"  Con {_pesos(tope)} NO alcanza para ninguna salida de {ambito}. "
            f"NO le digas «no hay nada» ni escales: ofrécele lo más económico "
            f"que sí existe."
        )
        mas_barato_ambito = _mas_barato([p for _, p in candidatos])
        if mas_barato_ambito is not None:
            hotel_barato = next(
                h for h, p in candidatos if p is mas_barato_ambito
            )
            lineas.append(f"  Lo más económico de {ambito}:")
            lineas.append(_linea_salida(hotel_barato, mas_barato_ambito, tope))
        if mes is not None:
            # Que no alcance en septiembre no quiere decir que no alcance nunca:
            # diciembre y enero son bastante más baratos. Se ofrece como cambio
            # de mes explícito, nunca colando el precio de otro mes en éste.
            otros = [
                (h, p)
                for h in hoteles
                for p in planes_vigentes(h, hoy)
                if p["multiple"] <= tope
            ]
            barato_otro = _mas_barato([p for _, p in otros])
            if barato_otro is not None:
                nombres = _lista_meses((p["mes"] for _, p in otros), hoy)
                lineas.append(
                    f"  PERO en otros meses sí le alcanza: {nombres}. La más "
                    f"económica de todas es "
                    f"{_pesos(barato_otro['multiple'])} en "
                    f"{_NOMBRE_MES[barato_otro['mes']]} ({barato_otro['fecha']}). "
                    f"Pregúntale si puede mover el viaje a alguno de esos meses "
                    f"— si dice que sí, vuelve a consultar con ese mes."
                )
        return lineas

    mostradas = caben[:_TOPE_LISTADO]
    if len(caben) > _TOPE_LISTADO:
        lineas.append(
            f"  Sí le alcanza: {len(caben)} salida(s). Van las "
            f"{len(mostradas)} MÁS ECONÓMICAS (hay más, sin listar):"
        )
    else:
        lineas.append(
            f"  Sí le alcanza: {len(caben)} salida(s), de la más económica a la "
            f"que más aprovecha su presupuesto:"
        )
    for h, p in mostradas:
        lineas.append(_linea_salida(h, p, tope))
    if len(caben) > _TOPE_LISTADO:
        restantes = caben[_TOPE_LISTADO:]
        lineas.append(
            f"  (y {len(restantes)} más, hasta {_pesos(restantes[-1][1]['multiple'])}, "
            f"en {_lista_meses((p['mes'] for _, p in restantes), hoy)}. Si quiere "
            f"ver esas, pregúntale por el mes y vuelve a consultar.)"
        )
    if mes is None:
        lineas.append(
            "  Cada fecha de arriba dice a qué mes pertenece: dilo cuando la "
            "ofrezcas. Cuando escoja mes, vuelve a consultar con ese mes para "
            "mandarle el flyer que le corresponde."
        )
    return lineas


def consultar(
    cfg: Dict[str, Any],
    *,
    hotel: str = "",
    mes: str = "",
    fecha: str = "",
    presupuesto: str = "",
    hoy: Optional[date] = None,
) -> str:
    """Resultado de `consultar_tarifario` que se le devuelve al modelo."""
    hoy = hoy or hoy_colombia()

    fecha_pedida: Optional[date] = None
    if fecha:
        try:
            fecha_pedida = date.fromisoformat(fecha.strip()[:10])
        except ValueError:
            fecha_pedida = None

    num_mes = normalizar_mes(mes) or (
        fecha_pedida.month if fecha_pedida is not None else None
    )
    tope = normalizar_presupuesto(presupuesto) if presupuesto else None
    if num_mes is None and tope is None:
        # Sin mes no se adivina: cada mes tiene su propio «desde» y responder
        # con el de la temporada entera es justo el bug que costó una cotización.
        return (
            "No entendí para qué mes. Pregúntale al cliente en qué mes piensa "
            "viajar y vuelve a consultar."
        )

    # El modelo no sabe en qué año vive y escribía fechas del año pasado.
    aviso_vencida = ""
    if fecha_pedida is not None:
        resuelta = resolver_fecha(fecha_pedida, num_mes, hoy)
        if resuelta != fecha_pedida:
            fecha_pedida = resuelta
            num_mes = resuelta.month
        elif fecha_pedida < hoy:
            # Ya pasó de verdad (no es un año mal escrito). Se avisa, pero NO se
            # corta: abajo van igual las salidas que quedan en ese mes, que es
            # lo que el cliente necesita para elegir otra.
            aviso_vencida = (
                f"OJO: el {fecha_pedida.isoformat()} ya pasó, no se puede vender. "
                "Dile que esa fecha ya salió y ofrécele de una las que siguen "
                "disponibles — NO le preguntes «¿para cuál otra fecha?» sin "
                "darle opciones."
            )
            fecha_pedida = None

    clave_hotel = normalizar_hotel(hotel) if hotel else None
    if hotel and clave_hotel is None:
        return (
            f"No reconozco el hotel '{hotel}'. Los hoteles del plan son: "
            "Amor de Dios, Piedra Mar y Bohíos."
        )

    # Sin hotel explícito se comparan los dos tarifarios: es justo lo que el
    # cliente quiere saber cuando pregunta "¿cuánto vale?" a secas, y ahorra un
    # ida y vuelta. Bohíos no se lista aparte porque cobra igual que Amor de Dios.
    hoteles = [clave_hotel] if clave_hotel else ["amor_de_dios", "piedra_mar"]

    partes: List[str] = [
        f"Tarifario de Coveñas — valores POR PERSONA (hoy es {hoy.isoformat()}; "
        "solo se listan salidas que todavía no han pasado)."
    ]
    if aviso_vencida:
        partes.append(aviso_vencida)
    if num_mes is not None:
        for h in hoteles:
            partes.extend(_bloque_hotel(cfg, h, num_mes, fecha_pedida, hoy))

    if clave_hotel is None:
        partes.append(
            "Bohíos cobra exactamente lo mismo que Amor de Dios (misma tabla)."
        )
    if tope is not None:
        partes.extend(_bloque_presupuesto(hoteles, tope, num_mes, hoy))

    # El «desde» solo se menciona si ese ámbito tiene fechas publicadas. Antes
    # se agregaba siempre, y el bot lo usó para concluir que julio "sí tiene
    # salidas" en un hotel que no publicó julio.
    con_salidas = [h for h in hoteles if planes_vigentes(h, hoy, num_mes)]
    for claves, representante, etiqueta, coletilla in _GRUPOS_DESDE:
        if any(h in claves for h in con_salidas):
            partes.extend(
                _lineas_desde(representante, etiqueta, num_mes, hoy, coletilla)
            )
    partes.append(
        "Recuerda: NUNCA le mandes el Excel ni un archivo de datos al cliente, "
        "solo la imagen del tarifario que corresponde al mes."
    )
    return "\n".join(partes)
