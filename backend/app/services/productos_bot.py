"""El puente entre el catálogo en la base (`services/productos.py`) y el bot.

`productos.py` sabe leer el catálogo de una cuenta y redactar el resultado;
`llm_engine.py` sabe conversar. Este módulo es lo único que los conoce a los
dos: arma el índice que va en el prompt, declara las tres herramientas que se
derivan del producto y las ejecuta. Se mantiene aparte y no dentro del motor
por dos razones, y la segunda es la importante:

  1. `llm_engine.py` ya pasa de las 3.600 líneas.
  2. **El borde del fallback es este archivo.** El motor viejo sigue vivo y
     encendible (fase 8 lo retira, no antes): si algo de la capa nueva revienta
     —una plantilla del cliente, una fila con un JSON raro, la base caída— el
     turno se completa con el motor viejo y el cliente recibe su respuesta
     normal. Teniendo la capa nueva detrás de una sola puerta, ese `except` es
     uno y se ve; desparramada por el motor, serían nueve y alguno faltaría.

El interruptor es `llm_config.fuente_datos`:

    "fuente_datos": "productos"   # lee las tablas bot_producto_*
    "fuente_datos": "tarifario"   # el motor viejo (POR DEFECTO)

Por defecto, `tarifario`: **esta fase no enciende nada**. Ningún bot cambia de
comportamiento al desplegarse, y el que quiera probar la capa nueva se apunta a
ella con una línea en su config.

Los tres niveles del prompt (ver `docs/bots_productos_modelo.puml`)
--------------------------------------------------------------------
  Nivel 1  las reglas del motor, iguales para todos            → `llm_engine`
  Nivel 2  lo que el negocio dice de sí mismo                  → `bots.instrucciones`
  Nivel 3  lo que hay que saber para vender UN producto        → `bot_productos.instrucciones`

El nivel 3 entra como **resultado de herramienta**, no metido en el bloque
`system`. Esa es la decisión que mantiene viva la caché del prompt: el prefijo
se cachea entero y una ficha que cambia de conversación en conversación lo
invalidaría en cada turno. La única excepción está medida y documentada en
`ficha_en_el_prefijo()`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from . import productos

logger = logging.getLogger(__name__)

#: Valores de `llm_config.fuente_datos`.
FUENTE_PRODUCTOS = "productos"
FUENTE_TARIFARIO = "tarifario"
#: No es un valor de configuración: es lo que se escribe en la telemetría del
#: turno en que la capa nueva falló y respondió la vieja. Un fallback que nadie
#: ve es un motor nuevo que lleva tres semanas sin usarse y nadie lo sabe.
FUENTE_FALLBACK = "fallback"

#: Mínimo de tokens que Bedrock exige en el prefijo para cachearlo. Por debajo
#: no cachea, **no avisa** y se paga el triple (gotcha del 2026-08-18).
MIN_TOKENS_CACHEABLE = 4096

#: Cuántos caracteres cuenta un token. No hay tokenizador disponible sin red,
#: así que se estima. 4,0 está deliberadamente por encima de lo que rinde el
#: español real (3,0–3,5), o sea que **subestima** los tokens: cuando esta
#: cuenta dice "pasa de 4.096" el prefijo de verdad ya pasó de largo. El error
#: caro es el contrario — creer que cachea cuando no.
CARACTERES_POR_TOKEN = 4.0

#: Las tres herramientas que se derivan del producto. Cuáles se **declaran** en
#: un turno lo decide `tools()`, y no siempre son las tres: ver `_a_declarar`.
ABRIR = "abrir_producto"
PRECIOS = "consultar_precios"
FECHAS = "fechas_disponibles"
TOOLS = frozenset({ABRIR, PRECIOS, FECHAS})

#: Cuántas etiquetas se listan por período en el calendario compacto. El
#: calendario es un panorama, no la consulta: para las filas exactas está
#: `consultar_precios`.
TOPE_ETIQUETAS = 12


def tokens_aprox(texto: str) -> int:
    return int(len(texto or "") / CARACTERES_POR_TOKEN)


def fuente_de(cfg: Dict[str, Any]) -> str:
    """De dónde saca los datos este bot. `tarifario` salvo que diga lo contrario."""
    valor = str((cfg or {}).get("fuente_datos") or "").strip().lower()
    return FUENTE_PRODUCTOS if valor == FUENTE_PRODUCTOS else FUENTE_TARIFARIO


# ---------------------------------------------------------------------------
# El contexto del turno
# ---------------------------------------------------------------------------

@dataclass(frozen=True, repr=False)
class Contexto:
    """Lo que este bot puede vender, resuelto una sola vez por turno.

    Se arma antes de la primera llamada al modelo (el índice va en el prompt y
    las herramientas hay que declararlas) y se conserva hasta el final del
    turno, que es cuando las herramientas lo usan.
    """

    team_id: int
    bot_id: Optional[int]
    catalogos: Tuple[productos.Catalogo, ...]
    hoy: date

    def __repr__(self) -> str:
        # Los catálogos traen `instrucciones` y `resumen`, que los escribe el
        # cliente y suelen incluir datos de contacto (regla 1 de CLAUDE.md).
        return (
            f"<Contexto team_id={self.team_id} bot_id={self.bot_id} "
            f"productos={len(self.catalogos)}>"
        )

    __str__ = __repr__

    @property
    def unico(self) -> Optional[productos.Catalogo]:
        return self.catalogos[0] if len(self.catalogos) == 1 else None


def abrir(
    db,
    *,
    team_id: Optional[int],
    bot_id: Optional[int],
    hoy: Optional[date] = None,
) -> Optional[Contexto]:
    """Los productos publicados y vigentes que ese bot puede vender.

    `None` cuando no hay ninguno: el bot se queda exactamente como está hoy —
    su prompt sin índice y sus herramientas de siempre—, que es la promesa de
    esta fase.
    """
    if team_id is None:
        # Sin cuenta no se consulta nada. Es el peor error posible de este
        # esquema (un bot cotizando con el catálogo de otra agencia) y por eso
        # falla ruidosa en vez de "si no hay cuenta, muéstralo todo".
        logger.warning(
            "productos_bot: bot sin team_id (bot_id=%s); no se arma el índice",
            bot_id,
        )
        return None
    hoy = hoy or productos.hoy_colombia()
    catalogos = tuple(
        c
        for c in productos.catalogos_de_bot(db, team_id=team_id, bot_id=bot_id)
        if productos.vigente(c, hoy)
    )
    if not catalogos:
        return None
    return Contexto(
        team_id=int(team_id), bot_id=bot_id, catalogos=catalogos, hoy=hoy
    )


# ---------------------------------------------------------------------------
# El índice, y la única ficha que entra al prefijo
# ---------------------------------------------------------------------------

_CABECERA = (
    "## Lo que vendes\n"
    "Esto es TODO lo que manejas. Nada que no esté en esta lista existe.\n"
)
_PIE_VARIOS = (
    "Antes de hablar de uno, ábrelo con `abrir_producto` usando su clave entre "
    "comillas: ahí están sus condiciones. Los precios y las fechas NO están en "
    "esta lista ni en tu memoria — salen de `consultar_precios`."
)
_PIE_UNICO = (
    "Los precios y las fechas NO están en tus instrucciones ni en tu memoria: "
    "salen de `consultar_precios`, siempre, antes de decir una cifra."
)


def _renglones(ctx: Contexto) -> List[str]:
    """Dos líneas por producto: la clave con la que se nombra, y qué es."""
    fuera = []
    for c in ctx.catalogos:
        fuera.append(f"- `{c.slug}` — {c.nombre}")
        resumen = (c.resumen or "").strip()
        if resumen:
            fuera.append(f"  {resumen}")
    return fuera


def ficha_en_el_prefijo(ctx: Contexto, prefijo_sin_ficha: str) -> bool:
    """¿Las instrucciones del producto van dentro del bloque `system`?

    Sólo cuando el bot vende **uno solo**: con un producto, su ficha es tan
    estable como el resto del prompt y meterla dentro del prefijo la vuelve
    gratis a partir del segundo turno, además de ahorrarle al modelo la ronda
    de `abrir_producto`. Con dos o más, la ficha que entrara dependería de la
    conversación y el prefijo dejaría de repetirse — que es exactamente lo que
    la caché necesita.

    La segunda condición es la que decide si sale barato o caro, y se **mide**:
    el prefijo con la ficha adentro tiene que quedar por encima del mínimo
    cacheable. Por debajo, Bedrock no cachea (y no avisa), así que esos tokens
    se volverían a pagar enteros en cada ronda de cada turno; ahí sale más
    barato servir la ficha como resultado de herramienta, que se paga una vez
    y sólo cuando la conversación llega a ese producto.
    """
    unico = ctx.unico
    if unico is None or not (unico.instrucciones or "").strip():
        return False
    return (
        tokens_aprox(prefijo_sin_ficha + unico.instrucciones)
        >= MIN_TOKENS_CACHEABLE
    )


def bloque_indice(ctx: Contexto, *, con_ficha: bool = False) -> str:
    """El índice de productos tal como entra al bloque `system`.

    **Con un solo producto no se lista nada**, y queda sólo el pie. Un índice de
    un elemento no indexa: no hay entre qué elegir y ya no hay clave que
    escribir (con un producto, ninguna herramienta declara `producto`). Lo que
    el bot vende es nivel 2 —`bots.instrucciones` o el `.md`, cuyo trabajo es
    justamente decir de qué es este negocio— y repetirlo aquí es pagar dos veces
    la misma frase en cada ronda de cada turno.

    Lo que sí es del motor y no del negocio es el pie, y por eso se queda: el
    `.md` del piloto nombra `consultar_tarifario` catorce veces y esa
    herramienta no existe en la capa nueva. Sin el pie, el bot pide una
    herramienta que nadie le declaró.

    Si el producto único tiene ficha y ésta cabe en el prefijo, entra con su
    título, así que el nombre no se pierde: el único caso en que el nombre no
    aparece es el del producto sin ficha.
    """
    partes: List[str] = []
    unico = ctx.unico
    if unico is None:
        partes.append(_CABECERA + "\n".join(_renglones(ctx)))
    if con_ficha and unico is not None and (unico.instrucciones or "").strip():
        partes.append(f"### {unico.nombre}\n{unico.instrucciones.strip()}")
    partes.append(_PIE_UNICO if unico is not None else _PIE_VARIOS)
    return "\n\n".join(partes)


def medios_declarados(ctx: Contexto) -> Dict[str, Dict[str, Any]]:
    """Los medios del catálogo, con la forma que espera `enviar_media`.

    `consultar_precios` puede terminar diciéndole al modelo "manda `flyer_x`";
    si esa clave no existiera en el catálogo de medios, `enviar_media` no
    enviaría nada y el bot quedaría diciendo «te dejo la imagen 👇» sin
    adjuntar — el fallo silencioso que ya se pagó una vez. Las claves que el
    bot ya tenga declaradas en su `llm_config` mandan sobre éstas: nadie pierde
    un medio configurado a mano por culpa de una fila nueva.
    """
    fuera: Dict[str, Dict[str, Any]] = {}
    for catalogo in ctx.catalogos:
        for medio in catalogo.medios:
            if not medio.clave or not medio.url:
                continue
            fuera.setdefault(
                str(medio.clave),
                {
                    "url": medio.url,
                    "media_type": medio.tipo or "image",
                    "descripcion": medio.descripcion or "",
                },
            )
    return fuera


# ---------------------------------------------------------------------------
# Las herramientas — cuáles existen, y cuáles se declaran en este turno
# ---------------------------------------------------------------------------

def _claves(ctx: Contexto) -> str:
    return ", ".join(f"'{c.slug}'" for c in ctx.catalogos)


def ficha_pendiente(ctx: Contexto, prefijo: str = "") -> bool:
    """¿Queda alguna ficha de producto que el modelo tenga que ir a buscar?

    Es la otra cara de `ficha_en_el_prefijo()`, y a propósito se responde
    mirando el prefijo ya armado en vez de volver a calcular el umbral: son la
    misma decisión tomada una sola vez. Con varios productos siempre queda
    ficha pendiente (la que haga falta depende de la conversación y por eso
    ninguna entra al prefijo). Con uno solo hay ficha pendiente únicamente si
    tiene ficha **y** no viajó ya dentro del bloque `system`.

    `prefijo` vacío significa "no sé qué lleva el prefijo", y entonces se
    responde que sí: declarar una herramienta de más es caro, no tenerla
    cuando hace falta es un bot que no sabe explicar lo que vende.
    """
    unico = ctx.unico
    if unico is None:
        return True
    ficha = (unico.instrucciones or "").strip()
    return bool(ficha) and ficha not in (prefijo or "")


def _a_declarar(ctx: Contexto, prefijo: str) -> List[str]:
    """Cuáles de las tres se le declaran al modelo en este turno.

    El esquema de una herramienta se paga en **cada** llamada de **cada** turno,
    esté o no cacheado el prefijo: declarar una que no tiene nada que hacer es
    pagar ~290 tokens por ronda a cambio de nada. La medición de la fase 5 lo
    cobró — el prefijo creció 3,7 % y `abrir_producto` y `fechas_disponibles`
    se usaron CERO veces en 69 guiones.

    `consultar_precios` va siempre: es la única fuente de cifras y el prompt
    entero se apoya en ella.

    `abrir_producto` sólo cuando hay ficha que abrir (`ficha_pendiente`). Con un
    único producto cuya ficha ya viaja en el prefijo —o que no tiene ficha— no
    queda nada que devolver que el modelo no esté leyendo ya.

    `fechas_disponibles` sólo cuando hay varios productos, y por la misma razón
    que el pie del índice: con uno solo, `_PIE_UNICO` ya le dice al modelo que
    «los precios y las fechas salen de `consultar_precios`». Declarar además un
    calendario aparte era contradecir el prompt con el catálogo de
    herramientas, y el modelo le hizo caso al prompt. El calendario sigue
    existiendo para cuando el bot maneje varios productos, donde recorrer
    `consultar_precios` producto por producto sí sale caro.
    """
    nombres = [PRECIOS]
    if ficha_pendiente(ctx, prefijo):
        nombres.insert(0, ABRIR)
    if ctx.unico is None:
        nombres.append(FECHAS)
    return nombres


def tools(ctx: Contexto, *, prefijo: str = "") -> List[Dict[str, Any]]:
    """Las herramientas derivadas del producto, con sus claves reales.

    Las claves van dentro de la descripción a propósito: el modelo las tiene en
    el índice del prompt, pero la descripción de la herramienta es lo que lee
    justo antes de llamarla y es donde menos se equivoca.

    `prefijo` es el bloque `system` de este turno, ya armado: de ahí sale si la
    ficha del producto único ya está adentro. Ver `_a_declarar`.
    """
    declaradas = _a_declarar(ctx, prefijo)
    claves = _claves(ctx)
    # Con un solo producto no hay nada que elegir: `resolver_producto` devuelve
    # ese mismo catálogo cuando el campo llega vacío. Declararlo no sólo cuesta
    # esquema en cada ronda — es una forma de fallar, porque el modelo tiene que
    # acertarle a la clave y un nombre que no resuelva contesta
    # "producto_desconocido" sobre el único producto que el bot vende.
    producto_prop = (
        None
        if ctx.unico is not None
        else {
            "type": "string",
            "description": f"Clave del producto. Una de: {claves}.",
        }
    )
    variante_prop = {
        "type": "string",
        "description": (
            "Versión del producto, como la dijo el cliente. Omítela si "
            "todavía no eligió: sin ella se comparan todas."
        ),
    }

    def _props(*pares) -> Dict[str, Any]:
        """Las propiedades declaradas, sin las que no aplican a este bot."""
        return {clave: valor for clave, valor in pares if valor is not None}

    catalogo: List[Dict[str, Any]] = [
        {
            "name": ABRIR,
            "description": (
                "Abre un producto y te devuelve sus condiciones, sus versiones "
                "y en qué períodos hay disponibilidad. ÚSALA antes de explicar "
                "un producto: lo que no esté en el resultado, no lo afirmes. No "
                "devuelve precios — para eso está `consultar_precios`."
            ),
            "input_schema": {
                "type": "object",
                "properties": _props(("producto", producto_prop)),
                "required": ["producto"] if producto_prop else [],
            },
        },
        {
            "name": PRECIOS,
            "description": (
                "Los precios reales y vigentes, y qué imagen mandar. ÚSALA "
                "SIEMPRE antes de decir una cifra o de enviar una imagen de "
                "precios: cambian por versión y por período, y los del "
                "historial pueden estar vencidos. Nunca cites un valor que no "
                "venga de esta herramienta."
            ),
            "input_schema": {
                "type": "object",
                "properties": _props(
                    ("producto", producto_prop),
                    ("variante", variante_prop),
                    ("mes", {
                        "type": "string",
                        "description": (
                            "Período que pidió el cliente, como lo dijo. Ej: "
                            "'septiembre', 'diciembre'."
                        ),
                    }),
                    ("fecha", {
                        "type": "string",
                        "description": (
                            "Fecha exacta en formato AAAA-MM-DD, sólo si pidió "
                            "un día concreto."
                        ),
                    }),
                    ("presupuesto", {
                        "type": "string",
                        "description": (
                            "Cuánto quiere gastar, si lo dijo: '450 mil', "
                            "'$400.000', 'menos de 400'. Te devuelve qué cabe "
                            "en ese presupuesto y, si no cabe nada, lo más "
                            "económico que sí existe."
                        ),
                    }),
                ),
                # Nada obligatorio salvo el producto cuando hay varios: un
                # cliente puede abrir con "¿qué tienes por $400.000?" sin decir
                # período, y forzar el campo obligaría al modelo a inventarlo.
                # `consultar()` degrada bien y pide lo que le falte.
                "required": [],
            },
        },
        {
            "name": FECHAS,
            "description": (
                "El calendario de lo que sigue disponible, sin precios. Úsala "
                "cuando el cliente pregunte «¿qué fechas hay?» o «¿para cuándo "
                "tienes?». Si ya sabes el período y quiere cifras, usa "
                "`consultar_precios`."
            ),
            "input_schema": {
                "type": "object",
                "properties": _props(
                    ("producto", producto_prop),
                    ("variante", variante_prop),
                    ("desde_mes", {
                        "type": "string",
                        "description": (
                            "Período desde el cual mirar, si el cliente lo "
                            "acotó. Ej: 'noviembre'."
                        ),
                    }),
                ),
                "required": [],
            },
        },
    ]
    por_nombre = {t["name"]: t for t in catalogo}
    return [por_nombre[nombre] for nombre in declaradas]


# ---------------------------------------------------------------------------
# Ejecución
# ---------------------------------------------------------------------------

def _sin_producto(ctx: Contexto, texto: str) -> str:
    """Qué contestar cuando el modelo no nombró un producto que exista."""
    catalogo = ctx.catalogos[0]
    return productos.texto_de(
        catalogo,
        "producto_desconocido" if texto else "falta_producto",
        texto=texto,
        productos=", ".join(c.nombre for c in ctx.catalogos),
    )


def _abrir_producto(ctx: Contexto, catalogo: productos.Catalogo) -> str:
    """Nivel 3: lo que hay que saber para vender ESTE producto."""
    filas = productos.filas_vigentes(catalogo, hoy=ctx.hoy)
    if not filas:
        # Sin nada vigente no se redacta: se escala. Un bot sin datos no dice
        # "no tengo datos", improvisa — y lo que improvisa se parece a una
        # cotización.
        return productos.texto_de(catalogo, "sin_datos", producto=catalogo.nombre,
                                  hoy=ctx.hoy.isoformat())

    lineas = [f"{catalogo.nombre}"]
    resumen = (catalogo.resumen or "").strip()
    if resumen:
        lineas.append(resumen)
    instrucciones = (catalogo.instrucciones or "").strip()
    if instrucciones:
        lineas.append(instrucciones)

    activas = catalogo.activas
    if activas:
        lineas.append("Versiones:")
        for v in activas:
            nota = (v.instrucciones or "").strip()
            lineas.append(f"  · {v.nombre}" + (f" — {nota}" if nota else ""))
            dueña = productos.origen_de_precios(catalogo, v)
            if dueña.id != v.id:
                lineas.append(
                    "    "
                    + productos.texto_de(
                        catalogo,
                        "nota_precios_compartidos",
                        variante=v.nombre,
                        origen=dueña.nombre,
                        producto=catalogo.nombre,
                        hoy=ctx.hoy.isoformat(),
                    )
                )
    meses = productos.periodos_con_filas(catalogo, hoy=ctx.hoy)
    if meses:
        lineas.append(
            "Períodos con disponibilidad: "
            + ", ".join(productos.nombre_mes(m) for m in meses)
            + ". Las cifras y las fechas exactas salen de `consultar_precios`."
        )
    return "\n".join(lineas)


def _fechas_disponibles(
    ctx: Contexto,
    catalogo: productos.Catalogo,
    variante: Optional[productos.Variante],
    desde_mes: Optional[int],
) -> str:
    """El calendario compacto: qué hay y cuándo, sin una sola cifra."""
    objetivo = [variante] if variante is not None else [
        v for v in catalogo.activas
        if productos.origen_de_precios(catalogo, v).id == v.id
    ]
    orden = productos.meses_por_cercania(ctx.hoy)
    if desde_mes in orden:
        orden = orden[orden.index(desde_mes):]

    lineas: List[str] = []
    for v in objetivo:
        for mes in orden:
            filas = productos.filas_vigentes(
                catalogo, variante=v, mes=mes, hoy=ctx.hoy
            )
            if not filas:
                continue
            etiquetas = [f.etiqueta for f in filas if f.etiqueta][:TOPE_ETIQUETAS]
            resto = len(filas) - len(etiquetas)
            cola = f" (y {resto} más)" if resto > 0 else ""
            lineas.append(
                f"  · {v.nombre} — {productos.nombre_mes(mes)}: "
                f"{', '.join(etiquetas)}{cola}"
            )
    if not lineas:
        return productos.texto_de(
            catalogo, "sin_datos", producto=catalogo.nombre,
            hoy=ctx.hoy.isoformat(),
        )
    return "\n".join(
        [f"{catalogo.nombre} — disponibilidad al {ctx.hoy.isoformat()}, sin precios:"]
        + lineas
        + ["Para las cifras, llama `consultar_precios` con el período."]
    )


def ejecutar(db, ctx: Contexto, name: str, tool_input: Dict[str, Any]) -> str:
    """Corre una de las tres herramientas y devuelve el texto que lee el modelo.

    Las excepciones NO se atrapan acá: suben hasta el motor, que es quien sabe
    completar el turno con la fuente vieja. Atraparlas aquí sería convertir un
    fallback visible en un mensaje raro para el cliente.
    """
    texto_producto = str(tool_input.get("producto", "") or "")
    catalogo = productos.resolver_producto(
        db, team_id=ctx.team_id, bot_id=ctx.bot_id, texto=texto_producto
    )
    if catalogo is None:
        return _sin_producto(ctx, texto_producto)

    if name == ABRIR:
        return _abrir_producto(ctx, catalogo)

    if name == PRECIOS:
        return productos.consultar(
            db,
            team_id=ctx.team_id,
            bot_id=ctx.bot_id,
            producto=texto_producto,
            variante=str(tool_input.get("variante", "") or ""),
            mes=str(tool_input.get("mes", "") or ""),
            fecha=str(tool_input.get("fecha", "") or ""),
            presupuesto=str(tool_input.get("presupuesto", "") or ""),
            hoy=ctx.hoy,
        )

    if name == FECHAS:
        pedida = str(tool_input.get("variante", "") or "")
        variante = productos.resolver_variante(catalogo, pedida) if pedida else None
        if pedida and variante is None:
            return productos.texto_de(
                catalogo,
                "variante_desconocida",
                texto=pedida,
                variantes=", ".join(v.nombre for v in catalogo.activas),
                producto=catalogo.nombre,
                hoy=ctx.hoy.isoformat(),
            )
        desde = productos.normalizar_mes(str(tool_input.get("desde_mes", "") or ""))
        return _fechas_disponibles(ctx, catalogo, variante, desde)

    return f"herramienta desconocida: {name}"
