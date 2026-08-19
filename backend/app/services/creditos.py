"""Catálogo de paquetes de mensajes: cuánto cuestan, cuánto se cobran y por qué.

El catálogo vive **en código y no en la base** a propósito. Son dos paquetes
fijos y el precio se recalcula cuando cambia el costo del proveedor, la TRM o
la comisión de la pasarela; teniéndolo acá, cada cambio de precio queda en un
diff revisable con su justificación al lado, en vez de ser un `UPDATE` a mano
en producción que nadie puede reconstruir seis meses después.

===========================================================================
DE DÓNDE SALE EL PRECIO
===========================================================================

Un mensaje de campaña le cuesta a Gloma **dos peajes**, y venderlo le cuesta
un **tercero** que se lleva la pasarela:

1. **Meta** cobra el fee de la plantilla, por mensaje entregado, según el país
   del destinatario y la categoría. Las campañas de envío masivo son plantillas
   de *marketing*, que es la categoría cara.
2. **Twilio** (nuestro BSP) cobra su propio fee por mensaje encima del de Meta.
3. **Wompi** se queda con su comisión de cada recaudo.

Los tres están abajo como constantes con su fuente y su fecha.

**El precio hace gross-up de la comisión de Wompi, no se la suma por encima.**
La diferencia importa: si uno cobra `costo + margen` y encima le suma la
comisión, la comisión que Wompi realmente cobra se calcula sobre ese total
más grande, y el neto que llega queda corto. Acá se resuelve al revés: se
define el **neto objetivo** (`costo + margen`) y se despeja el bruto que hay
que cobrar para que, después de que Wompi se quede con lo suyo, quede
exactamente ese neto. Ver `_gross_up_wompi`.
"""
from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, TypedDict

# ---------------------------------------------------------------------------
# 1. Costo del mensaje
# ---------------------------------------------------------------------------

#: Fee de Meta por plantilla de MARKETING entregada en Colombia (USD).
#: Rate card de Colombia vigente desde el 2026-04-01.
#: Revisar cada trimestre: es el número más volátil de este archivo.
COSTO_META_USD_MARKETING_CO = 0.014

#: Fee de Twilio por mensaje (USD). Igual para todos los países y categorías;
#: va ENCIMA del fee de Meta, no en vez de.
COSTO_TWILIO_USD_POR_MENSAJE = 0.005

#: Costo directo de un mensaje de marketing a Colombia (USD).
#: 0.014 (Meta) + 0.005 (Twilio) = 0.019
COSTO_USD_POR_MENSAJE = COSTO_META_USD_MARKETING_CO + COSTO_TWILIO_USD_POR_MENSAJE

#: Para cuando se vendan paquetes de otra categoría: en Colombia una plantilla
#: de *utility* o de *authentication* le cuesta a Meta USD 0.0008, así que el
#: costo directo sería 0.0008 + 0.005 = **USD 0.0058 por mensaje** — menos de
#: un tercio del de marketing. Hoy no se vende ningún paquete así; la constante
#: queda documentada para que el día que se cotice no haya que volver a
#: investigar el rate card.
COSTO_USD_POR_MENSAJE_UTILITY = 0.0008 + COSTO_TWILIO_USD_POR_MENSAJE

# ---------------------------------------------------------------------------
# 2. La tasa de cambio
# ---------------------------------------------------------------------------

#: TRM con la que se calcularon los precios de lista (COP por USD).
#: Fuente: Superintendencia Financiera, TRM del 15–18 de agosto de 2026.
#:
#: HAY QUE REVISARLA. El peso se movió ~22% en un año: una TRM vieja no hace
#: que el precio se vea desactualizado, hace que el paquete se venda por
#: debajo del costo sin que nadie se entere, porque el costo está en dólares
#: y el precio en pesos. Cada vez que se toque este archivo, mirar la TRM del
#: día y, si se salió del rango, subirla y recalcular los precios en el mismo PR.
TRM_COP_POR_USD = 3128.65
TRM_FECHA = "2026-08-18"

