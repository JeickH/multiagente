"""Pausa del servicio por falta de pago.

Lo que se fija acá, en orden de qué duele más si se rompe:

1. **Nadie se pausa sin orden.** El default es `nunca`, y una cuenta en
   `nunca` con tres meses de mora sigue funcionando. Se desplegó así a pedido
   del CEO: la regla existe pero no se le enciende a nadie sola.
2. **El mes de mora se cuenta bien.** Vence el 2-sep → sigue el 2-oct, se
   pausa el 3-oct. Y se reanuda sola al pagar.
3. **Lo que se bloquea, se bloquea en el backend**: envío manual, plantillas,
   adjuntos y campañas responden 402; el bot no responde por Twilio y no
   manda lo que tenía agendado. El mensaje del cliente sí queda guardado.
4. **El aviso** trae `pausado`, y lo ve también el asesor.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def emitir(db, team_id, *, vence: date, estado=None):
    from app.services import facturas as svc

    factura = svc.emitir(
        db, team_id,
        concepto="Suscripción mensual Gloma",
        amount_cents=350_000 * 100,
        due_date=vence,
        issued_on=vence,
        detalle="Detalle de prueba",
    )
    if estado is not None:
        factura.status = estado
    db.commit()
    return factura


def poner_pausa(db, team, modo):
    team.pausa_servicio = modo
    db.commit()


@pytest.fixture
def hoy(monkeypatch):
    """Congela "hoy" donde lo pregunta la pausa (a través de `facturas`)."""
    from app.services import facturas as svc

    estado = {"dia": date(2026, 10, 3)}
    monkeypatch.setattr(svc, "hoy_colombia", lambda: estado["dia"])
    return estado


# ---------------------------------------------------------------------------
# 1. Sin orden no se pausa nadie
# ---------------------------------------------------------------------------

class TestSinOrdenNoSePausa:
    def test_el_default_es_nunca(self, db, team):
        from app import models

        db.refresh(team["team"])
        assert team["team"].pausa_servicio == models.PAUSA_NUNCA

    def test_nunca_con_meses_de_mora_sigue_activa(self, db, team, hoy):
        from app.services import pausa

        emitir(db, team["team"].id, vence=date(2026, 6, 2))
        assert pausa.servicio_pausado(db, team["team"].id) is False

    def test_el_check_rechaza_un_valor_mal_escrito(self, db, team):
        from sqlalchemy.exc import IntegrityError

        team["team"].pausa_servicio = "pausado"
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


# ---------------------------------------------------------------------------
# 2. El mes de mora
# ---------------------------------------------------------------------------

class TestUnMesDeMora:
    @pytest.mark.parametrize(
        "entrada,salida",
        [
            (date(2026, 9, 2), date(2026, 10, 2)),
            (date(2026, 1, 31), date(2026, 2, 28)),
            (date(2028, 1, 31), date(2028, 2, 29)),
            (date(2026, 12, 15), date(2027, 1, 15)),
        ],
    )
    def test_sumar_un_mes(self, entrada, salida):
        from app.services.pausa import sumar_un_mes

        assert sumar_un_mes(entrada) == salida

    def test_el_dia_que_cumple_el_mes_todavia_no(self, db, team, hoy):
        from app import models
        from app.services import pausa

        poner_pausa(db, team["team"], models.PAUSA_POR_MORA)
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        hoy["dia"] = date(2026, 10, 2)
        assert pausa.servicio_pausado(db, team["team"].id) is False

    def test_al_dia_siguiente_se_pausa(self, db, team, hoy):
        from app import models
        from app.services import pausa

        poner_pausa(db, team["team"], models.PAUSA_POR_MORA)
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        hoy["dia"] = date(2026, 10, 3)
        assert pausa.servicio_pausado(db, team["team"].id) is True

    def test_pagar_la_reanuda_sola(self, db, team, hoy):
        from app import models
        from app.services import pausa

        poner_pausa(db, team["team"], models.PAUSA_POR_MORA)
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        assert pausa.servicio_pausado(db, team["team"].id) is True

        factura.status = models.INVOICE_PAGADA
        db.commit()
        assert pausa.servicio_pausado(db, team["team"].id) is False

    def test_una_anulada_no_cuenta(self, db, team, hoy):
        from app import models
        from app.services import pausa

        poner_pausa(db, team["team"], models.PAUSA_POR_MORA)
        emitir(
            db, team["team"].id, vence=date(2026, 8, 2),
            estado=models.INVOICE_ANULADA,
        )
        assert pausa.servicio_pausado(db, team["team"].id) is False

    def test_la_mora_de_otra_cuenta_no_pausa_esta(self, db, team, hoy):
        from app import models
        from app.services import pausa

        otra = models.Team(nombre="Otra", owner_user_id=team["dueño"].id)
        db.add(otra)
        db.commit()
        emitir(db, otra.id, vence=date(2026, 6, 2))
        poner_pausa(db, team["team"], models.PAUSA_POR_MORA)
        assert pausa.servicio_pausado(db, team["team"].id) is False

    def test_pausada_a_mano_no_depende_de_facturas(self, db, team, hoy):
        from app import models
        from app.services import pausa

        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)
        assert pausa.servicio_pausado(db, team["team"].id) is True


# ---------------------------------------------------------------------------
# 3. Lo que se bloquea
# ---------------------------------------------------------------------------

def _app(Sesion, usuario, *routers):
    from fastapi import FastAPI

    from app.dependencies import get_current_user, get_db

    app = FastAPI()
    for r in routers:
        app.include_router(r)

    def _get_db():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: usuario
    return app


@pytest.fixture
def cuenta_twilio(db, team):
    from app import models

    cuenta = models.MetaAccount(
        team_id=team["team"].id, phone_number_id="573001112233",
        display_phone="+573001112233", is_active=True,
        twilio_from="whatsapp:+573001112233",
        status="active", provider="twilio",
    )
    db.add(cuenta)
    db.commit()
    return cuenta


@pytest.fixture
def conversacion(db, team):
    from app import crud

    return crud.get_or_create_conversation(
        db, team_id=team["team"].id, contact_wa_id="573009990000",
    )


@pytest.fixture
def cliente_asesor(Sesion, team):
    from fastapi.testclient import TestClient

    from app.routers import campaigns, mensajes

    with TestClient(
        _app(Sesion, team["asesor"], mensajes.router, campaigns.router)
    ) as c:
        yield c


@pytest.fixture
def cliente_dueño(Sesion, team):
    from fastapi.testclient import TestClient

    from app.routers import campaigns, mensajes

    with TestClient(
        _app(Sesion, team["dueño"], mensajes.router, campaigns.router)
    ) as c:
        yield c


class TestEnvioManualBloqueado:
    def test_texto(self, cliente_asesor, db, team, conversacion, cuenta_twilio):
        from app import models

        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)
        r = cliente_asesor.post(
            f"/mensajes/conversaciones/{conversacion.id}/enviar",
            json={"content": "hola"},
        )
        assert r.status_code == 402
        assert "pausados" in r.json()["detail"]
        # Nada quedó persistido como si se hubiera intentado.
        assert db.query(models.Message).count() == 0

    def test_adjunto(self, cliente_asesor, db, team, conversacion, cuenta_twilio):
        from app import models

        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)
        r = cliente_asesor.post(
            f"/mensajes/conversaciones/{conversacion.id}/adjunto/preparar",
            json={"content_type": "image/jpeg", "filename": "a.jpg", "size": 100},
        )
        assert r.status_code == 402

    def test_plantilla_nueva_conversacion(self, cliente_asesor, db, team, cuenta_twilio):
        from app import models

        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)
        r = cliente_asesor.post(
            "/mensajes/conversaciones/nueva",
            json={"contact_wa_id": "573009990001", "template_name": "hola"},
        )
        assert r.status_code == 402

    def test_sin_pausa_no_se_bloquea(
        self, cliente_asesor, db, team, conversacion, cuenta_twilio, monkeypatch
    ):
        """El control: con `nunca` el mismo envío pasa del portero."""
        from app.routers import mensajes

        monkeypatch.setattr(
            mensajes.messaging, "send_text", lambda *a, **k: ("SM1", {})
        )
        r = cliente_asesor.post(
            f"/mensajes/conversaciones/{conversacion.id}/enviar",
            json={"content": "hola"},
        )
        assert r.status_code == 200


class TestSimuladorBloqueado:
    def test_no_gasta_bedrock(self, Sesion, db, team):
        """Cada turno de un bot LLM en el simulador es una llamada que paga Gloma."""
        from fastapi.testclient import TestClient

        from app import models
        from app.routers import bots

        bot = models.Bot(user_id=team["dueño"].id, team_id=team["team"].id, name="Bot")
        db.add(bot)
        db.commit()
        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)

        with TestClient(_app(Sesion, team["dueño"], bots.router)) as c:
            r = c.post(f"/bots/{bot.id}/simulate", json={"state": None, "user_input": None})
        assert r.status_code == 402


class TestConfirmarNoDejaHuerfanos:
    def test_el_temporal_se_borra_aunque_este_pausada(
        self, cliente_asesor, db, team, conversacion, cuenta_twilio, monkeypatch
    ):
        from app import models
        from app.routers import mensajes

        borrados = []
        monkeypatch.setattr(
            mensajes.adjuntos, "borrar_subida", lambda t, ref: borrados.append(ref)
        )
        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)

        r = cliente_asesor.post(
            f"/mensajes/conversaciones/{conversacion.id}/adjunto/confirmar",
            json={"referencia": "a" * 32, "content_type": "image/jpeg", "filename": "a.jpg"},
        )
        assert r.status_code == 402
        assert borrados == ["a" * 32]


class TestLoteNoRevienta:
    def test_un_error_evaluando_se_trata_como_pausada(self, db, team, monkeypatch):
        from app.services import pausa

        def _falla(*a, **k):
            raise RuntimeError("base caída")

        monkeypatch.setattr(pausa, "servicio_pausado", _falla)
        assert pausa.pausado_en_lote(db, team["team"].id) is True

    def test_vencimiento_absurdo_no_revienta(self):
        from app.services.pausa import sumar_un_mes

        assert sumar_un_mes(date(9999, 12, 15)) == date.max


class TestCampanasBloqueadas:
    def test_no_se_crea(self, cliente_dueño, db, team, cuenta_twilio):
        from app import models

        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)
        r = cliente_dueño.post(
            "/campaigns",
            json={
                "name": "Promo",
                "template_id": 1,
                "meta_account_id": cuenta_twilio.id,
                "recipients": {"mode": "individual", "contact_ids": [1]},
            },
        )
        assert r.status_code == 402
        assert db.query(models.Campaign).count() == 0

    def test_el_tick_no_manda_las_programadas(self, db, team, cuenta_twilio, monkeypatch):
        from app import models
        from app.services import campaign_sender

        plantilla = models.WhatsappTemplate(
            meta_account_id=cuenta_twilio.id, name="promo", language="es",
            category="MARKETING", status="APPROVED", components_json=[],
        )
        db.add(plantilla)
        db.commit()
        campana = models.Campaign(
            team_id=team["team"].id, meta_account_id=cuenta_twilio.id,
            template_id=plantilla.id, name="Promo", status="scheduled",
            scheduled_at=datetime.utcnow() - timedelta(minutes=5),
            created_by_user_id=team["dueño"].id,
        )
        db.add(campana)
        db.commit()
        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)

        resultado = campaign_sender.send_campaign_tick(db)

        assert resultado["campaigns_paused"] == 1
        assert resultado["campaigns_processed"] == 0
        db.refresh(campana)
        # Se queda como estaba: sale sola cuando la cuenta se reanude.
        assert campana.status == "scheduled"


class TestElBotNoResponde:
    def _form(self):
        return {
            "MessageSid": "SMpausa1",
            "From": "whatsapp:+573009990000",
            "To": "whatsapp:+573001112233",
            "Body": "Hola, ¿tienen cupo?",
            "NumMedia": "0",
        }

    def test_twilio_guarda_el_mensaje_pero_no_corre_el_bot(
        self, db, team, cuenta_twilio, monkeypatch
    ):
        from app import models
        from app.routers import twilio_webhook

        turnos = []
        monkeypatch.setattr(
            twilio_webhook.bot_router_svc,
            "resolve_bot_for_incoming_message",
            lambda *a, **k: (object(), None),
        )
        monkeypatch.setattr(
            twilio_webhook.bot_runner, "run_turn",
            lambda *a, **k: turnos.append(1),
        )
        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)

        twilio_webhook.process_twilio_inbound(db, self._form())

        assert turnos == []
        entrantes = db.query(models.Message).filter(
            models.Message.direction == "inbound"
        ).all()
        assert len(entrantes) == 1  # el mensaje del cliente NO se pierde

    def test_twilio_sin_pausa_si_corre_el_bot(
        self, db, team, cuenta_twilio, monkeypatch
    ):
        from app.routers import twilio_webhook

        turnos = []
        monkeypatch.setattr(
            twilio_webhook.bot_router_svc,
            "resolve_bot_for_incoming_message",
            lambda *a, **k: (type("B", (), {"id": 1})(), None),
        )
        monkeypatch.setattr(
            twilio_webhook.bot_runner, "run_turn",
            lambda *a, **k: turnos.append(1),
        )

        twilio_webhook.process_twilio_inbound(db, self._form())

        assert turnos == [1]

    def test_lo_agendado_no_sale(self, db, team, conversacion, monkeypatch):
        from app import models
        from app.services import bot_runner

        bot = models.Bot(
            user_id=team["dueño"].id, team_id=team["team"].id, name="Bot",
        )
        db.add(bot)
        db.commit()
        sesion = models.BotSession(
            bot_id=bot.id, conversation_id=conversacion.id,
        )
        db.add(sesion)
        db.commit()
        accion = models.BotPendingAction(
            session_id=sesion.id, scheduled_at=datetime.utcnow(),
        )
        db.add(accion)
        db.commit()
        enviados = []
        monkeypatch.setattr(bot_runner, "run_turn", lambda *a, **k: enviados.append(1))
        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)

        bot_runner.process_pending_action(db, accion)

        assert enviados == []
        db.refresh(accion)
        # Sale de la cola (si no, taparía las de las demás cuentas).
        assert accion.status == models.BOT_PENDING_STATUS_FAILED
        assert accion.last_error == "servicio pausado"


# ---------------------------------------------------------------------------
# 4. El aviso
# ---------------------------------------------------------------------------

class TestAviso:
    def test_el_asesor_ve_que_esta_pausada(self, asesor, db, team):
        from app import models

        poner_pausa(db, team["team"], models.PAUSA_PAUSADA)
        assert asesor.get("/pagos/aviso").json()["pausado"] is True

    def test_sin_pausa_dice_que_no(self, asesor, db, team, hoy):
        emitir(db, team["team"].id, vence=date(2026, 6, 2))
        assert asesor.get("/pagos/aviso").json()["pausado"] is False
