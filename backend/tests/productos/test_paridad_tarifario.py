"""La prueba de oro: la capa nueva tiene que decir EXACTAMENTE lo mismo.

`services/tarifario.py` lleva meses vendiendo de verdad y cada línea de su texto
es la cicatriz de algo que se perdió: un «desde» de otro mes, un flyer que no
correspondía, una salida vencida ofrecida como disponible. Reescribir eso contra
la base y comparar «se ve bien» no es una migración, es una apuesta.

Así que no se compara a ojo. Se corren **los 127 casos** de
`tests/viajes/test_tarifario.py` con las funciones del módulo viejo
interceptadas: cada llamada ejecuta las dos implementaciones y exige que el
resultado sea idéntico —el texto, carácter por carácter— antes de devolverle al
test el valor de siempre. Si alguna difiere, falla acá con las dos versiones al
lado. Mientras esta prueba esté verde, la migración no cambió nada de lo que el
bot lee.

Se interceptan también las funciones que no producen texto (`planes_de`,
`clave_imagen`, `normalizar_hotel`, `resolver_fecha`…) para que los casos que no
llaman a `consultar` tampoco pasen de largo.

El tarifario entra a la base como **dato**, con el helper `covenas.py`. La capa
nueva no sabe qué es un hotel: cada frase de negocio viaja en
`atributos["presentacion"]`.
"""
from __future__ import annotations

import itertools
from datetime import date
from typing import Any, Dict, List, Tuple

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.services import productos, tarifario

from tests.productos import covenas
from tests.productos.conftest import crear_cuenta
from tests.viajes import test_tarifario as suite

#: Cuántos casos tiene hoy la suite del módulo viejo. Está escrito para que, si
#: mañana alguien le agrega un caso, esta prueba avise en vez de cubrir 127 de
#: 128 calladamente.
CASOS_ESPERADOS = 127


# ---------------------------------------------------------------------------
# Expandir la suite vieja: cada test con cada combinación de sus `parametrize`
# ---------------------------------------------------------------------------

def _combinaciones(fn) -> List[Dict[str, Any]]:
    marcas = [m for m in getattr(fn, "pytestmark", []) if m.name == "parametrize"]
    if not marcas:
        return [{}]
    grupos = []
    for marca in marcas:
        crudos = marca.args[0]
        nombres = (
            [n.strip() for n in crudos.split(",")]
            if isinstance(crudos, str) else list(crudos)
        )
        opciones = []
        for valores in marca.args[1]:
            if len(nombres) == 1:
                valores = (valores,)
            opciones.append(dict(zip(nombres, valores)))
        grupos.append(opciones)
    return [
        {k: v for parcial in combo for k, v in parcial.items()}
        for combo in itertools.product(*grupos)
    ]


def _casos() -> List[Tuple[str, Any, Any, Dict[str, Any]]]:
    fuera = []
    for nombre, obj in vars(suite).items():
        if isinstance(obj, type) and nombre.startswith("Test"):
            for metodo, fn in vars(obj).items():
                if metodo.startswith("test_") and callable(fn):
                    for params in _combinaciones(fn):
                        fuera.append((f"{nombre}::{metodo}", obj, fn, params))
        elif nombre.startswith("test_") and callable(obj):
            for params in _combinaciones(obj):
                fuera.append((nombre, None, obj, params))
    return fuera


CASOS = _casos()


def _id(caso) -> str:
    etiqueta, _, _, params = caso
    if not params:
        return etiqueta
    return etiqueta + "[" + "-".join(str(v) for v in params.values()) + "]"


# ---------------------------------------------------------------------------
# La base con el tarifario cargado como producto
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    team_id, bot_id = crear_cuenta(sesion, "oro")
    covenas.cargar(sesion, team_id=team_id, bot_id=bot_id)
    yield sesion, team_id, bot_id
    sesion.close()
    engine.dispose()


@pytest.fixture
def catalogo(base):
    db, team_id, bot_id = base
    cat = productos.resolver_producto(db, team_id=team_id, bot_id=bot_id, texto="")
    assert cat is not None
    return cat


# ---------------------------------------------------------------------------
# Los espías: ejecutan las dos implementaciones y exigen que coincidan
# ---------------------------------------------------------------------------

def _proyectar_viejo(plan: Dict[str, Any]) -> tuple:
    return (
        plan["inicio"], plan["fecha"], plan["multiple"], plan["doble"],
        plan["noches"], plan["dias"], plan["plan"],
    )


def _proyectar_nuevo(fila: productos.Fila) -> tuple:
    v = fila.valores
    return (
        fila.inicio.isoformat(), fila.etiqueta, v["multiple"], v["doble"],
        v["noches"], v["dias"], v["plan"],
    )


