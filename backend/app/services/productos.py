"""Lo que vende una cuenta, leído de la base — capa genérica, no de un negocio.

Este módulo es el reemplazo de `services/tarifario.py`, que hoy le sirve los
precios al bot de viajes leyendo un JSON del repo. El JSON funciona, pero
cambiar un precio es un despliegue y sólo sirve para ese cliente. Las ocho
tablas `bot_producto_*` mueven ese catálogo a la base; esto es lo que las lee.

**Regla de diseño, y es la que define si el módulo está bien hecho: aquí no se
nombra ningún concepto de ningún negocio.** Ni una palabra del vocabulario de
un cliente, por evidente que parezca. Lo único que existe acá son productos,
variantes, filas, alias, medios y períodos — y el guardián de esa regla es
`test_el_texto_no_nombra_el_negocio_en_el_codigo`, que lee este archivo entero
y falla si se cuela una. Todo lo que suena a un cliente en particular
—incluido el texto con el que se le responde al modelo— vive en los datos:

  * los renglones del catálogo, en `bot_producto_filas` (`valores` JSONB);
  * las versiones del producto, en `bot_producto_variantes`;
  * cómo le dice la gente, en `bot_producto_alias`;
  * **cómo se redacta el resultado**, en `bot_productos.atributos["presentacion"]`,
    un diccionario de plantillas (ver `PLANTILLA`, que trae los valores por
    defecto). Sin esto no habría forma de que siete negocios distintos
    compartan una capa: el texto que lee el modelo es parte del producto, no
    del código. Una plantilla que reviente (un `{campo}` que no existe) se
    registra y cae de vuelta en la del módulo: un error de configuración del
    cliente no puede tumbarle el turno al bot.

Las tres reglas de negocio que `tarifario.py` dejó cableadas a propósito siguen
cableadas aquí, porque no son del cliente sino de la clase de problema:

  1. **Nunca se ofrece una fila que ya venció.** El filtro por `hoy` no es
     opcional, y `hoy` entra **por parámetro**: si se leyera del reloj, la
     suite empezaría a fallar sola el día que pase la última fecha cargada.
     Cuando no lo mandan, se usa la fecha de Colombia (`hoy_colombia`), no la
     del servidor: el backend corre en UTC y entre las 7 pm y la medianoche de
     allá ya cree que es mañana.
  2. **Ninguna cifra sale escrita a mano.** Todo «desde», todo mínimo y todo
     precio se calcula sobre las filas vigentes. Es la lección del Sprint 24:
     un mínimo *global* pegado al bloque de un mes se le citó a un cliente como
     el precio de ese mes. Si en este archivo aparece un número dentro de un
     `str`, es un bug esperando fecha.
  3. **Un producto sin filas vigentes NO se redacta: se escala.** Es la regla
     que este esquema viene a comprar. Un bot sin datos no dice "no tengo
     datos", improvisa — y lo que improvisa se parece muchísimo a una
     cotización. Decisión del CEO.

Aislamiento por cuenta
----------------------
Toda consulta filtra por `team_id`, y cuando se pide con `bot_id` el producto
además tiene que estar enganchado a ese bot en `bot_producto_bots`. Es el peor
error posible de este esquema: un bot cotizando con los precios de otra
agencia. Si `team_id` llega `None` no se consulta nada, se devuelve vacío y se
registra un warning con el `bot_id` — fallar callada aquí sería peor que fallar
(otra decisión ya tomada: nada de "si no hay cuenta, muéstralo todo").

Caché
-----
Un diccionario en proceso, sin Redis: son treinta líneas y el catálogo de una
cuenta cabe de sobra en memoria. Dentro de `TTL_SEGUNDOS` se devuelve la copia
sin tocar la base (cero consultas); pasado el TTL se consulta **un solo**
renglón —`MAX(updated_at)` y `COUNT(*)` sobre las cinco tablas del producto— y
sólo si ese sello cambió se releen las filas. El `COUNT(*)` va en el sello a
propósito: un `DELETE` no mueve el máximo de `updated_at`, así que sin contar
las filas una fila retirada seguiría vendiéndose hasta el siguiente cambio.
Consecuencia a la vista: un precio editado tarda a lo sumo `TTL_SEGUNDOS` en
llegarle al bot.
"""
from __future__ import annotations

import logging
import re
import string
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from app import models

logger = logging.getLogger(__name__)

# Colombia, sin horario de verano. Mismo motivo que en `tarifario.hoy_colombia`:
# el backend corre en UTC y `date.today()` se adelanta un día entre las 7 pm y
# la medianoche de allá.
_TZ_CO = timezone(timedelta(hours=-5))

#: Segundos que una copia del catálogo se considera fresca sin ir a la base.
#: Módulo-nivel y no constante encerrada para que la suite pueda ponerlo en 0.
TTL_SEGUNDOS = 60

#: Cuántas filas se listan dentro del bloque de un período antes de resumir.
#: Un período cargado se come el presupuesto de tokens del turno y el modelo
#: empieza a saltarse líneas. Se pisa por producto con `presentacion`.
#:
#: **Por qué 20 y no 8**: el módulo que esta capa reemplaza no recortaba el
#: bloque, y el período más cargado del catálogo que ya está migrado tiene 14
#: filas. Un tope por debajo de eso le habría cambiado la respuesta al bot —y
#: la prueba de oro lo dice en voz alta: con el tope en 5, 58 de los 127 casos
#: dejan de coincidir—. 20 protege el turno sin tocar lo que hoy se responde.
TOPE_BLOQUE = 20

#: Cuántas filas se listan en una búsqueda (por ejemplo, por precio máximo), que
#: puede cruzar todos los períodos a la vez y calzar con el catálogo entero. Es
#: el mismo número del módulo viejo, y ahí sí se ejercita todos los días.
TOPE_LISTADO = 8


def hoy_colombia() -> date:
    return datetime.now(_TZ_CO).date()


# ---------------------------------------------------------------------------
# Texto: normalización, meses y dinero. Todo calendario y aritmética, nada de
# ningún negocio en particular.
# ---------------------------------------------------------------------------

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_NOMBRE_MES = {v: k.capitalize() for k, v in _MESES.items() if k != "setiembre"}

_MULTIPLICADORES = (
    (("millon", "millones", "palo", "palos"), 1_000_000),
    (("mil", "lucas", "k"), 1_000),
)


def _sin_tildes(texto: str) -> str:
    base = unicodedata.normalize("NFD", (texto or "").strip().lower())
    return "".join(c for c in base if unicodedata.category(c) != "Mn")


def _pesos(valor: float) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def normalizar_mes(texto: str) -> Optional[int]:
    """Número de mes (1-12) a partir de un nombre, un número o AAAA-MM-DD."""
    limpio = _sin_tildes(texto)
    if not limpio:
        return None
    for nombre, num in _MESES.items():
        if nombre in limpio:
            return num
    digitos = [d for d in "".join(c if c.isdigit() else " " for c in limpio).split()]
    for d in digitos:
        if len(d) <= 2 and 1 <= int(d) <= 12:
            return int(d)
    for d in digitos:
        if len(d) == 6 and 1 <= int(d[4:]) <= 12:   # AAAAMM
            return int(d[4:])
    return None


