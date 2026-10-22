"""Cierre de venta de los bots de Arranquemos Pues (CEO, 2026-10-21).

El bot vende hasta los datos y las formas de pago; ahí entrega a un asesor y
deja la conversación marcada como «listo para reservar», de primera en la
bandeja. Más las reglas que salieron de leer los chats de las asesoras:
acomodación, pago total, ciudades, salida negada sin consultar, notas de voz
transcritas y búsqueda por teléfono.

Pasa por `bot_runner.run_turn`, que es el camino de producción (la lección del
2026-10-20: probar `advance` directo dejó pasar un defecto entero).
Datos inventados (regla #8).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any, Dict, List

import pytest

from app import crud, models
from app.data.bot_viajes import LLM_CONFIG
from app.data.bot_viajes_b import LLM_CONFIG_B
from app.data.bot_viajes_c import LLM_CONFIG_C
from app.services import adjuntos, bot_runner, llm_engine, tarifario, transcripcion

from .variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    conversacion,
    crear_agencia,
    db,
)

DATOS = "Ana Pérez Gómez, CC 1000000001, 01/02/1990; correo ana@ejemplo.test"
#: Sin cifra a propósito: con un monto y sin consulta previa en la sesión, el
#: guardarraíl de precio de los bots 2 y 3 (bien) tumba el mensaje.
COBRO = ("¡Listo, recibí tus datos! ✅ Para apartar pagas el anticipo del 30% del total. "
         "Haz la transferencia y mándame el comprobante por aquí 📎, un compañero te "
         "confirma la reserva ✨")


def _resp(*bloques):
    con_tool = any(b["type"] == "tool_use" for b in bloques)
    return {"content": list(bloques), "stop_reason": "tool_use" if con_tool else "end_turn"}


@pytest.fixture
def modelo(monkeypatch):
    """Modelo falso con guion: cada llamada saca la siguiente respuesta."""
    guion: List[Dict[str, Any]] = []
    vistos: List[str] = []

    def invocar(model_id, system, working, tools, *a, **k):
        vistos.append(json.dumps(working, ensure_ascii=False))
        return guion.pop(0)

    monkeypatch.setattr(llm_engine, "_invoke_model", invocar)
    monkeypatch.setattr(llm_engine, "record_booking", lambda *a, **k: None, raising=False)
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: date(2026, 10, 21))
    return guion, vistos


def _cierre(guion):
    guion.extend([
        _resp({"type": "text", "text": COBRO},
              {"type": "tool_use", "id": "t1", "name": "listo_para_reservar",
               "input": {"resumen": "Simulacro 23-26 oct, Amor de Dios, 2 adultos, doble",
                         "datos": DATOS}}),
        _resp({"type": "text", "text": ""}),
    ])


def _mensajes(db, conv):
    return db.query(models.Message).filter(models.Message.conversation_id == conv.id).order_by(models.Message.id).all()


# ---------------------------------------------------------------------------
# El cierre
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cfg,sufijo", [(LLM_CONFIG, "CR1"), (LLM_CONFIG_B, "CR2"), (LLM_CONFIG_C, "CR3")],
                         ids=["bot1", "bot2", "bot3"])
def test_los_datos_dejan_la_conversacion_lista_para_reservar(db, modelo, cfg, sufijo):
    guion, _ = modelo
    _cierre(guion)
    ag = crear_agencia(db, sufijo=sufijo, cfg=json.loads(json.dumps(cfg)))
    conv = conversacion(db, ag["team"])
    bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                        user_input=DATOS, meta_account=None)
    db.refresh(conv)
    assert conv.etiqueta == llm_engine.ETIQUETA_LISTO_PARA_RESERVAR
    assert conv.assigned_to in ("Camila", "Julián")
    msgs = _mensajes(db, conv)
    salientes = [m.content for m in msgs if m.direction == "outbound" and m.message_type != "nota_interna"]
    assert any("demo_viajes/medios_pago" in c for c in salientes), salientes
    assert any("comprobante" in c for c in salientes)
    notas = [m.content for m in msgs if m.message_type == "nota_interna"]
    assert notas and notas[-1].startswith("🟢 *Listo para reservar*")
    assert "Simulacro 23-26 oct" in notas[-1] and "CC 1000000001" in notas[-1]


def test_la_herramienta_existe_solo_con_tarifario():
    nombres = lambda cfg: [t["name"] for t in llm_engine._tools_for(cfg, None, "")]
    assert "listo_para_reservar" in nombres(dict(LLM_CONFIG))
    sin = {k: v for k, v in LLM_CONFIG.items() if k != "tarifario"}
    assert "listo_para_reservar" not in nombres(sin)


# ---------------------------------------------------------------------------
# La bandeja
# ---------------------------------------------------------------------------

def _conv(db, team, wa, nombre, etiqueta=None, status="open", minutos=0):
    c = models.Conversation(team_id=team.id, contact_wa_id=wa, contact_name=nombre,
                            status=status, assigned_to="Camila", etiqueta=etiqueta,
                            last_message_at=datetime.utcnow() - timedelta(minutes=minutos))
    db.add(c)
    db.commit()
    return c


def test_las_listas_para_reservar_van_de_primeras(db):
    ag = crear_agencia(db, sufijo="BJ1")
    reciente = _conv(db, ag["team"], "573000000301", "Reciente", minutos=1)
    lista = _conv(db, ag["team"], "573000000302", "Lista",
                  etiqueta="listo para reservar", minutos=90)
    cerrada = _conv(db, ag["team"], "573000000303", "Cerrada",
                    etiqueta="listo para reservar", status="closed", minutos=0)
    convs, _ = crud.list_conversations(db, ag["team"].id)
    assert [c.id for c in convs][:2] == [lista.id, cerrada.id] or convs[0].id == lista.id
    assert convs[0].id == lista.id
    solo, total = crud.list_conversations(db, ag["team"].id, etiqueta="listo para reservar")
    assert [c.id for c in solo] == [lista.id] and total == 1
    assert reciente.id not in [c.id for c in solo]


@pytest.mark.parametrize("busqueda", [
    "313 000 0304", "+57 313-000-0304", "(313) 0000304", "3130000304", "573130000304", "0000304",
])
def test_busca_por_telefono_en_cualquier_formato(db, busqueda):
    ag = crear_agencia(db, sufijo="BJ2" + str(abs(hash(busqueda)) % 1000))
    buscada = _conv(db, ag["team"], "573130000304", "Buscada")
    _conv(db, ag["team"], "573140000999", "Otra")
    convs, total = crud.list_conversations(db, ag["team"].id, busqueda=busqueda)
    assert [c.id for c in convs] == [buscada.id] and total == 1


def test_un_numero_corto_en_el_nombre_no_busca_por_telefono(db):
    ag = crear_agencia(db, sufijo="BJ3")
    _conv(db, ag["team"], "573130002026", "Ana")
    convs, _ = crud.list_conversations(db, ag["team"].id, busqueda="2026")
    assert len(convs) == 1   # por el LIKE de siempre sobre el número, no por dígitos


# ---------------------------------------------------------------------------
# Notas de precios y reglas
# ---------------------------------------------------------------------------

def test_notas_de_precios(monkeypatch):
    monkeypatch.setattr(tarifario, "hoy_colombia", lambda: date(2026, 10, 21))
    oct_ = tarifario.consultar(LLM_CONFIG, mes="octubre", hoy=date(2026, 10, 21))
    notas = llm_engine._notas_de_precios(oct_)
    assert "MÚLTIPLE es solo para 3 o más" in notas
    assert "PAGO TOTAL: la salida OCTUBRE 23 AL 26" in notas
    assert "OCTUBRE 30" not in notas      # faltan 9 días: anticipo normal
    nov = tarifario.consultar(LLM_CONFIG, mes="noviembre", hoy=date(2026, 10, 21))
    assert "PAGO TOTAL" not in llm_engine._notas_de_precios(nov)


@pytest.mark.parametrize("cfg", [LLM_CONFIG, LLM_CONFIG_B, LLM_CONFIG_C], ids=["bot1", "bot2", "bot3"])
def test_las_reglas_de_la_agencia_llegan_a_los_tres(cfg):
    bloque = llm_engine._bloque_reglas_agencia(dict(cfg))
    for frase in ("solo para 3 o más personas", "Solo desde Medellín", "no pases a un asesor",
                  "PAGO", "listo_para_reservar", "Islas de San Bernardo"):
        assert frase in bloque, frase
    assert "$" not in bloque


@pytest.mark.parametrize("texto,viola", [
    ("En noviembre las salidas publicadas son hasta el 30.", True),
    ("Esa fecha no la tenemos, lo siento.", True),
    ("No tenemos salida publicada para esas fechas.", True),
    ("La del 30 de noviembre al 3 de diciembre está en $459.000.", False),
])
def test_salida_negada_sin_consultar(texto, viola):
    cfg = dict(LLM_CONFIG)
    assert llm_engine._viola_salida_negada(cfg, [texto], []) is viola
    consultada = [{"tool": "consultar_tarifario", "input": {"fecha": "2026-11-30"}}]
    assert llm_engine._viola_salida_negada(cfg, [texto], consultada) is False


# ---------------------------------------------------------------------------
# Notas de voz
# ---------------------------------------------------------------------------

def test_la_nota_de_voz_llega_transcrita(db, modelo, monkeypatch):
    guion, vistos = modelo
    guion.append(_resp({"type": "text", "text": "¡Claro! ¿Para cuántas personas? 😊"}))
    monkeypatch.setattr(transcripcion, "habilitada", lambda: True)
    monkeypatch.setattr(adjuntos, "_bucket", lambda: "bucket-de-prueba")
    pedidos = []
    monkeypatch.setattr(transcripcion, "transcribir",
                        lambda uri, formato, **k: pedidos.append((uri, formato)) or "Hola, ¿cuánto vale el simulacro?")
    ag = crear_agencia(db, sufijo="NV1", cfg=json.loads(json.dumps(LLM_CONFIG)))
    conv = conversacion(db, ag["team"])
    crud.add_message(db, conv, direction="inbound", status="received", message_type="audio",
                     content=f"[nota de voz]\nhttps://api.ejemplo.test/mensajes/adjunto/{ag['team'].id}/"
                             "0123456789abcdef0123456789abcdef/nota-de-voz.ogg")
    sesion = bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                                 user_input=None, meta_account=None)
    bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=sesion,
                        user_input="[nota de voz]", meta_account=None)
    assert pedidos == [(f"s3://bucket-de-prueba/adjuntos/{ag['team'].id}/"
                        "0123456789abcdef0123456789abcdef/nota-de-voz.ogg", "ogg")]
    assert "🎤 (nota de voz): Hola, ¿cuánto vale el simulacro?" in vistos[-1]
    notas = [m.content for m in _mensajes(db, conv) if m.message_type == "nota_interna"]
    assert any("Transcripción de la nota de voz" in n for n in notas)


def test_sin_transcripcion_sigue_como_siempre(db, modelo, monkeypatch):
    guion, vistos = modelo
    guion.append(_resp({"type": "text", "text": "No puedo escuchar audios 😊"}))
    monkeypatch.setattr(transcripcion, "habilitada", lambda: True)
    monkeypatch.setattr(adjuntos, "_bucket", lambda: "bucket-de-prueba")
    monkeypatch.setattr(transcripcion, "transcribir", lambda *a, **k: None)
    ag = crear_agencia(db, sufijo="NV2", cfg=json.loads(json.dumps(LLM_CONFIG)))
    conv = conversacion(db, ag["team"])
    crud.add_message(db, conv, direction="inbound", status="received", message_type="audio",
                     content=f"[nota de voz]\nhttps://api.ejemplo.test/mensajes/adjunto/{ag['team'].id}/"
                             "0123456789abcdef0123456789abcdef/nota-de-voz.ogg")
    bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                        user_input="[nota de voz]", meta_account=None)
    assert "[nota de voz]" in vistos[-1] and "🎤" not in vistos[-1]


def test_apagada_no_llama_a_transcribe(db, modelo, monkeypatch):
    guion, _ = modelo
    guion.append(_resp({"type": "text", "text": "No puedo escuchar audios 😊"}))
    monkeypatch.setattr(transcripcion, "habilitada", lambda: False)
    monkeypatch.setattr(transcripcion, "transcribir",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía llamarse")))
    ag = crear_agencia(db, sufijo="NV3", cfg=json.loads(json.dumps(LLM_CONFIG)))
    conv = conversacion(db, ag["team"])
    bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                        user_input="[nota de voz]", meta_account=None)


@pytest.mark.parametrize("cfg,sufijo", [(LLM_CONFIG_B, "CS2"), (LLM_CONFIG_C, "CS3")], ids=["bot2", "bot3"])
def test_si_el_modelo_no_escribe_el_sistema_pone_el_cierre(db, modelo, cfg, sufijo, monkeypatch):
    """QA 2026-10-21: el modelo llamaba la herramienta sin texto y salía el aviso
    genérico (y fuera de horario, el de ausencia pidiendo otra vez los datos)."""
    guion, _ = modelo
    monkeypatch.setattr(llm_engine, "_horario", lambda cfg: (False, "mañana a partir de las 8:00 a.m."))
    guion.extend([
        _resp({"type": "tool_use", "id": "t1", "name": "listo_para_reservar",
               "input": {"resumen": "Simulacro, 2 adultos, doble", "datos": DATOS}}),
        _resp({"type": "text", "text": ""}),
    ])
    ag = crear_agencia(db, sufijo=sufijo, cfg=json.loads(json.dumps(cfg)))
    conv = conversacion(db, ag["team"])
    bot_runner.run_turn(db, bot=ag["bot"], conversation=conv, session=None,
                        user_input=DATOS, meta_account=None)
    salientes = [m.content for m in _mensajes(db, conv)
                 if m.direction == "outbound" and m.message_type != "nota_interna"]
    texto = " ".join(salientes)
    assert "comprobante" in texto and "recibí tus datos" in texto
    assert "Te paso con un compañero" not in texto
    assert "*nombre completo* y *cédula*" not in texto      # no repide los datos
    db.refresh(conv)
    assert conv.etiqueta == llm_engine.ETIQUETA_LISTO_PARA_RESERVAR
