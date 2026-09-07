"""Suscripción mensual a la plataforma: el plan, las fechas y los reintentos.

Es la parte del módulo de pagos que **no** son mensajes. Dos cosas distintas
conviven en la misma pantalla y conviene no confundirlas:

  - los **paquetes de mensajes** (`creditos.py`) son una compra puntual que
    suma créditos al saldo del team;
  - la **suscripción** es la cuota mensual por usar la plataforma. No otorga
    créditos: habilita el servicio. Si mañana el plan incluye mensajes, se
    agrega acá y se acredita en el cobro aprobado, no antes.

===========================================================================
CÓMO SE COBRA
===========================================================================

El Web Checkout de Wompi (el link de pago de toda la vida) **no sabe guardar
una tarjeta**: cobra una vez y se olvida. Para cobrar todos los meses sin que
el cliente vuelva a escribir la tarjeta hay que pasar por la API de *fuentes
de pago*, que son tres pasos (doc consultada 2026-09-05,
https://docs.wompi.co/docs/colombia/fuentes-de-pago/):

  1. el **navegador** tokeniza la tarjeta contra `POST /v1/tokens/cards` con
     la llave PÚBLICA. Los datos de la tarjeta nunca pasan por nuestro
     servidor — ver la nota de PCI abajo;
  2. el **backend** cambia ese token por una *fuente de pago* permanente
     (`POST /v1/payment_sources`, llave privada). Devuelve un `id` numérico
     que es lo único que guardamos;
  3. cada mes el backend cobra con `POST /v1/transactions` mandando ese
     `payment_source_id` y `recurrent: true`.

**Por qué la tarjeta no toca nuestro servidor.** El paso 1 va del navegador
directo a Wompi. Si el PAN pasara por nuestro backend —aunque fuera para
reenviarlo— la plataforma entera entraría en alcance PCI-DSS, con todo lo que
eso implica (auditoría anual, segmentación de red, retención de logs). Que el
token llegue ya hecho nos deja en el alcance mínimo. Es la razón por la que el
endpoint de activación recibe un `tok_...` y **rechaza** cualquier cosa que
parezca un número de tarjeta.

===========================================================================
CUÁNDO SE COBRA
===========================================================================

"El mismo día a la misma hora en que se activó", que es lo que pidió el CEO.
Dos precisiones que el enunciado no resuelve solo:

  - **El día se cuenta en hora de Colombia, no en UTC.** La base guarda UTC
    naive (convención del proyecto), pero quien activa a las 22:00 del 31 en
    Bogotá está en el 1.º a las 03:00 UTC: cobrarle "el 1.º" sería cobrarle un
    día distinto del que vio en pantalla. El aniversario se calcula en
    `America/Bogota` y se convierte de vuelta a UTC. Colombia no tiene horario
    de verano, así que la hora local no se corre nunca.
  - **Los meses cortos.** Quien se suscribe un 31 no tiene 31 en febrero. Se
    cobra el último día del mes (28 o 29) y en marzo **vuelve al 31**: por eso
    se guarda `billing_day` con el día original en vez de ir arrastrando la
    última fecha cobrada, que degradaría el 31 a 28 para siempre.

El ciclo avanza desde la fecha PROGRAMADA, no desde el momento del cobro. Si
el tick corre con cinco minutos de retraso, el mes siguiente no hereda esos
cinco minutos: sin eso la hora se iría corriendo sola mes a mes.
"""
from __future__ import annotations

import calendar
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .. import models
from . import wompi

logger = logging.getLogger(__name__)

#: Zona horaria del negocio. Colombia no tiene horario de verano: el offset es
#: -05:00 todo el año, así que "las 2 de la tarde" es siempre la misma hora UTC.
ZONA_COLOMBIA = ZoneInfo("America/Bogota")


