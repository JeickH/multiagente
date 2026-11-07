"""Esquema de `conversation_sales` y marcadores nuevos de `conversations` (Sprint 36).

Se prueba lo que la base hace cumplir sola, sin pasar por endpoints:

  1. Una sola venta ACTIVA por conversación (`uq_conversation_sales_activa`,
     índice único parcial): la segunda choca, pero tras anular la primera se
     puede registrar la corregida.
  2. El CHECK `ck_conversation_sales_valor` rechaza 0 (y lo que pase del tope).
  3. `reclamos_abandono` nace en 0 sin que nadie lo ponga.
  4. El `__repr__` no deja ver ni el valor ni la nota.

Corre sobre SQLite con `create_all()`, igual que el resto de la suite: por eso
el CHECK y el índice parcial viven en el modelo y no solo en la migración.
Datos inventados (regla #8).
"""
from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models


@pytest.fixture
def db():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


@pytest.fixture
def conv(db):
    user = models.User(
        nombre="Prueba", tipo_documento="CC", documento="S36-T1",
        correo="s36@ejemplo.invalid", hashed_password="x",
    )
    db.add(user)
    db.flush()
    team = models.Team(nombre="Equipo prueba", owner_user_id=user.id)
    db.add(team)
    db.flush()
    c = models.Conversation(team_id=team.id, contact_wa_id="573000036101")
    db.add(c)
    db.commit()
    return c


def _venta(conv, valor: int = 1_200_000, **extra) -> models.ConversationSale:
    return models.ConversationSale(
        team_id=conv.team_id, conversation_id=conv.id, valor_cop=valor, **extra
    )


def test_una_sola_venta_activa_y_otra_tras_anular(db, conv):
    primera = _venta(conv)
    db.add(primera)
    db.commit()

    db.add(_venta(conv, 900_000))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    primera.anulada_at = datetime.utcnow()
    primera.motivo_anulacion = "valor mal digitado"
    db.commit()

    db.add(_venta(conv, 900_000))
    db.commit()

    activas = (
        db.query(models.ConversationSale)
        .filter_by(conversation_id=conv.id, anulada_at=None)
        .all()
    )
    assert [v.valor_cop for v in activas] == [900_000]
    assert db.query(models.ConversationSale).count() == 2


@pytest.mark.parametrize("valor", [0, -5, models.VENTA_VALOR_MAX_COP + 1])
def test_check_rechaza_valor_fuera_de_rango(db, conv, valor):
    db.add(_venta(conv, valor))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_check_acepta_el_tope(db, conv):
    db.add(_venta(conv, models.VENTA_VALOR_MAX_COP))
    db.commit()


def test_reclamos_abandono_nace_en_cero(db, conv):
    db.refresh(conv)
    assert conv.reclamos_abandono == 0
    assert conv.abandono_at is None
    assert conv.ultimo_mensaje_humano_at is None
    assert conv.cerrada_por_inactividad_at is None


def test_repr_no_muestra_valor_ni_nota(db, conv):
    venta = _venta(conv, 1_234_567, nota="cliente pidió factura a nombre de X")
    db.add(venta)
    db.commit()
    texto = repr(venta)
    assert "1234567" not in texto
    assert "factura" not in texto
    assert str(venta) == texto
