"""Alta, corrección y borrado de reportes.

Las validaciones de aquí son las que impiden que nazca un reporte inservible.
Las dos que más importan (manual §2, regla 3): **ubicación y teléfono son
obligatorios; se pueden corregir, nunca vaciar**. Un reporte sin dónde buscar
ni a quién llamar no reúne a nadie, y ocupa un lugar en el cruce.

El mensaje de error de `crear_reporte` va **al modelo**, no al ciudadano: es lo
que le dice al bot qué volver a pedir. Por eso varios tests miran el texto.
"""
from __future__ import annotations

import pytest

from app import models
from app.services import mascotas as svc

BASE = {
    "tipo_registro": "encontrada",
    "especie": "perro",
    "ubicacion": "Barrio San Fernando, Cali",
    "contacto_telefono": "3001234567",
}


class TestCrearReporte:
    def test_reporte_minimo_valido(self, db):
        mascota, problema = svc.crear_reporte(db, dict(BASE))
        assert problema == ""
        assert mascota is not None
        assert mascota.estado == models.MASCOTA_ESTADO_ACTIVO
        assert mascota.source == "web"

    def test_el_codigo_se_deriva_del_id(self, db):
        primera, _ = svc.crear_reporte(db, dict(BASE))
        segunda, _ = svc.crear_reporte(db, dict(BASE))
        assert primera.codigo == f"MC-{primera.id:05d}"
        assert segunda.codigo != primera.codigo

    @pytest.mark.parametrize("tipo", ["perdida", "encontrada"])
    def test_los_dos_tipos_validos(self, db, tipo):
        mascota, problema = svc.crear_reporte(db, {**BASE, "tipo_registro": tipo})
        assert problema == ""
        assert mascota.tipo_registro == tipo

    @pytest.mark.parametrize("invalido", ["", "perdido", "encontrado", "otra cosa", None])
    def test_tipo_invalido_se_rechaza(self, db, invalido):
        mascota, problema = svc.crear_reporte(db, {**BASE, "tipo_registro": invalido})
        assert mascota is None
        assert "perdida" in problema and "encontrada" in problema

    def test_sin_especie_no_se_crea(self, db):
        mascota, problema = svc.crear_reporte(db, {**BASE, "especie": ""})
        assert mascota is None
        assert "perro, gato u otra" in problema

    @pytest.mark.parametrize("vacia", ["", "   ", None])
    def test_sin_ubicacion_no_se_crea(self, db, vacia):
        """Regla 3 del manual: la ubicación es obligatoria."""
        mascota, problema = svc.crear_reporte(db, {**BASE, "ubicacion": vacia})
        assert mascota is None
        assert "ubicación" in problema

    def test_sin_via_de_contacto_no_se_crea(self, db):
        datos = {**BASE}
        datos.pop("contacto_telefono")
        mascota, problema = svc.crear_reporte(db, datos)
        assert mascota is None
        assert "teléfono" in problema

    @pytest.mark.parametrize(
        "telefono",
        ["3001234567", "300 123 4567", "+57 300 123 4567", "602 555 3311",
         "3001234567 / 3109876543"],
    )
    def test_formatos_de_telefono_que_la_gente_escribe(self, db, telefono):
        # Dos números separados por `/` es el caso del hogar de paso: la
        # fundación y la casa donde el animal está durmiendo.
        mascota, problema = svc.crear_reporte(db, {**BASE, "contacto_telefono": telefono})
        assert problema == "", f"{telefono!r} debería aceptarse"
        assert mascota is not None

    @pytest.mark.xfail(
        strict=True,
        reason=(
            "`_TELEFONO_RE` exige que el primer carácter sea `+` o un dígito, "
            "pero acepta paréntesis en el resto: un fijo escrito como "
            "'(602) 555-3311' se rechaza. El propio `llm_engine` usa ese formato "
            "como ejemplo de teléfono válido en `_TELEFONO_EN_TEXTO_RE`, así que "
            "las dos expresiones no están de acuerdo. Impacto bajo — el bot "
            "vuelve a pedirlo — pero le cuesta un turno a alguien que escribió "
            "bien su número. Arreglo: permitir `(` inicial."
        ),
    )
    def test_un_fijo_con_indicativo_entre_parentesis(self, db):
        _, problema = svc.crear_reporte(
            db, {**BASE, "contacto_telefono": "(602) 555-3311"}
        )
        assert problema == ""

    @pytest.mark.parametrize("basura", ["no tengo", "abc", "12", "llámame"])
    def test_telefono_que_no_es_telefono_se_rechaza(self, db, basura):
        mascota, problema = svc.crear_reporte(db, {**BASE, "contacto_telefono": basura})
        assert mascota is None
        assert "no parece válido" in problema

    def test_un_importado_entra_sin_telefono_si_trae_origen_url(self, db):
        """Las plataformas hermanas no publican el teléfono: el contacto se
        resuelve mandando a su ficha original (manual §2, regla 3)."""
        datos = {**BASE, "origen_url": "https://encontradogs.co/pet/123",
                 "origen_id": "123"}
        datos.pop("contacto_telefono")
        mascota, problema = svc.crear_reporte(db, datos, source="encontradogs")
        assert problema == ""
        assert mascota.contacto_telefono is None
        assert mascota.origen_url.endswith("/123")
        # Marca de cuándo lo trajimos, para poder auditar la sincronización.
        assert mascota.sincronizado_at is not None

    def test_la_especie_se_normaliza_al_guardar(self, db):
        mascota, _ = svc.crear_reporte(db, {**BASE, "especie": "perrito"})
        assert mascota.especie == "perro"

    def test_especie_otra_conserva_lo_que_dijo_la_persona(self, db):
        mascota, _ = svc.crear_reporte(
            db, {**BASE, "especie": "conejo", "especie_otra": "conejo"}
        )
        assert mascota.especie == "otra"
        assert mascota.especie_otra == "conejo"

    def test_los_textos_se_recortan_al_limite_de_la_columna(self, db):
        mascota, _ = svc.crear_reporte(db, {**BASE, "raza": "x" * 500})
        assert len(mascota.raza) == 80

    def test_los_booleanos_son_tri_estado(self, db):
        """NULL es «la fuente no lo dice», que no es lo mismo que False."""
        mascota, _ = svc.crear_reporte(
            db, {**BASE, "esterilizado": "si", "vacunado": "no", "desparasitado": ""}
        )
        assert mascota.esterilizado is True
        assert mascota.vacunado is False
        assert mascota.desparasitado is None

    def test_peso_cero_de_la_fuente_no_se_guarda(self, db):
        # Protección Animal manda peso_animal=0 en todas sus fichas, y un animal
        # de 0 kg no existe.
        mascota, _ = svc.crear_reporte(db, {**BASE, "peso_kg": 0})
        assert mascota.peso_kg is None

    def test_adopta_las_fotos_que_se_subieron_durante_el_chat(self, db):
        """La gente manda las fotos antes de que el bot termine de preguntar."""
        foto = svc.guardar_foto(db, b"\xff\xd8imagen", "image/jpeg", upload_session="s1")
        assert foto.mascota_id is None

        mascota, _ = svc.crear_reporte(db, dict(BASE), upload_session="s1")
        db.refresh(foto)
        assert foto.mascota_id == mascota.id
        assert foto.upload_session is None
        assert foto.storage_key.startswith(f"mascotas/{mascota.codigo}/")


