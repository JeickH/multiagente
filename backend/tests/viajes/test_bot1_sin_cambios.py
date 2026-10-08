"""Red de seguridad: el bot 1 de Arranquemos Pues no cambia ni un carácter.

Viene el bot 2 (variante B) con una docena de cambios en `llm_engine.py` y
`bot_runner.py`, todos detrás de flags en su `llm_config`. La promesa es que el
bot 1 (`app/data/bot_viajes.py` + `bot_contexts/demo_viajes.md`, id 12 en
producción) se comporte **exactamente** igual que en el commit `7835c65`. Esta
prueba la hace cumplir comparando contra una foto tomada con ese commit:

  * ~20 conversaciones guionadas contra `llm_engine.advance` con un modelo FALSO
    (sin Bedrock, sin red): el `system` completo que recibe el modelo, las
    herramientas que se le ofrecen (con su esquema), los mensajes de cada
    llamada (ahí están los resultados de las herramientas y las correcciones
    de los guardarraíles), las acciones devueltas, `next_state` y la telemetría
    (sin `latency_ms`, que es reloj de pared).
  * Dos de ellas por la fuente que usa producción (`fuente_datos=productos`,
    con el tarifario cargado como producto en SQLite).
  * 4 cadenas completas `bot_router` → `bot_runner` → `llm_engine` sobre SQLite:
    lo que se le envió al cliente, las notas internas, las acciones agendadas
    (con sus minutos) y los textos de los recordatorios que salen al vencerlas.
  * `recordatorios_de` y tres consultas fijas a `tarifario.consultar`.

El reloj se congela el **2026-10-07 15:00 UTC** (10:00 en Colombia) reemplazando
`datetime`/`date` en los módulos `app.*` y los `default=datetime.utcnow` de las
columnas: freezegun no está en el `.venv` y no se agrega una dependencia para
esto. Teléfonos sintéticos y nombres inventados (regla #8).

Cómo se regenera el fixture
---------------------------
**ADVERTENCIA: regenerarlo es ACEPTAR como correcto el comportamiento actual del
bot 1.** Si esta prueba falla después de tocar el motor, lo primero es leer el
diff: casi siempre es un cambio que se escapó del flag. Solo se regenera cuando
el CEO pidió cambiar el bot 1 a propósito, y el diff del JSON va en el PR.

La foto original se tomó desde un worktree limpio del commit `7835c65` (no del
árbol de trabajo, que ya tenía cambios de otros agentes)::

    git worktree add --detach /tmp/wt_golden 7835c65
    cp backend/tests/viajes/test_bot1_sin_cambios.py /tmp/wt_golden/backend/tests/viajes/
    cd /tmp/wt_golden/backend && source /RUTA/AL/REPO/backend/.venv/bin/activate && \\
        TZ=UTC BOT1_GOLDEN_REGENERAR=1 python -m pytest -q tests/viajes/test_bot1_sin_cambios.py
    cp /tmp/wt_golden/backend/tests/viajes/fixtures/bot1_golden.json \\
        /RUTA/AL/REPO/backend/tests/viajes/fixtures/
    git worktree remove --force /tmp/wt_golden

Para aceptar a propósito el comportamiento del árbol actual::

    cd backend && source .venv/bin/activate && \\
        TZ=UTC BOT1_GOLDEN_REGENERAR=1 python -m pytest -q tests/viajes/test_bot1_sin_cambios.py

Con `BOT1_GOLDEN_REGENERAR=1` la prueba escribe el JSON y se marca como `skip`
(para que nadie la deje puesta en el CI creyendo que pasó).
"""
from __future__ import annotations

import copy
import datetime as _dt
import difflib
import hashlib
import importlib
import json
import os
import pkgutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bot1_golden.json"
REGENERAR = os.getenv("BOT1_GOLDEN_REGENERAR") == "1"

#: El instante congelado: miércoles 7-oct-2026, 10:00 en Colombia. Quedan
#: salidas en octubre, noviembre, diciembre y enero.
AHORA_UTC = _dt.datetime(2026, 10, 7, 15, 0, 0)
HOY_CO = _dt.date(2026, 10, 7)

#: Las llaves de `llm_config` que encienden la variante B (spec compartida,
#: tabla «Flags del bot 2»). Ninguna puede aparecer en la config del bot 1.
FLAGS_BOT2 = (
    "variante",
    "apertura_vitrina",
    "una_pregunta_por_turno",
    "presentacion_una_vez",
    "nombre_una_vez",
    "filtrar_nombres_genericos",
    "no_cerrar_aplazadas",
    "guardarrail_precio",
    "cargos_ninos",
    "promo_inexistente",
    "intencion_compra",
    "recordatorios_con_contexto",
)

#: Teléfonos sintéticos (regla #8).
WA_1 = "573000000101"
WA_2 = "573000000102"
WA_3 = "573000000103"
WA_4 = "573000000104"


# ---------------------------------------------------------------------------
# Reloj congelado (sin freezegun)
# ---------------------------------------------------------------------------

_DT_REAL = _dt.datetime
_DATE_REAL = _dt.date


class _Reloj:
    ahora: _dt.datetime = AHORA_UTC   # UTC sin marcar, como guarda la base

    def avanzar(self, **kw) -> None:
        self.ahora = self.ahora + _dt.timedelta(**kw)


_reloj = _Reloj()


class _MetaDT(type):
    def __instancecheck__(cls, obj):          # isinstance(x, datetime) sigue valiendo
        return isinstance(obj, _DT_REAL)


class _MetaDate(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _DATE_REAL)


class _DTCongelado(_DT_REAL, metaclass=_MetaDT):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return _reloj.ahora               # la suite corre con TZ=UTC
        return _reloj.ahora.replace(tzinfo=_dt.timezone.utc).astimezone(tz)

    @classmethod
    def utcnow(cls):
        return _reloj.ahora

    @classmethod
    def today(cls):
        return _reloj.ahora


class _DateCongelada(_DATE_REAL, metaclass=_MetaDate):
    @classmethod
    def today(cls):
        return _reloj.ahora.date()


