"""Una cuenta desactivada no entra, y la que ya estaba adentro se cae.

Lo segundo es lo que importa: los tokens duran 2 horas desde el 19-ago-2026, así
que si `activo` solo se mirara en el login, desactivar a alguien lo dejaría
trabajando dos horas más. Por eso se revisa en cada request.

El caso real: `arranquemospues.asesor@gmail.com`, la cuenta de asesor anterior
de Arranquemos Pues, reemplazada por `arranquemospues.ventas@outlook.com`.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, dependencies, models, schemas
from app.routers import auth as auth_router

CLAVE = "Clave-De-Prueba-1"


@pytest.fixture
def jwt_de_prueba():
    """Firma y verificación con una llave propia del test.

    `SECRET_KEY` y `ALGORITHM` se leen del entorno al importar el módulo, y en
    el CI no hay `.env`: sin esto, `ALGORITHM` llega en `None` y firmar el token
    revienta con "Algorithm None not supported". El test no tiene por qué
    depender de la configuración de la máquina donde corre.
    """
    with patch.object(auth_router, "SECRET_KEY", "secreto-de-prueba"), \
         patch.object(auth_router, "ALGORITHM", "HS256"), \
         patch.object(dependencies, "SECRET_KEY", "secreto-de-prueba"), \
         patch.object(dependencies, "ALGORITHM", "HS256"):
        yield


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


@pytest.fixture
def asesor(db_session):
    return crud.create_user(
        db_session,
        schemas.UserCreate(
            nombre="Asesor Viejo", correo="asesor_viejo@test.com",
            tipo_documento="CC", documento="DESACT01", password=CLAVE,
        ),
    )


class TestPorDefectoTodoSigueIgual:
    def test_una_cuenta_nueva_nace_activa(self, asesor):
        """Nadie pierde el acceso porque se aplique la columna."""
        assert asesor.activo is True

    def test_y_puede_entrar(self, db_session, asesor):
        assert crud.authenticate_user(db_session, asesor.correo, CLAVE) is not False


class TestDesactivada:
    def test_no_entra_ni_con_la_clave_correcta(self, db_session, asesor):
        asesor.activo = False
        db_session.commit()
        assert crud.authenticate_user(db_session, asesor.correo, CLAVE) is False

    def test_el_error_no_delata_que_el_correo_existe(self, db_session, asesor):
        """Devuelve lo mismo que un correo inexistente: `False`. Decir "esa
        cuenta está desactivada" le confirma a un desconocido que existe."""
        asesor.activo = False
        db_session.commit()
        desactivada = crud.authenticate_user(db_session, asesor.correo, CLAVE)
        inexistente = crud.authenticate_user(db_session, "nadie@test.com", CLAVE)
        assert desactivada == inexistente == False   # noqa: E712

    def test_el_token_que_ya_tenia_deja_de_servir(
        self, db_session, asesor, jwt_de_prueba
    ):
        """El corazón del cambio: con tokens de 2 horas, revisar `activo` solo
        en el login dejaría a la cuenta trabajando dos horas más."""
        token = auth_router.create_access_token({"sub": asesor.correo})
        credenciales = type("C", (), {"credentials": token})()

        # Con la cuenta activa, el token vale.
        assert dependencies.get_current_user(credenciales, db_session).id == asesor.id

        asesor.activo = False
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            dependencies.get_current_user(credenciales, db_session)
        assert exc.value.status_code == 401


class TestVolverAPrenderla:
    def test_se_reactiva_con_un_update(self, db_session, asesor):
        asesor.activo = False
        db_session.commit()
        assert crud.authenticate_user(db_session, asesor.correo, CLAVE) is False

        asesor.activo = True
        db_session.commit()
        assert crud.authenticate_user(db_session, asesor.correo, CLAVE) is not False

    def test_desactivar_no_borra_al_usuario_ni_su_membresia(self, db_session, asesor):
        """Los mensajes y el rastro de quién atendió qué cuelgan del usuario."""
        owner = crud.create_user(
            db_session,
            schemas.UserCreate(
                nombre="Dueña", correo="desact_owner@test.com",
                tipo_documento="CC", documento="DESACT02", password=CLAVE,
            ),
        )
        team = crud.create_team(db_session, "Agencia", owner)
        crud.add_member_to_team(db_session, team, asesor, role="agent")

        asesor.activo = False
        db_session.commit()

        assert crud.get_user_by_email(db_session, asesor.correo) is not None
        assert crud.get_membership_for_user(db_session, asesor) is not None