class Espia:
    """Intercepta el módulo viejo y compara cada llamada con el nuevo."""

    def __init__(self, db, team_id, bot_id, catalogo):
        self.db, self.team_id, self.bot_id = db, team_id, bot_id
        self.catalogo = catalogo
        self.comparaciones = 0
        self.textos = 0
        self.original = {
            nombre: getattr(tarifario, nombre)
            for nombre in (
                "consultar", "planes_de", "planes_vigentes", "clave_imagen",
                "normalizar_hotel", "normalizar_mes", "normalizar_presupuesto",
                "resolver_fecha", "hoy_colombia",
            )
        }

    # -- utilidades ---------------------------------------------------------
    def _variante(self, hotel: str):
        variante = productos.resolver_variante(self.catalogo, hotel)
        assert variante is not None, hotel
        return variante

    def _igual(self, viejo, nuevo, que: str):
        self.comparaciones += 1
        assert nuevo == viejo, f"{que}:\n--- viejo ---\n{viejo}\n--- nuevo ---\n{nuevo}"

    # -- las funciones interceptadas ---------------------------------------
    def consultar(self, cfg, *, hotel="", mes="", fecha="", presupuesto="", hoy=None):
        viejo = self.original["consultar"](
            cfg, hotel=hotel, mes=mes, fecha=fecha, presupuesto=presupuesto, hoy=hoy
        )
        nuevo = productos.consultar(
            self.db,
            team_id=self.team_id,
            bot_id=self.bot_id,
            variante=hotel,
            mes=mes,
            fecha=fecha,
            presupuesto=presupuesto,
            hoy=hoy,
        )
        self._igual(viejo, nuevo, f"consultar(hotel={hotel!r}, mes={mes!r}, "
                                  f"fecha={fecha!r}, presupuesto={presupuesto!r}, "
                                  f"hoy={hoy})")
        self.textos += 1
        return viejo

    def planes_de(self, hotel, mes, hoy=None):
        viejo = self.original["planes_de"](hotel, mes, hoy=hoy)
        nuevo = productos.filas_vigentes(
            self.catalogo, variante=self._variante(hotel), mes=mes, hoy=hoy
        )
        self._igual(
            [_proyectar_viejo(p) for p in viejo],
            [_proyectar_nuevo(f) for f in nuevo],
            f"planes_de({hotel!r}, {mes!r}, hoy={hoy})",
        )
        return viejo

    def planes_vigentes(self, hotel, hoy=None, mes=None):
        viejo = self.original["planes_vigentes"](hotel, hoy=hoy, mes=mes)
        nuevo = productos.filas_vigentes(
            self.catalogo, variante=self._variante(hotel), mes=mes, hoy=hoy
        )
        self._igual(
            [_proyectar_viejo(p) for p in viejo],
            [_proyectar_nuevo(f) for f in nuevo],
            f"planes_vigentes({hotel!r}, hoy={hoy}, mes={mes!r})",
        )
        return viejo

    def clave_imagen(self, cfg, hotel, mes):
        viejo = self.original["clave_imagen"](cfg, hotel, mes)
        medio = productos.clave_medio(self.catalogo, self._variante(hotel), mes)
        self._igual(viejo, medio[0] if medio else None,
                    f"clave_imagen({hotel!r}, {mes!r})")
        return viejo

    def normalizar_hotel(self, texto):
        viejo = self.original["normalizar_hotel"](texto)
        variante = productos.resolver_variante(self.catalogo, texto)
        self._igual(viejo, variante.slug if variante else None,
                    f"normalizar_hotel({texto!r})")
        return viejo

    def normalizar_mes(self, texto):
        viejo = self.original["normalizar_mes"](texto)
        self._igual(viejo, productos.normalizar_mes(texto),
                    f"normalizar_mes({texto!r})")
        return viejo

    def normalizar_presupuesto(self, texto):
        viejo = self.original["normalizar_presupuesto"](texto)
        self._igual(viejo, productos.normalizar_presupuesto(texto),
                    f"normalizar_presupuesto({texto!r})")
        return viejo

    def resolver_fecha(self, fecha, mes, hoy):
        viejo = self.original["resolver_fecha"](fecha, mes, hoy)
        self._igual(
            viejo,
            productos.resolver_fecha(self.catalogo, fecha, mes, hoy),
            f"resolver_fecha({fecha}, {mes}, {hoy})",
        )
        return viejo

    def hoy_colombia(self):
        viejo = self.original["hoy_colombia"]()
        self._igual(viejo, productos.hoy_colombia(), "hoy_colombia()")
        return viejo

    def instalar(self, monkeypatch):
        for nombre in self.original:
            monkeypatch.setattr(tarifario, nombre, getattr(self, nombre))


