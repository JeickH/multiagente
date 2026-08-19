"""El handoff reparte los chats entre los asesores por turnos.

Lo que se fija aquí:
  - con dos asesores configurados, alterna: primero uno, después el otro;
  - el turno sobrevive al proceso (vive en `teams.handoff_turno`), porque en
    producción hay varias tasks de ECS y si el turno viviera en memoria cada
    una llevaría su propia cuenta y el reparto dejaría de alternar;
  - sin configuración, cae a los miembros con rol `agent` y, si no hay
    ninguno, al handle histórico `asesor_1` (un team viejo no cambia de
    comportamiento por esta feature).
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas


def _usuario(db, nombre: str, correo: str, documento: str) -> models.User:
    return crud.create_user(
        db,
        schemas.UserCreate(
            nombre=nombre,
            correo=correo,
            tipo_documento="CC",
            documento=documento,
            password="Clave-De-Prueba-1",
        ),
    )


@pytest.fixture
def db_session():
    """SQLite en memoria, igual que el resto de la suite: sin Postgres ni red."""
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


@pytest.fixture
def team_con_asesores(db_session):
    """Team con la rotación ["Julián", "Camila"] configurada."""
    owner = _usuario(db_session, "Dueña", "rot_owner@test.com", "ROT001")
    team = crud.create_team(db_session, "Agencia Rotación", owner)
    team.asesores_rotacion = ["Julián", "Camila"]
    db_session.add(team)
    db_session.commit()
    return team


def test_alterna_entre_los_dos_asesores(db_session, team_con_asesores):
    turnos = [crud.siguiente_asesor(db_session, team_con_asesores) for _ in range(4)]
    assert turnos == ["Julián", "Camila", "Julián", "Camila"]


def test_el_turno_queda_guardado_en_la_base(db_session, team_con_asesores):
    """Releer el team desde la base debe conservar el turno.

    Es el caso real: cada mensaje entrante lo atiende un proceso distinto, que
    construye el objeto Team de cero.
    """
    primero = crud.siguiente_asesor(db_session, team_con_asesores)
    assert primero == "Julián"

    db_session.expire_all()
    team = db_session.query(models.Team).get(team_con_asesores.id)
    assert team.handoff_turno == 1

    segundo = crud.siguiente_asesor(db_session, team)
    assert segundo == "Camila"


def test_un_solo_asesor_no_gasta_turno(db_session, team_con_asesores):
    """Con un asesor no hay a quién alternar: siempre el mismo, sin avanzar."""
    team_con_asesores.asesores_rotacion = ["Julián"]
    db_session.add(team_con_asesores)
    db_session.commit()

    assert crud.siguiente_asesor(db_session, team_con_asesores) == "Julián"
    assert crud.siguiente_asesor(db_session, team_con_asesores) == "Julián"
    assert team_con_asesores.handoff_turno == 0


def test_sin_configurar_usa_los_miembros_agent(db_session):
    owner = _usuario(db_session, "Dueño2", "rot_owner2@test.com", "ROT002")
    team = crud.create_team(db_session, "Agencia Sin Config", owner)
    asesor = _usuario(db_session, "Paula", "rot_agente@test.com", "ROT003")
    crud.add_member_to_team(db_session, team, asesor, role="agent")

    assert crud.asesores_del_team(db_session, team) == ["Paula"]


def test_team_sin_asesores_cae_al_handle_historico(db_session):
    """Un team viejo, sin rotación ni miembros `agent`, sigue como antes."""
    owner = _usuario(db_session, "Dueño3", "rot_owner3@test.com", "ROT004")
    team = crud.create_team(db_session, "Agencia Vacía", owner)

    assert crud.asesores_del_team(db_session, team) == ["asesor_1"]
    assert crud.siguiente_asesor(db_session, team) == "asesor_1"