# ---------------------------------------------------------------------------
# 3. El margen
# ---------------------------------------------------------------------------

#: Margen comercial sobre el costo directo del mensaje: 0.10 = 10%.
#:
#: **Fijado por el CEO el 19-ago-2026** (bajó del 30% que había puesto el
#: equipo técnico como valor provisional). Es la única cifra del cálculo que
#: no sale de una fuente oficial: Meta y Twilio publican sus tarifas, la
#: Superfinanciera publica la TRM y Wompi publica su comisión.
#:
#: Con 10% el margen queda ajustado: es lo que sobra para cubrir lo que NO
#: está en el costo directo (infraestructura AWS, tokens del bot, soporte,
#: cartera). Y como el precio está atado a una TRM en mínimos de 7 años, una
#: subida del dólar se lo come rápido — ver la nota de `TRM_COP_POR_USD`.
MARGEN_COMERCIAL = 0.10

# ---------------------------------------------------------------------------
# 4. La comisión de la pasarela
# ---------------------------------------------------------------------------

#: Comisión de Wompi, **Plan Avanzado**: 2.65% del recaudo + $700 COP fijos,
#: y sobre esa comisión Wompi cobra IVA del 19%.
#:
#:     comision(bruto) = (0.0265 * bruto + 700) * 1.19
#:
#: Consultado 2026-08-19. Si el CEO cambia de plan (o Wompi cambia tarifas),
#: se tocan estas tres constantes y los precios se recalculan solos.
WOMPI_COMISION_PORCENTUAL = 0.0265
WOMPI_COMISION_FIJA_COP = 700.0
IVA_COLOMBIA = 0.19

#: A qué múltiplo (en COP) se redondea el precio de lista. Se redondea SIEMPRE
#: HACIA ARRIBA: hacia abajo el redondeo se comería parte del margen y podría
#: dejar el neto por debajo del objetivo, que es justo lo que el gross-up
#: existe para evitar.
REDONDEO_COP = 100


# ---------------------------------------------------------------------------
# El cálculo
# ---------------------------------------------------------------------------

def costo_cop_por_mensaje() -> float:
    """Costo directo de UN mensaje de marketing a Colombia, en pesos."""
    return COSTO_USD_POR_MENSAJE * TRM_COP_POR_USD


def comision_wompi(bruto_cop: float) -> float:
    """Lo que Wompi se queda de un recaudo de `bruto_cop` pesos (IVA incluido)."""
    return (WOMPI_COMISION_PORCENTUAL * bruto_cop + WOMPI_COMISION_FIJA_COP) * (
        1 + IVA_COLOMBIA
    )


def _gross_up_wompi(neto_objetivo_cop: float) -> float:
    """Cuánto hay que COBRAR para que, tras la comisión, queden `neto` pesos.

    Se despeja de `bruto - comision(bruto) = neto`:

        bruto - (p*bruto + f) * (1+iva) = neto
        bruto * (1 - p*(1+iva))         = neto + f*(1+iva)
        bruto = (neto + f*(1+iva)) / (1 - p*(1+iva))

    Con los números de hoy: `(neto + 833) / 0.968465`.
    """
    fija_con_iva = WOMPI_COMISION_FIJA_COP * (1 + IVA_COLOMBIA)
    factor = 1 - WOMPI_COMISION_PORCENTUAL * (1 + IVA_COLOMBIA)
    return (neto_objetivo_cop + fija_con_iva) / factor


#: Precio de lista de cada paquete, en pesos enteros.
#:
#: Lo fija el CEO en cifras cerradas y lo revisa cada semana; el cálculo de
#: `precio_sugerido_cop()` queda como referencia para saber si el precio sigue
#: cubriendo el costo. Antes esto se calculaba solo: se cambió porque un
#: precio que se mueve con la TRM da cifras como $80.653, imposibles de
#: comunicar y de cuadrar en la caja.
PRECIO_LISTA_COP: Dict[str, int] = {
    "mensajes_1000": 70_000,
    "mensajes_5000": 340_000,
}


