"""Rendimiento y salud de mascotasperdidascolombia.com (producción).

**Sale a internet.** Corre con `--con-costo`.

Solo hace GET. No postea al chat: cada turno del chat de producción invoca el
modelo (gasto real) y deja una fila en el registro de conversaciones del panel,
que el equipo lee como si fuera una persona buscando a su mascota. Lo que se
prueba aquí es que el sitio esté arriba, que cargue rápido desde Colombia y que
la firma de marca siga donde debe.

Los umbrales son deliberadamente holgados: esto mide una red real y tiene que
avisar cuando algo se rompió, no ponerse rojo porque el wifi anduvo lento.
"""
from __future__ import annotations

import time

import pytest

requests = pytest.importorskip("requests")

SITIO = "https://mascotasperdidascolombia.com"
API = "https://api.glomabeauty.com"
TIMEOUT = 30

# Umbrales. Un sitio de emergencia lo abre gente angustiada, muchas veces desde
# un celular con datos móviles: si tarda más de esto, hay que mirarlo.
TTFB_MAX_S = 5.0
CARGA_MAX_S = 10.0
PESO_MAX_KB = 3000


@pytest.fixture(scope="module")
def portada():
    """La portada, bajada una sola vez para todo el módulo."""
    inicio = time.monotonic()
    try:
        r = requests.get(SITIO, timeout=TIMEOUT)
    except requests.RequestException as exc:
        pytest.skip(f"no se pudo alcanzar {SITIO}: {exc}")
    return r, time.monotonic() - inicio


class TestDisponibilidad:
    def test_el_sitio_responde(self, portada):
        r, _ = portada
        assert r.status_code == 200, f"el sitio devolvió {r.status_code}"

    def test_llega_por_https(self, portada):
        r, _ = portada
        assert r.url.startswith("https://"), "la conexión no quedó en HTTPS"

    def test_es_la_pagina_de_mascotas(self, portada):
        r, _ = portada
        texto = r.text.lower()
        assert "mascota" in texto, "la portada no habla de mascotas"


class TestRendimiento:
    def test_carga_en_un_tiempo_razonable(self, portada):
        r, segundos = portada
        assert segundos < CARGA_MAX_S, (
            f"la portada tardó {segundos:.1f} s en cargar (máximo {CARGA_MAX_S} s)"
        )

    def test_el_primer_byte_no_se_hace_esperar(self):
        inicio = time.monotonic()
        try:
            with requests.get(SITIO, timeout=TIMEOUT, stream=True) as r:
                next(r.iter_content(1), None)
        except requests.RequestException as exc:
            pytest.skip(f"no se pudo alcanzar {SITIO}: {exc}")
        ttfb = time.monotonic() - inicio
        assert ttfb < TTFB_MAX_S, f"TTFB de {ttfb:.1f} s"

    def test_el_html_no_pesa_de_mas(self, portada):
        r, _ = portada
        kb = len(r.content) / 1024
        assert kb < PESO_MAX_KB, (
            f"el HTML pesa {kb:.0f} KB; con datos móviles eso se siente"
        )

    @pytest.mark.parametrize("intentos", [3])
    def test_responde_de_forma_consistente(self, intentos):
        """Tres cargas seguidas: detecta el caso de una sola instancia caída
        detrás del balanceador."""
        tiempos = []
        for _ in range(intentos):
            inicio = time.monotonic()
            try:
                r = requests.get(SITIO, timeout=TIMEOUT)
            except requests.RequestException as exc:
                pytest.skip(f"no se pudo alcanzar {SITIO}: {exc}")
            assert r.status_code == 200
            tiempos.append(time.monotonic() - inicio)
        assert max(tiempos) < CARGA_MAX_S, f"tiempos: {tiempos}"


class TestMarca:
    def test_el_footer_dice_tecnologia_de_gloma_app(self, portada):
        """Manual §1: la firma del sitio público. Los cambios de marca de este
        sitio viven solo aquí — si desaparece, alguien tocó lo que no era."""
        r, _ = portada
        texto = r.text.replace("&nbsp;", " ")
        assert "Gloma" in texto, "se cayó la firma 'Tecnología de Gloma App'"


class TestApi:
    def test_el_backend_esta_arriba(self):
        try:
            r = requests.get(f"{API}/docs", timeout=TIMEOUT)
        except requests.RequestException as exc:
            pytest.skip(f"no se pudo alcanzar {API}: {exc}")
        assert r.status_code < 500, f"la API devolvió {r.status_code}"

    def test_el_listado_exige_token(self):
        """La descarga pública no puede quedar abierta: sin token, 4xx."""
        try:
            r = requests.get(f"{API}/mascotas/listado.xlsx", timeout=TIMEOUT)
        except requests.RequestException as exc:
            pytest.skip(f"no se pudo alcanzar {API}: {exc}")
        assert 400 <= r.status_code < 500, (
            f"el listado respondió {r.status_code} sin token"
        )

    def test_el_panel_esta_cerrado_al_publico(self):
        """Sin JWT no se ve un solo teléfono."""
        try:
            r = requests.get(f"{API}/mascotas/panel", timeout=TIMEOUT)
        except requests.RequestException as exc:
            pytest.skip(f"no se pudo alcanzar {API}: {exc}")
        assert r.status_code in (401, 403), (
            f"el panel privado respondió {r.status_code} sin autenticación"
        )
