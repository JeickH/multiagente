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
         "DEMO_CORREO_PROMO_MAX_HORA", "DEMO_CORREO_PROMO_MAX_ERRORES",
         "DEMO_CORREO_PROMO_REARMADO_EN", "DEMO_CORREO_PROMO_SOLO_A", "DEMO_CORREO_REMITENTE",
         "DEMO_CORREO_RESPONDER_A", "DEMO_CORREO_CONFIG_SET", "SES_REGION")


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
    # Sin red en la suite: todo dominio tiene MX salvo que el test diga otra cosa.
    monkeypatch.setattr(correo_promo, "_consultar_mx", lambda dominio: ["mx.example.net"])
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
        "co", "Ana\r\nBcc: otro", 'Hotel "<script>" & Co\nX Hdr')
    assert "\r" not in asunto and "\n" not in asunto and "Bcc" not in asunto + cuerpo_txt
    assert "<script>" not in cuerpo_html
    assert "Hotel &quot;&lt;script&gt;&quot; &amp; Co X Hdr" in cuerpo_html
    assert 'Hotel "<script>" & Co X Hdr' in cuerpo_txt        # en una línea


# ---------------------------------------------------------------------------
# #647 A1: lista blanca del contenido
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre,esperado", [
    ("Ana María Ruiz", "Ana"), ("josé", "josé"), ("Ñusta", "Ñusta"),
    ("Jean-Luc", None), ("O'Brien", None), ("D’Angelo", None), ("Ana2", None),
    ("<b>", None), ("https://x.y", None), ("a@b.c", None), ("{{empresa}}", None),
    ("_ana", None), ("", None), ("A" * 31, None), ("A" * 30, "A" * 30),
])
def test_lista_blanca_del_nombre(nombre, esperado):
    assert correo_promo.nombre_para_correo(nombre) == esperado


@pytest.mark.parametrize("empresa", [
    "https://x.y", "bit.ly/a", "evil.ru", "a@b.c", "{{empresa}}", "Hotel {x}",
    "Agencia 3001234567", "Viajes 12345", "C:\\ruta", "Viajes S.A.S.",
])
def test_empresa_sospechosa_queda_generica(empresa):
    assert correo_promo.empresa_para_correo(empresa) == "tu empresa"


@pytest.mark.parametrize("empresa", ["Hotel Brisas del Carmen", "Viajes & Más", "Hostal 1234",
                                     "Ecoturismo O'Neill"])
def test_empresa_normal_pasa(empresa):
    assert correo_promo.empresa_para_correo(empresa) == empresa


@pytest.mark.parametrize("malo", ["https://x.y", "bit.ly/a", "evil.ru", "a@b.c", "{{empresa}}"])
@pytest.mark.parametrize("version", ["co", "intl"])
def test_inyeccion_no_llega_al_correo(malo, version):
    asunto, cuerpo_html, cuerpo_txt = correo_promo.renderizar(version, malo, malo)
    for parte in (asunto, cuerpo_html, cuerpo_txt):
        assert malo not in parte
        assert "{{" not in parte
    assert "x.y" not in cuerpo_html + cuerpo_txt and "bit.ly" not in cuerpo_html + cuerpo_txt
    assert "evil.ru" not in cuerpo_html + cuerpo_txt


def test_sin_nombre_el_correo_saluda_generico():
    asunto, cuerpo_html, cuerpo_txt = correo_promo.renderizar("co", "https://x.y", "Hotel X")
    assert asunto == "Tu promoción de Gloma: hasta $1.285.200 COP"
    assert cuerpo_txt.startswith("Hola, ganaste hasta $1.285.200 COP")
    assert "<title>Tu promoción de Gloma" in cuerpo_html and "Hola, ganaste hasta</h1>" in cuerpo_html
    asunto = correo_promo.renderizar("intl", None, None)[0]
    assert asunto == "Tu promoción de Gloma: hasta USD 402"


