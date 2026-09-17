"""Lo que SQLite no puede contestar: JSONB, el índice parcial y la zona horaria.

El resto de la suite corre en SQLite en memoria —gratis, en milisegundos, sin
depender de que alguien tenga una base levantada—, pero hay tres cosas del
esquema que ahí no existen y que si se rompen se rompen en producción:

  * los operadores JSONB (`@>`) con los que se busca dentro de `valores`;
  * el índice parcial de `bot_producto_filas`, que es el que sostiene la
    consulta caliente del bot;
  * la fecha de Colombia, que este módulo calcula con un `timezone(-5)` fijo y
    el motor sabe de verdad.

Van con el marcador `postgres` y **no corren por defecto**: el CI no tiene una
base al lado y el primer push se caería. Para correrlas:

    pytest --con-postgres -m postgres

La base sale de `POSTGRES_TEST_URL` o de las variables `POSTGRES_*` del
backend (el `docker-compose` local). Nada de esto toca RDS.

Todo se crea dentro de un **esquema temporal** que se borra al final: aunque se
apunte por error a una base con datos, no se le toca una tabla.
"""
from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app import models
from app.services import productos

from tests.productos.conftest import HOY, crear_cuenta, crear_juguete

pytestmark = pytest.mark.postgres

ESQUEMA = "productos_test_" + uuid.uuid4().hex[:8]


def _url() -> str:
    """La URL de la base de pruebas. Nunca se imprime: lleva la contraseña."""
    url = os.getenv("POSTGRES_TEST_URL")
    if url:
        return url
    usuario = os.getenv("POSTGRES_USER") or "postgres"
    clave = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST") or "localhost"
    puerto = os.getenv("POSTGRES_PORT") or "5432"
    base = os.getenv("POSTGRES_DB") or "multiagente_db"
    credencial = f"{usuario}:{clave}" if clave else usuario
    return f"postgresql+psycopg2://{credencial}@{host}:{puerto}/{base}"


@pytest.fixture(scope="module")
def motor():
    from app.database import Base

    url = _url()
    try:
        base = create_engine(url)
        with base.connect() as conexion:
            conexion.execute(text(f'CREATE SCHEMA "{ESQUEMA}"'))
            conexion.execute(text("COMMIT"))
    except Exception as error:      # noqa: BLE001
        # El detalle va al mensaje del skip sin la URL: ahí viaja la contraseña.
        pytest.skip(f"no se pudo preparar Postgres ({type(error).__name__})")

    engine = create_engine(
        url, connect_args={"options": f"-csearch_path={ESQUEMA}"}
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
    with base.connect() as conexion:
        conexion.execute(text(f'DROP SCHEMA "{ESQUEMA}" CASCADE'))
        conexion.execute(text("COMMIT"))
    base.dispose()


@pytest.fixture
def db_pg(motor):
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=motor)()
    yield sesion
    sesion.rollback()
    sesion.close()


@pytest.fixture
def juguete_pg(db_pg):
    team_id, bot_id = crear_cuenta(db_pg, uuid.uuid4().hex[:8])
    producto = crear_juguete(db_pg, team_id=team_id, bot_id=bot_id)
    return producto, team_id, bot_id


class TestJSONB:
    def test_se_puede_buscar_por_dentro_de_valores(self, db_pg, juguete_pg):
        """`valores @> '{"promocion": …}'` — lo que SQLite no sabe hacer.

        Es lo que le va a permitir al importador (fase 4) y al panel preguntar
        «¿cuáles filas traen esta columna?» sin recorrer la tabla entera.
        """
        producto, _, _ = juguete_pg
        filas = (
            db_pg.query(models.BotProductoFila)
            .filter(models.BotProductoFila.producto_id == producto.id)
            .filter(
                models.BotProductoFila.valores.contains(
                    {"promocion": "incluye esmaltes"}
                )
            )
            .all()
        )
        assert [f.etiqueta for f in filas] == ["21/03"]

    def test_el_json_vuelve_con_los_tipos_intactos(self, db_pg, juguete_pg):
        """Un entero que vuelva como texto rompe todo cálculo de mínimos."""
        producto, team_id, bot_id = juguete_pg
        catalogo = productos.cargar_catalogo(
            db_pg, team_id=team_id, producto_id=producto.id
        )
        fila = next(f for f in catalogo.filas if f.etiqueta == "21/03")
        assert isinstance(fila.valores["valor"], int)
        assert fila.valores["valor"] == 150_000


