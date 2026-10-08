"""Recordatorios con contexto del bot 2 (estrategia 28): `texto_recordatorio`.

Se lee la última consulta de precios de la conversación desde
`bot_llm_decisions.tools_called` (como la deja `llm_engine`) y se llena la
plantilla con las salidas que **quedan** de ese mes. Ante cualquier dato que
falte, `None`: el llamador manda el texto fijo de hoy.

Ninguna frase ni nombre de aquí es de una persona real (repo público, #8).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.services import recordatorios_contexto, tarifario
from app.services.recordatorios_contexto import PLANTILLAS_SUGERIDAS, texto_recordatorio
from tests.productos.conftest import crear_cuenta

HOY = date(2026, 10, 7)
CFG = {"recordatorios_con_contexto": True}
TODO = "{mes}|{salidas}|{n_salidas}|{desde}|{anticipo_pct}"


@pytest.fixture
def db():
    from app.database import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    yield sesion
    sesion.close()
    engine.dispose()


@pytest.fixture
def bot(db):
    _, bot_id = crear_cuenta(db, "recordatorios-b")
    return db.get(models.Bot, bot_id)


_RELOJ = {"t": datetime(2026, 10, 7, 12, 0)}


def _turno(db, bot_id, conv_id, llamadas):
    """Una fila de la bitácora como la escribe `llm_engine` (input recortado a
    200 caracteres por campo, todo string)."""
    _RELOJ["t"] += timedelta(minutes=1)
    db.add(models.BotLlmDecision(
        bot_id=bot_id, conversation_id=conv_id, source="whatsapp",
        camino="respuesta_libre", rounds=1, finished=False, failsafe=False,
        created_at=_RELOJ["t"],
        tools_called=json.dumps([
            {"tool": tool, "input": {k: str(v)[:200] for k, v in entrada.items()},
             "resultado": "…"}
            for tool, entrada in llamadas
        ], ensure_ascii=False),
    ))
    db.commit()


def _conv(conv_id=501, nombre=None):
    return SimpleNamespace(id=conv_id, contact_name=nombre)


def _texto(db, bot, plantilla=TODO, conv=None, cfg=CFG, hoy=HOY):
    return texto_recordatorio(
        db, conversation=conv or _conv(), bot=bot, cfg=cfg,
        etapa={"minutos": 300, "texto": "fijo", "plantilla": plantilla}, hoy=hoy,
    )


def _esperado(mes, anio, hotel, hoy=HOY):
    salidas = tarifario.salidas_restantes(mes, anio, hotel, hoy)
    return salidas, tarifario._pesos(min(s["desde"] for s in salidas))


# ---------------------------------------------------------------------------
# Lo normal
# ---------------------------------------------------------------------------

def test_llena_la_plantilla_con_la_consulta_de_tarifario(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre", "hotel": "Amor de Dios"})])
    mes, salidas, n, desde, pct = _texto(db, bot).split("|")
    esperadas, desde_ok = _esperado(10, 2026, "amor de dios")
    assert mes == "octubre"
    assert n == str(len(esperadas))
    assert desde == desde_ok
    tope = recordatorios_contexto.MAX_SALIDAS_EN_RECORDATORIO
    for s in esperadas[:tope]:
        assert s["etiqueta"] in salidas
    if len(esperadas) > tope:
        # No es un listado: se nombran las primeras y se cuenta el resto.
        assert salidas.endswith(f" y {len(esperadas) - tope} más")
        assert esperadas[-1]["etiqueta"] not in salidas
    else:
        assert salidas.count(" y ") == 1 and salidas.endswith(esperadas[-1]["etiqueta"])
    assert pct == str(tarifario.extras()["anticipo_pct"])


def test_consulta_de_productos_con_variante(db, bot):
    """`consultar_precios` trae el hotel en `variante` (el producto es el plan)."""
    _turno(db, bot.id, 501, [("consultar_precios", {"variante": "Bohíos", "mes": "diciembre"})])
    texto = _texto(db, bot, "{hotel} {mes} {desde}")
    _, desde = _esperado(12, 2026, "bohios")
    assert texto == f"Bohíos diciembre {desde}"   # su nombre, con la tabla de Amor de Dios


def test_sin_hotel_toma_los_dos(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    _, desde = _esperado(10, 2026, None)
    assert _texto(db, bot, "{desde}") == desde
    assert _texto(db, bot, "{hotel}") is None      # pide hotel y no lo hay


def test_toma_la_ultima_consulta(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "noviembre"})])
    _turno(db, bot.id, 501, [("enviar_media", {"clave": "tours"}),
                              ("consultar_tarifario", {"mes": "diciembre"}),
                              ("consultar_tarifario", {"mes": "octubre"}),
                              ("enviar_media", {"clave": "medios_pago"})])
    _turno(db, bot.id, 501, [("enviar_media", {"clave": "tours"})])
    assert _texto(db, bot, "{mes}") == "octubre"


def test_fecha_sin_mes(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"fecha": "2026-11-20"})])
    assert _texto(db, bot, "{mes}") == "noviembre"


def test_mes_del_anio_siguiente(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "enero"})])
    salidas, _ = _esperado(1, 2027, None)
    assert _texto(db, bot, "{n_salidas}") == str(len(salidas))


def test_nombre_cuando_es_de_verdad(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    assert _texto(db, bot, "Hola {nombre}", conv=_conv(nombre="valentina prueba")) == "Hola Valentina"


@pytest.mark.parametrize("nombre", [None, "", "Cliente", "No proporcionado", "573000000009", "x"])
def test_sin_nombre_util_cae_al_texto_fijo(db, bot, nombre):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    assert _texto(db, bot, "Hola {nombre}", conv=_conv(nombre=nombre)) is None
    assert _texto(db, bot, "Hola", conv=_conv(nombre=nombre)) == "Hola"


# ---------------------------------------------------------------------------
# Casos en que va el texto fijo
# ---------------------------------------------------------------------------

def test_sin_flag(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    assert _texto(db, bot, cfg={}) is None
    assert _texto(db, bot, cfg={"recordatorios_con_contexto": False}) is None


@pytest.mark.parametrize("plantilla", [None, "", "   "])
def test_sin_plantilla(db, bot, plantilla):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    assert _texto(db, bot, plantilla) is None


def test_sin_ninguna_consulta(db, bot):
    _turno(db, bot.id, 501, [("enviar_media", {"clave": "tours"})])
    assert _texto(db, bot) is None


def test_consulta_solo_por_presupuesto(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"presupuesto": "450 mil"})])
    assert _texto(db, bot) is None


def test_ya_no_quedan_salidas_de_ese_mes(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    assert _texto(db, bot, hoy=date(2026, 10, 31)) is None


def test_mes_sin_temporada(db, bot):
    """Septiembre ya pasó: el próximo septiembre (2027) no está publicado."""
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "septiembre"})])
    assert _texto(db, bot) is None


def test_hotel_que_no_se_reconoce(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre", "hotel": "Hotel Inventado"})])
    assert _texto(db, bot) is None


def test_no_mezcla_conversaciones_ni_bots(db, bot):
    _, otro_bot = crear_cuenta(db, "otro-bot")
    _turno(db, bot.id, 999, [("consultar_tarifario", {"mes": "octubre"})])
    _turno(db, otro_bot, 501, [("consultar_tarifario", {"mes": "octubre"})])
    assert _texto(db, bot) is None


@pytest.mark.parametrize("plantilla", ["{mes", "{otro}", "{0}", "{mes!z}"])
def test_plantilla_mal_formada(db, bot, plantilla):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    assert _texto(db, bot, plantilla) is None


@pytest.mark.parametrize("plantilla", [
    "Las salidas de {mes} que quedan con cupo: {salidas}",
    "Todavía hay cupo para {mes} 🌴",
    "Tenemos cupos disponibles en {mes}",
    "Quedan pocos cupos para {mes}",
])
def test_nunca_afirma_cupo(db, bot, plantilla, caplog):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre"})])
    with caplog.at_level(logging.WARNING):
        assert _texto(db, bot, plantilla) is None
    assert "octubre" not in caplog.text          # el log no lleva contenido


def test_bitacora_corrupta_no_rompe(db, bot):
    db.add(models.BotLlmDecision(bot_id=bot.id, conversation_id=501, source="whatsapp",
                                 camino="x", rounds=1, finished=False, failsafe=False,
                                 tools_called="{no es json"))
    db.commit()
    assert _texto(db, bot) is None


# ---------------------------------------------------------------------------
# Las plantillas sugeridas
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("etapa", sorted(PLANTILLAS_SUGERIDAS))
def test_las_plantillas_sugeridas_salen_bien(db, bot, etapa):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre", "hotel": "Piedra Mar"})])
    texto = _texto(db, bot, PLANTILLAS_SUGERIDAS[etapa])
    assert texto and "{" not in texto
    salidas, desde = _esperado(10, 2026, "piedra mar")
    assert desde in texto and salidas[0]["etiqueta"] in texto
    assert "con cupo" not in texto


@pytest.mark.parametrize("etapa", sorted(PLANTILLAS_SUGERIDAS))
def test_las_plantillas_sugeridas_con_una_sola_salida(db, bot, etapa):
    """El 24 de octubre solo queda la del 30: tiene que leerse bien igual."""
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre", "hotel": "Amor de Dios"})])
    texto = _texto(db, bot, PLANTILLAS_SUGERIDAS[etapa], hoy=date(2026, 10, 24))
    assert texto and "30 al 2 de noviembre" in texto and " y " not in texto.split("desde")[0]


def test_desde_llega_formateado_en_pesos(db, bot):
    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre", "hotel": "Amor de Dios"})])
    assert _texto(db, bot, "{desde}") == tarifario._pesos(
        min(s["desde"] for s in tarifario.salidas_restantes(10, 2026, "Amor de Dios", HOY))
    )
    assert _texto(db, bot, "{desde}").startswith("$")


def test_las_plantillas_del_bot_2_encajan():
    """Las que puso el agente variante en `bot_viajes_b.py` solo usan
    placeholders que esta función llena, y ninguna afirma cupo."""
    pytest.importorskip("app.data.bot_viajes_b")
    from string import Formatter

    from app.data.bot_viajes_b import PLANTILLAS_RECORDATORIO

    validos = {"nombre", "mes", "salidas", "n_salidas", "desde", "anticipo_pct", "hotel"}
    for plantilla in PLANTILLAS_RECORDATORIO.values():
        campos = {c for _, c, _, _ in Formatter().parse(plantilla) if c}
        assert campos <= validos - {"nombre", "hotel"}, campos


@pytest.mark.parametrize("hoy", [HOY, date(2026, 10, 24)])
def test_las_plantillas_del_bot_2_se_llenan(db, bot, hoy):
    pytest.importorskip("app.data.bot_viajes_b")
    from app.data.bot_viajes_b import PLANTILLAS_RECORDATORIO

    _turno(db, bot.id, 501, [("consultar_tarifario", {"mes": "octubre", "hotel": "Amor de Dios"})])
    for plantilla in PLANTILLAS_RECORDATORIO.values():
        texto = _texto(db, bot, plantilla, hoy=hoy)
        assert texto and "{" not in texto and "$" in texto
