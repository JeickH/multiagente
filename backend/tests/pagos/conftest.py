"""Fixtures del módulo de pagos.

Todo corre contra **SQLite en memoria**: la suite no necesita Postgres, ni
Docker, ni red — condición para que el CI la corra en cada push sin costo.

Dos cosas que hay que saber para escribir un test acá:

- **Las llaves de Wompi son de mentira y las pone la fixture.** `wompi.py` lee
  el entorno en cada llamada (no al importarse) justamente para que se puedan
  poner con `monkeypatch`. Ninguna llave real aparece en este repo, que es
  público.
- **El router se monta en una app propia**, no se importa `app.main`: ese
  módulo hace `Base.metadata.create_all(bind=engine)` al importarse, o sea que
  exigiría un Postgres vivo solo para levantar el cliente.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Llaves de juguete. El formato imita al real (`pub_test_`) porque
# `wompi.es_produccion()` mira el prefijo, y un `pub_prod_` acá encendería el
# fail-closed y la verificación contra la API en medio de los tests.
PUBLIC_KEY = "pub_test_llave_de_prueba"
PRIVATE_KEY = "prv_test_llave_de_prueba"
INTEGRITY_SECRET = "test_integrity_secreto"
EVENTS_SECRET = "test_events_secreto"


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    """SQLite en memoria compartida por todas las sesiones del test."""
    from app.database import Base

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def Sesion(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(Sesion):
    sesion = Sesion()
    yield sesion
    sesion.close()


# ---------------------------------------------------------------------------
# Entorno
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def llaves_wompi(monkeypatch):
    """Llaves de prueba en el entorno. Autouse: ningún test toca Wompi real.

    `WOMPI_BASE_URL` apunta al sandbox y `WOMPI_VERIFY_TX=0` apaga la
    re-consulta contra la API: en los tests no hay red, y lo que se prueba acá
    es la lógica de acreditación, no el cliente HTTP.
    """
    monkeypatch.setenv("WOMPI_PUBLIC_KEY", PUBLIC_KEY)
    monkeypatch.setenv("WOMPI_PRIVATE_KEY", PRIVATE_KEY)
    monkeypatch.setenv("WOMPI_INTEGRITY_SECRET", INTEGRITY_SECRET)
    monkeypatch.setenv("WOMPI_EVENTS_SECRET", EVENTS_SECRET)
    monkeypatch.setenv("WOMPI_BASE_URL", "https://sandbox.wompi.co/v1")
    monkeypatch.setenv("WOMPI_VERIFY_TX", "0")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("FRONTEND_BASE_URL", "https://app.glomabeauty.com")


# ---------------------------------------------------------------------------
# Datos: un team con su dueño y su asesor
# ---------------------------------------------------------------------------

@pytest.fixture
def team(db):
    """Un team con owner y un asesor, con los permisos por defecto de cada uno.

    Los permisos del asesor salen de `ASESOR_DEFAULT_PERMISSIONS` (la misma
    constante que usa la app), no de una lista copiada: si mañana alguien le
    enciende `can_manage_billing` por defecto, este test se entera.
    """
    from app import models

    dueño = models.User(
        nombre="Dueña de la cuenta",
        tipo_documento="CC",
        documento="1000001",
        correo="duena@ejemplo.com",
        hashed_password="x",
    )
    asesor = models.User(
        nombre="Asesor",
        tipo_documento="CC",
        documento="1000002",
        correo="asesor@ejemplo.com",
        hashed_password="x",
    )
    db.add_all([dueño, asesor])
    db.commit()

    equipo = models.Team(nombre="Equipo de prueba", owner_user_id=dueño.id)
    db.add(equipo)
    db.commit()

    m_dueño = models.TeamMember(team_id=equipo.id, user_id=dueño.id, role="owner")
    m_asesor = models.TeamMember(team_id=equipo.id, user_id=asesor.id, role="agent")
    db.add_all([m_dueño, m_asesor])
    db.commit()

    for clave, activo in models.ASESOR_DEFAULT_PERMISSIONS.items():
        db.add(
            models.TeamPermission(
                team_member_id=m_asesor.id, permission_key=clave, enabled=activo
            )
        )
    db.commit()

    return {
        "team": equipo,
        "dueño": dueño,
        "asesor": asesor,
        "membresia_asesor": m_asesor,
    }


# ---------------------------------------------------------------------------
# Clientes HTTP
# ---------------------------------------------------------------------------

def _app_de_pagos(Sesion, usuario):
    from fastapi import FastAPI

    from app.dependencies import get_current_user, get_db
    from app.routers import pagos as router_pagos

    app = FastAPI()
    app.include_router(router_pagos.router)

    def _get_db():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    if usuario is not None:
        app.dependency_overrides[get_current_user] = lambda: usuario
    return app


@pytest.fixture
def admin(Sesion, team):
    """Cliente autenticado como el DUEÑO de la cuenta."""
    from fastapi.testclient import TestClient

    with TestClient(_app_de_pagos(Sesion, team["dueño"])) as c:
        yield c


@pytest.fixture
def asesor(Sesion, team):
    """Cliente autenticado como el ASESOR (rol `agent`, sin `can_manage_billing`)."""
    from fastapi.testclient import TestClient

    with TestClient(_app_de_pagos(Sesion, team["asesor"])) as c:
        yield c


@pytest.fixture
def anonimo(Sesion, team):
    """Cliente SIN sesión. Solo sirve para el webhook, que no lleva auth."""
    from fastapi.testclient import TestClient

    with TestClient(_app_de_pagos(Sesion, None)) as c:
        yield c


# ---------------------------------------------------------------------------
# Eventos de Wompi
# ---------------------------------------------------------------------------

def evento_wompi(
    referencia: str,
    estado: str = "APPROVED",
    monto_centavos: int = 8_070_000,
    tx_id: str = "12345-1600052765-70017",
    timestamp: int = 1_530_291_411,
    secreto: Optional[str] = EVENTS_SECRET,
    propiedades: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Un evento `transaction.updated` con su checksum bien calculado.

    Firmarlo acá con la MISMA receta que documenta Wompi (y no reutilizando la
    función del servicio) es a propósito: si alguien cambia el orden de la
    concatenación en `wompi.verificar_evento`, este helper deja de cuadrar y
    los tests lo cazan. Un test que firma con la función que prueba no prueba
    nada.

    `secreto=None` produce un evento con checksum inválido.
    """
    propiedades = propiedades or [
        "transaction.id",
        "transaction.status",
        "transaction.amount_in_cents",
    ]
    transaccion = {
        "id": tx_id,
        "status": estado,
        "amount_in_cents": monto_centavos,
        "reference": referencia,
        "currency": "COP",
        "customer_email": "cliente@ejemplo.com",
    }
    valores = {
        "transaction.id": tx_id,
        "transaction.status": estado,
        "transaction.amount_in_cents": str(monto_centavos),
        "transaction.reference": referencia,
    }
    cadena = "".join(valores.get(p, "") for p in propiedades)
    cadena += str(timestamp) + (secreto or "")
    checksum = hashlib.sha256(cadena.encode("utf-8")).hexdigest()
    if secreto is None:
        checksum = "0" * 64  # firma que no corresponde a ningún secreto

    return {
        "event": "transaction.updated",
        "data": {"transaction": transaccion},
        "environment": "test",
        "signature": {"properties": propiedades, "checksum": checksum},
        "timestamp": timestamp,
        "sent_at": "2026-08-19T16:45:05.000Z",
    }
