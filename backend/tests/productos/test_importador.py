"""El importador con revisión: `scripts/importar_producto.py`.

Lo que se prueba acá no es que el script corra, es que cumpla las cuatro
promesas que lo hacen seguro de operar:

  1. cargar el mismo archivo dos veces no duplica ni una fila;
  2. lo que desaparece del archivo queda `activo = false` — nunca borrado — y
     se ve en el diff antes de que se escriba nada;
  3. un precio que cambia se ve como «cambiada», no como nueva + retirada (si
     no, el diff de una temporada sería ilegible y nadie lo miraría de verdad);
  4. `--cargar` sin `--revisar` se niega, y la revisión está atada al archivo
     por su sha256.

Casi todo corre sobre un **producto de juguete** —un taller de cerámica que no
es de ningún cliente—, por la misma razón que el resto de la suite: una prueba
escrita sobre el catálogo real termina consagrando las palabras de una agencia
dentro del código. El catálogo real aparece una sola vez, en la prueba de
paridad contra el embrión (`tests/productos/covenas.py`), y aparece como dato.
"""
from __future__ import annotations

import json
import os
import sys
import types
from datetime import date

import pytest

from app import models

from tests.productos.conftest import crear_cuenta

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
for ruta in (RAIZ, os.path.join(RAIZ, "scripts")):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

import importar_producto as importador          # noqa: E402
from productos_fuentes import base              # noqa: E402
from productos_fuentes import covenas as receta_covenas  # noqa: E402


# ---------------------------------------------------------------------------
# El producto de juguete y su "archivo del cliente"
# ---------------------------------------------------------------------------

#: (externo_id, variante, etiqueta, fecha, precio)
TALLERES = [
    ("T-001", "basico", "07/02", "2026-02-07", 120_000),
    ("T-002", "basico", "07/03", "2026-03-07", 120_000),
    ("T-003", "basico", "21/03", "2026-03-21", 150_000),
    ("T-004", "avanzado", "14/03", "2026-03-14", 260_000),
]


def escribir_archivo(ruta: str, talleres=None) -> str:
    """El 'Excel' del cliente. Un JSON, que es lo que hoy produce el conversor."""
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(
            [
                {"id": i, "variante": v, "etiqueta": e, "fecha": f, "precio": p}
                for i, v, e, f, p in (TALLERES if talleres is None else talleres)
            ],
            fh, ensure_ascii=False,
        )
    return ruta


def receta_juguete(archivo: str):
    """Una receta como las de `scripts/productos_fuentes/`, sin cliente detrás."""

    def leer(ruta: str) -> base.Catalogo:
        with open(ruta, encoding="utf-8") as fh:
            crudo = json.load(fh)
        cat = base.Catalogo(
            slug="taller_ceramica",
            nombre="Taller de cerámica",
            tipo=models.PRODUCTO_TIPO_PLAN,
            estado=models.PRODUCTO_ESTADO_PUBLICADO,
            resumen="Taller de cerámica de fin de semana.",
            atributos={"presentacion": {"precio": "precio"}},
            variantes=[
                base.Variante(slug="basico", nombre="Taller básico", orden=1),
                base.Variante(slug="avanzado", nombre="Taller avanzado", orden=2),
                base.Variante(slug="express", nombre="Taller express", orden=3,
                              precios_de="basico"),
            ],
            alias=[
                base.Alias(alias="el taller", nivel=models.ALIAS_NIVEL_PRODUCTO),
                base.Alias(alias="el pro", nivel=models.ALIAS_NIVEL_VARIANTE,
                           variante="avanzado"),
            ],
            medios=[
                base.Medio(clave="flyer_marzo", url="https://ejemplo.test/marzo.jpg",
                           variante="basico", aplica={"meses": [3]}),
            ],
        )
        for orden, fila in enumerate(crudo):
            cat.filas.append(
                base.Fila(
                    externo_id=fila["id"],
                    variante=fila["variante"],
                    tipo=models.FILA_TIPO_SALIDA,
                    etiqueta=fila["etiqueta"],
                    inicio=date.fromisoformat(fila["fecha"]),
                    valores={"precio": fila["precio"]},
                    orden=orden,
                )
            )
        return cat

    return types.SimpleNamespace(
        SLUG="taller_ceramica",
        TITULO="Taller de cerámica",
        ARCHIVO_POR_DEFECTO=archivo,
        COMO_SE_LLENO=["Cada línea del archivo es una fecha del taller."],
        leer=leer,
    )


