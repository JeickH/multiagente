"""El turno del bot cuando los datos vienen de la base (fase 3).

Lo que se prueba aquí es el **cableado**, no la redacción: que el prompt salga
de la columna cuando la hay, que el índice aparezca, que el interruptor conmute
y —sobre todo— que cuando la capa nueva se cae el cliente reciba igual su
respuesta y quede el rastro. La redacción del resultado ya la cuida la prueba
de oro (`test_paridad_tarifario.py`), que compara texto contra el motor viejo.

Todo corre contra SQLite en memoria y con el modelo mockeado: cero costo, cero
red. El producto de juguete es el del `conftest` (un taller de cerámica que no
existe) con las fechas corridas al futuro, porque una fila vencida no se ofrece
y la suite tiene que seguir verde el año que viene.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy.orm import sessionmaker

from app import models
from app.services import llm_engine, productos, productos_bot

from .conftest import crear_juguete

#: El prompt del bot de juguete. Corto a propósito: así el prefijo queda por
#: debajo del mínimo cacheable salvo que el test lo engorde adrede.
INSTRUCCIONES_CORTAS = "Eres el asistente del taller. Sé amable y breve."


# ---------------------------------------------------------------------------
# Andamiaje
# ---------------------------------------------------------------------------

def _texto(t: str) -> dict:
    return {"type": "text", "text": t}


def _tool(nombre: str, entrada: Optional[dict] = None, ident: str = "tu_1") -> dict:
    return {"type": "tool_use", "id": ident, "name": nombre, "input": entrada or {}}


def _respuesta(*bloques, stop: str = "end_turn") -> dict:
    return {
        "content": list(bloques),
        "stop_reason": stop,
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


class ModeloFalso:
    """Bedrock reemplazado por un guion. Guarda lo que se le mandó."""

    def __init__(self) -> None:
        self.guion: List[dict] = []
        self.recibidos: List[dict] = []

    def __call__(self, model_id, system, messages, tools):
        self.recibidos.append(
            {"system": system, "tools": [t["name"] for t in tools]}
        )
        if not self.guion:
            return _respuesta(_texto("(el guion se quedó sin respuestas)"))
        return self.guion.pop(0)

    @property
    def herramientas(self) -> List[str]:
        return self.recibidos[-1]["tools"]

    @property
    def system(self) -> str:
        return self.recibidos[-1]["system"]


@pytest.fixture
def modelo(monkeypatch) -> ModeloFalso:
    falso = ModeloFalso()
    monkeypatch.setattr(llm_engine, "_invoke_model", falso)
    return falso


@pytest.fixture
def motor_conectado(db_session, monkeypatch):
    """El motor abre su propia sesión: se la apuntamos a la base del test.

    Es el mismo arreglo que usa el bot de mascotas (`_mascotas_db`). Sin esto,
    las herramientas del catálogo irían a buscar el Postgres de verdad.
    """
    Sesion = sessionmaker(
        autocommit=False, autoflush=False, bind=db_session.get_bind()
    )
    monkeypatch.setattr(llm_engine, "_productos_db", Sesion)
    return Sesion


def _config(**extra: Any) -> str:
    cfg: Dict[str, Any] = {"context_key": "", "assignee": "asesor_1"}
    cfg.update(extra)
    return json.dumps(cfg, ensure_ascii=False)


def _bot(db, bot_id: int, *, instrucciones=None, **cfg) -> models.Bot:
    """El bot de la cuenta, con su config y su nivel 2 puestos."""
    bot = db.get(models.Bot, bot_id)
    bot.llm_config = _config(**cfg)
    bot.instrucciones = instrucciones
    db.add(bot)
    db.commit()
    return bot


def _futuras(*dias: int):
    """Fechas del juguete corridas al futuro: lo vencido no se ofrece."""
    hoy = productos.hoy_colombia()
    return [
        ("basico", hoy + timedelta(days=d), 120_000 + 1_000 * i, 4, "")
        for i, d in enumerate(dias)
    ]


def _dicho(resultado: dict) -> str:
    return "\n".join(
        a["payload"].get("text", "")
        for a in resultado["actions"]
        if a["type"] == "say"
    )


# ---------------------------------------------------------------------------
# Nivel 2: `bots.instrucciones`
# ---------------------------------------------------------------------------

class TestInstruccionesDelBot:
    def test_la_columna_vacia_deja_el_md_de_la_imagen(self, db_session, cuenta_a):
        """Nadie cambia de comportamiento por desplegar esto.

        Con `bots.instrucciones` en NULL, el prompt arranca con el archivo de
        siempre. Es el estado de los seis bots que hay en producción.
        """
        _, bot_id = cuenta_a
        bot = _bot(db_session, bot_id, context_key="demo_viajes")

        prompt = llm_engine._system_prompt(bot, llm_engine.config_de(bot))

        assert prompt.startswith(llm_engine._load_context("demo_viajes"))

    def test_con_la_columna_poblada_manda_la_columna(self, db_session, cuenta_a):
        """Y el `.md` no aparece: son alternativas, no se suman."""
        _, bot_id = cuenta_a
        bot = _bot(
            db_session, bot_id,
            instrucciones="Vendes talleres de cerámica. No hables de otra cosa.",
            context_key="demo_viajes",
        )

        prompt = llm_engine._system_prompt(bot, llm_engine.config_de(bot))

        assert prompt.startswith("Vendes talleres de cerámica.")
        assert llm_engine._load_context("demo_viajes") not in prompt

    def test_una_columna_con_espacios_no_cuenta_como_poblada(
        self, db_session, cuenta_a
    ):
        """`"  \\n "` es una columna vacía escrita con el pie, no un prompt."""
        _, bot_id = cuenta_a
        bot = _bot(
            db_session, bot_id, instrucciones="   \n  ", context_key="demo_viajes"
        )

        prompt = llm_engine._system_prompt(bot, llm_engine.config_de(bot))

        assert prompt.startswith(llm_engine._load_context("demo_viajes"))


# ---------------------------------------------------------------------------
# El índice en el prompt
# ---------------------------------------------------------------------------

class TestIndiceEnElPrompt:
    def test_sin_productos_el_prompt_queda_exactamente_como_hoy(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """La cuenta apuntada a la capa nueva pero sin catálogo cargado."""
        _, bot_id = cuenta_a
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS,
            fuente_datos="productos",
        )
        antes = llm_engine._system_prompt(bot, llm_engine.config_de(bot))

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")

        assert modelo.system == antes
        assert "Lo que vendes" not in modelo.system

    def test_con_tres_productos_va_el_indice_y_ninguna_ficha(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Dos líneas por producto y nada más.

        Las fichas de los tres no caben en el prefijo — y aunque cupieran, la
        que hiciera falta depende de la conversación: meterlas invalidaría la
        caché en cada turno. Entran como resultado de `abrir_producto`.
        """
        team_id, bot_id = cuenta_a
        for i, slug in enumerate(("taller_uno", "taller_dos", "taller_tres")):
            producto = crear_juguete(
                db_session, team_id=team_id, bot_id=bot_id, slug=slug,
                fechas=_futuras(10 + i, 40 + i),
            )
            producto.instrucciones = f"FICHA SECRETA DE {slug.upper()}"
            producto.resumen = f"Resumen del {slug}."
        db_session.commit()
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS,
            fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")

        for slug in ("taller_uno", "taller_dos", "taller_tres"):
            assert f"`{slug}`" in modelo.system
            assert f"Resumen del {slug}." in modelo.system
            assert f"FICHA SECRETA DE {slug.upper()}" not in modelo.system

    def test_con_un_solo_producto_y_prefijo_grande_la_ficha_va_dentro(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Un producto y un prefijo que pasa el mínimo cacheable.

        Ahí la ficha es tan estable como el resto del prompt: metida adentro se
        cachea y deja de costar a partir del segundo turno, además de ahorrarle
        al modelo la ronda de `abrir_producto`.
        """
        team_id, bot_id = cuenta_a
        producto = crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        producto.instrucciones = "FICHA DEL TALLER. " + "detalle del taller. " * 40
        db_session.commit()
        # Un prompt largo de verdad: el prefijo tiene que pasar de 4.096 tokens
        # o Bedrock no cachea (y no avisa).
        largo = "Instrucción de negocio número {}. " * 1
        bot = _bot(
            db_session, bot_id,
            instrucciones="".join(largo.format(i) for i in range(600)),
            fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")

        assert productos_bot.tokens_aprox(modelo.system) >= 4096
        assert "FICHA DEL TALLER." in modelo.system

    def test_con_un_solo_producto_y_prefijo_chico_la_ficha_se_queda_fuera(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """El caso que decide si esto sale barato o caro.

        Por debajo del mínimo, Bedrock no cachea nada: esos tokens se pagarían
        enteros en cada ronda de cada turno. Ahí sale más barato servir la
        ficha como resultado de herramienta — se paga una vez, y sólo si la
        conversación llega a ese producto.
        """
        team_id, bot_id = cuenta_a
        producto = crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        producto.instrucciones = "FICHA DEL TALLER, que aquí no debería salir."
        db_session.commit()
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS,
            fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")

        assert productos_bot.tokens_aprox(modelo.system) < 4096
        assert "FICHA DEL TALLER" not in modelo.system, "la ficha no va adentro"
        assert "`consultar_precios`" in modelo.system, "el pie sí va"
        # Y como la ficha se quedó afuera, ésta es la única forma de llegar a
        # ella: aquí `abrir_producto` sí tiene algo que abrir.
        assert productos_bot.ABRIR in modelo.herramientas

    def test_el_producto_en_borrador_no_se_le_nombra_al_modelo(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Publicado es publicado. Lo que se está editando no se vende."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, slug="en_borrador",
            estado=models.PRODUCTO_ESTADO_BORRADOR, fechas=_futuras(10),
        )
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")

        assert "en_borrador" not in modelo.system

    def test_el_producto_fuera_de_vigencia_tampoco(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Una campaña de temporada que ya cerró: nombrarla es invitar a
        ofrecerla."""
        team_id, bot_id = cuenta_a
        producto = crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, slug="temporada",
            fechas=_futuras(10),
        )
        producto.vigencia_hasta = productos.hoy_colombia() - timedelta(days=1)
        db_session.commit()
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")

        assert "temporada" not in modelo.system


