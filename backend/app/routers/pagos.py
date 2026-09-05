"""Pagos: compra de paquetes de mensajes por Wompi.

Módulo **de administrador**. El asesor que atiende la bandeja no ve precios,
ni saldo, ni historial de compras: no es su trabajo y son datos del negocio.
El portero es `require_billing_admin` y deja pasar a dos figuras:

  - el **owner** del team (el dueño de la cuenta), y
  - cualquier miembro con el permiso `can_manage_billing`.

Permiso además de rol para que mañana un cliente pueda darle la caja a su
contador sin volverlo dueño de la cuenta.

Cómo se acredita una compra
---------------------------
El único evento que suma créditos es el **webhook** de Wompi con la
transacción en `APPROVED`. Ni el `redirect-url` al que vuelve el navegador ni
un `POST` del frontend acreditan nada: esos los controla el usuario, y quien
puede visitar una URL podría regalarse mensajes.

La suma es idempotente por diseño y por tres candados encadenados:
  1. `credit_purchases.reference` es UNIQUE,
  2. la fila se lee con `SELECT ... FOR UPDATE` (dos webhooks simultáneos se
     serializan en vez de leer los dos `pending` y sumar los dos),
  3. si ya está `approved`, se sale sin tocar el saldo.
Wompi reintenta hasta 3 veces en 24 horas si no recibe un 200, así que el
webhook repetido no es un caso raro: es el comportamiento normal.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from .. import crud, models
from ..dependencies import get_current_user, get_db
from ..schemas import (
    CheckoutCreate,
    CheckoutFormOut,
    CheckoutOut,
    CobroOut,
    EstadoPagoOut,
    CompraOut,
    PagosAccesoOut,
    PaqueteOut,
    PaquetesOut,
    SaldoOut,
    SuscripcionActivarIn,
    SuscripcionConfigOut,
    SuscripcionOut,
    TarjetaOut,
)
from ..services import creditos as svc_creditos
from ..services import ratelimit
from ..services import suscripciones as svc_suscripciones
from ..services import wompi

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pagos", tags=["pagos"])

#: Permiso que habilita la caja. Vive en `AVAILABLE_PERMISSIONS`.
PERMISO_BILLING = "can_manage_billing"

#: A dónde vuelve el navegador después de pagar. Se arma en el SERVIDOR con
#: esta base: el cliente solo puede pedir una ruta relativa (ver
#: `_redirect_absoluto`). Si el `redirect-url` se aceptara tal cual del
#: request, el checkout de Wompi quedaría convertido en un redirector abierto
#: hacia cualquier dominio, firmado por nosotros.
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000")

#: Ruta por defecto de regreso: la misma pantalla de pagos.
REDIRECT_POR_DEFECTO = "/pagos"

#: Tope de intentos de registrar una tarjeta, por cuenta y por hora.
#:
#: No es una defensa contra un cliente torpe (con dos o tres intentos ya se
#: corrigió un número mal escrito): es contra el **card testing**. Quien
#: consiga una cuenta de administrador podría usar este endpoint para probar
#: tarjetas robadas de a una, y a quien las franquicias multan y terminan
#: cerrándole la pasarela es al comercio — a Gloma, no al atacante.
#:
#: La ventana es en memoria del proceso, igual que la de los chats públicos:
#: con más de una task de ECS el límite pasa a ser por task, que es más
#: permisivo pero nunca peor que no tener nada.
_activaciones_limiter = ratelimit.SlidingWindow(por_ip=5, global_=200)


# ---------------------------------------------------------------------------
# Autorización
# ---------------------------------------------------------------------------

def _es_admin_de_billing(member: Optional[models.TeamMember]) -> bool:
    """Owner del team, o miembro con `can_manage_billing`."""
    if member is None:
        return False
    if member.role == "owner":
        return True
    return crud.member_has_permission(member, PERMISO_BILLING)


def require_billing_admin(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.TeamMember:
    """Portero del módulo. 403 genérico para todo el que no sea admin.

    El motivo exacto (sin team / rol insuficiente) va al log del servidor; al
    cliente se le responde siempre lo mismo (regla 6), para no confirmarle a
    un asesor curioso qué le falta exactamente.
    """
    member = crud.get_membership_for_user(db, user)
    if not _es_admin_de_billing(member):
        logger.warning(
            "acceso denegado a /pagos: user_id=%s team_id=%s role=%s",
            user.id,
            getattr(member, "team_id", None),
            getattr(member, "role", None),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este módulo",
        )
    return member


def _team(db: Session, member: models.TeamMember) -> models.Team:
    team = db.query(models.Team).filter(models.Team.id == member.team_id).first()
    if team is None:  # pragma: no cover - integridad referencial lo impide
        logger.error("membresía %s apunta a un team inexistente", member.id)
        raise HTTPException(status_code=500, detail="Error temporal")
    return team


# ---------------------------------------------------------------------------
# Consulta
# ---------------------------------------------------------------------------

@router.get("/access", response_model=PagosAccesoOut)
def check_access(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PagosAccesoOut:
    """¿Esta sesión puede usar el módulo? Lo consulta el menú del frontend
    para mostrar la pestaña solo a quien puede pagar. Responde 200 siempre
    (no filtra nada: solo dice sí o no)."""
    member = crud.get_membership_for_user(db, user)
    return PagosAccesoOut(allowed=_es_admin_de_billing(member))


def _paquete_out(p: svc_creditos.Paquete) -> PaqueteOut:
    """El paquete tal como lo ve el cliente: nombre, precio y nada más.

    El desglose de costos ya no sale (ver `PaqueteOut`). Sigue calculándose en
    `creditos.desglose_paquete()` para auditar el precio desde el código.
    """
    return PaqueteOut(
        key=p.key,
        nombre=p.nombre,
        descripcion=p.descripcion,
        messages=p.messages,
        amount_cents=p.amount_cents,
        amount_cop=p.amount_cop,
        precio_por_mensaje_cop=p.precio_por_mensaje_cop,
        currency=p.currency,
        link_pago=p.link_pago,
    )


@router.get("/paquetes", response_model=PaquetesOut)
def listar_paquetes(
    member: models.TeamMember = Depends(require_billing_admin),
) -> PaquetesOut:
    """Los paquetes a la venta, con su precio.

    Sin el desglose de costos: aunque el endpoint sea solo para
    administradores, el administrador de una cuenta **es el cliente**, y el
    costo de los mensajes y el margen son datos de Gloma, no suyos.
    """
    return PaquetesOut(
        paquetes=[_paquete_out(p) for p in svc_creditos.catalogo()],
        pagos_habilitados=wompi.esta_configurado(),
    )


@router.get("/saldo", response_model=SaldoOut)
def ver_saldo(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_billing_admin),
) -> SaldoOut:
    """Créditos disponibles del team y sus últimas compras."""
    team = _team(db, member)
    compras = (
        db.query(models.CreditPurchase)
        .filter(models.CreditPurchase.team_id == team.id)
        .order_by(models.CreditPurchase.created_at.desc())
        .limit(100)
        .all()
    )
    return SaldoOut(
        message_credits=team.message_credits or 0,
        compras=[CompraOut.model_validate(c) for c in compras],
    )


# ---------------------------------------------------------------------------
# Checkout
# ---------------------------------------------------------------------------

def _redirect_absoluto(pedido: Optional[str]) -> str:
    """Convierte la ruta pedida en una URL absoluta de NUESTRO frontend.

    Solo se aceptan rutas relativas que empiecen por `/` y no por `//` (una
    ruta `//evil.com` es protocol-relative: el navegador la trata como otro
    dominio). Cualquier otra cosa cae en la ruta por defecto en vez de dar
    error: el destino de regreso es cosmético y no vale la pena tumbarle la
    compra a alguien por eso.
    """
    ruta = (pedido or "").strip() or REDIRECT_POR_DEFECTO
    if not ruta.startswith("/") or ruta.startswith("//"):
        logger.warning("redirect_url descartado por no ser una ruta propia")
        ruta = REDIRECT_POR_DEFECTO
    return f"{FRONTEND_BASE_URL.rstrip('/')}{ruta}"


@router.post("/checkout", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
def crear_checkout(
    payload: CheckoutCreate,
    request: Request,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_billing_admin),
    user: models.User = Depends(get_current_user),
) -> CheckoutOut:
    """Registra la intención de compra y devuelve el form firmado de Wompi.

    Deja la compra en `pending`. Los créditos NO se suman acá — se suman
    cuando el webhook confirme el pago. Que exista la fila antes de mandar al
    usuario a Wompi es lo que después permite reconocer la referencia cuando
    el webhook vuelva.

    El precio se toma del **catálogo del servidor**, nunca del request: el
    cliente manda `package_key`, no un monto.
    """
    paquete = svc_creditos.paquete(payload.package_key)
    if paquete is None:
        raise HTTPException(status_code=404, detail="Paquete no encontrado")

    team = _team(db, member)
    referencia = wompi.nueva_referencia(team.id, paquete.key)

    try:
        checkout = wompi.datos_checkout(
            referencia=referencia,
            monto_centavos=paquete.amount_cents,
            moneda=paquete.currency,
            redirect_url=_redirect_absoluto(payload.redirect_url),
            email_cliente=user.correo,
        )
    except wompi.WompiNoConfigurado:
        # El detalle (qué variable falta) ya quedó en el log del servicio.
        # Al cliente, mensaje genérico (regla 6).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El medio de pago no está disponible por ahora. Intenta más tarde.",
        )

    compra = models.CreditPurchase(
        team_id=team.id,
        created_by_user_id=user.id,
        package_key=paquete.key,
        messages=paquete.messages,
        amount_cents=paquete.amount_cents,
        currency=paquete.currency,
        reference=referencia,
        provider="wompi",
        status=models.CREDIT_PURCHASE_PENDING,
    )
    db.add(compra)
    db.commit()
    db.refresh(compra)

    logger.info(
        "checkout creado compra_id=%s team_id=%s paquete=%s",
        compra.id,
        team.id,
        paquete.key,
    )
    return CheckoutOut(
        reference=referencia,
        purchase_id=compra.id,
        amount_cents=paquete.amount_cents,
        currency=paquete.currency,
        messages=paquete.messages,
        checkout=CheckoutFormOut(**checkout),
    )


# ---------------------------------------------------------------------------
# Suscripción mensual
# ---------------------------------------------------------------------------
#
# El flujo completo, y por qué la tarjeta no pasa por acá, está explicado en
# `services/suscripciones.py`. Lo que este router aporta:
#
#   GET  /pagos/suscripcion          en qué va la suscripción de la cuenta
#   GET  /pagos/suscripcion/config   lo que el navegador necesita para
#                                    tokenizar la tarjeta contra Wompi
#   POST /pagos/suscripcion/activar  recibe el `tok_...`, guarda la tarjeta y
#                                    lanza el primer cobro
#   POST /pagos/suscripcion/cancelar apaga el cobro automático
#
# Los cuatro exigen `require_billing_admin`, igual que el resto del módulo.


def _suscripcion_out(
    db: Session, sub: models.Subscription
) -> SuscripcionOut:
    """Arma la respuesta pública de una suscripción.

    Es la única traducción del modelo a la pantalla, y por eso es también el
    sitio donde se decide qué NO sale: ni `payment_source_id` ni
    `customer_email` tienen campo en `SuscripcionOut`.
    """
    plan = svc_suscripciones.plan(sub.plan_key) or svc_suscripciones.PLAN_MENSUAL

    cobros = (
        db.query(models.SubscriptionCharge)
        .filter(models.SubscriptionCharge.subscription_id == sub.id)
        .order_by(models.SubscriptionCharge.created_at.desc())
        .limit(24)
        .all()
    )

    tarjeta = None
    if sub.card_last_four:
        tarjeta = TarjetaOut(brand=sub.card_brand, last_four=sub.card_last_four)

    return SuscripcionOut(
        status=sub.status,
        plan_key=plan.key,
        plan_nombre=plan.nombre,
        plan_descripcion=plan.descripcion,
        amount_cents=sub.amount_cents,
        amount_cop=sub.amount_cents // 100,
        currency=sub.currency,
        tarjeta=tarjeta,
        next_charge_at=sub.next_charge_at,
        last_charge_at=sub.last_charge_at,
        activated_at=sub.activated_at,
        canceled_at=sub.canceled_at,
        habilitada=wompi.suscripciones_habilitadas(),
        cobro_en_curso=any(
            c.status == models.SUBSCRIPTION_CHARGE_PENDING for c in cobros[:3]
        ),
        cobros=[CobroOut.model_validate(c) for c in cobros],
    )


@router.get("/suscripcion", response_model=SuscripcionOut)
def ver_suscripcion(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_billing_admin),
) -> SuscripcionOut:
    """Estado de la suscripción de la cuenta.

    Crea la fila en `pending` si no existía: una cuenta sin fila y una con fila
    `pending` son lo mismo de cara al cliente ("pendiente por activar"), y
    unificarlas acá le ahorra a la pantalla tener que distinguirlas.
    """
    team = _team(db, member)
    sub = svc_suscripciones.obtener_o_crear(db, team.id)
    return _suscripcion_out(db, sub)


@router.get("/suscripcion/config", response_model=SuscripcionConfigOut)
def config_suscripcion(
    member: models.TeamMember = Depends(require_billing_admin),
) -> SuscripcionConfigOut:
    """Llave pública y tokens de aceptación para el formulario de tarjeta.

    Se pide **al abrir el formulario**, no al cargar la pantalla: los tokens de
    aceptación expiran, y su razón de ser es probar que al cliente se le mostró
    la versión vigente del contrato justo antes de aceptarla.

    Nada de lo que sale de acá es secreto — ver `SuscripcionConfigOut`.
    """
    if not wompi.suscripciones_habilitadas():
        logger.error("suscripcion: faltan llaves de Wompi para tokenizar tarjetas")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El medio de pago no está disponible por ahora. Intenta más tarde.",
        )

    try:
        aceptacion = wompi.tokens_de_aceptacion()
    except wompi.WompiError:
        # El detalle ya quedó en el log del servicio (regla 6).
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El medio de pago no está disponible por ahora. Intenta más tarde.",
        )

    return SuscripcionConfigOut(
        public_key=os.environ.get("WOMPI_PUBLIC_KEY", "").strip(),
        tokens_url=f"{wompi.base_url().rstrip('/')}/tokens/cards",
        acceptance_token=aceptacion["acceptance_token"],
        acceptance_permalink=aceptacion.get("acceptance_permalink"),
        personal_auth_token=aceptacion.get("personal_auth_token"),
        personal_auth_permalink=aceptacion.get("personal_auth_permalink"),
        sandbox=not wompi.es_produccion(),
    )


@router.post("/suscripcion/activar", response_model=SuscripcionOut)
def activar_suscripcion(
    payload: SuscripcionActivarIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_billing_admin),
    user: models.User = Depends(get_current_user),
) -> SuscripcionOut:
    """Guarda la tarjeta en Wompi y lanza el primer cobro del plan.

    Devuelve la suscripción **todavía sin activar**: Wompi responde `PENDING` y
    la confirmación llega por el webhook firmado (o por la reconciliación del
    tick). La pantalla muestra "estamos confirmando" y refresca sola. Activar
    aquí, con la respuesta del `POST`, sería activar sobre una promesa.
    """
    if not payload.acepta_terminos:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debes aceptar los términos para registrar la tarjeta",
        )

    if not wompi.suscripciones_habilitadas():
        logger.error("suscripcion: intento de activar sin llaves de Wompi")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El medio de pago no está disponible por ahora. Intenta más tarde.",
        )

    team = _team(db, member)

    # El tope va por CUENTA, no por IP: la IP la cambia cualquiera, el team es
    # lo que de verdad identifica a quien está probando tarjetas.
    if not _activaciones_limiter.allow(f"team:{team.id}"):
        logger.warning(
            "suscripcion: team %s superó el tope de intentos de registrar tarjeta",
            team.id,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Espera un momento antes de volver a intentar.",
        )

    sub = svc_suscripciones.obtener_o_crear(db, team.id)

    try:
        svc_suscripciones.activar(
            db,
            sub,
            token_tarjeta=payload.card_token,
            email_cliente=user.correo,
            user_id=user.id,
        )
    except svc_suscripciones.TokenInvalido:
        # El servicio ya loggeó lo que pasó SIN escribir el valor recibido.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El registro de la tarjeta no se completó. Vuelve a intentarlo.",
        )
    except svc_suscripciones.SuscripcionError as error:
        if error.codigo == "YA_ACTIVA":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="La suscripción ya está activa",
            )
        if error.codigo == "COBRO_EN_CURSO":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya hay un cobro en curso. Espera unos minutos.",
            )
        # Todo lo demás (rechazo del banco, Wompi caído) → mensaje genérico.
        # El código real quedó en el log del servicio.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo registrar la tarjeta. Verifica los datos o intenta con otra.",
        )

    db.refresh(sub)
    return _suscripcion_out(db, sub)


@router.post("/suscripcion/cancelar", response_model=SuscripcionOut)
def cancelar_suscripcion(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_billing_admin),
    user: models.User = Depends(get_current_user),
) -> SuscripcionOut:
    """Apaga el cobro automático y olvida la tarjeta.

    La segunda confirmación es de la pantalla (un modal), no de acá: este
    endpoint es la acción, y una acción que ya se pidió dos veces no se
    pregunta una tercera. No reembolsa el mes en curso.
    """
    team = _team(db, member)
    sub = svc_suscripciones.obtener(db, team.id)
    if sub is None or sub.status == models.SUBSCRIPTION_PENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No hay una suscripción activa que desactivar",
        )

    svc_suscripciones.cancelar(db, sub, user_id=user.id)
    return _suscripcion_out(db, sub)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

def _transaccion(payload: Dict[str, Any]) -> Dict[str, Any]:
    datos = (payload or {}).get("data") or {}
    tx = datos.get("transaction") or {}
    return tx if isinstance(tx, dict) else {}


@router.post("/wompi/webhook")
async def wompi_webhook(request: Request, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Recibe los eventos de Wompi. **Sin sesión** — el que autentica es la firma.

    Fail-closed en producción (CLAUDE.md #5): sin `WOMPI_EVENTS_SECRET` o con
    checksum inválido, 403 y no se procesa nada.

    Responde 200 en los casos "no hay nada que hacer" (evento de otro tipo,
    referencia desconocida, compra ya acreditada) para que Wompi no reintente
    algo que no va a cambiar. Reserva los errores para lo que sí conviene
    reintentar.
    """
    try:
        payload = await request.json()
    except Exception:
        logger.error("wompi.webhook: cuerpo no es JSON")
        raise HTTPException(status_code=400, detail="Payload inválido")

    if not isinstance(payload, dict) or not wompi.verificar_evento(payload):
        # Sin pistas al emisor sobre qué falló de la firma.
        raise HTTPException(status_code=403, detail="Firma inválida")

    if payload.get("event") != "transaction.updated":
        logger.info("wompi.webhook: evento ignorado tipo=%s", payload.get("event"))
        return {"ok": True, "ignorado": True}

    tx = _transaccion(payload)
    referencia = (tx.get("reference") or "").strip()
    estado_wompi = (tx.get("status") or "").strip().upper()
    tx_id = (tx.get("id") or "").strip() or None

    if not referencia:
        logger.error("wompi.webhook: evento sin referencia")
        return {"ok": True, "ignorado": True}

    # FOR UPDATE: si Wompi manda el mismo evento dos veces a la vez (o hay dos
    # tasks de ECS atendiendo), la segunda espera a que la primera confirme.
    # Sin esto, ambas leerían `pending` y ambas sumarían. En SQLite (tests) la
    # cláusula no se emite y no estorba.
    compra = (
        db.query(models.CreditPurchase)
        .filter(models.CreditPurchase.reference == referencia)
        .with_for_update()
        .first()
    )
    if compra is None:
        # Puede ser el cobro de una suscripción, que vive en otra tabla.
        resultado = _webhook_de_suscripcion(db, referencia, estado_wompi, tx_id, tx)
        if resultado is not None:
            return resultado
        # O una transacción de otro sistema sobre el mismo comercio.
        logger.warning("wompi.webhook: referencia desconocida")
        return {"ok": True, "ignorado": True}

    # Candado de idempotencia: una compra ya acreditada no se vuelve a tocar,
    # pase lo que pase con los reintentos.
    if compra.status == models.CREDIT_PURCHASE_APPROVED:
        logger.info(
            "wompi.webhook: compra %s ya estaba acreditada, no se suma de nuevo",
            compra.id,
        )
        return {"ok": True, "ya_acreditada": True}

    nuevo_estado = wompi.estado_interno(estado_wompi)
    if nuevo_estado is None:
        # PENDING u otro estado no final: no hay nada que decidir todavía.
        logger.info("wompi.webhook: compra %s sigue en %s", compra.id, estado_wompi)
        return {"ok": True, "pendiente": True}

    if nuevo_estado != models.CREDIT_PURCHASE_APPROVED:
        compra.status = nuevo_estado
        compra.provider_tx_id = tx_id or compra.provider_tx_id
        db.commit()
        logger.info("wompi.webhook: compra %s → %s", compra.id, nuevo_estado)
        return {"ok": True, "status": nuevo_estado}

    # --- APROBADA: se valida el monto antes de acreditar -------------------
    # El monto viene del evento, y el evento viene firmado; aun así se compara
    # con lo que registramos al crear el checkout. Si no cuadra, algo se salió
    # del guion (¿otra referencia?, ¿un monto editado?) y no se acredita.
    monto_evento = tx.get("amount_in_cents")
    if monto_evento is not None and int(monto_evento) != int(compra.amount_cents):
        logger.error(
            "wompi.webhook: monto no coincide compra_id=%s esperado=%s recibido=%s",
            compra.id,
            compra.amount_cents,
            monto_evento,
        )
        compra.status = models.CREDIT_PURCHASE_ERROR
        compra.provider_tx_id = tx_id or compra.provider_tx_id
        db.commit()
        return {"ok": True, "status": models.CREDIT_PURCHASE_ERROR}

    # Segunda vuelta en producción: preguntarle a Wompi con la llave privada.
    # Convierte "un POST que dice APPROVED" en "Wompi dice que está APPROVED".
    # Si la API no responde, se devuelve 503 A PROPÓSITO: Wompi reintenta hasta
    # 3 veces en 24 h, y es preferible reintentar que perder la acreditación.
    if _verificar_contra_api() and tx_id:
        real = wompi.consultar_transaccion(tx_id)
        if real is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo verificar el pago. Reintentar.",
            )
        if (real.get("status") or "").upper() != "APPROVED":
            logger.error(
                "wompi.webhook: el evento decía APPROVED pero la API no. compra_id=%s",
                compra.id,
            )
            raise HTTPException(status_code=403, detail="Firma inválida")

    team = db.query(models.Team).filter(models.Team.id == compra.team_id).first()
    if team is None:  # pragma: no cover - FK ON DELETE CASCADE lo impide
        logger.error("wompi.webhook: compra %s sin team", compra.id)
        return {"ok": True, "ignorado": True}

    team.message_credits = (team.message_credits or 0) + compra.messages
    compra.status = models.CREDIT_PURCHASE_APPROVED
    compra.provider_tx_id = tx_id or compra.provider_tx_id
    compra.credited_at = datetime.utcnow()
    db.commit()

    logger.info(
        "wompi.webhook: acreditados %s mensajes al team %s (compra %s), saldo=%s",
        compra.messages,
        team.id,
        compra.id,
        team.message_credits,
    )
    return {"ok": True, "status": models.CREDIT_PURCHASE_APPROVED}


