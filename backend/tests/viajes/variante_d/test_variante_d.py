"""Bot D (estrategia D, Sprint 36): config, guion y creación con el script de variantes.

Decisión del CEO del 7-nov-2026: conversación humana sin menús numerados, total
del grupo pronto y cierre «¿Te los aparto?»; reparto 25 / 25 / 50 con los bots 1
y 3 (el bot 2 fuera) y D como bot de reenganche de la cuenta. La llamada en
franja (puerta 2) queda apagada hasta el acuerdo con la agencia.
"""
from __future__ import annotations

import json
import re

import pytest

from app import crud, models
from app.data.bot_viajes_b import FLAGS_VARIANTE as FLAGS_B
from app.data.bot_viajes_c import LLM_CONFIG_C, instrucciones_c
from app.data.bot_viajes_d import LLM_CONFIG_D, instrucciones_d

from ..variante_c.test_variante_crear_bot import (  # noqa: F401  (fixture db)
    _a_y_b,
    _bot,
    _correr,
    _cuenta,
    _de,
    db,
    script,
)


class TestConfig:
    def test_es_la_variante_d_con_tarifario(self):
        assert LLM_CONFIG_D["variante"] == "D"
        assert LLM_CONFIG_D["context_key"] == "demo_viajes_d"
        assert LLM_CONFIG_D.get("tarifario")
        assert LLM_CONFIG_D["guardarrail_precio"] is True

    def test_la_llamada_en_franja_esta_apagada(self):
        assert LLM_CONFIG_D["llamada_en_franja"] is False

    def test_sin_vitrina_y_con_el_resto_de_banderas_de_b(self):
        assert "apertura_vitrina" not in LLM_CONFIG_D
        for k in FLAGS_B:
            if k not in ("apertura_vitrina", "variante"):
                assert k in LLM_CONFIG_D, k


class TestGuion:
    texto = instrucciones_d()

    def test_cabe_en_el_tope(self):
        assert len(self.texto) <= 40_000
        crud.validar_instrucciones(self.texto)

    def test_sin_menus_numerados_salvo_la_regla_que_los_prohibe(self):
        lineas = [l for l in self.texto.splitlines() if re.search(r"[1-9]️?⃣", l)]
        assert all("menús numerados" in l or "No escribes" in l for l in lineas), lineas

    def test_cierre_y_medellin(self):
        assert "¿Te los aparto?" in self.texto
        assert "sale de *Medellín*" in self.texto
        assert "¿Para cuántas personas sería?" in self.texto

    def test_no_ofrece_llamadas_con_hora(self):
        assert "No ofrezcas llamadas con hora" in self.texto

    def test_palabras_prohibidas(self):
        plano = self.texto.lower()
        # «seña» solo aparece en la regla que la prohíbe, nunca como forma de pago.
        assert not re.search(r"(?:una|la|con|de)\s+seña\b", plano)
        assert not re.search(r"\b\d+\s+d[ií]as\b(?!\s+h[aá]biles)", plano), "nada de «N días» en el guion"


def _con_c(db, c, a):
    cfg_c = {**json.loads(json.dumps(LLM_CONFIG_C)), "fuente_datos": "productos",
             "model_id": "modelo-fijado"}
    v = _bot(db, c, cfg_c, nombre="Plan · C", instrucciones=instrucciones_c())
    prod = db.query(models.BotProductoBot).filter_by(bot_id=a.id).one()
    db.add(models.BotProductoBot(bot_id=v.id, producto_id=prod.producto_id, activo=True, orden=1))
    db.commit()
    miembro = db.query(models.TeamMember).filter_by(user_id=c.dueño.id).one()
    crud.guardar_reparto(db, miembro, [(a.id, 50), (v.id, 50)])
    return v


class TestCrearD:
    def test_simula_sin_escribir(self, db):
        c = _cuenta(db)
        a, b = _a_y_b(db, c, reparto_ab=False)
        _con_c(db, c, a)
        codigo, salida = _correr(db, variante="D", reenganche=True)
        assert codigo == 0, salida
        assert "Simulación terminada" in salida
        assert "bot de reenganche" in salida
        db.expire_all()
        assert _de(db, "D") == []

    def test_aplica_reparto_25_25_50_y_reenganche(self, db):
        c = _cuenta(db)
        a, b = _a_y_b(db, c, reparto_ab=False)
        v_c = _con_c(db, c, a)
        codigo, salida = _correr(db, variante="D", aplicar=True, reenganche=True)
        assert codigo == 0, salida
        db.expire_all()
        (d,) = _de(db, "D")
        assert json.loads(d.llm_config)["variante"] == "D"
        assert d.instrucciones.strip() == instrucciones_d()
        assert d.es_reenganche is True
        pct = {x.id: x.reparto_pct for x in db.query(models.Bot).all()}
        assert pct[a.id] == 25 and pct[v_c.id] == 25 and pct[d.id] == 50
        assert not pct[b.id]
        assert [x.id for x in db.query(models.Bot).all() if x.es_reenganche] == [d.id]

        # Segunda corrida: nada cambia.
        codigo, salida = _correr(db, variante="D", aplicar=True, reenganche=True)
        assert codigo == 0, salida
        assert "ya es D" in salida

    def test_sin_reenganche_no_lo_marca(self, db):
        c = _cuenta(db)
        a, b = _a_y_b(db, c, reparto_ab=False)
        _con_c(db, c, a)
        codigo, salida = _correr(db, variante="D", aplicar=True)
        assert codigo == 0, salida
        db.expire_all()
        (d,) = _de(db, "D")
        assert d.es_reenganche is False