class TestActualizarReporte:
    """La vía del bot: la gente da los datos de a poco, así que solo agrega."""

    def test_completa_lo_que_faltaba(self, db, crear):
        mascota = crear(raza=None)
        actualizada, problema = svc.actualizar_reporte(
            db, mascota.codigo, {"raza": "labrador", "color": "dorado"}
        )
        assert problema == ""
        assert actualizada.raza == "labrador"
        assert actualizada.color == "dorado"

    def test_el_codigo_no_distingue_mayusculas(self, db, crear):
        mascota = crear()
        _, problema = svc.actualizar_reporte(
            db, mascota.codigo.lower(), {"raza": "criollo"}
        )
        assert problema == ""

    def test_codigo_inexistente(self, db):
        mascota, problema = svc.actualizar_reporte(db, "MC-99999", {"raza": "x"})
        assert mascota is None
        assert "no existe" in problema

    def test_un_valor_vacio_no_borra_lo_que_ya_habia(self, db, crear):
        """El bot solo agrega: si el modelo manda "" no puede vaciar la zona."""
        mascota = crear(barrio="San Fernando")
        actualizada, _ = svc.actualizar_reporte(db, mascota.codigo, {"barrio": ""})
        assert actualizada.barrio == "San Fernando"

    def test_sin_datos_nuevos_lo_dice(self, db, crear):
        mascota = crear()
        _, problema = svc.actualizar_reporte(db, mascota.codigo, {})
        assert problema == "no había datos nuevos que guardar"


