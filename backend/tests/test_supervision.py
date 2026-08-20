"""La ventana de supervisión: qué ve la cuenta administradora y qué no.

Lo que más importa acá no es que la lista salga bonita sino el aislamiento: el
`hilo_id` viaja en la URL, así que `conv-1` no puede servir para asomarse a las
conversaciones de un tenant que no está en la lista blanca. Eso se prueba
explícitamente (`TestAislamiento`), junto con que ningún endpoint quede sin
portero cuando alguien agregue el siguiente.
"""
from __future__ import annotations

import inspect
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException, params
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.dependencies import require_gloma_account
from app.routers import supervision
from app.services import caminos

CLAVE = "Clave-De-Prueba-1"
GLOMA = "gloma@glomabeauty.com"
MASCOTAS = "recuperatumascota@gmail.com"
VIAJES = "arranquemospues.marketing@gmail.com"
AJENA = "otro.cliente@test.com"


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


def _cuenta(db, correo: str, nombre: str, doc: str):
    """Un usuario con su team y su bot LLM, como las cuentas reales."""
    user = crud.create_user(
        db,
        schemas.UserCreate(
            nombre=nombre, correo=correo, tipo_documento="CC",
            documento=doc, password=CLAVE,
        ),
    )
    team = models.Team(nombre=nombre, owner_user_id=user.id)
    db.add(team)
    db.flush()
    db.add(models.TeamMember(team_id=team.id, user_id=user.id, role="owner"))
    bot = models.Bot(user_id=user.id, team_id=team.id, name=f"Bot {nombre}", engine="llm")
    db.add(bot)
    db.commit()
    return user, team, bot


@pytest.fixture
def mundo(db_session, monkeypatch):
    """Las tres cuentas del caso: Gloma mira; mascotas y viajes son miradas.

    `AJENA` no está en la lista blanca y es la que prueba el aislamiento.
    """
    monkeypatch.setenv("SUPERVISION_CUENTAS", f"{MASCOTAS},{VIAJES}")
    datos = {
        "gloma": _cuenta(db_session, GLOMA, "Gloma", "SUP-GLOMA"),
        "mascotas": _cuenta(db_session, MASCOTAS, "Recupera Tu Mascota", "SUP-MASC"),
        "viajes": _cuenta(db_session, VIAJES, "Arranquemos Pues", "SUP-VIAJ"),
        "ajena": _cuenta(db_session, AJENA, "Cliente Ajeno", "SUP-AJEN"),
    }
    return datos


def _conversacion_whatsapp(db, team, bot, *, contacto="573001112233", nombre="Ana",
                           cuando=None):
    """Un chat de WhatsApp con su bitácora del bot, como lo deja `bot_runner`."""
    ahora = cuando or datetime(2026, 8, 18, 15, 0, 0)
    conv = models.Conversation(
        team_id=team.id, contact_wa_id=contacto, contact_name=nombre,
        status="open", last_message_at=ahora, created_at=ahora,
    )
    db.add(conv)
    db.flush()
    db.add_all([
        models.Message(
            conversation_id=conv.id, direction="inbound",
            content="¿cuánto vale el plan?", created_at=ahora,
        ),
        models.Message(
            conversation_id=conv.id, direction="outbound",
            content="El plan a Coveñas está en $450.000 por persona.",
            created_at=ahora + timedelta(seconds=4),
        ),
    ])
    db.add(models.BotLlmDecision(
        bot_id=bot.id, conversation_id=conv.id, source="whatsapp",
        user_input="¿cuánto vale el plan?", camino="precios_condiciones",
        reply_preview="El plan a Coveñas está en $450.000 por persona.",
        created_at=ahora,
    ))
    db.commit()
    return conv


def _chat_web(db, bot, chat_ref="sesion-abc", *, hablo=True, cuando=None):
    """Un hilo del chat web: sin `conversation_id`, agrupado por `chat_ref`."""
    ahora = cuando or datetime(2026, 8, 18, 16, 0, 0)
    db.add(models.BotLlmDecision(
        bot_id=bot.id, source="mascotas", chat_ref=chat_ref,
        chat_contacto="Camila" if hablo else None,
        user_input="perdí a mi perro en Meléndez" if hablo else None,
        camino="busqueda_mascota" if hablo else "saludo",
        reply_preview="Cuéntame cómo es tu perro 🐾", created_at=ahora,
    ))
    db.commit()