@pytest.fixture
def taller(tmp_path, db_session, monkeypatch):
    """Cuenta, archivo, receta registrada y CLI apuntando a `tmp_path`.

    Devuelve un objeto con `correr(*argv)` —que es literalmente la línea de
    comando— y los datos que las pruebas necesitan.
    """
    team_id, bot_id = crear_cuenta(db_session, "imp")
    dueno = db_session.query(models.User).filter(
        models.User.id == db_session.query(models.Team)
        .filter(models.Team.id == team_id).first().owner_user_id
    ).first()
    # Se guardan los valores, no el objeto: `main()` cierra la sesión al salir
    # y un `User` cargado antes queda detached.
    aprobador = (dueno.id, dueno.correo)
    archivo = escribir_archivo(str(tmp_path / "talleres.json"))
    receta = receta_juguete(archivo)
    monkeypatch.setattr(importador, "RECETAS", {receta.SLUG: receta})
    monkeypatch.setattr(importador, "abrir_sesion", lambda: db_session)
    salida = str(tmp_path / "revisiones")

    def correr(*argv):
        return importador.main([receta.SLUG, "--team-id", str(team_id), "--salida", salida, *argv])

    return types.SimpleNamespace(
        team_id=team_id, bot_id=bot_id, archivo=archivo, receta=receta,
        salida=salida, correr=correr, db=db_session,
        aprobador_id=aprobador[0], aprobador_correo=aprobador[1],
        carpeta=importador.carpeta_de(salida, team_id=team_id, slug=receta.SLUG),
    )


def filas_de(db, team_id, slug="taller_ceramica"):
    producto = base.producto_de(db, team_id=team_id, slug=slug)
    return (
        db.query(models.BotProductoFila)
        .filter(models.BotProductoFila.producto_id == producto.id)
        .order_by(models.BotProductoFila.externo_id)
        .all()
    )


def aprobar(taller, *extra):
    return taller.correr("--cargar", "--aprobado-por", taller.aprobador_correo, *extra)


# ---------------------------------------------------------------------------
# El flujo, de punta a punta
# ---------------------------------------------------------------------------

class TestFlujo:
    def test_revisar_no_toca_la_base_y_deja_el_html(self, taller):
        taller.correr("--revisar")

        assert base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica") is None
        html = os.path.join(taller.carpeta, "revision.html")
        assert os.path.exists(html)
        texto = open(html, encoding="utf-8").read()
        assert "Nada se ha escrito en la base todavía" in texto
        # El diff dice lo que entra, y el HTML lo muestra.
        assert "T-001" in texto
        pendiente = json.load(open(os.path.join(taller.carpeta, "pendiente.json"), encoding="utf-8"))
        assert pendiente["diff"]["totales"]["filas_nuevas"] == len(TALLERES)
        assert pendiente["diff"]["producto"]["nuevo"] is True

    def test_cargar_escribe_el_catalogo_entero(self, taller):
        taller.correr("--revisar")
        aprobar(taller)

        producto = base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica")
        assert producto is not None
        assert producto.estado == models.PRODUCTO_ESTADO_PUBLICADO
        assert len(filas_de(taller.db, taller.team_id)) == len(TALLERES)

        variantes = {
            v.slug: v
            for v in taller.db.query(models.BotProductoVariante)
            .filter(models.BotProductoVariante.producto_id == producto.id).all()
        }
        assert set(variantes) == {"basico", "avanzado", "express"}
        # La auto-FK: express cobra lo de básico.
        assert variantes["express"].precios_de_variante_id == variantes["basico"].id

    def test_la_carga_queda_firmada_en_la_bitacora(self, taller):
        taller.correr("--revisar")
        aprobar(taller)

        carga = taller.db.query(models.BotProductoCarga).one()
        assert carga.estado == models.CARGA_ESTADO_APLICADO
        assert carga.archivo == "talleres.json"           # el nombre, no la ruta
        assert carga.hash_sha256 == base.hash_archivo(taller.archivo)
        assert carga.filas_nuevas == len(TALLERES)
        assert carga.filas_cambiadas == 0
        assert carga.filas_retiradas == 0
        assert carga.aprobado_por_user_id == taller.aprobador_id
        assert carga.diff["totales"]["filas_nuevas"] == len(TALLERES)


