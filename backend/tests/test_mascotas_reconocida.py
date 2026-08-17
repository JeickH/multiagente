"""Un reencuentro tiene dos fichas y un par en el panel, no una sola ficha.

Antes, reconocer a una mascota en el chat solo marcaba la ficha de la
encontrada. La familia seguía figurando como "buscando" y la coincidencia
seguía contando como "sin revisar" — que es justo la lista por la que el equipo
decide a quién llamar. Estos casos fijan que los tres avancen juntos.
"""
from __future__ import annotations

import pytest

from app import models
from app.services import mascotas as svc


class _Ficha:
    def __init__(self, id_, codigo, estado=models.MASCOTA_ESTADO_ACTIVO):
        self.id, self.codigo, self.estado = id_, codigo, estado
        self.reconocida_at = self.reconocida_chat = self.updated_at = None


class _Par:
    def __init__(self, estado=models.MATCH_ESTADO_NUEVA):
        self.estado, self.updated_at = estado, None


class _Query:
    def __init__(self, resultado):
        self._r = resultado

    def filter(self, *a, **k):
        return self

    def first(self):
        return self._r


class _DB:
    def __init__(self, par=None):
        self.par, self.commits = par, 0

    def query(self, _modelo):
        return _Query(self.par)

    def commit(self):
        self.commits += 1


@pytest.fixture
def fichas(monkeypatch):
    encontrada = _Ficha(2, "MC-00002")
    perdida = _Ficha(1, "MC-00001")
    por_codigo = {"MC-00002": encontrada, "MC-00001": perdida}
    monkeypatch.setattr(svc, "obtener", lambda db, c: por_codigo.get(c))
    return perdida, encontrada


def test_marca_las_dos_fichas_y_el_par(fichas):
    perdida, encontrada = fichas
    par = _Par()
    db = _DB(par)

    assert svc.marcar_reconocida(db, "MC-00002", "chat123", "MC-00001") is True

    assert encontrada.estado == models.MASCOTA_ESTADO_RECONOCIDA
    assert perdida.estado == models.MASCOTA_ESTADO_RECONOCIDA
    assert par.estado == models.MATCH_ESTADO_RECONOCIDA
    assert encontrada.reconocida_chat == "chat123"
    assert db.commits == 1


def test_sin_reporte_de_quien_busca_solo_marca_la_encontrada(fichas):
    """El caso común: la persona reconoce sin haber registrado su propio caso."""
    perdida, encontrada = fichas
    db = _DB(None)

    assert svc.marcar_reconocida(db, "MC-00002", "chat123") is True

    assert encontrada.estado == models.MASCOTA_ESTADO_RECONOCIDA
    assert perdida.estado == models.MASCOTA_ESTADO_ACTIVO


def test_no_retrocede_un_estado_ya_avanzado(monkeypatch):
    """Una conversación nueva no puede devolver a `reconocida` algo ya reunido."""
    reunida = _Ficha(2, "MC-00002", estado=models.MASCOTA_ESTADO_REUNIDA)
    monkeypatch.setattr(svc, "obtener", lambda db, c: reunida)

    assert svc.marcar_reconocida(_DB(), "MC-00002") is False
    assert reunida.estado == models.MASCOTA_ESTADO_REUNIDA


def test_no_pisa_un_par_ya_confirmado(fichas):
    """Si el equipo ya confirmó el reencuentro, el bot no lo baja de categoría."""
    _, _ = fichas
    par = _Par(estado=models.MATCH_ESTADO_CONFIRMADA)
    db = _DB(None)  # el filtro por estado no lo devuelve

    svc.marcar_reconocida(db, "MC-00002", None, "MC-00001")

    assert par.estado == models.MATCH_ESTADO_CONFIRMADA


def test_reconocida_es_un_estado_valido_del_panel():
    assert models.MATCH_ESTADO_RECONOCIDA in models.AVAILABLE_MATCH_ESTADOS