#: Lo que se comparó de verdad, sumado a lo largo del archivo. Un espía que se
#: quedara callado —porque cambió el nombre de una función del módulo viejo, por
#: ejemplo— dejaría pasar los 127 casos sin comparar nada.
TOTAL = {"casos": 0, "comparaciones": 0, "textos": 0}


@pytest.fixture
def espia(base, catalogo, monkeypatch):
    db, team_id, bot_id = base
    espia = Espia(db, team_id, bot_id, catalogo)
    espia.instalar(monkeypatch)
    yield espia
    TOTAL["casos"] += 1
    TOTAL["comparaciones"] += espia.comparaciones
    TOTAL["textos"] += espia.textos


# ---------------------------------------------------------------------------
# Las pruebas
# ---------------------------------------------------------------------------

def test_la_suite_vieja_sigue_teniendo_los_casos_que_creemos():
    assert len(CASOS) == CASOS_ESPERADOS


@pytest.mark.parametrize("caso", CASOS, ids=_id)
def test_el_caso_dice_lo_mismo_por_la_capa_nueva(caso, espia):
    """Corre el caso original con el módulo viejo interceptado.

    El test de siempre sigue haciendo sus propias comprobaciones (recibe el
    valor del módulo viejo, así que no se relaja ni una); lo que agrega el espía
    es la exigencia de que la capa nueva haya dicho exactamente lo mismo.
    """
    _, clase, fn, params = caso
    fn(clase(), **params) if clase is not None else fn(**params)
    assert espia.comparaciones > 0 or _sin_llamadas(caso), (
        "este caso no ejercitó ninguna función del tarifario: la comparación "
        "no cubrió nada"
    )


#: El único caso que no llama a ninguna función del módulo: lee el JSON crudo
#: con los helpers del propio test para verificar los mínimos de la temporada.
#: Su equivalente en la capa nueva es `test_las_filas_cargadas_son_las_del_json`.
SIN_LLAMADAS = {"TestNingunaCifraSeInventa::test_el_minimo_de_la_temporada_sale_de_los_datos"}


def _sin_llamadas(caso) -> bool:
    return caso[0] in SIN_LLAMADAS


def test_la_prueba_de_oro_comparo_de_verdad():
    """Que los 127 casos hayan ejercitado el número de comparaciones de siempre.

    Sin esto, el día que el módulo viejo renombre una función el espía deja de
    interceptarla, los 127 casos siguen verdes y la migración deja de estar
    protegida sin que nadie se entere.
    """
    if TOTAL["casos"] < len(CASOS):
        pytest.skip("se corrió solo una parte de los casos")
    # Los 127 casos disparan 108 respuestas completas de `consultar` y 1.253
    # comparaciones en total: las demás son las llamadas internas del propio
    # módulo viejo (busca sus filas, su medio, su alias), que quedan
    # interceptadas también y se verifican una por una.
    assert TOTAL["textos"] >= 108, TOTAL
    assert TOTAL["comparaciones"] >= 1253, TOTAL


def test_las_filas_cargadas_son_las_del_json(base, catalogo):
    """Que el helper no haya perdido ni inventado una fila al cargar.

    Es lo que sostiene a la prueba de oro: si el producto tuviera otras filas,
    los dos textos podrían coincidir y estar los dos mal.
    """
    del base
    planes = covenas.datos()["planes"]
    assert len(catalogo.filas) == len(planes)

    por_hotel = {}
    for plan in planes:
        for hotel in plan["hoteles"]:
            por_hotel.setdefault(hotel, []).append(_proyectar_viejo(plan))

    for hotel, esperadas in por_hotel.items():
        variante = productos.resolver_variante(catalogo, hotel)
        # Sin filtro de vigencia: se comparan TODAS, incluidas las que ya pasaron.
        cargadas = productos.filas_vigentes(
            catalogo, variante=variante, hoy=date(2020, 1, 1)
        )
        # Estable por fecha: dos planes que arrancan el mismo día conservan el
        # orden en que los publicó la agencia, que es lo que guarda `orden`.
        assert [_proyectar_nuevo(f) for f in cargadas] == sorted(
            esperadas, key=lambda fila: fila[0]
        ), hotel


def test_el_texto_no_nombra_el_negocio_en_el_codigo():
    """La regla que define si la capa está bien hecha.

    Si una de estas palabras aparece en `services/productos.py`, es que la capa
    dejó de ser genérica y el próximo cliente necesitará su propio módulo.
    """
    from pathlib import Path

    fuente = Path(productos.__file__).read_text(encoding="utf-8").lower()
    for palabra in (
        "hotel", "coveñas", "covenas", "amor de dios", "piedra mar", "bohío",
        "bohio", "múltiple", "multiple", "doble", "flyer", "acomodación",
    ):
        assert palabra not in fuente, palabra
