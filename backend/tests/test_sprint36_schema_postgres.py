"""Sprint 36 — lo del esquema que solo Postgres puede contestar.

  * La migración converge con `create_all()` por los dos caminos (gotcha del
    17-sep-2026): base creada por el modelo → la migración no repara nada y el
    verificador da verde; base de antes del Sprint 36 → la migración la deja
    igual, y la segunda corrida dice «0 cambios, 0 reparados».
  * Repara el borrador `370f4f9` (FK simple, sin `bot_id`, sin CHECK de
    anulación, sin DEFAULT) y el verificador detecta una base rota.
  * La FK compuesta rechaza una venta cuyo team no es el de su conversación.
  * Carreras con dos o tres sesiones reales: una sola venta activa gana; el
    cupo por franja/puesto se respeta (cupo 1 con dos clientes → 1 fila; cupo 2
    con tres → 2).
  * Índice parcial de reenganche, CHECKs y ON DELETE.

Marcador `postgres`: no corre por defecto. Para correrlas contra el docker
compose local (`-p wati`):

    POSTGRES_TEST_URL=postgresql+psycopg2://equipo:<clave>@<ip-lan>:5432/multiagente_db \\
        pytest --con-postgres -m postgres tests/test_sprint36_schema_postgres.py

(en el Mac del CEO `localhost:5432` lo captura un Postgres del host; por eso la
IP de la LAN). Todo va en esquemas temporales que se borran al final: aunque se
apunte por error a una base con datos, no se toca una tabla suya. Nada de esto
toca RDS. Datos inventados (regla #8).
"""
from __future__ import annotations

import os
import threading
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app import models
from scripts import migrate_sprint36_ventas_abandono as migracion

pytestmark = pytest.mark.postgres


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
def base():
    try:
        motor = create_engine(_url(), isolation_level="AUTOCOMMIT")
        with motor.connect() as conexion:
            conexion.execute(text("SELECT 1"))
    except Exception as error:      # noqa: BLE001
        # Sin la URL en el mensaje: ahí viaja la contraseña.
        pytest.skip(f"no se pudo conectar a Postgres ({type(error).__name__})")
    yield motor
    motor.dispose()


@pytest.fixture
def esquema(base):
    """Fábrica de esquemas temporales con `create_all()`. Devuelve el engine."""
    creados: list[tuple[str, object]] = []

    def crear():
        from app.database import Base

        nombre = "s36_test_" + uuid.uuid4().hex[:8]
        with base.connect() as conexion:
            conexion.execute(text(f'CREATE SCHEMA "{nombre}"'))
        engine = create_engine(
            _url(), connect_args={"options": f"-csearch_path={nombre}"}
        )
        Base.metadata.create_all(engine)
        creados.append((nombre, engine))
        return engine

    yield crear
    for nombre, engine in creados:
        engine.dispose()
        with base.connect() as conexion:
            conexion.execute(text(f'DROP SCHEMA "{nombre}" CASCADE'))


def _silencio(*_a, **_k) -> None:
    pass


# ---------------------------------------------------------------------------
# La migración converge con create_all()
# ---------------------------------------------------------------------------

#: Deja la base como estaba antes del Sprint 36.
ANTES_DEL_SPRINT = [
    "DROP TABLE conversation_sales",
    "ALTER TABLE conversations DROP CONSTRAINT uq_conversations_id_team",
    "ALTER TABLE conversations DROP COLUMN abandono_at, DROP COLUMN abandono_asesor, "
    "DROP COLUMN reclamos_abandono, DROP COLUMN ultimo_mensaje_humano_at, "
    "DROP COLUMN cerrada_por_inactividad_at, DROP COLUMN marcador_consumido",
    "ALTER TABLE bots DROP COLUMN es_reenganche",
    "ALTER TABLE agendamientos DROP COLUMN franja_inicio, DROP COLUMN puesto, "
    "DROP COLUMN origen, DROP COLUMN resultado, DROP COLUMN resultado_por_user_id, "
    "DROP COLUMN resultado_at, DROP COLUMN aviso_inicio_at, DROP COLUMN alerta_fin_at, "
    "DROP COLUMN cotizacion",
]


def test_base_creada_por_create_all_no_necesita_reparar_nada(esquema):
    engine = esquema()
    assert migracion.verificar(engine, decir=_silencio) == []
    resultado = migracion.aplicar(engine)
    assert resultado == {"cambios": [], "reparados": []}