# ---------------------------------------------------------------------------
# El plan
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Plan:
    """Un plan de suscripción. Igual que el catálogo de paquetes, vive en
    código y no en la base: el precio queda en un diff revisable en vez de en
    un `UPDATE` a mano en producción que nadie puede reconstruir después."""

    key: str
    nombre: str
    descripcion: str
    #: En centavos de COP, que es como los quiere Wompi (COP 350.000 → 35_000_000).
    amount_cents: int
    currency: str = "COP"

    @property
    def amount_cop(self) -> int:
        """Precio en pesos enteros, para pintar."""
        return self.amount_cents // 100


#: El único plan que hay hoy. Precio fijado por el CEO el 5-sep-2026.
PLAN_MENSUAL = Plan(
    key="plan_mensual",
    nombre="Plan mensual Gloma",
    descripcion=(
        "Acceso a la plataforma con cobro automático cada mes. "
        "Puedes desactivarlo cuando quieras."
    ),
    amount_cents=350_000 * 100,
)

_PLANES = {PLAN_MENSUAL.key: PLAN_MENSUAL}


def plan(key: str) -> Optional[Plan]:
    """El plan con esa `key`, o `None`. Devuelve `None` en vez de levantar:
    quien la llama viene de un input del usuario y traduce eso a un 404."""
    return _PLANES.get((key or "").strip())


# ---------------------------------------------------------------------------
# Precio por cuenta
# ---------------------------------------------------------------------------

#: Cuentas que pagan algo distinto del precio de lista, por correo del dueño.
#:
#: Vive en código y no en la base por lo mismo que el catálogo de paquetes: un
#: precio especial que se mete con un `UPDATE` a mano en producción no deja
#: rastro de quién lo puso ni por qué, y seis meses después nadie sabe si esa
#: cuenta paga menos por un acuerdo comercial o por un error.
#:
#: ⚠️ **`gloma@glomabeauty.com` es TEMPORAL** (6-sep-2026, pedido del CEO).
#: Wompi no permite ensayar un cobro recurrente real sin cobrar de verdad —el
#: sandbox es otro ambiente y no prueba las llaves de producción—, así que la
#: cuenta interna de Gloma queda en $3.000 para verificar el flujo completo
#: (registrar tarjeta → cobro → webhook → activación) moviendo lo mínimo.
#: **Devolverla a los $350.000 cuando la prueba termine.**
PRECIO_POR_CUENTA: Dict[str, int] = {
    "gloma@glomabeauty.com": 3_000 * 100,
}


def precio_para(correo_dueño: Optional[str], *, el_plan: Plan = PLAN_MENSUAL) -> int:
    """Cuántos centavos paga esta cuenta al mes.

    El precio sale **siempre del servidor**: el cliente manda a lo sumo qué
    plan quiere, nunca cuánto cuesta. La comparación de correos es
    case-insensitive porque el login no distingue mayúsculas y un override que
    dependa de cómo se escribió el correo es un override que un día no aplica.
    """
    clave = (correo_dueño or "").strip().lower()
    return PRECIO_POR_CUENTA.get(clave, el_plan.amount_cents)


# ---------------------------------------------------------------------------
# Reintentos
# ---------------------------------------------------------------------------

#: Cuántas veces se intenta el cobro de UN mes antes de rendirse.
MAX_INTENTOS = 3

#: Cuánto se espera entre intentos. 24 h porque el motivo más común de un
#: rechazo (cupo insuficiente) se resuelve solo al día siguiente, y porque
#: reintentar cada hora contra la misma tarjeta rechazada es la forma más
#: rápida de que el banco marque el comercio.
ESPERA_ENTRE_INTENTOS = timedelta(hours=24)


# ---------------------------------------------------------------------------
# Fechas
# ---------------------------------------------------------------------------

def _a_colombia(momento_utc: datetime) -> datetime:
    """UTC naive (como lo guarda la base) → hora de Colombia con tz."""
    return momento_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZONA_COLOMBIA)