def _importar_todo_app() -> None:
    """Importa ya los módulos de `app` para que todos queden congelados.

    Uno que se importara perezosamente a mitad del turno traería el `datetime`
    de verdad y la foto dependería del día en que se corre.
    """
    import app
    import app.services

    for paquete in (app, app.services):
        for info in pkgutil.iter_modules(paquete.__path__, paquete.__name__ + "."):
            try:
                importlib.import_module(info.name)
            except Exception:                  # pragma: no cover - defensivo
                pass


def _congelar(monkeypatch) -> None:
    _reloj.ahora = AHORA_UTC
    _importar_todo_app()
    for nombre, mod in list(sys.modules.items()):
        if mod is None or not (nombre == "app" or nombre.startswith("app.")):
            continue
        if getattr(mod, "datetime", None) is _DT_REAL:
            monkeypatch.setattr(mod, "datetime", _DTCongelado)
        if getattr(mod, "date", None) is _DATE_REAL:
            monkeypatch.setattr(mod, "date", _DateCongelada)

    from app.database import Base

    for tabla in Base.metadata.tables.values():
        for col in tabla.columns:
            for cual in ("default", "onupdate"):
                d = getattr(col, cual, None)
                if d is None or not getattr(d, "is_callable", False):
                    continue
                if getattr(d.arg, "__name__", "") in ("utcnow", "now"):
                    monkeypatch.setattr(d, "arg", lambda ctx: _reloj.ahora)


# ---------------------------------------------------------------------------
# Modelo falso y registro de lo que recibe
# ---------------------------------------------------------------------------

def T(texto: str) -> dict:
    return {"type": "text", "text": texto}


def U(nombre: str, entrada: Optional[dict] = None, ident: str = "tu_1") -> dict:
    return {"type": "tool_use", "id": ident, "name": nombre, "input": entrada or {}}


def R(*bloques, stop: Optional[str] = None) -> dict:
    if stop is None:
        stop = "tool_use" if any(b["type"] == "tool_use" for b in bloques) else "end_turn"
    return {
        "content": list(bloques),
        "stop_reason": stop,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


class _Registro:
    """Prompts y esquemas de herramientas, una sola vez cada uno (por hash)."""

    def __init__(self) -> None:
        self.prompts: Dict[str, str] = {}
        self.herramientas: Dict[str, list] = {}

    def prompt(self, texto: str) -> str:
        clave = "p_" + hashlib.sha256(texto.encode("utf-8")).hexdigest()[:12]
        self.prompts[clave] = texto
        return clave

    def tools(self, tools: list) -> str:
        crudo = json.dumps(tools, ensure_ascii=False, sort_keys=True)
        clave = "t_" + hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:12]
        self.herramientas[clave] = copy.deepcopy(tools)
        return clave


class ModeloFalso:
    def __init__(self, registro: _Registro) -> None:
        self.registro = registro
        self.guion: List[dict] = []
        self.llamadas: List[dict] = []

    def __call__(self, model_id, system, messages, tools):
        self.llamadas.append({
            "model_id": model_id,
            "system": self.registro.prompt(system),
            "herramientas": [t["name"] for t in tools],
            "esquemas": self.registro.tools(tools),
            "messages": copy.deepcopy(list(messages)),
        })
        if not self.guion:
            return R(T("(el guion se quedó sin respuestas)"))
        return copy.deepcopy(self.guion.pop(0))

    def tomar(self) -> List[dict]:
        fuera, self.llamadas = self.llamadas, []
        return fuera


# ---------------------------------------------------------------------------
# Normalización: lo que no es comportamiento sale de la foto
# ---------------------------------------------------------------------------

