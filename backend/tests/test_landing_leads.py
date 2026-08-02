"""Tests del formulario "Quiero que me contacten" de la landing (#298).

Solo validación de entrada (`LeadIn`) y del enum de estados que usa el panel
`/citas/solicitudes` (#298): no requieren BD ni red. La persistencia se cubre
con el smoke manual documentado en la BITACORA.
"""
from __future__ import annotations

import os
import unittest

from cryptography.fernet import Fernet
from pydantic import ValidationError

# El módulo de cifrado hace fail-fast al importarse: en tests usamos una clave
# efímera (nunca una real).
os.environ.setdefault("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())

from app.routers import citas as citas_router  # noqa: E402
from app.routers.landing import LeadIn  # noqa: E402


class TestLeadIn(unittest.TestCase):
    """El nombre es obligatorio y se normaliza antes de tocar la BD."""

    def test_lead_valido(self):
        lead = LeadIn(
            nombre="  Ana   María  ",
            email="Ana@Example.com",
            telefono="+57 300 111 2233",
        )
        self.assertEqual(lead.nombre, "Ana María")   # espacios colapsados
        self.assertEqual(lead.source, "gloma_landing")

    def test_nombre_obligatorio(self):
        with self.assertRaises(ValidationError):
            LeadIn(email="ana@example.com", telefono="+573001112233")

    def test_nombre_muy_corto(self):
        with self.assertRaises(ValidationError):
            LeadIn(nombre="A", email="ana@example.com", telefono="+573001112233")

    def test_nombre_solo_espacios(self):
        with self.assertRaises(ValidationError):
            LeadIn(nombre="    ", email="ana@example.com", telefono="+573001112233")

    def test_nombre_sin_caracteres_de_control(self):
        lead = LeadIn(
            nombre="Ana\tMaría\nQA",
            email="ana@example.com",
            telefono="+573001112233",
        )
        self.assertEqual(lead.nombre, "Ana María QA")

    def test_telefono_invalido(self):
        with self.assertRaises(ValidationError):
            LeadIn(nombre="Ana María", email="ana@example.com", telefono="abcdef")

    def test_email_invalido(self):
        with self.assertRaises(ValidationError):
            LeadIn(nombre="Ana María", email="no-es-correo", telefono="+573001112233")


class TestSolicitudSchemas(unittest.TestCase):
    """Validación server-side del panel: estado del enum y correo con formato."""

    def test_estado_por_defecto(self):
        s = citas_router.SolicitudCreate(email="ana@example.com")
        self.assertEqual(s.estado, "pendiente")
        self.assertEqual(s.email, "ana@example.com")

    def test_email_se_normaliza(self):
        s = citas_router.SolicitudCreate(email="  Ana@EXAMPLE.com ")
        self.assertEqual(s.email, "ana@example.com")

    def test_estado_invalido_en_alta(self):
        with self.assertRaises(ValidationError):
            citas_router.SolicitudCreate(email="ana@example.com", estado="masomenos")

    def test_estado_invalido_en_edicion(self):
        with self.assertRaises(ValidationError):
            citas_router.SolicitudUpdate(estado="ya_casi")

    def test_correo_invalido_en_edicion(self):
        with self.assertRaises(ValidationError):
            citas_router.SolicitudUpdate(email="ana@")

    def test_patch_parcial_no_toca_lo_no_enviado(self):
        cambios = citas_router.SolicitudUpdate(estado="contactado").model_dump(
            exclude_unset=True
        )
        self.assertEqual(cambios, {"estado": "contactado"})

    def test_estados_expuestos(self):
        self.assertEqual(citas_router.ESTADOS_SOLICITUD, ("pendiente", "contactado"))


if __name__ == "__main__":
    unittest.main()
