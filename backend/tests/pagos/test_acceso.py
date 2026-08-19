"""Quién entra a la caja y quién no.

El módulo de pagos es de ADMINISTRADOR. El asesor que atiende la bandeja no
ve precios, ni saldo, ni historial: son datos del negocio. Lo que se prueba
acá es el portero, que es lo primero que hay que romper para que el resto
importe.
"""
from __future__ import annotations

import pytest

RUTAS_PRIVADAS = ["/pagos/paquetes", "/pagos/saldo"]


class TestAsesorNoEntra:
    @pytest.mark.parametrize("ruta", RUTAS_PRIVADAS)
    def test_asesor_recibe_403(self, asesor, ruta):
        assert asesor.get(ruta).status_code == 403

    def test_asesor_no_puede_iniciar_un_checkout(self, asesor):
        respuesta = asesor.post(
            "/pagos/checkout", json={"package_key": "mensajes_1000"}
        )
        assert respuesta.status_code == 403

    def test_el_403_no_explica_que_le_falta(self, asesor):
        """Regla 6: el motivo va al log del servidor, no al cliente."""
        detalle = asesor.get("/pagos/saldo").json()["detail"].lower()
        assert "can_manage_billing" not in detalle
        assert "owner" not in detalle
        assert "rol" not in detalle

    def test_access_le_dice_que_no_sin_reventar(self, asesor):
        """`/access` responde 200 siempre: solo dice sí o no."""
        respuesta = asesor.get("/pagos/access")
        assert respuesta.status_code == 200
        assert respuesta.json() == {"allowed": False}


class TestAdminEntra:
    @pytest.mark.parametrize("ruta", RUTAS_PRIVADAS)
    def test_el_dueño_pasa(self, admin, ruta):
        assert admin.get(ruta).status_code == 200

    def test_access_le_dice_que_si(self, admin):
        assert admin.get("/pagos/access").json() == {"allowed": True}


class TestPermisoEnVezDeRol:
    """`can_manage_billing` abre la caja sin volver dueño de la cuenta."""

    def test_asesor_con_el_permiso_entra(self, Sesion, db, team, asesor):
        from app import models

        permiso = (
            db.query(models.TeamPermission)
            .filter(
                models.TeamPermission.team_member_id == team["membresia_asesor"].id,
                models.TeamPermission.permission_key == "can_manage_billing",
            )
            .first()
        )
        assert permiso is not None, "el asesor debería traer el permiso en falso"
        assert permiso.enabled is False, (
            "REGRESIÓN: el asesor no puede traer la caja encendida por defecto"
        )

        permiso.enabled = True
        db.commit()

        assert asesor.get("/pagos/saldo").status_code == 200
        assert asesor.get("/pagos/access").json() == {"allowed": True}


class TestSaldo:
    def test_arranca_en_cero_y_sin_compras(self, admin):
        cuerpo = admin.get("/pagos/saldo").json()
        assert cuerpo["message_credits"] == 0
        assert cuerpo["compras"] == []

    def test_el_historial_no_expone_datos_del_pagador(self, admin, db, team):
        """Una compra del historial no puede traer correo, teléfono ni medio de pago."""
        from app import models

        db.add(
            models.CreditPurchase(
                team_id=team["team"].id,
                package_key="mensajes_1000",
                messages=1000,
                amount_cents=8_070_000,
                currency="COP",
                reference="gloma-1-mensajes_1000-abc",
                status=models.CREDIT_PURCHASE_APPROVED,
            )
        )
        db.commit()

        compra = admin.get("/pagos/saldo").json()["compras"][0]
        prohibidos = {"customer_email", "correo", "telefono", "payment_method", "card"}
        assert prohibidos.isdisjoint(compra.keys())