def _normalizar(obj: Any) -> Any:
    from app.data import bot_viajes

    base = bot_viajes.M
    if isinstance(obj, dict):
        return {str(k): _normalizar(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalizar(v) for v in obj]
    if isinstance(obj, _DT_REAL):
        return obj.isoformat()
    if isinstance(obj, _DATE_REAL):
        return obj.isoformat()
    if isinstance(obj, str) and base:
        return obj.replace(base, "{MEDIA_BASE}")
    return obj


def _telemetria(tel: Optional[dict]) -> Optional[dict]:
    if tel is None:
        return None
    fuera = dict(tel)
    fuera.pop("latency_ms", None)
    return fuera


# ---------------------------------------------------------------------------
# Bots
# ---------------------------------------------------------------------------

class _BotEnMemoria:
    """El bot 1 tal como lo ve el motor, sin base (el `.md` como guion)."""

    engine = "llm"
    status = "active"
    instrucciones = None

    def __init__(self, cfg: Dict[str, Any], *, ident: int = 12,
                 team_id: Optional[int] = None) -> None:
        self.id = ident
        if team_id is not None:
            self.team_id = team_id
        self.llm_config = json.dumps(cfg, ensure_ascii=False)


def _cfg_bot1() -> Dict[str, Any]:
    from app.data.bot_viajes import LLM_CONFIG

    return copy.deepcopy(LLM_CONFIG)


# ---------------------------------------------------------------------------
# Historiales de arranque (texto inventado)
# ---------------------------------------------------------------------------

_SALUDO_PREVIO = (
    "¡Hola! Soy Maria Camila de Arranquemos Pues 🌴 Te cuento del plan a "
    "Coveñas: 3 días y 2 noches con transporte, hotel y tours. ¿Para qué mes "
    "lo estás pensando? 😊"
)

HIST_BASICO = {"history": [
    {"role": "user", "content": "Hola, quiero info del plan a Coveñas"},
    {"role": "assistant", "content": _SALUDO_PREVIO},
]}

HIST_CON_PRECIOS = {"history": [
    {"role": "user", "content": "Hola, quiero info del plan a Coveñas"},
    {"role": "assistant", "content": _SALUDO_PREVIO},
    {"role": "user", "content": "Para diciembre, somos dos"},
    {"role": "assistant", "content": (
        "¡Súper! En diciembre en Amor de Dios hay salidas desde $406.000 por "
        "persona en acomodación doble 🌴 ¿Qué fecha te queda mejor?\n"
        "[enviaste: tarifario_amordios_dic_ene]"
    )},
]}


# ---------------------------------------------------------------------------
# Casos del motor
# ---------------------------------------------------------------------------
#
# Cada turno: entrada del cliente (None = primer turno sin texto), runtime que
# pondría `bot_runner`, y el guion de respuestas del modelo. El estado pasa de
# un turno al siguiente como lo haría `bot_runner`.

def _rt(**kw) -> Dict[str, Any]:
    base = {"bot_id": 12, "source": "whatsapp", "conversation_id": 1,
            "contact_name": None, "retomada": False, "desde": None}
    base.update(kw)
    return base


CASOS_MOTOR: List[Dict[str, Any]] = [
    {
        "nombre": "apertura_sin_texto",
        "descripcion": "Primer turno sin texto (simulador): saludo + flyer.",
        "turnos": [{
            "entrada": None, "runtime": _rt(),
            "guion": [
                R(T("¡Hola! 👋 Soy Maria Camila de Arranquemos Pues 🌴 Te cuento "
                    "del plan a Coveñas. ¿Con quién tengo el gusto? 😊"),
                  U("enviar_media", {"claves": ["info_amordios"]})),
                R(T("¿Para qué mes lo estás pensando? 😊")),
            ],
        }],
    },
    {
        "nombre": "apertura_sin_perfil_whatsapp",
        "descripcion": "Primer mensaje del cliente, sin nombre de perfil; el "
                       "modelo pide el nombre y nombre_al_reservar lo quita.",
        "turnos": [{
            "entrada": "Hola, me interesa el plan a Coveñas", "runtime": _rt(),
            "guion": [
                R(T("¡Hola! Soy Maria Camila de Arranquemos Pues 🌴\n\nEl plan "
                    "incluye transporte, hotel, desayunos y tours.\n\n¿Con quién "
                    "tengo el gusto? 😊")),
            ],
        }],
    },
    {
        "nombre": "apertura_con_perfil_whatsapp",
        "descripcion": "Nombre del perfil de WhatsApp presente (inventado).",
        "turnos": [{
            "entrada": "Buenas tardes, información por favor",
            "runtime": _rt(contact_name="Laura Gomez"),
            "guion": [
                R(T("¡Hola, Laura! Soy Maria Camila de Arranquemos Pues 🌴 ¿Cómo "
                    "te llamas? Te cuento del plan."),
                  U("enviar_media", {"claves": ["info_amordios", "tours"]})),
                R(T("¿Para qué mes lo está pensando? 😊")),
            ],
        }],
    },
    {
        "nombre": "nombre_generico_cliente",
        "descripcion": "Perfil de WhatsApp genérico ('Cliente'): hoy pasa el "
                       "saneado y llega al bloque de continuidad.",
        "turnos": [{
            "entrada": "Hola", "runtime": _rt(contact_name="Cliente"),
            "guion": [R(T("¡Hola, Cliente! Soy Maria Camila 🌴 ¿Para qué mes?"))],
        }],
    },
    {
        "nombre": "nombre_generico_no_proporcionado",
        "descripcion": "Perfil 'No proporcionado' y registrar_nombre con un "
                       "valor inválido y otro válido.",
        "turnos": [{
            "entrada": "Me llamo Andrea, quiero ir en noviembre",
            "runtime": _rt(contact_name="No proporcionado"),
            "guion": [
                R(U("registrar_nombre", {"nombre": "Cliente 12345"}, "tu_a"),
                  U("registrar_nombre", {"nombre": "Andrea"}, "tu_b")),
                R(T("¡Mucho gusto, Andrea! 😊 Ya te consulto noviembre.")),
            ],
        }],
    },
    {
        "nombre": "precio_sin_mes",
        "descripcion": "Pregunta el precio sin mes: el tarifario pide el mes.",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "¿Cuánto cuesta el plan?", "runtime": _rt(),
            "guion": [
                R(U("consultar_tarifario", {})),
                R(T("¡Claro! Los precios cambian según el mes 🌴 ¿Para qué mes "
                    "lo estás pensando?")),
            ],
        }],
    },
    {
        "nombre": "precio_con_mes_y_hotel",
        "descripcion": "Diciembre en Amor de Dios: tarifario + flyer del mes.",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "Cuánto vale para diciembre en Amor de Dios? somos 2",
            "runtime": _rt(),
            "guion": [
                R(U("consultar_tarifario", {"mes": "diciembre", "hotel": "Amor de Dios"})),
                R(T("En diciembre en Amor de Dios tienes salidas desde *$406.000* "
                    "por persona en doble 🌴 Te dejo el tarifario 👇"),
                  U("enviar_media", {"claves": ["tarifario_amordios_dic_ene"]}, "tu_2")),
                R(T("¿Qué fecha te queda mejor? 😊")),
            ],
        }],
    },
    {
        "nombre": "precio_comparacion_sin_hotel",
        "descripcion": "Noviembre sin hotel: comparación de los dos tarifarios.",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "y en noviembre qué precios hay?", "runtime": _rt(),
            "guion": [
                R(U("consultar_tarifario", {"mes": "noviembre"})),
                R(T("En noviembre: Amor de Dios desde $505.000 y Piedra Mar desde "
                    "$516.000 por persona en doble 🌴 ¿Cuál te llama más?")),
            ],
        }],
    },
    {
        "nombre": "precio_por_presupuesto",
        "descripcion": "Presupuesto por persona sin mes.",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "tengo como 400 mil por persona, qué me sale?",
            "runtime": _rt(),
            "guion": [
                R(U("consultar_tarifario", {"presupuesto": "400 mil"})),
                R(T("Con $400.000 te sirve la salida entre semana de diciembre 🌴")),
            ],
        }],
    },
    {
        "nombre": "duracion_inventada_corregida",
        "descripcion": "El modelo dice una duración sin consultar: el "
                       "guardarraíl de duración corrige y se reintenta.",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "cuántos días es el plan del 8 de diciembre?",
            "runtime": _rt(),
            "guion": [
                R(T("Ese plan es de 5 días y 4 noches 🌴")),
                R(U("consultar_tarifario", {"mes": "diciembre", "fecha": "2026-12-08"})),
                R(T("La salida del 8 al 11 de diciembre es de 2 noches / 3 días 🌴")),
            ],
        }],
    },
    {
        "nombre": "disponibilidad_sin_consultar",
        "descripcion": "Afirma cupo sin consultar: guardarraíl de disponibilidad.",
        "estado_inicial": HIST_CON_PRECIOS,
        "turnos": [{
            "entrada": "hay cupo para el 18 de diciembre?", "runtime": _rt(),
            "guion": [
                R(T("¡Sí, claro! Para el 18 de diciembre sí hay disponibilidad 🌴")),
                R(T("Déjame confirmarlo con una asesora 🙏"),
                  U("escalar_a_asesor", {"motivo": "pregunta por cupo",
                                         "resumen": "2 personas, 18 de diciembre"})),
            ],
        }],
    },
    {
        "nombre": "flyer_y_medios",
        "descripcion": "Pide video e info de Piedra Mar; una clave no existe.",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "me mandas el video del hotel Piedra Mar y la info?",
            "runtime": _rt(),
            "guion": [
                R(T("¡Claro que sí! 👇"),
                  U("enviar_media", {"claves": ["video_piedramar", "info_piedramar",
                                                "flyer_que_no_existe"]})),
                R(T("¿Te gustaría ver también los tours? 🌴")),
            ],
        }],
    },
    {
        "nombre": "anticipo_y_reemplazos",
        "descripcion": "Pregunta del anticipo; el modelo escribe 'seña' y voseo, "
                       "que los reemplazos del tenant corrigen.",
        "estado_inicial": HIST_CON_PRECIOS,
        "turnos": [{
            "entrada": "¿cuánto hay que dar de anticipo para separar?",
            "runtime": _rt(),
            "guion": [
                R(T("Para apartar el cupo pagás una seña del 30% y el resto lo "
                    "querés pagar antes del viaje 😊 ¿Vos tenés la fecha?"),
                  U("enviar_media", {"claves": ["medios_pago"]})),
                R(T("¿Te mando el formulario de reserva?")),
            ],
        }],
    },
    {
        "nombre": "reserva_formulario",
        "descripcion": "Quiere reservar: pide nombre completo y cédula (el "
                       "recorte del nombre no debe tocarlo).",
        "estado_inicial": HIST_CON_PRECIOS,
        "turnos": [{
            "entrada": "listo, quiero reservar para el 18", "runtime": _rt(),
            "guion": [
                R(T("¡Qué alegría! 🎉 Para apartar tu cupo regálame el nombre "
                    "completo y la cédula de cada viajero."),
                  U("enviar_media", {"claves": ["formulario_reserva", "medios_pago"]})),
                R(T("¿Me confirmas cuántos viajan? 😊")),
            ],
        }],
    },
    {
        "nombre": "mencion_350000",
        "descripcion": "Menciona la promo de $350.000 (bot 1 no la escala solo).",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "vi en el flyer que de lunes a jueves es desde $350.000, "
                       "es así?",
            "runtime": _rt(),
            "guion": [
                R(U("consultar_tarifario", {"mes": "diciembre"})),
                R(T("¿De dónde sacaste ese valor? 🤔 En diciembre la salida entre "
                    "semana en Amor de Dios es desde $406.000 por persona.")),
            ],
        }],
    },
    {
        "nombre": "esposo_no_responder",
        "descripcion": "«Lo consulto con mi esposo» y el modelo llama "
                       "no_responder escribiendo además texto (se descarta).",
        "estado_inicial": HIST_CON_PRECIOS,
        "turnos": [{
            "entrada": "listo, lo consulto con mi esposo y te aviso",
            "runtime": _rt(),
            "guion": [
                R(T("¡Con gusto! Quedo atenta 🤗"), U("no_responder", {})),
            ],
        }],
    },
    {
        "nombre": "esposo_finalizar",
        "descripcion": "«Lo consulto con mi esposo» y el modelo se despide con "
                       "finalizar_conversacion.",
        "estado_inicial": HIST_CON_PRECIOS,
        "turnos": [{
            "entrada": "déjame lo hablo con mi esposo y te confirmo",
            "runtime": _rt(),
            "guion": [
                R(T("¡Claro que sí! Aquí estaré cuando lo decidan 🌴"),
                  U("finalizar_conversacion", {})),
            ],
        }],
    },
    {
        "nombre": "resaludo_sesion_retomada",
        "descripcion": "Vuelve dentro de la ventana `retomar`: bloque de "
                       "continuidad y la presentación se recorta.",
        "estado_inicial": HIST_CON_PRECIOS,
        "turnos": [{
            "entrada": "hola de nuevo, ya hablé con mi esposo",
            "runtime": _rt(retomada=True, desde="hace 3 horas",
                           contact_name="Marta Ruiz"),
            "guion": [
                R(T("¡Hola de nuevo! Soy Maria Camila de Arranquemos Pues 🌴\n\n"
                    "¡Qué bueno! ¿Qué decidieron? 😊")),
            ],
        }],
    },
    {
        "nombre": "resaludo_sesion_nueva",
        "descripcion": "Sesión nueva fuera de la ventana: historial vacío pero "
                       "nombre conocido por el perfil.",
        "turnos": [{
            "entrada": "Hola buenas",
            "runtime": _rt(contact_name="Marta Ruiz"),
            "guion": [
                R(T("¡Hola, Marta! Soy Maria Camila de Arranquemos Pues 🌴 "
                    "¿Con quién tengo el gusto? ¿Para qué mes lo estás pensando?")),
            ],
        }],
    },
    {
        "nombre": "handoff_asesor",
        "descripcion": "Pide hablar con una persona: aviso + escalar_a_asesor.",
        "estado_inicial": HIST_CON_PRECIOS,
        "turnos": [{
            "entrada": "prefiero hablar con una asesora por favor", "runtime": _rt(),
            "guion": [
                R(T("¡Claro! Te comunico con una asesora 🙌"),
                  U("escalar_a_asesor", {"motivo": "pide asesora",
                                         "resumen": "diciembre, 2 personas"})),
            ],
        }],
    },
    {
        "nombre": "nota_de_voz_y_multipregunta",
        "descripcion": "Nota de voz; luego un turno con varias preguntas y "
                       "medios después de la pregunta (bot 1 lo deja igual).",
        "estado_inicial": HIST_BASICO,
        "turnos": [
            {
                "entrada": "[nota de voz]", "runtime": _rt(),
                "guion": [R(T("¡Hola! 😊 De momento no puedo escuchar las notas "
                              "de voz. ¿Me lo escribes por aquí?"))],
            },
            {
                "entrada": "es para enero, qué incluye?", "runtime": _rt(),
                "guion": [
                    R(T("Incluye transporte, hotel y tours 🌴 ¿Cuántas personas "
                        "viajan? ¿Ya tienes fecha?"),
                      U("enviar_media", {"claves": ["tours", "tour_video"]})),
                    R(T("¿Te mando también el tarifario de enero?")),
                ],
            },
        ],
    },
]

