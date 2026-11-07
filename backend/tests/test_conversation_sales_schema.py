"""Esquema del Sprint 36: ventas, reenganche, marcador y agenda de llamadas.

Se prueba lo que la base hace cumplir sola, sin pasar por endpoints:

  1. Una sola venta ACTIVA por conversación (`uq_conversation_sales_activa`,
     índice único parcial): la segunda choca, pero tras anular la primera se
     puede registrar la corregida.
  2. El CHECK `ck_conversation_sales_valor` rechaza 0 (y lo que pase del tope)
     y `ck_conversation_sales_anulacion` exige anular con fecha y motivo.
  3. La FK compuesta (conversation_id, team_id) rechaza una venta de otro team.
  4. `reclamos_abandono` nace en 0 y `es_reenganche` en False; un solo bot de
     reenganche por owner.
  5. Agenda: franja y puesto van juntos, un puesto por franja entre las
     pendientes, valores cerrados de origen/resultado y cotización ≤ 1000.
  6. Los `__repr__` no dejan ver ni el valor, ni la nota, ni la cotización.
  7. El contrato modelo ↔ migración (defaults, columnas, constraints, índices)
     y los schemas de entrada del diseño de seguridad (1.4, 1.5, 3.4).

Corre sobre SQLite con `create_all()`, igual que el resto de la suite: por eso
los CHECK y los índices parciales viven en el modelo y no solo en la migración.
Lo que solo Postgres contesta está en `test_sprint36_schema_postgres.py`.
Datos inventados (regla #8).
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models, schemas
from app.database import Base
from scripts import migrate_sprint36_ventas_abandono as migracion


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite no hace cumplir las FK si no se le pide; sin esto la FK
    # compuesta no se probaría.
    @event.listens_for(engine, "connect")
    def _fk(conexion, _registro):  # noqa: ANN001
        conexion.execute("PRAGMA foreign_keys=ON")

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


# ---------------------------------------------------------------------------
# Venta: FK compuesta, anulación, relación
# ---------------------------------------------------------------------------

def _otro_team(db, sufijo="B"):
    user = models.User(
        nombre=f"Otro {sufijo}", tipo_documento="CC", documento=f"S36-T{sufijo}",
        correo=f"s36{sufijo.lower()}@ejemplo.invalid", hashed_password="x",
    )
    db.add(user)
    db.flush()
    team = models.Team(nombre=f"Otro equipo {sufijo}", owner_user_id=user.id)
    db.add(team)
    db.commit()
    return team


def test_fk_compuesta_rechaza_venta_con_team_ajeno(db, conv):
    otro = _otro_team(db)
    db.add(models.ConversationSale(team_id=otro.id, conversation_id=conv.id, valor_cop=1000))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_asignar_la_conversacion_copia_su_team(db, conv):
    venta = models.ConversationSale(conversation=conv, valor_cop=1000)
    db.add(venta)
    db.commit()
    assert (venta.team_id, venta.conversation_id) == (conv.team_id, conv.id)


@pytest.mark.parametrize("campos", [
    {"anulada_at": datetime(2026, 11, 1)},                      # sin motivo
    {"motivo_anulacion": "error"},                              # sin fecha
    {"anulada_por_user_id": 1},                                 # quién, sin anular
])
def test_check_de_anulacion_rechaza_a_medias(db, conv, campos):
    db.add(_venta(conv, **campos))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_anulacion_completa_pasa(db, conv):
    db.add(_venta(conv, anulada_at=datetime(2026, 11, 1), motivo_anulacion="mal digitado"))
    db.commit()


# ---------------------------------------------------------------------------
# Marcador y bot de reenganche
# ---------------------------------------------------------------------------

def test_marcador_consumido_solo_valores_cerrados(db, conv):
    conv.marcador_consumido = models.MARCADOR_CONSUMIDO_HUMANO
    db.commit()
    conv.marcador_consumido = "bot"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_un_solo_bot_de_reenganche_por_owner(db, conv):
    owner = conv.team.owner_user_id
    normal = models.Bot(user_id=owner, name="Normal")
    db.add(normal)
    db.commit()
    db.refresh(normal)
    assert normal.es_reenganche is False

    db.add_all([
        models.Bot(user_id=owner, name="Otro normal"),
        models.Bot(user_id=owner, name="Reenganche", es_reenganche=True),
        models.Bot(user_id=_otro_team(db).owner_user_id, name="R ajeno", es_reenganche=True),
    ])
    db.commit()

    db.add(models.Bot(user_id=owner, name="Segundo reenganche", es_reenganche=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# Agenda de llamadas
# ---------------------------------------------------------------------------

FRANJA = datetime(2026, 11, 10, 15, 0)


def _agenda(conv, **campos) -> models.Agendamiento:
    return models.Agendamiento(
        team_id=conv.team_id, conversation_id=conv.id, fecha_llamada=date(2026, 11, 10),
        **campos,
    )


@pytest.mark.parametrize("campos", [
    {"franja_inicio": FRANJA},                       # franja sin puesto: se saltaría el cupo
    {"puesto": 1},                                   # puesto sin franja
    {"franja_inicio": FRANJA, "puesto": 0},
    {"origen": "manual"},
    {"resultado": "vendio"},
    {"cotizacion": "x" * (models.AGENDAMIENTO_COTIZACION_MAX + 1)},
])
def test_checks_de_agenda_rechazan(db, conv, campos):
    db.add(_agenda(conv, **campos))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_agenda_valida_pasa(db, conv):
    db.add(_agenda(
        conv, franja_inicio=FRANJA, puesto=1,
        origen=models.AGENDAMIENTO_ORIGEN_BOT_LLAMADA,
        resultado=models.AGENDAMIENTO_RESULTADO_LO_PENSARA,
        cotizacion="x" * models.AGENDAMIENTO_COTIZACION_MAX,
    ))
    db.commit()


def test_un_puesto_por_franja_entre_pendientes(db, conv):
    otra = models.Conversation(team_id=conv.team_id, contact_wa_id="573000036102")
    db.add(otra)
    db.commit()
    db.add(_agenda(conv, franja_inicio=FRANJA, puesto=1))
    db.commit()

    db.add(_agenda(otra, franja_inicio=FRANJA, puesto=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    db.add(_agenda(otra, franja_inicio=FRANJA, puesto=2))       # otro puesto: cabe
    db.commit()


def test_repr_de_agendamiento_sin_cotizacion(db, conv):
    agenda = _agenda(conv, cotizacion="Plan Coveñas 3 días, 2 personas, total 1.890.000")
    db.add(agenda)
    db.commit()
    texto = repr(agenda)
    assert "Coveñas" not in texto and "1.890.000" not in texto
    assert str(agenda) == texto


# ---------------------------------------------------------------------------
# Contrato modelo ↔ migración (no comparten import a propósito)
# ---------------------------------------------------------------------------

def _tabla(nombre):
    return Base.metadata.tables[nombre]


def test_las_columnas_de_la_migracion_son_las_del_modelo():
    for tabla, esperadas in migracion.ESPERADAS.items():
        columnas = _tabla(tabla).columns
        for col, (_tipo, nulable, _default, largo) in esperadas.items():
            assert col in columnas, f"{tabla}.{col} no está en models.py"
            c = columnas[col]
            assert c.nullable == (nulable == "YES"), f"{tabla}.{col} nullable"
            if largo is not None:
                assert c.type.length == largo, f"{tabla}.{col} largo"
    # La tabla nueva, exacta en las dos direcciones.
    assert set(_tabla("conversation_sales").columns.keys()) == set(
        migracion.ESPERADAS["conversation_sales"]
    )


def test_los_defaults_de_la_migracion_son_los_del_modelo():
    for (tabla, col), (_literal, esperado) in migracion.DEFAULTS.items():
        server_default = _tabla(tabla).columns[col].server_default
        assert server_default is not None, f"{tabla}.{col} sin server_default"
        arg = server_default.arg
        # "0" / "false" son texto; func.now() es una expresión → "now()".
        texto = arg if isinstance(arg, str) else str(arg.compile(dialect=postgresql.dialect()))
        assert texto.strip("'").lower() == esperado, f"{tabla}.{col}: {texto!r}"
    # Y al revés: toda columna nueva con server_default figura en DEFAULTS.
    for tabla, esperadas in migracion.ESPERADAS.items():
        for col, (_t, _n, default, _l) in esperadas.items():
            if default is None or default.startswith("nextval("):
                continue
            assert (tabla, col) in migracion.DEFAULTS, f"{tabla}.{col} falta en DEFAULTS"


def test_constraints_e_indices_de_la_migracion_estan_en_el_modelo():
    for tabla, esperadas in migracion.CONSTRAINTS_ESPERADAS.items():
        nombres = {c.name for c in _tabla(tabla).constraints if c.name}
        faltan = set(esperadas) - nombres - {f"{tabla}_pkey"}
        # Las FK sin nombre en el modelo las nombra Postgres `<tabla>_<col>_fkey`.
        faltan = {
            n for n in faltan
            if not (n.endswith("_fkey") and any(
                fk.parent.name == n[len(tabla) + 1:-len("_fkey")]
                for fk in _tabla(tabla).foreign_keys
            ))
        }
        assert not faltan, f"{tabla}: {sorted(faltan)}"
    for tabla, esperados in migracion.INDICES_ESPERADOS.items():
        nombres = {i.name for i in _tabla(tabla).indexes} | {
            c.name for c in _tabla(tabla).constraints if c.name
        }
        faltan = set(esperados) - nombres - {f"{tabla}_pkey"}
        assert not faltan, f"{tabla}: {sorted(faltan)}"


def test_tope_de_valor_y_de_cotizacion_iguales_en_modelo_y_migracion():
    assert f"<= {models.VENTA_VALOR_MAX_COP}" in migracion.CREAR_VENTAS
    assert any(
        n == "ck_agendamientos_cotizacion_largo"
        and f"<= {models.AGENDAMIENTO_COTIZACION_MAX}" in cuerpo
        for _t, n, cuerpo in migracion.CONSTRAINTS
    )


# ---------------------------------------------------------------------------
# Schemas de entrada y salida (diseño de seguridad 1.4, 1.5, 3.4)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("valor", [0, -1, 500_000_001, "1000", 1000.5, 1000.0, True, None])
def test_venta_in_rechaza_valores_no_enteros_o_fuera_de_rango(valor):
    with pytest.raises(ValidationError):
        schemas.VentaIn(valor_cop=valor, vendida_por="Ana")


def test_venta_in_acepta_el_tope_y_limpia_textos():
    venta = schemas.VentaIn(valor_cop=500_000_000, vendida_por="  Ana ", nota="  ")
    assert (venta.valor_cop, venta.vendida_por, venta.nota) == (500_000_000, "Ana", None)
    assert schemas.VentaIn(valor_cop=1, vendida_por="Ana", nota="dos\nlíneas").nota == "dos\nlíneas"


@pytest.mark.parametrize("campos", [
    {"nota": "x" * 281},
    {"nota": "tab\taquí"},
    {"nota": "nulo\x00"},
    {"vendida_por": ""},
    {"vendida_por": "x" * 65},
    {"vendida_por": "Ana\nB"},
    {"team_id": 5},                     # extra="forbid": el team no viaja en el body
    {"conversation_id": 9},
])
def test_venta_in_rechaza(campos):
    datos = {"valor_cop": 1000, "vendida_por": "Ana", **campos}
    with pytest.raises(ValidationError):
        schemas.VentaIn(**datos)


@pytest.mark.parametrize("motivo", [None, "", "  ", "ab", "x" * 281])
def test_anular_exige_motivo_de_3_a_280(motivo):
    with pytest.raises(ValidationError):
        schemas.AnularVentaIn(motivo=motivo)


def test_anular_con_motivo_valido():
    assert schemas.AnularVentaIn(motivo="  mal digitado ").motivo == "mal digitado"
    with pytest.raises(ValidationError):
        schemas.AnularVentaIn(motivo="ok ok", venta_id=3)


def test_resultado_de_llamada_solo_valores_cerrados():
    assert set(models.AVAILABLE_AGENDAMIENTO_RESULTADOS) == {
        schemas.ResultadoLlamadaIn(resultado=r).resultado
        for r in ("vendida", "lo_pensara", "no_contesto")
    }
    for malo in ("vendio", "", None, 1):
        with pytest.raises(ValidationError):
            schemas.ResultadoLlamadaIn(resultado=malo)
    with pytest.raises(ValidationError):
        schemas.ResultadoLlamadaIn(resultado="vendida", team_id=5)


def test_venta_out_no_expone_team_ni_ids_de_usuario():
    campos = set(schemas.VentaOut.model_fields)
    assert campos == {
        "id", "valor_cop", "vendida_por", "nota", "registrada_at",
        "registrada_por_nombre", "anulada_at", "motivo_anulacion",
    }
    assert not {c for c in campos if c.endswith("_id")}