class TestEditarDesdePanel:
    """La vía del equipo: puede corregir y vaciar opcionales, pero no los dos
    campos que sostienen todo."""

    def test_corrige_un_campo(self, db, crear):
        mascota = crear(raza="labradr")
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"raza": "labrador"}
        )
        assert problema == ""
        assert editada.raza == "labrador"

    def test_puede_vaciar_un_campo_opcional(self, db, crear):
        mascota = crear(senas="collar azul")
        editada, problema = svc.editar_desde_panel(db, mascota.codigo, {"senas": ""})
        assert problema == ""
        assert editada.senas is None

    @pytest.mark.parametrize("vacia", ["", "   ", None])
    def test_no_puede_vaciar_la_ubicacion(self, db, crear, vacia):
        mascota = crear()
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"ubicacion": vacia}
        )
        assert editada is None
        assert "obligatoria" in problema
        db.refresh(mascota)
        assert mascota.ubicacion  # sigue intacta

    @pytest.mark.parametrize("vacio", ["", "   ", None])
    def test_no_puede_vaciar_el_telefono(self, db, crear, vacio):
        mascota = crear()
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"contacto_telefono": vacio}
        )
        assert editada is None
        assert "obligatorio" in problema

    def test_el_telefono_corregido_se_valida(self, db, crear):
        mascota = crear()
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"contacto_telefono": "no tengo"}
        )
        assert editada is None
        assert "no parece válido" in problema

    def test_cambiar_el_tipo_de_registro(self, db, crear):
        mascota = crear(tipo_registro="perdida")
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"tipo_registro": "encontrada"}
        )
        assert problema == ""
        assert editada.tipo_registro == "encontrada"

    def test_tipo_invalido_se_rechaza(self, db, crear):
        mascota = crear()
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"tipo_registro": "extraviada"}
        )
        assert editada is None
        assert "perdida" in problema

    def test_estado_invalido_se_rechaza(self, db, crear):
        mascota = crear()
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"estado": "inventado"}
        )
        assert editada is None
        assert problema == "Estado inválido"

    def test_fecha_mal_formada_se_rechaza(self, db, crear):
        mascota = crear()
        editada, problema = svc.editar_desde_panel(
            db, mascota.codigo, {"fecha_evento": "13/08/2026"}
        )
        assert editada is None
        assert "AAAA-MM-DD" in problema

    def test_un_booleano_puede_volver_a_no_sabemos(self, db, crear):
        mascota = crear(esterilizado=True)
        editada, _ = svc.editar_desde_panel(db, mascota.codigo, {"esterilizado": ""})
        assert editada.esterilizado is None


class TestEliminar:
    """Regla 1 del manual: nunca se borra sin confirmación del CEO. El servicio
    sí tiene que saber borrar bien cuando se lo piden desde el panel."""

    def test_borra_el_reporte_y_su_archivo(self, db, crear, medios):
        mascota = crear()
        foto = svc.guardar_foto(db, b"\xff\xd8imagen", "image/jpeg", mascota=mascota)
        archivo = medios / foto.storage_key
        assert archivo.exists()

        assert svc.eliminar_reporte(db, mascota.codigo) is True
        assert svc.obtener(db, mascota.codigo) is None
        assert not archivo.exists(), "el archivo quedaría huérfano pagando storage"

    def test_borrar_lo_que_no_existe_no_revienta(self, db):
        assert svc.eliminar_reporte(db, "MC-99999") is False

    def test_borra_una_sola_foto(self, db, crear, medios):
        mascota = crear()
        una = svc.guardar_foto(db, b"\xff\xd8uno", "image/jpeg", mascota=mascota)
        otra = svc.guardar_foto(db, b"\xff\xd8dos", "image/jpeg", mascota=mascota)

        assert svc.eliminar_foto(db, mascota.codigo, una.id) is True
        db.refresh(mascota)
        assert [f.id for f in mascota.fotos] == [otra.id]

    def test_no_se_puede_borrar_la_foto_de_otro_reporte(self, db, crear):
        mia = crear()
        ajena = crear()
        foto = svc.guardar_foto(db, b"\xff\xd8x", "image/jpeg", mascota=ajena)
        assert svc.eliminar_foto(db, mia.codigo, foto.id) is False
