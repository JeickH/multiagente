"""Facturas de la cuenta: el listado, el aviso de mora y el PDF.

Tres piezas que conviene no confundir, porque cada una tiene un público
distinto:

- **El listado y el pago** son de ADMINISTRADOR. Traen valores, conceptos y
  vencimientos, o sea las finanzas de la cuenta.
- **El aviso** lo ve cualquiera que entre a la plataforma, asesores incluidos.
  Por eso `debe_avisar()` devuelve un sí/no y una clave opaca, y nunca un
  monto ni un conteo: el asesor que atiende la bandeja no tiene por qué
  enterarse de cuánto debe su empleador.
- **El PDF** lo genera el administrador desde el listado.

De dónde sale "cuándo se genera la próxima factura"
---------------------------------------------------
De `subscriptions`, que ya lo sabe: `next_charge_at` es la fecha del siguiente
ciclo y `amount_cents` el valor del plan de esa cuenta. No se agregó columna
para esto. La suscripción de una cuenta que todavía no registró tarjeta queda
en `pending`, y una `pending` con `next_charge_at` puesta **no se cobra** — el
tick solo mira las `active` y `past_due` (`suscripciones._cobrar_vencidas`).
Así la fecha se puede anunciar sin que eso dispare un cobro.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .. import models
from .suscripciones import ZONA_COLOMBIA

logger = logging.getLogger(__name__)

#: Días de mora a partir de los cuales aparece el aviso amarillo.
#:
#: Se cuentan desde el **vencimiento** de la factura (`due_date`), no desde que
#: se emitió ni desde que el cliente la vio. El día que vence no hay mora: la
#: factura se puede pagar ese mismo día, así que el reloj arranca al día
#: siguiente. Con el umbral en 7, una factura vencida el 2 de septiembre avisa
#: desde el 9.
#:
#: Todo se compara en **fechas de Colombia**. El servidor guarda UTC, y en
#: Colombia (-05:00) las últimas cinco horas del día ya son del día siguiente
#: en UTC: comparar contra `datetime.utcnow().date()` adelantaría el aviso una
#: noche entera.
DIAS_PARA_AVISAR = 7


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

def hoy_colombia() -> date:
    """El día de hoy según el negocio, no según el reloj UTC del servidor."""
    return datetime.now(ZONA_COLOMBIA).date()


def dias_de_mora(factura: models.Invoice, *, hoy: Optional[date] = None) -> int:
    """Días vencidos de una factura. 0 o negativo si todavía no se vence."""
    return ((hoy or hoy_colombia()) - factura.due_date).days


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

def listar(db: Session, team_id: int, *, limite: int = 200) -> List[models.Invoice]:
    """Las facturas de la cuenta: primero lo que se debe, después lo pagado.

    El orden lo decide el estado y no la fecha, porque lo que el
    administrador abre a buscar es lo que tiene que pagar. Dentro de las
    pendientes manda el vencimiento más viejo; el resto va por fecha
    descendente, como cualquier historial.
    """
    pendientes = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.team_id == team_id,
            models.Invoice.status == models.INVOICE_PENDIENTE,
        )
        .order_by(models.Invoice.due_date.asc(), models.Invoice.id.asc())
        .limit(limite)
        .all()
    )
    resto = (
        db.query(models.Invoice)
        .filter(
            models.Invoice.team_id == team_id,
            models.Invoice.status != models.INVOICE_PENDIENTE,
        )
        .order_by(models.Invoice.due_date.desc(), models.Invoice.id.desc())
        .limit(limite)
        .all()
    )
    return pendientes + resto


def pendientes(db: Session, team_id: int) -> List[models.Invoice]:
    return (
        db.query(models.Invoice)
        .filter(
            models.Invoice.team_id == team_id,
            models.Invoice.status == models.INVOICE_PENDIENTE,
        )
        .order_by(models.Invoice.due_date.asc(), models.Invoice.id.asc())
        .all()
    )


def obtener(db: Session, team_id: int, factura_id: int) -> Optional[models.Invoice]:
    """Una factura **de este team**.

    El `team_id` va en el filtro y no en un `if` después de leerla: es el
    aislamiento entre cuentas, y un filtro que está en la consulta no se
    olvida de poner en la siguiente rama.
    """
    return (
        db.query(models.Invoice)
        .filter(
            models.Invoice.id == factura_id,
            models.Invoice.team_id == team_id,
        )
        .first()
    )


def proxima_factura(
    db: Session, team_id: int
) -> Optional[Tuple[date, int]]:
    """Cuándo se genera la próxima factura y por cuánto. `None` si no hay.

    Sale de la suscripción de la cuenta. Una suscripción cancelada no anuncia
    nada: no va a haber próxima factura.
    """
    sub = (
        db.query(models.Subscription)
        .filter(models.Subscription.team_id == team_id)
        .first()
    )
    if sub is None or sub.next_charge_at is None:
        return None
    if sub.status == models.SUBSCRIPTION_CANCELED:
        return None

    # `next_charge_at` es UTC naive; se pasa a Colombia antes de quedarse con
    # el día, por lo mismo de siempre: un cobro programado a las 7 p. m. hora
    # de Colombia cae al día siguiente si se lee en UTC.
    local = (
        sub.next_charge_at.replace(tzinfo=ZoneInfo("UTC"))
        .astimezone(ZONA_COLOMBIA)
        .date()
    )
    return local, int(sub.amount_cents)


# ---------------------------------------------------------------------------
# El aviso de mora
# ---------------------------------------------------------------------------

def debe_avisar(
    db: Session, team_id: int, *, hoy: Optional[date] = None
) -> Optional[str]:
    """¿Hay que mostrarle el aviso amarillo a esta cuenta?

    Devuelve `None` si no, o una **clave opaca** si sí. La clave es un hash de
    las facturas vencidas que lo provocan, y existe para que la X del aviso no
    lo apague para siempre: el navegador guarda la clave que el usuario cerró,
    y cuando la deuda cambia —se paga una, se vence otra— la clave cambia y el
    aviso vuelve a aparecer. Un aviso que se apaga de por vida es un aviso que
    sirve una sola vez.

    La clave no dice nada de la deuda: es un SHA-256 truncado sobre ids
    internos, sin montos ni cantidades. La ve el asesor, y esa es justamente la
    condición que tenía que cumplir.
    """
    hoy = hoy or hoy_colombia()
    corte = hoy - timedelta(days=DIAS_PARA_AVISAR)

    vencidas = (
        db.query(models.Invoice.id)
        .filter(
            models.Invoice.team_id == team_id,
            models.Invoice.status == models.INVOICE_PENDIENTE,
            models.Invoice.due_date <= corte,
        )
        .order_by(models.Invoice.id.asc())
        .all()
    )
    if not vencidas:
        return None

    semilla = ",".join(str(fila[0]) for fila in vencidas)
    return hashlib.sha256(semilla.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Emisión
# ---------------------------------------------------------------------------

def siguiente_numero(db: Session, team_id: int, *, emitida_el: date) -> str:
    """Consecutivo por cuenta y año: `FAC-2026-0003`.

    Por cuenta y no global para que el cliente vea sus facturas numeradas
    desde 1 y no se entere de cuántos clientes tiene la plataforma — el mismo
    motivo por el que las referencias de Wompi llevan sufijo aleatorio.
    """
    prefijo = f"FAC-{emitida_el.year}-"
    ultimas = (
        db.query(models.Invoice.numero)
        .filter(
            models.Invoice.team_id == team_id,
            models.Invoice.numero.like(f"{prefijo}%"),
        )
        .all()
    )
    consecutivo = 0
    for (numero,) in ultimas:
        try:
            consecutivo = max(consecutivo, int(str(numero).rsplit("-", 1)[1]))
        except (IndexError, ValueError):  # pragma: no cover - numeración a mano
            continue
    return f"{prefijo}{consecutivo + 1:04d}"


def emitir(
    db: Session,
    team_id: int,
    *,
    concepto: str,
    amount_cents: int,
    due_date: date,
    detalle: Optional[str] = None,
    issued_on: Optional[date] = None,
    subscription_id: Optional[int] = None,
) -> models.Invoice:
    """Crea una factura pendiente. No la cobra ni la manda a ningún lado."""
    issued_on = issued_on or due_date
    factura = models.Invoice(
        team_id=team_id,
        numero=siguiente_numero(db, team_id, emitida_el=issued_on),
        concepto=concepto,
        detalle=detalle,
        amount_cents=int(amount_cents),
        currency="COP",
        status=models.INVOICE_PENDIENTE,
        issued_on=issued_on,
        due_date=due_date,
        subscription_id=subscription_id,
    )
    db.add(factura)
    db.flush()
    return factura


def nueva_referencia(team_id: int, factura_id: int) -> str:
    """Referencia del pago de una factura: `glomafact-<team>-<id>-<aleatorio>`.

    El sufijo aleatorio va por lo mismo que en las compras y los cobros: la
    referencia viaja en la URL de Wompi y en el correo que le llega al
    cliente, y sin él sería adivinable la de otra cuenta.
    """
    return f"glomafact-{team_id}-{factura_id}-{secrets.token_hex(4)}"


def marcar_pagada(
    db: Session,
    factura: models.Invoice,
    *,
    tx_id: Optional[str] = None,
    cuando: Optional[datetime] = None,
) -> None:
    """Da la factura por pagada. Idempotente: si ya lo estaba, no toca nada."""
    if factura.status == models.INVOICE_PAGADA:
        return
    factura.status = models.INVOICE_PAGADA
    factura.paid_at = cuando or datetime.utcnow()
    if tx_id:
        factura.provider_tx_id = tx_id
    db.commit()
    logger.info("factura %s marcada como pagada", factura.id)


# ---------------------------------------------------------------------------
# El PDF
# ---------------------------------------------------------------------------

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)

#: Deep Forest, en la escala 0–1 que usa el PDF.
_VERDE = (0.0, 0.302, 0.251)
_MINT_SUAVE = (0.878, 0.949, 0.945)


def pesos(centavos: int) -> str:
    """35_000_000 → `$ 350.000`. Separador de miles con punto, como en Colombia."""
    return f"$ {centavos // 100:,.0f}".replace(",", ".")


def fecha_larga(dia: date) -> str:
    return f"{dia.day} de {_MESES[dia.month - 1]} de {dia.year}"


def nombre_archivo(factura: models.Invoice) -> str:
    """`factura-FAC-2026-0001.pdf`, sin nada del cliente en el nombre."""
    return f"factura-{factura.numero}.pdf"


def generar_pdf(
    factura: models.Invoice,
    *,
    nombre_cuenta: str,
) -> bytes:
    """La factura en PDF, con el concepto de lo que se cobra bien visible.

    El documento dice **qué** se cobra (una fila por concepto, que hoy es uno),
    cuánto, cuándo vence o cuándo se pagó. No lleva NIT, ni resolución de la
    DIAN, ni discrimina IVA: es un comprobante de cobro para que el cliente
    sepa qué le están facturando, no una factura electrónica. El día que tenga
    que serlo, eso se emite por el proveedor de facturación, no por acá.
    """
    from . import pdf as motor

    pagina = motor.Pagina()
    ancho = pagina.ancho
    izq, der = 56.0, ancho - 56.0

    # --- Encabezado ---------------------------------------------------------
    pagina.rectangulo(0, pagina.alto - 110, ancho, 110, rgb=_VERDE)
    pagina.texto(
        "Gloma", izq, pagina.alto - 58, tamaño=26, fuente=motor.NEGRILLA, gris=1.0
    )
    pagina.texto(
        "Plataforma de atención por WhatsApp",
        izq, pagina.alto - 78, tamaño=9.5, gris=0.85,
    )
    pagina.texto_derecha(
        "FACTURA", der, pagina.alto - 52, tamaño=14, fuente=motor.NEGRILLA, gris=1.0
    )
    pagina.texto_derecha(
        factura.numero, der, pagina.alto - 70, tamaño=11, gris=0.88
    )

    y = pagina.alto - 152

    # --- A quién y con qué fechas ------------------------------------------
    pagina.texto("CUENTA", izq, y, tamaño=8, fuente=motor.NEGRILLA, gris=0.45)
    pagina.texto(nombre_cuenta, izq, y - 16, tamaño=12, fuente=motor.NEGRILLA)

    pagina.texto_derecha("EMISIÓN", der, y, tamaño=8, fuente=motor.NEGRILLA, gris=0.45)
    pagina.texto_derecha(fecha_larga(factura.issued_on), der, y - 16, tamaño=10.5)

    y -= 44
    pagada = factura.status == models.INVOICE_PAGADA
    if pagada and factura.paid_at is not None:
        etiqueta, valor = "FECHA DE PAGO", fecha_larga(factura.paid_at.date())
    else:
        etiqueta, valor = "SE VENCE EL", fecha_larga(factura.due_date)
    pagina.texto_derecha(etiqueta, der, y, tamaño=8, fuente=motor.NEGRILLA, gris=0.45)
    pagina.texto_derecha(valor, der, y - 16, tamaño=10.5)

    pagina.texto("ESTADO", izq, y, tamaño=8, fuente=motor.NEGRILLA, gris=0.45)
    pagina.texto(
        {"pagada": "Pagada", "anulada": "Anulada"}.get(factura.status, "Pendiente"),
        izq, y - 16, tamaño=10.5, fuente=motor.NEGRILLA,
    )

    # --- Qué se cobra -------------------------------------------------------
    y -= 60
    pagina.rectangulo(izq, y - 8, der - izq, 26, rgb=_MINT_SUAVE)
    pagina.texto("CONCEPTO", izq + 12, y, tamaño=8.5, fuente=motor.NEGRILLA, gris=0.25)
    pagina.texto_derecha("VALOR", der - 12, y, tamaño=8.5, fuente=motor.NEGRILLA, gris=0.25)

    y -= 34
    pagina.texto(factura.concepto, izq + 12, y, tamaño=11, fuente=motor.NEGRILLA)
    pagina.texto_derecha(pesos(factura.amount_cents), der - 12, y, tamaño=11)
    if factura.detalle:
        for linea in _partir(factura.detalle, ancho_max=der - izq - 140, tamaño=9.5):
            y -= 14
            pagina.texto(linea, izq + 12, y, tamaño=9.5, gris=0.4)

    y -= 22
    pagina.linea(izq, y, der, y)

    # --- Total --------------------------------------------------------------
    y -= 26
    pagina.texto_derecha("TOTAL", der - 130, y, tamaño=10, fuente=motor.NEGRILLA, gris=0.4)
    pagina.texto_derecha(
        pesos(factura.amount_cents), der - 12, y, tamaño=16, fuente=motor.NEGRILLA
    )

    # --- Pie ----------------------------------------------------------------
    pie = (
        "Esta factura ya fue pagada. Gracias."
        if pagada
        else "Para pagarla entra a Pagos en la plataforma. "
        "Si ya la pagaste, ignora este mensaje."
    )
    pagina.texto(pie, izq, 92, tamaño=9, gris=0.45)
    pagina.texto(
        "Comprobante de cobro emitido por la plataforma. No es una factura electrónica DIAN.",
        izq, 76, tamaño=8, gris=0.6,
    )
    pagina.linea(izq, 112, der, 112)

    return motor.construir([pagina], titulo=f"Factura {factura.numero}")


def _partir(texto: str, *, ancho_max: float, tamaño: float) -> List[str]:
    """Parte el detalle en líneas que quepan. Tope de 4 para no desbordar la página."""
    from . import pdf as motor

    lineas: List[str] = []
    actual = ""
    for palabra in (texto or "").split():
        tentativa = f"{actual} {palabra}".strip()
        if actual and motor.ancho_texto(tentativa, tamaño) > ancho_max:
            lineas.append(actual)
            actual = palabra
            if len(lineas) == 4:
                return lineas
        else:
            actual = tentativa
    if actual:
        lineas.append(actual)
    return lineas[:4]