#: Casos por la fuente de producción (`fuente_datos=productos`).
CASOS_PRODUCTOS: List[Dict[str, Any]] = [
    {
        "nombre": "productos_apertura",
        "descripcion": "Primer mensaje con el catálogo de la base.",
        "turnos": [{
            "entrada": "Hola, info del plan", "runtime": _rt(),
            "guion": [R(T("¡Hola! Soy Maria Camila de Arranquemos Pues 🌴 ¿Para "
                          "qué mes lo estás pensando? 😊"))],
        }],
    },
    {
        "nombre": "productos_precio_con_mes",
        "descripcion": "consultar_precios para diciembre en Piedra Mar.",
        "estado_inicial": HIST_BASICO,
        "turnos": [{
            "entrada": "precio para diciembre en Piedra Mar", "runtime": _rt(),
            "guion": [
                R(U("consultar_precios", {"producto": "Plan Coveñas",
                                          "variante": "Piedra Mar",
                                          "mes": "diciembre"})),
                R(T("En diciembre en Piedra Mar desde $428.000 por persona 🌴"),
                  U("enviar_media", {"claves": ["tarifario_piedramar_nov_ene"]}, "tu_2")),
                R(T("¿Qué fecha te sirve?")),
            ],
        }],
    },
]


def _correr_caso(caso: Dict[str, Any], bot, modelo: ModeloFalso) -> Dict[str, Any]:
    from app.services import llm_engine

    estado = copy.deepcopy(caso.get("estado_inicial"))
    turnos = []
    for turno in caso["turnos"]:
        modelo.guion = copy.deepcopy(turno["guion"])
        resultado = llm_engine.advance(
            bot, copy.deepcopy(estado), turno["entrada"],
            runtime=copy.deepcopy(turno["runtime"]),
        )
        turnos.append({
            "entrada": turno["entrada"],
            "runtime": turno["runtime"],
            "llamadas_al_modelo": modelo.tomar(),
            "guion_sobrante": len(modelo.guion),
            "acciones": resultado["actions"],
            "finished": resultado["finished"],
            "next_state": resultado["next_state"],
            "telemetria": _telemetria(resultado.get("telemetry")),
        })
        estado = resultado["next_state"]
    return {"descripcion": caso["descripcion"], "turnos": turnos}