@pytest.mark.parametrize("version,montos", [
    ("co", ["$1.285.200 COP", "535.500 COP", "696.150 COP", "1.071.000 COP"]),
    ("intl", ["USD 402", "USD 167,50", "USD 217,75", "USD 335"]),
])
def test_promocion_del_plan_mensual(version, montos):
    """Promoción del 2026-10-28: 50 % en el mes 1 y 35 % en los meses 2 y 3,
    sumada a la prueba gratis de 14 días y a la instalación en 0. Nada de la
    promoción vieja (instalación pagada y paquetes que no se vencen)."""
    asunto, cuerpo_html, cuerpo_txt = correo_promo.renderizar(version, "Ana", "Hotel X")
    assert montos[0] in asunto
    for cuerpo in (cuerpo_html, cuerpo_txt):
        for monto in montos:
            assert monto in cuerpo
        assert "14 días de prueba gratis" in cuerpo
        assert "la instalación, que no te cuesta nada" in cuerpo
        for viejo in ("8.700.000", "2.700", "paquete", "no se vencen", "2.400.000", "USD 750"):
            assert viejo not in cuerpo
    assert "paquete" not in correo_promo._asuntos()[version]["preheader"]


def test_plantillas_sin_google_fonts():
    for version in ("co", "intl"):
        assert "googleapis" not in correo_promo._plantilla(version, "html")


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


def test_configuration_set_por_env(monkeypatch):
    import boto3

    for var in _ENVS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DEMO_CORREO_CONFIG_SET", "promo-demo")
    cliente = boto3.client("sesv2", region_name="us-east-1",
                           aws_access_key_id="x", aws_secret_access_key="x")
    monkeypatch.setattr(correo_promo, "_cliente_ses", lambda: cliente)
    vistos = []
    cliente.meta.events.register("provide-client-params.sesv2.SendEmail",
                                 lambda params, **_: vistos.append(dict(params)))
    with Stubber(cliente) as stub:
        stub.add_response("send_email", {"MessageId": "m"})
        correo_promo._enviar_ses("ana@example.com", "a", "<p>b</p>", "b")
    assert vistos[0]["ConfigurationSetName"] == "promo-demo"
    monkeypatch.setenv("DEMO_CORREO_CONFIG_SET", "")
    with Stubber(cliente) as stub:
        stub.add_response("send_email", {"MessageId": "m"})
        correo_promo._enviar_ses("ana@example.com", "a", "<p>b</p>", "b")
    assert "ConfigurationSetName" not in vistos[1]


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


# ---------------------------------------------------------------------------
# #647 M1: techo por hora, MX, desechables y cortacircuitos
# ---------------------------------------------------------------------------

def test_techo_por_hora(client, db, ses, monkeypatch):
    monkeypatch.setenv("DEMO_CORREO_PROMO_MAX_HORA", "1")
    ids = [_nueva(client, correo=_correo(), telefono=f"300 333 {i:04d}") for i in range(2)]
    assert [_demo_de(db, i).correo_promo_estado for i in ids] == ["enviado", "omitido"]
    db.query(models.Demo).filter(models.Demo.public_id == uuid.UUID(ids[0])).update(
        {models.Demo.correo_promo_enviado_at: datetime.utcnow() - timedelta(minutes=61)},
        synchronize_session=False)
    db.commit()
    tercera = _nueva(client, correo=_correo(), telefono="300 333 0009")
    assert _demo_de(db, tercera).correo_promo_estado == "enviado"


def test_dominio_sin_mx(client, db, ses, monkeypatch):
    import dns.resolver

    def _nx(dominio):
        raise dns.resolver.NXDOMAIN()
    monkeypatch.setattr(correo_promo, "_consultar_mx", _nx)
    demo_id = _nueva(client)
    assert ses.enviados == [] and _demo_de(db, demo_id).correo_promo_estado == "omitido"