# ---------------------------------------------------------------------------
# El interruptor
# ---------------------------------------------------------------------------

class TestInterruptor:
    def test_por_defecto_responde_el_motor_viejo(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """**Esta fase no enciende nada.** Sin `fuente_datos` en la config, el
        bot conserva `consultar_tarifario` aunque tenga productos cargados."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(db_session, bot_id, tarifario="covenas")

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        resultado = llm_engine.advance(bot, None, "hola")

        assert "consultar_tarifario" in modelo.herramientas
        assert not (productos_bot.TOOLS & set(modelo.herramientas))
        assert "Lo que vendes" not in modelo.system
        assert resultado["telemetry"]["fuente_datos"] == "tarifario"

    def test_con_el_interruptor_responde_la_capa_nueva(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Y `consultar_tarifario` desaparece: dos fuentes de precios en el
        mismo turno es pedirle al modelo que elija por su cuenta."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(db_session, bot_id, tarifario="covenas", fuente_datos="productos")

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        resultado = llm_engine.advance(bot, None, "hola")

        # Un solo producto y sin ficha: la única herramienta del catálogo que
        # tiene algo que hacer es la de precios. Cuáles se declaran lo fija
        # `TestQueSeDeclara`.
        assert productos_bot.PRECIOS in modelo.herramientas
        assert "consultar_tarifario" not in modelo.herramientas
        assert resultado["telemetry"]["fuente_datos"] == "productos"

    def test_el_bot_sin_ninguna_fuente_no_marca_nada(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """El de mascotas y el institucional: la columna queda en NULL.

        Es por lo que es nullable — "no consultó ninguna fuente" no se puede
        confundir con "consultó la vieja".
        """
        _, bot_id = cuenta_a
        bot = _bot(db_session, bot_id, instrucciones=INSTRUCCIONES_CORTAS)

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        resultado = llm_engine.advance(bot, None, "hola")

        assert resultado["telemetry"]["fuente_datos"] is None


# ---------------------------------------------------------------------------
# Cuáles de las tres se declaran
# ---------------------------------------------------------------------------

class TestQueSeDeclara:
    """El esquema de una herramienta se paga en CADA llamada de CADA turno.

    La medición de la fase 5 lo cobró: el prefijo creció 3,7 % contra el motor
    viejo y las dos herramientas culpables —`abrir_producto` y
    `fechas_disponibles`— se llamaron **cero** veces en 69 guiones. Eran ~290
    tokens de esquema por ronda a cambio de nada.

    Esta clase fija la regla: **no se declara una herramienta que no tiene nada
    que hacer**. Si alguien vuelve a declarar una de más, falla acá.
    """

    def _declaradas(self, bot, modelo) -> set:
        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")
        return productos_bot.TOOLS & set(modelo.herramientas)

    def test_un_producto_sin_ficha_solo_declara_precios(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Nada que abrir (no hay ficha) y las fechas ya las da `consultar_precios`."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        assert self._declaradas(bot, modelo) == {productos_bot.PRECIOS}

    def test_un_producto_con_la_ficha_ya_en_el_prefijo_tampoco_declara_abrir(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Es el mismo criterio de `ficha_en_el_prefijo`, no uno paralelo: si la
        ficha viaja adentro del bloque `system`, `abrir_producto` devolvería lo
        que el modelo ya está leyendo."""
        team_id, bot_id = cuenta_a
        producto = crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        producto.instrucciones = "FICHA DEL TALLER. " + "detalle del taller. " * 40
        db_session.commit()
        bot = _bot(
            db_session, bot_id,
            instrucciones="".join(f"Instrucción de negocio número {i}. " for i in range(600)),
            fuente_datos="productos",
        )

        declaradas = self._declaradas(bot, modelo)

        assert "FICHA DEL TALLER." in modelo.system, "la ficha sí entró"
        assert declaradas == {productos_bot.PRECIOS}

    def test_un_producto_con_la_ficha_afuera_si_declara_abrir(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """La otra cara: si la ficha no cupo en el prefijo, ésta es la única
        forma de llegar a ella y la herramienta se gana su esquema."""
        team_id, bot_id = cuenta_a
        producto = crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        producto.instrucciones = "FICHA: se paga la mitad al reservar."
        db_session.commit()
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        assert self._declaradas(bot, modelo) == {
            productos_bot.ABRIR, productos_bot.PRECIOS
        }

    def test_con_varios_productos_se_declaran_las_tres(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Con varios sí hay entre qué elegir: hay fichas que abrir y el
        calendario cruza productos, que es lo que `consultar_precios` no hace
        de una sola pasada."""
        team_id, bot_id = cuenta_a
        for i, slug in enumerate(("taller_uno", "taller_dos")):
            producto = crear_juguete(
                db_session, team_id=team_id, bot_id=bot_id, slug=slug,
                fechas=_futuras(10 + i, 40 + i),
            )
            producto.instrucciones = f"FICHA DE {slug.upper()}"
        db_session.commit()
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        assert self._declaradas(bot, modelo) == productos_bot.TOOLS

    def test_con_un_solo_producto_no_se_pide_la_clave_del_producto(
        self, db_session, cuenta_a, motor_conectado
    ):
        """No hay entre qué elegir: `resolver_producto` devuelve el único cuando
        el campo llega vacío. Declararlo cuesta esquema en cada ronda y además
        es una forma de fallar — si el modelo escribe una clave que no resuelve,
        el bot contesta «no reconozco ese producto» sobre lo único que vende."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        db_session.commit()
        ctx = productos_bot.abrir(db_session, team_id=team_id, bot_id=bot_id)

        esquemas = productos_bot.tools(ctx)

        assert esquemas, "algo tiene que quedar declarado"
        for tool in esquemas:
            assert "producto" not in tool["input_schema"]["properties"], tool["name"]
            assert tool["input_schema"]["required"] == []

    def test_con_varios_productos_si_se_pide_la_clave(
        self, db_session, cuenta_a, motor_conectado
    ):
        """Y ahí sí es obligatoria para abrir: adivinar cuál es exactamente el
        error que este esquema viene a cerrar."""
        team_id, bot_id = cuenta_a
        for slug in ("taller_uno", "taller_dos"):
            crear_juguete(
                db_session, team_id=team_id, bot_id=bot_id, slug=slug,
                fechas=_futuras(10, 40),
            )
        db_session.commit()
        ctx = productos_bot.abrir(db_session, team_id=team_id, bot_id=bot_id)

        por_nombre = {t["name"]: t for t in productos_bot.tools(ctx)}

        for nombre, tool in por_nombre.items():
            assert "producto" in tool["input_schema"]["properties"], nombre
        assert por_nombre[productos_bot.ABRIR]["input_schema"]["required"] == [
            "producto"
        ]

    def test_el_producto_unico_se_resuelve_sin_que_el_modelo_lo_nombre(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """La contrapartida de no declarar la clave: la herramienta tiene que
        funcionar con la entrada vacía, o se habría ahorrado esquema a cambio de
        romper el turno."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )
        mes = (productos.hoy_colombia() + timedelta(days=10)).month
        modelo.guion = [
            _respuesta(
                _tool(productos_bot.PRECIOS, {"mes": productos.nombre_mes(mes)}),
                stop="tool_use",
            ),
            _respuesta(_texto("Estos son los valores.")),
        ]

        resultado = llm_engine.advance(bot, None, "¿cuánto vale?")

        assert "$120.000" in resultado["telemetry"]["tools"][0]["resultado"]


# ---------------------------------------------------------------------------
# Las tres herramientas
# ---------------------------------------------------------------------------

class TestHerramientas:
    @pytest.fixture
    def bot_con_catalogo(self, db_session, cuenta_a, motor_conectado):
        team_id, bot_id = cuenta_a
        producto = crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id,
            fechas=_futuras(10, 20, 40),
        )
        producto.instrucciones = "FICHA: se paga la mitad al reservar."
        db_session.commit()
        return _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

    def test_abrir_producto_entrega_la_ficha_y_las_versiones(
        self, bot_con_catalogo, modelo
    ):
        modelo.guion = [
            _respuesta(
                _tool("abrir_producto", {"producto": "taller_ceramica"}),
                stop="tool_use",
            ),
            _respuesta(_texto("Te cuento del taller.")),
        ]
        resultado = llm_engine.advance(bot_con_catalogo, None, "cuéntame")

        ficha = resultado["telemetry"]["tools"][0]["resultado"]
        assert "FICHA: se paga la mitad al reservar." in ficha
        assert "Taller básico" in ficha

    def test_consultar_precios_devuelve_las_filas_y_la_imagen(
        self, bot_con_catalogo, modelo, db_session
    ):
        """Las cifras salen de la fila, y con ellas qué medio mandar."""
        mes = (productos.hoy_colombia() + timedelta(days=10)).month
        modelo.guion = [
            _respuesta(
                _tool(
                    "consultar_precios",
                    {"producto": "taller_ceramica",
                     "mes": productos.nombre_mes(mes)},
                ),
                stop="tool_use",
            ),
            _respuesta(_texto("Estos son los valores.")),
        ]
        resultado = llm_engine.advance(bot_con_catalogo, None, "¿cuánto vale?")

        texto = resultado["telemetry"]["tools"][0]["resultado"]
        assert "$120.000" in texto

    def test_fechas_disponibles_no_dice_un_solo_precio(
        self, bot_con_catalogo, modelo
    ):
        """Es un panorama. Para cifras está `consultar_precios`, y decirlas dos
        veces con formatos distintos es como se cita un precio viejo."""
        modelo.guion = [
            _respuesta(
                _tool("fechas_disponibles", {"producto": "taller_ceramica"}),
                stop="tool_use",
            ),
            _respuesta(_texto("Estas fechas hay.")),
        ]
        resultado = llm_engine.advance(bot_con_catalogo, None, "¿qué fechas hay?")

        texto = resultado["telemetry"]["tools"][0]["resultado"]
        assert "120.000" not in texto
        assert "Taller básico" in texto

    def test_sin_filas_vigentes_la_herramienta_ordena_escalar(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Un bot sin datos no dice "no tengo datos": improvisa, y lo que
        improvisa se parece muchísimo a una cotización."""
        team_id, bot_id = cuenta_a
        hoy = productos.hoy_colombia()
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id,
            fechas=[("basico", hoy - timedelta(days=30), 100_000, 4, "")],
        )
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )
        modelo.guion = [
            _respuesta(
                _tool("abrir_producto", {"producto": "taller_ceramica"}),
                stop="tool_use",
            ),
            _respuesta(_texto("Déjame confirmarte.")),
        ]

        resultado = llm_engine.advance(bot, None, "cuéntame")

        texto = resultado["telemetry"]["tools"][0]["resultado"]
        assert "pasa la conversación a un asesor" in texto

    def test_el_medio_del_catalogo_se_puede_enviar(self, bot_con_catalogo, modelo):
        """`consultar_precios` puede decir "manda `flyer_x`": esa clave tiene
        que existir para `enviar_media`, o el envío falla en silencio y el bot
        queda diciendo «te dejo la imagen 👇» sin adjuntar nada."""
        modelo.guion = [
            _respuesta(
                _tool("enviar_media", {"claves": ["flyer_marzo"]}), stop="tool_use"
            ),
            _respuesta(_texto("Ahí te va.")),
        ]
        resultado = llm_engine.advance(bot_con_catalogo, None, "mándame la imagen")

        medios = [a for a in resultado["actions"] if a["type"] == "say_media"]
        assert len(medios) == 1
        assert medios[0]["payload"]["url"].endswith("flyer_marzo.jpg")


# ---------------------------------------------------------------------------
# Aislamiento por cuenta
# ---------------------------------------------------------------------------

class TestAislamiento:
    def test_el_producto_de_una_cuenta_no_lo_ve_el_bot_de_la_otra(
        self, db_session, cuenta_a, cuenta_b, motor_conectado, modelo
    ):
        """El peor error posible de este esquema: un bot cotizando con el
        catálogo de otra agencia."""
        team_a, _ = cuenta_a
        _, bot_b = cuenta_b
        crear_juguete(db_session, team_id=team_a, fechas=_futuras(10, 40))
        bot = _bot(
            db_session, bot_b,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        resultado = llm_engine.advance(bot, None, "hola")

        assert "`taller_ceramica`" not in modelo.system
        assert "Lo que vendes" not in modelo.system
        assert not (productos_bot.TOOLS & set(modelo.herramientas))
        assert resultado["telemetry"]["fuente_datos"] is None

    def test_ni_aunque_alguien_le_enganche_el_producto_ajeno(
        self, db_session, cuenta_a, cuenta_b, motor_conectado, modelo
    ):
        """La fila cruzada: el producto de una cuenta enganchado al bot de otra.

        Nunca debería existir —es un error de datos—, y es justo por eso que la
        prueba vale: el filtro por `team_id` es la segunda cerradura. Sin ella,
        el enganche por sí solo le abriría el catálogo ajeno al bot.
        """
        team_a, _ = cuenta_a
        _, bot_b = cuenta_b
        ajeno = crear_juguete(db_session, team_id=team_a, fechas=_futuras(10, 40))
        db_session.add(
            models.BotProductoBot(bot_id=bot_b, producto_id=ajeno.id, activo=True)
        )
        db_session.commit()
        bot = _bot(
            db_session, bot_b,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        resultado = llm_engine.advance(bot, None, "hola")

        assert "`taller_ceramica`" not in modelo.system
        assert "Lo que vendes" not in modelo.system
        assert resultado["telemetry"]["fuente_datos"] is None

    def test_la_consulta_tampoco_cruza_de_cuenta(
        self, db_session, cuenta_a, cuenta_b, motor_conectado, modelo
    ):
        """Y si el modelo nombra el producto ajeno a pelo, tampoco sale.

        El índice es sólo lo que el bot *lee*; la puerta de verdad es la
        consulta, que vuelve a filtrar por cuenta.
        """
        team_a, _ = cuenta_a
        _, bot_b = cuenta_b
        ajeno = crear_juguete(db_session, team_id=team_a, fechas=_futuras(10, 40))
        db_session.add(
            models.BotProductoBot(bot_id=bot_b, producto_id=ajeno.id, activo=True)
        )
        db_session.commit()
        bot = _bot(db_session, bot_b, fuente_datos="productos")

        texto = productos.consultar(
            db_session,
            team_id=db_session.get(models.Bot, bot_b).team_id,
            bot_id=bot_b,
            producto="taller_ceramica",
            mes="marzo",
        )

        assert "120.000" not in texto

    def test_el_producto_no_asignado_al_bot_tampoco(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """Misma cuenta, otro bot: un bot de soporte no cotiza el catálogo."""
        team_id, bot_id = cuenta_a
        crear_juguete(db_session, team_id=team_id, fechas=_futuras(10, 40))
        bot = _bot(
            db_session, bot_id,
            instrucciones=INSTRUCCIONES_CORTAS, fuente_datos="productos",
        )

        modelo.guion = [_respuesta(_texto("¡Hola!"))]
        llm_engine.advance(bot, None, "hola")

        assert "Lo que vendes" not in modelo.system


# ---------------------------------------------------------------------------
# El fallback
# ---------------------------------------------------------------------------

class TestFallback:
    """Si la capa nueva revienta, el turno se completa igual — y se ve.

    Las dos mitades son inseparables: un fallback silencioso es un motor nuevo
    que lleva tres semanas sin usarse y nadie lo sabe.
    """

    @pytest.fixture
    def revienta(self, monkeypatch):
        """Inyecta la falla en `services.productos`, que es la capa nueva."""

        def _romper(nombre: str):
            def _boom(*_args, **_kw):
                raise RuntimeError("la capa nueva se cayó")

            monkeypatch.setattr(productos, nombre, _boom)

        return _romper

    def test_si_falla_al_armar_el_catalogo_el_turno_se_completa(
        self, db_session, cuenta_a, motor_conectado, modelo, revienta, caplog
    ):
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(
            db_session, bot_id, tarifario="covenas", fuente_datos="productos"
        )
        revienta("catalogos_de_bot")
        modelo.guion = [_respuesta(_texto("¡Hola! ¿En qué te ayudo?"))]

        with caplog.at_level(logging.WARNING, logger="app.services.llm_engine"):
            resultado = llm_engine.advance(bot, None, "hola")

        assert _dicho(resultado) == "¡Hola! ¿En qué te ayudo?"
        assert not resultado["telemetry"]["failsafe"], "el cliente no ve un error"
        # Y el turno lo resolvió la fuente vieja, con sus herramientas.
        assert "consultar_tarifario" in modelo.herramientas
        assert resultado["telemetry"]["fuente_datos"] == "fallback"
        assert any(
            "catálogo" in r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING
        ), "el fallback nunca es silencioso"

    def test_si_falla_la_consulta_contesta_el_motor_viejo(
        self, db_session, cuenta_a, motor_conectado, modelo, revienta, caplog
    ):
        """La falla llega a mitad de turno, con las herramientas ya declaradas.

        `consultar_precios` es el reemplazo de `consultar_tarifario`, así que
        la consulta se le pasa al viejo con los mismos argumentos y el modelo
        recibe un resultado de verdad — no un error.
        """
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(
            db_session, bot_id, tarifario="covenas", fuente_datos="productos"
        )
        revienta("consultar")
        modelo.guion = [
            _respuesta(
                _tool("consultar_precios",
                      {"producto": "taller_ceramica", "mes": "diciembre"}),
                stop="tool_use",
            ),
            _respuesta(_texto("Estos son los precios de diciembre.")),
        ]

        with caplog.at_level(logging.WARNING, logger="app.services.llm_engine"):
            resultado = llm_engine.advance(bot, None, "¿precios de diciembre?")

        assert _dicho(resultado) == "Estos son los precios de diciembre."
        assert not resultado["telemetry"]["failsafe"]
        texto = resultado["telemetry"]["tools"][0]["resultado"]
        assert texto and "error" not in texto.lower()
        assert resultado["telemetry"]["fuente_datos"] == "fallback"
        assert any(
            "productos falló" in r.getMessage() for r in caplog.records
            if r.levelno >= logging.WARNING
        )

    def test_sin_motor_viejo_detras_el_fallback_manda_escalar(
        self, db_session, cuenta_a, motor_conectado, modelo, revienta
    ):
        """No se improvisa: sin datos, se escala. Es la regla de siempre."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(db_session, bot_id, fuente_datos="productos")
        revienta("consultar")
        modelo.guion = [
            _respuesta(
                _tool("consultar_precios", {"producto": "taller_ceramica"}),
                stop="tool_use",
            ),
            _respuesta(_texto("Déjame confirmarte eso.")),
        ]

        resultado = llm_engine.advance(bot, None, "¿cuánto vale?")

        texto = resultado["telemetry"]["tools"][0]["resultado"]
        assert "pasa la conversación a un asesor" in texto
        assert resultado["telemetry"]["fuente_datos"] == "fallback"

    def test_el_turno_que_no_falla_no_queda_marcado(
        self, db_session, cuenta_a, motor_conectado, modelo
    ):
        """El contrapunto: si `fallback` apareciera siempre, no diría nada."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
        )
        bot = _bot(
            db_session, bot_id, tarifario="covenas", fuente_datos="productos"
        )
        modelo.guion = [
            _respuesta(
                _tool("consultar_precios", {"producto": "taller_ceramica"}),
                stop="tool_use",
            ),
            _respuesta(_texto("Ahí va.")),
        ]

        resultado = llm_engine.advance(bot, None, "¿cuánto vale?")

        assert resultado["telemetry"]["fuente_datos"] == "productos"


# ---------------------------------------------------------------------------
# La telemetría llega a la tabla
# ---------------------------------------------------------------------------

def test_la_marca_del_fallback_queda_escrita_en_la_bitacora(
    db_session, cuenta_a, motor_conectado, modelo, monkeypatch
):
    """`record_decision` es lo que hace que el fallback se pueda contar con un
    `GROUP BY` en vez de rastreando logs."""
    team_id, bot_id = cuenta_a
    crear_juguete(
        db_session, team_id=team_id, bot_id=bot_id, fechas=_futuras(10, 40)
    )
    bot = _bot(db_session, bot_id, fuente_datos="productos")

    def _boom(*_a, **_k):
        raise RuntimeError("la capa nueva se cayó")

    monkeypatch.setattr(productos, "consultar", _boom)
    modelo.guion = [
        _respuesta(
            _tool("consultar_precios", {"producto": "taller_ceramica"}),
            stop="tool_use",
        ),
        _respuesta(_texto("Te confirmo en un momento.")),
    ]

    resultado = llm_engine.advance(bot, None, "¿cuánto vale?")
    llm_engine.record_decision(
        db_session, bot, resultado.get("telemetry"), source="whatsapp"
    )

    fila = db_session.query(models.BotLlmDecision).one()
    assert fila.fuente_datos == "fallback"
    assert fila.source == "whatsapp", "no se confunde con `source`"