def test_base_vieja_queda_igual_y_la_segunda_corrida_no_hace_nada(esquema):
    engine = esquema()
    with engine.begin() as conexion:
        for sql in ANTES_DEL_SPRINT:
            conexion.execute(text(sql))
    errores = migracion.verificar(engine, decir=_silencio)
    assert any("conversation_sales" in e for e in errores)

    primera = migracion.aplicar(engine)
    assert primera["cambios"] and primera["reparados"] == []
    assert migracion.verificar(engine, decir=_silencio) == []

    segunda = migracion.aplicar(engine)
    assert segunda == {"cambios": [], "reparados": []}


def test_repara_el_borrador_y_el_verificador_no_da_verde_sobre_una_base_rota(esquema):
    engine = esquema()
    with engine.begin() as conexion:
        conexion.execute(text(
            "ALTER TABLE conversation_sales "
            "DROP CONSTRAINT fk_conversation_sales_conv_team, "
            "DROP CONSTRAINT ck_conversation_sales_anulacion, "
            "DROP COLUMN bot_id, "
            "ALTER COLUMN created_at DROP DEFAULT, "
            "ADD CONSTRAINT conversation_sales_conversation_id_fkey "
            "FOREIGN KEY (conversation_id) REFERENCES conversations (id) ON DELETE CASCADE"
        ))
        conexion.execute(text("ALTER TABLE bots ALTER COLUMN es_reenganche DROP DEFAULT"))
        conexion.execute(text("DROP INDEX uq_agendamientos_franja_puesto"))
    errores = migracion.verificar(engine, decir=_silencio)
    textos = "\n".join(errores)
    for pieza in (
        "fk_conversation_sales_conv_team", "ck_conversation_sales_anulacion",
        "conversation_sales.bot_id", "conversation_sales.created_at default",
        "bots.es_reenganche default", "uq_agendamientos_franja_puesto",
        "conversation_sales_conversation_id_fkey",
    ):
        assert pieza in textos, pieza

    resultado = migracion.aplicar(engine)
    assert len(resultado["reparados"]) == 3   # FK simple + 2 DEFAULT
    assert migracion.verificar(engine, decir=_silencio) == []
    assert migracion.aplicar(engine) == {"cambios": [], "reparados": []}


def test_backfill_por_lotes_solo_llena_nulos(esquema, monkeypatch):
    engine = esquema()
    monkeypatch.setattr(migracion, "LOTE", 1)
    Sesion = sessionmaker(bind=engine)
    with Sesion() as db:
        team, convs = _cuenta(db, "bf", n_convs=3)
        hace = datetime(2026, 10, 1, 12, 0)
        humano, abandonada, cerrada = convs
        abandonada.status, abandonada.etiqueta, abandonada.assigned_to = "pending", "abandonada", "Ana"
        cerrada.status = "closed"
        db.add_all([
            models.Message(conversation_id=humano.id, direction="outbound", content="hola",
                           sent_by_user_id=team.owner_user_id, created_at=hace),
            models.Message(conversation_id=humano.id, direction="outbound", content="nota",
                           message_type="nota_interna", sent_by_user_id=team.owner_user_id,
                           created_at=hace + timedelta(hours=1)),
            models.Message(conversation_id=abandonada.id, direction="outbound",
                           content="🕒 *Abandonada*\nresumen", message_type="nota_interna",
                           created_at=hace),
            models.Message(conversation_id=cerrada.id, direction="outbound",
                           content="🔒 *Cerrada por inactividad*", message_type="nota_interna",
                           created_at=hace),
            models.Agendamiento(team_id=team.id, conversation_id=abandonada.id,
                                fecha_llamada=date(2026, 10, 4)),
        ])
        db.commit()

        tocadas = migracion.backfill(engine, set(migracion.BACKFILLS), decir=_silencio)
        assert tocadas == {"humano": 1, "inactividad": 1, "abandono": 1, "origen": 1}
        db.expire_all()
        assert humano.ultimo_mensaje_humano_at == hace          # la nota no cuenta
        assert (abandonada.abandono_at, abandonada.abandono_asesor) == (hace, "Ana")
        assert abandonada.reclamos_abandono == 0
        assert cerrada.cerrada_por_inactividad_at == hace
        assert db.query(models.Agendamiento).one().origen == "abandono"

        # Segunda corrida: nada que llenar, y no pisa lo que ya tiene valor.
        assert set(migracion.backfill(engine, set(migracion.BACKFILLS), decir=_silencio).values()) == {0}