def test_null_mx_es_sin_mx(monkeypatch):
    monkeypatch.setattr(correo_promo, "_consultar_mx", lambda d: [""])
    assert correo_promo.motivo_mx("a@example.com") == "sin_mx"
    import dns.resolver

    def _sin(dominio):
        raise dns.resolver.NoAnswer()
    monkeypatch.setattr(correo_promo, "_consultar_mx", _sin)
    assert correo_promo.motivo_mx("a@example.com") == "sin_mx"


@pytest.mark.parametrize("error", ["timeout", "nonameservers", "otro"])
def test_dns_que_falla_no_envia(client, db, ses, monkeypatch, caplog, error):
    import dns.exception
    import dns.resolver

    def _falla(dominio):
        if error == "timeout":
            raise dns.exception.Timeout()
        if error == "nonameservers":
            raise dns.resolver.NoNameservers()
        raise OSError("red")
    monkeypatch.setattr(correo_promo, "_consultar_mx", _falla)
    caplog.set_level(logging.INFO)
    demo_id = _nueva(client)
    assert ses.enviados == [] and _demo_de(db, demo_id).correo_promo_estado == "omitido"
    assert "motivo=dns" in caplog.text


def test_timeout_del_resolver_es_2_s(monkeypatch):
    import dns.resolver

    vistos = {}

    class _Resolver:
        def __init__(self):
            self.timeout = self.lifetime = None

        def resolve(self, dominio, tipo):
            vistos.update(timeout=self.timeout, lifetime=self.lifetime, tipo=tipo, dominio=dominio)
            raise dns.resolver.NXDOMAIN()
    monkeypatch.setattr(dns.resolver, "Resolver", _Resolver)
    assert correo_promo.motivo_mx("Ana@Ejemplo.CO") == "sin_mx"
    assert vistos == {"timeout": 2.0, "lifetime": 2.0, "tipo": "MX", "dominio": "ejemplo.co"}


@pytest.mark.parametrize("correo", ["x@mailinator.com", "x@sub.yopmail.com", "x@10minutemail.com"])
def test_desechables(client, db, ses, correo):
    assert correo_promo.es_desechable(correo)
    demo_id = _nueva(client, correo=correo)
    assert ses.enviados == [] and _demo_de(db, demo_id).correo_promo_estado == "omitido"


def test_no_desechable():
    assert not correo_promo.es_desechable("ana@gmail.com")
    assert not correo_promo.es_desechable("ana@notmailinator.com")


def _errores(db, n, desde, cada=timedelta(minutes=10)):
    for i in range(n):
        lead = models.Lead(email=f"e{uuid.uuid4().hex[:6]}@example.com", telefono="+573000000000",
                           source="gloma_demo", nombre="Prueba")
        db.add(lead)
        db.flush()
        db.add(models.Demo(empresa="X", tipo_empresa="hotel", acepta_contacto_at=desde,
                           consent_version="demo-2026-10c", lead_id=lead.id, estado="lista",
                           created_at=desde + i * cada, correo_promo_estado="error"))
    db.commit()


def test_cortacircuitos_se_abre_y_se_queda_abierto(client, db, ses, monkeypatch, caplog):
    _errores(db, 20, datetime.utcnow() - timedelta(days=3))          # ráfaga de hace 3 días
    caplog.set_level(logging.INFO)
    demo_id = _nueva(client)
    assert ses.enviados == [] and _demo_de(db, demo_id).correo_promo_estado == "omitido"
    assert "motivo=cortacircuitos" in caplog.text
    # Se rearma por env: solo cuentan los errores posteriores.
    monkeypatch.setenv("DEMO_CORREO_PROMO_REARMADO_EN",
                       (datetime.utcnow() - timedelta(hours=1)).isoformat(timespec="seconds"))
    _nueva(client, correo=_correo(), telefono="300 444 0001")
    assert len(ses.enviados) == 1


