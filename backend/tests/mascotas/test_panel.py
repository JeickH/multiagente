"""El panel privado: quién entra y qué ve.

Manual §7: **acceso solo para la cuenta de la iniciativa**; cualquier otra
recibe 403 y ni siquiera ve el menú. El panel es la única superficie donde
salen los teléfonos de las familias, así que el portero es lo primero que se
prueba aquí.
"""
from __future__ import annotations

import pytest

from app import models
from app.services import mascotas as svc


@pytest.fixture
def panel(Sesion, db, usuaria_iniciativa):
    """Cliente autenticado como la cuenta de la iniciativa."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_db
    from app.routers import mascotas as router_mascotas

    dueña = usuaria_iniciativa

    app = FastAPI()
    app.include_router(router_mascotas.router)

    def _get_db():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: dueña
    with TestClient(app) as c:
        yield c


@pytest.fixture
def intruso(Sesion, db, usuaria_iniciativa):
    """Cliente autenticado como otra cuenta cualquiera de la plataforma."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_db
    from app.routers import mascotas as router_mascotas

    ajeno = models.User(
        nombre="Otra Empresa", tipo_documento="CC", documento="123",
        correo="talulah@gloma.com", hashed_password="x",
    )
    db.add(ajeno)
    db.commit()

    app = FastAPI()
    app.include_router(router_mascotas.router)

    def _get_db():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_current_user] = lambda: ajeno
    with TestClient(app) as c:
        yield c


ENCONTRADA = {
    "tipo_registro": "encontrada", "especie": "perro", "raza": "labrador",
    "contacto_telefono": "3009998877", "contacto_nombre": "Ana",
}


class TestPortero:
    """Cada ruta privada, con la cuenta equivocada."""

    RUTAS = [
        ("get", "/mascotas/panel"),
        ("get", "/mascotas/panel/conversaciones"),
        ("get", "/mascotas/panel/export.xlsx"),
        ("get", "/mascotas/panel/export.json"),
        ("get", "/mascotas/panel/export.zip"),
        ("post", "/mascotas/panel/cruzar"),
    ]

    @pytest.mark.parametrize("metodo,ruta", RUTAS)
    def test_otra_cuenta_recibe_403(self, intruso, metodo, ruta):
        r = getattr(intruso, metodo)(ruta)
        assert r.status_code == 403

    @pytest.mark.parametrize("metodo,ruta", RUTAS)
    def test_la_cuenta_de_la_iniciativa_entra(self, panel, metodo, ruta):
        r = getattr(panel, metodo)(ruta)
        assert r.status_code == 200

    def test_el_403_no_explica_el_porqué(self, intruso):
        """Regla de seguridad #6: nada de "no eres el owner de X"."""
        r = intruso.get("/mascotas/panel")
        assert r.json()["detail"] == "No tienes acceso a este módulo"

    def test_el_menu_solo_le_aparece_a_la_iniciativa(self, panel, intruso):
        assert panel.get("/mascotas/access").json() == {"allowed": True}
        assert intruso.get("/mascotas/access").json() == {"allowed": False}

    def test_editar_y_borrar_tambien_estan_cerrados(self, intruso, crear):
        mascota = crear(**ENCONTRADA)
        assert intruso.patch(
            f"/mascotas/panel/{mascota.codigo}", json={"raza": "otra"}
        ).status_code == 403
        assert intruso.delete(
            f"/mascotas/panel/{mascota.codigo}"
        ).status_code == 403