# ---------------------------------------------------------------------------
# Idempotencia
# ---------------------------------------------------------------------------

class TestIdempotencia:
    def test_el_mismo_archivo_dos_veces_no_duplica_nada(self, taller, capsys):
        taller.correr("--revisar")
        aprobar(taller)
        antes = [(f.variante_id, f.externo_id, f.id) for f in filas_de(taller.db, taller.team_id)]

        taller.correr("--revisar")
        aprobar(taller)

        despues = [(f.variante_id, f.externo_id, f.id) for f in filas_de(taller.db, taller.team_id)]
        assert despues == antes                    # mismas filas, y los MISMOS ids
        assert len(despues) == len(TALLERES)
        # La segunda pasada no tiene nada que hacer y lo dice.
        assert "no se escribió nada" in capsys.readouterr().out.lower()
        # Y no inventó una segunda entrada en la bitácora.
        assert taller.db.query(models.BotProductoCarga).count() == 1

    def test_el_candado_es_de_la_base_no_del_script(self, taller):
        """Si el importador se equivocara e insertara, el UNIQUE lo tumba.

        La idempotencia no depende de que este script se acuerde de buscar
        antes: `(producto_id, variante_id, externo_id)` es único en la tabla, y
        el centinela `variante_id = 0` existe para que eso también valga en las
        filas sin variante.
        """
        from sqlalchemy.exc import IntegrityError

        taller.correr("--revisar")
        aprobar(taller)
        una = filas_de(taller.db, taller.team_id)[0]

        taller.db.add(
            models.BotProductoFila(
                producto_id=una.producto_id,
                variante_id=una.variante_id,
                externo_id=una.externo_id,
                tipo=models.FILA_TIPO_SALIDA,
                valores={"precio": 1},
            )
        )
        with pytest.raises(IntegrityError):
            taller.db.flush()
        taller.db.rollback()

    def test_una_fila_sin_externo_id_no_pasa(self, taller):
        cat = taller.receta.leer(taller.archivo)
        cat.filas[0].externo_id = ""
        with pytest.raises(ValueError, match="externo_id"):
            base.comparar(None, cat)


# ---------------------------------------------------------------------------
# Lo que se retira y lo que cambia
# ---------------------------------------------------------------------------