# ---------------------------------------------------------------------------
# Lo que la base hace cumplir
# ---------------------------------------------------------------------------

def _cuenta(db, sufijo: str, n_convs: int = 1):
    user = models.User(
        nombre=f"Prueba {sufijo}", tipo_documento="CC", documento=f"S36PG-{sufijo}",
        correo=f"s36pg-{sufijo}@ejemplo.invalid", hashed_password="x",
    )
    db.add(user)
    db.flush()
    team = models.Team(nombre=f"Equipo {sufijo}", owner_user_id=user.id)
    db.add(team)
    db.flush()
    convs = [
        models.Conversation(team_id=team.id, contact_wa_id=f"57300036{i:04d}")
        for i in range(n_convs)
    ]
    db.add_all(convs)
    db.commit()
    return team, convs


@pytest.fixture
def motor(esquema):
    return esquema()


def test_fk_compuesta_rechaza_venta_de_otro_team(motor):
    with sessionmaker(bind=motor)() as db:
        team_a, (conv_a,) = _cuenta(db, "a")
        team_b, _ = _cuenta(db, "b")
        db.add(models.ConversationSale(team_id=team_b.id, conversation_id=conv_a.id, valor_cop=1000))
        with pytest.raises(IntegrityError, match="fk_conversation_sales_conv_team"):
            db.commit()
        db.rollback()
        db.add(models.ConversationSale(team_id=team_a.id, conversation_id=conv_a.id, valor_cop=1000))
        db.commit()


def test_borrar_la_conversacion_borra_sus_ventas_y_borrar_el_bot_deja_null(motor):
    with sessionmaker(bind=motor)() as db:
        team, (conv,) = _cuenta(db, "del")
        bot = models.Bot(user_id=team.owner_user_id, name="B")
        db.add(bot)
        db.flush()
        venta = models.ConversationSale(team_id=team.id, conversation_id=conv.id,
                                        valor_cop=5000, bot_id=bot.id)
        db.add(venta)
        db.commit()
        venta_id = venta.id
        db.execute(text("DELETE FROM bots WHERE id = :i"), {"i": bot.id})
        db.commit()
        assert db.execute(text("SELECT bot_id FROM conversation_sales WHERE id = :i"),
                          {"i": venta_id}).scalar() is None
        db.execute(text("DELETE FROM conversations WHERE id = :i"), {"i": conv.id})
        db.commit()
        assert db.execute(text("SELECT COUNT(*) FROM conversation_sales")).scalar() == 0


def _en_paralelo(motor, n: int, trabajo) -> list:
    """Corre `trabajo(sesion)` en `n` hilos con su propia conexión, a la vez."""
    barrera = threading.Barrier(n)
    resultados: list = [None] * n

    def correr(i: int) -> None:
        with sessionmaker(bind=motor)() as sesion:
            barrera.wait()
            try:
                resultados[i] = trabajo(sesion)
            except Exception as error:      # noqa: BLE001
                sesion.rollback()
                resultados[i] = error

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)
    return resultados


def test_dos_sesiones_registran_venta_a_la_vez_y_gana_una(motor):
    with sessionmaker(bind=motor)() as db:
        team, (conv,) = _cuenta(db, "race")
        team_id, conv_id = team.id, conv.id

    def registrar(sesion):
        sesion.add(models.ConversationSale(team_id=team_id, conversation_id=conv_id, valor_cop=7000))
        sesion.commit()
        return "ok"

    resultados = _en_paralelo(motor, 2, registrar)
    assert resultados.count("ok") == 1
    assert sum(isinstance(r, IntegrityError) for r in resultados) == 1
    with motor.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM conversation_sales")).scalar() == 1


def _reservar(sesion, team_id: int, conv_id: int, franja: datetime, cupo: int):
    """Lo que hará el handler: probar puestos 1..cupo con un SAVEPOINT."""
    for puesto in range(1, cupo + 1):
        try:
            with sesion.begin_nested():
                sesion.add(models.Agendamiento(
                    team_id=team_id, conversation_id=conv_id, fecha_llamada=franja.date(),
                    franja_inicio=franja, puesto=puesto,
                    origen=models.AGENDAMIENTO_ORIGEN_BOT_LLAMADA,
                ))
            sesion.commit()
            return puesto
        except IntegrityError:
            continue
    return "llena"


