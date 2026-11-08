"""Sprint 36 · release 2 — recordatorios que leen la conversación y ventana de 24 h.

Pedido del CEO (7-nov-2026) para los bots 1, 2 y 3 de Arranquemos Pues:

  * El recordatorio no se disculpa por una respuesta que nadie quedó debiendo
    («Te quedé debiendo la respuesta»), no vuelve a preguntar lo que la persona
    ya dijo (personas, mes, hotel) y no reutiliza los números del menú anterior
    con otro significado (`recordatorios_contexto.ajustar_a_la_conversacion`).
  * Diseño de seguridad 2.7: solo sale dentro de las 24 h desde el último
    mensaje del cliente, con 10 min de margen. Si el horario de silencio
    (23–05 h) lo corre fuera de la ventana, no sale y la cadena va directo al
    abandono (los que siguen caerían todavía más tarde). `_programar` hace el
    mismo chequeo al agendar.

Datos inventados (regla #8). Nunca llama a Bedrock.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest

from app import models
from app.services import bot_runner, recordatorios_contexto as rc, silencio

from .variante_b.test_interesados_andamiaje import (  # noqa: F401  (fixtures)
    Sesion,
    conversacion,
    crear_agencia,
    db,
    mensaje,
)

MENU_HOTELES = "¿Cuál te gusta más? 👇\n1️⃣ Piedra Mar\n2️⃣ Bohíos"
MENU_OTRO = "¿Seguimos? 👇\n1️⃣ Sí, quiero reservar ✅\n2️⃣ Prefiero otro mes"


def utc(local: str) -> datetime:
    """'2026-11-10 04:30' en Colombia → UTC sin marcar."""
    return datetime.fromisoformat(local) + timedelta(hours=5)


def _consulta(db, ag, conv, **entrada):
    db.add(models.BotLlmDecision(
        bot_id=ag["bot"].id, conversation_id=conv.id, source="whatsapp", camino="precios",
        tools_called=json.dumps([{"tool": "consultar_tarifario", "input": entrada,
                                  "resultado": "…"}]),
    ))
    db.commit()


# ---------------------------------------------------------------------------
# ajustar_a_la_conversacion
# ---------------------------------------------------------------------------

class TestLeeLaConversacion:
    def test_sin_la_disculpa(self, db):
        ag = crear_agencia(db, sufijo="R1")
        conv = conversacion(db, ag["team"])
        texto = ("¡Hola de nuevo! 👋 Te quedé debiendo la respuesta por acá. "
                 "¿Seguimos con tu plan a Coveñas? 🌴 Cuando quieras me cuentas 🙌")
        nuevo, motivo = rc.ajustar_a_la_conversacion(
            db, conversation=conv, texto=texto, posicion=1, total=3)
        assert "debiend" not in nuevo.lower()
        assert "Seguimos con tu plan" in nuevo
        assert motivo == "deuda"

    def test_solo_la_disculpa_queda_el_neutro(self, db):
        ag = crear_agencia(db, sufijo="R2")
        conv = conversacion(db, ag["team"])
        nuevo, _ = rc.ajustar_a_la_conversacion(
            db, conversation=conv, texto="Te quedé debiendo la respuesta 🙏", posicion=1, total=3)
        assert nuevo == rc.NEUTRO_MEDIO

    def test_no_repregunta_cuantos_viajan(self, db):
        ag = crear_agencia(db, sufijo="R3")
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "inbound", "somos 2 adultos", datetime.utcnow() - timedelta(hours=1))
        nuevo, motivo = rc.ajustar_a_la_conversacion(
            db, conversation=conv, posicion=0, total=3,
            texto="¿Cuántas personas viajarían? 😊 Así te doy el total")
        assert "cuántas" not in nuevo.lower()
        assert motivo == "repregunta:personas"

    def test_no_repregunta_el_mes_que_ya_consulto(self, db):
        ag = crear_agencia(db, sufijo="R4")
        conv = conversacion(db, ag["team"])
        _consulta(db, ag, conv, mes="diciembre", hotel="Piedra Mar")
        nuevo, motivo = rc.ajustar_a_la_conversacion(
            db, conversation=conv, posicion=1, total=3,
            texto="¡Hola de nuevo! 👋 ¿Para qué mes lo estás pensando? 🌴")
        assert "qué mes" not in nuevo.lower()
        assert motivo.startswith("repregunta:") and "mes" in motivo

    def test_el_numero_del_menu_cuenta_como_respuesta(self, db):
        ag = crear_agencia(db, sufijo="R5")
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "outbound", "¿Cuántos viajan? 👇\n1️⃣ 1 persona\n2️⃣ 2 personas",
                datetime.utcnow() - timedelta(hours=2))
        mensaje(db, conv, "inbound", "2", datetime.utcnow() - timedelta(hours=1))
        _, motivo = rc.ajustar_a_la_conversacion(
            db, conversation=conv, posicion=1, total=3,
            texto="¿Cuántas personas viajarían? 😊")
        assert motivo == "repregunta:personas"

    def test_no_reusa_los_numeros_del_menu_anterior(self, db):
        ag = crear_agencia(db, sufijo="R6")
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "outbound", MENU_HOTELES, datetime.utcnow() - timedelta(hours=2))
        nuevo, motivo = rc.ajustar_a_la_conversacion(
            db, conversation=conv, texto=MENU_OTRO, posicion=0, total=3)
        assert motivo == "menu"
        assert "Prefiero otro mes" not in nuevo
        # Repite el menú de antes tal cual: el «2» sigue siendo Bohíos.
        assert "1️⃣ Piedra Mar" in nuevo and "2️⃣ Bohíos" in nuevo

    def test_el_mismo_menu_no_es_conflicto(self, db):
        ag = crear_agencia(db, sufijo="R7")
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "outbound", MENU_HOTELES, datetime.utcnow() - timedelta(hours=2))
        texto = "¡Hola de nuevo! 👋 ¿Te animas? 👇\n1️⃣ Piedra Mar\n2️⃣ Bohíos"
        nuevo, motivo = rc.ajustar_a_la_conversacion(
            db, conversation=conv, texto=texto, posicion=1, total=3)
        assert (nuevo, motivo) == (texto, "")

    def test_las_notas_internas_no_son_el_menu_anterior(self, db):
        ag = crear_agencia(db, sufijo="R8")
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "outbound", MENU_HOTELES, datetime.utcnow() - timedelta(hours=2))
        mensaje(db, conv, "outbound", "🕒 nota\n1️⃣ otra cosa\n2️⃣ y otra",
                datetime.utcnow() - timedelta(hours=1), tipo="nota_interna")
        nuevo, motivo = rc.ajustar_a_la_conversacion(
            db, conversation=conv, texto=MENU_OTRO, posicion=0, total=3)
        assert motivo == "menu" and "2️⃣ Bohíos" in nuevo

    def test_sin_nada_que_ajustar_no_cambia(self, db):
        ag = crear_agencia(db, sufijo="R9")
        conv = conversacion(db, ag["team"])
        texto = "Última razón por hoy 🌴 Si más adelante quieres retomar el plan, aquí estoy"
        assert rc.ajustar_a_la_conversacion(
            db, conversation=conv, texto=texto, posicion=2, total=3) == (texto, "")

    @pytest.mark.parametrize("posicion", [0, 1, 2])
    def test_los_neutros_no_preguntan_ni_numeran(self, posicion):
        texto = rc._neutro(posicion, 3, "")
        assert rc.preguntas_de(texto) == set()
        assert not rc._lineas_de_opciones(texto)
        assert not rc.tiene_deuda(texto)

    def test_los_textos_fijos_del_bot_1_no_se_disculpan(self):
        from app.data.bot_viajes import LLM_CONFIG

        for etapa in LLM_CONFIG["seguimiento"]["recordatorios"]:
            assert not rc.tiene_deuda(etapa["texto"])


# ---------------------------------------------------------------------------
# Por el tick: el texto que sale de verdad
# ---------------------------------------------------------------------------

def _sesion(db, ag, conv):
    s = models.BotSession(bot_id=ag["bot"].id, conversation_id=conv.id,
                          status=models.BOT_SESSION_WAITING, state='{"history": []}')
    db.add(s)
    db.commit()
    return s


def _pendiente(db, sesion, etapa: int, *, creada: datetime, vence: datetime):
    pa = models.BotPendingAction(
        session_id=sesion.id, scheduled_at=vence, created_at=creada,
        action_type=models.BOT_PENDING_ACTION_SEGUIMIENTO,
        payload=json.dumps({"etapa": etapa}), status=models.BOT_PENDING_STATUS_PENDING,
    )
    db.add(pa)
    db.commit()
    return pa


@pytest.fixture
def envios(monkeypatch):
    salieron: list = []
    monkeypatch.setattr(bot_runner, "_send_text", lambda db, conv, bot, acc, texto: salieron.append(texto))
    return salieron


def _pendientes(db, sesion):
    return (db.query(models.BotPendingAction)
            .filter_by(session_id=sesion.id, status=models.BOT_PENDING_STATUS_PENDING).all())


def test_el_recordatorio_que_sale_no_repregunta(db, envios, monkeypatch):
    """Integración: la cadena real del bot 1 con un 2.º recordatorio que
    preguntaba por las personas a quien ya dijo «somos 2»."""
    from app.data.bot_viajes import LLM_CONFIG

    cfg = json.loads(json.dumps(LLM_CONFIG))
    cfg["seguimiento"]["recordatorios"][1]["texto"] = (
        "Te quedé debiendo la respuesta 🙏 ¿Cuántas personas viajarían?")
    ag = crear_agencia(db, sufijo="RT1", cfg=cfg)
    conv = conversacion(db, ag["team"])
    hace = datetime.utcnow() - timedelta(hours=5, minutes=1)
    mensaje(db, conv, "inbound", "somos 2", hace)
    s = _sesion(db, ag, conv)
    pa = _pendiente(db, s, 1, creada=hace + timedelta(minutes=1),
                    vence=datetime.utcnow() - timedelta(minutes=1))
    monkeypatch.setattr(silencio, "ahora", lambda: datetime.utcnow())

    bot_runner.process_pending_action(db, pa)

    assert len(envios) == 1
    assert "debiend" not in envios[0].lower() and "cuántas" not in envios[0].lower()


# ---------------------------------------------------------------------------
# Ventana de 24 h (diseño 2.7)
# ---------------------------------------------------------------------------

class TestVentanaDe24Horas:
    def _armar(self, db, sufijo, entrante: datetime, etapa: int, vence: datetime):
        ag = crear_agencia(db, sufijo=sufijo)
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "inbound", "info del plan", entrante)
        s = _sesion(db, ag, conv)
        pa = _pendiente(db, s, etapa, creada=entrante + timedelta(minutes=1), vence=vence)
        return ag, conv, s, pa

    def test_dentro_de_la_ventana_sale(self, db, envios, monkeypatch):
        entrante = utc("2026-11-10 10:00")
        ag, conv, s, pa = self._armar(db, "V1", entrante, 2, entrante + timedelta(hours=23))
        ahora = entrante + timedelta(hours=23, minutes=49)
        monkeypatch.setattr(silencio, "ahora", lambda: ahora)
        bot_runner.process_pending_action(db, pa)
        db.refresh(conv)
        assert len(envios) == 1
        assert conv.assigned_to == "bot" and conv.abandono_at is None
        # El último agenda el abandono.
        assert [p.action_type for p in _pendientes(db, s)] == [models.BOT_PENDING_ACTION_ABANDONO]

    def test_a_10_minutos_del_cierre_ya_no_sale_y_va_al_abandono(self, db, envios, monkeypatch):
        entrante = utc("2026-11-10 10:00")
        ag, conv, s, pa = self._armar(db, "V2", entrante, 2, entrante + timedelta(hours=23))
        ahora = entrante + timedelta(hours=23, minutes=50)
        monkeypatch.setattr(silencio, "ahora", lambda: ahora)
        bot_runner.process_pending_action(db, pa)
        db.refresh(conv)
        db.refresh(pa)
        assert envios == []
        assert pa.status == models.BOT_PENDING_STATUS_DONE
        assert conv.etiqueta == "conversación abandonada"
        assert conv.abandono_at is not None and conv.reclamos_abandono == 0
        assert conv.assigned_to in ("Camila", "Julián") and conv.status == "pending"
        assert _pendientes(db, s) == []

    def test_un_recordatorio_intermedio_fuera_salta_el_resto(self, db, envios, monkeypatch):
        """El tick atrasado (o el silencio) dejó el 2.º fuera: el 3.º caería
        aún más tarde, así que no se agenda; va directo al abandono."""
        entrante = utc("2026-11-10 10:00")
        ag, conv, s, pa = self._armar(db, "V3", entrante, 1, entrante + timedelta(hours=5))
        monkeypatch.setattr(silencio, "ahora", lambda: entrante + timedelta(hours=24, minutes=5))
        bot_runner.process_pending_action(db, pa)
        db.refresh(conv)
        assert envios == []
        assert conv.etiqueta == "conversación abandonada"
        assert _pendientes(db, s) == []

    def test_el_silencio_lo_corre_fuera_de_la_ventana(self, db, envios, monkeypatch):
        """Escribió a las 4:30 a.m.; el 3.º (23 h) vence a las 3:30 a.m. del día
        siguiente, el silencio lo correría a las 5:00 a.m. = 24 h 30 min: no
        sale y la conversación pasa al abandono."""
        monkeypatch.setattr(silencio, "ACTIVO", True)
        entrante = utc("2026-11-10 04:30")
        ag, conv, s, pa = self._armar(db, "V4", entrante, 2, utc("2026-11-11 03:30"))
        monkeypatch.setattr(silencio, "ahora", lambda: utc("2026-11-11 03:31"))
        bot_runner.process_pending_action(db, pa)
        db.refresh(conv)
        db.refresh(pa)
        assert envios == []
        assert pa.status == models.BOT_PENDING_STATUS_DONE
        assert conv.etiqueta == "conversación abandonada"

    def test_el_silencio_que_cae_dentro_solo_lo_corre(self, db, envios, monkeypatch):
        monkeypatch.setattr(silencio, "ACTIVO", True)
        entrante = utc("2026-11-10 21:00")
        ag, conv, s, pa = self._armar(db, "V5", entrante, 1, utc("2026-11-11 02:00"))
        monkeypatch.setattr(silencio, "ahora", lambda: utc("2026-11-11 02:01"))
        bot_runner.process_pending_action(db, pa)
        db.refresh(pa)
        db.refresh(conv)
        assert envios == []
        assert pa.status == models.BOT_PENDING_STATUS_PENDING
        assert pa.scheduled_at == utc("2026-11-11 05:00")
        assert conv.abandono_at is None

    def test_al_agendar_fuera_de_la_ventana_queda_en_el_borde(self, db, monkeypatch):
        monkeypatch.setattr(silencio, "ACTIVO", True)
        entrante = utc("2026-11-10 04:30")
        ag = crear_agencia(db, sufijo="V6")
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "inbound", "info del plan", entrante)
        s = _sesion(db, ag, conv)
        reloj = utc("2026-11-10 09:30")       # cinco horas después
        monkeypatch.setattr(silencio, "ahora", lambda: reloj)
        monkeypatch.setattr(bot_runner, "datetime",
                            type("dt", (), {"utcnow": staticmethod(lambda: reloj)}))
        # 3.º a las 23 h del silencio (18 h después de ahora): 3:30 a.m. → 5:00 a.m.,
        # fuera de la ventana; se agenda en el borde (24 h − 10 min).
        pa = bot_runner._programar(db, s, models.BOT_PENDING_ACTION_SEGUIMIENTO, 18 * 60, etapa=2)
        assert pa.scheduled_at == entrante + timedelta(hours=23, minutes=50)

    def test_al_agendar_dentro_de_la_ventana_no_cambia(self, db, monkeypatch):
        entrante = utc("2026-11-10 10:00")
        ag = crear_agencia(db, sufijo="V7")
        conv = conversacion(db, ag["team"])
        mensaje(db, conv, "inbound", "info del plan", entrante)
        s = _sesion(db, ag, conv)
        reloj = entrante + timedelta(minutes=15)
        monkeypatch.setattr(bot_runner, "datetime",
                            type("dt", (), {"utcnow": staticmethod(lambda: reloj)}))
        pa = bot_runner._programar(db, s, models.BOT_PENDING_ACTION_SEGUIMIENTO, 285, etapa=1)
        assert pa.scheduled_at == entrante + timedelta(hours=5)

    def test_cuenta_desde_el_ultimo_entrante(self, db, envios, monkeypatch):
        """Un segundo mensaje del cliente reabre la ventana completa."""
        entrante = utc("2026-11-10 10:00")
        ag, conv, s, pa = self._armar(db, "V8", entrante - timedelta(hours=20), 2,
                                      entrante + timedelta(hours=23))
        mensaje(db, conv, "inbound", "¿y qué incluye?", entrante)
        pa.created_at = entrante + timedelta(minutes=1)
        db.commit()
        monkeypatch.setattr(silencio, "ahora", lambda: entrante + timedelta(hours=23))
        bot_runner.process_pending_action(db, pa)
        assert len(envios) == 1