class TestDiff:
    def test_lo_que_desaparece_se_desactiva_y_se_ve_antes(self, taller):
        taller.correr("--revisar")
        aprobar(taller)

        escribir_archivo(taller.archivo, TALLERES[:-1])      # se cae T-004
        taller.correr("--revisar")

        diff = json.load(open(os.path.join(taller.carpeta, "pendiente.json"),
                              encoding="utf-8"))["diff"]
        assert [f["externo_id"] for f in diff["filas"]["retiradas"]] == ["T-004"]
        assert diff["totales"]["filas_retiradas"] == 1
        # Y el HTML lo dice con todas las letras, antes de tocar nada.
        texto = open(os.path.join(taller.carpeta, "revision.html"), encoding="utf-8").read()
        assert "Filas que se retiran (1)" in texto
        assert "No se borra ninguna" in texto

        aprobar(taller)

        filas = {f.externo_id: f for f in filas_de(taller.db, taller.team_id)}
        assert len(filas) == len(TALLERES)          # sigue estando: no se borró
        assert filas["T-004"].activo is False
        assert filas["T-004"].valores == {"precio": 260_000}   # con su precio intacto
        assert all(filas[e].activo for e, *_ in TALLERES[:-1])

    def test_un_precio_que_cambia_es_una_fila_cambiada(self, taller):
        taller.correr("--revisar")
        aprobar(taller)

        nuevos = [list(t) for t in TALLERES]
        nuevos[1][-1] = 135_000
        escribir_archivo(taller.archivo, [tuple(t) for t in nuevos])
        taller.correr("--revisar")

        diff = json.load(open(os.path.join(taller.carpeta, "pendiente.json"),
                              encoding="utf-8"))["diff"]
        assert diff["totales"] == dict(
            diff["totales"],
            filas_nuevas=0, filas_retiradas=0, filas_cambiadas=1,
        )
        (cambiada,) = diff["filas"]["cambiadas"]
        assert cambiada["externo_id"] == "T-002"
        assert cambiada["cambios"] == {"valores": [{"precio": 120_000}, {"precio": 135_000}]}

        aprobar(taller)
        filas = {f.externo_id: f for f in filas_de(taller.db, taller.team_id)}
        assert filas["T-002"].valores == {"precio": 135_000}
        assert filas["T-002"].activo is True

    def test_quitar_una_fila_del_medio_no_ensucia_el_diff(self, taller):
        """El `orden` se corre solo, y no puede tapar el cambio que sí importa.

        Con las 102 salidas de una temporada real, borrar una fila del Excel
        deja 91 filas con el `orden` movido. Si eso entrara a «cambiadas», el
        único precio que de verdad cambió quedaría enterrado y el HTML dejaría
        de mirarse.
        """
        taller.correr("--revisar")
        aprobar(taller)

        nuevos = [list(t) for t in TALLERES]
        nuevos[3][-1] = 275_000              # la última: un precio que sí cambia
        del nuevos[1]                        # y una del medio que se cae
        escribir_archivo(taller.archivo, [tuple(t) for t in nuevos])
        taller.correr("--revisar")

        diff = json.load(open(os.path.join(taller.carpeta, "pendiente.json"),
                              encoding="utf-8"))["diff"]
        assert [f["externo_id"] for f in diff["filas"]["retiradas"]] == ["T-002"]
        assert [f["externo_id"] for f in diff["filas"]["cambiadas"]] == ["T-004"]
        # T-004 también se corrió de lugar, pero cambió de precio: manda el
        # cambio de verdad. Solo T-003 se movió y nada más.
        assert [f["externo_id"] for f in diff["filas"]["reordenadas"]] == ["T-003"]
        assert diff["totales"]["filas_cambiadas"] == 1

        aprobar(taller)
        filas = {f.externo_id: f for f in filas_de(taller.db, taller.team_id)}
        assert filas["T-004"].valores == {"precio": 275_000}
        assert (filas["T-003"].orden, filas["T-004"].orden) == (1, 2)   # sí se escribió
        # Y la bitácora cuenta el cambio real, no los corrimientos.
        ultima = taller.db.query(models.BotProductoCarga).order_by(
            models.BotProductoCarga.id.desc()).first()
        assert (ultima.filas_nuevas, ultima.filas_cambiadas, ultima.filas_retiradas) == (0, 1, 1)

    def test_una_fila_retirada_que_vuelve_se_reactiva(self, taller):
        taller.correr("--revisar")
        aprobar(taller)
        escribir_archivo(taller.archivo, TALLERES[:-1])
        taller.correr("--revisar")
        aprobar(taller)
        retirada = {f.externo_id: f.id for f in filas_de(taller.db, taller.team_id)}["T-004"]

        escribir_archivo(taller.archivo, TALLERES)            # vuelve a publicarse
        taller.correr("--revisar")
        diff = json.load(open(os.path.join(taller.carpeta, "pendiente.json"),
                              encoding="utf-8"))["diff"]
        assert [f["externo_id"] for f in diff["filas"]["reactivadas"]] == ["T-004"]
        assert diff["totales"]["filas_nuevas"] == 0          # no es un alta

        aprobar(taller)
        filas = {f.externo_id: f for f in filas_de(taller.db, taller.team_id)}
        assert filas["T-004"].activo is True
        assert filas["T-004"].id == retirada                  # la misma fila de siempre


# ---------------------------------------------------------------------------
# La revisión es obligatoria y está atada al archivo
# ---------------------------------------------------------------------------

