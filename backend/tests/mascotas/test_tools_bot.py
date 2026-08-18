"""Las herramientas del bot Huella (`llm_engine._run_tool_mascotas`).

Cada tool devuelve `(texto_para_el_modelo, terminado)` y puede empujar acciones
(mandar una foto, un archivo, cerrar el canal). El texto no lo lee el
ciudadano: lo lee el modelo, y lleva una `instruccion` que le dice qué hacer
después. Varias pruebas afirman sobre esa instrucción porque es lo que sostiene
el comportamiento del bot — si desaparece, el bot deja de pedir el teléfono
cuando no hay coincidencias, o se pone a describir mascotas de memoria.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from app import models
from app.services import llm_engine, mascotas as svc

CFG: Dict[str, Any] = {"context_key": "mascotas_cali", "mascotas": {}}

ENCONTRADA = {
    "tipo_registro": "encontrada", "especie": "perro", "raza": "labrador",
    "color": "dorado", "sexo": "hembra", "tamano": "grande",
    "ubicacion": "San Fernando, Cali", "barrio": "San Fernando",
    "senas": "collar rojo", "contacto_telefono": "3009998877",
    "contacto_nombre": "Ana",
}


def correr(nombre, entrada=None, cfg=None, runtime=None):
    """Ejecuta una tool y devuelve (resultado, terminado, acciones, notas)."""
    acciones: List[Dict[str, Any]] = []
    notas: List[str] = []
    config = dict(cfg or CFG)
    if runtime is not None:
        config["_runtime"] = runtime
    resultado, terminado = llm_engine._run_tool_mascotas(
        nombre, entrada or {}, config, acciones, notas
    )
    return resultado, terminado, acciones, notas


class TestBuscarMascota:
    def test_devuelve_las_coincidencias_con_su_resumen(self, crear):
        mascota = crear(**ENCONTRADA)
        resultado, terminado, _, _ = correr(
            "buscar_mascota",
            {"especie": "perro", "raza": "labrador", "color": "dorado"},
        )
        datos = json.loads(resultado)
        assert terminado is False
        assert len(datos["coincidencias"]) == 1
        encontrada = datos["coincidencias"][0]
        assert encontrada["codigo"] == mascota.codigo
        # El resumen es la línea que el modelo lee y le cuenta a la persona.
        assert "labrador" in encontrada["resumen"]
        assert mascota.codigo in encontrada["resumen"]

    def test_sin_coincidencias_manda_a_registrar_y_pedir_telefono(self, db):
        """Comportamiento afinado a mano (manual §4): decir que la lista se
        actualiza a diario, que el caso queda guardado, y pedir el teléfono."""
        resultado, _, _, notas = correr(
            "buscar_mascota", {"especie": "perro", "raza": "labrador"}
        )
        datos = json.loads(resultado)
        assert datos["coincidencias"] == []
        instruccion = datos["instruccion"]
        assert "actualiza" in instruccion
        assert "registrar_reporte" in instruccion
        assert "teléfono" in instruccion
        assert notas == ["buscaste y no hubo coincidencias"]

    def test_nunca_entrega_el_telefono_en_la_busqueda(self, crear):
        """La ficha pública no lleva PII: el teléfono solo sale de
        `entregar_contacto`, y solo cuando la persona reconoce a la mascota."""
        crear(**ENCONTRADA)
        resultado, _, _, _ = correr(
            "buscar_mascota", {"especie": "perro", "raza": "labrador"}
        )
        assert "3009998877" not in resultado
        assert "Ana" not in resultado
        assert "Nunca des el teléfono" in json.loads(resultado)["instruccion"]

    def test_anota_los_codigos_que_vio_para_el_turno_siguiente(self, crear):
        """El historial solo guarda el texto que dijo el bot. Sin esta nota, en
        el turno siguiente no sabe de qué reporte hablaba la persona."""
        mascota = crear(**ENCONTRADA)
        _, _, _, notas = correr(
            "buscar_mascota", {"especie": "perro", "raza": "labrador"}
        )
        assert mascota.codigo in notas[0]

    def test_busca_donde_le_pidan(self, crear):
        crear(**{**ENCONTRADA, "tipo_registro": "perdida"})
        vacio, _, _, _ = correr(
            "buscar_mascota", {"especie": "perro", "raza": "labrador"}
        )
        assert json.loads(vacio)["coincidencias"] == []

        lleno, _, _, _ = correr(
            "buscar_mascota",
            {"especie": "perro", "raza": "labrador", "buscar_en": "perdidas"},
        )
        assert len(json.loads(lleno)["coincidencias"]) == 1


class TestVerFicha:
    def test_manda_la_foto_junto_con_la_ficha(self, db, crear):
        mascota = crear(**ENCONTRADA)
        foto = svc.guardar_foto(db, b"\xff\xd8img", "image/jpeg", mascota=mascota)

        resultado, _, acciones, notas = correr("ver_ficha", {"codigo": mascota.codigo})

        assert [a["type"] for a in acciones] == ["say_media"]
        assert acciones[0]["payload"]["url"].endswith(
            f"/mascotas/foto/{mascota.codigo}/{foto.id}"
        )
        assert json.loads(resultado)["foto_enviada"] is True
        assert mascota.codigo in notas[0]

    def test_el_codigo_no_distingue_mayusculas(self, crear):
        mascota = crear(**ENCONTRADA)
        resultado, _, _, _ = correr("ver_ficha", {"codigo": mascota.codigo.lower()})
        assert "no existe" not in resultado

    def test_reporte_inexistente(self):
        resultado, terminado, acciones, _ = correr("ver_ficha", {"codigo": "MC-99999"})
        assert resultado == "no existe el reporte MC-99999"
        assert terminado is False
        assert acciones == []

    def test_un_importado_con_foto_nuestra_la_manda_igual(self, db, crear):
        """Antes los importados salían por otra rama y nunca enviaban la foto,
        aunque estuviera guardada: la persona recibía un enlace en vez del
        animal."""
        mascota = crear(
            **{**ENCONTRADA, "origen_url": "https://encontradogs.co/pet/7"},
            source="encontradogs",
        )
        svc.guardar_foto(db, b"\xff\xd8img", "image/jpeg", mascota=mascota)

        resultado, _, acciones, _ = correr("ver_ficha", {"codigo": mascota.codigo})

        assert [a["type"] for a in acciones] == ["say_media"]
        instruccion = json.loads(resultado)["instruccion"]
        assert "ya la tiene" in instruccion
        assert "encontradogs" in instruccion

    def test_un_importado_sin_foto_pasa_el_enlace(self, crear):
        mascota = crear(
            **{**ENCONTRADA, "origen_url": "https://encontradogs.co/pet/7"},
            source="encontradogs",
        )
        resultado, _, acciones, _ = correr("ver_ficha", {"codigo": mascota.codigo})
        assert acciones == []
        assert "https://encontradogs.co/pet/7" in json.loads(resultado)["instruccion"]


class TestEntregarContacto:
    def test_entrega_ubicacion_y_telefono(self, crear):
        mascota = crear(**ENCONTRADA)
        resultado, _, _, notas = correr(
            "entregar_contacto", {"codigo": mascota.codigo}, runtime={}
        )
        contacto = json.loads(resultado)["contacto"]
        assert contacto["contacto_telefono"] == "3009998877"
        assert contacto["ubicacion"] == "San Fernando, Cali"
        assert "entregaste el contacto" in notas[0]

    def test_marca_el_reporte_como_reconocido_por_confirmar(self, db, crear):
        """No pasa a "reunida": es una afirmación sin verificar. El equipo
        llama a las dos partes y confirma desde el panel."""
        mascota = crear(**ENCONTRADA)
        correr(
            "entregar_contacto", {"codigo": mascota.codigo},
            runtime={"chat_ref": "abc123"},
        )
        db.refresh(mascota)
        assert mascota.estado == models.MASCOTA_ESTADO_RECONOCIDA
        assert mascota.reconocida_at is not None
        assert mascota.reconocida_chat == "abc123"

    def test_un_importado_sin_telefono_manda_al_sitio_de_origen(self, crear):
        """La regla que impide inventar: si no tenemos teléfono, se dice."""
        mascota = crear(
            **{**ENCONTRADA, "origen_url": "https://encontradogs.co/pet/7",
               "contacto_telefono": None},
            source="encontradogs",
        )

        resultado, _, _, _ = correr(
            "entregar_contacto", {"codigo": mascota.codigo}, runtime={}
        )

        instruccion = json.loads(resultado)["instruccion"]
        assert "no debes inventar" in instruccion
        assert "https://encontradogs.co/pet/7" in instruccion

    def test_un_importado_con_telefono_entrega_las_dos_vias(self, crear):
        """PetSearch sí publica el teléfono: primero el número (quien reconoció
        a su mascota quiere marcar ya), después el enlace."""
        mascota = crear(
            **{**ENCONTRADA, "origen_url": "https://petsearch.neuralync.dev/p/9"},
            source="petsearch",
        )
        resultado, _, _, _ = correr(
            "entregar_contacto", {"codigo": mascota.codigo}, runtime={}
        )
        instruccion = json.loads(resultado)["instruccion"]
        assert "teléfono" in instruccion
        assert "https://petsearch.neuralync.dev/p/9" in instruccion

    def test_reporte_inexistente(self):
        resultado, _, _, _ = correr(
            "entregar_contacto", {"codigo": "MC-99999"}, runtime={}
        )
        assert resultado == "no existe el reporte MC-99999"


class TestRegistrarReporte:
    def test_registra_y_devuelve_el_codigo(self, db):
        runtime = {"bot_id": None, "source": "web"}
        resultado, _, _, notas = correr(
            "registrar_reporte",
            {"tipo_registro": "perdida", "especie": "perro",
             "ubicacion": "Barrio Meléndez", "contacto_telefono": "3001234567"},
            runtime=runtime,
        )
        datos = json.loads(resultado)
        assert datos["codigo"].startswith("MC-")
        # `runtime` es de ida y vuelta: el chat lo usa para no crear dos
        # reportes del mismo caso y para pegarle fotos nuevas.
        assert runtime["reportes_creados"] == [datos["codigo"]]
        assert datos["codigo"] in notas[0]

    @pytest.mark.parametrize(
        "muletilla", ["pendiente", "no sé", "por confirmar", "N/A"]
    )
    def test_rechaza_una_ubicacion_de_relleno(self, db, muletilla):
        """Cuando el modelo se siente presionado a registrar sin la ubicación,
        rellena el campo y el reporte nace inservible: nadie sabe dónde buscar."""
        resultado, _, _, _ = correr(
            "registrar_reporte",
            {"tipo_registro": "perdida", "especie": "perro",
             "ubicacion": muletilla, "contacto_telefono": "3001234567"},
            runtime={},
        )
        assert "NO registré nada" in resultado
        assert "Nunca la inventes" in resultado
        assert db.query(models.Mascota).count() == 0

    def test_le_explica_al_modelo_qué_falta(self, db):
        resultado, _, _, _ = correr(
            "registrar_reporte",
            {"tipo_registro": "perdida", "especie": "perro",
             "ubicacion": "Barrio Meléndez"},
            runtime={},
        )
        assert "teléfono" in resultado
        assert db.query(models.Mascota).count() == 0

    def test_invita_a_mandar_fotos_si_no_hubo(self, db):
        resultado, _, _, _ = correr(
            "registrar_reporte",
            {"tipo_registro": "perdida", "especie": "perro",
             "ubicacion": "Barrio Meléndez", "contacto_telefono": "3001234567"},
            runtime={},
        )
        datos = json.loads(resultado)
        assert datos["fotos_guardadas"] == 0
        assert "📎" in datos["instruccion"]

    def test_adopta_las_fotos_de_la_conversacion(self, db):
        svc.guardar_foto(db, b"\xff\xd8img", "image/jpeg", upload_session="chat-1")
        resultado, _, _, _ = correr(
            "registrar_reporte",
            {"tipo_registro": "perdida", "especie": "perro",
             "ubicacion": "Barrio Meléndez", "contacto_telefono": "3001234567"},
            runtime={"upload_session": "chat-1"},
        )
        assert json.loads(resultado)["fotos_guardadas"] == 1


class TestCompletarReporte:
    def test_agrega_datos_al_reporte_del_chat(self, db, crear):
        mascota = crear(**{**ENCONTRADA, "raza": None})
        resultado, _, _, _ = correr(
            "completar_reporte", {"codigo": mascota.codigo, "raza": "labrador"}
        )
        assert "actualizado" in resultado
        db.refresh(mascota)
        assert mascota.raza == "labrador"

    def test_reporte_inexistente(self):
        resultado, _, _, _ = correr(
            "completar_reporte", {"codigo": "MC-99999", "raza": "x"}
        )
        assert "no existe" in resultado


class TestDescargarListado:
    def test_manda_el_archivo_como_accion(self, db):
        resultado, _, acciones, notas = correr("descargar_listado", {})

        assert [a["type"] for a in acciones] == ["say_file"]
        payload = acciones[0]["payload"]
        assert payload["filename"] == "mascotas_encontradas.xlsx"
        assert "/mascotas/listado.xlsx?token=" in payload["url"]
        assert json.loads(resultado)["enlace_enviado"] is True
        assert "listado" in notas[0]

    def test_el_token_solo_autoriza_las_encontradas(self, db):
        """Regla del manual §2: el Excel es solo de encontradas. Los reportes
        de familias buscando llevan datos de contacto y no se reparten."""
        # Se descifra con la referencia que ya tenía cargada el router, no con
        # un import nuevo: `tests/test_crypto.py` recarga `app.services.crypto`
        # con otra clave, así que un `from ... import` aquí dentro toma un
        # Fernet distinto al que firmó el token y el test pasa o falla según el
        # orden en que corra la suite.
        from app.routers import mascotas as router_mascotas

        _, _, acciones, _ = correr("descargar_listado", {})
        token = acciones[0]["payload"]["url"].split("token=")[1]
        assert json.loads(router_mascotas.decrypt_secret(token))["t"] == "encontrada"


class TestFueraDeAlcance:
    def test_cierra_la_conversacion_y_pausa_el_canal(self, db):
        resultado, terminado, acciones, notas = correr(
            "finalizar_fuera_de_alcance", {"motivo": "pregunta por veterinarias"}
        )
        assert terminado is True
        assert [a["type"] for a in acciones] == ["end"]
        assert acciones[0]["payload"]["cooldown_minutos"] == llm_engine.COOLDOWN_MINUTOS
        assert "pausa" in resultado
        assert "fuera de alcance" in notas[0]


class TestErrores:
    def test_herramienta_desconocida(self, db):
        resultado, terminado, _, _ = correr("inventada", {})
        assert "desconocida" in resultado
        assert terminado is False

    def test_un_fallo_interno_no_se_le_cuenta_al_modelo(self, db, monkeypatch):
        """Regla de seguridad #6: el detalle va a `logger.exception`; hacia
        afuera solo un mensaje genérico."""
        def explota(*_a, **_k):
            raise RuntimeError("la contraseña de la BD es hunter2")

        monkeypatch.setattr(svc, "buscar", explota)
        resultado, terminado, _, _ = correr("buscar_mascota", {"especie": "perro"})

        assert json.loads(resultado) == {
            "error": "la consulta no está disponible ahora mismo"
        }
        assert "hunter2" not in resultado
        assert terminado is False