def precio_sugerido_cop(mensajes: int) -> int:
    """Lo que costaría el paquete si se calculara: costo → +margen → gross-up.

    Ya no manda sobre el precio (ese lo pone `PRECIO_LISTA_COP`), pero sirve
    de alarma: si el precio de lista se queda por debajo de esto, el paquete
    dejó de dar el margen objetivo — típicamente porque subió el dólar.
    """
    costo = costo_cop_por_mensaje() * mensajes
    neto_objetivo = costo * (1 + MARGEN_COMERCIAL)
    bruto = _gross_up_wompi(neto_objetivo)
    return int(math.ceil(bruto / REDONDEO_COP) * REDONDEO_COP)


class Paquete:
    """Un paquete del catálogo, con su precio ya calculado.

    `amount_cents` es lo que exige Wompi: el monto SIEMPRE viaja en centavos
    de la moneda, también en COP (COP 80.700 → 8_070_000).
    """

    __slots__ = ("key", "nombre", "messages", "amount_cents", "currency", "descripcion")

    def __init__(self, key: str, nombre: str, messages: int, descripcion: str) -> None:
        self.key = key
        self.nombre = nombre
        self.messages = messages
        self.currency = "COP"
        self.amount_cents = PRECIO_LISTA_COP[key] * 100
        self.descripcion = descripcion

    @property
    def link_pago(self) -> Optional[str]:
        """Link de pago de Wompi creado a mano para este paquete, si lo hay.

        Es la alternativa al checkout por API: el CEO crea el link en el panel
        de Wompi (por el valor exacto de `amount_cop`) y lo pega en la variable
        de entorno `WOMPI_LINK_<KEY>` — por ejemplo `WOMPI_LINK_MENSAJES_1000`.

        **Un link de pago NO es un secreto**: es una página pública donde
        cualquiera puede pagar. Por eso va en una variable de entorno normal de
        la task-def y no en SSM, al revés que las llaves de la API.

        Si está vacío, el frontend cae al checkout por API (que sí necesita las
        llaves). Los dos caminos conviven a propósito: el link sirve desde el
        día uno sin credenciales, y el checkout por API es el que permite
        acreditar los mensajes solo.
        """
        return (
            os.environ.get(f"WOMPI_LINK_{self.key.upper()}")
            or LINKS_DE_PAGO.get(self.key)
        )

    # --- ayudas para pintar el precio sin que el frontend haga cuentas ---

    @property
    def amount_cop(self) -> int:
        """Precio en pesos enteros (sin centavos)."""
        return self.amount_cents // 100

    @property
    def precio_por_mensaje_cop(self) -> int:
        """Cuánto le sale al cliente cada mensaje de este paquete, en COP."""
        return round(self.amount_cop / self.messages)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return (
            f"<Paquete {self.key} mensajes={self.messages} "
            f"precio={self.amount_cop} COP>"
        )


class Desglose(TypedDict):
    """En qué se va cada peso del precio de un paquete.

    Todo en pesos enteros. Es para que el CEO pueda auditar el precio desde la
    pantalla, sin abrir el código:

        precio  −  comision_wompi  =  neto
        neto    −  costo           =  margen (la utilidad real)
    """

    package_key: str
    messages: int
    #: Lo que paga el cliente.
    precio_cop: int
    #: Costo directo de los mensajes (Meta + Twilio), a la TRM de `TRM_FECHA`.
    costo_cop: int
    #: Margen objetivo sobre el costo (el `MARGEN_COMERCIAL`), en pesos.
    margen_objetivo_cop: int
    #: Neto que se buscaba recibir: costo + margen objetivo.
    neto_objetivo_cop: int
    #: Lo que Wompi se queda de este recaudo, con IVA.
    comision_wompi_cop: int
    #: Lo que realmente le queda a Gloma tras la comisión.
    neto_real_cop: int
    #: Utilidad real = neto real − costo. Es ≥ margen objetivo por el redondeo.
    margen_real_cop: int
    #: El margen real como porcentaje del costo (0.30 = 30%).
    margen_real_pct: float
    #: Datos del cálculo, para que la pantalla pueda citarlos.
    trm: float
    trm_fecha: str
    costo_usd_por_mensaje: float