def _a_utc_naive(momento_col: datetime) -> datetime:
    """Hora de Colombia con tz → UTC naive, que es lo que va a la columna."""
    return momento_col.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


def dia_de_facturacion(activacion_utc: datetime) -> int:
    """El día del mes que el cliente vio al activar (1–31), en hora de Colombia.

    Se guarda aparte para que un 31 no se degrade a 28 al pasar por febrero.
    """
    return _a_colombia(activacion_utc).day


def proxima_fecha_cobro(
    desde_utc: datetime,
    billing_day: int,
    *,
    meses: int = 1,
) -> datetime:
    """El mismo día del mes siguiente, a la misma hora local. En UTC naive.

    `desde_utc` es la fecha del ciclo que se está cerrando (la programada, no
    la real: ver el docstring del módulo) y `billing_day` es el día original
    de la activación, que manda sobre el día de `desde_utc`. Así, un ciclo que
    se cobró el 28 de febrero por ser mes corto vuelve al 31 en marzo.

    Si el mes destino no tiene ese día, se usa el último día del mes.
    """
    local = _a_colombia(desde_utc)

    mes = local.month - 1 + meses
    año = local.year + mes // 12
    mes = mes % 12 + 1

    dia = min(max(int(billing_day), 1), calendar.monthrange(año, mes)[1])
    destino = local.replace(year=año, month=mes, day=dia)
    return _a_utc_naive(destino)


def nueva_referencia(team_id: int, ciclo: datetime) -> str:
    """Referencia única del cobro de un mes.

    Formato: `glomasub-<team>-<AAAAMM>-<aleatorio>`. El sufijo aleatorio es
    `secrets.token_hex` por lo mismo que en las compras: la referencia viaja en
    la URL y en el correo de Wompi, y no debe dejar adivinar la de otro cliente
    ni delatar cuántos clientes lleva la plataforma.

    El `AAAAMM` **no** es la clave de idempotencia (esa es el UNIQUE sobre
    `reference` más el estado de la fila): está para que el CEO pueda leer de
    un vistazo a qué mes corresponde un cobro en el panel de Wompi.
    """
    return f"glomasub-{int(team_id)}-{ciclo:%Y%m}-{secrets.token_hex(6)}"


# ---------------------------------------------------------------------------
# El token de la tarjeta
# ---------------------------------------------------------------------------

#: Un token de tarjeta de Wompi: `tok_test_...` / `tok_prod_...`.
_TOKEN_VALIDO = re.compile(r"^tok_(test|prod|stagtest)_[A-Za-z0-9_\-]{5,120}$")

#: Cualquier cosa que parezca un número de tarjeta: 13–19 dígitos, aunque
#: vengan separados por espacios o guiones.
_PARECE_TARJETA = re.compile(r"^[\d\s\-]{13,25}$")


class TokenInvalido(ValueError):
    """Lo que llegó no es un token de tarjeta de Wompi."""


def validar_token_tarjeta(valor: str) -> str:
    """Acepta un `tok_...` y **rechaza todo lo demás**, sin excepción.

    Este guardarraíl es la frontera de PCI del proyecto. Si un cliente (o un
    frontend con un bug) mandara aquí el número de la tarjeta, el PAN entraría
    en nuestros logs de acceso, en el cuerpo del request y en cualquier traza
    de errores — y la plataforma entera pasaría a estar en alcance PCI-DSS por
    accidente. Por eso no se intenta "arreglar" lo que llega: se rechaza.

    El mensaje de error **nunca incluye el valor recibido**, justamente para
    no escribir en el log lo que se está tratando de mantener fuera de él.
    """
    limpio = (valor or "").strip()
    if _TOKEN_VALIDO.match(limpio):
        return limpio

    if _PARECE_TARJETA.match(limpio):
        # Ni el número ni un fragmento: solo que pasó.
        logger.error(
            "suscripcion: se recibió algo con forma de número de tarjeta en vez "
            "de un token. Se descarta sin registrarlo."
        )
        raise TokenInvalido("La tarjeta debe registrarse contra Wompi, no aquí")

    logger.warning("suscripcion: token de tarjeta con formato inválido")
    raise TokenInvalido("El registro de la tarjeta no se completó")