class TestRevisionObligatoria:
    def test_cargar_sin_revisar_se_niega(self, taller):
        with pytest.raises(SystemExit) as exc:
            aprobar(taller)
        assert "revisar" in str(exc.value).lower()
        assert base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica") is None

    def test_el_hash_cambia_si_el_archivo_cambia(self, taller):
        antes = base.hash_archivo(taller.archivo)
        assert antes == base.hash_archivo(taller.archivo)       # estable
        nuevos = [list(t) for t in TALLERES]
        nuevos[0][-1] = 999_000
        escribir_archivo(taller.archivo, [tuple(t) for t in nuevos])
        assert base.hash_archivo(taller.archivo) != antes

    def test_si_el_archivo_cambio_despues_de_la_revision_no_carga(self, taller):
        taller.correr("--revisar")
        nuevos = [list(t) for t in TALLERES]
        nuevos[0][-1] = 999_000
        escribir_archivo(taller.archivo, [tuple(t) for t in nuevos])

        with pytest.raises(SystemExit) as exc:
            aprobar(taller)
        assert "sha256" in str(exc.value)
        assert base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica") is None

    def test_si_la_base_se_movio_pide_revisar_otra_vez(self, taller):
        """El diff que se aplica tiene que ser el que alguien miró.

        Entre la revisión y la carga puede haber pasado otra carga, o una
        edición desde la app. El archivo es el mismo —el hash coincide— pero lo
        que entraría ya no es lo aprobado.
        """
        # Se revisa el archivo completo y se guarda esa aprobación…
        taller.correr("--revisar")
        pendiente = os.path.join(taller.carpeta, "pendiente.json")
        aprobado = open(pendiente, encoding="utf-8").read()

        # …pero mientras tanto entró otra carga, con tres de las cuatro fechas.
        escribir_archivo(taller.archivo, TALLERES[:-1])
        taller.correr("--revisar")
        aprobar(taller)

        # Ahora vuelve el archivo aprobado (mismo hash) con su pendiente.
        escribir_archivo(taller.archivo, TALLERES)
        open(pendiente, "w", encoding="utf-8").write(aprobado)

        with pytest.raises(SystemExit) as exc:
            aprobar(taller)
        assert "ya no es el que se aprobó" in str(exc.value)

    def test_aprobado_por_tiene_que_existir(self, taller):
        taller.correr("--revisar")
        with pytest.raises(SystemExit) as exc:
            taller.correr("--cargar", "--aprobado-por", "quien.sea@ejemplo.test")
        assert "No existe el usuario" in str(exc.value)


# ---------------------------------------------------------------------------
# El candado de la ventana de observación
# ---------------------------------------------------------------------------

class TestVentanaDeFallback:
    def _encender(self, taller, **extra):
        bot = taller.db.query(models.Bot).filter(models.Bot.id == taller.bot_id).one()
        bot.llm_config = json.dumps({"fuente_datos": "productos", **extra})
        taller.db.commit()

    def test_sin_bots_en_productos_no_molesta(self, taller):
        assert base.bots_en_ventana(taller.db, team_id=taller.team_id) == []
        taller.correr("--revisar")
        aprobar(taller)
        assert base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica")

    def test_con_la_ventana_abierta_pide_confirmacion(self, taller):
        self._encender(taller)
        taller.correr("--revisar")

        with pytest.raises(SystemExit) as exc:
            aprobar(taller)
        assert "ventana de observación" in str(exc.value)
        assert "--acepto-ventana-abierta" in str(exc.value)
        assert base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica") is None

        # El aviso también está en el HTML que mira el CEO, no solo en la consola.
        texto = open(os.path.join(taller.carpeta, "revision.html"), encoding="utf-8").read()
        assert "ventana de observación del fallback sigue abierta" in texto

    def test_con_la_confirmacion_explicita_carga(self, taller):
        self._encender(taller)
        taller.correr("--revisar")
        aprobar(taller, "--acepto-ventana-abierta")
        assert base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica")

    def test_una_ventana_cerrada_no_frena_nada(self, taller):
        self._encender(taller, productos_ventana_hasta="2026-01-01")
        assert base.bots_en_ventana(taller.db, team_id=taller.team_id,
                                    hoy=date(2026, 6, 1)) == []
        taller.correr("--revisar")
        aprobar(taller)
        assert base.producto_de(taller.db, team_id=taller.team_id, slug="taller_ceramica")

    def test_sin_fecha_anotada_la_ventana_se_asume_abierta(self, taller):
        """Fail-closed: la ventana se cierra cuando alguien lo decide y lo escribe."""
        self._encender(taller)
        (abierta,) = base.bots_en_ventana(taller.db, team_id=taller.team_id)
        assert abierta["bot_id"] == taller.bot_id and abierta["hasta"] is None


# ---------------------------------------------------------------------------
# El catálogo real: paridad contra el embrión
# ---------------------------------------------------------------------------