def _webhook_de_suscripcion(
    db: Session,
    referencia: str,
    estado_wompi: str,
    tx_id: Optional[str],
    tx: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Procesa el evento si la referencia es la de un cobro de suscripción.

    Devuelve `None` si la referencia no es de acá (para que el llamador siga
    buscando), o el dict de respuesta si sí lo era.

    Mismos candados que la acreditación de mensajes, y por las mismas razones:
    `SELECT ... FOR UPDATE` para serializar dos webhooks simultáneos, salida
    temprana si el cobro ya está aprobado, verificación del monto contra lo que
    registramos, y re-consulta a la API de Wompi en producción antes de dar
    nada por bueno.
    """
    cobro = (
        db.query(models.SubscriptionCharge)
        .filter(models.SubscriptionCharge.reference == referencia)
        .with_for_update()
        .first()
    )
    if cobro is None:
        return None

    if cobro.status == models.SUBSCRIPTION_CHARGE_APPROVED:
        logger.info("wompi.webhook: cobro %s ya estaba aprobado", cobro.id)
        return {"ok": True, "ya_acreditada": True}

    nuevo_estado = wompi.estado_interno(estado_wompi)
    if nuevo_estado is None:
        logger.info("wompi.webhook: cobro %s sigue en %s", cobro.id, estado_wompi)
        return {"ok": True, "pendiente": True}

    # El monto viene firmado en el evento, pero se compara igual con lo que
    # registramos: si no cuadra, algo se salió del guion y no se activa nada.
    monto_evento = tx.get("amount_in_cents")
    if (
        nuevo_estado == models.SUBSCRIPTION_CHARGE_APPROVED
        and monto_evento is not None
        and int(monto_evento) != int(cobro.amount_cents)
    ):
        logger.error(
            "wompi.webhook: monto no coincide cobro_id=%s esperado=%s recibido=%s",
            cobro.id,
            cobro.amount_cents,
            monto_evento,
        )
        cobro.failure_code = "MONTO_NO_COINCIDE"
        svc_suscripciones.aplicar_estado(
            db, cobro, models.SUBSCRIPTION_CHARGE_ERROR, tx_id=tx_id
        )
        return {"ok": True, "status": models.SUBSCRIPTION_CHARGE_ERROR}

    # Segunda vuelta en producción: preguntarle a Wompi con la llave privada.
    # El 503 es a propósito — Wompi reintenta hasta 3 veces en 24 h, y es
    # preferible reintentar que activar una suscripción que no se pagó.
    if (
        nuevo_estado == models.SUBSCRIPTION_CHARGE_APPROVED
        and _verificar_contra_api()
        and tx_id
    ):
        real = wompi.consultar_transaccion(tx_id)
        if real is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No se pudo verificar el pago. Reintentar.",
            )
        if (real.get("status") or "").upper() != "APPROVED":
            logger.error(
                "wompi.webhook: el evento decía APPROVED pero la API no. cobro_id=%s",
                cobro.id,
            )
            raise HTTPException(status_code=403, detail="Firma inválida")

    svc_suscripciones.aplicar_estado(db, cobro, nuevo_estado, tx_id=tx_id)
    logger.info("wompi.webhook: cobro %s → %s", cobro.id, nuevo_estado)
    return {"ok": True, "status": nuevo_estado}


def _verificar_contra_api() -> bool:
    """¿Se re-consulta la transacción contra la API de Wompi antes de acreditar?

    Encendido por defecto en producción (llave `pub_prod_` o `APP_ENV=production`);
    apagado en desarrollo, donde no hay a quién preguntarle. `WOMPI_VERIFY_TX`
    fuerza cualquiera de los dos (`1`/`0`).
    """
    forzado = (os.getenv("WOMPI_VERIFY_TX") or "").strip()
    if forzado:
        return forzado == "1"
    return wompi.es_produccion() or (
        os.getenv("APP_ENV", "development") or ""
    ).strip().lower() in ("production", "prod")


@router.get("/transaccion/{transaccion_id}", response_model=EstadoPagoOut)
def estado_de_transaccion(
    transaccion_id: str,
    member: models.TeamMember = Depends(require_billing_admin),
):
    """Cómo le fue a un pago, para mostrárselo al que vuelve de Wompi.

    Con los **links de pago** el cliente regresa a `/pagos?id=<transaccion>` y
    hay que decirle algo. Esta consulta es **solo informativa**: no acredita
    nada ni toca el saldo. Los créditos los sigue habilitando el equipo tras
    conciliar el recaudo, porque un link de pago no le dice a la plataforma
    quién pagó — y el `id` de la URL lo puede escribir cualquiera.
    """
    datos = wompi.consultar_transaccion_publica(transaccion_id.strip())
    if not datos:
        # Ni confirmamos ni desmentimos: no se pudo saber.
        return EstadoPagoOut(estado="desconocido")

    bruto = str(datos.get("status") or "").upper()
    if bruto == "APPROVED":
        estado = "aprobado"
    elif bruto in ("DECLINED", "ERROR", "VOIDED"):
        estado = "rechazado"
    else:
        estado = "pendiente"

    monto = datos.get("amount_in_cents")
    return EstadoPagoOut(
        estado=estado,
        amount_cents=int(monto) if isinstance(monto, int) else None,
    )