@pytest.mark.parametrize("cupo,clientes", [(1, 2), (2, 3)])
def test_cupo_por_franja_con_sesiones_concurrentes(motor, cupo, clientes):
    franja = datetime(2026, 11, 10, 15, 0)
    with sessionmaker(bind=motor)() as db:
        team, convs = _cuenta(db, f"cupo{cupo}", n_convs=clientes)
        team_id, ids = team.id, [c.id for c in convs]

    turnos = iter(ids)
    candado = threading.Lock()

    def reservar(sesion):
        with candado:
            conv_id = next(turnos)
        return _reservar(sesion, team_id, conv_id, franja, cupo)

    resultados = _en_paralelo(motor, clientes, reservar)
    assert sorted(r for r in resultados if r != "llena") == list(range(1, cupo + 1))
    assert resultados.count("llena") == clientes - cupo
    with motor.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM agendamientos")).scalar() == cupo


def test_cerrar_la_llamada_libera_el_puesto(motor):
    franja = datetime(2026, 11, 10, 16, 0)
    with sessionmaker(bind=motor)() as db:
        team, (c1, c2) = _cuenta(db, "libera", n_convs=2)
        assert _reservar(db, team.id, c1.id, franja, 1) == 1
        assert _reservar(db, team.id, c2.id, franja, 1) == "llena"
        db.query(models.Agendamiento).update({"estado": models.AGENDAMIENTO_CERRADO})
        db.commit()
        assert _reservar(db, team.id, c2.id, franja, 1) == 1


def test_un_solo_bot_de_reenganche_por_owner(motor):
    with sessionmaker(bind=motor)() as db:
        team_a, _ = _cuenta(db, "ra")
        team_b, _ = _cuenta(db, "rb")
        db.add_all([
            models.Bot(user_id=team_a.owner_user_id, name="R1", es_reenganche=True),
            models.Bot(user_id=team_a.owner_user_id, name="N1"),
            models.Bot(user_id=team_a.owner_user_id, name="N2"),
            models.Bot(user_id=team_b.owner_user_id, name="R2", es_reenganche=True),
        ])
        db.commit()
        db.add(models.Bot(user_id=team_a.owner_user_id, name="R3", es_reenganche=True))
        with pytest.raises(IntegrityError, match="uq_bot_reenganche_por_owner"):
            db.commit()


@pytest.mark.parametrize("cambios,constraint", [
    ({"anulada_at": datetime(2026, 11, 1)}, "ck_conversation_sales_anulacion"),
    ({"motivo_anulacion": "x"}, "ck_conversation_sales_anulacion"),
])
def test_check_de_anulacion(motor, cambios, constraint):
    with sessionmaker(bind=motor)() as db:
        team, (conv,) = _cuenta(db, "an")
        db.add(models.ConversationSale(team_id=team.id, conversation_id=conv.id,
                                       valor_cop=1000, **cambios))
        with pytest.raises(IntegrityError, match=constraint):
            db.commit()


@pytest.mark.parametrize("campos,constraint", [
    ({"franja_inicio": datetime(2026, 11, 10, 15)}, "ck_agendamientos_franja_con_puesto"),
    ({"puesto": 1}, "ck_agendamientos_franja_con_puesto"),
    ({"franja_inicio": datetime(2026, 11, 10, 15), "puesto": 0}, "ck_agendamientos_puesto"),
    ({"origen": "otro"}, "ck_agendamientos_origen"),
    ({"resultado": "vendio"}, "ck_agendamientos_resultado"),
    ({"cotizacion": "x" * 1001}, "ck_agendamientos_cotizacion_largo"),
])
def test_checks_de_agendamientos(motor, campos, constraint):
    with sessionmaker(bind=motor)() as db:
        team, (conv,) = _cuenta(db, "ck")
        db.add(models.Agendamiento(team_id=team.id, conversation_id=conv.id,
                                   fecha_llamada=date(2026, 11, 10), **campos))
        with pytest.raises(IntegrityError, match=constraint):
            db.commit()


def test_check_de_marcador_consumido(motor):
    with sessionmaker(bind=motor)() as db:
        _, (conv,) = _cuenta(db, "mc")
        conv.marcador_consumido = "volvio"
        db.commit()
        conv.marcador_consumido = "bot"
        with pytest.raises(IntegrityError, match="ck_conversations_marcador_consumido"):
            db.commit()
