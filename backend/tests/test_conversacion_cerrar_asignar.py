"""Cerrar una conversación y reasignarla: quién puede, y qué NO se lleva puesto.

Las dos operaciones tocan la misma fila y es fácil confundirlas, así que lo que
se fija acá es sobre todo lo que cada una **no** hace:

1. **Cerrar no devuelve el chat al bot.** La puerta del motor es
   `assigned_to != "bot"`, no el estado (`bot_router` línea 108). Si cerrar
   pusiera `assigned_to='bot'` de paso, cada vez que un asesor archivara un
   chat atendido el bot se le metería encima al siguiente mensaje del cliente.

2. **Reasignar valida el destino contra el team.** Aceptar texto libre
   reintroduce #376/#377: un nombre que no es de nadie llega tal cual a la
   etiqueta 👤 de la bandeja y el chat queda en una casilla que nadie mira.

3. **Devolver al bot limpia la etiqueta.** La etiqueta es la señal de por qué
   le llegó frío a un asesor; con el chat de vuelta en el motor ya no aplica, y
   si se queda puesta la bandeja lo sigue mostrando como pendiente de alguien.

4. **El aislamiento por tenant.** Ninguna de las dos puede tocar una
   conversación de otro equipo, ni siquiera para enterarse de que existe: 404,
   no 403.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.routers import mensajes

CLAVE = "Clave-De-Prueba-1"


@pytest.fixture
def db_session():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sesion = Sesion()
    yield sesion
    sesion.close()
    engine.dispose()


def _usuario(db, nombre, correo, documento):
    return crud.create_user(
        db,
        schemas.UserCreate(
            nombre=nombre, correo=correo, tipo_documento="CC",
            documento=documento, password=CLAVE,
        ),
    )


@pytest.fixture
def equipo(db_session):
    """Team con dos asesores configurados y su membresía de owner."""
    owner = _usuario(db_session, "Dueña", "cierre_owner@test.com", "CIE001")
    team = crud.create_team(db_session, "Agencia Cierre", owner)
    team.asesores_rotacion = ["Alexandra", "Camila"]
    db_session.add(team)
    db_session.commit()
    return crud.get_membership_for_user(db_session, owner)


@pytest.fixture
def otro_equipo(db_session):
    """Un segundo tenant, para probar que no se ven entre sí."""
    ajeno = _usuario(db_session, "Ajeno", "cierre_ajeno@test.com", "CIE002")
    crud.create_team(db_session, "Otra Agencia", ajeno)
    return crud.get_membership_for_user(db_session, ajeno)


def _conversacion(db, team_id, *, estado="open", asignado="bot", etiqueta=None):
    conv = models.Conversation(
        team_id=team_id,
        contact_wa_id="573000000001",
        contact_name="Cliente",
        status=estado,
        assigned_to=asignado,
        etiqueta=etiqueta,
        last_message_at=datetime(2026, 8, 29, 12, 0, 0),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


# ───────────────────────── cerrar ─────────────────────────
def test_el_asesor_cierra_la_conversacion(db_session, equipo):
    conv = _conversacion(db_session, equipo.team_id)

    out = mensajes.close_conversation(conv.id, db=db_session, member=equipo)

    assert out.status == "closed"
    db_session.refresh(conv)
    assert conv.status == "closed"


def test_cerrar_no_le_devuelve_el_chat_al_bot(db_session, equipo):
    """El dueño humano se mantiene: si no, el bot se le mete al siguiente mensaje."""
    conv = _conversacion(db_session, equipo.team_id, asignado="Alexandra")

    out = mensajes.close_conversation(conv.id, db=db_session, member=equipo)

    assert out.status == "closed"
    assert out.assigned_to == "Alexandra"
    db_session.refresh(conv)
    assert conv.assigned_to == "Alexandra"


def test_cerrar_una_conversacion_de_otro_equipo_da_404(db_session, equipo, otro_equipo):
    conv = _conversacion(db_session, equipo.team_id)

    with pytest.raises(HTTPException) as exc:
        mensajes.close_conversation(conv.id, db=db_session, member=otro_equipo)

    assert exc.value.status_code == 404
    db_session.refresh(conv)
    assert conv.status == "open"


# ───────────────────────── asignar ─────────────────────────
def test_el_admin_reasigna_a_un_asesor_del_equipo(db_session, equipo):
    conv = _conversacion(db_session, equipo.team_id, asignado="Camila")

    out = mensajes.assign_conversation(
        conv.id,
        schemas.ConversationAsignarIn(assigned_to="Alexandra"),
        db=db_session,
        member=equipo,
    )

    assert out.assigned_to == "Alexandra"
    db_session.refresh(conv)
    assert conv.assigned_to == "Alexandra"


def test_devolver_al_bot_limpia_la_etiqueta_y_reabre(db_session, equipo):
    conv = _conversacion(
        db_session, equipo.team_id,
        estado="closed", asignado="Camila", etiqueta="conversación abandonada",
    )

    out = mensajes.assign_conversation(
        conv.id,
        schemas.ConversationAsignarIn(assigned_to="bot"),
        db=db_session,
        member=equipo,
    )

    assert out.assigned_to == "bot"
    assert out.etiqueta is None
    assert out.status == "open"
    db_session.refresh(conv)
    assert (conv.assigned_to, conv.etiqueta, conv.status) == ("bot", None, "open")


def test_no_se_puede_asignar_a_alguien_que_no_es_del_equipo(db_session, equipo):
    """#376/#377: un nombre libre deja el chat en una casilla fantasma."""
    conv = _conversacion(db_session, equipo.team_id, asignado="Camila")

    with pytest.raises(HTTPException) as exc:
        mensajes.assign_conversation(
            conv.id,
            schemas.ConversationAsignarIn(assigned_to="asesor_1"),
            db=db_session,
            member=equipo,
        )

    assert exc.value.status_code == 422
    db_session.refresh(conv)
    assert conv.assigned_to == "Camila"


