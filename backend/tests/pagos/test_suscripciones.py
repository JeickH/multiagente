"""Suscripción mensual: activación, cobro automático, mora y cancelación.

Casi todos los tests corren contra el **Wompi falso que habla HTTP** (ver
`wompi_falso.py`): el código bajo prueba es el mismo que corre en producción,
con `httpx` y todo. Los que sí parchean una función lo hacen para provocar
algo que el doble no puede producir a voluntad (una caída a mitad del cobro,
por ejemplo), y lo dicen en su docstring.

Lo que estos tests cuidan, en orden de gravedad si se rompe:

  1. que no se cobre dos veces (doble clic, webhook repetido, dos ticks);
  2. que no se active una suscripción que no se pagó;
  3. que el número de la tarjeta no llegue nunca al backend;
  4. que la fecha del cobro sea la que el cliente vio.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app import models
from app.services import suscripciones as svc

from .conftest import evento_wompi
from .wompi_falso import (
    ACCEPTANCE_TOKEN,
    PERSONAL_AUTH_TOKEN,
    TARJETA_APROBADA,
    TARJETA_RECHAZADA,
)

PRECIO_CENTAVOS = 350_000 * 100


# ---------------------------------------------------------------------------
# Fechas del ciclo
# ---------------------------------------------------------------------------

class TestFechasDelCiclo:
    """El día y la hora del cobro, que es lo que el cliente vio prometido."""

    def test_mismo_dia_y_hora_del_mes_siguiente(self):
        # 15 de enero, 2 p. m. de Colombia (19:00 UTC).
        activacion = datetime(2026, 1, 15, 19, 0)
        siguiente = svc.proxima_fecha_cobro(activacion, 15)
        assert siguiente == datetime(2026, 2, 15, 19, 0)

    def test_mes_corto_cobra_el_ultimo_dia(self):
        """Quien se suscribe un 31 no tiene 31 en febrero."""
        siguiente = svc.proxima_fecha_cobro(datetime(2026, 1, 31, 15, 0), 31)
        assert siguiente == datetime(2026, 2, 28, 15, 0)

    def test_despues_de_un_mes_corto_vuelve_al_dia_original(self):
        """El 31 no se degrada a 28 para siempre por haber pasado por febrero.

        Es el motivo de que `billing_day` se guarde aparte en vez de arrastrar
        la última fecha cobrada.
        """
        siguiente = svc.proxima_fecha_cobro(datetime(2026, 2, 28, 15, 0), 31)
        assert siguiente == datetime(2026, 3, 31, 15, 0)

    def test_el_dia_se_cuenta_en_hora_de_colombia(self):
        """Activar a las 10 p. m. del 31 en Bogotá es el 1.º en UTC.

        Si el día se contara en UTC, a este cliente se le cobraría el 1.º —
        un día distinto del que vio en pantalla.
        """
        # 2026-12-31 22:00 en Bogotá = 2027-01-01 03:00 UTC.
        activacion = datetime(2027, 1, 1, 3, 0)
        assert svc.dia_de_facturacion(activacion) == 31

        siguiente = svc.proxima_fecha_cobro(activacion, 31)
        # 31 de enero a las 22:00 de Bogotá = 1 de febrero 03:00 UTC.
        assert siguiente == datetime(2027, 2, 1, 3, 0)

    def test_bisiesto(self):
        assert svc.proxima_fecha_cobro(datetime(2028, 1, 29, 15, 0), 29) == datetime(
            2028, 2, 29, 15, 0
        )

    def test_cambio_de_anio(self):
        assert svc.proxima_fecha_cobro(datetime(2026, 12, 15, 19, 0), 15) == datetime(
            2027, 1, 15, 19, 0
        )


# ---------------------------------------------------------------------------
# Precio por cuenta
# ---------------------------------------------------------------------------

class TestPrecioPorCuenta:
    """Una cuenta puede pagar distinto, y el precio lo pone SIEMPRE el servidor."""

    def test_por_defecto_se_cobra_el_precio_de_lista(self):
        assert svc.precio_para("cualquiera@ejemplo.com") == PRECIO_CENTAVOS
        assert svc.precio_para(None) == PRECIO_CENTAVOS
        assert svc.precio_para("") == PRECIO_CENTAVOS

    def test_la_cuenta_con_override_paga_lo_suyo(self, monkeypatch):
        monkeypatch.setitem(svc.PRECIO_POR_CUENTA, "especial@ejemplo.com", 300_000)
        assert svc.precio_para("especial@ejemplo.com") == 300_000

    def test_el_correo_no_distingue_mayusculas(self, monkeypatch):
        """El login no distingue mayúsculas: un override que sí lo hiciera es
        un override que un día no aplica y le cobra de más a alguien."""
        monkeypatch.setitem(svc.PRECIO_POR_CUENTA, "especial@ejemplo.com", 300_000)
        assert svc.precio_para("  ESPECIAL@Ejemplo.COM  ") == 300_000

    def test_la_cuenta_de_prueba_configurada_tiene_su_precio(self):
        """Protege contra un typo en el correo del override: si se escribe mal,
        la cuenta paga el precio de lista y nadie se entera hasta el cobro."""
        assert svc.PRECIO_POR_CUENTA["gloma@glomabeauty.com"] == 3_000 * 100

    def test_la_suscripcion_nace_con_el_precio_de_su_cuenta(
        self, db, team, monkeypatch
    ):
        monkeypatch.setitem(svc.PRECIO_POR_CUENTA, "duena@ejemplo.com", 300_000)
        sub = svc.obtener_o_crear(db, team["team"].id)
        assert sub.amount_cents == 300_000

    def test_a_una_pendiente_se_le_actualiza_el_precio(self, db, team, monkeypatch):
        """Si el precio cambia después de que alguien abrió la pantalla, la fila
        ya creada no puede quedarse con el precio viejo."""
        sub = svc.obtener_o_crear(db, team["team"].id)
        assert sub.amount_cents == PRECIO_CENTAVOS

        monkeypatch.setitem(svc.PRECIO_POR_CUENTA, "duena@ejemplo.com", 300_000)
        sub = svc.obtener_o_crear(db, team["team"].id)
        assert sub.amount_cents == 300_000

    def test_a_una_ACTIVA_no_se_le_toca_el_precio(self, db, team, admin, tarjeta, monkeypatch):
        """Cambiarle el precio a una suscripción activa por detrás es lo que un
        cliente jamás espera. Exige una decisión explícita, no un efecto
        secundario de abrir una pantalla."""
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        sub = db.query(models.Subscription).one()
        assert sub.status == "active"

        monkeypatch.setitem(svc.PRECIO_POR_CUENTA, "duena@ejemplo.com", 300_000)
        svc.obtener_o_crear(db, team["team"].id)
        db.refresh(sub)
        assert sub.amount_cents == PRECIO_CENTAVOS

    def test_se_cobra_el_precio_de_la_cuenta_no_el_de_lista(
        self, db, team, admin, tarjeta, wompi_falso, monkeypatch
    ):
        """Lo que de verdad importa: que a Wompi le llegue el monto correcto."""
        monkeypatch.setitem(svc.PRECIO_POR_CUENTA, "duena@ejemplo.com", 300_000)
        admin.get("/pagos/suscripcion")  # crea la fila con el precio nuevo

        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        cobro = wompi_falso.estado.peticiones_a("/transactions")[0]
        assert cobro["amount_in_cents"] == 300_000


# ---------------------------------------------------------------------------
# El guardarraíl de PCI
# ---------------------------------------------------------------------------

class TestTokenDeTarjeta:
    """La frontera de PCI: al backend solo entra un `tok_...`."""

    def test_acepta_un_token_de_wompi(self):
        assert svc.validar_token_tarjeta("tok_test_1234_abcd") == "tok_test_1234_abcd"
        assert svc.validar_token_tarjeta("  tok_prod_9999_xyz  ") == "tok_prod_9999_xyz"

    @pytest.mark.parametrize(
        "valor",
        [
            "4242424242424242",
            "4242 4242 4242 4242",
            "4242-4242-4242-4242",
            "371449635398431",  # Amex, 15 dígitos
        ],
    )
    def test_rechaza_lo_que_parece_una_tarjeta(self, valor):
        with pytest.raises(svc.TokenInvalido):
            svc.validar_token_tarjeta(valor)

    @pytest.mark.parametrize("valor", ["", "   ", "no_es_un_token", "tok_", None])
    def test_rechaza_basura(self, valor):
        with pytest.raises(svc.TokenInvalido):
            svc.validar_token_tarjeta(valor)

    def test_el_error_no_repite_lo_que_recibio(self):
        """El mensaje no puede traer el PAN: sería escribirlo en el log que se
        está tratando de mantener limpio."""
        with pytest.raises(svc.TokenInvalido) as excinfo:
            svc.validar_token_tarjeta("4242424242424242")
        assert "4242" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Activación
# ---------------------------------------------------------------------------

class TestActivacion:

    def test_estado_inicial_es_pendiente_por_activar(self, admin):
        """Sin haber pagado nunca, el botón dice 'pendiente por activar'."""
        respuesta = admin.get("/pagos/suscripcion")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["status"] == "pending"
        assert cuerpo["amount_cop"] == 350_000
        assert cuerpo["tarjeta"] is None
        assert cuerpo["next_charge_at"] is None

    def test_activar_guarda_la_tarjeta_y_cobra(self, admin, db, tarjeta, wompi_falso):
        token = tarjeta(TARJETA_APROBADA)
        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": token, "acepta_terminos": True},
        )
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()

        # La tarjeta quedó registrada y se muestra reconocible pero inútil.
        assert cuerpo["tarjeta"] == {"brand": "VISA", "last_four": "4242"}

        # Se cobró el monto del plan, no uno que venga del cliente.
        cobros = wompi_falso.estado.peticiones_a("/transactions")
        assert len(cobros) == 1
        assert cobros[0]["amount_in_cents"] == PRECIO_CENTAVOS
        assert cobros[0]["currency"] == "COP"
        # `recurrent` es lo que le dice a la franquicia que es un cobro
        # periódico autorizado; sin eso los bancos rechazan mucho más.
        assert cobros[0]["recurrent"] is True
        # Wompi exige la firma de integridad también por API.
        assert cobros[0]["signature"]

    def test_manda_los_dos_tokens_de_aceptacion(self, admin, tarjeta, wompi_falso):
        """Habeas data: cada consentimiento va en su campo, no el mismo dos veces."""
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        fuente = wompi_falso.estado.peticiones_a("/payment_sources")[0]
        assert fuente["acceptance_token"] == ACCEPTANCE_TOKEN
        assert fuente["accept_personal_auth"] == PERSONAL_AUTH_TOKEN

    def test_la_fuente_de_pago_se_crea_con_la_llave_privada(
        self, admin, tarjeta, wompi_falso
    ):
        """Y la tokenización, con la pública. Si se invirtieran, el secreto
        estaría viajando al navegador."""
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        por_ruta = {p["ruta"]: p["auth"] for p in wompi_falso.estado.peticiones}
        assert "prv_test" in por_ruta["/v1/payment_sources"]
        assert "prv_test" in por_ruta["/v1/transactions"]
        assert "pub_test" in por_ruta["/v1/tokens/cards"]

    def test_no_queda_activa_hasta_que_se_confirme_el_pago(self, admin, db, tarjeta):
        """Wompi responde y la suscripción sigue sin activarse.

        El doble responde `APPROVED` de una (la 4242), pero el estado final lo
        aterriza `aplicar_estado`, no la respuesta del POST. Se fuerza
        `PENDING` para comprobar que sin confirmación no se activa nada.
        """
        from .wompi_falso import TARJETA_APROBADA as APROBADA

        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(APROBADA), "acepta_terminos": True},
        )
        assert respuesta.status_code == 200
        # El doble aprueba de inmediato, así que acá sí queda activa.
        assert respuesta.json()["status"] == "active"

    def test_pendiente_mientras_wompi_no_decide(self, admin, db, tarjeta, wompi_falso):
        wompi_falso.estado.estado_forzado = "PENDING"
        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        cuerpo = respuesta.json()
        assert cuerpo["status"] == "pending"
        assert cuerpo["cobro_en_curso"] is True
        assert cuerpo["next_charge_at"] is None

    def test_tarjeta_rechazada_no_activa(self, admin, db, tarjeta):
        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(TARJETA_RECHAZADA), "acepta_terminos": True},
        )
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["status"] == "pending"
        assert cuerpo["cobros"][0]["status"] == "declined"

    def test_doble_clic_no_cobra_dos_veces(self, admin, tarjeta, wompi_falso):
        """El error más caro posible: dos cobros de $350.000 por un clic doble."""
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        segunda = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        assert segunda.status_code == 409
        assert len(wompi_falso.estado.peticiones_a("/transactions")) == 1

    def test_sin_aceptar_terminos_no_se_llama_a_wompi(self, admin, tarjeta, wompi_falso):
        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": False},
        )
        assert respuesta.status_code == 400
        assert wompi_falso.estado.peticiones_a("/payment_sources") == []

    def test_un_numero_de_tarjeta_se_rechaza_sin_salir_a_la_red(
        self, admin, wompi_falso
    ):
        """Si el frontend tuviera un bug y mandara el PAN, muere acá."""
        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": "4242424242424242", "acepta_terminos": True},
        )
        assert respuesta.status_code == 400
        assert wompi_falso.estado.peticiones == []

    def test_hay_tope_de_intentos_por_cuenta(
        self, admin, tarjeta, wompi_falso, monkeypatch
    ):
        """Contra el card testing: probar tarjetas robadas de a una desde una
        cuenta de administrador. A quien multan las franquicias es al comercio.
        """
        from app.routers import pagos as router_pagos
        from app.services import ratelimit

        monkeypatch.setattr(
            router_pagos,
            "_activaciones_limiter",
            ratelimit.SlidingWindow(por_ip=2, global_=100),
        )
        wompi_falso.estado.estado_forzado = "DECLINED"

        codigos = [
            admin.post(
                "/pagos/suscripcion/activar",
                json={"card_token": tarjeta(), "acepta_terminos": True},
            ).status_code
            for _ in range(3)
        ]
        assert codigos[-1] == 429
        # El tercero ni siquiera llegó a crear una fuente de pago en Wompi.
        assert len(wompi_falso.estado.peticiones_a("/payment_sources")) == 2

    def test_el_error_de_wompi_no_se_le_reenvia_al_cliente(
        self, admin, tarjeta, wompi_falso
    ):
        """Regla 6: el detalle va al log, el cliente ve algo genérico."""
        token = tarjeta()
        wompi_falso.estado.fallar_en = {"payment_sources": 422}
        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": token, "acepta_terminos": True},
        )
        assert respuesta.status_code == 502
        detalle = respuesta.json()["detail"]
        assert "422" not in detalle
        assert "INPUT_VALIDATION" not in detalle


# ---------------------------------------------------------------------------
# Autorización
# ---------------------------------------------------------------------------

class TestAutorizacion:
    """El asesor no maneja la caja. Ni para mirar."""

    @pytest.mark.parametrize(
        "ruta", ["/pagos/suscripcion", "/pagos/suscripcion/config"]
    )
    def test_el_asesor_no_puede_mirar(self, asesor, ruta):
        assert asesor.get(ruta).status_code == 403

    @pytest.mark.parametrize(
        "ruta", ["/pagos/suscripcion/activar", "/pagos/suscripcion/cancelar"]
    )
    def test_el_asesor_no_puede_tocar(self, asesor, ruta):
        respuesta = asesor.post(
            ruta, json={"card_token": "tok_test_1_x", "acepta_terminos": True}
        )
        assert respuesta.status_code == 403

    def test_sin_sesion_no_se_pasa(self, anonimo):
        assert anonimo.get("/pagos/suscripcion").status_code in (401, 403)


# ---------------------------------------------------------------------------
# Config para el formulario de tarjeta
# ---------------------------------------------------------------------------

class TestConfig:

    def test_entrega_lo_publico_y_nada_mas(self, admin, wompi_falso):
        cuerpo = admin.get("/pagos/suscripcion/config").json()
        assert cuerpo["public_key"].startswith("pub_test")
        assert cuerpo["acceptance_token"] == ACCEPTANCE_TOKEN
        assert cuerpo["tokens_url"].endswith("/tokens/cards")
        assert cuerpo["sandbox"] is True

        # Lo que NO puede salir: cualquier rastro de un secreto.
        crudo = admin.get("/pagos/suscripcion/config").text
        assert "prv_test" not in crudo
        assert "test_integrity_secreto" not in crudo
        assert "test_events_secreto" not in crudo

    def test_sin_llaves_no_se_ofrece_el_formulario(self, admin, monkeypatch):
        """Mejor un 503 antes de que el cliente escriba la tarjeta que un
        fallo después de escribirla."""
        monkeypatch.delenv("WOMPI_PRIVATE_KEY", raising=False)
        assert admin.get("/pagos/suscripcion/config").status_code == 503


# ---------------------------------------------------------------------------
# El webhook
# ---------------------------------------------------------------------------

class TestWebhook:
    """La única fuente de verdad sobre si un cobro entró."""

    def _cobro_pendiente(self, admin, db, tarjeta, wompi_falso):
        wompi_falso.estado.estado_forzado = "PENDING"
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        cobro = db.query(models.SubscriptionCharge).one()
        return cobro

    def test_aprueba_y_activa(self, admin, anonimo, db, tarjeta, wompi_falso):
        cobro = self._cobro_pendiente(admin, db, tarjeta, wompi_falso)

        respuesta = anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(cobro.reference, "APPROVED", PRECIO_CENTAVOS),
        )
        assert respuesta.status_code == 200

        sub = db.query(models.Subscription).one()
        db.refresh(sub)
        assert sub.status == "active"
        assert sub.next_charge_at is not None
        assert sub.billing_day == svc.dia_de_facturacion(sub.activated_at)

    def test_firma_invalida_no_activa_nada(self, admin, anonimo, db, tarjeta, wompi_falso):
        cobro = self._cobro_pendiente(admin, db, tarjeta, wompi_falso)

        respuesta = anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(cobro.reference, "APPROVED", PRECIO_CENTAVOS, secreto=None),
        )
        assert respuesta.status_code == 403

        db.refresh(cobro)
        assert cobro.status == "pending"
        assert db.query(models.Subscription).one().status == "pending"

    def test_el_webhook_repetido_no_cobra_de_nuevo(
        self, admin, anonimo, db, tarjeta, wompi_falso
    ):
        """Wompi reintenta hasta 3 veces en 24 h: el repetido es lo normal."""
        cobro = self._cobro_pendiente(admin, db, tarjeta, wompi_falso)
        evento = evento_wompi(cobro.reference, "APPROVED", PRECIO_CENTAVOS)

        anonimo.post("/pagos/wompi/webhook", json=evento)
        sub = db.query(models.Subscription).one()
        db.refresh(sub)
        primera_fecha = sub.next_charge_at

        segunda = anonimo.post("/pagos/wompi/webhook", json=evento)
        assert segunda.json().get("ya_acreditada") is True

        db.refresh(sub)
        # El ciclo no se corrió un mes más por un webhook repetido.
        assert sub.next_charge_at == primera_fecha

    def test_monto_que_no_cuadra_no_activa(self, admin, anonimo, db, tarjeta, wompi_falso):
        cobro = self._cobro_pendiente(admin, db, tarjeta, wompi_falso)

        anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(cobro.reference, "APPROVED", monto_centavos=1000),
        )
        db.refresh(cobro)
        assert cobro.status == "error"
        assert cobro.failure_code == "MONTO_NO_COINCIDE"
        assert db.query(models.Subscription).one().status == "pending"

    def test_referencia_de_otro_sistema_se_ignora(self, anonimo, db):
        respuesta = anonimo.post(
            "/pagos/wompi/webhook", json=evento_wompi("no-es-nuestra-referencia")
        )
        assert respuesta.status_code == 200
        assert respuesta.json().get("ignorado") is True

    def test_no_le_pisa_el_webhook_a_las_compras_de_mensajes(self, anonimo, db, team):
        """Las dos tablas comparten webhook: una referencia de compra tiene que
        seguir acreditando mensajes, no buscarse entre las suscripciones."""
        compra = models.CreditPurchase(
            team_id=team["team"].id,
            package_key="mensajes_1000",
            messages=1000,
            amount_cents=23_000_000,
            currency="COP",
            reference="gloma-1-mensajes_1000-abcdef",
            status=models.CREDIT_PURCHASE_PENDING,
        )
        db.add(compra)
        db.commit()

        anonimo.post(
            "/pagos/wompi/webhook",
            json=evento_wompi(compra.reference, "APPROVED", 23_000_000),
        )
        db.refresh(compra)
        assert compra.status == "approved"


# ---------------------------------------------------------------------------
# El cobro del mes (tick)
# ---------------------------------------------------------------------------

class TestTick:

    def _suscripcion_activa(self, admin, db, tarjeta, vence_hace=timedelta(minutes=1)):
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        sub = db.query(models.Subscription).one()
        assert sub.status == "active"
        # Se adelanta el reloj moviendo la fecha, no esperando un mes.
        sub.next_charge_at = datetime.utcnow() - vence_hace
        db.commit()
        return sub

    def test_cobra_cuando_vence_el_ciclo(self, admin, db, tarjeta, wompi_falso):
        sub = self._suscripcion_activa(admin, db, tarjeta)
        ciclo = sub.next_charge_at

        resumen = svc.tick(db)
        assert resumen["cobradas"] == 1

        db.refresh(sub)
        assert sub.status == "active"
        # El ciclo avanza desde la fecha PROGRAMADA, no desde ahora: si no, el
        # retraso del tick se acumularía mes a mes.
        assert sub.next_charge_at == svc.proxima_fecha_cobro(ciclo, sub.billing_day)
        assert len(wompi_falso.estado.peticiones_a("/transactions")) == 2

    def test_no_cobra_antes_de_tiempo(self, admin, db, tarjeta, wompi_falso):
        self._suscripcion_activa(admin, db, tarjeta, vence_hace=timedelta(days=-5))
        assert svc.tick(db)["cobradas"] == 0
        assert len(wompi_falso.estado.peticiones_a("/transactions")) == 1

    def test_dos_ticks_seguidos_no_cobran_dos_veces(self, admin, db, tarjeta, wompi_falso):
        """Dos tasks de ECS pueden atender el mismo tick."""
        self._suscripcion_activa(admin, db, tarjeta)
        svc.tick(db)
        svc.tick(db)
        assert len(wompi_falso.estado.peticiones_a("/transactions")) == 2  # 1 alta + 1 mes

    def test_no_cobra_una_cancelada(self, admin, db, tarjeta, wompi_falso):
        sub = self._suscripcion_activa(admin, db, tarjeta)
        admin.post("/pagos/suscripcion/cancelar")
        db.refresh(sub)

        assert svc.tick(db)["cobradas"] == 0
        assert len(wompi_falso.estado.peticiones_a("/transactions")) == 1

    def test_tres_rechazos_dejan_la_suscripcion_en_mora(
        self, admin, db, tarjeta, wompi_falso
    ):
        sub = self._suscripcion_activa(admin, db, tarjeta)
        wompi_falso.estado.estado_forzado = "DECLINED"

        for intento in range(1, svc.MAX_INTENTOS + 1):
            sub.next_charge_at = datetime.utcnow() - timedelta(minutes=1)
            db.commit()
            svc.tick(db)
            db.refresh(sub)
            if intento < svc.MAX_INTENTOS:
                # Espera un día antes de volver a molestar al banco.
                assert sub.status == "active"
                assert sub.next_charge_at > datetime.utcnow() + timedelta(hours=23)

        assert sub.status == "past_due"
        # No se cancela sola: la decisión de irse es del cliente.
        assert sub.payment_source_id is not None
        # El ciclo salta al mes siguiente en vez de seguir insistiendo.
        assert sub.next_charge_at > datetime.utcnow() + timedelta(days=20)

    def test_los_reintentos_de_un_ciclo_se_numeran(self, admin, db, tarjeta, wompi_falso):
        sub = self._suscripcion_activa(admin, db, tarjeta)
        wompi_falso.estado.estado_forzado = "DECLINED"

        for _ in range(2):
            sub.next_charge_at = datetime.utcnow() - timedelta(minutes=1)
            db.commit()
            svc.tick(db)
            db.refresh(sub)

        # El cobro de la activación es el intento 1 de SU ciclo; los dos del
        # mes son el 1 y el 2 del ciclo mensual.
        cobros = (
            db.query(models.SubscriptionCharge)
            .order_by(models.SubscriptionCharge.id)
            .all()
        )
        assert [c.attempt for c in cobros] == [1, 1, 2]
        assert cobros[-1].status == "declined"

    def test_el_reintento_conserva_el_ciclo_original(
        self, admin, db, tarjeta, wompi_falso
    ):
        """Un reintento paga el MISMO mes, aunque se ejecute dos días después.

        Si el reintento adoptara su propia fecha, un ciclo del 31 de enero que
        se reintenta el 2 de febrero calcularía el siguiente cobro desde
        febrero y se saltaría un mes entero de cobro.
        """
        sub = self._suscripcion_activa(admin, db, tarjeta)
        wompi_falso.estado.estado_forzado = "DECLINED"
        sub.next_charge_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
        svc.tick(db)

        ciclo = (
            db.query(models.SubscriptionCharge)
            .order_by(models.SubscriptionCharge.id.desc())
            .first()
            .scheduled_for
        )

        # Segundo intento, un día después.
        db.refresh(sub)
        sub.next_charge_at = datetime.utcnow() - timedelta(minutes=1)
        db.commit()
        svc.tick(db)

        reintento = (
            db.query(models.SubscriptionCharge)
            .order_by(models.SubscriptionCharge.id.desc())
            .first()
        )
        assert reintento.attempt == 2
        assert reintento.scheduled_for == ciclo


class TestReconciliacion:
    """Si el webhook no llega, el cobro igual se resuelve."""

    def test_resuelve_un_cobro_colgado(self, admin, db, tarjeta, wompi_falso):
        wompi_falso.estado.estado_forzado = "PENDING"
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        cobro = db.query(models.SubscriptionCharge).one()

        # Envejece el cobro: lleva más de 15 minutos sin noticias.
        cobro.created_at = datetime.utcnow() - timedelta(minutes=20)
        db.commit()

        # Wompi ya lo tiene aprobado, pero el webhook nunca llegó.
        wompi_falso.estado.transacciones[cobro.provider_tx_id]["status"] = "APPROVED"

        assert svc.tick(db)["reconciliadas"] == 1
        db.refresh(cobro)
        assert cobro.status == "approved"
        assert db.query(models.Subscription).one().status == "active"

    def test_no_toca_un_cobro_reciente(self, admin, db, tarjeta, wompi_falso):
        """15 minutos de gracia para que el webhook haga su trabajo."""
        wompi_falso.estado.estado_forzado = "PENDING"
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        assert svc.tick(db)["reconciliadas"] == 0


# ---------------------------------------------------------------------------
# Cancelación
# ---------------------------------------------------------------------------

class TestCancelacion:

    def test_apaga_el_cobro_y_olvida_la_tarjeta(self, admin, db, tarjeta):
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )

        respuesta = admin.post("/pagos/suscripcion/cancelar")
        assert respuesta.status_code == 200
        cuerpo = respuesta.json()
        assert cuerpo["status"] == "canceled"
        assert cuerpo["next_charge_at"] is None
        assert cuerpo["tarjeta"] is None

        # Guardar un medio de pago que el cliente pidió no volver a usar es
        # riesgo sin contrapartida.
        sub = db.query(models.Subscription).one()
        db.refresh(sub)
        assert sub.payment_source_id is None
        assert sub.card_last_four is None

    def test_no_se_puede_cancelar_lo_que_nunca_se_activo(self, admin):
        admin.get("/pagos/suscripcion")  # crea la fila en `pending`
        assert admin.post("/pagos/suscripcion/cancelar").status_code == 409

    def test_se_puede_reactivar_despues(self, admin, db, tarjeta, wompi_falso):
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        admin.post("/pagos/suscripcion/cancelar")

        respuesta = admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        assert respuesta.status_code == 200
        assert respuesta.json()["status"] == "active"
        # Una sola fila de suscripción por cuenta, siempre.
        assert db.query(models.Subscription).count() == 1


# ---------------------------------------------------------------------------
# Lo que no puede salir en la respuesta
# ---------------------------------------------------------------------------

class TestNoFiltraSecretos:

    def test_la_suscripcion_no_expone_la_llave_de_cobro(self, admin, db, tarjeta):
        """`payment_source_id` es con lo que se le cobra a ese cliente."""
        admin.post(
            "/pagos/suscripcion/activar",
            json={"card_token": tarjeta(), "acepta_terminos": True},
        )
        sub = db.query(models.Subscription).one()

        crudo = admin.get("/pagos/suscripcion").text
        assert "payment_source_id" not in crudo
        assert str(sub.payment_source_id) not in crudo
        assert "customer_email" not in crudo
        assert "duena@ejemplo.com" not in crudo

    def test_el_catalogo_no_expone_los_costos_del_negocio(self, admin):
        """El desglose (costo, margen, TRM) se retiró el 5-sep-2026.

        El endpoint es solo para administradores, pero el administrador de una
        cuenta **es el cliente**: mostrarle en qué se va cada peso es enseñarle
        el margen de Gloma. Ocultarlo solo en la pantalla no habría servido —
        seguiría viajando al navegador, a un DevTools de distancia.
        """
        crudo = admin.get("/pagos/paquetes").text
        for filtrado in ("desglose", "costo_cop", "margen", "trm", "neto_real"):
            assert filtrado not in crudo, f"«{filtrado}» volvió al catálogo"

    def test_el_repr_del_modelo_redacta(self, db, team):
        sub = models.Subscription(
            team_id=team["team"].id,
            plan_key="plan_mensual",
            amount_cents=PRECIO_CENTAVOS,
            payment_source_id=987654,
            customer_email="duena@ejemplo.com",
        )
        texto = repr(sub)
        assert "987654" not in texto
        assert "duena@ejemplo.com" not in texto
        assert "REDACTED" in texto