# ---------------------------------------------------------------------------
# Base SQLite para la cadena completa y la fuente `productos`
# ---------------------------------------------------------------------------

def _base():
    from app.database import Base

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _foto_productos(monkeypatch, modelo: ModeloFalso) -> Dict[str, Any]:
    from app.services import llm_engine, productos
    from tests.productos import covenas
    from tests.productos.conftest import crear_cuenta

    engine, Sesion = _base()
    db = Sesion()
    try:
        team_id, bot_id = crear_cuenta(db, "golden")
        covenas.cargar(db, team_id=team_id, bot_id=bot_id)
        monkeypatch.setattr(llm_engine, "_productos_db", Sesion)
        cfg = _cfg_bot1()
        cfg["fuente_datos"] = "productos"
        bot = _BotEnMemoria(cfg, ident=bot_id, team_id=team_id)
        productos.limpiar_cache()
        fuera = {}
        for caso in CASOS_PRODUCTOS:
            fuera[caso["nombre"]] = _correr_caso(caso, bot, modelo)
        return fuera
    finally:
        productos.limpiar_cache()
        db.close()
        engine.dispose()


# ---------------------------------------------------------------------------
# Cadena completa: bot_router → bot_runner → llm_engine
# ---------------------------------------------------------------------------

class _Cadena:
    def __init__(self, db, modelo: ModeloFalso) -> None:
        from app import crud, models

        self.db = db
        self.modelo = modelo
        owner = models.User(
            nombre="Agencia Golden", tipo_documento="CC", documento="GOLD0001",
            correo="agencia.golden@example.com",
            hashed_password="sin-clave-no-se-autentica-en-estas-pruebas",
        )
        db.add(owner)
        db.flush()
        self.team = models.Team(nombre="Agencia Golden", owner_user_id=owner.id)
        db.add(self.team)
        db.flush()
        self.bot = models.Bot(
            user_id=owner.id, team_id=self.team.id, name="Maria Camila",
            engine="llm", status="active",
            trigger_type=models.BOT_TRIGGER_DEFAULT,
            llm_config=json.dumps(_cfg_bot1(), ensure_ascii=False),
        )
        db.add(self.bot)
        db.commit()
        self.crud = crud
        self.models = models
        self.pasos: List[Dict[str, Any]] = []

    # -- lo que pasa -------------------------------------------------------

    def entra(self, wa_id: str, texto: str, guion: List[dict],
              perfil: Optional[str] = None) -> None:
        from app.services import bot_router, bot_runner

        db, crud = self.db, self.crud
        self.modelo.guion = copy.deepcopy(guion)
        conv = crud.get_or_create_conversation(db, self.team.id, wa_id,
                                               contact_name=perfil)
        crud.add_message(db, conv, direction="inbound", content=texto,
                         status="received")
        bot, sesion = bot_router.resolve_bot_for_incoming_message(
            db, team=self.team, conversation_id=conv.id, message_text=texto,
        )
        if bot is not None:
            bot_runner.run_turn(
                db, bot=bot, conversation=conv, session=sesion,
                user_input=texto if sesion is not None else None,
                meta_account=None,
            )
        db.refresh(conv)
        self.pasos.append({
            "paso": "entra",
            "a_las": _reloj.ahora,
            "texto": texto,
            "perfil": perfil,
            "lo_atendio_el_bot": bot is not None,
            "llamadas_al_modelo": self.modelo.tomar(),
            "guion_sobrante": len(self.modelo.guion),
            "estado": self._estado(conv),
        })

    def vencen_pendientes(self, wa_id: str) -> None:
        """Adelanta el reloj hasta la siguiente acción agendada y la procesa."""
        from app.services import bot_runner

        db, models = self.db, self.models
        conv = self._conv(wa_id)
        pa = (
            db.query(models.BotPendingAction)
            .join(models.BotSession)
            .filter(models.BotSession.conversation_id == conv.id,
                    models.BotPendingAction.status == models.BOT_PENDING_STATUS_PENDING)
            .order_by(models.BotPendingAction.scheduled_at, models.BotPendingAction.id)
            .first()
        )
        if pa is None:
            self.pasos.append({"paso": "vence", "sin_pendientes": True})
            return
        _reloj.ahora = pa.scheduled_at + _dt.timedelta(seconds=1)
        tipo = pa.action_type
        bot_runner.process_pending_action(db, pa)
        db.refresh(conv)
        self.pasos.append({
            "paso": "vence",
            "a_las": _reloj.ahora,
            "accion": tipo,
            "llamadas_al_modelo": self.modelo.tomar(),
            "estado": self._estado(conv),
        })

    # -- la foto -----------------------------------------------------------

    def _conv(self, wa_id: str):
        models = self.models
        return (
            self.db.query(models.Conversation)
            .filter(models.Conversation.team_id == self.team.id,
                    models.Conversation.contact_wa_id == wa_id)
            .one()
        )

    def _estado(self, conv) -> Dict[str, Any]:
        db, models = self.db, self.models
        mensajes = (
            db.query(models.Message)
            .filter(models.Message.conversation_id == conv.id)
            .order_by(models.Message.id).all()
        )
        sesiones = (
            db.query(models.BotSession)
            .filter(models.BotSession.conversation_id == conv.id)
            .order_by(models.BotSession.id).all()
        )
        ids = [s.id for s in sesiones]
        pendientes = (
            db.query(models.BotPendingAction)
            .filter(models.BotPendingAction.session_id.in_(ids))
            .order_by(models.BotPendingAction.id).all()
        ) if ids else []
        decisiones = (
            db.query(models.BotLlmDecision)
            .filter(models.BotLlmDecision.conversation_id == conv.id)
            .order_by(models.BotLlmDecision.id).all()
        )
        agendamientos = (
            db.query(models.Agendamiento)
            .filter(models.Agendamiento.conversation_id == conv.id)
            .order_by(models.Agendamiento.id).all()
        )
        return {
            "conversacion": {
                "status": conv.status,
                "assigned_to": conv.assigned_to,
                "contact_name": conv.contact_name,
                "etiqueta": getattr(conv, "etiqueta", None),
            },
            "mensajes": [
                {"direction": m.direction, "message_type": m.message_type,
                 "status": m.status, "content": m.content}
                for m in mensajes
            ],
            "sesiones": [
                {"id_relativo": i, "status": s.status,
                 "state": json.loads(s.state) if s.state else None}
                for i, s in enumerate(sesiones)
            ],
            "pendientes": [
                {"sesion": ids.index(p.session_id), "action_type": p.action_type,
                 "status": p.status, "payload": p.payload,
                 "minutos_desde_ahora": round(
                     (p.scheduled_at - _reloj.ahora).total_seconds() / 60, 2)
                 if p.status == models.BOT_PENDING_STATUS_PENDING else None}
                for p in pendientes
            ],
            "decisiones": [
                {"camino": d.camino,
                 "tools_called": json.loads(d.tools_called) if d.tools_called else None,
                 "finished": d.finished, "escalated_to": d.escalated_to}
                for d in decisiones
            ],
            "agendamientos": [
                {"nivel_interes": a.nivel_interes, "fecha_llamada": a.fecha_llamada,
                 "estado": a.estado, "asesor": a.asesor}
                for a in agendamientos
            ],
        }


