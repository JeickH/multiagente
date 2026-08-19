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
    CompraOut,
    PagosAccesoOut,
    PaqueteDesgloseOut,
    PaqueteOut,
    PaquetesOut,
    SaldoOut,
)
from ..services import creditos as svc_creditos
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
    desglose = svc_creditos.desglose_paquete(p.key)
    assert desglose is not None  # viene del propio catálogo
    return PaqueteOut(
        key=p.key,
        nombre=p.nombre,
        descripcion=p.descripcion,
        messages=p.messages,
        amount_cents=p.amount_cents,
        amount_cop=p.amount_cop,
        precio_por_mensaje_cop=p.precio_por_mensaje_cop,
        currency=p.currency,
        desglose=PaqueteDesgloseOut(
            costo_cop=desglose["costo_cop"],
            margen_objetivo_cop=desglose["margen_objetivo_cop"],
            neto_objetivo_cop=desglose["neto_objetivo_cop"],
            comision_wompi_cop=desglose["comision_wompi_cop"],
            neto_real_cop=desglose["neto_real_cop"],
            margen_real_cop=desglose["margen_real_cop"],
            margen_real_pct=desglose["margen_real_pct"],
            trm=desglose["trm"],
            trm_fecha=desglose["trm_fecha"],
            costo_usd_por_mensaje=desglose["costo_usd_por_mensaje"],
        ),
    )


@router.get("/paquetes", response_model=PaquetesOut)
def listar_paquetes(
    member: models.TeamMember = Depends(require_billing_admin),
) -> PaquetesOut:
    """Catálogo con precios y el desglose de en qué se va cada peso.

    El desglose (costo, margen, comisión de Wompi) es información de costos
    del negocio: sale acá porque el endpoint ya es solo para administradores.
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
        # Puede ser una transacción de otro sistema sobre el mismo comercio.
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
