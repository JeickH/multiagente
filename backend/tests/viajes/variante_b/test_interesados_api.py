"""API de Interesados: `/agendamientos/interesados` (lista, tomar, cambiar estado).

Por esta pantalla salen nombre y teléfono de clientes reales, y "tomar" cambia
quién le responde al cliente. Lo que se cuida:

  1. **Aislamiento entre cuentas**: lo ajeno da el mismo 404 que lo inexistente,
     en lectura y en escritura (`TestAislamiento`).
  2. **La frontera exacta del umbral** de 6 h y que el interesado salga solo de
     la lista al abandonar, al haber handoff o al cerrar el bot
     (`TestQuienEsInteresado`).
  3. **Tomar**: 200/409/410/403, lo puede una asesora `agent` con permiso de
     responder, gana una sola si dos lo intentan, y el efecto es el del handoff
     (`TestTomar`).
  4. **Contactado / descartado / deshacer**, con el motivo de una lista cerrada
     (`TestCambiarEstado`).
  5. Orden, resumen y que la página no haga N+1 (`TestListaYOrden`).

Se prueba por HTTP (TestClient) para que los porteros (`get_current_membership`,
`require_permission`) sean los de verdad. Datos inventados (regla #8).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from app import crud, models, schemas
from app.data.bot_viajes import LLM_CONFIG
from app.services import agendamientos as svc
from app.services import bot_runner

from .test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    WA_1,
    WA_2,
    WA_3,
    Sesion,
    conversacion,
    crear_agencia,
    db,
    interesado,
    mensaje,
    motor,
)


def _cliente(Sesion, usuario):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_db
    from app.routers import agendamientos

    app = FastAPI()
    app.include_router(agendamientos.router)

    def _get_db():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: usuario
    return TestClient(app)


AHORA = datetime.utcnow


def _visible(db, ag, **kw):
    """Un interesado que ya cumplió el umbral: empezó hace 7 h y el cliente
    escribió hace 1 h."""
    ahora = AHORA()
    kw.setdefault("inicio", ahora - timedelta(hours=7))
    kw.setdefault("ultimo_entrante", ahora - timedelta(hours=1))
    return interesado(db, ag, **kw)


@pytest.fixture
def ag(db):
    return crear_agencia(db, sufijo="A")


@pytest.fixture
def otra(db):
    return crear_agencia(db, sufijo="B")


# ---------------------------------------------------------------------------
# 1. Aislamiento
# ---------------------------------------------------------------------------

class TestAislamiento:
    def test_cada_cuenta_ve_solo_lo_suyo(self, db, Sesion, ag, otra):
        mio = _visible(db, ag, wa_id=WA_1)
        _visible(db, otra, wa_id=WA_2)

        r = _cliente(Sesion, ag["asesora"]).get("/agendamientos/interesados")
        assert r.status_code == 200
        assert [i["id"] for i in r.json()["interesados"]] == [mio.id]
        assert r.json()["resumen"]["por_contactar"] == 1

    @pytest.mark.parametrize("accion", ["tomar", "patch"])
    def test_lo_ajeno_da_el_mismo_404_que_lo_inexistente(self, db, Sesion, ag, otra, accion):
        ajeno = _visible(db, otra, wa_id=WA_2)
        c = _cliente(Sesion, ag["asesora"])

        def pedir(i):
            if accion == "tomar":
                return c.post(f"/agendamientos/interesados/{i}/tomar")
            return c.patch(f"/agendamientos/interesados/{i}", json={"estado": "contactado"})

        r_ajeno, r_nada = pedir(ajeno.id), pedir(999999)
        assert r_ajeno.status_code == r_nada.status_code == 404
        assert r_ajeno.json() == r_nada.json()
        db.refresh(ajeno)
        assert ajeno.estado == models.INTENCION_POR_CONTACTAR
        conv = db.query(models.Conversation).get(ajeno.conversation_id)
        assert conv.assigned_to == "bot"

    def test_habilitado_y_puede_tomar_salen_del_servidor(self, db, Sesion, ag):
        sin_flag = crear_agencia(db, sufijo="NF", cfg=json.loads(json.dumps(LLM_CONFIG)))
        sin_permiso = crear_agencia(db, sufijo="NP", permiso_responder=False)

        r = _cliente(Sesion, ag["asesora"]).get("/agendamientos/interesados").json()
        assert r["habilitado"] is True and r["puede_tomar"] is True and r["umbral_horas"] == 6
        r = _cliente(Sesion, sin_flag["duenio"]).get("/agendamientos/interesados").json()
        assert r["habilitado"] is False and r["puede_tomar"] is True
        r = _cliente(Sesion, sin_permiso["asesora"]).get("/agendamientos/interesados").json()
        assert r["puede_tomar"] is False

    def test_bot_en_pausa_no_habilita(self, db, Sesion, ag):
        ag["bot"].status = "paused"
        db.commit()
        r = _cliente(Sesion, ag["duenio"]).get("/agendamientos/interesados").json()
        assert r["habilitado"] is False


# ---------------------------------------------------------------------------
# 2. Quién es interesado
# ---------------------------------------------------------------------------

def _ids(db, team_id, ahora, estado=models.INTENCION_POR_CONTACTAR):
    filas, total, _ = svc.listar_interesados(
        db, team_id=team_id, estado=estado, pagina=1, limite=50, ahora=ahora,
    )
    return [f[0].id for f in filas]


class TestQuienEsInteresado:
    def test_frontera_exacta_de_las_6_horas(self, db, ag):
        inicio = datetime(2026, 10, 7, 9, 0, 0)
        fila = interesado(db, ag, inicio=inicio, ultimo_entrante=inicio + timedelta(minutes=5))
        assert fila.visible_desde == inicio + timedelta(hours=6)

        justo = inicio + timedelta(hours=6)
        assert _ids(db, ag["team"].id, justo) == [fila.id]
        assert _ids(db, ag["team"].id, justo - timedelta(microseconds=1)) == []
        # Mismo criterio fila por fila (lo usa "tomar").
        conv = db.query(models.Conversation).get(fila.conversation_id)
        assert svc.sigue_siendo_interesado(fila, conv, fila.session, justo)
        assert not svc.sigue_siendo_interesado(
            fila, conv, fila.session, justo - timedelta(microseconds=1))

    def test_umbral_configurado_por_el_bot(self, db, motor):
        ag = crear_agencia(db, sufijo="U2", cfg={**json.loads(json.dumps(LLM_CONFIG)),
                                                  "intencion_compra": {"horas_para_interesado": 2}})
        conv = conversacion(db, ag["team"])
        s = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                                user_input="quiero reservar", meta_account=None)
        fila = db.query(models.IntencionCompra).one()
        assert fila.visible_desde == s.started_at + timedelta(hours=2)

    def test_sale_de_la_lista_cuando_se_abandona(self, db, ag, motor):
        conv = conversacion(db, ag["team"])
        s = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                                user_input="¿cuánto es el anticipo?", meta_account=None)
        fila = db.query(models.IntencionCompra).one()
        despues = s.started_at + timedelta(hours=7)
        assert _ids(db, ag["team"].id, despues) == [fila.id]

        pa = models.BotPendingAction(
            session_id=s.id, scheduled_at=datetime.utcnow(),
            action_type=models.BOT_PENDING_ACTION_ABANDONO,
            status=models.BOT_PENDING_STATUS_PENDING,
            created_at=datetime.utcnow() - timedelta(minutes=1),
        )
        db.add(pa)
        db.commit()
        bot_runner.process_pending_action(db, pa)
        db.refresh(conv)
        assert conv.assigned_to != "bot"
        assert _ids(db, ag["team"].id, despues) == []

    def test_sale_de_la_lista_con_el_handoff_del_bot(self, db, ag, motor):
        conv = conversacion(db, ag["team"])
        s = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                                user_input="quiero reservar", meta_account=None)
        despues = s.started_at + timedelta(hours=7)
        assert len(_ids(db, ag["team"].id, despues)) == 1
        motor.turno("Te paso con un asesor", finished=True,
                    extra_actions=[{"type": "handoff", "payload": {"resumen": "reserva"}}])
        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=s,
                            user_input="con una persona", meta_account=None)
        assert _ids(db, ag["team"].id, despues) == []

    def test_sale_de_la_lista_cuando_el_bot_cierra(self, db, ag, motor):
        conv = conversacion(db, ag["team"])
        s = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                                user_input="quiero reservar", meta_account=None)
        motor.guion.append({
            "actions": [{"type": "end", "payload": {"text": "¡Gracias, feliz día!"}}],
            "next_state": None, "finished": True, "telemetry": {"tools": []},
        })
        bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=s,
                            user_input="gracias, lo pienso", meta_account=None)
        assert _ids(db, ag["team"].id, s.started_at + timedelta(hours=7)) == []

    def test_conversacion_closed_con_el_bot_hablando_sigue_saliendo(self, db, ag):
        """El cliente vuelve fuera de `retomar`: sesión nueva y la conversación
        queda `closed` mientras el bot contesta (comportamiento del bot 1). La
        que manda es la sesión viva + el bot a cargo."""
        fila = _visible(db, ag)
        conv = db.query(models.Conversation).get(fila.conversation_id)
        conv.status = "closed"
        db.commit()
        assert _ids(db, ag["team"].id, AHORA()) == [fila.id]


# ---------------------------------------------------------------------------
# 3. Tomar
# ---------------------------------------------------------------------------

class TestTomar:
    def test_la_asesora_agent_la_toma(self, db, Sesion, ag):
        fila = _visible(db, ag)
        pa = models.BotPendingAction(
            session_id=fila.session_id, scheduled_at=AHORA() + timedelta(minutes=10),
            action_type=models.BOT_PENDING_ACTION_SEGUIMIENTO,
            status=models.BOT_PENDING_STATUS_PENDING,
        )
        db.add(pa)
        db.commit()

        r = _cliente(Sesion, ag["asesora"]).post(f"/agendamientos/interesados/{fila.id}/tomar")
        assert r.status_code == 200, r.text
        item = r.json()
        assert item["id"] == fila.id and item["atiende"] == "asesor"
        assert item["tomado_por"] == ag["asesora"].nombre
        assert item["estado"] == "contactado"

        db.expire_all()
        conv = db.query(models.Conversation).get(fila.conversation_id)
        assert conv.assigned_to == ag["asesora"].nombre and conv.status == "pending"
        fila = db.query(models.IntencionCompra).get(fila.id)
        assert fila.tomado_por_user_id == ag["asesora"].id and fila.tomado_at is not None
        assert db.query(models.BotSession).get(fila.session_id).status == models.BOT_SESSION_FINISHED
        assert db.query(models.BotPendingAction).get(pa.id).status == models.BOT_PENDING_STATUS_DONE
        [nota] = db.query(models.Message).filter(
            models.Message.conversation_id == conv.id,
            models.Message.message_type == "nota_interna").all()
        assert nota.sent_by_user_id == ag["asesora"].id
        assert f"Tomada por {ag['asesora'].nombre} desde Interesados" in nota.content
        # Al cliente no le salió nada.
        assert db.query(models.Message).filter(
            models.Message.conversation_id == conv.id,
            models.Message.direction == "outbound",
            models.Message.message_type != "nota_interna",
            models.Message.created_at > AHORA() - timedelta(minutes=5),
        ).count() == 0
        # Y deja de salir en "por contactar".
        assert _ids(db, ag["team"].id, AHORA()) == []

    def test_dos_veces_da_409(self, db, Sesion, ag, otra):
        fila = _visible(db, ag)
        c = _cliente(Sesion, ag["asesora"])
        assert c.post(f"/agendamientos/interesados/{fila.id}/tomar").status_code == 200
        r = _cliente(Sesion, ag["duenio"]).post(f"/agendamientos/interesados/{fila.id}/tomar")
        assert r.status_code == 409
        # Sin el nombre de quien la tiene.
        assert ag["asesora"].nombre not in r.text

    def test_si_otra_persona_gana_la_carrera_da_409(self, db, Sesion, ag, monkeypatch):
        fila = _visible(db, ag)
        real = crud.asignar_si_sigue

        def llega_otra_primero(db_, **kw):
            otra = Sesion()
            real(otra, conversation_id=kw["conversation_id"], team_id=kw["team_id"],
                 esperado="bot", destino="Julián")
            otra.commit()
            otra.close()
            return real(db_, **kw)

        monkeypatch.setattr(crud, "asignar_si_sigue", llega_otra_primero)
        r = _cliente(Sesion, ag["asesora"]).post(f"/agendamientos/interesados/{fila.id}/tomar")
        assert r.status_code == 409
        db.expire_all()
        assert db.query(models.Conversation).get(fila.conversation_id).assigned_to == "Julián"
        assert db.query(models.IntencionCompra).get(fila.id).tomado_por_user_id is None

    def test_ya_asignada_a_una_persona_da_409(self, db, Sesion, ag):
        fila = _visible(db, ag)
        conv = db.query(models.Conversation).get(fila.conversation_id)
        conv.assigned_to = "Camila"
        db.commit()
        r = _cliente(Sesion, ag["asesora"]).post(f"/agendamientos/interesados/{fila.id}/tomar")
        assert r.status_code == 409

    @pytest.mark.parametrize("caso", ["sesion_terminada", "no_cumple_umbral", "descartado"])
    def test_si_ya_no_es_interesado_da_410(self, db, Sesion, ag, caso):
        if caso == "no_cumple_umbral":
            fila = _visible(db, ag, inicio=AHORA() - timedelta(hours=5, minutes=59))
        else:
            fila = _visible(db, ag)
        if caso == "sesion_terminada":
            fila.session.status = models.BOT_SESSION_FINISHED
        if caso == "descartado":
            fila.estado = models.INTENCION_DESCARTADO
        db.commit()
        r = _cliente(Sesion, ag["asesora"]).post(f"/agendamientos/interesados/{fila.id}/tomar")
        assert r.status_code == 410
        db.expire_all()
        assert db.query(models.Conversation).get(fila.conversation_id).assigned_to == "bot"

    def test_sin_permiso_de_responder_da_403(self, db, Sesion):
        ag = crear_agencia(db, sufijo="NP2", permiso_responder=False)
        fila = _visible(db, ag)
        r = _cliente(Sesion, ag["asesora"]).post(f"/agendamientos/interesados/{fila.id}/tomar")
        assert r.status_code == 403
        db.expire_all()
        assert db.query(models.Conversation).get(fila.conversation_id).assigned_to == "bot"

    def test_el_body_no_elige_destino(self, db, Sesion, ag):
        fila = _visible(db, ag)
        r = _cliente(Sesion, ag["asesora"]).post(
            f"/agendamientos/interesados/{fila.id}/tomar",
            json={"assigned_to": "Otra persona", "team_id": 999},
        )
        assert r.status_code == 200
        db.expire_all()
        assert db.query(models.Conversation).get(fila.conversation_id).assigned_to == ag["asesora"].nombre


# ---------------------------------------------------------------------------
# 4. Contactado / descartado / deshacer
# ---------------------------------------------------------------------------

class TestCambiarEstado:
    def test_contactado_sale_de_la_lista_y_el_bot_sigue(self, db, Sesion, ag):
        fila = _visible(db, ag)
        c = _cliente(Sesion, ag["asesora"])
        r = c.patch(f"/agendamientos/interesados/{fila.id}", json={"estado": "contactado"})
        assert r.status_code == 200
        item = r.json()
        assert item["estado"] == "contactado" and item["gestionado_por"] == ag["asesora"].nombre
        assert item["gestionado_at"] and item["atiende"] == "bot"
        assert c.get("/agendamientos/interesados").json()["interesados"] == []
        lista = c.get("/agendamientos/interesados?estado=contactado").json()
        assert [i["id"] for i in lista["interesados"]] == [fila.id]
        assert lista["resumen"]["contactados_hoy"] == 1
        db.expire_all()
        assert db.query(models.Conversation).get(fila.conversation_id).assigned_to == "bot"

    def test_descartar_con_motivo_y_deshacer(self, db, Sesion, ag):
        fila = _visible(db, ag)
        c = _cliente(Sesion, ag["asesora"])
        r = c.patch(f"/agendamientos/interesados/{fila.id}",
                    json={"estado": "descartado", "motivo": "ya_compro"})
        assert r.status_code == 200 and r.json()["motivo_descarte"] == "ya_compro"

        r = c.patch(f"/agendamientos/interesados/{fila.id}", json={"estado": "por_contactar"})
        assert r.status_code == 200
        item = r.json()
        assert item["estado"] == "por_contactar"
        assert item["motivo_descarte"] is None and item["gestionado_por"] is None
        assert [i["id"] for i in c.get("/agendamientos/interesados").json()["interesados"]] == [fila.id]

    @pytest.mark.parametrize(
        "body",
        [
            {"estado": "descartado"},                                   # falta motivo
            {"estado": "descartado", "motivo": "me cayó mal, 3000000000"},  # texto libre
            {"estado": "contactado", "motivo": "otro"},                 # motivo sin descartar
            {"estado": "cerrado"},
            {"estado": "contactado", "team_id": 2},                     # campo extra
        ],
    )
    def test_validacion(self, db, Sesion, ag, body):
        fila = _visible(db, ag)
        r = _cliente(Sesion, ag["asesora"]).patch(f"/agendamientos/interesados/{fila.id}", json=body)
        assert r.status_code == 422
        db.refresh(fila)
        assert fila.estado == models.INTENCION_POR_CONTACTAR

    def test_filtros_invalidos(self, db, Sesion, ag):
        c = _cliente(Sesion, ag["asesora"])
        r = c.get("/agendamientos/interesados?estado=todos")
        assert r.status_code == 400 and r.json() == {"detail": "Estado no válido"}
        assert c.get("/agendamientos/interesados?limite=201").status_code == 422
        assert c.get("/agendamientos/interesados?pagina=0").status_code == 422


# ---------------------------------------------------------------------------
# 5. Lista, orden, resumen, sin N+1
# ---------------------------------------------------------------------------

class TestListaYOrden:
    def test_orden_y_resumen(self, db, Sesion, ag):
        ahora = AHORA()
        inicio = ahora - timedelta(hours=40)
        cierra_en_4h = interesado(db, ag, wa_id="573000000301", inicio=inicio,
                                  ultimo_entrante=ahora - timedelta(hours=20))
        cierra_en_22h = interesado(db, ag, wa_id="573000000302", inicio=inicio,
                                   ultimo_entrante=ahora - timedelta(hours=2))
        urgente = interesado(db, ag, wa_id="573000000303", inicio=inicio,
                             ultimo_entrante=ahora - timedelta(hours=22))
        cerrada_reciente = interesado(db, ag, wa_id="573000000304", inicio=inicio,
                                      ultimo_entrante=ahora - timedelta(hours=26))
        cerrada_vieja = interesado(db, ag, wa_id="573000000305", inicio=inicio,
                                   ultimo_entrante=ahora - timedelta(hours=30))

        r = _cliente(Sesion, ag["asesora"]).get("/agendamientos/interesados").json()
        assert [i["id"] for i in r["interesados"]] == [
            urgente.id, cierra_en_4h.id, cierra_en_22h.id,
            cerrada_reciente.id, cerrada_vieja.id,
        ]
        assert r["resumen"] == {"por_contactar": 5, "urgentes": 1, "ventana_cerrada": 2,
                                "contactados_hoy": 0}
        primero = r["interesados"][0]
        ultimo = datetime.fromisoformat(primero["ultimo_mensaje_cliente_at"])
        assert datetime.fromisoformat(primero["ventana_cierra_at"]) == ultimo + timedelta(hours=24)
        assert primero["bot"] == {"id": ag["bot"].id, "nombre": ag["bot"].name}
        assert primero["telefono"] == "573000000303" and primero["contacto"] == "Valentina"
        assert primero["tipos"] == ["anticipo"]

    def test_paginacion_y_total(self, db, Sesion, ag):
        for n in range(5):
            _visible(db, ag, wa_id=f"57300000040{n}")
        r = _cliente(Sesion, ag["asesora"]).get("/agendamientos/interesados?limite=2&pagina=3").json()
        assert r["total"] == 5 and len(r["interesados"]) == 1
        assert r["pagina"] == 3 and r["por_pagina"] == 2

    def test_interes_sale_de_la_ultima_consulta_de_precios(self, db, Sesion, ag):
        fila = _visible(db, ag)
        for entrada in ({"mes": "noviembre"}, {"mes": "diciembre", "variante": "Amor de Dios"}):
            db.add(models.BotLlmDecision(
                bot_id=ag["bot"].id, session_id=fila.session_id,
                conversation_id=fila.conversation_id, source="whatsapp",
                tools_called=json.dumps([{"tool": "consultar_precios", "input": entrada,
                                          "resultado": "..."}]),
            ))
            db.commit()
        hoy = svc.hoy_en_colombia()
        anio = hoy.year if 12 >= hoy.month else hoy.year + 1
        [item] = _cliente(Sesion, ag["asesora"]).get("/agendamientos/interesados").json()["interesados"]
        assert item["interes"] == {"mes": f"{anio}-12", "hotel": "Amor de Dios"}

    def test_mes_de_la_consulta(self):
        from datetime import date

        hoy = date(2026, 10, 7)
        assert svc._mes_iso("diciembre", None, hoy) == "2026-12"
        assert svc._mes_iso("Enero", None, hoy) == "2027-01"
        assert svc._mes_iso("octubre", None, hoy) == "2026-10"
        assert svc._mes_iso("x", "2027-03-14", hoy) == "2027-03"
        assert svc._mes_iso("2026-11", None, hoy) == "2026-11"
        assert svc._mes_iso("el que sea", None, hoy) is None

    def test_sin_n_mas_1(self, db, Sesion, ag):
        """La página de 1 y la de 6 hacen el mismo número de consultas."""
        engine = Sesion.kw["bind"]
        contador = {"n": 0}

        def contar(*a, **k):
            contador["n"] += 1

        def consultas_de_la_pagina():
            contador["n"] = 0
            event.listen(engine, "before_cursor_execute", contar)
            try:
                r = _cliente(Sesion, ag["asesora"]).get("/agendamientos/interesados")
            finally:
                event.remove(engine, "before_cursor_execute", contar)
            assert r.status_code == 200
            return contador["n"], len(r.json()["interesados"])

        # La primera fila ya trae de todo (sin nombre, consulta de precios,
        # gestionada): las consultas "por si hay algo" se pagan desde la 1.
        conv0 = _visible(db, ag, wa_id="573000000500", nombre=None)
        db.add(models.BotLlmDecision(
            bot_id=ag["bot"].id, session_id=conv0.session_id, source="whatsapp",
            tools_called=json.dumps([{"tool": "consultar_tarifario", "input": {"mes": "enero"}}]),
        ))
        conv0.gestionado_por_user_id = ag["asesora"].id
        db.commit()
        n1, filas1 = consultas_de_la_pagina()
        for n in range(1, 6):
            fila = _visible(db, ag, wa_id=f"57300000050{n}", nombre=None if n % 2 else "Ana")
            db.add(models.BotLlmDecision(
                bot_id=ag["bot"].id, session_id=fila.session_id, source="whatsapp",
                tools_called=json.dumps([{"tool": "consultar_tarifario",
                                          "input": {"mes": "diciembre"}}]),
            ))
            fila.gestionado_por_user_id = ag["asesora"].id
            db.commit()
        n6, filas6 = consultas_de_la_pagina()
        assert (filas1, filas6) == (1, 6)
        assert n6 == n1
        assert conv0 is not None

    def test_el_tutorial_nuevo_esta_permitido(self):
        assert "agendamientos_interesados" in schemas.ALLOWED_TUTORIAL_MODULES