def _foto_cadena(modelo: ModeloFalso) -> Dict[str, Any]:
    engine, Sesion = _base()
    db = Sesion()
    fuera: Dict[str, Any] = {}
    try:
        c = _Cadena(db, modelo)

        # 1) Sin perfil: saluda, la persona calla → 3 recordatorios + abandono.
        c.pasos = []
        c.entra(WA_1, "Hola, me interesa el plan a Coveñas", [
            R(T("¡Hola! Soy Maria Camila de Arranquemos Pues 🌴 ¿Para qué mes lo "
                "estás pensando? 😊"),
              U("enviar_media", {"claves": ["info_amordios"]})),
            R(T("Te dejo la info del plan 👆")),
        ])
        for _ in range(5):
            c.vencen_pendientes(WA_1)
        fuera["silencio_recordatorios_y_abandono"] = c.pasos

        # 2) Con perfil de WhatsApp: precios, nombre y handoff con nota interna.
        _reloj.ahora = AHORA_UTC
        c.pasos = []
        c.entra(WA_2, "Buenas, precios para diciembre", [
            R(U("consultar_tarifario", {"mes": "diciembre"})),
            R(T("En diciembre hay salidas desde $406.000 por persona 🌴")),
        ], perfil="Laura Gomez")
        _reloj.avanzar(minutes=2)
        c.entra(WA_2, "me llamo Laurita, quiero hablar con una asesora", [
            R(U("registrar_nombre", {"nombre": "Laurita"}, "tu_n"),
              T("¡Claro, Laurita! Te comunico con una asesora 🙌"),
              U("escalar_a_asesor", {"motivo": "pide asesora",
                                     "resumen": "Laurita, diciembre"}, "tu_e")),
        ])
        fuera["perfil_nombre_y_handoff"] = c.pasos

        # 3) Se despide; vuelve a las 3 h (retoma) y a las 30 h (sesión nueva).
        _reloj.ahora = AHORA_UTC
        c.pasos = []
        c.entra(WA_3, "Hola info", [
            R(T("¡Hola! Soy Maria Camila 🌴 ¿Para qué mes lo estás pensando?")),
        ])
        _reloj.avanzar(minutes=3)
        c.entra(WA_3, "Para enero, lo consulto con mi esposo y te aviso", [
            R(T("¡Con gusto! Aquí estaré 🌴"), U("finalizar_conversacion", {})),
        ])
        _reloj.avanzar(minutes=1)
        c.entra(WA_3, "Gracias", [])
        _reloj.avanzar(hours=3)
        c.entra(WA_3, "Hola de nuevo, ya hablé con él", [
            R(T("¡Hola de nuevo! Soy Maria Camila de Arranquemos Pues 🌴 ¡Qué "
                "bueno! ¿Qué decidieron?")),
        ])
        _reloj.avanzar(minutes=2)
        c.entra(WA_3, "mejor después te escribo", [
            R(T("¡Listo! 🌴"), U("finalizar_conversacion", {})),
        ])
        _reloj.avanzar(hours=30)
        c.entra(WA_3, "Hola, sigue el plan?", [
            R(T("¡Hola! Soy Maria Camila de Arranquemos Pues 🌴 ¡Sí! ¿Para qué "
                "mes?")),
        ])
        fuera["despedida_retoma_y_sesion_nueva"] = c.pasos

        # 4) «Lo consulto con mi esposo» → no_responder: no sale nada, se cierra.
        _reloj.ahora = AHORA_UTC
        c.pasos = []
        c.entra(WA_4, "Hola, cuánto vale para noviembre?", [
            R(U("consultar_tarifario", {"mes": "noviembre"})),
            R(T("En noviembre desde $505.000 por persona 🌴")),
        ])
        _reloj.avanzar(minutes=4)
        c.entra(WA_4, "ok lo consulto con mi esposo", [
            R(T("¡Con gusto! 🤗"), U("no_responder", {})),
        ])
        c.vencen_pendientes(WA_4)
        fuera["esposo_no_responder"] = c.pasos
        return fuera
    finally:
        db.close()
        engine.dispose()
        _reloj.ahora = AHORA_UTC


