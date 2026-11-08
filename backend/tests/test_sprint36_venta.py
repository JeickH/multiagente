"""Sprint 36 — botón «venta cerrada» (diseño de seguridad, sección 1).

Lo que se fija aquí, en el orden del diseño:

* 1.1 Permiso `can_reply_messages` (201 con él, 403 sin él) y la conversación
  cargada con el team de la membresía: ajena e inexistente dan el MISMO 404 y
  no dejan rastro. El team de la venta es el de la conversación, nunca del body.
* 1.2 La supervisión de Gloma solo lee: todas sus rutas son GET, y la admin de
  Gloma que llame al POST sobre una conversación de otra cuenta recibe 404.
* 1.3 Doble registro → 409 (y con dos sesiones Postgres reales gana una).
  Anular: sin motivo 422, dos veces 404, y tras anular se registra otra.
* 1.4 Validación estricta del valor: ni texto, ni decimales, ni booleanos.
* 1.5 Qué ve cada pantalla: el detalle trae la venta; la lista solo el valor;
  la supervisión solo valor y fecha (ni nota, ni motivo, ni ids de usuario).
* 1.6 Los logs solo llevan ids: ni valor, ni nota, ni nombres, ni teléfono.
* 0.7 La venta queda atribuida al bot que atendía la conversación.

Por HTTP de verdad (TestClient sobre los dos routers) para que las
dependencias de permisos corran como en producción; solo se sustituyen la
sesión de base y el usuario autenticado. Datos inventados (regla #8): los
teléfonos son de relleno y los correos de un dominio de ejemplo.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.dependencies import GLOMA_EMAIL, get_current_user, get_db
from app.routers import mensajes, supervision

CLAVE = "Clave-De-Prueba-1"
VIAJES = "cuenta-viajes@example.com"
AJENA = "cuenta-ajena@example.com"
#: Valores que no pueden aparecer en ningún log (diseño 1.6).
VALOR = 7_654_321
NOTA = "Pagó en la oficina, contacto 3XXXXXXXXX, nota secreta"
MOTIVO = "Valor mal digitado por la asesora"
TELEFONO = "573009998877"


# ---------------------------------------------------------------------------
# Infra
# ---------------------------------------------------------------------------

@pytest.fixture
def Sesion():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


@pytest.fixture
def db(Sesion):
    sesion = Sesion()
    try:
        yield sesion
    finally:
        sesion.close()


def _usuario(db, nombre, correo, documento):
    return crud.create_user(
        db,
        schemas.UserCreate(
            nombre=nombre, correo=correo, tipo_documento="CC",
            documento=documento, password=CLAVE,
        ),
    )


def _conversacion(db, team_id, *, wa_id=TELEFONO, nombre="Cliente Prueba"):
    conv = models.Conversation(
        team_id=team_id,
        contact_wa_id=wa_id,
        contact_name=nombre,
        status="open",
        assigned_to="Alexandra",
        last_message_at=datetime(2026, 11, 7, 15, 0, 0),
        created_at=datetime(2026, 11, 7, 14, 0, 0),
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    db.add(models.Message(
        conversation_id=conv.id, direction="inbound", content="Quiero el plan",
        created_at=datetime(2026, 11, 7, 14, 30, 0),
    ))
    db.commit()
    return conv


@pytest.fixture
def mundo(db, monkeypatch):
    """Tres cuentas: viajes (la que vende), una ajena y la de Gloma (supervisa).

    En viajes: la dueña (todos los permisos) y una asesora SIN permiso de
    responder, con su bot y una conversación atendida por ese bot.
    """
    monkeypatch.setenv("SUPERVISION_CUENTAS", VIAJES)

    duena = _usuario(db, "Duena Viajes", VIAJES, "S36V-001")
    team = crud.create_team(db, "Agencia Viajes", duena)
    team.asesores_rotacion = ["Alexandra", "Camila"]
    db.add(team)
    db.commit()

    sin_permiso = _usuario(db, "Mirona Sinpermiso", "mirona@example.com", "S36V-002")
    miembro = models.TeamMember(team_id=team.id, user_id=sin_permiso.id, role="agent")
    db.add(miembro)
    db.commit()
    crud.set_member_permissions(db, miembro, {"can_reply_messages": False})

    bot = models.Bot(user_id=duena.id, team_id=team.id, name="Bot Viajes", engine="llm")
    db.add(bot)
    db.commit()
    conv = _conversacion(db, team.id)
    db.add(models.BotSession(bot_id=bot.id, conversation_id=conv.id))
    db.commit()

    ajeno = _usuario(db, "Duena Ajena", AJENA, "S36V-003")
    team_ajeno = crud.create_team(db, "Otra Agencia", ajeno)
    conv_ajena = _conversacion(db, team_ajeno.id, wa_id="573001110000")

    gloma = _usuario(db, "Admin Gloma", GLOMA_EMAIL, "S36V-004")
    crud.create_team(db, "Gloma", gloma)

    return {
        "duena": duena, "team": team, "sin_permiso": sin_permiso, "bot": bot,
        "conv": conv, "ajeno": ajeno, "team_ajeno": team_ajeno,
        "conv_ajena": conv_ajena, "gloma": gloma,
    }


@pytest.fixture
def cliente(Sesion, mundo):
    """TestClient sobre `/mensajes` y `/supervision`. `cliente.como(user)` cambia
    quién está autenticado; los permisos y la membresía se resuelven de verdad."""
    app = FastAPI()
    app.include_router(mensajes.router)
    app.include_router(supervision.router)
    actual = {"user_id": mundo["duena"].id}

    def _get_db():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    def _usuario_actual():
        sesion = Sesion()
        try:
            return sesion.query(models.User).get(actual["user_id"])
        finally:
            sesion.close()

    # `get_current_user` usa su propia sesión: la membresía y el permiso se
    # leen con la del request (`get_db`), que es la que importa.
    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = _usuario_actual
    with TestClient(app) as c:
        def como(user):
            actual["user_id"] = user.id
            return c
        c.como = como
        yield c


def _url(conv_id, accion="venta"):
    return f"/mensajes/conversaciones/{conv_id}/{accion}"


def _venta(**extra):
    cuerpo = {"valor_cop": VALOR, "vendida_por": "Alexandra", "nota": NOTA}
    cuerpo.update(extra)
    return cuerpo


def _ventas(db):
    db.expire_all()
    return db.query(models.ConversationSale).order_by(models.ConversationSale.id).all()


# ---------------------------------------------------------------------------
# 1.1 Permiso y aislamiento
# ---------------------------------------------------------------------------

def test_con_permiso_registra_201_y_el_team_es_el_de_la_conversacion(cliente, mundo, db):
    r = cliente.post(_url(mundo["conv"].id), json=_venta())
    assert r.status_code == 201, r.text
    cuerpo = r.json()
    assert cuerpo["valor_cop"] == VALOR
    assert cuerpo["vendida_por"] == "Alexandra"
    assert cuerpo["nota"] == NOTA
    assert cuerpo["registrada_por_nombre"] == "Duena Viajes"
    assert cuerpo["anulada_at"] is None
    # VentaOut sin team ni ids de usuario (1.5).
    assert set(cuerpo) == {
        "id", "valor_cop", "vendida_por", "nota", "registrada_at",
        "registrada_por_nombre", "anulada_at", "motivo_anulacion",
    }

    (venta,) = _ventas(db)
    assert venta.team_id == mundo["team"].id
    assert venta.conversation_id == mundo["conv"].id
    assert venta.registrada_por_user_id == mundo["duena"].id
    # 0.7: atribuida al bot que atendía la conversación.
    assert venta.bot_id == mundo["bot"].id


def test_sin_permiso_de_responder_da_403_y_no_registra(cliente, mundo, db):
    r = cliente.como(mundo["sin_permiso"]).post(_url(mundo["conv"].id), json=_venta())
    assert r.status_code == 403
    assert _ventas(db) == []
    r = cliente.post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO})
    assert r.status_code == 403


def test_conversacion_ajena_e_inexistente_dan_el_mismo_404_sin_cambios(cliente, mundo, db):
    ajena = cliente.post(_url(mundo["conv_ajena"].id), json=_venta())
    inexistente = cliente.post(_url(999_999), json=_venta())
    assert ajena.status_code == inexistente.status_code == 404
    assert ajena.json() == inexistente.json() == {"detail": "Conversación no encontrada"}
    assert _ventas(db) == []

    # Y anular la venta de otro team tampoco: ni la encuentra ni la toca.
    cliente.como(mundo["ajeno"]).post(_url(mundo["conv_ajena"].id), json=_venta(vendida_por="asesor_1"))
    r = cliente.como(mundo["duena"]).post(
        _url(mundo["conv_ajena"].id, "venta/anular"), json={"motivo": MOTIVO}
    )
    assert r.status_code == 404
    (venta,) = _ventas(db)
    assert venta.anulada_at is None


def test_el_body_no_puede_traer_team_ni_campos_de_mas(cliente, mundo, db):
    r = cliente.post(_url(mundo["conv"].id), json=_venta(team_id=mundo["team_ajeno"].id))
    assert r.status_code == 422
    r = cliente.post(_url(mundo["conv"].id, "venta/anular"),
                     json={"motivo": MOTIVO, "team_id": mundo["team_ajeno"].id})
    assert r.status_code == 422
    assert _ventas(db) == []


# ---------------------------------------------------------------------------
# 1.2 Supervisión solo lee
# ---------------------------------------------------------------------------

def test_la_admin_de_gloma_sobre_otra_cuenta_recibe_404(cliente, mundo, db):
    gloma = cliente.como(mundo["gloma"])
    r = gloma.post(_url(mundo["conv"].id), json=_venta())
    assert r.status_code == 404
    assert _ventas(db) == []

    cliente.como(mundo["duena"]).post(_url(mundo["conv"].id), json=_venta())
    r = cliente.como(mundo["gloma"]).post(
        _url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO}
    )
    assert r.status_code == 404
    (venta,) = _ventas(db)
    assert venta.anulada_at is None


def test_todas_las_rutas_de_supervision_son_get():
    metodos = set()
    for ruta in supervision.router.routes:
        metodos |= set(getattr(ruta, "methods", set()) or set())
    assert metodos and metodos <= {"GET", "HEAD"}, metodos


def test_supervision_solo_ve_valor_y_fecha(cliente, mundo, db):
    # Vende Camila; el chat lo atiende Alexandra (eso sí lo muestra la
    # supervisión desde antes, en `atendido_por`).
    cliente.post(_url(mundo["conv"].id), json=_venta(vendida_por="Camila"))
    gloma = cliente.como(mundo["gloma"])

    cuentas = gloma.get("/supervision/cuentas").json()["cuentas"]
    slug = cuentas[0]["slug"]
    lista = gloma.get("/supervision/conversaciones", params={"cuenta": slug})
    assert lista.status_code == 200, lista.text
    (hilo,) = [h for h in lista.json()["conversaciones"] if h["hilo_id"] == f"conv-{mundo['conv'].id}"]
    assert hilo["venta_valor_cop"] == VALOR
    assert hilo["vendida_at"]

    detalle = gloma.get(f"/supervision/conversaciones/conv-{mundo['conv'].id}",
                        params={"cuenta": slug})
    assert detalle.status_code == 200, detalle.text
    assert detalle.json()["venta_valor_cop"] == VALOR
    assert detalle.json()["vendida_at"]

    for crudo in (lista.text, detalle.text):
        for prohibido in ("nota", "motivo_anulacion", "registrada_por_user_id",
                          "vendida_por", "registrada_por_nombre", NOTA, "Camila",
                          "Duena Viajes"):
            assert prohibido not in crudo, prohibido

    # Anulada, la supervisión deja de verla.
    cliente.como(mundo["duena"]).post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO})
    detalle = cliente.como(mundo["gloma"]).get(
        f"/supervision/conversaciones/conv-{mundo['conv'].id}", params={"cuenta": slug}
    )
    assert detalle.json()["venta_valor_cop"] is None
    assert MOTIVO not in detalle.text


# ---------------------------------------------------------------------------
# 1.4 Validación del valor y de quién vendió
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("valor", [0, -1, 500_000_001, "1000", 1000.5, True, None, "", [1000]])
def test_valores_invalidos_dan_422(cliente, mundo, db, valor):
    r = cliente.post(_url(mundo["conv"].id), json=_venta(valor_cop=valor))
    assert r.status_code == 422, (valor, r.text)
    assert _ventas(db) == []


def test_el_tope_exacto_pasa(cliente, mundo, db):
    assert models.VENTA_VALOR_MAX_COP == 500_000_000
    r = cliente.post(_url(mundo["conv"].id), json=_venta(valor_cop=500_000_000))
    assert r.status_code == 201, r.text
    assert _ventas(db)[0].valor_cop == 500_000_000


@pytest.mark.parametrize("vendida_por", ["Fulanita", "", "   ", "alexandra", None, 5])
def test_vendida_por_que_no_es_del_team_da_422(cliente, mundo, db, vendida_por):
    r = cliente.post(_url(mundo["conv"].id), json=_venta(vendida_por=vendida_por))
    assert r.status_code == 422, r.text
    assert _ventas(db) == []


def test_vendida_por_de_otro_team_da_422(cliente, mundo, db):
    """`asesor_1` es la asesora por defecto del team ajeno, no de este."""
    r = cliente.post(_url(mundo["conv"].id), json=_venta(vendida_por="asesor_1"))
    assert r.status_code == 422
    assert _ventas(db) == []


def test_vendida_por_se_recorta(cliente, mundo, db):
    r = cliente.post(_url(mundo["conv"].id), json=_venta(vendida_por="  Camila "))
    assert r.status_code == 201
    assert _ventas(db)[0].vendida_por == "Camila"


@pytest.mark.parametrize("nota,esperado", [
    ("   ", None), (None, None), ("  dos\nlineas  ", "dos\nlineas"),
])
def test_nota_vacia_queda_none_y_se_recorta(cliente, mundo, db, nota, esperado):
    r = cliente.post(_url(mundo["conv"].id), json=_venta(nota=nota))
    assert r.status_code == 201, r.text
    assert _ventas(db)[0].nota == esperado


@pytest.mark.parametrize("nota", ["x" * 281, "tab\taqui", "nulo\x00", "retorno\rcarro"])
def test_nota_larga_o_con_control_da_422(cliente, mundo, db, nota):
    r = cliente.post(_url(mundo["conv"].id), json=_venta(nota=nota))
    assert r.status_code == 422
    assert _ventas(db) == []


# ---------------------------------------------------------------------------
# 1.3 Doble registro y anulación
# ---------------------------------------------------------------------------

def test_doble_registro_da_409(cliente, mundo, db):
    assert cliente.post(_url(mundo["conv"].id), json=_venta()).status_code == 201
    r = cliente.post(_url(mundo["conv"].id), json=_venta(valor_cop=1000))
    assert r.status_code == 409
    assert "ya tiene una venta" in r.json()["detail"]
    (venta,) = _ventas(db)
    assert venta.valor_cop == VALOR


@pytest.mark.parametrize("cuerpo", [{}, {"motivo": ""}, {"motivo": "  ab  "}, {"motivo": "x" * 281},
                                    {"motivo": None}, {"motivo": 123}])
def test_anular_sin_motivo_valido_da_422(cliente, mundo, db, cuerpo):
    cliente.post(_url(mundo["conv"].id), json=_venta())
    r = cliente.post(_url(mundo["conv"].id, "venta/anular"), json=cuerpo)
    assert r.status_code == 422
    assert _ventas(db)[0].anulada_at is None


def test_anular_dos_veces_da_404_y_despues_se_registra_otra(cliente, mundo, db):
    cliente.post(_url(mundo["conv"].id), json=_venta())
    r = cliente.post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": f"  {MOTIVO} "})
    assert r.status_code == 200, r.text
    assert r.json()["motivo_anulacion"] == MOTIVO
    assert r.json()["anulada_at"]

    r = cliente.post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO})
    assert r.status_code == 404

    r = cliente.post(_url(mundo["conv"].id), json=_venta(valor_cop=8_000_000, vendida_por="Camila"))
    assert r.status_code == 201

    vieja, nueva = _ventas(db)
    assert vieja.anulada_at is not None
    assert vieja.anulada_por_user_id == mundo["duena"].id
    assert vieja.motivo_anulacion == MOTIVO
    assert nueva.anulada_at is None and nueva.valor_cop == 8_000_000


def test_anular_sin_venta_da_404(cliente, mundo):
    r = cliente.post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 1.5 Lo que ve /mensajes
# ---------------------------------------------------------------------------

def test_el_detalle_trae_la_activa_y_las_anuladas(cliente, mundo):
    cliente.post(_url(mundo["conv"].id), json=_venta(valor_cop=1_000))
    cliente.post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO})
    cliente.post(_url(mundo["conv"].id), json=_venta(valor_cop=2_000))

    d = cliente.get(f"/mensajes/conversaciones/{mundo['conv'].id}").json()
    assert d["venta"]["valor_cop"] == 2_000
    assert d["venta"]["anulada_at"] is None
    assert [v["valor_cop"] for v in d["ventas_anuladas"]] == [1_000]
    assert d["ventas_anuladas"][0]["motivo_anulacion"] == MOTIVO
    assert "team_id" not in json.dumps(d)


def test_el_detalle_sin_venta(cliente, mundo):
    d = cliente.get(f"/mensajes/conversaciones/{mundo['conv'].id}").json()
    assert d["venta"] is None and d["ventas_anuladas"] == []


def test_la_lista_solo_trae_el_valor(cliente, mundo, db):
    otra = _conversacion(db, mundo["team"].id, wa_id="573002220000")
    cliente.post(_url(mundo["conv"].id), json=_venta())

    lista = cliente.get("/mensajes/conversaciones").json()["conversaciones"]
    por_id = {c["id"]: c for c in lista}
    assert por_id[mundo["conv"].id]["venta_valor_cop"] == VALOR
    assert por_id[otra.id]["venta_valor_cop"] is None
    assert "venta" not in por_id[mundo["conv"].id]
    assert NOTA not in json.dumps(lista)

    # Una anulada no cuenta como venta en la lista.
    cliente.post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO})
    lista = cliente.get("/mensajes/conversaciones").json()["conversaciones"]
    assert {c["id"]: c for c in lista}[mundo["conv"].id]["venta_valor_cop"] is None


def test_la_lista_con_ventas_no_suma_consultas(db, mundo):
    """El valor viaja en la consulta de la página: con 30 ventas, las mismas
    consultas que sin ninguna (y dentro del techo de test_mensajes_paginacion)."""
    member = crud.get_membership_for_user(db, mundo["duena"])
    for i in range(30):
        conv = _conversacion(db, mundo["team"].id, wa_id=f"57301{i:07d}", nombre=None)
        crud.registrar_venta(db, conv, valor_cop=1000 + i, vendida_por="Camila",
                             nota=None, user_id=mundo["duena"].id, bot_id=None)

    conteo = {"n": 0}

    @event.listens_for(Engine, "after_cursor_execute")
    def _contar(*_a):
        conteo["n"] += 1

    try:
        db.expire_all()
        salida = mensajes.list_conversations(
            estado=None, busqueda=None, etiqueta=None, limite=40, pagina=1,
            db=db, member=member,
        )
    finally:
        event.remove(Engine, "after_cursor_execute", _contar)

    assert sum(1 for c in salida.conversaciones if c.venta_valor_cop) == 30
    assert conteo["n"] <= 5, f"{conteo['n']} consultas"


# ---------------------------------------------------------------------------
# 1.6 Logs
# ---------------------------------------------------------------------------

def test_los_logs_no_llevan_valor_nota_nombres_ni_telefono(cliente, mundo, caplog):
    caplog.set_level(logging.DEBUG)
    cliente.post(_url(mundo["conv"].id), json=_venta())
    cliente.post(_url(mundo["conv"].id), json=_venta())                     # 409
    cliente.post(_url(mundo["conv"].id, "venta/anular"), json={"motivo": MOTIVO})
    cliente.post(_url(mundo["conv"].id), json=_venta(vendida_por="Fulanita"))  # 422

    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "venta.registrada" in texto and "venta.anulada" in texto
    for prohibido in (str(VALOR), "7.654.321", NOTA, "3XXXXXXXXX", MOTIVO, "Alexandra",
                      "Fulanita", "Duena Viajes", "Cliente Prueba", TELEFONO):
        assert prohibido not in texto, prohibido


def test_el_repr_de_la_venta_no_lleva_valor_ni_nota(db, mundo):
    venta = crud.registrar_venta(db, mundo["conv"], valor_cop=VALOR, vendida_por="Camila",
                                 nota=NOTA, user_id=mundo["duena"].id, bot_id=None)
    assert str(VALOR) not in repr(venta) and NOTA not in repr(venta)
    assert "Camila" not in repr(venta)


# ---------------------------------------------------------------------------
# 0.7 Atribución por bot
# ---------------------------------------------------------------------------

def test_sin_sesion_de_bot_usa_el_del_reparto_y_nunca_uno_ajeno(db, mundo):
    conv = _conversacion(db, mundo["team"].id, wa_id="573004440000")
    owner = mundo["team"].owner_user_id
    assert crud.bot_que_atendia(db, owner, conv) is None

    conv.bot_asignado_id = mundo["bot"].id
    db.commit()
    assert crud.bot_que_atendia(db, owner, conv) == mundo["bot"].id

    # Un bot de otro owner (forzado en la base) no se atribuye nunca.
    ajeno = models.Bot(user_id=mundo["ajeno"].id, team_id=mundo["team_ajeno"].id,
                       name="Bot Ajeno", engine="llm")
    db.add(ajeno)
    db.commit()
    conv.bot_asignado_id = ajeno.id
    db.add(models.BotSession(bot_id=ajeno.id, conversation_id=conv.id))
    db.commit()
    assert crud.bot_que_atendia(db, owner, conv) is None


# ---------------------------------------------------------------------------
# Postgres: carrera real y FK compuesta
# ---------------------------------------------------------------------------

from tests.test_sprint36_schema_postgres import (  # noqa: E402,F401  (fixtures)
    _cuenta, base, esquema, motor,
)


@pytest.mark.postgres
def test_postgres_dos_registros_a_la_vez_gana_uno_y_el_otro_es_409(motor):
    with sessionmaker(bind=motor)() as sesion:
        team, (conv,) = _cuenta(sesion, "venta-race")
        team.asesores_rotacion = ["Camila"]
        sesion.add(models.TeamMember(team_id=team.id, user_id=team.owner_user_id, role="owner"))
        sesion.commit()
        team_id, conv_id, owner_id = team.id, conv.id, team.owner_user_id

    barrera = threading.Barrier(2)
    resultados: list = [None, None]

    def correr(i):
        with sessionmaker(bind=motor)() as sesion:
            member = (sesion.query(models.TeamMember)
                      .filter(models.TeamMember.user_id == owner_id).one())
            payload = schemas.VentaIn(valor_cop=5_000 + i, vendida_por="Camila")
            # El permiso lo resuelve la dependencia; aquí se llama al endpoint.
            barrera.wait()
            try:
                resultados[i] = mensajes.registrar_venta(conv_id, payload, db=sesion, member=member)
            except HTTPException as error:
                resultados[i] = error.status_code

    hilos = [threading.Thread(target=correr, args=(i,)) for i in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    assert sum(isinstance(r, schemas.VentaOut) for r in resultados) == 1, resultados
    assert resultados.count(409) == 1, resultados
    with sessionmaker(bind=motor)() as sesion:
        filas = sesion.query(models.ConversationSale).all()
        assert len(filas) == 1 and filas[0].team_id == team_id


@pytest.mark.postgres
def test_postgres_fk_compuesta_rechaza_venta_con_team_distinto(motor):
    from sqlalchemy.exc import IntegrityError

    with sessionmaker(bind=motor)() as sesion:
        _team_a, (conv_a,) = _cuenta(sesion, "fk-a")
        team_b, _ = _cuenta(sesion, "fk-b")
        sesion.add(models.ConversationSale(team_id=team_b.id, conversation_id=conv_a.id,
                                           valor_cop=1000))
        with pytest.raises(IntegrityError, match="fk_conversation_sales_conv_team"):
            sesion.commit()