def test_19_errores_o_espaciados_no_abren(db, monkeypatch):
    ahora = datetime.utcnow()
    _errores(db, 19, ahora - timedelta(hours=5))
    assert not correo_promo.cortacircuitos_abierto(db, ahora)
    _errores(db, 19, ahora - timedelta(days=10), cada=timedelta(hours=2))   # 38 h de ventana
    assert not correo_promo.cortacircuitos_abierto(db, ahora)
    _errores(db, 1, ahora - timedelta(hours=1))
    assert correo_promo.cortacircuitos_abierto(db, ahora)
    monkeypatch.setenv("DEMO_CORREO_PROMO_MAX_ERRORES", "50")
    assert not correo_promo.cortacircuitos_abierto(db, ahora)


def test_rearmado_con_zona(monkeypatch):
    monkeypatch.setenv("DEMO_CORREO_PROMO_REARMADO_EN", "2026-10-22T10:00:00-05:00")
    assert correo_promo.rearmado_en() == datetime(2026, 10, 22, 15, 0)
    monkeypatch.setenv("DEMO_CORREO_PROMO_REARMADO_EN", "basura")
    assert correo_promo.rearmado_en() is None


# ---------------------------------------------------------------------------
# #647 M3: consentimiento
# ---------------------------------------------------------------------------

def test_version_de_consentimiento_actual_habilita_el_correo():
    from app.routers import demo as router_demo

    assert router_demo.CONSENT_VERSION == "demo-2026-10c"
    assert router_demo.CONSENT_VERSION in correo_promo.VERSIONES_CON_CORREO


@pytest.mark.parametrize("version", ["demo-2026-10b", "demo-2026-10a", "demo-2026-10d", "demo-2027", ""])
def test_sin_la_version_que_avisa_no_sale(client, db, ses, Sesion, version):
    demo_id = _nueva(client)
    interno = _demo_de(db, demo_id).id
    db.query(models.Demo).filter(models.Demo.id == interno).update(
        {models.Demo.consent_version: version, models.Demo.correo_promo_estado: None},
        synchronize_session=False)
    db.commit()
    antes = len(ses.enviados)
    assert correo_promo.enviar_promo_de_demo(interno, nueva_sesion=Sesion) == "omitido"
    assert len(ses.enviados) == antes


def test_script_de_baja(monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    import boto3

    cliente = boto3.client("sesv2", region_name="us-east-1",
                           aws_access_key_id="x", aws_secret_access_key="x")
    monkeypatch.setattr(boto3, "client", lambda *a, **k: cliente)
    ruta = Path(__file__).resolve().parent.parent / "scripts" / "baja_correo_promo.py"
    spec = importlib.util.spec_from_file_location("baja_correo_promo_test", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with Stubber(cliente) as stub:
        stub.add_response("put_suppressed_destination", {},
                          {"EmailAddress": "ana@example.com", "Reason": "COMPLAINT"})
        assert mod.main(["Ana@Example.com"]) == 0
    salida = capsys.readouterr().out
    assert "ok" in salida and "ana@example.com" not in salida.lower()
    with pytest.raises(SystemExit):
        mod.main(["sin-arroba"])


# ---------------------------------------------------------------------------
# #647: demo_bot._DOMINIO_RE con TLD genérico
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("texto", ["evil.ru", "bit.ly", "EVIL.RU", "agenciaxyz.com",
                                   "reservas.co", "viajes.travel", "promo.cc", "x.museum"])
def test_dominio_con_cualquier_tld(texto):
    from app.services import demo_bot

    assert demo_bot.tiene_contacto(texto)


@pytest.mark.parametrize("texto", ["Viajes S.A.S.", "Hotel Brisas.", "Turismo Ltda.",
                                   "Inversiones J.M. S.A.", "a las 9 a.m.", "Agencia & Cía. Ltda",
                                   "Hotel 4.5 estrellas", "Mundo Viajes S.A.S. Ltda.",
                                   "Desayuno incluido. Traslados también."])
def test_dominio_no_tumba_nombres_normales(texto):
    from app.services import demo_bot

    assert not demo_bot.tiene_contacto(texto)