class TestIndices:
    def test_el_indice_de_la_consulta_caliente_es_parcial(self, motor):
        """Sin el `WHERE activo` el índice se lleva también las filas retiradas,
        que después de unas temporadas son la mayoría de la tabla."""
        with motor.connect() as conexion:
            definicion = conexion.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :esquema AND indexname = :nombre"
                ),
                {"esquema": ESQUEMA, "nombre": "ix_bot_producto_filas_prod_inicio"},
            ).scalar()
        assert definicion is not None
        assert "WHERE" in definicion.upper() and "activo" in definicion

    def test_el_indice_de_valores_es_gin(self, motor):
        with motor.connect() as conexion:
            definicion = conexion.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = :esquema AND indexname = :nombre"
                ),
                {"esquema": ESQUEMA, "nombre": "ix_bot_producto_filas_valores"},
            ).scalar()
        assert definicion is not None
        assert "gin" in definicion.lower()

    def test_el_centinela_cero_hace_morder_el_unique(self, db_pg, juguete_pg):
        """La razón de que `variante_id` sea `0` y no NULL.

        En Postgres `NULL <> NULL`, así que un UNIQUE con una columna nullable
        no impide duplicados cuando esa columna viene vacía: el importador
        reinsertaría las mismas filas en cada corrida. Con `0` sí muerde.
        """
        from sqlalchemy.exc import IntegrityError

        producto, _, _ = juguete_pg
        for _ in range(2):
            db_pg.add(
                models.BotProductoFila(
                    producto_id=producto.id,
                    variante_id=models.REF_TODAS,
                    etiqueta="repetida",
                    valores={"valor": 1_000},
                    externo_id="misma-fila-del-excel",
                )
            )
        with pytest.raises(IntegrityError):
            db_pg.commit()


class TestZonaHoraria:
    def test_el_hoy_del_modulo_es_el_que_dice_el_motor(self, motor):
        """El módulo usa un `timezone(-5)` fijo porque Colombia no tiene horario
        de verano. Si algún día lo tuviera, esta prueba lo avisa."""
        with motor.connect() as conexion:
            del_motor = conexion.execute(
                text("SELECT (now() AT TIME ZONE 'America/Bogota')::date")
            ).scalar()
        assert productos.hoy_colombia() == del_motor

    def test_no_se_ofrece_lo_que_ya_paso_segun_el_reloj_de_alla(
        self, db_pg, juguete_pg
    ):
        producto, team_id, bot_id = juguete_pg
        catalogo = productos.cargar_catalogo(
            db_pg, team_id=team_id, producto_id=producto.id
        )
        filas = productos.filas_vigentes(catalogo, hoy=HOY)
        assert all(f.inicio >= HOY for f in filas)


class TestElTextoNoCambiaDeMotor:
    """Lo que el bot lee tiene que ser igual en la suite y en producción."""

    def test_la_respuesta_es_la_misma_que_en_sqlite(
        self, db_pg, juguete_pg, db_session, cuenta_a
    ):
        producto, team_id, bot_id = juguete_pg
        team_sqlite, bot_sqlite = cuenta_a
        crear_juguete(db_session, team_id=team_sqlite, bot_id=bot_sqlite)

        en_postgres = productos.consultar(
            db_pg, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
        )
        productos.limpiar_cache()
        en_sqlite = productos.consultar(
            db_session, team_id=team_sqlite, bot_id=bot_sqlite, mes="marzo", hoy=HOY
        )
        assert en_postgres == en_sqlite

    def test_el_volcado_generico_no_depende_del_orden_de_claves(
        self, db_pg, db_session
    ):
        """JSONB reordena las claves; SQLite las devuelve como llegaron.

        Un producto sin plantillas cae en el volcado genérico de `valores`, y
        si ese volcado siguiera el orden del motor diría una cosa en la suite y
        otra en producción.
        """
        salidas = []
        for db in (db_pg, db_session):
            team_id, bot_id = crear_cuenta(db, uuid.uuid4().hex[:8])
            crear_juguete(
                db, team_id=team_id, bot_id=bot_id, presentacion={},
                fechas=[("basico", date(2026, 3, 21), 150_000, 6, "sin tacc")],
            )
            productos.limpiar_cache()
            salidas.append(
                productos.consultar(
                    db, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
                )
            )
        assert salidas[0] == salidas[1]
        assert "horas: 6, promocion: sin tacc, valor: 150000" in salidas[0]