def normalizar_presupuesto(texto: str) -> Optional[int]:
    """Pesos que el cliente dijo tener, de lo que sea que escriba el modelo.

    Casi nunca llega un número limpio: llega «450 mil», «$459.000», «menos de
    400», «un millón». Se resuelve acá y no en el prompt para que el modelo no
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
        # "tengo 450" son 450 mil, no 450 pesos. Nadie compra con 450 pesos y
        # sin esto la búsqueda respondería "no alcanza para nada" a alguien con
        # presupuesto de sobra.
        if valor < 10_000:
            valor *= 1_000
    return valor if 1_000 <= valor <= 100_000_000 else None


def nombre_mes(mes: int) -> str:
    """'Marzo'. Público: el puente con el bot arma su calendario con esto."""
    return _NOMBRE_MES.get(int(mes), "")


def _meses_por_cercania(hoy: date) -> List[int]:
    """Los 12 meses desde el actual hacia adelante, dando la vuelta.

    Recorrerlos de enero a diciembre pone «Enero» de primero en agosto, como si
    fuera el mes más cercano cuando en realidad es el del año siguiente.
    """
    return [(hoy.month - 1 + i) % 12 + 1 for i in range(12)]


def _lista_meses(meses: Iterable[int], hoy: date) -> str:
    orden = {m: i for i, m in enumerate(_meses_por_cercania(hoy))}
    return ", ".join(_NOMBRE_MES[m] for m in sorted(set(meses), key=lambda m: orden[m]))


def _lista_y(nombres: Sequence[str]) -> str:
    """«A, B y C» — la última con «y», como la escribiría una persona."""
    nombres = [n for n in nombres if n]
    if not nombres:
        return ""
    if len(nombres) == 1:
        return nombres[0]
    return ", ".join(nombres[:-1]) + " y " + nombres[-1]


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------

#: Los textos por defecto. Un producto los pisa, entero o por clave, en
#: `atributos["presentacion"]`. Son a propósito sosos: el que quiera vender con
#: su voz la escribe en sus datos, no acá.
PLANTILLA: Dict[str, Any] = {
    # Cabecera y cierre: listas de líneas.
    "encabezado": [
        "{producto} — información vigente al {hoy}. Solo se listan opciones "
        "que todavía se pueden ofrecer.",
    ],
    "cierre": [],
    # Cortes de camino.
    "sin_periodo": (
        "No entendí para qué fecha. Pregúntale al cliente y vuelve a consultar."
    ),
    "sin_datos": (
        "No hay información vigente de este producto. NO improvises precios, "
        "fechas ni condiciones: dile al cliente que lo vas a confirmar y pasa "
        "la conversación a un asesor."
    ),
    "variante_desconocida": "No reconozco '{texto}'. Las opciones son: {variantes}.",
    "producto_desconocido": (
        "No reconozco '{texto}'. Los productos disponibles son: {productos}."
    ),
    "falta_producto": (
        "No dijiste de cuál producto. Los que manejas son: {productos}. "
        "Pregúntale al cliente cuál le interesa y vuelve a consultar."
    ),
    "aviso_vencido": (
        "OJO: el {fecha} ya pasó y no se puede ofrecer. Dile que esa fecha ya "
        "salió y ofrécele de una las que siguen disponibles."
    ),
    # Una fila.
    "duracion": "",
    "nota_fila": "",
    "fila": "  · {etiqueta} — {valores}{obs}{marca}",
    "fila_marcada": "  <-- lo que pidió",
    # El bloque de un período.
    "bloque_titulo": "{variante} — {periodo} ({n} opciones):",
    "bloque_tope": (
        "  (y {n} más sin listar. Si quiere verlas, pregúntale por cuál se "
        "inclina y vuelve a consultar.)"
    ),
    "vacio": "{variante} — {periodo}: no hay nada publicado para ese período.",
    "vacio_periodos": (
        "  Períodos que SÍ tienen, del más próximo al más lejano: {periodos}."
    ),
    "vacio_cierre": "  Dile cuáles SÍ hay antes de escalar.",
    "fecha_sin_fila": (
        "  OJO: no hay nada que arranque el {fecha} en {variante}. Lo más "
        "cercano: {cercanas}. Ofrécele eso — NO escales por esto."
    ),
    "fila_cercana": "{etiqueta}",
    "medio": (
        "  OBLIGATORIO: en esta misma respuesta envía `{clave}` con "
        "`enviar_media`."
    ),
    "nota_precios_compartidos": "{variante} cuesta exactamente lo mismo que {origen}.",
    # El «desde».
    "ambito_global": "todos los períodos publicados",
    "desde_periodo": "{grupo} — «desde» de {ambito}: {precio} ({etiqueta}).",
    "desde_global": (
        "{grupo} — «desde» de {ambito} (ojo: NO es de un período en "
        "particular): {precio} ({etiqueta})."
    ),
    #: Subconjunto opcional del que se informa aparte (ej.: ciertos días de la
    #: semana). `dias_semana` usa la convención de `date.weekday()`: 0 = lunes.
    "subgrupo": {},
    "subgrupo_con": "",
    "subgrupo_sin": "",
    # Búsqueda por tope de precio.
    "presupuesto_ambito_global": "todo lo publicado",
    "presupuesto_titulo": "PRESUPUESTO de {tope} — búsqueda sobre {ambito}.",
    "presupuesto_nada": (
        "  Con {tope} no alcanza para nada de {ambito}. NO le digas «no hay "
        "nada» ni escales: ofrécele lo más económico que sí existe."
    ),
    "presupuesto_nada_mejor": "  Lo más económico de {ambito}:",
    "presupuesto_otros": (
        "  PERO en otros períodos sí le alcanza: {periodos}. La más económica "
        "es {precio} en {periodo} ({etiqueta})."
    ),
    "presupuesto_si": "  Sí le alcanza: {total} opción(es), de la más económica en adelante:",
    "presupuesto_si_tope": (
        "  Sí le alcanza: {total} opción(es). Van las {n} MÁS ECONÓMICAS (hay "
        "más, sin listar):"
    ),
    "fila_presupuesto": "  · {variante} — {etiqueta}: {valores}{cabe}",
    "cabe_si": "",
    "cabe_no": "",
    "presupuesto_restantes": (
        "  (y {n} más, hasta {precio}, en {periodos}. Si quiere ver esas, "
        "pregúntale por el período y vuelve a consultar.)"
    ),
    "presupuesto_cierre_sin_periodo": "",
    #: Clave de `valores` con la cifra que se compara y se ordena.
    "precio": "precio",
    "tope_bloque": TOPE_BLOQUE,
    "tope_listado": TOPE_LISTADO,
}

_CAMPOS = string.Formatter()


def _placeholders(plantilla: str) -> List[str]:
    return [
        campo.split("!")[0].split(":")[0].split(".")[0].split("[")[0]
        for _, campo, _, _ in _CAMPOS.parse(plantilla)
        if campo
    ]


def _fmt(plantillas: Dict[str, Any], clave: str, datos: Dict[str, Any]) -> str:
    """Renderiza una plantilla; si la del cliente está mal, usa la del módulo.

    Un `{campo}` que no existe es un error de configuración del tenant, no del
    turno del cliente: se registra server-side (regla 6 de CLAUDE.md) y el bot
    sigue respondiendo con el texto por defecto.
    """
    plantilla = plantillas.get(clave, PLANTILLA.get(clave, ""))
    if not plantilla:
        return ""
    try:
        return str(plantilla).format(**datos)
    except Exception:
        logger.exception("productos: plantilla '%s' inválida", clave)
    respaldo = PLANTILLA.get(clave, "")
    try:
        return str(respaldo).format(**datos) if respaldo else ""
    except Exception:
        return ""


def _fmt_lista(plantillas: Dict[str, Any], clave: str, datos: Dict[str, Any]) -> List[str]:
    lineas = plantillas.get(clave, PLANTILLA.get(clave, []))
    if isinstance(lineas, str):
        lineas = [lineas]
    fuera = []
    for i, linea in enumerate(lineas or []):
        try:
            fuera.append(str(linea).format(**datos))
        except Exception:
            logger.exception("productos: plantilla '%s'[%d] inválida", clave, i)
    return fuera


def _opcional(plantillas: Dict[str, Any], clave: str, datos: Dict[str, Any]) -> str:
    """Igual que `_fmt`, pero vacía si alguno de sus campos no tiene valor.

    Es lo que permite que una plantilla como `", {promocion}"` se caiga sola en
    las filas que no traen esa columna, sin que el cliente tenga que declarar
    dos plantillas ni el módulo saber qué es una promoción.
    """
    plantilla = plantillas.get(clave, PLANTILLA.get(clave, ""))
    if not plantilla:
        return ""
    for campo in _placeholders(str(plantilla)):
        if not datos.get(campo):
            return ""
    return _fmt(plantillas, clave, datos)


# ---------------------------------------------------------------------------
# El catálogo en memoria: copias planas, desprendidas de la sesión
# ---------------------------------------------------------------------------

@dataclass(frozen=True, repr=False)
class Variante:
    id: int
    slug: str
    nombre: str
    instrucciones: Optional[str]
    atributos: Dict[str, Any]
    precios_de_variante_id: Optional[int]
    activo: bool
    orden: int

    def __repr__(self) -> str:
        # Regla 1 (CLAUDE.md): `instrucciones` lo escribe el cliente y suele
        # traer datos de contacto. No sale ni en un repr de debug, igual que en
        # el modelo del que se copió.
        return (
            f"<Variante id={self.id} slug={self.slug!r} activo={self.activo} "
            f"instrucciones=<REDACTED>>"
        )

    __str__ = __repr__


@dataclass(frozen=True)
class Fila:
    id: int
    variante_id: int
    tipo: str
    etiqueta: str
    inicio: Optional[date]
    fin: Optional[date]
    valores: Dict[str, Any]
    nota: Optional[str]
    orden: int


@dataclass(frozen=True)
class Medio:
    id: int
    variante_id: int
    clave: str
    url: str
    tipo: str
    descripcion: Optional[str]
    aplica: Dict[str, Any]


@dataclass(frozen=True, repr=False)
class Catalogo:
    """Foto inmutable de un producto y todo lo que cuelga de él.

    Se guarda en la caché y sobrevive a la sesión que lo leyó, así que no
    contiene ni una instancia del ORM: todo son dataclasses y dicts.
    """

    producto_id: int
    team_id: int
    slug: str
    nombre: str
    tipo: str
    estado: str
    resumen: Optional[str]
    instrucciones: Optional[str]
    atributos: Dict[str, Any]
    #: Ventana en que el producto se puede ofrecer. `None` a cada lado = sin
    #: límite. Es distinto de la vigencia de una fila: acá vence el producto
    #: entero (una campaña de temporada), allá vence una fecha suelta.
    vigencia_desde: Optional[date]
    vigencia_hasta: Optional[date]
    variantes: Tuple[Variante, ...]
    filas: Tuple[Fila, ...]
    medios: Tuple[Medio, ...]
    #: (nivel, alias normalizado) -> ref_id, en orden de inserción.
    alias: Tuple[Tuple[str, str, int], ...]

    def __repr__(self) -> str:
        # Mismo criterio que `BotProducto.__repr__`: `instrucciones`, `resumen`
        # y `atributos` los escribe el cliente y ahí aparecen teléfonos y
        # direcciones. Un catálogo puede terminar en un log o en la traza de una
        # prueba que falla.
        return (
            f"<Catalogo producto_id={self.producto_id} team_id={self.team_id} "
            f"slug={self.slug!r} estado={self.estado!r} "
            f"variantes={len(self.variantes)} filas={len(self.filas)} "
            f"instrucciones=<REDACTED> resumen=<REDACTED> "
            f"atributos=<REDACTED>>"
        )

    __str__ = __repr__

    @property
    def plantillas(self) -> Dict[str, Any]:
        presentacion = self.atributos.get("presentacion")
        return presentacion if isinstance(presentacion, dict) else {}

    def variante(self, variante_id: Optional[int]) -> Optional[Variante]:
        for v in self.variantes:
            if v.id == variante_id:
                return v
        return None

    @property
    def activas(self) -> List[Variante]:
        return [v for v in self.variantes if v.activo]


# ---------------------------------------------------------------------------
# Caché
# ---------------------------------------------------------------------------

@dataclass
class _Entrada:
    catalogo: Catalogo
    sello: Tuple[Any, int]
    revisado: float


_CACHE: Dict[Tuple[int, int], _Entrada] = {}


def limpiar_cache(team_id: Optional[int] = None) -> None:
    """Bota la copia en memoria. Sin `team_id`, la de todas las cuentas.

    Se llama al escribir en el catálogo (el importador) y en cada test: la
    caché es de proceso, y dos tests con bases distintas pueden reusar los
    mismos ids.
    """
    if team_id is None:
        _CACHE.clear()
        return
    for clave in [c for c in _CACHE if c[0] == team_id]:
        _CACHE.pop(clave, None)


def _sello(db: Session, team_id: int, producto_id: int) -> Optional[Tuple[Any, int]]:
    """`(MAX(updated_at), COUNT(*))` de las cinco tablas, en una consulta.

    `None` cuando el producto no existe **para esa cuenta**: las cinco partes
    pasan por `bot_productos` con el `team_id` puesto, así que un id ajeno no
    devuelve ni el sello.
    """
    P = models.BotProducto
    trozos = [
        select(P.updated_at.label("u")).where(P.id == producto_id, P.team_id == team_id)
    ]
    for tabla in (
        models.BotProductoVariante,
        models.BotProductoFila,
        models.BotProductoMedio,
        models.BotProductoAlias,
    ):
        trozos.append(
            select(tabla.updated_at.label("u"))
            .select_from(tabla)
            .join(P, tabla.producto_id == P.id)
            .where(P.id == producto_id, P.team_id == team_id)
        )
    sub = union_all(*trozos).subquery()
    maximo, cuantas = db.execute(
        select(func.max(sub.c.u), func.count()).select_from(sub)
    ).one()
    if not cuantas:
        return None
    return (maximo, int(cuantas))


def _leer_catalogo(db: Session, team_id: int, producto_id: int) -> Optional[Catalogo]:
    producto = (
        db.query(models.BotProducto)
        .filter(
            models.BotProducto.id == producto_id,
            models.BotProducto.team_id == team_id,
        )
        .first()
    )
    if producto is None:
        return None

    variantes = tuple(
        Variante(
            id=v.id,
            slug=v.slug,
            nombre=v.nombre,
            instrucciones=v.instrucciones,
            atributos=dict(v.atributos or {}),
            precios_de_variante_id=v.precios_de_variante_id,
            activo=bool(v.activo),
            orden=int(v.orden or 0),
        )
        for v in db.query(models.BotProductoVariante)
        .filter(models.BotProductoVariante.producto_id == producto_id)
        .order_by(
            models.BotProductoVariante.orden, models.BotProductoVariante.id
        )
        .all()
    )
    filas = tuple(
        Fila(
            id=f.id,
            variante_id=int(f.variante_id or 0),
            tipo=f.tipo,
            etiqueta=f.etiqueta or "",
            inicio=f.inicio,
            fin=f.fin,
            valores=dict(f.valores or {}),
            nota=f.nota,
            orden=int(f.orden or 0),
        )
        for f in db.query(models.BotProductoFila)
        .filter(
            models.BotProductoFila.producto_id == producto_id,
            models.BotProductoFila.activo.is_(True),
        )
        .order_by(models.BotProductoFila.orden, models.BotProductoFila.id)
        .all()
    )
    medios = tuple(
        Medio(
            id=m.id,
            variante_id=int(m.variante_id or 0),
            clave=m.clave,
            url=m.url,
            tipo=m.tipo,
            descripcion=m.descripcion,
            aplica=dict(m.aplica or {}),
        )
        for m in db.query(models.BotProductoMedio)
        .filter(models.BotProductoMedio.producto_id == producto_id)
        .order_by(models.BotProductoMedio.id)
        .all()
    )
    alias = tuple(
        (a.nivel, _sin_tildes(a.alias), int(a.ref_id or 0))
        for a in db.query(models.BotProductoAlias)
        .filter(models.BotProductoAlias.producto_id == producto_id)
        .order_by(models.BotProductoAlias.id)
        .all()
    )
    return Catalogo(
        producto_id=producto.id,
        team_id=producto.team_id,
        slug=producto.slug,
        nombre=producto.nombre,
        tipo=producto.tipo,
        estado=producto.estado,
        resumen=producto.resumen,
        instrucciones=producto.instrucciones,
        atributos=dict(producto.atributos or {}),
        vigencia_desde=producto.vigencia_desde,
        vigencia_hasta=producto.vigencia_hasta,
        variantes=variantes,
        filas=filas,
        medios=medios,
        alias=alias,
    )


def cargar_catalogo(
    db: Session,
    *,
    team_id: Optional[int],
    producto_id: int,
    bot_id: Optional[int] = None,
) -> Optional[Catalogo]:
    """El catálogo de un producto de esa cuenta, de la caché o de la base."""
    if team_id is None:
        logger.warning(
            "productos: se pidió el catálogo sin team_id (bot_id=%s, "
            "producto_id=%s); se devuelve vacío",
            bot_id, producto_id,
        )
        return None

    clave = (int(team_id), int(producto_id))
    ahora = time.monotonic()
    entrada = _CACHE.get(clave)
    if entrada is not None and (ahora - entrada.revisado) < TTL_SEGUNDOS:
        return entrada.catalogo

    sello = _sello(db, team_id, producto_id)
    if sello is None:
        _CACHE.pop(clave, None)
        return None
    if entrada is not None and entrada.sello == sello:
        entrada.revisado = ahora
        return entrada.catalogo

    catalogo = _leer_catalogo(db, team_id, producto_id)
    if catalogo is None:
        _CACHE.pop(clave, None)
        return None
    _CACHE[clave] = _Entrada(catalogo=catalogo, sello=sello, revisado=ahora)
    return catalogo


# ---------------------------------------------------------------------------
# Qué ve cada bot
# ---------------------------------------------------------------------------

def catalogos_de_bot(
    db: Session, *, team_id: Optional[int], bot_id: Optional[int] = None
) -> List[Catalogo]:
    """Los productos publicados que ese bot puede vender.

    Con `bot_id`, el producto además tiene que estar enganchado y activo en
    `bot_producto_bots` — que es para lo que existe esa tabla: un bot de
    soporte no cotiza el catálogo.
    """
    if team_id is None:
        logger.warning(
            "productos: se pidieron los productos sin team_id (bot_id=%s); "
            "se devuelve vacío",
            bot_id,
        )
        return []

    consulta = db.query(models.BotProducto).filter(
        models.BotProducto.team_id == team_id,
        models.BotProducto.estado == models.PRODUCTO_ESTADO_PUBLICADO,
    )
    orden = [models.BotProducto.id]
    if bot_id is not None:
        consulta = consulta.join(
            models.BotProductoBot,
            models.BotProductoBot.producto_id == models.BotProducto.id,
        ).filter(
            models.BotProductoBot.bot_id == bot_id,
            models.BotProductoBot.activo.is_(True),
        )
        orden = [models.BotProductoBot.orden] + orden
    ids = [p.id for p in consulta.order_by(*orden).all()]

    fuera = []
    for producto_id in ids:
        catalogo = cargar_catalogo(
            db, team_id=team_id, producto_id=producto_id, bot_id=bot_id
        )
        if catalogo is not None:
            fuera.append(catalogo)
    return fuera


def resolver_producto(
    db: Session,
    *,
    team_id: Optional[int],
    bot_id: Optional[int] = None,
    texto: str = "",
) -> Optional[Catalogo]:
    """El producto que nombró el modelo: por slug, por alias, o el único.

    Sin texto y con un solo producto visible, ese. Con varios, `None`: adivinar
    cuál es exactamente la clase de error que este esquema viene a cerrar.
    """
    catalogos = catalogos_de_bot(db, team_id=team_id, bot_id=bot_id)
    if not catalogos:
        return None
    limpio = _sin_tildes(texto)
    if not limpio:
        return catalogos[0] if len(catalogos) == 1 else None

    for catalogo in catalogos:
        if _sin_tildes(catalogo.slug) == limpio or _sin_tildes(catalogo.nombre) == limpio:
            return catalogo
    for catalogo in catalogos:
        for nivel, alias, ref_id in catalogo.alias:
            if nivel == models.ALIAS_NIVEL_PRODUCTO and alias == limpio:
                return catalogo
    # Por contención: "el plan de cove", "quiero el sirope de mora".
    for catalogo in catalogos:
        for nivel, alias, ref_id in catalogo.alias:
            if nivel == models.ALIAS_NIVEL_PRODUCTO and alias and alias in limpio:
                return catalogo
    return None


def resolver_variante(catalogo: Catalogo, texto: str) -> Optional[Variante]:
    """La variante que nombró el cliente, por slug, nombre o alias.

    Primero exacto y después por contención, en el orden en que se cargaron los
    alias: «en el de la esquina por favor» tiene que resolver igual que «el de
    la esquina». Los alias de otra cuenta no llegan hasta acá: el catálogo ya
    viene filtrado por `team_id`.
    """
    limpio = _sin_tildes(texto)
    if not limpio:
        return None
    activas = catalogo.activas
    for v in activas:
        if _sin_tildes(v.slug) == limpio or _sin_tildes(v.nombre) == limpio:
            return v
    for nivel, alias, ref_id in catalogo.alias:
        if nivel == models.ALIAS_NIVEL_VARIANTE and alias == limpio:
            variante = catalogo.variante(ref_id)
            if variante is not None and variante.activo:
                return variante
    for nivel, alias, ref_id in catalogo.alias:
        if nivel == models.ALIAS_NIVEL_VARIANTE and alias and alias in limpio:
            variante = catalogo.variante(ref_id)
            if variante is not None and variante.activo:
                return variante
    return None


# ---------------------------------------------------------------------------
# Filas: de quién son, cuáles siguen vigentes, cómo se ordenan
# ---------------------------------------------------------------------------

def vigente(catalogo: Catalogo, hoy: Optional[date] = None) -> bool:
    """¿El producto entero está dentro de su ventana de vigencia?

    Un producto publicado pero fuera de ventana (una campaña de temporada que
    ya cerró) no se le nombra al modelo: mencionarlo es invitarlo a ofrecerlo.
    Sin ventana declarada, siempre vigente.
    """
    hoy = hoy or hoy_colombia()
    if catalogo.vigencia_desde is not None and hoy < catalogo.vigencia_desde:
        return False
    if catalogo.vigencia_hasta is not None and hoy > catalogo.vigencia_hasta:
        return False
    return True


def origen_de_precios(catalogo: Catalogo, variante: Variante) -> Variante:
    """La variante de la que salen los precios de ésta.

    `precios_de_variante_id` es una auto-FK: dos variantes que comparten tabla
    no la duplican. Los ciclos (A apunta a B y B a A) se cortan acá y no en la
    base: un ciclo es un error de datos del cliente, no algo que deba tumbar el
    turno del bot colgándolo en un `while`.
    """
    vista = {variante.id}
    actual = variante
    while actual.precios_de_variante_id:
        siguiente = catalogo.variante(actual.precios_de_variante_id)
        if siguiente is None or siguiente.id in vista:
            if siguiente is not None:
                logger.warning(
                    "productos: ciclo de precios_de_variante_id en el producto "
                    "%s (variante %s)",
                    catalogo.producto_id, variante.id,
                )
            break
        vista.add(siguiente.id)
        actual = siguiente
    return actual


def _orden_fila(fila: Fila) -> Tuple[Any, ...]:
    return (fila.inicio is None, fila.inicio or date.min, fila.orden, fila.id)


def filas_vigentes(
    catalogo: Catalogo,
    *,
    variante: Optional[Variante] = None,
    mes: Optional[int] = None,
    hoy: Optional[date] = None,
    tope: Optional[int] = None,
) -> List[Fila]:
    """Las filas que todavía se pueden ofrecer, de la más próxima a la lejana.

    El filtro por `hoy` **no es opcional**: un mínimo calculado sobre una fila
    vencida es otra forma de citarle al cliente algo que no se le puede vender.
    Una fila sin fecha (una lista de precios, una sede) no vence nunca.
    """
    hoy = hoy or hoy_colombia()
    if variante is not None:
        dueña = origen_de_precios(catalogo, variante)
        candidatas = [
            f for f in catalogo.filas
            if f.variante_id in (dueña.id, models.REF_TODAS)
        ]
    else:
        candidatas = list(catalogo.filas)

    fuera = []
    for fila in candidatas:
        if mes is not None and (fila.inicio is None or fila.inicio.month != mes):
            continue
        vence = fila.fin or fila.inicio
        if vence is not None and vence < hoy:
            continue
        fuera.append(fila)
    fuera.sort(key=_orden_fila)
    return fuera[:tope] if tope else fuera


def _clave_precio(catalogo: Catalogo) -> str:
    plantillas = catalogo.plantillas
    return str(plantillas.get("precio", PLANTILLA["precio"]))


def _precio(catalogo: Catalogo, fila: Fila) -> Optional[float]:
    valor = (fila.valores or {}).get(_clave_precio(catalogo))
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def _mas_barata(catalogo: Catalogo, filas: Sequence[Fila]) -> Optional[Fila]:
    """La fila más económica según la columna de precio declarada.

    Los empates los rompe la fecha y después el orden de carga, que es lo mismo
    que hacía el `min` sobre una lista ya ordenada por fecha.
    """
    con_precio = [(f, _precio(catalogo, f)) for f in filas]
    con_precio = [(f, p) for f, p in con_precio if p is not None]
    if not con_precio:
        return None
    return min(
        con_precio,
        key=lambda fp: (fp[1], fp[0].inicio or date.min, fp[0].orden, fp[0].id),
    )[0]


def _subgrupo(catalogo: Catalogo, filas: Sequence[Fila]) -> List[Fila]:
    """El subconjunto del que el producto quiere informar aparte.

    Hoy la única regla es por día de la semana (`dias_semana`, 0 = lunes), que
    es calendario y no negocio. Sin `subgrupo` declarado, no hay subconjunto.
    """
    config = catalogo.plantillas.get("subgrupo") or PLANTILLA["subgrupo"]
    dias = config.get("dias_semana") if isinstance(config, dict) else None
    if not dias:
        return []
    permitidos = {int(d) for d in dias}
    return [
        f for f in filas
        if f.inicio is not None and f.inicio.weekday() in permitidos
    ]


def clave_medio(
    catalogo: Catalogo, variante: Optional[Variante], mes: Optional[int]
) -> Optional[Tuple[str, Optional[Variante]]]:
    """La clave del medio que ilustra ese período, y de quién se tomó prestado.

    Si la variante no tiene medio propio para el período, se cae a la variante
    de la que toma los precios: dos versiones que comparten tabla suelen
    compartir también la foto. El segundo elemento es esa variante prestadora
    (o `None` si el medio es suyo), y es lo que le permite al producto avisar
    que la imagen sale a nombre de otra cosa.
    """
    if mes is None:
        return None
    objetivos: List[Tuple[int, Optional[Variante]]] = []
    if variante is None:
        objetivos.append((models.REF_TODAS, None))
    else:
        objetivos.append((variante.id, None))
        dueña = origen_de_precios(catalogo, variante)
        if dueña.id != variante.id:
            objetivos.append((dueña.id, dueña))
        objetivos.append((models.REF_TODAS, None))

    for variante_id, prestadora in objetivos:
        for medio in catalogo.medios:
            if medio.variante_id != variante_id:
                continue
            meses = (medio.aplica or {}).get("meses")
            if isinstance(meses, list) and mes in meses:
                return medio.clave, prestadora
    return None


def rango_publicado(catalogo: Catalogo) -> Optional[Tuple[date, date]]:
    """(primera, última) fecha de arranque publicada, vencidas incluidas."""
    fechas = [f.inicio for f in catalogo.filas if f.inicio is not None]
    return (min(fechas), max(fechas)) if fechas else None


def resolver_fecha(
    catalogo: Catalogo, fecha: date, mes: Optional[int], hoy: date
) -> date:
    """Corrige el año cuando el modelo manda una fecha que ya pasó.

    El modelo no sabe en qué año vive: al pedirle una fecha exacta escribe
    `2025-01-15` para «el 15 de enero» y la consulta le responde «eso ya pasó» a
    un cliente que quería enero del año entrante. Una fecha en el pasado nunca
    es una petición válida, así que se reinterpreta el año.

    Solo se toca lo que está demostrablemente mal: una fecha futura se respeta
    tal cual. Y si ninguna reinterpretación cae dentro de lo publicado, se
    devuelve la original para que la consulta responda «ya pasó» — que en ese
    caso es la verdad y no un error de año.
    """
    if fecha >= hoy:
        return fecha

    dia, m = fecha.day, (mes or fecha.month)
    rango = rango_publicado(catalogo)
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


# ---------------------------------------------------------------------------
# Redacción del resultado
# ---------------------------------------------------------------------------

def _datos_fila(
    catalogo: Catalogo,
    fila: Fila,
    *,
    variante: Optional[Variante] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """El contexto con el que se renderiza una fila.

    Cada columna de `valores` entra con su nombre, y las numéricas además con
    `<columna>_pesos` ya formateada. Ninguna cifra se escribe a mano en este
    módulo: todas salen de acá.
    """
    plantillas = catalogo.plantillas
    datos: Dict[str, Any] = {}
    resumen = []
    # Ordenado por nombre de columna, y no como venga: JSONB **no** conserva el
    # orden en que se insertaron las claves (las reordena por longitud y bytes),
    # así que un `{valores}` en orden de llegada se vería de una forma en la
    # suite (SQLite) y de otra en producción. Aplica solo al volcado genérico;
    # un producto que quiera su propio orden nombra sus columnas en la plantilla.
    for k, v in sorted((fila.valores or {}).items()):
        datos[k] = v
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            datos[f"{k}_pesos"] = _pesos(v)
        resumen.append(f"{k}: {v}")
    datos["valores"] = ", ".join(resumen)
    datos["etiqueta"] = fila.etiqueta or ""
    datos["inicio"] = fila.inicio.isoformat() if fila.inicio else ""
    datos["fin"] = fila.fin.isoformat() if fila.fin else ""
    datos["nota"] = fila.nota or ""
    datos["producto"] = catalogo.nombre
    datos["variante"] = variante.nombre if variante is not None else ""
    datos["periodo"] = _NOMBRE_MES[fila.inicio.month] if fila.inicio else ""
    datos["duracion"] = _fmt(plantillas, "duracion", datos)
    datos["obs"] = _opcional(plantillas, "nota_fila", datos)
    datos["marca"] = ""
    datos["cabe"] = ""
    if extra:
        datos.update(extra)
    return datos


def _periodos_con_filas(
    catalogo: Catalogo, variante: Variante, hoy: date
) -> List[int]:
    return [
        m for m in _meses_por_cercania(hoy)
        if filas_vigentes(catalogo, variante=variante, mes=m, hoy=hoy)
    ]


def meses_por_cercania(hoy: Optional[date] = None) -> List[int]:
    """Los 12 períodos desde el actual hacia adelante. Público, ver arriba."""
    return _meses_por_cercania(hoy or hoy_colombia())


def periodos_con_filas(
    catalogo: Catalogo,
    *,
    variante: Optional[Variante] = None,
    hoy: Optional[date] = None,
) -> List[int]:
    """Los períodos que todavía tienen algo que ofrecer, del más próximo al
    más lejano. Sin `variante`, los del producto entero."""
    hoy = hoy or hoy_colombia()
    return [
        m for m in _meses_por_cercania(hoy)
        if filas_vigentes(catalogo, variante=variante, mes=m, hoy=hoy)
    ]


def texto_de(catalogo: Optional[Catalogo], clave: str, **datos: Any) -> str:
    """Renderiza una plantilla del producto (o la del módulo si no la pisa).

    Es el acceso público a la redacción: quien le habla al modelo desde fuera
    de este archivo no escribe el texto a mano, lo pide por su clave. Así el
    cliente que quiera decirlo con su voz lo sigue haciendo desde sus datos.
    """
    plantillas = catalogo.plantillas if catalogo is not None else {}
    return _fmt(plantillas, clave, datos)


def _bloque_variante(
    catalogo: Catalogo,
    variante: Variante,
    mes: int,
    fecha: Optional[date],
    hoy: date,
) -> List[str]:
    plantillas = catalogo.plantillas
    filas = filas_vigentes(catalogo, variante=variante, mes=mes, hoy=hoy)
    base = {
        "producto": catalogo.nombre,
        "variante": variante.nombre,
        "periodo": _NOMBRE_MES[mes],
        "hoy": hoy.isoformat(),
    }
    lineas: List[str] = []

    if not filas:
        lineas.append(_fmt(plantillas, "vacio", base))
        disponibles = [_NOMBRE_MES[m] for m in _periodos_con_filas(catalogo, variante, hoy)]
        if disponibles:
            lineas.append(
                _fmt(plantillas, "vacio_periodos", {**base, "periodos": ", ".join(disponibles)})
            )
        lineas.append(_fmt(plantillas, "vacio_cierre", base))
        return [l for l in lineas if l]

    tope = int(plantillas.get("tope_bloque", PLANTILLA["tope_bloque"]))
    mostradas = filas[:tope] if tope else filas
    lineas.append(_fmt(plantillas, "bloque_titulo", {**base, "n": len(filas)}))
    for fila in mostradas:
        marca = (
            _fmt(plantillas, "fila_marcada", base)
            if fecha is not None and fila.inicio == fecha
            else ""
        )
        lineas.append(
            _fmt(
                plantillas,
                "fila",
                _datos_fila(catalogo, fila, variante=variante, extra={"marca": marca}),
            )
        )
    if len(filas) > len(mostradas):
        lineas.append(
            _fmt(plantillas, "bloque_tope", {**base, "n": len(filas) - len(mostradas)})
        )

    if fecha is not None and not any(f.inicio == fecha for f in filas):
        # Una por fecha de arranque: varias filas pueden empezar el mismo día, y
        # sin deduplicar «las dos más cercanas» terminan siendo el mismo día
        # ofrecido dos veces.
        por_inicio: Dict[Any, Fila] = {}
        for f in filas:
            por_inicio.setdefault(f.inicio, f)
        cercanas = sorted(
            por_inicio.values(),
            key=lambda f: abs((f.inicio - fecha).days) if f.inicio else 10**6,
        )[:2]
        lineas.append(
            _fmt(
                plantillas,
                "fecha_sin_fila",
                {
                    **base,
                    "fecha": fecha.isoformat(),
                    "cercanas": " y ".join(
                        _fmt(
                            plantillas,
                            "fila_cercana",
                            _datos_fila(catalogo, f, variante=variante),
                        )
                        for f in cercanas
                    ),
                },
            )
        )

    medio = clave_medio(catalogo, variante, mes)
    if medio is not None:
        clave, prestadora = medio
        lineas.append(_fmt(plantillas, "medio", {**base, "clave": clave}))
        if prestadora is not None:
            nota = variante.atributos.get("nota_medio_prestado")
            if nota:
                lineas.append(
                    _fmt(
                        {"nota_medio_prestado": nota},
                        "nota_medio_prestado",
                        {**base, "clave": clave, "origen": prestadora.nombre},
                    )
                )
    return [l for l in lineas if l]


def _grupos_de_precio(catalogo: Catalogo) -> List[Tuple[Variante, List[Variante]]]:
    """Las variantes agrupadas por quién les pone el precio.

    El «desde» se cotiza una vez por tabla de precios, no una por variante: dos
    variantes que comparten tarifa comparten también su mínimo, y repetirlo
    dos veces invita al modelo a leerlos como dos ofertas distintas.
    """
    grupos: Dict[int, List[Variante]] = {}
    for v in catalogo.activas:
        dueña = origen_de_precios(catalogo, v)
        grupos.setdefault(dueña.id, []).append(v)
    fuera = []
    for dueña_id, miembros in grupos.items():
        dueña = catalogo.variante(dueña_id)
        if dueña is None:
            continue
        miembros = sorted(miembros, key=lambda v: (v.orden, v.id))
        fuera.append((dueña, miembros))
    return sorted(fuera, key=lambda g: (g[0].orden, g[0].id))


def _lineas_desde(
    catalogo: Catalogo,
    dueña: Variante,
    miembros: Sequence[Variante],
    mes: Optional[int],
    hoy: date,
) -> List[str]:
    """El «desde» del ámbito consultado, calculado de las filas que siguen vivas.

    Éste es el arreglo del bug del Sprint 24 traído tal cual: el mínimo que se
    cita tiene que ser el del ámbito que el cliente pidió, con su fila al lado
    para que no se pueda despegar de él. Un «desde» de otro período —o peor, uno
    fijo en el código— es una cotización que revienta cuando el cliente va a
    pagar.
    """
    plantillas = catalogo.plantillas
    filas = filas_vigentes(catalogo, variante=dueña, mes=mes, hoy=hoy)
    barata = _mas_barata(catalogo, filas)
    if barata is None:
        return []

    ambito = (
        _NOMBRE_MES[mes] if mes is not None
        else str(plantillas.get("ambito_global", PLANTILLA["ambito_global"]))
    )
    grupo = _lista_y([v.nombre for v in miembros])
    coletilla = str(dueña.atributos.get("coletilla_desde") or "")
    clave_precio = _clave_precio(catalogo)
    datos = _datos_fila(
        catalogo, barata, variante=dueña,
        extra={"ambito": ambito, "grupo": grupo, "coletilla": coletilla},
    )
    datos["precio"] = _pesos(_precio(catalogo, barata) or 0)
    lineas = [
        _fmt(plantillas, "desde_periodo" if mes is not None else "desde_global", datos)
    ]

    subgrupo = _subgrupo(catalogo, filas)
    barata_sub = _mas_barata(catalogo, subgrupo)
    if barata_sub is not None:
        sub = _datos_fila(
            catalogo, barata_sub, variante=dueña,
            extra={
                "ambito": ambito, "grupo": grupo, "coletilla": coletilla,
                "n": len(subgrupo),
            },
        )
        sub["precio"] = _pesos(_precio(catalogo, barata_sub) or 0)
        lineas.append(_fmt(plantillas, "subgrupo_con", sub))
    else:
        lineas.append(
            _fmt(
                plantillas,
                "subgrupo_sin",
                {
                    "ambito": ambito, "grupo": grupo, "coletilla": coletilla,
                    "producto": catalogo.nombre, "variante": dueña.nombre,
                    "periodo": ambito, "n": 0,
                },
            )
        )
    return [l for l in lineas if l]


def _bloque_presupuesto(
    catalogo: Catalogo,
    variantes: Sequence[Variante],
    tope: int,
    mes: Optional[int],
    hoy: date,
) -> List[str]:
    """Búsqueda inversa: de un presupuesto a las filas que caben en él.

    El sentido natural es período → precios, pero media clientela pregunta al
    revés («tengo 450 mil, ¿qué me alcanza?»). Casi ninguna pregunta trae un
    precio exacto, así que se busca por techo y no por igualdad. Y si no cabe
    **nada**, no se responde con una lista vacía: se ofrece lo más económico
    que sí existe. Misma filosofía que la fecha sin fila — dejar al cliente sin
    opciones es como se pierde la venta.
    """
    plantillas = catalogo.plantillas
    ambito = (
        _NOMBRE_MES[mes] if mes is not None
        else str(plantillas.get(
            "presupuesto_ambito_global", PLANTILLA["presupuesto_ambito_global"]
        ))
    )
    base = {
        "producto": catalogo.nombre,
        "ambito": ambito,
        "tope": _pesos(tope),
        "hoy": hoy.isoformat(),
    }
    candidatas: List[Tuple[Variante, Fila]] = [
        (v, f)
        for v in variantes
        for f in filas_vigentes(catalogo, variante=v, mes=mes, hoy=hoy)
    ]
    caben = sorted(
        [
            (v, f) for v, f in candidatas
            if (_precio(catalogo, f) or 0) <= tope and _precio(catalogo, f) is not None
        ],
        key=lambda vf: (_precio(catalogo, vf[1]), vf[1].inicio or date.min),
    )

    lineas = [_fmt(plantillas, "presupuesto_titulo", base)]

    def _linea(variante: Variante, fila: Fila) -> str:
        datos = _datos_fila(catalogo, fila, variante=variante, extra=base)
        # Una fila puede caber por la columna que se compara y pasarse por otra
        # (la versión más cara de lo mismo). Cada columna numérica trae su
        # propio `<columna>_cabe` para que el producto lo diga donde quiera.
        for columna, valor in (fila.valores or {}).items():
            if isinstance(valor, bool) or not isinstance(valor, (int, float)):
                continue
            datos[f"{columna}_cabe"] = _fmt(
                plantillas, "cabe_si" if valor <= tope else "cabe_no", base
            )
        datos["cabe"] = datos.get(f"{_clave_precio(catalogo)}_cabe", "")
        return _fmt(plantillas, "fila_presupuesto", datos)

    if not caben:
        lineas.append(_fmt(plantillas, "presupuesto_nada", base))
        barata = _mas_barata(catalogo, [f for _, f in candidatas])
        if barata is not None:
            variante_barata = next(v for v, f in candidatas if f is barata)
            lineas.append(_fmt(plantillas, "presupuesto_nada_mejor", base))
            lineas.append(_linea(variante_barata, barata))
        if mes is not None:
            # Que no alcance en un período no quiere decir que no alcance nunca.
            # Se ofrece el cambio diciendo cuál, nunca colando el precio de otro
            # período dentro de éste.
            otras = [
                (v, f)
                for v in variantes
                for f in filas_vigentes(catalogo, variante=v, hoy=hoy)
                if (_precio(catalogo, f) is not None and _precio(catalogo, f) <= tope)
            ]
            barata_otra = _mas_barata(catalogo, [f for _, f in otras])
            if barata_otra is not None:
                datos = _datos_fila(catalogo, barata_otra, extra=base)
                datos["periodos"] = _lista_meses(
                    (f.inicio.month for _, f in otras if f.inicio), hoy
                )
                datos["precio"] = _pesos(_precio(catalogo, barata_otra) or 0)
                lineas.append(_fmt(plantillas, "presupuesto_otros", datos))
        return [l for l in lineas if l]

    tope_listado = int(plantillas.get("tope_listado", PLANTILLA["tope_listado"]))
    mostradas = caben[:tope_listado] if tope_listado else caben
    lineas.append(
        _fmt(
            plantillas,
            "presupuesto_si_tope" if len(caben) > len(mostradas) else "presupuesto_si",
            {**base, "total": len(caben), "n": len(mostradas)},
        )
    )
    for variante, fila in mostradas:
        lineas.append(_linea(variante, fila))
    if len(caben) > len(mostradas):
        restantes = caben[len(mostradas):]
        lineas.append(
            _fmt(
                plantillas,
                "presupuesto_restantes",
                {
                    **base,
                    "n": len(restantes),
                    "precio": _pesos(_precio(catalogo, restantes[-1][1]) or 0),
                    "periodos": _lista_meses(
                        (f.inicio.month for _, f in restantes if f.inicio), hoy
                    ),
                },
            )
        )
    if mes is None:
        lineas.append(_fmt(plantillas, "presupuesto_cierre_sin_periodo", base))
    return [l for l in lineas if l]


# ---------------------------------------------------------------------------
# La consulta que ve el modelo
# ---------------------------------------------------------------------------

def consultar(
    db: Session,
    *,
    team_id: Optional[int],
    bot_id: Optional[int] = None,
    producto: str = "",
    variante: str = "",
    mes: str = "",
    fecha: str = "",
    presupuesto: str = "",
    hoy: Optional[date] = None,
) -> str:
    """El texto que se le devuelve al modelo cuando consulta el catálogo."""
    hoy = hoy or hoy_colombia()

    if team_id is None:
        logger.warning(
            "productos: consulta sin team_id (bot_id=%s); se devuelve vacío",
            bot_id,
        )
        return str(PLANTILLA["sin_datos"])

    catalogo = resolver_producto(db, team_id=team_id, bot_id=bot_id, texto=producto)
    if catalogo is None:
        catalogos = catalogos_de_bot(db, team_id=team_id, bot_id=bot_id)
        if not catalogos:
            return str(PLANTILLA["sin_datos"])
        # Con varios productos y ninguno nombrado no se adivina: contestar por
        # el primero es venderle al cliente algo que no preguntó.
        return _fmt(
            catalogos[0].plantillas,
            "falta_producto" if not producto else "producto_desconocido",
            {
                "texto": producto,
                "productos": _lista_y([c.nombre for c in catalogos]),
            },
        )

    plantillas = catalogo.plantillas
    base = {"producto": catalogo.nombre, "hoy": hoy.isoformat()}

    # Un producto sin nada vigente NO se redacta: se escala. Un bot sin datos
    # improvisa, y lo que improvisa se parece a una cotización.
    if not filas_vigentes(catalogo, hoy=hoy):
        return _fmt(plantillas, "sin_datos", base)

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
    con_fechas = any(f.inicio is not None for f in catalogo.filas)
    if con_fechas and num_mes is None and tope is None:
        # Sin período no se adivina: cada período tiene su propio «desde» y
        # responder con el de todo el catálogo es justo el bug que costó una
        # cotización. Un producto sin fechas (una lista de precios, unas sedes)
        # no necesita período y no pasa por acá.
        return _fmt(plantillas, "sin_periodo", base)

    aviso_vencido = ""
    if fecha_pedida is not None:
        resuelta = resolver_fecha(catalogo, fecha_pedida, num_mes, hoy)
        if resuelta != fecha_pedida:
            fecha_pedida = resuelta
            num_mes = resuelta.month
        elif fecha_pedida < hoy:
            # Ya pasó de verdad (no es un año mal escrito). Se avisa, pero NO se
            # corta: abajo van igual las filas que quedan en ese período, que es
            # lo que el cliente necesita para elegir otra.
            aviso_vencido = _fmt(
                plantillas, "aviso_vencido", {**base, "fecha": fecha_pedida.isoformat()}
            )
            fecha_pedida = None

    elegida = resolver_variante(catalogo, variante) if variante else None
    if variante and elegida is None:
        return _fmt(
            plantillas,
            "variante_desconocida",
            {
                **base,
                "texto": variante,
                "variantes": _lista_y([v.nombre for v in catalogo.activas]),
            },
        )

    # Sin variante explícita se comparan las que tienen tabla propia: es lo que
    # el cliente quiere saber cuando pregunta «¿cuánto vale?» a secas. Las que
    # copian su precio de otra no se listan aparte (se dice abajo que cuestan
    # lo mismo), porque duplicarlas se lee como dos ofertas distintas.
    if elegida is not None:
        variantes = [elegida]
    else:
        variantes = [
            v for v in catalogo.activas
            if origen_de_precios(catalogo, v).id == v.id
        ]

    partes: List[str] = _fmt_lista(plantillas, "encabezado", base)
    if aviso_vencido:
        partes.append(aviso_vencido)
    if num_mes is not None:
        for v in variantes:
            partes.extend(_bloque_variante(catalogo, v, num_mes, fecha_pedida, hoy))

    if elegida is None:
        for v in catalogo.activas:
            dueña = origen_de_precios(catalogo, v)
            if dueña.id == v.id:
                continue
            partes.append(
                _fmt(
                    plantillas,
                    "nota_precios_compartidos",
                    {**base, "variante": v.nombre, "origen": dueña.nombre},
                )
            )

    if tope is not None:
        partes.extend(_bloque_presupuesto(catalogo, variantes, tope, num_mes, hoy))

    # El «desde» solo se menciona si ese ámbito tiene filas publicadas. Si se
    # agregara siempre, el modelo lo lee como prueba de que el período «sí
    # tiene» — y le ofrece al cliente un período vacío.
    con_filas = [
        v for v in variantes
        if filas_vigentes(catalogo, variante=v, mes=num_mes, hoy=hoy)
    ]
    for dueña, miembros in _grupos_de_precio(catalogo):
        ids = {v.id for v in miembros}
        if any(v.id in ids for v in con_filas):
            partes.extend(_lineas_desde(catalogo, dueña, miembros, num_mes, hoy))

    partes.extend(_fmt_lista(plantillas, "cierre", base))
    return "\n".join([p for p in partes if p])