class TestCovenas:
    """El tarifario completo, y que dé lo mismo que `tests/productos/covenas.py`.

    El embrión es lo que hoy sostiene la prueba de oro (`test_paridad_tarifario`):
    si el importador construye otro catálogo, la migración del piloto no sería
    la que quedó probada.
    """

    @pytest.fixture
    def cargado(self, db_session, tmp_path, monkeypatch):
        team_id, bot_id = crear_cuenta(db_session, "cov")
        archivo = receta_covenas.ARCHIVO_POR_DEFECTO
        monkeypatch.setattr(importador, "RECETAS", {receta_covenas.SLUG: receta_covenas})
        monkeypatch.setattr(importador, "abrir_sesion", lambda: db_session)
        salida = str(tmp_path / "rev")
        argv = [receta_covenas.SLUG, "--team-id", str(team_id), "--salida", salida]
        importador.main(argv + ["--revisar"])
        dueno = db_session.query(models.User).order_by(models.User.id.desc()).first()
        importador.main(argv + ["--cargar", "--aprobado-por", str(dueno.id)])
        return team_id, archivo

    def test_el_tarifario_completo_entra(self, db_session, cargado):
        team_id, _ = cargado
        cat = base.estado_actual(db_session, team_id=team_id, slug=receta_covenas.SLUG)

        assert len(cat.filas) == 102
        assert len(cat.variantes) == 3
        assert len(cat.medios) == 13
        assert len(cat.alias) == 12
        # Una variante comparte la tabla de precios con otra.
        comparte = {v.slug: v.precios_de for v in cat.variantes}
        assert comparte == {"amor_de_dios": None, "piedra_mar": None, "bohios": "amor_de_dios"}
        # Los flyers llevan sus meses; el resto del catálogo, no.
        con_meses = [m for m in cat.medios if m.aplica.get("meses")]
        assert len(con_meses) == 4
        assert all(m.variante for m in con_meses)

    def test_cargarlo_dos_veces_deja_las_mismas_102_filas(
        self, db_session, tmp_path, monkeypatch, cargado
    ):
        team_id, _ = cargado
        antes = {f.id: (f.externo_id, f.valores) for f in db_session.query(models.BotProductoFila).all()}
        salida = str(tmp_path / "rev2")
        argv = [receta_covenas.SLUG, "--team-id", str(team_id), "--salida", salida]
        importador.main(argv + ["--revisar"])
        dueno = db_session.query(models.User).order_by(models.User.id.desc()).first()
        importador.main(argv + ["--cargar", "--aprobado-por", str(dueno.id)])

        despues = {f.id: (f.externo_id, f.valores) for f in db_session.query(models.BotProductoFila).all()}
        assert despues == antes
        assert len(despues) == 102

    def test_paridad_con_el_embrion(self, db_session, cargado):
        """Mismo catálogo que el helper de los tests, campo por campo."""
        from tests.productos import covenas as embrion

        team_importado, _ = cargado
        team_embrion, _ = crear_cuenta(db_session, "emb")
        embrion.cargar(db_session, team_id=team_embrion, slug=receta_covenas.SLUG)

        uno = base.estado_actual(db_session, team_id=team_importado, slug=receta_covenas.SLUG)
        dos = base.estado_actual(db_session, team_id=team_embrion, slug=receta_covenas.SLUG)

        for campo in base.CAMPOS_PRODUCTO:
            assert getattr(uno, campo) == getattr(dos, campo), campo
        assert uno.variantes == dos.variantes
        assert sorted((a.nivel, a.alias, a.variante) for a in uno.alias) == \
               sorted((a.nivel, a.alias, a.variante) for a in dos.alias)
        assert uno.filas == dos.filas

        # Los medios son la única diferencia, y es deliberada: el embrión solo
        # carga los cuatro flyers de tarifario porque es lo único que necesita
        # para comparar el TEXTO del motor viejo. El importador trae el catálogo
        # entero del bot (13 piezas), que es lo que pidió el CEO para la carga
        # real. Sobre los cuatro que ambos tienen, coinciden en todo salvo que
        # el importador conserva además el `camino` de `llm_config`.
        del_embrion = {m.clave: m for m in dos.medios}
        del_importador = {m.clave: m for m in uno.medios}
        assert set(del_embrion) < set(del_importador)
        assert len(del_embrion) == 4 and len(del_importador) == 13
        for clave, esperado in del_embrion.items():
            tiene = del_importador[clave]
            assert (tiene.url, tiene.tipo, tiene.descripcion, tiene.variante) == \
                   (esperado.url, esperado.tipo, esperado.descripcion, esperado.variante)
            assert tiene.aplica["meses"] == esperado.aplica["meses"]
            assert tiene.aplica.keys() == {"meses", "camino"}
