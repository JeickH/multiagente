"""El actualizador de la config del bot de viajes no puede apagar el piloto.

`scripts/actualizar_bot_viajes.py` reconstruye `llm_config` desde
`app/data/bot_viajes.py` para poder cambiar los caminos y el catálogo de medios
sin borrar el bot (el seed sí lo borra, y con él las sesiones abiertas y la
telemetría).

El problema: conservaba una lista blanca de una sola llave (`model_id`). Todo
lo demás que no viniera del archivo se perdía — y ahí vive `fuente_datos`, el
interruptor que apunta el bot al catálogo de la base. Correrlo contra
producción durante la ventana de observación del piloto lo devolvía al motor
viejo **en silencio**: el script imprimía su resumen de siempre y el bot seguía
contestando, solo que con la otra fuente de datos. Un apagón así no se ve en
ninguna alarma; se ve semanas después, en una medición que no cuadra.

La regla que fija este archivo: el archivo de datos manda sobre lo suyo, y
sobre nada más.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from app.data.bot_viajes import LLM_CONFIG

# El script vive en `scripts/`, fuera del paquete `app`.
RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from scripts import actualizar_bot_viajes as actualizador  # noqa: E402


class TestFusionar:
    def test_conserva_fuente_datos(self):
        """El defecto concreto: correr esto no puede apagar el piloto."""
        nueva = actualizador.fusionar({"fuente_datos": "productos"})

        assert nueva["fuente_datos"] == "productos"

    def test_conserva_el_model_id_fijado_a_mano(self):
        """Lo que la lista blanca vieja ya cuidaba, que se siga cuidando."""
        nueva = actualizador.fusionar({"model_id": "un-modelo-fijado-a-mano"})

        assert nueva["model_id"] == "un-modelo-fijado-a-mano"

    def test_conserva_una_llave_que_todavia_no_existe(self):
        """La parte que importa a futuro.

        La regla no es «acuérdate de agregar la llave nueva a la lista»: es que
        lo que el archivo de datos no declara, no se toca. El próximo
        interruptor operativo va a estar protegido sin que nadie edite esto —
        que es justo lo que no pasó con `fuente_datos`.
        """
        nueva = actualizador.fusionar({"interruptor_que_no_existe_aun": True})

        assert nueva["interruptor_que_no_existe_aun"] is True

    def test_el_archivo_de_datos_manda_sobre_lo_suyo(self):
        """Para eso se corre: lo que el archivo declara, se pisa."""
        nueva = actualizador.fusionar(
            {"media": {"flyer_viejo": {"url": "https://ejemplo/viejo.jpg"}}}
        )

        assert nueva["media"] == LLM_CONFIG["media"]
        assert "flyer_viejo" not in nueva["media"]

    @pytest.mark.parametrize("clave", sorted(LLM_CONFIG))
    def test_ninguna_llave_del_archivo_sobrevive_a_la_version_vieja(self, clave):
        """Una por una, para que agregar una llave al archivo no abra un hueco."""
        nueva = actualizador.fusionar({clave: "valor viejo que debe desaparecer"})

        assert nueva[clave] == LLM_CONFIG[clave]

    def test_el_assignee_fijo_si_se_borra(self):
        """La única llave que el script borra a propósito: mientras esté puesta
        gana sobre el reparto por turnos y todos los chats caen en la misma
        persona."""
        nueva = actualizador.fusionar({"assignee": "asesor_1"})

        assert "assignee" not in nueva

    def test_con_la_config_vacia_queda_exactamente_el_archivo(self):
        nueva = actualizador.fusionar({})

        assert nueva == dict(LLM_CONFIG)

    def test_no_muta_la_config_anterior_ni_el_archivo(self):
        """`dict(LLM_CONFIG)` es superficial: el archivo es un módulo importado
        una sola vez por proceso y escribirle encima contaminaría a todo el que
        lo lea después, tests incluidos."""
        anterior = {"fuente_datos": "productos"}
        antes_del_archivo = dict(LLM_CONFIG)

        actualizador.fusionar(anterior)

        assert anterior == {"fuente_datos": "productos"}
        assert LLM_CONFIG == antes_del_archivo
