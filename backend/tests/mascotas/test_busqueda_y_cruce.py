"""Búsqueda en vivo (lo que hace el bot) y cruce diario (lo que ve el panel).

Son el mismo scoring con dos umbrales distintos, y la diferencia es deliberada
(manual §5):

- **Búsqueda en vivo, umbral 3**: la persona está en el chat y puede descartar
  una candidata de un vistazo. Mejor mostrar de más.
- **Cruce diario, umbral 12 y tope de 3 por caso**: nadie está mirando, y el
  equipo llama por teléfono. Con umbral 6 sobre 250×50 pares salieron 5.284
  coincidencias y el panel quedó inservible.
"""
from __future__ import annotations

import pytest

from app import models
from app.services import mascotas as svc

# Una perdida y su encontrada, descritas por dos personas distintas: la dueña
# dice "labrador dorado", quien la halló dice lo mismo con otras palabras.
PERDIDA = {
    "tipo_registro": "perdida", "especie": "perro", "raza": "labrador",
    "color": "dorado", "sexo": "hembra", "tamano": "grande",
    "ubicacion": "San Fernando, Cali", "barrio": "San Fernando",
    "senas": "collar rojo",
}
ENCONTRADA = {
    "tipo_registro": "encontrada", "especie": "perro", "raza": "labrador",
    "color": "amarillo", "sexo": "hembra", "tamano": "grande",
    "ubicacion": "San Fernando, Cali", "barrio": "San Fernando",
    "senas": "tenía un collar rojo",
}


class TestBuscar:
    def test_encuentra_a_la_mascota_por_su_descripcion(self, db, crear):
        crear(**ENCONTRADA)
        resultados = svc.buscar(
            db, {"especie": "perro", "raza": "labrador", "color": "dorado"}
        )
        assert len(resultados) == 1
        assert resultados[0]["coincidencia"] >= 3

    def test_busca_por_defecto_entre_las_encontradas(self, db, crear):
        """El caso normal: alguien busca a SU mascota, así que le interesan las
        que otras personas hallaron."""
        crear(**ENCONTRADA)
        crear(**PERDIDA)
        resultados = svc.buscar(db, {"especie": "perro", "raza": "labrador"})
        assert {r["tipo"] for r in resultados} == {"encontrada"}

    def test_quien_hallo_una_mascota_busca_entre_las_perdidas(self, db, crear):
        crear(**ENCONTRADA)
        crear(**PERDIDA)
        resultados = svc.buscar(
            db, {"especie": "perro", "raza": "labrador"}, buscar_en="perdidas"
        )
        assert {r["tipo"] for r in resultados} == {"perdida"}

    def test_todas_trae_los_dos_tipos(self, db, crear):
        crear(**ENCONTRADA)
        crear(**PERDIDA)
        resultados = svc.buscar(
            db, {"especie": "perro", "raza": "labrador"}, buscar_en="todas"
        )
        assert {r["tipo"] for r in resultados} == {"perdida", "encontrada"}

    def test_busca_apenas_hay_especie_y_dos_datos(self, db, crear):
        """Pedir cuatro cosas antes de buscar es el peor error con alguien
        angustiado (manual §4). Con especie + raza + color tiene que salir."""
        crear(**ENCONTRADA)
        assert svc.buscar(
            db, {"especie": "perro", "raza": "labrador", "color": "dorado"}
        )

    def test_no_devuelve_parecidos_flojos(self, db, crear):
        # Umbral 3: un solo campo débil en común no alcanza.
        crear(**ENCONTRADA)
        assert svc.buscar(db, {"especie": "perro", "nombre": "Pelusa"}) == []

    def test_otra_especie_nunca_aparece(self, db, crear):
        crear(**{**ENCONTRADA, "especie": "gato"})
        assert svc.buscar(db, {"especie": "perro", "raza": "labrador"}) == []

    def test_los_cerrados_no_aparecen(self, db, crear):
        mascota = crear(**ENCONTRADA)
        mascota.estado = "reunida"
        db.commit()
        assert svc.buscar(db, {"especie": "perro", "raza": "labrador"}) == []

    def test_las_mejores_primero(self, db, crear):
        crear(**{**ENCONTRADA, "color": "negro", "raza": "criollo"})
        exacta = crear(**ENCONTRADA)
        resultados = svc.buscar(
            db,
            {"especie": "perro", "raza": "labrador", "color": "dorado",
             "sexo": "hembra", "zona": "San Fernando"},
        )
        assert resultados[0]["codigo"] == exacta.codigo
        puntajes = [r["coincidencia"] for r in resultados]
        assert puntajes == sorted(puntajes, reverse=True)

    def test_respeta_el_limite(self, db, crear):
        for _ in range(6):
            crear(**ENCONTRADA)
        assert len(svc.buscar(db, {"especie": "perro", "raza": "labrador"})) == 4
        assert len(
            svc.buscar(db, {"especie": "perro", "raza": "labrador"}, limite=2)
        ) == 2

    def test_base_vacia_no_revienta(self, db):
        assert svc.buscar(db, {"especie": "perro", "raza": "labrador"}) == []