# ---------------------------------------------------------------------------
# La foto completa
# ---------------------------------------------------------------------------

def _foto(monkeypatch) -> Dict[str, Any]:
    _congelar(monkeypatch)
    for var in ("LLM_MODEL_ID", "LLM_MAX_TOKENS"):
        monkeypatch.delenv(var, raising=False)

    from app.services import llm_engine, tarifario

    registro = _Registro()
    modelo = ModeloFalso(registro)
    monkeypatch.setattr(llm_engine, "_invoke_model", modelo)

    bot = _BotEnMemoria(_cfg_bot1())
    motor = {c["nombre"]: _correr_caso(c, bot, modelo) for c in CASOS_MOTOR}
    por_productos = _foto_productos(monkeypatch, modelo)
    cadena = _foto_cadena(modelo)

    cfg = _cfg_bot1()
    seguimiento = llm_engine.seguimiento_de(bot)
    recordatorios = {
        "seguimiento_de": seguimiento,
        "recordatorios_de": llm_engine.recordatorios_de(seguimiento),
        "minutos_de_seguimiento": llm_engine.minutos_de_seguimiento(seguimiento),
        "etiqueta_de_abandono": llm_engine.etiqueta_de_abandono(seguimiento),
        "texto_de_seguimiento": llm_engine.texto_de_seguimiento(seguimiento),
        "horas_para_retomar": llm_engine.horas_para_retomar(cfg),
    }
    consultas = [
        {"hotel": "Amor de Dios", "mes": "diciembre"},
        {"mes": "noviembre"},
        {"hotel": "Piedra Mar", "fecha": "2026-12-18", "mes": "diciembre"},
        {"presupuesto": "450 mil"},
    ]
    tarifas = [
        {"consulta": q, "hoy": HOY_CO.isoformat(),
         "resultado": tarifario.consultar(cfg, hoy=HOY_CO, **q)}
        for q in consultas
    ]

    foto = {
        "_meta": {
            "que_es": "Foto del comportamiento del bot 1 (demo_viajes). La compara "
                      "tests/viajes/test_bot1_sin_cambios.py; regenerarla ACEPTA "
                      "los cambios — ver el docstring de esa prueba.",
            "commit_origen": "7835c65",
            "reloj_utc": AHORA_UTC.isoformat(),
            "hoy_colombia": HOY_CO.isoformat(),
        },
        "llm_config_bot1": cfg,
        "motor": motor,
        "motor_fuente_productos": por_productos,
        "cadena": cadena,
        "recordatorios": recordatorios,
        "tarifario": tarifas,
        "herramientas": registro.herramientas,
        "prompts": registro.prompts,
    }
    # Ida y vuelta por JSON: lo que se compara es exactamente lo que se guarda.
    return json.loads(json.dumps(_normalizar(foto), ensure_ascii=False))