# ---------------------------------------------------------------------------
# El motor de cobro
# ---------------------------------------------------------------------------

class SuscripcionError(RuntimeError):
    """No se pudo completar la operación. `codigo` es para el log, no para el
    cliente: el router lo traduce a un mensaje genérico (regla 6)."""

    def __init__(self, mensaje: str, codigo: str = "ERROR") -> None:
        super().__init__(mensaje)
        self.codigo = codigo


def obtener(db: Session, team_id: int) -> Optional[models.Subscription]:
    """La suscripción de un team, si alguna vez se creó la fila."""
    return (
        db.query(models.Subscription)
        .filter(models.Subscription.team_id == team_id)
        .first()
    )


def correo_del_dueño(db: Session, team_id: int) -> Optional[str]:
    """El correo del owner del team. Es la llave de `PRECIO_POR_CUENTA`."""
    fila = (
        db.query(models.User.correo)
        .join(models.Team, models.Team.owner_user_id == models.User.id)
        .filter(models.Team.id == team_id)
        .first()
    )
    return fila[0] if fila else None


def obtener_o_crear(
    db: Session, team_id: int, *, plan_key: str = PLAN_MENSUAL.key
) -> models.Subscription:
    """La suscripción del team, creándola en `pending` si no existía.

    `pending` es exactamente lo que el CEO pidió que muestre el botón:
    "pendiente por activar". Una cuenta sin fila y una cuenta con fila
    `pending` son lo mismo de cara al cliente, y unificarlas acá evita que cada
    pantalla tenga que tratar el `None` por su cuenta.

    **Al precio de una suscripción todavía `pending` se le da alcance.** Si el
    precio de lista cambia —o se le pone un override a la cuenta— después de
    que alguien abrió la pantalla, la fila ya creada se quedaría con el precio
    viejo y le cobraríamos eso. Solo se toca en `pending`: cambiarle el precio
    a una suscripción **activa** por detrás es lo que un cliente jamás espera,
    y eso exige una decisión explícita, no un efecto secundario de abrir una
    pantalla.
    """
    el_plan = plan(plan_key) or PLAN_MENSUAL
    precio = precio_para(correo_del_dueño(db, team_id), el_plan=el_plan)

    sub = obtener(db, team_id)
    if sub is not None:
        if sub.status == models.SUBSCRIPTION_PENDING and sub.amount_cents != precio:
            logger.info(
                "suscripcion %s (pending): precio %s → %s",
                sub.id, sub.amount_cents, precio,
            )
            sub.amount_cents = precio
            db.commit()
        return sub

    sub = models.Subscription(
        team_id=team_id,
        plan_key=el_plan.key,
        status=models.SUBSCRIPTION_PENDING,
        amount_cents=precio,
        currency=el_plan.currency,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def _registrar_cobro(
    db: Session,
    sub: models.Subscription,
    *,
    ciclo: datetime,
    intento: int,
) -> models.SubscriptionCharge:
    """Crea la fila del intento ANTES de hablar con Wompi.

    El orden importa: si se creara después, un timeout justo en el cobro
    dejaría plata cobrada sin fila que la explique. Al revés, lo peor que puede
    pasar es una fila `pending` de un cobro que nunca salió, que la
    reconciliación resuelve.
    """
    cobro = models.SubscriptionCharge(
        subscription_id=sub.id,
        team_id=sub.team_id,
        reference=nueva_referencia(sub.team_id, ciclo),
        amount_cents=sub.amount_cents,
        currency=sub.currency,
        status=models.SUBSCRIPTION_CHARGE_PENDING,
        scheduled_for=ciclo,
        attempt=intento,
    )
    db.add(cobro)
    db.commit()
    db.refresh(cobro)
    return cobro


def _ejecutar_cobro(
    db: Session, sub: models.Subscription, cobro: models.SubscriptionCharge
) -> models.SubscriptionCharge:
    """Le pide el cobro a Wompi y anota el resultado en la fila del intento.

    **No activa la suscripción.** Wompi casi siempre responde `PENDING` y el
    estado final lo confirma el webhook firmado (o la reconciliación). Dar el
    cobro por bueno porque la llamada respondió 201 sería creerle a la
    pasarela una respuesta que todavía no dio.
    """
    try:
        aceptacion = wompi.tokens_de_aceptacion()
        transaccion = wompi.cobrar_con_fuente_de_pago(
            payment_source_id=int(sub.payment_source_id),
            monto_centavos=sub.amount_cents,
            referencia=cobro.reference,
            email_cliente=sub.customer_email or "",
            acceptance_token=aceptacion["acceptance_token"],
            moneda=sub.currency,
        )
    except wompi.WompiError as error:
        cobro.status = models.SUBSCRIPTION_CHARGE_ERROR
        cobro.failure_code = error.codigo[:40]
        db.commit()
        logger.error(
            "suscripcion: cobro rechazado sub=%s intento=%s codigo=%s",
            sub.id, cobro.attempt, error.codigo,
        )
        return cobro

    cobro.provider_tx_id = (transaccion.get("id") or "")[:80] or None
    estado = wompi.estado_interno(transaccion.get("status") or "")
    if estado is not None:
        aplicar_estado(db, cobro, estado)
    else:
        db.commit()
    return cobro


def aplicar_estado(
    db: Session,
    cobro: models.SubscriptionCharge,
    estado: str,
    *,
    tx_id: Optional[str] = None,
) -> models.SubscriptionCharge:
    """Aterriza el estado final de un cobro sobre la suscripción.

    Es el único sitio donde una suscripción pasa a `active`, y lo llaman los
    dos caminos que pueden traer una confirmación: el **webhook** firmado y la
    **reconciliación** del tick. Que sea uno solo es lo que hace que los dos
    lleguen al mismo resultado.

    Idempotente: un cobro ya aprobado no se vuelve a procesar por más veces que
    Wompi reintente el webhook (reintenta hasta 3 veces en 24 h).
    """
    if cobro.status == models.SUBSCRIPTION_CHARGE_APPROVED:
        logger.info("suscripcion: cobro %s ya estaba aprobado", cobro.id)
        return cobro

    if tx_id:
        cobro.provider_tx_id = tx_id[:80]

    sub = (
        db.query(models.Subscription)
        .filter(models.Subscription.id == cobro.subscription_id)
        .first()
    )

    if estado != models.SUBSCRIPTION_CHARGE_APPROVED:
        cobro.status = estado
        cobro.failure_code = (cobro.failure_code or estado.upper())[:40]
        db.commit()
        if sub is not None:
            _programar_reintento(db, sub, cobro)
        return cobro

    # --- aprobado ---------------------------------------------------------
    ahora = datetime.utcnow()
    cobro.status = models.SUBSCRIPTION_CHARGE_APPROVED
    cobro.paid_at = ahora
    cobro.failure_code = None

    if sub is not None:
        if sub.activated_at is None:
            # Primer pago: acá arranca el ciclo y queda fijado el día de cobro.
            sub.activated_at = ahora
            sub.billing_day = dia_de_facturacion(ahora)
        sub.status = models.SUBSCRIPTION_ACTIVE
        sub.last_charge_at = ahora
        sub.attempts = 0
        sub.canceled_at = None
        # Desde la fecha PROGRAMADA, no desde `ahora`: si no, el retraso del
        # tick se acumularía mes a mes hasta correr la hora del cobro.
        sub.next_charge_at = proxima_fecha_cobro(
            cobro.scheduled_for, sub.billing_day or dia_de_facturacion(ahora)
        )

    db.commit()
    logger.info(
        "suscripcion: cobro %s aprobado sub=%s proximo=%s",
        cobro.id,
        cobro.subscription_id,
        getattr(sub, "next_charge_at", None),
    )
    return cobro


def _programar_reintento(
    db: Session, sub: models.Subscription, cobro: models.SubscriptionCharge
) -> None:
    """Decide qué pasa después de un cobro que no entró.

    Hasta `MAX_INTENTOS` por ciclo, separados `ESPERA_ENTRE_INTENTOS`. Agotados
    los intentos la suscripción queda en `past_due` y **el ciclo salta al mes
    siguiente**: no se sigue insistiendo con una tarjeta que ya dijo que no
    tres veces, pero tampoco se cancela sola. Cancelar por un rechazo sería
    tomar por el cliente una decisión que es suya — y la causa más común es un
    cupo insuficiente, no una intención de irse.

    Mientras está en `past_due` el cliente ve el aviso en la pantalla de pagos
    y puede registrar otra tarjeta, que reactiva de inmediato.
    """
    if sub.status == models.SUBSCRIPTION_CANCELED:
        # La canceló mientras el cobro viajaba. Se respeta la cancelación.
        return

    sub.attempts = (sub.attempts or 0) + 1

    if sub.attempts >= MAX_INTENTOS:
        sub.status = models.SUBSCRIPTION_PAST_DUE
        sub.attempts = 0
        sub.next_charge_at = proxima_fecha_cobro(
            cobro.scheduled_for, sub.billing_day or cobro.scheduled_for.day
        )
        logger.warning(
            "suscripcion %s en mora: %s intentos fallidos del ciclo %s",
            sub.id, MAX_INTENTOS, cobro.scheduled_for,
        )
    else:
        sub.next_charge_at = datetime.utcnow() + ESPERA_ENTRE_INTENTOS

    db.commit()


def activar(
    db: Session,
    sub: models.Subscription,
    *,
    token_tarjeta: str,
    email_cliente: str,
    user_id: Optional[int] = None,
) -> models.SubscriptionCharge:
    """Guarda la tarjeta y lanza el primer cobro. Devuelve el intento creado.

    La suscripción **no queda activa al volver de acá**: queda con la tarjeta
    registrada y un cobro en curso. Se activa cuando ese cobro se confirme
    aprobado, que es cosa del webhook o de la reconciliación. La pantalla
    muestra "estamos confirmando" en el intervalo.

    Si ya estaba activa, se rechaza en vez de cobrar de nuevo: un doble clic en
    el botón no puede convertirse en dos cobros de $350.000.
    """
    if sub.status == models.SUBSCRIPTION_ACTIVE:
        raise SuscripcionError("la suscripción ya está activa", "YA_ACTIVA")

    token = validar_token_tarjeta(token_tarjeta)

    if _hay_cobro_en_curso(db, sub):
        raise SuscripcionError("ya hay un cobro en curso", "COBRO_EN_CURSO")

    try:
        aceptacion = wompi.tokens_de_aceptacion()
        fuente = wompi.crear_fuente_de_pago(
            token_tarjeta=token,
            email_cliente=email_cliente,
            acceptance_token=aceptacion["acceptance_token"],
            personal_auth_token=aceptacion.get("personal_auth_token"),
        )
    except wompi.WompiError as error:
        logger.error("suscripcion: no se pudo guardar la tarjeta codigo=%s", error.codigo)
        raise SuscripcionError("no se pudo registrar la tarjeta", error.codigo)

    if not fuente.get("id") or fuente.get("status") != "AVAILABLE":
        logger.error(
            "suscripcion: fuente de pago inutilizable status=%s", fuente.get("status")
        )
        raise SuscripcionError("no se pudo registrar la tarjeta", "FUENTE_NO_DISPONIBLE")

    sub.payment_source_id = int(fuente["id"])
    sub.card_brand = (fuente.get("brand") or "")[:20] or None
    sub.card_last_four = (str(fuente.get("last_four") or ""))[-4:] or None
    sub.customer_email = email_cliente[:255]
    if user_id is not None:
        sub.created_by_user_id = user_id
    sub.attempts = 0
    db.commit()

    ahora = datetime.utcnow()
    cobro = _registrar_cobro(db, sub, ciclo=ahora, intento=1)
    return _ejecutar_cobro(db, sub, cobro)


def _hay_cobro_en_curso(db: Session, sub: models.Subscription) -> bool:
    """¿Hay un intento reciente todavía sin resolver?

    Ventana de 10 minutos: pasado ese tiempo, un `pending` es un cobro que se
    perdió (y que la reconciliación va a resolver), no uno en vuelo. Sin la
    ventana, un solo cobro fantasma dejaría la cuenta trabada para siempre.
    """
    limite = datetime.utcnow() - timedelta(minutes=10)
    return (
        db.query(models.SubscriptionCharge)
        .filter(
            models.SubscriptionCharge.subscription_id == sub.id,
            models.SubscriptionCharge.status == models.SUBSCRIPTION_CHARGE_PENDING,
            models.SubscriptionCharge.created_at >= limite,
        )
        .first()
        is not None
    )


def cancelar(
    db: Session, sub: models.Subscription, *, user_id: Optional[int] = None
) -> models.Subscription:
    """Apaga el cobro automático. No reembolsa el mes ya pagado.

    Se **olvida la tarjeta** (`payment_source_id = NULL`): dejarla guardada
    después de que el cliente dijo "no me cobres más" es exactamente lo que un
    cliente no espera, y guardar un medio de pago que ya no se va a usar es
    riesgo sin contrapartida. Reactivar exige registrarla de nuevo.
    """
    sub.status = models.SUBSCRIPTION_CANCELED
    sub.canceled_at = datetime.utcnow()
    sub.canceled_by_user_id = user_id
    sub.next_charge_at = None
    sub.attempts = 0
    sub.payment_source_id = None
    sub.card_brand = None
    sub.card_last_four = None
    db.commit()
    logger.info("suscripcion %s cancelada por user=%s", sub.id, user_id)
    return sub


# ---------------------------------------------------------------------------
# El tick: cobros del mes y reconciliación
# ---------------------------------------------------------------------------

#: Cuánto se le da a un cobro para que el webhook lo resuelva antes de ir a
#: preguntarle a Wompi directamente. Wompi suele avisar en segundos; 15 min es
#: margen de sobra sin dejar a un cliente esperando media hora.
ESPERA_ANTES_DE_RECONCILIAR = timedelta(minutes=15)


def tick(db: Session, *, limite: int = 50) -> Dict[str, Any]:
    """Cobra las suscripciones vencidas y resuelve los cobros colgados.

    Lo llama un scheduler externo (ver `routers/internal.py`). Devuelve un
    resumen **sin PII**: solo conteos.

    Son dos trabajos en uno a propósito, porque el segundo es lo que hace
    confiable al primero: si el webhook no llega —URL mal configurada, un
    despliegue en curso, Wompi con problemas—, la reconciliación pregunta y el
    cobro igual se resuelve. Sin ella, un webhook perdido deja una suscripción
    pagada sin activar y nadie se entera.
    """
    return {
        "cobradas": _cobrar_vencidas(db, limite=limite),
        "reconciliadas": _reconciliar_colgados(db, limite=limite),
        "tick_at": datetime.utcnow().isoformat() + "Z",
    }


def _ciclo_a_cobrar(
    db: Session, sub: models.Subscription, ahora: datetime
) -> datetime:
    """Qué mes está pagando este intento.

    Un **reintento conserva el `scheduled_for` del ciclo original**, aunque se
    ejecute dos días después. Es lo que evita dos errores encadenados:

      - la hora se correría — un cobro de las 2 p. m. que falla y entra en el
        reintento de las 4 p. m. dejaría al cliente cobrado a las 4 p. m. para
        siempre;
      - y peor, un ciclo del 31 de enero cuyo reintento cae el 2 de febrero
        calcularía el siguiente desde febrero y **se saltaría un mes entero**.

    `sub.attempts > 0` es lo que distingue un reintento del primer cobro de un
    ciclo nuevo: se pone a 0 en cuanto un cobro entra.
    """
    if (sub.attempts or 0) > 0:
        ultimo = (
            db.query(models.SubscriptionCharge)
            .filter(models.SubscriptionCharge.subscription_id == sub.id)
            .order_by(models.SubscriptionCharge.id.desc())
            .first()
        )
        if ultimo is not None:
            return ultimo.scheduled_for
    return sub.next_charge_at or ahora


def _cobrar_vencidas(db: Session, *, limite: int) -> int:
    """Lanza el cobro de las suscripciones cuya fecha ya pasó."""
    ahora = datetime.utcnow()
    vencidas: List[models.Subscription] = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.status.in_(
                (models.SUBSCRIPTION_ACTIVE, models.SUBSCRIPTION_PAST_DUE)
            ),
            models.Subscription.next_charge_at.isnot(None),
            models.Subscription.next_charge_at <= ahora,
            models.Subscription.payment_source_id.isnot(None),
        )
        .order_by(models.Subscription.next_charge_at.asc())
        .limit(limite)
        .all()
    )

    cobradas = 0
    for sub in vencidas:
        try:
            if _hay_cobro_en_curso(db, sub):
                continue
            cobro = _registrar_cobro(
                db,
                sub,
                ciclo=_ciclo_a_cobrar(db, sub, ahora),
                intento=(sub.attempts or 0) + 1,
            )
            _ejecutar_cobro(db, sub, cobro)
            cobradas += 1
        except Exception:
            # Una suscripción que revienta no puede tumbar el cobro de las
            # demás: se anota y el tick sigue.
            db.rollback()
            logger.exception("suscripcion %s: el cobro del ciclo falló", sub.id)
    return cobradas