class TestPortero:
    def test_gloma_entra(self, db_session, mundo):
        user = mundo["gloma"][0]
        assert supervision.check_access(user=user, db=db_session).allowed is True

    def test_una_cuenta_supervisada_no_ve_el_modulo(self, db_session, mundo):
        """Ser mirado no da derecho a mirar: mascotas no entra a esta ventana."""
        user = mundo["mascotas"][0]
        assert supervision.check_access(user=user, db=db_session).allowed is False

    def test_ningun_endpoint_queda_sin_portero(self):
        """El día que alguien agregue un endpoint acá, este test se lo recuerda.

        `/access` es la excepción a propósito: responde 200 siempre porque el
        menú lo consulta desde cualquier cuenta, y solo dice sí o no.
        """
        for ruta in supervision.router.routes:
            if ruta.path.endswith("/access"):
                continue
            guardas = [
                p.default.dependency
                for p in inspect.signature(ruta.endpoint).parameters.values()
                if isinstance(p.default, params.Depends)
            ]
            assert require_gloma_account in guardas, f"{ruta.path} sin portero"

    def test_todos_los_endpoints_son_de_lectura(self):
        """Esta ventana no escribe: si aparece un POST, fue sin querer."""
        for ruta in supervision.router.routes:
            assert ruta.methods == {"GET"}, f"{ruta.path} no es de solo lectura"


class TestCuentas:
    def test_lista_las_de_la_configuracion_y_solo_esas(self, db_session, mundo):
        salida = supervision.listar_cuentas(_=mundo["gloma"][0], db=db_session)
        correos = {c.correo for c in salida.cuentas}
        assert correos == {MASCOTAS, VIAJES}
        assert AJENA not in correos
        assert GLOMA not in correos

    def test_una_cuenta_configurada_que_no_existe_no_rompe_la_ventana(
        self, db_session, mundo, monkeypatch
    ):
        """Pasa en local, donde no están todas las cuentas de producción."""
        monkeypatch.setenv("SUPERVISION_CUENTAS", f"{MASCOTAS},nadie@ninguna.com")
        salida = supervision.listar_cuentas(_=mundo["gloma"][0], db=db_session)
        assert [c.correo for c in salida.cuentas] == [MASCOTAS]


class TestHilosDeWhatsapp:
    def test_arma_el_hilo_desde_los_mensajes(self, db_session, mundo):
        _, team, bot = mundo["viajes"]
        _conversacion_whatsapp(db_session, team, bot)

        salida = supervision.listar_conversaciones(
            cuenta=supervision._slug(VIAJES), limite=200, pagina=1,
            _=mundo["gloma"][0], db=db_session,
        )
        assert salida.total == 1
        hilo = salida.conversaciones[0]
        assert hilo.contacto == "Ana"
        assert hilo.canal == "whatsapp"
        # Los dos mensajes, no el único turno de la bitácora del bot.
        assert hilo.turnos == 2
        assert hilo.caminos == ["💲 Preguntó precios"]

    def test_el_detalle_trae_la_transcripcion_completa(self, db_session, mundo):
        _, team, bot = mundo["viajes"]
        conv = _conversacion_whatsapp(db_session, team, bot)

        detalle = supervision.detalle_conversacion(
            hilo_id=f"conv-{conv.id}", cuenta=supervision._slug(VIAJES),
            _=mundo["gloma"][0], db=db_session,
        )
        assert detalle.completo is True
        assert [t.quien for t in detalle.turnos] == ["persona", "bot"]
        # El camino se le pega al mensaje de la persona cruzando por su texto.
        assert detalle.turnos[0].camino_label == "💲 Preguntó precios"
        assert detalle.turnos[1].texto.startswith("El plan a Coveñas")

    def test_una_conversacion_sin_bitacora_igual_aparece(self, db_session, mundo):
        """Un chat que atendió un humano de punta a punta también es del cliente."""
        _, team, _bot = mundo["viajes"]
        ahora = datetime(2026, 8, 18, 12, 0, 0)
        conv = models.Conversation(
            team_id=team.id, contact_wa_id="573009998877", contact_name="Pedro",
            status="open", last_message_at=ahora, created_at=ahora,
        )
        db_session.add(conv)
        db_session.flush()
        db_session.add(models.Message(
            conversation_id=conv.id, direction="inbound",
            content="hola", created_at=ahora,
        ))
        db_session.commit()

        salida = supervision.listar_conversaciones(
            cuenta=supervision._slug(VIAJES), limite=200, pagina=1,
            _=mundo["gloma"][0], db=db_session,
        )
        assert [h.contacto for h in salida.conversaciones] == ["Pedro"]
        assert salida.conversaciones[0].caminos == []


