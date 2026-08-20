"""La bandeja pagina en la base, y los filtros van en la misma consulta.

Lo que se protege acá no es que la lista salga en orden sino dos cosas que se
rompen calladas:

1. **Que el filtro se aplique ANTES de paginar.** Si se filtrara en el
   navegador sobre una página ya recortada, "20 por página" filtraría dentro de
   esas 20: el usuario vería "no hay conversaciones pendientes" teniendo
   pendientes tres páginas más abajo. Es un bug que no se ve —la pantalla queda
   perfecta, solo que miente.

2. **Que el adelanto no vuelva a ser un N+1.** `conv.messages[-1]` con la
   relación en lazy es una consulta por conversación, y la bandeja se refresca
   sola cada 8 segundos. Se cuenta el número de consultas, porque la única
   señal de que volvió es que todo sigue funcionando más lento.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
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


@pytest.fixture
def equipo(db_session):
    user = crud.create_user(
        db_session,
        schemas.UserCreate(
            nombre="Dueña", correo="duena@test.com", tipo_documento="CC",
            documento="MSG-0001", password=CLAVE,
        ),
    )
    team = crud.create_team(db_session, nombre="Equipo", owner=user)
    return crud.get_membership_for_user(db_session, user)


def _conversacion(db, team_id, *, i, estado="open", nombre=None, mensajes=2):
    """Una conversación con sus mensajes. La `i` la ubica en el tiempo."""
    cuando = datetime(2026, 8, 18, 9, 0, 0) + timedelta(minutes=10 * i)
    conv = models.Conversation(
        team_id=team_id,
        contact_wa_id=f"57900{i:07d}",
        contact_name=nombre,
        status=estado,
        last_message_at=cuando,
        created_at=cuando - timedelta(hours=1),
    )
    db.add(conv)
    db.flush()
    for t in range(mensajes):
        db.add(models.Message(
            conversation_id=conv.id,
            direction="inbound" if t % 2 == 0 else "outbound",
            content=f"mensaje {t} de la conversación {i}",
            created_at=cuando - timedelta(minutes=mensajes - t),
        ))
    db.commit()
    return conv


def _listar(db, member, **kw):
    kw.setdefault("estado", None)
    kw.setdefault("busqueda", None)
    kw.setdefault("limite", 20)
    kw.setdefault("pagina", 1)
    return mensajes.list_conversations(db=db, member=member, **kw)


class TestPaginacion:
    def test_las_paginas_recorren_todo_sin_repetir(self, db_session, equipo):
        for i in range(10):
            _conversacion(db_session, equipo.team_id, i=i)

        recorrido = []
        for pagina in (1, 2, 3, 4, 5):
            salida = _listar(db_session, equipo, limite=2, pagina=pagina)
            assert len(salida.conversaciones) == 2
            recorrido += [c.id for c in salida.conversaciones]

        assert len(set(recorrido)) == 10
        # De la más reciente a la más vieja: la última creada va primero.
        assert recorrido == sorted(recorrido, reverse=True)

    def test_el_total_es_el_del_filtro_y_no_el_de_la_pagina(self, db_session, equipo):
        for i in range(10):
            _conversacion(db_session, equipo.team_id, i=i)

        salida = _listar(db_session, equipo, limite=3)
        assert len(salida.conversaciones) == 3
        assert salida.total == 10
        assert salida.pagina == 1
        assert salida.por_pagina == 3

    def test_una_pagina_pasada_del_final_viene_vacia(self, db_session, equipo):
        _conversacion(db_session, equipo.team_id, i=0)
        salida = _listar(db_session, equipo, limite=20, pagina=99)
        assert salida.conversaciones == []
        assert salida.total == 1


class TestFiltrosAntesDePaginar:
    """El caso que motivó todo: paginar tiene que operar sobre lo filtrado."""

    def test_el_estado_filtra_en_toda_la_cuenta_no_solo_en_la_primera_pagina(
        self, db_session, equipo
    ):
        # 25 abiertas, y las pendientes AL FINAL: fuera de la primera página.
        for i in range(25):
            _conversacion(db_session, equipo.team_id, i=i, estado="open")
        for i in range(25, 30):
            _conversacion(db_session, equipo.team_id, i=i, estado="pending")

        salida = _listar(db_session, equipo, estado="pending", limite=3, pagina=1)

        # Si el filtro se aplicara después de recortar, esto vendría vacío.
        assert len(salida.conversaciones) == 3
        assert salida.total == 5
        assert {c.status for c in salida.conversaciones} == {"pending"}

    def test_el_total_de_un_filtro_sin_resultados_es_cero(self, db_session, equipo):
        _conversacion(db_session, equipo.team_id, i=0, estado="open")
        salida = _listar(db_session, equipo, estado="closed")
        assert salida.conversaciones == []
        assert salida.total == 0

    def test_un_estado_inventado_se_rechaza(self, db_session, equipo):
        """No se ignora en silencio: devolver "todas" ante un filtro que no
        existe le muestra al usuario cosas que pidió excluir."""
        with pytest.raises(HTTPException) as e:
            _listar(db_session, equipo, estado="archivado")
        assert e.value.status_code == 400

    def test_la_busqueda_encuentra_por_nombre(self, db_session, equipo):
        _conversacion(db_session, equipo.team_id, i=0, nombre="Marcela Rojas")
        _conversacion(db_session, equipo.team_id, i=1, nombre="Bruno Gómez")

        salida = _listar(db_session, equipo, busqueda="rojas")
        assert [c.contact_name for c in salida.conversaciones] == ["Marcela Rojas"]
        assert salida.total == 1

    def test_la_busqueda_encuentra_por_numero_aunque_no_haya_nombre(
        self, db_session, equipo
    ):
        """`lower(NULL) LIKE ...` es NULL: sin el OR, una conversación sin
        nombre no aparecía ni buscando su propio número."""
        conv = _conversacion(db_session, equipo.team_id, i=7, nombre=None)

        salida = _listar(db_session, equipo, busqueda=conv.contact_wa_id[-5:])
        assert [c.id for c in salida.conversaciones] == [conv.id]

    def test_la_busqueda_y_el_estado_se_combinan(self, db_session, equipo):
        _conversacion(db_session, equipo.team_id, i=0, nombre="Ana Vélez", estado="open")
        _conversacion(db_session, equipo.team_id, i=1, nombre="Ana Rojas", estado="closed")

        salida = _listar(db_session, equipo, busqueda="ana", estado="closed")
        assert [c.contact_name for c in salida.conversaciones] == ["Ana Rojas"]
        assert salida.total == 1


class TestSinNMasUno:
    def test_el_adelanto_no_cuesta_una_consulta_por_conversacion(
        self, db_session, equipo
    ):
        """Con 40 conversaciones el número de consultas no puede moverse.

        Es la prueba que se cae el día que alguien vuelva a poner
        `conv.messages[-1]` en el bucle.
        """
        for i in range(40):
            _conversacion(db_session, equipo.team_id, i=i, mensajes=5)

        conteo = {"n": 0}

        @event.listens_for(Engine, "after_cursor_execute")
        def _contar(conn, cursor, statement, params, context, executemany):
            conteo["n"] += 1

        try:
            db_session.expire_all()
            salida = _listar(db_session, equipo, limite=40)
        finally:
            event.remove(Engine, "after_cursor_execute", _contar)

        assert len(salida.conversaciones) == 40
        # count + página + previews. El techo deja aire para un JOIN más, pero
        # no para 40 consultas.
        assert conteo["n"] <= 5, f"{conteo['n']} consultas: volvió el N+1"

    def test_el_adelanto_es_el_ultimo_mensaje(self, db_session, equipo):
        conv = _conversacion(db_session, equipo.team_id, i=0, mensajes=3)
        db_session.add(models.Message(
            conversation_id=conv.id, direction="outbound",
            content="este es el último", created_at=datetime(2026, 8, 19, 10, 0, 0),
        ))
        db_session.commit()

        salida = _listar(db_session, equipo)
        assert salida.conversaciones[0].last_message_preview == "este es el último"

    def test_una_conversacion_sin_mensajes_no_revienta(self, db_session, equipo):
        _conversacion(db_session, equipo.team_id, i=0, mensajes=0)
        salida = _listar(db_session, equipo)
        assert salida.conversaciones[0].last_message_preview is None


class TestAislamiento:
    def test_no_se_ven_las_conversaciones_de_otro_team(self, db_session, equipo):
        otro = crud.create_user(
            db_session,
            schemas.UserCreate(
                nombre="Ajeno", correo="ajeno@test.com", tipo_documento="CC",
                documento="MSG-0002", password=CLAVE,
            ),
        )
        otro_team = crud.create_team(db_session, nombre="Ajeno", owner=otro)
        _conversacion(db_session, otro_team.id, i=0, nombre="De la otra cuenta")
        _conversacion(db_session, equipo.team_id, i=1, nombre="Mía")

        salida = _listar(db_session, equipo)
        assert [c.contact_name for c in salida.conversaciones] == ["Mía"]
        assert salida.total == 1