def _reconciliar_colgados(db: Session, *, limite: int) -> int:
    """Le pregunta a Wompi por los cobros que quedaron `pending` demasiado tiempo."""
    limite_tiempo = datetime.utcnow() - ESPERA_ANTES_DE_RECONCILIAR
    colgados: List[models.SubscriptionCharge] = (
        db.query(models.SubscriptionCharge)
        .filter(
            models.SubscriptionCharge.status == models.SUBSCRIPTION_CHARGE_PENDING,
            models.SubscriptionCharge.created_at <= limite_tiempo,
        )
        .order_by(models.SubscriptionCharge.created_at.asc())
        .limit(limite)
        .all()
    )

    resueltos = 0
    for cobro in colgados:
        if not cobro.provider_tx_id:
            # Nunca llegó a existir en Wompi: el cobro no salió.
            cobro.status = models.SUBSCRIPTION_CHARGE_ERROR
            cobro.failure_code = "SIN_TRANSACCION"
            db.commit()
            sub = (
                db.query(models.Subscription)
                .filter(models.Subscription.id == cobro.subscription_id)
                .first()
            )
            if sub is not None:
                _programar_reintento(db, sub, cobro)
            resueltos += 1
            continue

        try:
            real = wompi.consultar_transaccion(cobro.provider_tx_id)
        except Exception:
            logger.exception("suscripcion: no se pudo reconciliar el cobro %s", cobro.id)
            continue
        if not real:
            continue

        estado = wompi.estado_interno(real.get("status") or "")
        if estado is None:
            continue  # sigue en curso de verdad
        aplicar_estado(db, cobro, estado)
        resueltos += 1
    return resueltos
