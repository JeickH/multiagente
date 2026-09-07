"""Agendamientos: a quién se llama, cuándo, y quién puede ver la lista.

Tres cosas se cuidan acá, en este orden de importancia:

  1. **El corte del nivel de interés.** Es la regla de la que depende todo el
     módulo: si clasifica de más, el asesor pierde el día llamando a gente que
     sólo dijo "hola"; si clasifica de menos, se pierden clientes que sí
     preguntaron. Los casos reproducen la FORMA de las conversaciones reales de
     Arranquemos Pues, con textos inventados (`TestNivelDeInteres`).
  2. **El aislamiento entre cuentas.** Por esta pantalla salen teléfonos de
     personas reales. Que una cuenta no vea —ni pueda cerrar— los clientes
     potenciales de otra se prueba explícitamente (`TestAislamiento`).
  3. **Que no se dupliquen.** Dos ticks a la vez, o una persona que vuelve y se
     calla otra vez, no pueden dejarle al asesor dos renglones de la misma
     persona (`TestNoSeDuplica`).

Los teléfonos, los nombres y los mensajes son inventados: este repositorio es
público y lo que escriben los clientes son datos de terceros (regla #8).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.routers import agendamientos as router_agendamientos
from app.services import agendamientos as svc

CLAVE = "Clave-De-Prueba-1"
#: Números sintéticos (regla #8). Los reales van enmascarados como 3XXXXXXXXX.
WA_UNO = "573000000021"
WA_DOS = "573000000022"


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


def _cuenta(db, correo: str, nombre: str, doc: str, *, rol: str = "owner"):
    """Un usuario con su team y su membresía, como una cuenta real."""
    user = crud.create_user(
        db,
        schemas.UserCreate(
            nombre=nombre, correo=correo, tipo_documento="CC",
            documento=doc, password=CLAVE,
        ),
    )
    team = models.Team(nombre=nombre, owner_user_id=user.id)
    db.add(team)
    db.flush()
    member = models.TeamMember(team_id=team.id, user_id=user.id, role=rol)
    db.add(member)
    db.commit()
    db.refresh(member)
    return user, team, member


def _conversacion(db, team, wa_id: str = WA_UNO, nombre: str | None = "Ricardo"):
    conv = models.Conversation(
        team_id=team.id, contact_wa_id=wa_id, contact_name=nombre,
        status="pending", assigned_to="Alexandra",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _mensaje(db, conv, direccion: str, texto: str, *, minuto: int, tipo: str = "text"):
    """Un mensaje con hora controlada: el orden es justo lo que se prueba."""
    msg = models.Message(
        conversation_id=conv.id, direction=direccion, content=texto,
        message_type=tipo, status="sent",
        created_at=datetime(2026, 9, 4, 16, 0) + timedelta(minutes=minuto),
    )
    db.add(msg)
    db.commit()
    return msg


def _solo_saludo(db, conv):
    """El caso de "sólo bienvenida": escribió una vez, recibió el saludo y nunca
    volvió; después, los tres recordatorios y la nota interna.

    Los textos son inventados, con la misma forma que los reales: los mensajes
    de clientes de verdad no se copian a un repo público (regla 8)."""
    _mensaje(db, conv, "inbound", "¡Hola! Quiero más información.", minuto=0)
    _mensaje(db, conv, "outbound", "¡Hola, buen día! 😊 Soy Luisa…", minuto=1)
    _mensaje(db, conv, "outbound", "¿Te quedó alguna otra pregunta?", minuto=15)
    _mensaje(db, conv, "outbound", "¡Hola de nuevo! 👋", minuto=5 * 60)
    _mensaje(db, conv, "outbound", "Última razón por hoy 🌴", minuto=23 * 60)
    _mensaje(
        db, conv, "outbound", "🕒 Conversación abandonada",
        minuto=23 * 60 + 17, tipo="nota_interna",
    )


def _con_informacion(db, conv):
    """El caso de "con información": preguntó, le contestaron, y aun así se fue."""
    _mensaje(db, conv, "inbound", "Buenas, ¿cuántas noches son?", minuto=0)
    _mensaje(db, conv, "outbound", "¡Hola, buen día! 😊 Soy Luisa…", minuto=1)
    _mensaje(db, conv, "inbound", "Ricardo", minuto=5)
    _mensaje(db, conv, "outbound", "¡Un gusto, Ricardo! ¿Para qué mes?", minuto=6)
    _mensaje(db, conv, "inbound", "¿Se pueden tomar más días?", minuto=8)
    _mensaje(db, conv, "outbound", "El plan es de viernes a lunes…", minuto=9)


# ---------------------------------------------------------------------------
# 1. El corte: quién vale una llamada
# ---------------------------------------------------------------------------

class TestNivelDeInteres:
    def test_el_que_solo_recibio_el_saludo_no_vale_llamada(self, db_session):
        _, team, _ = _cuenta(db_session, "ag1@test.com", "Agencia", "AG-001")
        conv = _conversacion(db_session, team)
        _solo_saludo(db_session, conv)

        assert (
            svc.nivel_de_interes(db_session, conv)
            == models.AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA
        )
        assert svc.registrar_por_abandono(db_session, conv) is None
        assert db_session.query(models.Agendamiento).count() == 0

    def test_el_que_pregunto_y_le_contestaron_si(self, db_session):
        _, team, _ = _cuenta(db_session, "ag2@test.com", "Agencia", "AG-002")
        conv = _conversacion(db_session, team)
        _con_informacion(db_session, conv)

        assert (
            svc.nivel_de_interes(db_session, conv)
            == models.AGENDAMIENTO_NIVEL_CON_INFORMACION
        )
        ag = svc.registrar_por_abandono(db_session, conv)
        assert ag is not None
        assert ag.estado == models.AGENDAMIENTO_PENDIENTE
        assert ag.nivel_interes == models.AGENDAMIENTO_NIVEL_CON_INFORMACION

    def test_los_recordatorios_no_cuentan_como_informacion(self, db_session):
        """El bot manda 3 recordatorios él solo, cuando ya no hay nadie del otro
        lado. Contar salientes en vez de la respuesta del cliente haría que
        TODO abandono pareciera un cliente interesado — que es exactamente el
        error que dejaría la lista sin valor."""
        _, team, _ = _cuenta(db_session, "ag3@test.com", "Agencia", "AG-003")
        conv = _conversacion(db_session, team)
        _solo_saludo(db_session, conv)

        salientes = (
            db_session.query(models.Message)
            .filter(
                models.Message.conversation_id == conv.id,
                models.Message.direction == "outbound",
            )
            .count()
        )
        assert salientes == 5  # saludo + 3 recordatorios + nota interna
        assert (
            svc.nivel_de_interes(db_session, conv)
            == models.AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA
        )

    def test_la_nota_interna_no_es_el_saludo(self, db_session):
        """Si la nota contara como "el bot escribió", una conversación que
        arranca con nota quedaría mal clasificada. Se excluye por tipo."""
        _, team, _ = _cuenta(db_session, "ag4@test.com", "Agencia", "AG-004")
        conv = _conversacion(db_session, team)
        _mensaje(db_session, conv, "outbound", "📋 nota", minuto=0, tipo="nota_interna")
        _mensaje(db_session, conv, "inbound", "Hola", minuto=1)

        # Sólo hay nota y un entrante: el bot nunca saludó de verdad.
        assert (
            svc.nivel_de_interes(db_session, conv)
            == models.AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA
        )

    def test_una_conversacion_sin_mensajes_no_revienta(self, db_session):
        _, team, _ = _cuenta(db_session, "ag5@test.com", "Agencia", "AG-005")
        conv = _conversacion(db_session, team)
        assert (
            svc.nivel_de_interes(db_session, conv)
            == models.AGENDAMIENTO_NIVEL_SOLO_BIENVENIDA
        )


# ---------------------------------------------------------------------------
# 2. La fecha de la llamada
# ---------------------------------------------------------------------------

class TestFechaDeLaLlamada:
    def test_son_tres_dias_despues(self, db_session):
        ahora = datetime(2026, 9, 5, 15, 0)  # 10:00 en Colombia
        assert svc.fecha_tentativa(ahora) == date(2026, 9, 8)

    def test_de_madrugada_utc_sigue_siendo_el_dia_de_colombia(self):
        """Las 02:00 UTC del 5 son las 21:00 del 4 en Medellín. Sumar 3 días
        sobre la fecha UTC le correría la llamada un día entero, y el asesor
        llamaría cuando en su calendario ya pasó."""
        ahora = datetime(2026, 9, 5, 2, 0)
        assert svc.hoy_en_colombia(ahora) == date(2026, 9, 4)
        assert svc.fecha_tentativa(ahora) == date(2026, 9, 7)

    def test_se_puede_forzar_una_fecha(self, db_session):
        """Lo que usa el backfill: todo lo viejo se cita el mismo día."""
        _, team, _ = _cuenta(db_session, "ag6@test.com", "Agencia", "AG-006")
        conv = _conversacion(db_session, team)
        _con_informacion(db_session, conv)

        ag = svc.registrar_por_abandono(db_session, conv, fecha=date(2026, 9, 8))
        assert ag.fecha_llamada == date(2026, 9, 8)


# ---------------------------------------------------------------------------
# 3. No se duplica
# ---------------------------------------------------------------------------

class TestNoSeDuplica:
    def test_dos_abandonos_del_mismo_chat_dejan_un_solo_renglon(self, db_session):
        _, team, _ = _cuenta(db_session, "ag7@test.com", "Agencia", "AG-007")
        conv = _conversacion(db_session, team)
        _con_informacion(db_session, conv)

        primero = svc.registrar_por_abandono(db_session, conv)
        segundo = svc.registrar_por_abandono(db_session, conv)

        assert primero.id == segundo.id
        assert db_session.query(models.Agendamiento).count() == 1

    def test_cerrada_la_anterior_si_se_puede_agendar_otra(self, db_session):
        """Volver a escribir, volver a callarse y volver a irse **después** de
        que el asesor ya cerró la llamada es una oportunidad nueva, no un
        duplicado: por eso el índice único es parcial."""
        _, team, _ = _cuenta(db_session, "ag8@test.com", "Agencia", "AG-008")
        conv = _conversacion(db_session, team)
        _con_informacion(db_session, conv)

        primero = svc.registrar_por_abandono(db_session, conv)
        primero.estado = models.AGENDAMIENTO_CERRADO
        db_session.commit()

        segundo = svc.registrar_por_abandono(db_session, conv)
        assert segundo.id != primero.id
        assert db_session.query(models.Agendamiento).count() == 2


# ---------------------------------------------------------------------------
# 4. La pantalla: lista, cierre y aislamiento
# ---------------------------------------------------------------------------

@pytest.fixture
def dos_cuentas(db_session):
    """Dos agencias distintas, cada una con su cliente potencial abandonado."""
    _, team_a, member_a = _cuenta(db_session, "propia@test.com", "Propia", "AG-A")
    _, team_b, member_b = _cuenta(db_session, "ajena@test.com", "Ajena", "AG-B")

    conv_a = _conversacion(db_session, team_a, WA_UNO, "Ricardo")
    _con_informacion(db_session, conv_a)
    ag_a = svc.registrar_por_abandono(db_session, conv_a, asesor="Alexandra")

    conv_b = _conversacion(db_session, team_b, WA_DOS, "Ajeno")
    _con_informacion(db_session, conv_b)
    ag_b = svc.registrar_por_abandono(db_session, conv_b, asesor="Otra")

    return {
        "a": (team_a, member_a, conv_a, ag_a),
        "b": (team_b, member_b, conv_b, ag_b),
    }


class TestLaLista:
    def test_trae_el_telefono_y_la_fecha_que_es_para_lo_que_existe(
        self, db_session, dos_cuentas
    ):
        _, member, conv, _ = dos_cuentas["a"]
        salida = router_agendamientos.listar_agendamientos(
            estado=None, limite=20, pagina=1, db=db_session, member=member
        )
        assert len(salida.agendamientos) == 1
        fila = salida.agendamientos[0]
        assert fila.telefono == conv.contact_wa_id
        assert fila.contacto == "Ricardo"
        assert fila.asesor == "Alexandra"
        assert fila.estado == models.AGENDAMIENTO_PENDIENTE
        assert fila.nivel_interes == models.AGENDAMIENTO_NIVEL_CON_INFORMACION

    def test_ordena_por_fecha_de_llamada_lo_vencido_primero(self, db_session):
        _, team, member = _cuenta(db_session, "orden@test.com", "Agencia", "AG-ORD")
        for i, dia in enumerate((12, 8, 10)):
            conv = _conversacion(db_session, team, f"57300000010{i}", f"C{i}")
            _con_informacion(db_session, conv)
            svc.registrar_por_abandono(db_session, conv, fecha=date(2026, 9, dia))

        salida = router_agendamientos.listar_agendamientos(
            estado=None, limite=20, pagina=1, db=db_session, member=member
        )
        assert [f.fecha_llamada.day for f in salida.agendamientos] == [8, 10, 12]

    def test_el_resumen_cuenta_todo_el_team_no_el_filtro(
        self, db_session, dos_cuentas
    ):
        """Con el filtro en "cerrados", un `pendientes` calculado sobre el
        filtro diría cero y el asesor creería que no le queda nada."""
        _, member, _, ag = dos_cuentas["a"]
        ag.estado = models.AGENDAMIENTO_CERRADO
        db_session.commit()

        salida = router_agendamientos.listar_agendamientos(
            estado=models.AGENDAMIENTO_CERRADO, limite=20, pagina=1,
            db=db_session, member=member,
        )
        assert salida.resumen.cerrados == 1
        assert salida.resumen.pendientes == 0
        assert salida.resumen.total == 1

    def test_un_estado_inventado_se_rechaza(self, db_session, dos_cuentas):
        _, member, _, _ = dos_cuentas["a"]
        with pytest.raises(HTTPException) as e:
            router_agendamientos.listar_agendamientos(
                estado="urgente", limite=20, pagina=1, db=db_session, member=member
            )
        assert e.value.status_code == 400


class TestCerrarYReabrir:
    def test_el_asesor_la_cierra(self, db_session, dos_cuentas):
        user_a = db_session.query(models.User).filter_by(correo="propia@test.com").first()
        _, member, _, ag = dos_cuentas["a"]

        salida = router_agendamientos.cambiar_estado(
            agendamiento_id=ag.id,
            cambio=router_agendamientos.CambioEstadoIn(estado="cerrado"),
            db=db_session, member=member, user=user_a,
        )
        assert salida.estado == models.AGENDAMIENTO_CERRADO
        db_session.refresh(ag)
        assert ag.cerrado_at is not None
        assert ag.cerrado_por_user_id == user_a.id

    def test_reabrir_borra_la_marca_de_cierre(self, db_session, dos_cuentas):
        user_a = db_session.query(models.User).filter_by(correo="propia@test.com").first()
        _, member, _, ag = dos_cuentas["a"]
        for estado in ("cerrado", "pendiente"):
            router_agendamientos.cambiar_estado(
                agendamiento_id=ag.id,
                cambio=router_agendamientos.CambioEstadoIn(estado=estado),
                db=db_session, member=member, user=user_a,
            )
        db_session.refresh(ag)
        assert ag.estado == models.AGENDAMIENTO_PENDIENTE
        assert ag.cerrado_at is None
        assert ag.cerrado_por_user_id is None

    def test_un_estado_que_no_existe_no_pasa_el_schema(self):
        with pytest.raises(ValueError):
            router_agendamientos.CambioEstadoIn(estado="archivado")


class TestAislamiento:
    def test_cada_cuenta_ve_solo_lo_suyo(self, db_session, dos_cuentas):
        for clave, esperado in (("a", WA_UNO), ("b", WA_DOS)):
            _, member, _, _ = dos_cuentas[clave]
            salida = router_agendamientos.listar_agendamientos(
                estado=None, limite=20, pagina=1, db=db_session, member=member
            )
            assert [f.telefono for f in salida.agendamientos] == [esperado]

    def test_no_se_puede_cerrar_el_de_otra_cuenta(self, db_session, dos_cuentas):
        """El id viaja en la URL. Adivinarlo no puede alcanzar para tocar la
        fila de otro tenant: el `team_id` va en el WHERE, no en un `if`."""
        user_a = db_session.query(models.User).filter_by(correo="propia@test.com").first()
        _, member_a, _, _ = dos_cuentas["a"]
        _, _, _, ag_ajeno = dos_cuentas["b"]

        with pytest.raises(HTTPException) as e:
            router_agendamientos.cambiar_estado(
                agendamiento_id=ag_ajeno.id,
                cambio=router_agendamientos.CambioEstadoIn(estado="cerrado"),
                db=db_session, member=member_a, user=user_a,
            )
        assert e.value.status_code == 404
        db_session.refresh(ag_ajeno)
        assert ag_ajeno.estado == models.AGENDAMIENTO_PENDIENTE

    def test_el_asesor_tambien_ve_la_ventana(self, db_session):
        """Pedido del CEO: la ven todos los tipos de cuenta. Un `agent` sin
        permisos especiales entra igual que el dueño."""
        _, team, _ = _cuenta(db_session, "duenio@test.com", "Agencia", "AG-DUE")
        asesor = crud.create_user(
            db_session,
            schemas.UserCreate(
                nombre="Alexandra", correo="alexandra@test.com", tipo_documento="CC",
                documento="AG-ASE", password=CLAVE,
            ),
        )
        member_asesor = models.TeamMember(
            team_id=team.id, user_id=asesor.id, role="agent"
        )
        db_session.add(member_asesor)
        db_session.commit()
        db_session.refresh(member_asesor)

        conv = _conversacion(db_session, team)
        _con_informacion(db_session, conv)
        svc.registrar_por_abandono(db_session, conv, asesor="Alexandra")

        salida = router_agendamientos.listar_agendamientos(
            estado=None, limite=20, pagina=1, db=db_session, member=member_asesor
        )
        assert len(salida.agendamientos) == 1

    def test_ningun_endpoint_queda_sin_portero(self):
        """La alarma para el que agregue el siguiente endpoint: sin
        `get_current_membership` la lista de teléfonos queda abierta."""
        import inspect

        from fastapi import params

        for ruta in router_agendamientos.router.routes:
            firma = inspect.signature(ruta.endpoint)
            porteros = [
                p.default.dependency.__name__
                for p in firma.parameters.values()
                if isinstance(p.default, params.Depends) and p.default.dependency
            ]
            assert "get_current_membership" in porteros, ruta.path