class TestPaginacion:
    """La página se arma fusionando DOS listas ordenadas (WhatsApp y chat web).

    Es el punto donde se pierde o se repite un hilo sin que nadie lo note: si la
    fusión se hace mal, la página 2 empieza donde no debe y una conversación
    queda invisible para siempre. Por eso se prueba contra el orden global.
    """

    def _mundo_mezclado(self, db, mundo, cantidad=5):
        """Hilos de las dos fuentes intercalados en el tiempo, a propósito.

        Alternados: si una fuente quedara toda antes que la otra, la fusión
        podría estar rota y los tests igual pasarían.
        """
        _, team, bot = mundo["viajes"]
        base = datetime(2026, 8, 18, 12, 0, 0)
        esperados = []
        for i in range(cantidad):
            momento = base + timedelta(hours=2 * i)
            conv = _conversacion_whatsapp(
                db, team, bot, contacto=f"57300000{i:04d}",
                nombre=f"Wa{i}", cuando=momento,
            )
            _chat_web(db, bot, f"sesion-{i}", cuando=momento + timedelta(hours=1))
            esperados += [f"conv-{conv.id}", f"chat-sesion-{i}"]
        # Del más reciente al más viejo, que es como se listan.
        return list(reversed(esperados))

    def _pagina(self, db, mundo, pagina, limite):
        return supervision.listar_conversaciones(
            cuenta=supervision._slug(VIAJES), limite=limite, pagina=pagina,
            _=mundo["gloma"][0], db=db,
        )

    def test_las_paginas_recorren_todo_sin_repetir_ni_saltarse_nada(
        self, db_session, mundo
    ):
        orden_global = self._mundo_mezclado(db_session, mundo)

        recorrido = []
        for pagina in (1, 2, 3, 4, 5):
            salida = self._pagina(db_session, mundo, pagina, limite=2)
            assert len(salida.conversaciones) == 2
            recorrido += [h.hilo_id for h in salida.conversaciones]

        assert recorrido == orden_global
        assert len(set(recorrido)) == 10  # ningún hilo repetido entre páginas

    def test_el_total_es_el_de_la_cuenta_y_no_el_de_la_pagina(self, db_session, mundo):
        self._mundo_mezclado(db_session, mundo)

        primera = self._pagina(db_session, mundo, 1, limite=2)
        assert len(primera.conversaciones) == 2
        assert primera.total == 10
        assert primera.pagina == 1
        assert primera.por_pagina == 2

        # El total no se mueve al pasar de página: es de la cuenta.
        assert self._pagina(db_session, mundo, 4, limite=2).total == 10

    def test_una_pagina_pasada_del_final_viene_vacia_pero_no_revienta(
        self, db_session, mundo
    ):
        self._mundo_mezclado(db_session, mundo)
        salida = self._pagina(db_session, mundo, 99, limite=20)
        assert salida.conversaciones == []
        assert salida.total == 10

    def test_el_techo_de_pagina_lo_impone_el_contrato_no_el_frontend(self):
        """`limite` viene de la URL: el tope tiene que estar en el endpoint.

        Si el techo viviera solo en el `<select>` del navegador, un
        `?limite=100000` a mano volvería a traerse la cuenta entera.
        """
        parametro = inspect.signature(
            supervision.listar_conversaciones
        ).parameters["limite"].default
        topes = [m.le for m in parametro.metadata if hasattr(m, "le")]
        assert topes == [supervision.MAX_POR_PAGINA]


class TestHilosDelChatWeb:
    def test_agrupa_por_chat_ref(self, db_session, mundo):
        _, _team, bot = mundo["mascotas"]
        _chat_web(db_session, bot, "sesion-abc")
        _chat_web(db_session, bot, "sesion-xyz")

        salida = supervision.listar_conversaciones(
            cuenta=supervision._slug(MASCOTAS), limite=200, pagina=1,
            _=mundo["gloma"][0], db=db_session,
        )
        assert salida.total == 2
        assert {h.canal for h in salida.conversaciones} == {"web"}
        assert salida.conversaciones[0].caminos == ["🔎 Buscó su mascota"]

    def test_las_visitas_que_nunca_escribieron_no_se_listan(self, db_session, mundo):
        """Abrieron el chat, recibieron el saludo y se fueron: no son un hilo."""
        _, _team, bot = mundo["mascotas"]
        _chat_web(db_session, bot, "solo-miro", hablo=False)

        salida = supervision.listar_conversaciones(
            cuenta=supervision._slug(MASCOTAS), limite=200, pagina=1,
            _=mundo["gloma"][0], db=db_session,
        )
        assert salida.total == 0

    def test_el_detalle_avisa_que_el_texto_del_bot_viene_recortado(self, db_session, mundo):
        _, _team, bot = mundo["mascotas"]
        _chat_web(db_session, bot, "sesion-abc")

        detalle = supervision.detalle_conversacion(
            hilo_id="chat-sesion-abc", cuenta=supervision._slug(MASCOTAS),
            _=mundo["gloma"][0], db=db_session,
        )
        assert detalle.completo is False
        assert [t.quien for t in detalle.turnos] == ["persona", "bot"]


