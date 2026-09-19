"""La capa de acceso a productos, sobre un producto inventado.

Se prueba contra un taller de cerámica y no contra el catálogo de un cliente a
propósito: esta capa tiene que servirle a los siete bots del portafolio, y una
suite escrita sobre el vocabulario de uno termina metiéndolo dentro del código.
La comparación contra el catálogo real —carácter por carácter— vive aparte, en
`test_paridad_tarifario.py`.

Lo que se protege acá es lo que se paga caro si falla:

  * que un bot NUNCA vea lo de otra cuenta (el peor error posible del esquema:
    un bot cotizando con los precios del competidor);
  * que no se ofrezca algo que ya venció;
  * que una variante que copia su precio de otra lo copie de la correcta;
  * que un producto sin datos vigentes mande a escalar en vez de dejar que el
    modelo redacte;
  * que la caché no sirva un precio viejo después de que lo cambiaron.

El «hoy» va por parámetro en todas: si se leyera del reloj, la suite empezaría
a fallar sola el día que pase la última fecha del producto de juguete.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from app import models
from app.services import productos

from tests.productos.conftest import (
    HOY, JUGUETE, contar_consultas, crear_juguete,
)


def _catalogo(db, cuenta):
    team_id, bot_id = cuenta
    return productos.resolver_producto(db, team_id=team_id, bot_id=bot_id, texto="")


def _variante(catalogo, slug):
    return next(v for v in catalogo.variantes if v.slug == slug)


# ---------------------------------------------------------------------------

class TestAislamientoPorCuenta:
    """Un bot no puede ver —ni de refilón— lo que vende otra cuenta.

    Es el peor error posible de este esquema, y el que ninguna prueba de texto
    detectaría: los precios de la otra agencia se ven perfectamente válidos.
    """

    def test_el_producto_de_una_cuenta_no_existe_para_el_bot_de_la_otra(
        self, db_session, cuenta_a, cuenta_b
    ):
        team_a, bot_a = cuenta_a
        team_b, bot_b = cuenta_b
        crear_juguete(db_session, team_id=team_a, bot_id=bot_a)

        assert productos.catalogos_de_bot(
            db_session, team_id=team_b, bot_id=bot_b
        ) == []
        assert productos.resolver_producto(
            db_session, team_id=team_b, bot_id=bot_b, texto="taller_ceramica"
        ) is None

    def test_pedir_el_producto_de_otra_cuenta_por_id_no_lo_devuelve(
        self, db_session, cuenta_a, cuenta_b
    ):
        """Ni con el id en la mano: el `WHERE team_id` está en la consulta."""
        team_a, bot_a = cuenta_a
        team_b, _ = cuenta_b
        producto = crear_juguete(db_session, team_id=team_a, bot_id=bot_a)

        assert productos.cargar_catalogo(
            db_session, team_id=team_b, producto_id=producto.id
        ) is None
        assert productos.cargar_catalogo(
            db_session, team_id=team_a, producto_id=producto.id
        ) is not None

    def test_consultar_con_el_bot_de_la_otra_cuenta_manda_a_escalar(
        self, db_session, cuenta_a, cuenta_b
    ):
        team_a, bot_a = cuenta_a
        team_b, bot_b = cuenta_b
        crear_juguete(db_session, team_id=team_a, bot_id=bot_a)

        salida = productos.consultar(
            db_session, team_id=team_b, bot_id=bot_b, mes="marzo", hoy=HOY
        )
        assert salida == productos.PLANTILLA["sin_datos"]
        assert "Taller" not in salida
        assert "$" not in salida

    def test_un_bot_sin_el_producto_enganchado_no_lo_ve(
        self, db_session, cuenta_a
    ):
        """`bot_producto_bots` es lo que decide qué vende cada bot.

        Dos bots de la misma cuenta no venden lo mismo: el de soporte no cotiza.
        """
        team_id, bot_id = cuenta_a
        crear_juguete(db_session, team_id=team_id, bot_id=None)

        assert productos.catalogos_de_bot(
            db_session, team_id=team_id, bot_id=bot_id
        ) == []
        # Sin `bot_id` (un backoffice, el importador) sí se ven los de la cuenta.
        assert len(productos.catalogos_de_bot(db_session, team_id=team_id)) == 1

    def test_un_producto_en_borrador_no_lo_ve_el_bot(self, db_session, cuenta_a):
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id,
            estado=models.PRODUCTO_ESTADO_BORRADOR,
        )
        assert productos.catalogos_de_bot(
            db_session, team_id=team_id, bot_id=bot_id
        ) == []

    def test_sin_team_id_devuelve_vacio_y_deja_rastro(
        self, db_session, cuenta_a, caplog
    ):
        """Decisión del CEO: vacío **y** un warning, nunca fallar callada.

        Sin el warning, el día que un llamador pierda el `team_id` el bot
        respondería «no tengo datos» y nadie sabría por qué.
        """
        team_id, bot_id = cuenta_a
        crear_juguete(db_session, team_id=team_id, bot_id=bot_id)

        with caplog.at_level(logging.WARNING, logger=productos.__name__):
            assert productos.catalogos_de_bot(
                db_session, team_id=None, bot_id=bot_id
            ) == []
            assert productos.cargar_catalogo(
                db_session, team_id=None, producto_id=1, bot_id=bot_id
            ) is None
            salida = productos.consultar(
                db_session, team_id=None, bot_id=bot_id, mes="marzo", hoy=HOY
            )

        assert salida == productos.PLANTILLA["sin_datos"]
        avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(avisos) == 3
        for aviso in avisos:
            # El `bot_id` es lo que permite rastrear de dónde salió la llamada
            # sin `team_id`; un warning sin él no sirve para nada.
            assert "bot_id=%s" in aviso.msg
            assert bot_id in aviso.args


class TestAlias:
    """Reemplazan el diccionario cableado que hoy vive en el código."""

    def test_resuelve_el_nombre_el_slug_y_los_apodos(self, db_session, juguete):
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        for texto in ("Taller avanzado", "avanzado", "el pro", "EL PRO"):
            assert productos.resolver_variante(catalogo, texto).slug == "avanzado"

    def test_resuelve_por_contencion(self, db_session, juguete):
        """«me sirve el de siempre, gracias» tiene que resolver igual."""
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        variante = productos.resolver_variante(
            catalogo, "me sirve el de siempre, gracias"
        )
        assert variante.slug == "basico"

    def test_lo_que_no_es_un_alias_no_resuelve(self, db_session, juguete):
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        assert productos.resolver_variante(catalogo, "el de vidrio soplado") is None

    def test_el_alias_de_producto_encuentra_el_producto(self, db_session, cuenta_a):
        team_id, bot_id = cuenta_a
        crear_juguete(db_session, team_id=team_id, bot_id=bot_id)
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id,
            slug="otro_taller",
        )
        catalogo = productos.resolver_producto(
            db_session, team_id=team_id, bot_id=bot_id, texto="el taller"
        )
        assert catalogo is not None and catalogo.slug == "taller_ceramica"

    def test_el_alias_de_otra_cuenta_no_resuelve(
        self, db_session, cuenta_a, cuenta_b
    ):
        """El mismo apodo en dos cuentas apunta a dos cosas distintas.

        «el pro» es una variante de la cuenta A; el bot de la cuenta B, que
        tiene su propio producto, no puede terminar resolviéndolo contra el de
        la vecina.
        """
        team_a, bot_a = cuenta_a
        team_b, bot_b = cuenta_b
        crear_juguete(db_session, team_id=team_a, bot_id=bot_a)
        crear_juguete(
            db_session, team_id=team_b, bot_id=bot_b,
            fechas=[("basico", date(2026, 3, 21), 99_000, 4, "")],
        )

        catalogo_b = productos.resolver_producto(
            db_session, team_id=team_b, bot_id=bot_b, texto=""
        )
        assert catalogo_b.team_id == team_b
        # El alias existe en B también (es el mismo producto de juguete), pero
        # resuelve contra SUS variantes, no contra las de A.
        variante = productos.resolver_variante(catalogo_b, "el pro")
        assert variante is not None
        assert variante.id != _variante(
            _catalogo(db_session, cuenta_a), "avanzado"
        ).id

    def test_una_variante_inactiva_no_resuelve(self, db_session, juguete):
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        variante = _variante(catalogo, "avanzado")
        db_session.query(models.BotProductoVariante).filter_by(
            id=variante.id
        ).update({"activo": False})
        db_session.commit()
        productos.limpiar_cache()

        catalogo = _catalogo(db_session, (juguete.team_id, None))
        assert productos.resolver_variante(catalogo, "el pro") is None


class TestVigencia:
    """Nunca se ofrece algo que ya pasó. Es la regla que más plata cuesta."""

    def test_las_fechas_corridas_no_aparecen(self, db_session, juguete):
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        filas = productos.filas_vigentes(
            catalogo, variante=_variante(catalogo, "basico"), hoy=HOY
        )
        etiquetas = [f.etiqueta for f in filas]
        assert etiquetas == ["21/03", "11/04"]          # 07/02 y 07/03 ya pasaron

    def test_lo_de_hoy_mismo_todavia_se_ofrece(self, db_session, juguete):
        """El corte es `< hoy`, no `<= hoy`: hoy todavía se vende."""
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        filas = productos.filas_vigentes(
            catalogo, variante=_variante(catalogo, "basico"), hoy=date(2026, 3, 21)
        )
        assert [f.etiqueta for f in filas] == ["21/03", "11/04"]

    def test_una_fila_sin_fecha_no_vence_nunca(self, db_session, cuenta_a):
        """Una lista de precios o unas sedes no tienen fecha de salida."""
        team_id, bot_id = cuenta_a
        producto = crear_juguete(db_session, team_id=team_id, bot_id=bot_id)
        db_session.add(
            models.BotProductoFila(
                producto_id=producto.id,
                tipo=models.FILA_TIPO_PRECIO,
                etiqueta="Clase suelta",
                valores={"valor": 60_000, "horas": 2},
                orden=99,
                externo_id="suelta",
            )
        )
        db_session.commit()
        productos.limpiar_cache()

        catalogo = _catalogo(db_session, (team_id, bot_id))
        filas = productos.filas_vigentes(catalogo, hoy=date(2030, 1, 1))
        assert [f.etiqueta for f in filas] == ["Clase suelta"]

    def test_la_fecha_vencida_se_avisa_pero_no_corta(self, db_session, juguete):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, variante="el basico",
            mes="marzo", fecha="2026-03-07", hoy=HOY,
        )
        assert "OJO: el 2026-03-07 ya pasó." in salida
        assert "21/03" in salida               # las que sí quedan van igual

    def test_la_zona_horaria_es_la_de_colombia(self):
        """El backend corre en UTC y el negocio vende en Colombia.

        Entre las 7 pm y la medianoche de allá, el servidor ya cree que es
        mañana y el bot dejaría de ofrecer algo que todavía se puede vender.
        """
        from datetime import timezone

        esperado = datetime.now(timezone(timedelta(hours=-5))).date()
        assert productos.hoy_colombia() == esperado


class TestElAnioQueElModeloNoSabe:
    """Portado de `test_tarifario.py`: el modelo no sabe en qué año vive.

    Al pedirle una fecha exacta escribe la del año pasado, y la consulta le
    responde «eso ya pasó» a un cliente que quería una fecha futura y vendible.
    Le pega justo a los de mayor intención: los que ya escogieron día.
    """

    def test_el_21_de_marzo_no_es_del_ano_pasado(self, db_session, juguete):
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        assert productos.resolver_fecha(
            catalogo, date(2025, 3, 21), 3, HOY
        ) == date(2026, 3, 21)

        salida = productos.consultar(
            db_session, team_id=juguete.team_id, variante="el basico",
            mes="marzo", fecha="2025-03-21", hoy=HOY,
        )
        assert "ya pasó" not in salida
        assert "<-- la fecha que pidió" in salida

    def test_una_fecha_futura_explicita_se_respeta(self, db_session, juguete):
        """Solo se corrige lo que está demostrablemente mal."""
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        futura = date(2026, 4, 11)
        assert productos.resolver_fecha(catalogo, futura, 4, HOY) == futura

    def test_una_fecha_de_verdad_vencida_sigue_marcandose(self, db_session, juguete):
        """Febrero ya pasó y el producto no publica el febrero entrante: no hay
        reinterpretación válida, así que se avisa."""
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        assert productos.resolver_fecha(
            catalogo, date(2026, 2, 7), 2, HOY
        ) == date(2026, 2, 7)

    def test_el_29_de_febrero_no_revienta(self, db_session, juguete):
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        assert productos.resolver_fecha(catalogo, date(2024, 2, 29), 2, HOY) is not None


class TestVarianteQueCompartePrecio:
    """`precios_de_variante_id` mal resuelto = cotizar con el precio de otra."""

    def test_la_variante_que_copia_usa_la_tabla_de_la_otra(self, db_session, juguete):
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        basico = productos.filas_vigentes(
            catalogo, variante=_variante(catalogo, "basico"), hoy=HOY
        )
        express = productos.filas_vigentes(
            catalogo, variante=_variante(catalogo, "express"), hoy=HOY
        )
        avanzado = productos.filas_vigentes(
            catalogo, variante=_variante(catalogo, "avanzado"), hoy=HOY
        )
        assert [f.id for f in express] == [f.id for f in basico]
        assert [f.id for f in express] != [f.id for f in avanzado]

    def test_sin_variante_no_se_lista_la_que_copia_pero_se_dice_que_cuesta_igual(
        self, db_session, juguete
    ):
        """Listarla aparte se lee como dos ofertas distintas del mismo precio."""
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, mes="marzo", hoy=HOY
        )
        assert "Taller express — Marzo" not in salida       # no tiene bloque propio
        assert "Taller express cuesta lo mismo que Taller básico." in salida

    def test_pedida_por_su_nombre_si_se_cotiza(self, db_session, juguete):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, variante="el corto",
            mes="marzo", hoy=HOY,
        )
        assert "Taller express — Marzo (1 fechas):" in salida
        assert "$150.000" in salida

    def test_el_desde_se_cotiza_una_vez_por_tabla(self, db_session, juguete):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, mes="marzo", hoy=HOY
        )
        desde = [l for l in salida.split("\n") if "«desde»" in l]
        assert len(desde) == 2                    # básico+express y avanzado
        assert "Taller básico y Taller express — «desde» de Marzo" in desde[0]

    def test_un_ciclo_no_cuelga_la_consulta(self, db_session, juguete, caplog):
        """Un ciclo es un error de datos del cliente, no algo que pueda dejar al
        bot dando vueltas dentro de un `while`."""
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        basico = _variante(catalogo, "basico")
        express = _variante(catalogo, "express")
        db_session.query(models.BotProductoVariante).filter_by(
            id=basico.id
        ).update({"precios_de_variante_id": express.id})
        db_session.commit()
        productos.limpiar_cache()

        catalogo = _catalogo(db_session, (juguete.team_id, None))
        with caplog.at_level(logging.WARNING, logger=productos.__name__):
            filas = productos.filas_vigentes(
                catalogo, variante=_variante(catalogo, "basico"), hoy=HOY
            )
        assert isinstance(filas, list)
        assert any("ciclo" in r.getMessage() for r in caplog.records)


class TestProductoSinFilasVigentes:
    """Un bot sin datos no dice «no tengo datos»: improvisa. Por eso se escala."""

    def test_cuando_todo_vencio_ordena_escalar(self, db_session, juguete):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, mes="marzo",
            hoy=date(2027, 1, 1),
        )
        assert salida == JUGUETE["presentacion"].get(
            "sin_datos", productos.PLANTILLA["sin_datos"]
        )
        assert "escala" in salida.lower() or "asesor" in salida.lower()
        assert "$" not in salida

    def test_no_le_deja_redactar_nada_del_producto(self, db_session, juguete):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, mes="marzo",
            hoy=date(2027, 1, 1),
        )
        for filtrado in ("Taller básico", "120.000", "21/03", "Marzo"):
            assert filtrado not in salida

    def test_un_periodo_vacio_no_escala_si_el_producto_sigue_vivo(
        self, db_session, juguete
    ):
        """Distinto del anterior: en mayo no hay básico, pero el taller existe.

        Escalar acá sería regalar la conversación: lo que corresponde es decir
        qué meses sí tienen.
        """
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, variante="basico",
            mes="mayo", hoy=HOY,
        )
        assert "Taller básico — Mayo: no hay nada abierto." in salida
        assert "Meses con cupo en Taller básico: Marzo, Abril." in salida
        assert salida != productos.PLANTILLA["sin_datos"]


class TestTopeDeFilas:
    """Un período cargado se lleva el presupuesto de tokens del turno."""

    def _muchas(self, db, cuenta, cuantas):
        """Un marzo cargado: `cuantas` fechas, todas dentro del mismo mes.

        Se repiten días a propósito (`% 20`): un taller puede abrir dos grupos
        el mismo día, y así el tope se mide contra el número de filas y no
        contra el calendario.
        """
        team_id, bot_id = cuenta
        fechas = [
            (
                "basico",
                date(2026, 3, 11) + timedelta(days=i % 20),
                100_000 + i * 1_000,
                4,
                "",
            )
            for i in range(cuantas)
        ]
        return crear_juguete(db, team_id=team_id, bot_id=bot_id, fechas=fechas)

    def test_lista_las_primeras_y_dice_cuantas_faltan(self, db_session, cuenta_a):
        self._muchas(db_session, cuenta_a, 25)
        team_id, bot_id = cuenta_a
        salida = productos.consultar(
            db_session, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
        )
        listadas = [l for l in salida.split("\n") if l.startswith("  · ")]
        assert len(listadas) == productos.TOPE_BLOQUE
        assert "(y 5 más sin listar.)" in salida
        # Y el título sigue diciendo cuántas hay de verdad, no cuántas listó.
        assert "Taller básico — Marzo (25 fechas):" in salida

    def test_sin_pasarse_del_tope_no_recorta_ni_avisa(self, db_session, cuenta_a):
        self._muchas(db_session, cuenta_a, 3)
        team_id, bot_id = cuenta_a
        salida = productos.consultar(
            db_session, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
        )
        assert "más sin listar" not in salida
        assert len([l for l in salida.split("\n") if l.startswith("  · ")]) == 3

    def test_el_producto_puede_poner_su_propio_tope(self, db_session, cuenta_a):
        team_id, bot_id = cuenta_a
        presentacion = {
            "presentacion": {**JUGUETE["presentacion"], "tope_bloque": 2}
        }
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, presentacion=presentacion,
            fechas=[
                ("basico", date(2026, 3, 11) + timedelta(days=i), 100_000, 4, "")
                for i in range(5)
            ],
        )
        salida = productos.consultar(
            db_session, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
        )
        assert len([l for l in salida.split("\n") if l.startswith("  · ")]) == 2
        assert "(y 3 más sin listar.)" in salida

    def test_la_busqueda_por_presupuesto_tiene_su_propio_tope(
        self, db_session, cuenta_a
    ):
        """Una búsqueda cruza todos los períodos y calza con el catálogo entero."""
        self._muchas(db_session, cuenta_a, 25)
        team_id, bot_id = cuenta_a
        salida = productos.consultar(
            db_session, team_id=team_id, bot_id=bot_id,
            presupuesto="200 mil", hoy=HOY,
        )
        bloque = salida.split("PRESUPUESTO")[1]
        listadas = [l for l in bloque.split("\n") if l.startswith("  · ")]
        assert len(listadas) == productos.TOPE_LISTADO
        assert "Sí le alcanza: 25. Van 8:" in bloque
        assert "(y 17 más, hasta $124.000.)" in bloque


class TestCache:
    """Sin caché, cada turno del bot relee el catálogo entero de la base."""

    def test_dentro_del_ttl_no_consulta_nada(self, db_session, juguete):
        conteo = contar_consultas(db_session)
        primera = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        gastadas = conteo["n"]
        assert gastadas > 0

        segunda = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        assert conteo["n"] == gastadas            # ni una consulta más
        assert segunda is primera                 # y es la misma copia

    def test_pasado_el_ttl_revisa_con_una_sola_consulta(
        self, db_session, juguete, monkeypatch
    ):
        """Vencido el TTL se revisa el sello, no se relee el catálogo.

        Es la diferencia entre una consulta por turno y seis.
        """
        primera = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        monkeypatch.setattr(productos, "TTL_SEGUNDOS", 0)
        conteo = contar_consultas(db_session)
        segunda = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        assert conteo["n"] == 1
        assert segunda is primera

    def test_cambiar_un_precio_invalida_la_copia(
        self, db_session, juguete, monkeypatch
    ):
        """El sello es `MAX(updated_at)`: si alguien editó, se relee."""
        monkeypatch.setattr(productos, "TTL_SEGUNDOS", 0)
        antes = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        fila = next(f for f in antes.filas if f.etiqueta == "21/03")
        assert fila.valores["valor"] == 150_000

        db_session.query(models.BotProductoFila).filter_by(id=fila.id).update(
            {
                "valores": {**fila.valores, "valor": 175_000},
                "updated_at": datetime.utcnow() + timedelta(minutes=1),
            }
        )
        db_session.commit()

        despues = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        assert despues is not antes
        assert next(
            f for f in despues.filas if f.etiqueta == "21/03"
        ).valores["valor"] == 175_000

    def test_retirar_una_fila_tambien_invalida(
        self, db_session, juguete, monkeypatch
    ):
        """Un `DELETE` no mueve el `MAX(updated_at)`.

        Por eso el sello cuenta también las filas: sin eso, una fecha retirada
        se seguiría ofreciendo hasta que alguien editara otra cosa.
        """
        monkeypatch.setattr(productos, "TTL_SEGUNDOS", 0)
        antes = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        fila = next(f for f in antes.filas if f.etiqueta == "21/03")
        db_session.query(models.BotProductoFila).filter_by(id=fila.id).delete()
        db_session.commit()

        despues = productos.cargar_catalogo(
            db_session, team_id=juguete.team_id, producto_id=juguete.id
        )
        assert "21/03" not in [f.etiqueta for f in despues.filas]

    def test_la_copia_de_una_cuenta_no_le_sirve_a_la_otra(
        self, db_session, cuenta_a, cuenta_b
    ):
        """La clave de la caché lleva el `team_id`, no solo el id del producto."""
        team_a, bot_a = cuenta_a
        team_b, bot_b = cuenta_b
        producto_a = crear_juguete(db_session, team_id=team_a, bot_id=bot_a)

        assert productos.cargar_catalogo(
            db_session, team_id=team_a, producto_id=producto_a.id
        ) is not None
        assert productos.cargar_catalogo(
            db_session, team_id=team_b, producto_id=producto_a.id
        ) is None

    def test_limpiar_la_de_una_cuenta_no_bota_la_de_la_otra(
        self, db_session, cuenta_a, cuenta_b
    ):
        team_a, bot_a = cuenta_a
        team_b, bot_b = cuenta_b
        a = crear_juguete(db_session, team_id=team_a, bot_id=bot_a)
        b = crear_juguete(db_session, team_id=team_b, bot_id=bot_b)
        cat_a = productos.cargar_catalogo(
            db_session, team_id=team_a, producto_id=a.id
        )
        cat_b = productos.cargar_catalogo(
            db_session, team_id=team_b, producto_id=b.id
        )

        productos.limpiar_cache(team_id=team_a)
        conteo = contar_consultas(db_session)
        assert productos.cargar_catalogo(
            db_session, team_id=team_b, producto_id=b.id
        ) is cat_b
        assert conteo["n"] == 0
        assert productos.cargar_catalogo(
            db_session, team_id=team_a, producto_id=a.id
        ) is not cat_a


class TestRedaccion:
    """El texto es del producto; del módulo es la estructura."""

    def test_un_producto_sin_plantillas_igual_responde(self, db_session, cuenta_a):
        """Los siete bots no van a configurar las 30 plantillas el primer día."""
        team_id, bot_id = cuenta_a
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, presentacion={}
        )
        salida = productos.consultar(
            db_session, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
        )
        assert "Taller de cerámica" in salida
        assert "valor: 150000" in salida

    def test_una_plantilla_rota_no_tumba_el_turno(
        self, db_session, cuenta_a, caplog
    ):
        """Un `{campo}` que no existe es un error del tenant, no del cliente.

        Se registra server-side y el bot sigue respondiendo con el texto por
        defecto (regla 6 de CLAUDE.md: al cliente, mensajes sanos).
        """
        team_id, bot_id = cuenta_a
        presentacion = {
            "presentacion": {
                **JUGUETE["presentacion"],
                "bloque_titulo": "{variante} — {columna_que_no_existe}:",
            }
        }
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, presentacion=presentacion
        )
        with caplog.at_level(logging.ERROR, logger=productos.__name__):
            salida = productos.consultar(
                db_session, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
            )
        assert "Taller básico — Marzo (1 opciones):" in salida
        assert any("plantilla" in r.getMessage() for r in caplog.records)

    def test_el_medio_del_periodo_es_obligatorio_y_sale_del_producto(
        self, db_session, juguete
    ):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, variante="basico",
            mes="marzo", hoy=HOY,
        )
        assert "OBLIGATORIO: envía `flyer_marzo` con `enviar_media`." in salida

    def test_un_periodo_sin_medio_no_inventa_uno(self, db_session, juguete):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, variante="basico",
            mes="abril", hoy=HOY,
        )
        assert "enviar_media" not in salida

    def test_la_variante_que_copia_precios_tambien_hereda_el_medio(
        self, db_session, juguete
    ):
        """Dos variantes que comparten tabla suelen compartir la foto."""
        catalogo = _catalogo(db_session, (juguete.team_id, None))
        medio = productos.clave_medio(catalogo, _variante(catalogo, "express"), 3)
        assert medio is not None
        clave, prestadora = medio
        assert clave == "flyer_marzo"
        assert prestadora.slug == "basico"

    def test_sin_periodo_pide_el_periodo_en_vez_de_adivinar(
        self, db_session, juguete
    ):
        """Cada período tiene su propio «desde»: responder con el de todo el
        catálogo es el bug que ya costó una cotización."""
        salida = productos.consultar(db_session, team_id=juguete.team_id, hoy=HOY)
        assert salida == JUGUETE["presentacion"]["sin_periodo"]
        assert "$" not in salida

    def test_un_producto_sin_fechas_no_necesita_periodo(self, db_session, cuenta_a):
        """Una lista de precios o unas sedes se consultan sin decir un mes."""
        team_id, bot_id = cuenta_a
        producto = crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, fechas=[]
        )
        db_session.add(
            models.BotProductoFila(
                producto_id=producto.id,
                tipo=models.FILA_TIPO_SEDE,
                etiqueta="Sede norte",
                valores={"valor": 0, "horas": 0},
                externo_id="norte",
            )
        )
        db_session.commit()
        productos.limpiar_cache()

        salida = productos.consultar(
            db_session, team_id=team_id, bot_id=bot_id, hoy=HOY
        )
        assert "Sede norte" in salida

    def test_una_variante_que_no_existe_no_se_confunde_con_una_real(
        self, db_session, juguete
    ):
        salida = productos.consultar(
            db_session, team_id=juguete.team_id, variante="el de vidrio",
            mes="marzo", hoy=HOY,
        )
        assert salida == (
            "No reconozco 'el de vidrio'. Hay: Taller básico, Taller avanzado "
            "y Taller express."
        )
        assert "$" not in salida

    def test_con_varios_productos_pregunta_cual_en_vez_de_adivinar(
        self, db_session, cuenta_a
    ):
        """Contestar por el primero es venderle al cliente lo que no preguntó."""
        team_id, bot_id = cuenta_a
        crear_juguete(db_session, team_id=team_id, bot_id=bot_id)
        crear_juguete(
            db_session, team_id=team_id, bot_id=bot_id, slug="otro_taller"
        )
        salida = productos.consultar(
            db_session, team_id=team_id, bot_id=bot_id, mes="marzo", hoy=HOY
        )
        assert salida.startswith("No dijiste de cuál producto.")
        assert "$" not in salida

    def test_el_repr_no_filtra_lo_que_escribio_el_cliente(
        self, db_session, juguete
    ):
        """Regla 1 de CLAUDE.md, y no es teórica: un catálogo termina en el log
        de un error o en la traza de una prueba que falla, y `instrucciones` es
        donde el cliente escribe «si preguntan, el WhatsApp de la sede es…»."""
        db_session.query(models.BotProducto).filter_by(id=juguete.id).update(
            {"instrucciones": "escríbele al 3001112233 si insiste"}
        )
        db_session.commit()
        productos.limpiar_cache()

        catalogo = _catalogo(db_session, (juguete.team_id, None))
        assert catalogo.instrucciones is not None       # se lee, pero no se imprime
        for texto in (repr(catalogo), str(catalogo)):
            assert "3001112233" not in texto
            assert "<REDACTED>" in texto
        assert "3001112233" not in repr(_variante(catalogo, "basico"))

    def test_ninguna_cifra_de_la_respuesta_se_inventa(self, db_session, juguete):
        """Toda cifra tiene que existir como fila. Si mañana alguien pega un
        número a mano en un `f"..."`, este test lo caza."""
        import re

        publicados = {
            f.valores["valor"]
            for f in _catalogo(db_session, (juguete.team_id, None)).filas
        }
        for mes in ("marzo", "abril", "mayo"):
            salida = productos.consultar(
                db_session, team_id=juguete.team_id, mes=mes, hoy=HOY
            )
            cifras = {
                int(c.replace(".", "")) for c in re.findall(r"\$([\d.]+)", salida)
            }
            assert not cifras - publicados, (mes, sorted(cifras - publicados))