def test_asignar_sin_destino_es_422(db_session, equipo):
    conv = _conversacion(db_session, equipo.team_id)

    with pytest.raises(HTTPException) as exc:
        mensajes.assign_conversation(
            conv.id,
            schemas.ConversationAsignarIn(assigned_to="   "),
            db=db_session,
            member=equipo,
        )

    assert exc.value.status_code == 422


def test_asignar_una_conversacion_de_otro_equipo_da_404(db_session, equipo, otro_equipo):
    conv = _conversacion(db_session, equipo.team_id, asignado="Camila")

    with pytest.raises(HTTPException) as exc:
        mensajes.assign_conversation(
            conv.id,
            schemas.ConversationAsignarIn(assigned_to="bot"),
            db=db_session,
            member=otro_equipo,
        )

    assert exc.value.status_code == 404
    db_session.refresh(conv)
    assert conv.assigned_to == "Camila"


def test_los_asesores_que_ve_el_selector_son_los_del_team(db_session, equipo):
    """La misma lista que reparte el handoff: lo que el admin ve es lo que hay."""
    assert mensajes.list_assignees(db=db_session, member=equipo) == [
        "Alexandra", "Camila",
    ]


# ───────────────────────── reabrir ─────────────────────────
def test_el_asesor_reabre_lo_que_cerro(db_session, equipo):
    """Cerrar era un camino de una sola dirección: un click de más y el asesor
    no tenía cómo recuperar el chat sin ir a buscar al dueño de la cuenta."""
    conv = _conversacion(db_session, equipo.team_id, estado="closed")

    out = mensajes.reopen_conversation(conv.id, db=db_session, member=equipo)

    assert out.status == "open"
    db_session.refresh(conv)
    assert conv.status == "open"


def test_reabrir_no_le_devuelve_el_chat_al_bot(db_session, equipo):
    """Simétrico de cerrar, y por el mismo motivo: si reabrir reasignara de
    paso, el motor se le metería encima al asesor que sólo se estaba
    corrigiendo."""
    conv = _conversacion(
        db_session, equipo.team_id,
        estado="closed", asignado="Alexandra", etiqueta="conversación abandonada",
    )

    out = mensajes.reopen_conversation(conv.id, db=db_session, member=equipo)

    assert out.status == "open"
    assert out.assigned_to == "Alexandra"
    assert out.etiqueta == "conversación abandonada", "la etiqueta no es del estado"


def test_reabrir_una_conversacion_de_otro_equipo_da_404(db_session, equipo, otro_equipo):
    conv = _conversacion(db_session, equipo.team_id, estado="closed")

    with pytest.raises(HTTPException) as exc:
        mensajes.reopen_conversation(conv.id, db=db_session, member=otro_equipo)

    assert exc.value.status_code == 404
    db_session.refresh(conv)
    assert conv.status == "closed"