class TestCruceDiario:
    def test_cruza_el_par_evidente(self, db, crear):
        perdida = crear(**PERDIDA)
        encontrada = crear(**ENCONTRADA)

        resumen = svc.cruzar_reportes(db)

        assert resumen["nuevas"] == 1
        par = db.query(models.MascotaCoincidencia).one()
        assert par.perdida_id == perdida.id
        assert par.encontrada_id == encontrada.id
        assert par.score >= svc.UMBRAL_COINCIDENCIA
        assert par.estado == models.MATCH_ESTADO_NUEVA

    def test_el_detalle_explica_por_que_cruzaron(self, db, crear):
        """El equipo necesita ver el porqué antes de llamar a una familia."""
        crear(**PERDIDA)
        crear(**ENCONTRADA)
        svc.cruzar_reportes(db)
        par = db.query(models.MascotaCoincidencia).one()
        assert par.detalle
        assert sum(par.detalle.values()) == par.score

    def test_lo_flojo_no_pasa_el_umbral(self, db, crear):
        # Dos perros negros en Cali: comparten lo que comparte media base.
        crear(tipo_registro="perdida", especie="perro", color="negro",
              ubicacion="Cali")
        crear(tipo_registro="encontrada", especie="perro", color="negro",
              ubicacion="Cali")
        resumen = svc.cruzar_reportes(db)
        assert resumen["nuevas"] == 0

    def test_es_idempotente(self, db, crear):
        crear(**PERDIDA)
        crear(**ENCONTRADA)
        primera = svc.cruzar_reportes(db)
        segunda = svc.cruzar_reportes(db)

        assert primera["nuevas"] == 1
        assert segunda["nuevas"] == 0
        assert segunda["actualizadas"] == 0
        assert db.query(models.MascotaCoincidencia).count() == 1

    def test_respeta_lo_que_descarto_el_equipo(self, db, crear):
        """Una coincidencia descartada no puede volver a "nueva" al día
        siguiente: el equipo ya la miró y dijo que no."""
        crear(**PERDIDA)
        crear(**ENCONTRADA)
        svc.cruzar_reportes(db)
        par = db.query(models.MascotaCoincidencia).one()
        par.estado = models.MATCH_ESTADO_DESCARTADA
        db.commit()

        svc.cruzar_reportes(db)

        db.refresh(par)
        assert par.estado == models.MATCH_ESTADO_DESCARTADA

    def test_guarda_a_lo_sumo_tres_candidatas_por_caso(self, db, crear):
        crear(**PERDIDA)
        for _ in range(6):
            crear(**ENCONTRADA)

        svc.cruzar_reportes(db)

        assert db.query(models.MascotaCoincidencia).count() == \
            svc.MAX_COINCIDENCIAS_POR_PERDIDA

    def test_guarda_las_mejores_no_las_primeras(self, db, crear):
        crear(**PERDIDA)
        for _ in range(3):
            crear(**{**ENCONTRADA, "senas": None, "tamano": None})
        mejor = crear(**ENCONTRADA)

        svc.cruzar_reportes(db)

        guardadas = db.query(models.MascotaCoincidencia).all()
        assert mejor.id in {c.encontrada_id for c in guardadas}
        top = max(guardadas, key=lambda c: c.score)
        assert top.encontrada_id == mejor.id

    def test_los_reportes_cerrados_no_se_cruzan(self, db, crear):
        perdida = crear(**PERDIDA)
        crear(**ENCONTRADA)
        perdida.estado = "reunida"
        db.commit()

        resumen = svc.cruzar_reportes(db)

        assert resumen["perdidas"] == 0
        assert resumen["nuevas"] == 0

    def test_actualiza_el_puntaje_si_el_reporte_cambio(self, db, crear):
        perdida = crear(**PERDIDA)
        crear(**ENCONTRADA)
        svc.cruzar_reportes(db)
        antes = db.query(models.MascotaCoincidencia).one().score

        # El equipo completa un dato que faltaba: el par se parece más.
        perdida.edad = "adulto"
        db.commit()
        crear(**{**ENCONTRADA, "edad": "adulto"})
        svc.cruzar_reportes(db)

        assert db.query(models.MascotaCoincidencia).count() >= 1
        assert max(c.score for c in db.query(models.MascotaCoincidencia).all()) >= antes

    def test_umbral_configurable_para_experimentar(self, db, crear):
        crear(tipo_registro="perdida", especie="perro", color="negro",
              ubicacion="Cali")
        crear(tipo_registro="encontrada", especie="perro", color="negro",
              ubicacion="Cali")
        assert svc.cruzar_reportes(db, umbral=100)["nuevas"] == 0
        assert svc.cruzar_reportes(db, umbral=1)["nuevas"] >= 1


class TestListarCoincidencias:
    def test_las_de_mayor_puntaje_primero(self, db, crear):
        crear(**PERDIDA)
        crear(**ENCONTRADA)
        crear(**{**ENCONTRADA, "senas": None})
        svc.cruzar_reportes(db)

        puntajes = [c.score for c in svc.listar_coincidencias(db)]
        assert puntajes == sorted(puntajes, reverse=True)

    def test_filtra_por_estado(self, db, crear):
        crear(**PERDIDA)
        crear(**ENCONTRADA)
        svc.cruzar_reportes(db)
        par = db.query(models.MascotaCoincidencia).one()
        par.estado = models.MATCH_ESTADO_DESCARTADA
        db.commit()

        assert svc.listar_coincidencias(db, estado=models.MATCH_ESTADO_NUEVA) == []
        assert len(
            svc.listar_coincidencias(db, estado=models.MATCH_ESTADO_DESCARTADA)
        ) == 1
