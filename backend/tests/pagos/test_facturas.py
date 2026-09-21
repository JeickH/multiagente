"""Facturas: quién las ve, quién las paga, cuándo avisa y qué dice el PDF.

Lo que se prueba acá, en orden de qué duele más si se rompe:

1. **El asesor no entra.** Contra los endpoints, no contra la pantalla: que la
   interfaz no le pinte el listado no sirve de nada si el endpoint responde.
2. **El aviso no filtra plata.** El asesor SÍ puede llamar `/pagos/aviso` —
   tiene que ver el recuadro—, y ahí lo que importa es que la respuesta no
   traiga montos ni conteos por ningún lado.
3. **Los 7 días.** Que avise al séptimo y no al sexto.
4. **El PDF.** Que salga un PDF de verdad y que diga qué se está cobrando.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def emitir(db, team_id, *, concepto="Suscripción mensual Gloma",
           centavos=350_000 * 100, vence: date, estado=None):
    """Mete una factura directo en la base, sin pasar por la API."""
    from app import models
    from app.services import facturas as svc

    factura = svc.emitir(
        db, team_id,
        concepto=concepto,
        amount_cents=centavos,
        due_date=vence,
        issued_on=vence,
        detalle="Detalle de prueba",
    )
    if estado is not None:
        factura.status = estado
        if estado == models.INVOICE_PAGADA:
            factura.paid_at = datetime(2026, 9, 2, 15, 0)
    db.commit()
    return factura


@pytest.fixture
def hoy(monkeypatch):
    """Congela "hoy" en el servicio. Sin esto los tests de mora caducan solos.

    Se parchea `hoy_colombia` y no `datetime.now`: lo que hay que fijar es la
    respuesta a "qué día es en Colombia", que es la pregunta que hace el
    código. Parchear el reloj entero arrastraría también a `paid_at` y a los
    `created_at`, que no tienen nada que ver con esto.
    """
    from app.services import facturas as svc

    estado = {"dia": date(2026, 9, 20)}
    monkeypatch.setattr(svc, "hoy_colombia", lambda: estado["dia"])
    return estado


# ---------------------------------------------------------------------------
# 1. El portero
# ---------------------------------------------------------------------------

class TestElAsesorNoVeLasFacturas:
    """La autorización es del BACKEND. Ocultar la tabla por CSS no es un permiso."""

    def test_no_puede_listar(self, asesor, db, team):
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        assert asesor.get("/pagos/facturas").status_code == 403

    def test_no_puede_pagar(self, asesor, db, team):
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        respuesta = asesor.post(f"/pagos/facturas/{factura.id}/checkout", json={})
        assert respuesta.status_code == 403

    def test_no_puede_bajar_el_pdf(self, asesor, db, team):
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        assert asesor.get(f"/pagos/facturas/{factura.id}/pdf").status_code == 403

    def test_el_403_no_le_explica_que_le_falta(self, asesor):
        """Regla 6: el motivo va al log del servidor, no al cliente."""
        detalle = asesor.get("/pagos/facturas").json()["detail"].lower()
        for pista in ("can_manage_billing", "owner", "rol", "permiso"):
            assert pista not in detalle

    def test_el_403_llega_antes_de_mirar_la_factura(self, asesor):
        """Una factura inexistente le da 403, no 404.

        Si el portero corriera DESPUÉS de buscar la factura, el asesor podría
        distinguir un id que existe de uno que no por el código de respuesta, y
        contar las facturas de la cuenta sin ver ninguna.
        """
        assert asesor.get("/pagos/facturas/99999/pdf").status_code == 403


class TestElAdministradorSiEntra:
    def test_lista_sus_facturas(self, admin, db, team):
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        cuerpo = admin.get("/pagos/facturas").json()
        assert len(cuerpo["facturas"]) == 1
        assert cuerpo["facturas"][0]["concepto"] == "Suscripción mensual Gloma"

    def test_el_permiso_abre_la_caja_sin_volver_dueño(self, db, team, asesor):
        """`can_manage_billing` sobre un rol `agent`, igual que en el resto del módulo."""
        from app import models

        permiso = (
            db.query(models.TeamPermission)
            .filter(
                models.TeamPermission.team_member_id == team["membresia_asesor"].id,
                models.TeamPermission.permission_key == "can_manage_billing",
            )
            .first()
        )
        permiso.enabled = True
        db.commit()
        assert asesor.get("/pagos/facturas").status_code == 200


class TestAislamientoEntreCuentas:
    def test_la_factura_de_otra_cuenta_da_404(self, admin, db, team):
        """404 y no 403: un 403 confirmaría que el id existe en otra cuenta."""
        from app import models

        otro_dueño = models.User(
            nombre="Otra dueña", tipo_documento="CC", documento="2000001",
            correo="otra@ejemplo.com", hashed_password="x",
        )
        db.add(otro_dueño)
        db.commit()
        otro_team = models.Team(nombre="Otra cuenta", owner_user_id=otro_dueño.id)
        db.add(otro_team)
        db.commit()

        ajena = emitir(db, otro_team.id, vence=date(2026, 9, 2))

        assert admin.get(f"/pagos/facturas/{ajena.id}/pdf").status_code == 404
        assert admin.post(
            f"/pagos/facturas/{ajena.id}/checkout", json={}
        ).status_code == 404
        # Y no se coló en el listado del otro team.
        assert admin.get("/pagos/facturas").json()["facturas"] == []


# ---------------------------------------------------------------------------
# 2. El aviso: lo ve el asesor, y no le dice cuánto
# ---------------------------------------------------------------------------

class TestElAvisoNoFiltraFinanzas:
    def test_el_asesor_puede_consultarlo(self, asesor, db, team, hoy):
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        respuesta = asesor.get("/pagos/aviso")
        assert respuesta.status_code == 200
        assert respuesta.json()["mostrar"] is True

    def test_la_respuesta_solo_trae_un_si_y_una_clave(self, asesor, db, team, hoy):
        """El contrato completo: `mostrar` y `clave`. Nada más entra acá."""
        emitir(db, team["team"].id, centavos=1_000_000 * 100, vence=date(2026, 9, 2))
        cuerpo = asesor.get("/pagos/aviso").json()
        assert set(cuerpo.keys()) == {"mostrar", "clave"}

    def test_ni_el_monto_ni_el_conteo_aparecen_en_el_cuerpo(
        self, asesor, db, team, hoy
    ):
        """Se revisa el texto crudo: un campo nuevo "para depurar" cae acá."""
        emitir(db, team["team"].id, centavos=1_000_000 * 100, vence=date(2026, 9, 2))
        emitir(
            db, team["team"].id, concepto="Implementación",
            centavos=350_000 * 100, vence=date(2026, 9, 2),
        )
        crudo = asesor.get("/pagos/aviso").text
        for valor in ("1000000", "100000000", "350000", "35000000", "$"):
            assert valor not in crudo
        # Ni el número de facturas pendientes, que también es información.
        assert '"2"' not in crudo and ": 2" not in crudo

    def test_la_clave_no_deja_reconstruir_la_deuda(self, asesor, db, team, hoy):
        """Es un hash truncado: no debe parecerse a un id ni a un monto."""
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        clave = asesor.get("/pagos/aviso").json()["clave"]
        assert clave and len(clave) == 12
        assert str(factura.id) != clave
        assert str(factura.amount_cents) not in clave

    def test_sin_facturas_no_hay_aviso_ni_clave(self, asesor, hoy):
        assert asesor.get("/pagos/aviso").json() == {"mostrar": False, "clave": None}


class TestLaClaveDelAvisoCambiaConLaDeuda:
    """La X oculta el aviso; una deuda nueva lo trae de vuelta."""

    def test_la_misma_deuda_da_la_misma_clave(self, admin, db, team, hoy):
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        primera = admin.get("/pagos/aviso").json()["clave"]
        assert primera == admin.get("/pagos/aviso").json()["clave"]

    def test_una_factura_mas_cambia_la_clave(self, admin, db, team, hoy):
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        antes = admin.get("/pagos/aviso").json()["clave"]
        emitir(db, team["team"].id, concepto="Implementación", vence=date(2026, 9, 1))
        assert admin.get("/pagos/aviso").json()["clave"] != antes


# ---------------------------------------------------------------------------
# 3. Los 7 días
# ---------------------------------------------------------------------------

class TestElUmbralDeSieteDias:
    """Se cuenta desde el VENCIMIENTO, en fechas de Colombia."""

    @pytest.mark.parametrize(
        "dias_desde_el_vencimiento, esperado",
        [
            (0, False),   # vence hoy: se puede pagar hoy, no hay mora
            (3, False),
            (6, False),   # el día antes del umbral
            (7, True),    # el séptimo día
            (30, True),
        ],
    )
    def test_avisa_al_septimo_dia(
        self, admin, db, team, hoy, dias_desde_el_vencimiento, esperado
    ):
        vence = hoy["dia"] - timedelta(days=dias_desde_el_vencimiento)
        emitir(db, team["team"].id, vence=vence)
        assert admin.get("/pagos/aviso").json()["mostrar"] is esperado

    def test_una_factura_pagada_no_avisa_por_vieja_que_sea(
        self, admin, db, team, hoy
    ):
        from app import models

        emitir(
            db, team["team"].id,
            vence=date(2026, 1, 1), estado=models.INVOICE_PAGADA,
        )
        assert admin.get("/pagos/aviso").json()["mostrar"] is False

    def test_una_anulada_tampoco(self, admin, db, team, hoy):
        from app import models

        emitir(
            db, team["team"].id,
            vence=date(2026, 1, 1), estado=models.INVOICE_ANULADA,
        )
        assert admin.get("/pagos/aviso").json()["mostrar"] is False

    def test_basta_una_vencida_entre_varias_al_dia(self, admin, db, team, hoy):
        emitir(db, team["team"].id, vence=hoy["dia"] + timedelta(days=10))
        emitir(
            db, team["team"].id, concepto="Implementación",
            vence=hoy["dia"] - timedelta(days=8),
        )
        assert admin.get("/pagos/aviso").json()["mostrar"] is True

    def test_el_corte_se_calcula_en_fechas_de_colombia(self):
        """`hoy_colombia()` no es `utcnow().date()`.

        A las 2 a. m. UTC en Colombia son las 9 p. m. del día anterior. Si el
        corte se calculara en UTC, el aviso aparecería una noche antes de
        tiempo — y con el umbral en 7 días eso es un día de diferencia visible
        para el cliente.
        """
        from datetime import timezone

        from app.services import facturas as svc

        ahora_utc = datetime.now(timezone.utc)
        hoy_co = svc.hoy_colombia()
        assert (ahora_utc.date() - hoy_co).days in (0, 1)


# ---------------------------------------------------------------------------
# 4. El listado
# ---------------------------------------------------------------------------

class TestElListado:
    def test_dice_vencimiento_o_fecha_de_pago_segun_el_estado(
        self, admin, db, team, hoy
    ):
        from app import models

        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        emitir(
            db, team["team"].id, concepto="Implementación",
            vence=date(2026, 8, 2), estado=models.INVOICE_PAGADA,
        )
        facturas = {f["concepto"]: f for f in admin.get("/pagos/facturas").json()["facturas"]}

        pendiente = facturas["Suscripción mensual Gloma"]
        assert pendiente["due_date"] == "2026-09-02"
        assert pendiente["paid_at"] is None

        pagada = facturas["Implementación"]
        assert pagada["paid_at"] is not None

    def test_las_pendientes_van_primero(self, admin, db, team, hoy):
        from app import models

        emitir(
            db, team["team"].id, concepto="Vieja pagada",
            vence=date(2026, 12, 1), estado=models.INVOICE_PAGADA,
        )
        emitir(db, team["team"].id, concepto="Pendiente", vence=date(2026, 9, 2))
        conceptos = [f["concepto"] for f in admin.get("/pagos/facturas").json()["facturas"]]
        assert conceptos[0] == "Pendiente"

    def test_los_dias_de_mora_los_calcula_el_servidor(self, admin, db, team, hoy):
        emitir(db, team["team"].id, vence=hoy["dia"] - timedelta(days=18))
        assert admin.get("/pagos/facturas").json()["facturas"][0]["dias_de_mora"] == 18

    def test_el_total_pendiente_excluye_lo_pagado(self, admin, db, team, hoy):
        from app import models

        emitir(db, team["team"].id, centavos=1_000_000 * 100, vence=date(2026, 9, 2))
        emitir(db, team["team"].id, concepto="Mes", centavos=350_000 * 100,
               vence=date(2026, 9, 2))
        emitir(db, team["team"].id, concepto="Ya pagada", centavos=999 * 100,
               vence=date(2026, 8, 2), estado=models.INVOICE_PAGADA)
        cuerpo = admin.get("/pagos/facturas").json()
        assert cuerpo["total_pendiente_cents"] == 1_350_000 * 100

    def test_sin_suscripcion_no_anuncia_proxima_factura(self, admin):
        assert admin.get("/pagos/facturas").json()["proxima"] is None

    def test_la_proxima_sale_de_la_suscripcion(self, admin, db, team):
        """Sin columna nueva: `next_charge_at` + `amount_cents` ya lo sabían."""
        from app import models

        db.add(
            models.Subscription(
                team_id=team["team"].id,
                plan_key="plan_mensual",
                status=models.SUBSCRIPTION_PENDING,
                amount_cents=350_000 * 100,
                billing_day=2,
                # 2-oct-2026 9:00 en Colombia = 14:00 UTC.
                next_charge_at=datetime(2026, 10, 2, 14, 0),
            )
        )
        db.commit()

        proxima = admin.get("/pagos/facturas").json()["proxima"]
        assert proxima["fecha"] == "2026-10-02"
        assert proxima["amount_cop"] == 350_000

    def test_una_suscripcion_cancelada_no_anuncia_nada(self, admin, db, team):
        from app import models

        db.add(
            models.Subscription(
                team_id=team["team"].id,
                plan_key="plan_mensual",
                status=models.SUBSCRIPTION_CANCELED,
                amount_cents=350_000 * 100,
                next_charge_at=datetime(2026, 10, 2, 14, 0),
            )
        )
        db.commit()
        assert admin.get("/pagos/facturas").json()["proxima"] is None

    def test_no_salen_secretos_en_el_listado(self, admin, db, team, hoy):
        """Regla 2, revisada sobre el texto crudo de la respuesta."""
        emitir(db, team["team"].id, vence=date(2026, 9, 2))
        crudo = admin.get("/pagos/facturas").text.lower()
        for prohibido in (
            "hashed_password", "payment_source", "customer_email",
            "card_last_four", "app_secret", "private_key",
        ):
            assert prohibido not in crudo


# ---------------------------------------------------------------------------
# 5. Pagar
# ---------------------------------------------------------------------------

class TestPagarUnaFactura:
    def test_el_monto_sale_de_la_factura_y_no_del_request(self, admin, db, team):
        """Mandar un monto en el cuerpo no lo cambia: el precio lo pone el servidor."""
        factura = emitir(db, team["team"].id, centavos=1_000_000 * 100,
                         vence=date(2026, 9, 2))
        respuesta = admin.post(
            f"/pagos/facturas/{factura.id}/checkout",
            json={"package_key": "x", "redirect_url": "/pagos", "amount_cents": 100},
        )
        assert respuesta.status_code == 201
        assert respuesta.json()["amount_cents"] == 1_000_000 * 100

    def test_el_checkout_no_da_la_factura_por_pagada(self, admin, db, team):
        """Quien controla la URL de retorno se pagaría sus propias facturas."""
        from app import models

        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        admin.post(f"/pagos/facturas/{factura.id}/checkout", json={})
        db.refresh(factura)
        assert factura.status == models.INVOICE_PENDIENTE
        assert factura.paid_at is None

    def test_una_factura_pagada_no_se_vuelve_a_cobrar(self, admin, db, team):
        from app import models

        factura = emitir(
            db, team["team"].id, vence=date(2026, 9, 2), estado=models.INVOICE_PAGADA
        )
        respuesta = admin.post(f"/pagos/facturas/{factura.id}/checkout", json={})
        assert respuesta.status_code == 409

    def test_cada_intento_estrena_referencia(self, admin, db, team):
        """Wompi no acepta dos transacciones con la misma referencia."""
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        primera = admin.post(f"/pagos/facturas/{factura.id}/checkout", json={}).json()
        segunda = admin.post(f"/pagos/facturas/{factura.id}/checkout", json={}).json()
        assert primera["reference"] != segunda["reference"]
        db.refresh(factura)
        assert factura.intentos == 2

    def test_la_referencia_no_deja_adivinar_la_de_otra_cuenta(self, admin, db, team):
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        referencia = admin.post(
            f"/pagos/facturas/{factura.id}/checkout", json={}
        ).json()["reference"]
        assert referencia.startswith(f"glomafact-{team['team'].id}-{factura.id}-")
        # El sufijo aleatorio: sin él la referencia sería enteramente adivinable.
        assert len(referencia.rsplit("-", 1)[1]) == 8

    def test_el_redirect_no_se_va_a_otro_dominio(self, admin, db, team):
        """El mismo guardarraíl del checkout de paquetes, sobre el otro endpoint."""
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        respuesta = admin.post(
            f"/pagos/facturas/{factura.id}/checkout",
            json={"package_key": "x", "redirect_url": "https://evil.example/cobrar"},
        )
        campos = respuesta.json()["checkout"]["fields"]
        destino = campos.get("redirect-url", "")
        assert "evil.example" not in destino
        assert destino.startswith("https://app.glomabeauty.com")


class TestElWebhookEsQuienPaga:
    def test_un_evento_aprobado_marca_la_factura(self, admin, anonimo, db, team):
        from app import models

        from .conftest import evento_wompi

        factura = emitir(db, team["team"].id, centavos=350_000 * 100,
                         vence=date(2026, 9, 2))
        referencia = admin.post(
            f"/pagos/facturas/{factura.id}/checkout", json={}
        ).json()["reference"]

        respuesta = anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(referencia, monto_centavos=350_000 * 100),
        )
        assert respuesta.status_code == 200
        db.refresh(factura)
        assert factura.status == models.INVOICE_PAGADA
        assert factura.paid_at is not None

    def test_el_evento_repetido_no_hace_nada_nuevo(self, admin, anonimo, db, team):
        """Wompi reintenta hasta 3 veces en 24 h: el repetido es lo normal."""
        from .conftest import evento_wompi

        factura = emitir(db, team["team"].id, centavos=350_000 * 100,
                         vence=date(2026, 9, 2))
        referencia = admin.post(
            f"/pagos/facturas/{factura.id}/checkout", json={}
        ).json()["reference"]
        evento = evento_wompi(referencia, monto_centavos=350_000 * 100)

        anonimo.post("/pagos/wompi/webhook", json=evento)
        db.refresh(factura)
        pagada_en = factura.paid_at

        segunda = anonimo.post("/pagos/wompi/webhook", json=evento)
        assert segunda.json().get("ya_acreditada") is True
        db.refresh(factura)
        assert factura.paid_at == pagada_en

    def test_un_evento_sin_firma_no_paga_nada(self, admin, anonimo, db, team):
        from app import models

        from .conftest import evento_wompi

        factura = emitir(db, team["team"].id, centavos=350_000 * 100,
                         vence=date(2026, 9, 2))
        referencia = admin.post(
            f"/pagos/facturas/{factura.id}/checkout", json={}
        ).json()["reference"]

        respuesta = anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(referencia, monto_centavos=350_000 * 100, secreto=None),
        )
        assert respuesta.status_code == 403
        db.refresh(factura)
        assert factura.status == models.INVOICE_PENDIENTE

    def test_un_monto_distinto_no_paga_la_factura(self, admin, anonimo, db, team):
        """Pagar $1.000 no salda una factura de $350.000."""
        from app import models

        from .conftest import evento_wompi

        factura = emitir(db, team["team"].id, centavos=350_000 * 100,
                         vence=date(2026, 9, 2))
        referencia = admin.post(
            f"/pagos/facturas/{factura.id}/checkout", json={}
        ).json()["reference"]

        anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(referencia, monto_centavos=1_000 * 100),
        )
        db.refresh(factura)
        assert factura.status == models.INVOICE_PENDIENTE

    def test_un_rechazo_deja_la_factura_pendiente(self, admin, anonimo, db, team):
        """Lo que falló fue el intento de pago, no la deuda."""
        from app import models

        from .conftest import evento_wompi

        factura = emitir(db, team["team"].id, centavos=350_000 * 100,
                         vence=date(2026, 9, 2))
        referencia = admin.post(
            f"/pagos/facturas/{factura.id}/checkout", json={}
        ).json()["reference"]

        anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(
                referencia, estado="DECLINED", monto_centavos=350_000 * 100
            ),
        )
        db.refresh(factura)
        assert factura.status == models.INVOICE_PENDIENTE

    def test_pagar_apaga_el_aviso(self, admin, anonimo, db, team, hoy):
        from .conftest import evento_wompi

        factura = emitir(
            db, team["team"].id, centavos=350_000 * 100,
            vence=hoy["dia"] - timedelta(days=18),
        )
        assert admin.get("/pagos/aviso").json()["mostrar"] is True

        referencia = admin.post(
            f"/pagos/facturas/{factura.id}/checkout", json={}
        ).json()["reference"]
        anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(referencia, monto_centavos=350_000 * 100),
        )
        assert admin.get("/pagos/aviso").json()["mostrar"] is False


# ---------------------------------------------------------------------------
# 6. El PDF
# ---------------------------------------------------------------------------

class TestElPdf:
    def test_devuelve_un_pdf_de_verdad(self, admin, db, team):
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        respuesta = admin.get(f"/pagos/facturas/{factura.id}/pdf")
        assert respuesta.status_code == 200
        assert respuesta.headers["content-type"].startswith("application/pdf")
        assert respuesta.content.startswith(b"%PDF-1.")
        assert respuesta.content.rstrip().endswith(b"%%EOF")

    def test_la_tabla_xref_apunta_a_donde_debe(self, admin, db, team):
        """Lo único delicado del formato: si las posiciones no cuadran, los
        lectores estrictos rechazan el archivo aunque el texto esté bien."""
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        crudo = admin.get(f"/pagos/facturas/{factura.id}/pdf").content

        inicio = int(crudo.rsplit(b"startxref", 1)[1].split(b"%%EOF")[0].strip())
        assert crudo[inicio:inicio + 4] == b"xref"

        entradas = crudo[inicio:].split(b"\n")[2:]
        for entrada in entradas:
            if not entrada.endswith(b" n ") and not entrada.endswith(b" n"):
                break
            posicion = int(entrada.split()[0])
            assert b" obj" in crudo[posicion:posicion + 20]

    def test_dice_que_se_esta_cobrando(self, admin, db, team):
        """El requisito del CEO: la factura especifica QUÉ se cobra."""
        factura = emitir(
            db, team["team"].id,
            concepto="Implementación de la plataforma",
            centavos=1_000_000 * 100, vence=date(2026, 9, 2),
        )
        crudo = admin.get(f"/pagos/facturas/{factura.id}/pdf").content
        # El texto va en latin-1 dentro del contenido del PDF.
        assert "Implementación de la plataforma".encode("latin-1") in crudo
        assert b"$ 1.000.000" in crudo
        assert factura.numero.encode("latin-1") in crudo

    def test_una_pendiente_muestra_el_vencimiento(self, admin, db, team):
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        crudo = admin.get(f"/pagos/facturas/{factura.id}/pdf").content
        assert "SE VENCE EL".encode("latin-1") in crudo
        assert "2 de septiembre de 2026".encode("latin-1") in crudo

    def test_una_pagada_muestra_la_fecha_de_pago(self, admin, db, team):
        from app import models

        factura = emitir(
            db, team["team"].id, vence=date(2026, 8, 2), estado=models.INVOICE_PAGADA
        )
        crudo = admin.get(f"/pagos/facturas/{factura.id}/pdf").content
        assert "FECHA DE PAGO".encode("latin-1") in crudo
        assert "SE VENCE EL".encode("latin-1") not in crudo

    def test_un_parentesis_en_el_concepto_no_rompe_el_archivo(self, admin, db, team):
        """Sin escapar, un `)` cierra la cadena y el PDF queda ilegible."""
        factura = emitir(
            db, team["team"].id,
            concepto="Implementación (fase 1) \\ ajuste", vence=date(2026, 9, 2),
        )
        crudo = admin.get(f"/pagos/facturas/{factura.id}/pdf").content
        assert crudo.startswith(b"%PDF-1.")
        assert rb"\(fase 1\)" in crudo

    def test_no_se_cachea(self, admin, db, team):
        """Trae el estado impreso: cacheado, reaparece "Pendiente" tras pagarla."""
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        respuesta = admin.get(f"/pagos/facturas/{factura.id}/pdf")
        assert respuesta.headers.get("cache-control") == "no-store"

    def test_el_nombre_del_archivo_no_lleva_datos_del_cliente(self, admin, db, team):
        factura = emitir(db, team["team"].id, vence=date(2026, 9, 2))
        disposicion = admin.get(
            f"/pagos/facturas/{factura.id}/pdf"
        ).headers["content-disposition"]
        assert disposicion == f'inline; filename="factura-{factura.numero}.pdf"'


class TestFormatoDePesos:
    @pytest.mark.parametrize(
        "centavos, esperado",
        [
            (350_000 * 100, "$ 350.000"),
            (1_000_000 * 100, "$ 1.000.000"),
            (999 * 100, "$ 999"),
        ],
    )
    def test_separador_de_miles_con_punto(self, centavos, esperado):
        from app.services import facturas as svc

        assert svc.pesos(centavos) == esperado


# ---------------------------------------------------------------------------
# 7. La numeración
# ---------------------------------------------------------------------------

class TestNumeracion:
    def test_es_consecutiva_por_cuenta(self, db, team):
        from app.services import facturas as svc

        primera = svc.emitir(
            db, team["team"].id, concepto="Una", amount_cents=1000,
            due_date=date(2026, 9, 2),
        )
        db.commit()
        segunda = svc.emitir(
            db, team["team"].id, concepto="Otra", amount_cents=1000,
            due_date=date(2026, 9, 2),
        )
        db.commit()
        assert primera.numero == "FAC-2026-0001"
        assert segunda.numero == "FAC-2026-0002"

    def test_cada_cuenta_arranca_en_uno(self, db, team):
        """Así el cliente no deduce cuántos clientes tiene la plataforma."""
        from app import models
        from app.services import facturas as svc

        otro_dueño = models.User(
            nombre="Otra dueña", tipo_documento="CC", documento="3000001",
            correo="tercera@ejemplo.com", hashed_password="x",
        )
        db.add(otro_dueño)
        db.commit()
        otro = models.Team(nombre="Tercera cuenta", owner_user_id=otro_dueño.id)
        db.add(otro)
        db.commit()

        svc.emitir(db, team["team"].id, concepto="Una", amount_cents=1000,
                   due_date=date(2026, 9, 2))
        db.commit()
        suya = svc.emitir(db, otro.id, concepto="Una", amount_cents=1000,
                          due_date=date(2026, 9, 2))
        db.commit()
        assert suya.numero == "FAC-2026-0001"
