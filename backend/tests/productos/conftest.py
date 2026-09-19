"""Base en memoria, dos cuentas y un producto de juguete.

Dos cuentas y no una porque el peor error posible de este esquema es un bot
cotizando con los precios de otra agencia: sin una segunda cuenta poblada, un
`WHERE team_id` que falte pasa todas las pruebas.

El producto de juguete es inventado a propósito. La capa nueva tiene que servir
para los siete bots del portafolio, y una suite escrita sobre el catálogo real
de un cliente termina consagrando sus palabras dentro del código. El catálogo
real entra una sola vez, en la prueba de oro, y entra como **dato**.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.services import productos

#: Mitad de temporada del producto de juguete: hay talleres por delante y ya
#: quedaron dos atrás. Va por parámetro en cada consulta; si se leyera del
#: reloj, la suite empezaría a fallar sola el día que pase el último.
HOY = date(2026, 3, 10)


@pytest.fixture(autouse=True)
def _cache_limpia():
    """La caché es de proceso y dos tests reusan los mismos ids.

    Sin esto, el segundo test de cada archivo leería el catálogo que dejó el
    primero — en una base que ya no existe.
    """
    productos.limpiar_cache()
    yield
    productos.limpiar_cache()


@pytest.fixture
def db_session():
    from app.database import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    sesion = Sesion()
    yield sesion
    sesion.close()
    engine.dispose()


def crear_cuenta(db, sufijo: str) -> tuple:
    """Una cuenta con su bot. Devuelve (team_id, bot_id).

    Las filas se insertan a mano en vez de pasar por `crud.create_user`: acá no
    se autentica a nadie y el hash de bcrypt cuesta ~0,15 s por cuenta, que
    multiplicado por la suite es más de lo que tarda todo lo demás junto. El
    `hashed_password` es un relleno que no es el hash de ninguna clave.
    """
    user = models.User(
        nombre=f"Dueña {sufijo}",
        tipo_documento="CC",
        documento=f"PRD-{sufijo}",
        correo=f"duena.{sufijo}@test.com",
        hashed_password="sin-clave-no-se-autentica-en-estas-pruebas",
    )
    db.add(user)
    db.flush()
    team = models.Team(nombre=f"Cuenta {sufijo}", owner_user_id=user.id)
    db.add(team)
    db.flush()
    bot = models.Bot(
        user_id=user.id, team_id=team.id, name=f"Bot {sufijo}", engine="llm"
    )
    db.add(bot)
    db.commit()
    return team.id, bot.id


@pytest.fixture
def cuenta_a(db_session):
    return crear_cuenta(db_session, "a")


@pytest.fixture
def cuenta_b(db_session):
    return crear_cuenta(db_session, "b")


# ---------------------------------------------------------------------------
# El producto de juguete
# ---------------------------------------------------------------------------

#: Un taller de cerámica: tres versiones, una de ellas sin tabla propia. No
#: tiene nada que ver con ningún cliente real, que es justamente el punto.
JUGUETE = {
    "presentacion": {
        "encabezado": ["{producto} — al {hoy}."],
        "cierre": ["No le mandes el archivo de precios al cliente."],
        "sin_periodo": "¿Para qué mes? Pregúntale y vuelve a consultar.",
        "variante_desconocida": "No reconozco '{texto}'. Hay: {variantes}.",
        "aviso_vencido": "OJO: el {fecha} ya pasó.",
        "duracion": "{horas} horas",
        "nota_fila": ", {promocion}",
        "fila": "  · {etiqueta} — {valor_pesos} ({duracion}{obs}){marca}",
        "fila_marcada": "  <-- la fecha que pidió",
        "bloque_titulo": "{variante} — {periodo} ({n} fechas):",
        "bloque_tope": "  (y {n} más sin listar.)",
        "vacio": "{variante} — {periodo}: no hay nada abierto.",
        "vacio_periodos": "  Meses con cupo en {variante}: {periodos}.",
        "vacio_cierre": "  Dile cuáles sí hay.",
        "fecha_sin_fila": "  OJO: no hay nada el {fecha} en {variante}. Cerca: {cercanas}.",
        "fila_cercana": "{etiqueta}",
        "medio": "  OBLIGATORIO: envía `{clave}` con `enviar_media`.",
        "nota_precios_compartidos": "{variante} cuesta lo mismo que {origen}.",
        "ambito_global": "todo el semestre",
        "desde_periodo": "{grupo} — «desde» de {ambito}: {precio} ({etiqueta}).",
        "desde_global": "{grupo} — «desde» de {ambito}: {precio} ({etiqueta}).",
        "presupuesto_titulo": "PRESUPUESTO de {tope} sobre {ambito}.",
        "presupuesto_si": "  Sí le alcanza: {total}.",
        "presupuesto_si_tope": "  Sí le alcanza: {total}. Van {n}:",
        "presupuesto_nada": "  Con {tope} no alcanza en {ambito}.",
        "presupuesto_nada_mejor": "  Lo más económico:",
        "fila_presupuesto": "  · {variante} — {etiqueta}: {valor_pesos}",
        "presupuesto_restantes": "  (y {n} más, hasta {precio}.)",
        "precio": "valor",
    }
}

#: (slug, nombre, orden, comparte precios con)
VARIANTES_JUGUETE = [
    ("basico", "Taller básico", 1, None),
    ("avanzado", "Taller avanzado", 2, None),
    ("express", "Taller express", 3, "basico"),
]

#: (slug de la variante, fecha, valor, horas, promoción)
FECHAS_JUGUETE = [
    ("basico", date(2026, 2, 7), 120_000, 4, ""),
    ("basico", date(2026, 3, 7), 120_000, 4, ""),
    ("basico", date(2026, 3, 21), 150_000, 6, "incluye esmaltes"),
    ("basico", date(2026, 4, 11), 130_000, 4, ""),
    ("avanzado", date(2026, 3, 14), 260_000, 8, ""),
    ("avanzado", date(2026, 5, 9), 240_000, 8, ""),
]


def crear_juguete(
    db,
    *,
    team_id: int,
    bot_id=None,
    slug: str = "taller_ceramica",
    estado: str = models.PRODUCTO_ESTADO_PUBLICADO,
    fechas=None,
    presentacion=None,
) -> models.BotProducto:
    producto = models.BotProducto(
        team_id=team_id,
        slug=slug,
        tipo=models.PRODUCTO_TIPO_PLAN,
        nombre="Taller de cerámica",
        estado=estado,
        resumen="Taller de cerámica de fin de semana.",
        # `{}` es un valor legítimo —un producto sin plantillas, que usa las del
        # módulo—, así que no puede confundirse con «no me pasaron nada».
        atributos=JUGUETE if presentacion is None else presentacion,
    )
    db.add(producto)
    db.flush()

    variantes = {}
    for slug_v, nombre, orden, _ in VARIANTES_JUGUETE:
        variante = models.BotProductoVariante(
            producto_id=producto.id, slug=slug_v, nombre=nombre, orden=orden
        )
        db.add(variante)
        variantes[slug_v] = variante
    db.flush()
    for slug_v, _, _, comparte in VARIANTES_JUGUETE:
        if comparte:
            variantes[slug_v].precios_de_variante_id = variantes[comparte].id

    for alias, slug_v in [
        ("el basico", "basico"), ("basico", "basico"),
        ("el de siempre", "basico"),
        ("avanzado", "avanzado"), ("el pro", "avanzado"),
        ("express", "express"), ("el corto", "express"),
    ]:
        db.add(
            models.BotProductoAlias(
                producto_id=producto.id,
                nivel=models.ALIAS_NIVEL_VARIANTE,
                ref_id=variantes[slug_v].id,
                alias=alias,
            )
        )
    db.add(
        models.BotProductoAlias(
            producto_id=producto.id,
            nivel=models.ALIAS_NIVEL_PRODUCTO,
            ref_id=models.REF_TODAS,
            alias="el taller",
        )
    )

    for i, (slug_v, cuando, valor, horas, promocion) in enumerate(
        fechas if fechas is not None else FECHAS_JUGUETE
    ):
        valores = {"valor": valor, "horas": horas}
        if promocion:
            valores["promocion"] = promocion
        db.add(
            models.BotProductoFila(
                producto_id=producto.id,
                variante_id=variantes[slug_v].id,
                tipo=models.FILA_TIPO_SALIDA,
                etiqueta=cuando.strftime("%d/%m"),
                inicio=cuando,
                valores=valores,
                orden=i,
                externo_id=f"{slug_v}-{i}-{cuando.isoformat()}",
            )
        )

    db.add(
        models.BotProductoMedio(
            producto_id=producto.id,
            variante_id=variantes["basico"].id,
            clave="flyer_marzo",
            url="https://ejemplo.test/flyer_marzo.jpg",
            tipo="image",
            aplica={"meses": [3]},
        )
    )
    if bot_id is not None:
        db.add(
            models.BotProductoBot(
                bot_id=bot_id, producto_id=producto.id, activo=True, orden=1
            )
        )
    db.commit()
    return producto


@pytest.fixture
def juguete(db_session, cuenta_a):
    team_id, bot_id = cuenta_a
    producto = crear_juguete(db_session, team_id=team_id, bot_id=bot_id)
    return producto


def contar_consultas(db):
    """Contador de sentencias SQL sobre el motor de esa sesión.

    Devuelve una función que responde cuántas van; es como se comprueba que la
    caché no esté consultando de más (y que siga consultando lo justo).
    """
    motor = db.get_bind()
    marcador = {"n": 0}

    def _sumar(*_args, **_kw):
        marcador["n"] += 1

    event.listen(motor, "before_cursor_execute", _sumar)
    return marcador
