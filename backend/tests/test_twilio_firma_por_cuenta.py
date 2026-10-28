"""La firma de Twilio se valida con el token de la cuenta que manda el webhook.

Hasta ahora `_verify_signature` usaba siempre el `TWILIO_AUTH_TOKEN` global, que
es el de la cuenta de Arranquemos. Gloma tiene su propia cuenta de Twilio (ver
CLAUDE.md, convención #4) y Twilio firma cada webhook con el token de la cuenta
dueña del número: con el token global, todo lo que le llegara a Gloma salía 403.

Lo que se fija acá:
  * la cuenta global sigue validando con la env var, como siempre;
  * una cuenta propia valida con su token cifrado en `meta_accounts`;
  * un `AccountSid` que no es de nadie se rechaza, también en desarrollo;
  * la firma de una cuenta no sirve para el número de otra (aislamiento).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
from urllib.parse import urlencode

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.database import Base
from app.dependencies import get_db
from app.routers import twilio_webhook

BASE = "https://api.ejemplo.test"
SID_GLOBAL = "AC" + "1" * 32
TOKEN_GLOBAL = "token-global"
SID_GLOMA = "AC" + "2" * 32
TOKEN_GLOMA = "token-gloma"
SID_INTRUSO = "AC" + "3" * 32
TOKEN_INTRUSO = "token-intruso"
NUM_ARRANQUEMOS = "+573001110000"
NUM_GLOMA = "+573002220000"
NUM_INTRUSO = "+573003330000"


def _crypto():
    # Siempre el módulo vigente: otros tests borran `app.services.crypto` de
    # `sys.modules` y lo recargan, y el webhook lo importa en cada llamada. Una
    # referencia tomada al importar este archivo cifraría con una copia vieja.
    return importlib.import_module("app.services.crypto")


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("APP_ENCRYPTION_KEY_OLD", raising=False)
    _crypto()._get_fernet.cache_clear()
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", SID_GLOBAL)
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", TOKEN_GLOBAL)
    monkeypatch.setenv("TWILIO_WEBHOOK_BASE_URL", BASE)
    monkeypatch.setenv("APP_ENV", "production")
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        _crypto()._get_fernet.cache_clear()


def _cuenta(db, nombre, numero, sid=None, token=None, token_enc=None):
    user = models.User(
        nombre=nombre, correo=f"{nombre}@test.com", tipo_documento="CC",
        documento=nombre.upper(), hashed_password="x",
    )
    db.add(user)
    db.commit()
    team = models.Team(nombre=nombre, owner_user_id=user.id)
    db.add(team)
    db.commit()
    cuenta = models.MetaAccount(
        team_id=team.id, phone_number_id=numero.lstrip("+"), display_phone=numero,
        is_active=True, status="active", provider="twilio",
        twilio_from=f"whatsapp:{numero}",
        twilio_account_sid=sid,
        encrypted_twilio_auth_token=token_enc or (_crypto().encrypt_secret(token) if token else None),
    )
    db.add(cuenta)
    db.commit()
    return cuenta


@pytest.fixture
def cuentas(db):
    # Arranquemos: sin credenciales propias, usa la cuenta global.
    arranquemos = _cuenta(db, "arranquemos", NUM_ARRANQUEMOS)
    gloma = _cuenta(db, "gloma", NUM_GLOMA, SID_GLOMA, TOKEN_GLOMA)
    intruso = _cuenta(db, "intruso", NUM_INTRUSO, SID_INTRUSO, TOKEN_INTRUSO)
    return arranquemos, gloma, intruso


@pytest.fixture
def cliente(db, monkeypatch):
    # El bot no es lo que se prueba acá.
    monkeypatch.setattr(
        twilio_webhook.bot_router_svc,
        "resolve_bot_for_incoming_message",
        lambda *a, **k: (None, None),
    )
    app = FastAPI()
    app.include_router(twilio_webhook.router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _firma(token, path, form):
    payload = BASE + path + "".join(k + form[k] for k in sorted(form))
    return base64.b64encode(
        hmac.new(token.encode(), payload.encode(), hashlib.sha1).digest()
    ).decode()


def _entrante(account_sid, to, sid_msg="SM1"):
    return {
        "MessageSid": sid_msg,
        "AccountSid": account_sid,
        "From": "whatsapp:+573009998877",
        "To": f"whatsapp:{to}",
        "Body": "Hola",
        "NumMedia": "0",
    }


def _post(cliente, path, form, token):
    return cliente.post(
        path,
        content=urlencode(form),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": _firma(token, path, form),
        },
    )


def _entrantes_de(db, cuenta):
    return (
        db.query(models.Message)
        .join(models.Conversation, models.Message.conversation_id == models.Conversation.id)
        .filter(models.Conversation.team_id == cuenta.team_id)
        .all()
    )


class TestCadaCuentaFirmaConSuToken:
    def test_la_cuenta_global_sigue_validando_con_la_env_var(self, db, cuentas, cliente):
        arranquemos, _, _ = cuentas
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOBAL, NUM_ARRANQUEMOS), TOKEN_GLOBAL)
        assert r.status_code == 200
        assert len(_entrantes_de(db, arranquemos)) == 1

    def test_la_cuenta_propia_valida_con_su_token_cifrado(self, db, cuentas, cliente):
        _, gloma, _ = cuentas
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOMA, NUM_GLOMA), TOKEN_GLOMA)
        assert r.status_code == 200
        assert len(_entrantes_de(db, gloma)) == 1

    def test_la_cuenta_propia_firmada_con_el_token_global_se_rechaza(self, db, cuentas, cliente):
        _, gloma, _ = cuentas
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOMA, NUM_GLOMA), TOKEN_GLOBAL)
        assert r.status_code == 403
        assert _entrantes_de(db, gloma) == []

    def test_el_callback_de_estado_tambien_usa_el_token_de_la_cuenta(self, cuentas, cliente):
        form = {"MessageSid": "SM9", "AccountSid": SID_GLOMA, "MessageStatus": "delivered"}
        assert _post(cliente, "/twilio/status", form, TOKEN_GLOMA).status_code == 200
        assert _post(cliente, "/twilio/status", form, TOKEN_GLOBAL).status_code == 403


class TestCuentaDesconocida:
    def test_se_rechaza_en_produccion(self, cuentas, cliente):
        r = _post(cliente, "/twilio/webhook", _entrante("AC" + "9" * 32, NUM_GLOMA), "cualquiera")
        assert r.status_code == 403

    def test_se_rechaza_tambien_en_desarrollo(self, cuentas, cliente, monkeypatch):
        # El fail-open de desarrollo es para "no hay token configurado", no para
        # una cuenta que nadie registró.
        monkeypatch.setenv("APP_ENV", "development")
        monkeypatch.delenv("TWILIO_AUTH_TOKEN")
        r = _post(cliente, "/twilio/webhook", _entrante("AC" + "9" * 32, NUM_GLOMA), "cualquiera")
        assert r.status_code == 401


class TestAislamientoEntreTenants:
    def test_un_tenant_no_puede_firmar_mensajes_para_el_numero_de_otro(
        self, db, cuentas, cliente
    ):
        # El intruso tiene su propia cuenta y conoce su token: la firma es
        # válida, pero el número de destino es de Gloma.
        _, gloma, intruso = cuentas
        r = _post(cliente, "/twilio/webhook", _entrante(SID_INTRUSO, NUM_GLOMA), TOKEN_INTRUSO)
        assert r.status_code == 200  # 200 para que Twilio no reintente
        assert _entrantes_de(db, gloma) == []
        assert _entrantes_de(db, intruso) == []

    def test_tampoco_hacia_la_cuenta_global(self, db, cuentas, cliente):
        arranquemos, _, _ = cuentas
        r = _post(
            cliente, "/twilio/webhook", _entrante(SID_INTRUSO, NUM_ARRANQUEMOS), TOKEN_INTRUSO
        )
        assert r.status_code == 200
        assert _entrantes_de(db, arranquemos) == []

    def test_la_cuenta_global_no_puede_escribirle_al_numero_de_gloma(self, db, cuentas, cliente):
        _, gloma, _ = cuentas
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOBAL, NUM_GLOMA), TOKEN_GLOBAL)
        assert r.status_code == 200
        assert _entrantes_de(db, gloma) == []


class TestCompatibilidadConArranquemos:
    """Cómo están hoy las filas de producción: que nada de esto corte el inbound."""

    def test_sin_account_sid_en_el_form_entra_con_el_token_global(self, db, cuentas, cliente):
        arranquemos, _, _ = cuentas
        form = _entrante(SID_GLOBAL, NUM_ARRANQUEMOS)
        del form["AccountSid"]
        assert _post(cliente, "/twilio/webhook", form, TOKEN_GLOBAL).status_code == 200
        assert len(_entrantes_de(db, arranquemos)) == 1

    def test_fila_con_el_sid_global_y_su_token_cifrado(self, db, cliente):
        # Así está la fila 3 en RDS (verificado el 2026-10-28).
        cuenta = _cuenta(db, "arranquemos", NUM_ARRANQUEMOS, SID_GLOBAL, TOKEN_GLOBAL)
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOBAL, NUM_ARRANQUEMOS), TOKEN_GLOBAL)
        assert r.status_code == 200
        assert len(_entrantes_de(db, cuenta)) == 1

    def test_el_sid_global_con_salto_de_linea_en_la_env_var(self, db, cuentas, cliente, monkeypatch):
        arranquemos, _, _ = cuentas
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", SID_GLOBAL + "\n")
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOBAL, NUM_ARRANQUEMOS), TOKEN_GLOBAL)
        assert r.status_code == 200
        assert len(_entrantes_de(db, arranquemos)) == 1

    def test_fila_con_el_sid_de_otra_cuenta_se_descarta_y_avisa(self, db, cliente, caplog):
        # Si la fila quedara con el SID de una subcuenta mientras el número vive
        # en la cuenta global, el inbound se pierde: tiene que quedar el error
        # que vigila CloudWatch.
        cuenta = _cuenta(db, "arranquemos", NUM_ARRANQUEMOS, SID_GLOMA, TOKEN_GLOMA)
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOBAL, NUM_ARRANQUEMOS), TOKEN_GLOBAL)
        assert r.status_code == 200
        assert _entrantes_de(db, cuenta) == []
        assert any(
            rec.levelname == "ERROR" and "AISLAMIENTO" in rec.getMessage() for rec in caplog.records
        )


class TestTokensRaros:
    def test_si_el_token_no_se_puede_descifrar_se_rechaza(self, db, cliente):
        _cuenta(db, "gloma", NUM_GLOMA, SID_GLOMA, token_enc="no-es-un-ciphertext")
        r = _post(cliente, "/twilio/webhook", _entrante(SID_GLOMA, NUM_GLOMA), TOKEN_GLOMA)
        assert r.status_code == 403

    def test_un_account_sid_sin_forma_de_sid_se_rechaza(self, cuentas, cliente):
        r = _post(cliente, "/twilio/webhook", _entrante("x" * 5000, NUM_GLOMA), "cualquiera")
        assert r.status_code == 403


class TestAislamientoEnLosEstados:
    def _campana_de(self, db, cuenta):
        # SQLite no aplica las FK: la plantilla y el contacto pueden ser de mentira.
        camp = models.Campaign(
            team_id=cuenta.team_id, meta_account_id=cuenta.id, template_id=1,
            name="c", status="running",
        )
        db.add(camp)
        db.commit()
        rec = models.CampaignRecipient(
            campaign_id=camp.id, contact_id=1, phone_e164="+573009998877",
            status="sent", provider_message_id="SMG1",
        )
        db.add(rec)
        db.commit()
        return rec

    def test_un_tenant_no_puede_mover_los_estados_de_la_campana_de_otro(
        self, db, cuentas, cliente
    ):
        _, gloma, _ = cuentas
        rec = self._campana_de(db, gloma)
        form = {"MessageSid": "SMG1", "AccountSid": SID_INTRUSO, "MessageStatus": "read"}
        assert _post(cliente, "/twilio/status", form, TOKEN_INTRUSO).status_code == 200
        db.refresh(rec)
        assert rec.status == "sent"

    def test_la_cuenta_duena_si_los_mueve(self, db, cuentas, cliente):
        _, gloma, _ = cuentas
        rec = self._campana_de(db, gloma)
        form = {"MessageSid": "SMG1", "AccountSid": SID_GLOMA, "MessageStatus": "read"}
        assert _post(cliente, "/twilio/status", form, TOKEN_GLOMA).status_code == 200
        db.refresh(rec)
        assert rec.status == "read"
