"""Pruebas que cuestan plata.

**Todo lo que viva bajo este paquete queda marcado `costo` automáticamente**, y
por lo tanto no corre a menos que se pase `--con-costo`. Es a propósito: el CI
de cada push corre la suite completa sin generar un centavo de factura, y estas
se corren a mano cuando se quiere medir de verdad.

    pytest --con-costo -m costo tests/mascotas/costo

Qué cuesta aquí:
- `test_modelo_real.py` invoca **Claude en Bedrock** de verdad (centavos por
  corrida, ver el resumen que imprime al final).
- `test_sitio_publico.py` sale a internet contra mascotasperdidascolombia.com.
  No escribe nada: solo GET. **Nunca** postea al chat de producción, que
  gastaría modelo y ensuciaría el registro de conversaciones del panel.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List

import pytest

# Precios de Haiku 4.5 por millón de tokens (us-east-1/global, agosto 2026).
# Solo para estimar el costo de la corrida en el resumen final.
USD_POR_MTOK_ENTRADA = 1.00
USD_POR_MTOK_SALIDA = 5.00
USD_POR_MTOK_CACHE_LECTURA = 0.10
USD_POR_MTOK_CACHE_ESCRITURA = 1.25


_AQUI = Path(__file__).parent


def pytest_collection_modifyitems(config, items):
    """Marca `costo` todo lo de este paquete, sin tener que repetirlo archivo
    por archivo (olvidarlo una vez significa facturar en el CI).

    El hook recibe **todos** los tests de la sesión, no solo los de esta
    carpeta: hay que filtrar por ruta o se marcaría la suite entera como
    facturable y no correría nada por defecto.
    """
    for item in items:
        try:
            ruta = Path(str(item.fspath))
        except Exception:
            continue
        if _AQUI == ruta.parent or _AQUI in ruta.parents:
            item.add_marker(pytest.mark.costo)


class Medidor:
    """Acumula lo que gastó y tardó cada llamada al modelo."""

    def __init__(self) -> None:
        self.llamadas: List[Dict[str, Any]] = []

    def registrar(self, uso: Dict[str, Any], ms: float, etiqueta: str) -> None:
        self.llamadas.append({
            "etiqueta": etiqueta,
            "ms": ms,
            "entrada": uso.get("input_tokens") or 0,
            "salida": uso.get("output_tokens") or 0,
            "cache_lectura": uso.get("cache_read_input_tokens") or 0,
            "cache_escritura": uso.get("cache_creation_input_tokens") or 0,
        })

    @property
    def usd(self) -> float:
        total = 0.0
        for c in self.llamadas:
            total += c["entrada"] / 1e6 * USD_POR_MTOK_ENTRADA
            total += c["salida"] / 1e6 * USD_POR_MTOK_SALIDA
            total += c["cache_lectura"] / 1e6 * USD_POR_MTOK_CACHE_LECTURA
            total += c["cache_escritura"] / 1e6 * USD_POR_MTOK_CACHE_ESCRITURA
        return total

    def latencias(self) -> List[float]:
        return sorted(c["ms"] for c in self.llamadas)

    def percentil(self, p: float) -> float:
        datos = self.latencias()
        if not datos:
            return 0.0
        return datos[min(len(datos) - 1, int(len(datos) * p))]


@pytest.fixture(scope="session")
def medidor() -> Medidor:
    return Medidor()


@pytest.fixture(scope="session", autouse=True)
def resumen_de_gasto(medidor, request):
    """Imprime al final qué se gastó. Sin esto, "las pruebas con costo" es una
    frase; con esto es un número que el CEO puede mirar."""
    yield
    if not medidor.llamadas:
        return
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    entrada = sum(c["entrada"] for c in medidor.llamadas)
    salida = sum(c["salida"] for c in medidor.llamadas)
    cache_r = sum(c["cache_lectura"] for c in medidor.llamadas)
    cache_w = sum(c["cache_escritura"] for c in medidor.llamadas)
    reporter.write_sep("=", "gasto de esta corrida")
    reporter.write_line(f"llamadas al modelo : {len(medidor.llamadas)}")
    reporter.write_line(
        f"tokens             : {entrada} entrada · {salida} salida · "
        f"{cache_r} leídos de caché · {cache_w} escritos en caché"
    )
    reporter.write_line(
        f"latencia por llamada: p50 {medidor.percentil(0.5):.0f} ms · "
        f"p95 {medidor.percentil(0.95):.0f} ms"
    )
    if entrada + cache_r:
        ahorro = cache_r / (entrada + cache_r) * 100
        reporter.write_line(f"entrada servida por caché: {ahorro:.0f}%")
    reporter.write_line(f"costo estimado     : US$ {medidor.usd:.4f}")


@pytest.fixture
def bedrock_disponible():
    """Salta la prueba con un motivo claro si no hay credenciales o región.

    Mejor un skip explicativo que un fallo de red que parezca un bug del bot.
    """
    boto3 = pytest.importorskip("boto3")
    region = os.getenv("BEDROCK_REGION", "sa-east-1")
    sesion = boto3.session.Session()
    if sesion.get_credentials() is None:
        pytest.skip(
            "sin credenciales AWS: configura el perfil (cuenta 747456040509) "
            f"y BEDROCK_REGION={region}"
        )
    return region


@pytest.fixture
def modelo_real(monkeypatch, medidor, bedrock_disponible):
    """Deja pasar las llamadas de verdad a Bedrock y las mide.

    Envuelve `_invoke_model` en vez de reemplazarlo: se mide exactamente lo que
    corre en producción, con su prompt caching y sus tools.
    """
    from app.services import llm_engine

    original = llm_engine._invoke_model
    etiqueta = {"actual": "sin-etiqueta"}

    def _medido(model_id, system, messages, tools):
        t0 = time.monotonic()
        data = original(model_id, system, messages, tools)
        ms = (time.monotonic() - t0) * 1000
        medidor.registrar(data.get("usage") or {}, ms, etiqueta["actual"])
        return data

    monkeypatch.setattr(llm_engine, "_invoke_model", _medido)
    return etiqueta
