"""#644: correo automático de la promoción al iniciar la demo (SES mockeado)."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from app import models
from app.services import correo_promo
from tests.test_demo_api import (  # noqa: F401  (fixtures)
    CORREO, NOMBRE, Sesion, _demo_de, _iniciar, client, cuenta_demos, db, entorno,
    generacion_modelo,
)

_ENVS = ("DEMO_CORREO_PROMO_ACTIVO", "DEMO_CORREO_PROMO_DIAS", "DEMO_CORREO_PROMO_MAX_DIA",
         "DEMO_CORREO_PROMO_SOLO_A", "DEMO_CORREO_REMITENTE", "DEMO_CORREO_RESPONDER_A",
         "SES_REGION")


class SesFalso:
    def __init__(self, error: Exception | None = None):
        self.enviados: list[dict] = []
        self.error = error

    def __call__(self, destino, asunto, cuerpo_html, cuerpo_txt):
        if self.error:
            raise self.error
        self.enviados.append({"destino": destino, "asunto": asunto,
                              "html": cuerpo_html, "txt": cuerpo_txt})
        return f"0100019a-prueba-{len(self.enviados)}"


@pytest.fixture
def ses(monkeypatch):
    for var in _ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEMO_CORREO_PROMO_ACTIVO", "1")
    falso = SesFalso()
    monkeypatch.setattr(correo_promo, "_enviar_ses", falso)
    return falso


def _correo(n=None):
    return f"p{n if n is not None else uuid.uuid4().hex[:8]}@example.com"


def _nueva(client, **over):
    r = _iniciar(client, **over)
    assert r.status_code == 202, r.text
    return r.json()["demo_id"]


# ---------------------------------------------------------------------------
# Plantillas
# ---------------------------------------------------------------------------

def test_version_por_telefono():
    assert correo_promo.version_para("+573001234567") == "co"
    assert correo_promo.version_para("+525512345678") == "intl"
    assert correo_promo.version_para("+14155550100") == "intl"
    assert correo_promo.version_para(None) == "intl"


def test_plantillas_sin_placeholders_ni_datos_ajenos():
    for version in ("co", "intl"):
        asunto, cuerpo_html, cuerpo_txt = correo_promo.renderizar(version, "Ana María Ruiz", "Hotel X")
        assert "{{" not in asunto + cuerpo_html + cuerpo_txt
        assert asunto.startswith("Ana, tu promoción de Gloma")
        assert "Hotel X" in cuerpo_html and "Hotel X" in cuerpo_txt
    assert "COP" in correo_promo.renderizar("co", "Ana", "X")[0]
    assert "USD" in correo_promo.renderizar("intl", "Ana", "X")[0]


def test_escape_html_y_asunto_de_una_linea():
    asunto, cuerpo_html, cuerpo_txt = correo_promo.renderizar(
        "co", "<script>alert(1)</script>\r\nBcc: otro@example.com", 'Hotel "<b>Mal</b>"\nX-Hdr: 1')
    assert "\r" not in asunto and "\n" not in asunto
    assert "<script>" not in cuerpo_html and "&lt;script&gt;" in cuerpo_html
    assert "<b>Mal</b>" not in cuerpo_html and "&quot;&lt;b&gt;Mal&lt;/b&gt;&quot;" in cuerpo_html
    # En el texto, los valores van en una línea.
    assert "Hotel \"<b>Mal</b>\" X-Hdr: 1" in cuerpo_txt
    assert "\nX-Hdr" not in cuerpo_txt and "\nBcc" not in cuerpo_txt


def test_envio_ses_arma_el_mensaje(monkeypatch):
    import boto3

    for var in _ENVS:
        monkeypatch.delenv(var, raising=False)
    cliente = boto3.client("sesv2", region_name="us-east-1",
                           aws_access_key_id="x", aws_secret_access_key="x")
    monkeypatch.setattr(correo_promo, "_cliente_ses", lambda: cliente)
    asunto, cuerpo_html, cuerpo_txt = correo_promo.renderizar("co", "Ana", "Hotel")
    esperado = {
        "FromEmailAddress": "Gloma <contacto@glomacx.com>",
        "Destination": {"ToAddresses": ["ana@example.com"]},
        "ReplyToAddresses": ["contacto@glomacx.com"],
        "Content": {"Simple": {
            "Subject": {"Data": asunto, "Charset": "UTF-8"},
            "Body": {"Text": {"Data": cuerpo_txt, "Charset": "UTF-8"},
                     "Html": {"Data": cuerpo_html, "Charset": "UTF-8"}},
            "Headers": [{"Name": "List-Unsubscribe", "Value": correo_promo.LIST_UNSUBSCRIBE}],
        }},
    }
    with Stubber(cliente) as stub:
        stub.add_response("send_email", {"MessageId": "abc-123"}, esperado)
        assert correo_promo._enviar_ses("ana@example.com", asunto, cuerpo_html, cuerpo_txt) == "abc-123"
        stub.assert_no_pending_responses()


def test_region_por_defecto_us_east_1(monkeypatch):
    monkeypatch.delenv("SES_REGION", raising=False)
    assert correo_promo._cliente_ses().meta.region_name == "us-east-1"
    monkeypatch.setenv("SES_REGION", "eu-west-1")
    assert correo_promo._cliente_ses().meta.region_name == "eu-west-1"


# ---------------------------------------------------------------------------
# Disparo desde /demo/iniciar
# ---------------------------------------------------------------------------

def test_envia_la_version_co_y_registra(client, db, ses):
    demo_id = _nueva(client)
    assert len(ses.enviados) == 1
    e = ses.enviados[0]
    assert e["destino"] == CORREO and "COP" in e["asunto"]
    assert e["asunto"].startswith(NOMBRE.split()[0] + ",")
    demo = _demo_de(db, demo_id)
    assert demo.correo_promo_estado == "enviado"
    assert demo.correo_promo_enviado_at is not None
    assert demo.correo_promo_message_id == "0100019a-prueba-1"
    assert demo.estado == "lista"          # la generación corrió igual


def test_envia_la_version_intl_si_no_es_57(client, db, ses):
    _nueva(client, telefono="+52 55 1234 5678", correo=_correo())
    assert "USD" in ses.enviados[0]["asunto"]


def test_una_vez_por_correo_cada_30_dias(client, db, ses):
    primera = _nueva(client)
    segunda = _nueva(client)
    assert len(ses.enviados) == 1
    assert _demo_de(db, segunda).correo_promo_estado == "omitido"
    assert _demo_de(db, segunda).correo_promo_enviado_at is None
    # A los 31 días, otra vez.
    db.query(models.Demo).filter(models.Demo.public_id == uuid.UUID(primera)).update(
        {models.Demo.correo_promo_enviado_at: datetime.utcnow() - timedelta(days=31)},
        synchronize_session=False)
    db.commit()
    tercera = _nueva(client)
    assert len(ses.enviados) == 2 and _demo_de(db, tercera).correo_promo_estado == "enviado"


def test_ventana_configurable(client, db, ses, monkeypatch):
    monkeypatch.setenv("DEMO_CORREO_PROMO_DIAS", "1")
    primera = _nueva(client)
    db.query(models.Demo).filter(models.Demo.public_id == uuid.UUID(primera)).update(
        {models.Demo.correo_promo_enviado_at: datetime.utcnow() - timedelta(days=2)},
        synchronize_session=False)
    db.commit()
    _nueva(client)
    assert len(ses.enviados) == 2


def test_techo_diario(client, db, ses, monkeypatch):
    monkeypatch.setenv("DEMO_CORREO_PROMO_MAX_DIA", "2")
    ids = [_nueva(client, correo=_correo(), telefono=f"300 111 {i:04d}") for i in range(3)]
    assert len(ses.enviados) == 2
    assert [_demo_de(db, i).correo_promo_estado for i in ids] == ["enviado", "enviado", "omitido"]


def test_interruptor_apagado_no_envia(client, db, ses, monkeypatch):
    monkeypatch.delenv("DEMO_CORREO_PROMO_ACTIVO")
    demo_id = _nueva(client)
    assert ses.enviados == [] and _demo_de(db, demo_id).correo_promo_estado is None
    monkeypatch.setenv("DEMO_CORREO_PROMO_ACTIVO", "0")
    _nueva(client, correo=_correo())
    assert ses.enviados == []


def test_solo_a(client, db, ses, monkeypatch):
    monkeypatch.setenv("DEMO_CORREO_PROMO_SOLO_A", "Prueba@Example.com, otra@example.com")
    fuera = _nueva(client, correo=_correo())
    assert ses.enviados == [] and _demo_de(db, fuera).correo_promo_estado == "omitido"
    _nueva(client, correo="prueba@example.com", telefono="300 222 0001")
    assert [e["destino"] for e in ses.enviados] == ["prueba@example.com"]


@pytest.mark.parametrize("over", [{"sitio_web": "http://spam.example"}, {"form_ms": 500}])
def test_honeypot_no_envia(client, db, ses, over):
    r = _iniciar(client, **over)
    assert r.status_code == 202
    assert ses.enviados == [] and db.query(models.Demo).count() == 0


def test_tope_que_rechaza_no_envia(client, db, ses, monkeypatch):
    monkeypatch.setenv("DEMO_MAX_POR_CORREO_DIA", "1")
    _nueva(client)
    r = _iniciar(client)
    assert r.status_code == 429 and len(ses.enviados) == 1


def test_sin_demo_por_demanda_no_envia(client, db, ses, monkeypatch):
    monkeypatch.setenv("DEMO_MAX_GLOBAL_DIA", "0")
    r = _iniciar(client)
    assert r.status_code == 429
    assert ses.enviados == [] and db.query(models.Lead).count() == 1


def test_error_de_ses_no_rompe_iniciar(client, db, ses, caplog):
    ses.error = ClientError({"Error": {"Code": "MessageRejected",
                                       "Message": f"Email address is not verified: {CORREO}"}},
                            "SendEmail")
    caplog.set_level(logging.INFO)
    r = _iniciar(client)
    assert r.status_code == 202 and "token" in r.json()
    demo = _demo_de(db, r.json()["demo_id"])
    assert demo.correo_promo_estado == "error" and demo.correo_promo_enviado_at is None
    assert demo.estado == "lista"
    assert "MessageRejected" in caplog.text
    assert CORREO not in caplog.text and NOMBRE not in caplog.text
    # Un error no cuenta para los 30 días: la siguiente sí sale.
    ses.error = None
    _nueva(client)
    assert len(ses.enviados) == 1


def test_excepcion_cualquiera_no_rompe(client, db, ses):
    ses.error = TimeoutError("lento")
    r = _iniciar(client)
    assert r.status_code == 202
    assert _demo_de(db, r.json()["demo_id"]).correo_promo_estado == "error"


def test_idempotente_por_demo(client, db, ses, Sesion):
    demo_id = _nueva(client)
    interno = _demo_de(db, demo_id).id
    assert correo_promo.enviar_promo_de_demo(interno, nueva_sesion=Sesion) == "enviado"
    assert len(ses.enviados) == 1          # no reenvía


def test_logs_sin_pii(client, db, ses, caplog):
    caplog.set_level(logging.INFO)
    _nueva(client)
    lineas = [r.getMessage() for r in caplog.records if r.name == correo_promo.logger.name]
    assert lineas and all("estado=enviado" in l or "estado=" in l for l in lineas)
    texto = " ".join(lineas)
    assert CORREO not in texto and NOMBRE.split()[0] not in texto and "Brisas" not in texto


def test_panel_expone_el_estado(client, db, ses):
    from app.routers import admin_demos

    campos = admin_demos.DemoAdminDetalleOut.model_fields
    assert "correo_promo_enviado_at" in campos and "correo_promo_estado" in campos
    assert "correo_promo_message_id" not in campos
