"""El abandono real deja agendada la llamada (o no, según lo que alcanzó a recibir).

`test_agendamientos.py` prueba la regla y la pantalla con mensajes puestos a
mano. Acá se prueba lo otro: que el enganche esté de verdad en el camino que
recorre el bot en producción — saludo → silencio → tres recordatorios →
abandono — y no sólo en una función que nadie llama.

Se reusan las piezas de `test_abandono_asignacion.py` (el modelo de mentira, el
team con sus asesores, el bucle que vence los recordatorios) para que el día que
cambie la cadencia del seguimiento no haya dos andamiajes que mantener.
"""
from __future__ import annotations

from datetime import date

from app import models
from app.services import agendamientos as svc

from .test_abandono_asignacion import (  # noqa: F401  (fixtures de pytest)
    ASESORES,
    WA_ID,
    abandonar,
    agencia,
    db_session,
    entra_mensaje,
    hasta_el_abandono,
    modelo,
    _respuesta,
    _texto,
)


def _agendamientos(db) -> list:
    return db.query(models.Agendamiento).all()


def abandonar_habiendo_informado(db, team, modelo_falso, wa_id: str = WA_ID):
    """El caso que sí vale una llamada: preguntó, le contestaron, se fue.

    Es `abandonar()` con un intercambio real en medio — dos entrantes en vez de
    uno — porque el corte del nivel de interés es justamente si la persona
    volvió a escribir después del saludo.
    """
    modelo_falso.guion = [
        _respuesta(_texto("¡Hola! Soy Luisa 😊 ¿Con quién tengo el gusto?")),
        _respuesta(_texto("¡Un gusto! El plan es de viernes a lunes, 3 noches.")),
    ]
    entra_mensaje(db, team, "Hola", wa_id=wa_id)
    conv, _ = entra_mensaje(db, team, "¿cuántas noches son?", wa_id=wa_id)

    pa = hasta_el_abandono(db, conv)
    from app.services import bot_runner

    bot_runner.process_pending_action(db, pa)
    db.refresh(conv)
    return conv


class TestElAbandonoAgendaLaLlamada:
    def test_el_que_recibio_informacion_queda_en_la_lista(
        self, db_session, agencia, modelo
    ):
        team, _ = agencia
        conv = abandonar_habiendo_informado(db_session, team, modelo)

        filas = _agendamientos(db_session)
        assert len(filas) == 1
        ag = filas[0]
        assert ag.conversation_id == conv.id
        assert ag.team_id == team.id
        assert ag.estado == models.AGENDAMIENTO_PENDIENTE
        assert ag.nivel_interes == models.AGENDAMIENTO_NIVEL_CON_INFORMACION
        assert ag.fecha_llamada == svc.fecha_tentativa()

    def test_le_queda_el_asesor_del_turno(self, db_session, agencia, modelo):
        """El mismo nombre que recibió el chat en la bandeja: si la lista dijera
        otro, dos personas creerían que el cliente es suyo."""
        team, _ = agencia
        conv = abandonar_habiendo_informado(db_session, team, modelo)

        ag = _agendamientos(db_session)[0]
        assert ag.asesor == conv.assigned_to
        assert ag.asesor in ASESORES

    def test_el_que_solo_recibio_el_saludo_no_entra(self, db_session, agencia, modelo):
        """Mismo recorrido completo, pero sin que la persona volviera a
        escribir: se etiqueta y se asigna como siempre, y NO se agenda llamada."""
        team, _ = agencia
        conv = abandonar(db_session, team, modelo)

        assert conv.etiqueta == "conversación abandonada"
        assert conv.assigned_to in ASESORES
        assert _agendamientos(db_session) == []

    def test_la_fecha_es_tres_dias_despues_de_hoy(self, db_session, agencia, modelo):
        team, _ = agencia
        abandonar_habiendo_informado(db_session, team, modelo)

        ag = _agendamientos(db_session)[0]
        assert isinstance(ag.fecha_llamada, date)
        assert (ag.fecha_llamada - svc.hoy_en_colombia()).days == 3