def _diff(esperado: Any, actual: Any, ruta: str = "") -> List[str]:
    """Diferencias legibles: ruta de la llave y, en textos largos, el diff."""
    if type(esperado) is not type(actual):
        return [f"{ruta}: tipo {type(esperado).__name__} → {type(actual).__name__}: "
                f"{json.dumps(esperado, ensure_ascii=False)[:300]} → "
                f"{json.dumps(actual, ensure_ascii=False)[:300]}"]
    if isinstance(esperado, dict):
        fuera = []
        for k in esperado.keys() | actual.keys():
            sub = f"{ruta}.{k}" if ruta else k
            if k not in actual:
                fuera.append(f"{sub}: desapareció")
            elif k not in esperado:
                fuera.append(f"{sub}: nueva → "
                             f"{json.dumps(actual[k], ensure_ascii=False)[:300]}")
            else:
                fuera.extend(_diff(esperado[k], actual[k], sub))
        return sorted(fuera)
    if isinstance(esperado, list):
        fuera = []
        if len(esperado) != len(actual):
            fuera.append(f"{ruta}: largo {len(esperado)} → {len(actual)}")
        for i, (a, b) in enumerate(zip(esperado, actual)):
            fuera.extend(_diff(a, b, f"{ruta}[{i}]"))
        return fuera
    if esperado != actual:
        if isinstance(esperado, str) and ("\n" in esperado or len(esperado) > 200):
            udiff = "\n".join(difflib.unified_diff(
                esperado.splitlines(), actual.splitlines(),
                "esperado", "actual", lineterm="", n=1,
            ))
            return [f"{ruta}: texto distinto\n{udiff}"]
        return [f"{ruta}: {json.dumps(esperado, ensure_ascii=False)} → "
                f"{json.dumps(actual, ensure_ascii=False)}"]
    return []


# ---------------------------------------------------------------------------
# Pruebas
# ---------------------------------------------------------------------------

def test_bot1_se_comporta_igual_que_en_7835c65(monkeypatch):
    actual = _foto(monkeypatch)
    if REGENERAR:
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(
            json.dumps(actual, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"fixture regenerado en {FIXTURE} (BOT1_GOLDEN_REGENERAR=1)")

    assert FIXTURE.exists(), (
        f"falta {FIXTURE}; ver el docstring de este archivo para generarlo"
    )
    esperado = json.loads(FIXTURE.read_text(encoding="utf-8"))
    diferencias = _diff(esperado, actual)
    if diferencias:
        pytest.fail(_informe(esperado, actual, diferencias), pytrace=False)


def _informe(esperado: dict, actual: dict, diferencias: List[str]) -> str:
    """El mensaje de falla, legible.

    Los `system` y los esquemas se guardan por hash, así que un cambio en el
    prompt sale como decenas de «p_abc → p_def». Esas referencias se resumen
    y en su lugar va el diff del TEXTO, una vez por par distinto.
    """
    pares: Dict[tuple, int] = {}
    resto: List[str] = []
    for d in diferencias:
        ruta, _, cola = d.partition(": ")
        if ruta.endswith((".system", ".esquemas")) and " → " in cola:
            viejo, nuevo = (json.loads(x) for x in cola.split(" → ", 1))
            pares[(viejo, nuevo)] = pares.get((viejo, nuevo), 0) + 1
        elif ruta.startswith(("prompts.", "herramientas.")):
            continue          # lo cubre el diff de texto de abajo
        else:
            resto.append(d)

    bloques = []
    for (viejo, nuevo), veces in sorted(pares.items()):
        seccion = "prompts" if viejo.startswith("p_") else "herramientas"
        antes = esperado[seccion].get(viejo, "")
        despues = actual[seccion].get(nuevo, "")
        if seccion == "herramientas":
            antes = json.dumps(antes, ensure_ascii=False, indent=1, sort_keys=True)
            despues = json.dumps(despues, ensure_ascii=False, indent=1, sort_keys=True)
        udiff = list(difflib.unified_diff(
            antes.splitlines(), despues.splitlines(),
            f"{seccion}/{viejo}", f"{seccion}/{nuevo}", lineterm="", n=1,
        ))
        bloques.append(
            f"[{seccion}] {viejo} → {nuevo} (en {veces} llamadas al modelo)\n"
            + "\n".join(udiff[:60])
            + (f"\n… ({len(udiff) - 60} líneas más)" if len(udiff) > 60 else "")
        )

    partes = [
        f"El bot 1 cambió de comportamiento ({len(diferencias)} diferencias). "
        "Si NO fue a propósito, algo se escapó de un flag de la variante B."
    ]
    if bloques:
        partes.append("── Lo que recibe el modelo ──\n" + "\n\n".join(bloques))
    if resto:
        partes.append(
            "── Lo demás ──\n" + "\n".join(resto[:40])
            + (f"\n… y {len(resto) - 40} más" if len(resto) > 40 else "")
        )
    return "\n\n".join(partes)


def test_el_fixture_cubre_lo_pactado():
    """Que nadie regenere la foto con menos casos sin darse cuenta."""
    if REGENERAR and not FIXTURE.exists():
        pytest.skip("se está regenerando")
    foto = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(foto["motor"]) == len(CASOS_MOTOR) >= 15
    assert len(foto["motor_fuente_productos"]) == len(CASOS_PRODUCTOS)
    assert len(foto["cadena"]) == 4
    assert len(foto["tarifario"]) >= 3
    assert foto["prompts"], "la foto no guardó ningún system prompt"


def test_la_config_del_bot1_no_trae_flags_de_la_variante_b():
    from app.data.bot_viajes import LLM_CONFIG

    presentes = [f for f in FLAGS_BOT2 if f in LLM_CONFIG]
    assert not presentes, f"flags de la variante B en el bot 1: {presentes}"
    # Tampoco escondidas dentro del seguimiento (#28 usa `plantilla` ahí).
    for etapa in (LLM_CONFIG.get("seguimiento") or {}).get("recordatorios") or []:
        assert "plantilla" not in etapa, etapa
    assert LLM_CONFIG.get("context_key") == "demo_viajes"