class TestAislamiento:
    def test_una_cuenta_fuera_de_la_lista_blanca_da_404(self, db_session, mundo):
        with pytest.raises(HTTPException) as exc:
            supervision.listar_conversaciones(
                cuenta=supervision._slug(AJENA), limite=200, pagina=1,
                _=mundo["gloma"][0], db=db_session,
            )
        assert exc.value.status_code == 404

    def test_no_se_puede_leer_un_hilo_de_otro_tenant(self, db_session, mundo):
        """El caso que justifica que el detalle reciba también la cuenta.

        La conversación existe y el `hilo_id` es válido, pero es de un tenant
        que nadie habilitó: pedirla prestada desde una cuenta supervisada tiene
        que dar 404, no la transcripción.
        """
        _, team_ajeno, bot_ajeno = mundo["ajena"]
        conv = _conversacion_whatsapp(db_session, team_ajeno, bot_ajeno)

        with pytest.raises(HTTPException) as exc:
            supervision.detalle_conversacion(
                hilo_id=f"conv-{conv.id}", cuenta=supervision._slug(VIAJES),
                _=mundo["gloma"][0], db=db_session,
            )
        assert exc.value.status_code == 404

    def test_tampoco_un_chat_web_de_otro_tenant(self, db_session, mundo):
        _, _team, bot_ajeno = mundo["ajena"]
        _chat_web(db_session, bot_ajeno, "sesion-ajena")

        with pytest.raises(HTTPException) as exc:
            supervision.detalle_conversacion(
                hilo_id="chat-sesion-ajena", cuenta=supervision._slug(MASCOTAS),
                _=mundo["gloma"][0], db=db_session,
            )
        assert exc.value.status_code == 404

    def test_un_hilo_inventado_da_404(self, db_session, mundo):
        for inventado in ("conv-99999", "chat-noexiste", "cualquier-cosa", "dia-1-x-nofecha"):
            with pytest.raises(HTTPException) as exc:
                supervision.detalle_conversacion(
                    hilo_id=inventado, cuenta=supervision._slug(MASCOTAS),
                    _=mundo["gloma"][0], db=db_session,
                )
            assert exc.value.status_code == 404, inventado


class TestEtiquetasDeCamino:
    def test_el_mismo_slug_dice_cosas_distintas_segun_la_cuenta(self):
        """`reserva` es un cupo apartado en la agencia y no existe en mascotas."""
        assert caminos.etiqueta("reserva", VIAJES) == "✅ Apartó un cupo"
        assert caminos.etiqueta("busqueda_mascota", MASCOTAS) == "🔎 Buscó su mascota"

    def test_un_camino_nuevo_se_muestra_legible_en_vez_de_esconderse(self):
        assert caminos.etiqueta("promo_fin_de_ano", VIAJES) == "Promo fin de ano"

    def test_estan_los_caminos_que_los_bots_emiten_de_verdad(self):
        """La lista salió de consultar producción, no de leer los seeds: el bot
        emite caminos que el clasificador no declara (`hotel`) y declara otros
        que todavía no se han visto (`agradecimiento`). Si uno se queda sin
        etiqueta no se rompe nada —el fallback lo muestra legible— pero en la
        ventana se lee como una palabra suelta ("Hotel") y se nota."""
        for camino in ("info_general", "hotel", "tours", "precios_condiciones",
                       "reserva", "escalar_a_asesor"):
            assert camino in caminos.catalogo(VIAJES), camino
        for camino in ("buscar_mascota", "reportar_encontrada", "reporte_registrado",
                       "descarga_listado", "ficha_mascota", "mascota_reconocida",
                       "busqueda_mascota", "terremoto", "agradecimiento"):
            assert camino in caminos.catalogo(MASCOTAS), camino

    def test_los_genericos_valen_para_cualquier_cuenta(self):
        assert caminos.etiqueta("saludo", VIAJES) == caminos.etiqueta("saludo", MASCOTAS)