def desglose_paquete(key: str) -> Optional[Desglose]:
    """El detalle del precio de un paquete, o `None` si la `key` no existe.

    No recalcula el precio: parte del `amount_cents` publicado (que es el que
    de verdad se le cobra al cliente, ya redondeado) y desanda el camino. Así
    el desglose siempre cuadra con lo que se cobró, redondeo incluido.
    """
    p = paquete(key)
    if p is None:
        return None

    precio = float(p.amount_cop)
    costo = costo_cop_por_mensaje() * p.messages
    margen_objetivo = costo * MARGEN_COMERCIAL
    comision = comision_wompi(precio)
    neto_real = precio - comision

    return Desglose(
        package_key=p.key,
        messages=p.messages,
        precio_cop=int(precio),
        costo_cop=round(costo),
        margen_objetivo_cop=round(margen_objetivo),
        neto_objetivo_cop=round(costo + margen_objetivo),
        comision_wompi_cop=round(comision),
        neto_real_cop=round(neto_real),
        margen_real_cop=round(neto_real - costo),
        margen_real_pct=round((neto_real - costo) / costo, 4) if costo else 0.0,
        trm=TRM_COP_POR_USD,
        trm_fecha=TRM_FECHA,
        costo_usd_por_mensaje=COSTO_USD_POR_MENSAJE,
    )


# ---------------------------------------------------------------------------
# El catálogo
# ---------------------------------------------------------------------------
#
# Con los números de arriba (costo directo COP 59,44 por mensaje):
#
#   | paquete |    costo    | +30% (neto) | gross-up | precio de lista |
#   |---------|-------------|-------------|----------|-----------------|
#   | 1.000   | COP  59.444 | COP  77.277 |  80.653  | COP     80.700  |
#   | 5.000   | COP 297.222 | COP 386.389 | 399.830  | COP    399.900  |
#
# La tabla es ilustrativa: la fuente de verdad es el cálculo, y los tests
# verifican los precios contra él (y contra el gross-up), no contra estos
# comentarios.

#: Links de pago creados a mano en el panel de Wompi, uno por paquete.
#:
#: NO son secretos: son páginas públicas de cobro, así que viven en el código
#: y no en SSM. La variable de entorno `WOMPI_LINK_<KEY>` los pisa, para poder
#: cambiarlos sin desplegar.
#:
#: OJO al actualizarlos: el valor del link tiene que coincidir con
#: `PRECIO_LISTA_COP`. Si no coinciden, el cliente ve un precio en la app y
#: paga otro en Wompi.
LINKS_DE_PAGO: Dict[str, str] = {
    "mensajes_1000": "https://checkout.wompi.co/l/LXZc6o",
    "mensajes_5000": "https://checkout.wompi.co/l/a1sl2W",
}


_CATALOGO: List[Paquete] = [
    Paquete(
        key="mensajes_1000",
        nombre="1.000 mensajes",
        messages=1000,
        descripcion="Ideal para arrancar o para una campaña puntual.",
    ),
    Paquete(
        key="mensajes_5000",
        nombre="5.000 mensajes",
        messages=5000,
        descripcion="Para envíos recurrentes, con la comisión fija diluida.",
    ),
]

_POR_KEY: Dict[str, Paquete] = {p.key: p for p in _CATALOGO}


def catalogo() -> List[Paquete]:
    """Los paquetes a la venta, del más chico al más grande."""
    return list(_CATALOGO)


def paquete(key: str) -> Optional[Paquete]:
    """El paquete con esa `key`, o `None` si no existe.

    Devuelve `None` en vez de levantar: quien la llama viene de un input del
    usuario y tiene que traducir eso a un 404/422 propio.
    """
    return _POR_KEY.get((key or "").strip())