class TestTablero:
    def test_trae_los_contadores_y_la_tabla(self, panel, crear):
        crear(**ENCONTRADA)
        crear(**{**ENCONTRADA, "tipo_registro": "perdida"})

        cuerpo = panel.get("/mascotas/panel").json()

        assert cuerpo["resumen"]["encontradas"] >= 1
        assert cuerpo["resumen"]["perdidas"] >= 1
        assert len(cuerpo["reportes"]) == 2

    def test_el_equipo_sí_ve_los_telefonos(self, panel, crear):
        """Es el único lugar donde salen: el equipo tiene que poder llamar."""
        crear(**ENCONTRADA)
        cuerpo = panel.get("/mascotas/panel").json()
        assert cuerpo["reportes"][0]["contacto_telefono"] == "3009998877"

    def test_editar_un_reporte(self, panel, db, crear):
        mascota = crear(**ENCONTRADA)
        r = panel.patch(
            f"/mascotas/panel/{mascota.codigo}", json={"raza": "golden retriever"}
        )
        assert r.status_code == 200
        db.refresh(mascota)
        assert mascota.raza == "golden retriever"

    def test_no_deja_vaciar_la_ubicacion_desde_el_panel(self, panel, crear):
        mascota = crear(**ENCONTRADA)
        r = panel.patch(f"/mascotas/panel/{mascota.codigo}", json={"ubicacion": ""})
        assert r.status_code == 400
        assert "obligatoria" in r.json()["detail"]

    def test_borrar_un_reporte(self, panel, db, crear):
        mascota = crear(**ENCONTRADA)
        assert panel.delete(f"/mascotas/panel/{mascota.codigo}").status_code == 200
        assert svc.obtener(db, mascota.codigo) is None

    def test_borrar_lo_que_no_existe_da_404(self, panel):
        assert panel.delete("/mascotas/panel/MC-99999").status_code == 404

    def test_el_boton_de_cruzar_funciona(self, panel, db, crear):
        crear(**{**ENCONTRADA, "tipo_registro": "perdida", "color": "dorado",
                 "barrio": "San Fernando", "senas": "collar rojo"})
        crear(**{**ENCONTRADA, "color": "dorado", "barrio": "San Fernando",
                 "senas": "collar rojo"})

        r = panel.post("/mascotas/panel/cruzar")

        assert r.status_code == 200
        assert r.json()["nuevas"] == 1


class TestCoincidencias:
    def test_el_equipo_puede_descartar_una(self, panel, db, crear):
        crear(**{**ENCONTRADA, "tipo_registro": "perdida", "color": "dorado",
                 "barrio": "San Fernando", "senas": "collar rojo"})
        crear(**{**ENCONTRADA, "color": "dorado", "barrio": "San Fernando",
                 "senas": "collar rojo"})
        panel.post("/mascotas/panel/cruzar")
        par = db.query(models.MascotaCoincidencia).one()

        r = panel.patch(
            f"/mascotas/panel/coincidencias/{par.id}", json={"estado": "descartada"}
        )

        assert r.status_code == 200
        db.refresh(par)
        assert par.estado == models.MATCH_ESTADO_DESCARTADA

    def test_un_estado_inventado_se_rechaza(self, panel, db, crear):
        crear(**{**ENCONTRADA, "tipo_registro": "perdida", "color": "dorado",
                 "barrio": "San Fernando", "senas": "collar rojo"})
        crear(**{**ENCONTRADA, "color": "dorado", "barrio": "San Fernando",
                 "senas": "collar rojo"})
        panel.post("/mascotas/panel/cruzar")
        par = db.query(models.MascotaCoincidencia).one()

        r = panel.patch(
            f"/mascotas/panel/coincidencias/{par.id}", json={"estado": "inventado"}
        )
        assert r.status_code in (400, 422)


class TestConversaciones:
    def test_lista_los_hilos_con_su_contacto(self, panel, db, cuenta_mascotas):
        """Manual §7: una fila por hilo, con el contacto y los caminos que
        tomó el bot."""
        db.add(models.BotLlmDecision(
            bot_id=cuenta_mascotas.id, source="mascotas", camino="buscar",
            user_input="busco mi perro", reply_preview="Claro, te ayudo",
            chat_ref="hilo-1", chat_contacto="Ana · 3001234567", rounds=1,
        ))
        db.commit()

        cuerpo = panel.get("/mascotas/panel/conversaciones").json()

        assert cuerpo["conversaciones"][0]["chat_ref"] == "hilo-1"
        assert cuerpo["conversaciones"][0]["contacto"] == "Ana · 3001234567"

    def test_el_detalle_trae_los_turnos(self, panel, db, cuenta_mascotas):
        for i in range(2):
            db.add(models.BotLlmDecision(
                bot_id=cuenta_mascotas.id, source="mascotas", camino="buscar",
                user_input=f"mensaje {i}", chat_ref="hilo-1", rounds=1,
            ))
        db.commit()

        turnos = panel.get("/mascotas/panel/conversaciones/hilo-1").json()

        assert len(turnos) == 2
        assert [t["user_input"] for t in turnos] == ["mensaje 0", "mensaje 1"]
