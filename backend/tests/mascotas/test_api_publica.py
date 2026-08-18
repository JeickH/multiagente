"""La cara pública de mascotasperdidascolombia.com.

Todo lo de aquí lo puede llamar cualquiera desde internet, sin login. Las
pruebas cubren las tres cosas que protegen ese canal: que el estado de la
conversación no lo controle el visitante, que las fotos tengan techo, y que la
descarga del listado exija un token nuestro.
"""
from __future__ import annotations

import json

import pytest

from app import models
from app.services import mascotas as svc

from .conftest import texto, usa_tool


class TestChat:
    def test_un_turno_devuelve_lo_que_dijo_el_bot(
        self, cliente, cuenta_mascotas, respuestas
    ):
        respuestas(texto("Hola 🐾 Soy Huella, ¿en qué te ayudo?"))
        r = cliente.post("/mascotas/chat", json={"message": "hola"})

        assert r.status_code == 200
        cuerpo = r.json()
        assert cuerpo["actions"][0]["text"].startswith("Hola 🐾")
        assert cuerpo["finished"] is False
        assert cuerpo["session"], "sin token de sesión se pierde el hilo"

    def test_sin_bot_activo_responde_con_amabilidad(self, cliente, db):
        """No hay fila de bot: el ciudadano no puede quedarse sin respuesta."""
        r = cliente.post("/mascotas/chat", json={"message": "hola"})
        assert r.status_code == 200
        assert "no puedo atenderte" in r.json()["actions"][0]["text"]

    def test_la_sesion_viaja_cifrada(self, cliente, cuenta_mascotas, respuestas):
        """El historial NUNCA lo controla el visitante: va cifrado con Fernet,
        así que no puede inyectar turnos falsos ni adueñarse de fotos ajenas."""
        respuestas(texto("Hola 🐾"))
        token = cliente.post("/mascotas/chat", json={"message": "hola"}).json()["session"]

        assert "history" not in token
        assert "upload" not in token
        from app.services.crypto import decrypt_secret
        assert isinstance(json.loads(decrypt_secret(token)), dict)

    def test_una_sesion_falsificada_se_ignora(self, cliente, cuenta_mascotas, respuestas):
        """Token inválido → conversación nueva, no un error ni un historial
        elegido por el visitante."""
        respuestas(texto("Hola 🐾"))
        r = cliente.post(
            "/mascotas/chat",
            json={"message": "hola", "session": "esto-no-es-un-token"},
        )
        assert r.status_code == 200
        assert r.json()["actions"]

    def test_el_codigo_del_reporte_vuelve_al_cliente(
        self, cliente, cuenta_mascotas, respuestas
    ):
        respuestas(
            usa_tool(
                "registrar_reporte",
                {"tipo_registro": "perdida", "especie": "perro",
                 "ubicacion": "Barrio Meléndez", "contacto_telefono": "3001234567"},
            ),
            texto("Listo, tu reporte quedó guardado 🐾"),
        )
        r = cliente.post("/mascotas/chat", json={"message": "perdí mi perro"})
        assert r.json()["reporte_codigo"].startswith("MC-")

    def test_las_urls_de_fotos_salen_por_el_proxy_del_frontend(
        self, db, cliente, cuenta_mascotas, crear, respuestas
    ):
        """El motor emite rutas del backend; el sitio las consume por el
        rewrite `/api/*` de Next."""
        mascota = crear(tipo_registro="encontrada", especie="perro")
        svc.guardar_foto(db, b"\xff\xd8img", "image/jpeg", mascota=mascota)
        respuestas(
            usa_tool("ver_ficha", {"codigo": mascota.codigo}),
            texto("¿Es esta tu mascota?"),
        )
        r = cliente.post("/mascotas/chat", json={"message": "sí"})

        media = [a for a in r.json()["actions"] if a["type"] == "say_media"]
        assert media and media[0]["url"].startswith("/api/mascotas/foto/")

    def test_el_cierre_fuera_de_alcance_pausa_el_canal(
        self, cliente, cuenta_mascotas, respuestas
    ):
        """Tras cerrar, el canal queda en pausa 20 minutos y los turnos
        siguientes NO gastan una llamada al modelo."""
        mock = respuestas(
            usa_tool("finalizar_fuera_de_alcance", {"motivo": "otro tema"},
                     dice="Aquí solo ayudo con mascotas 🤍"),
        )
        primera = cliente.post("/mascotas/chat", json={"message": "véndeme algo"})
        assert primera.json()["finished"] is True

        segunda = cliente.post("/mascotas/chat", json={"message": "hola?"})
        assert "en pausa" in segunda.json()["actions"][0]["text"]
        assert mock.call_count == 1, "el turno en pausa no puede llamar a Bedrock"

    def test_mensaje_demasiado_largo_se_rechaza(self, cliente, cuenta_mascotas):
        r = cliente.post("/mascotas/chat", json={"message": "x" * 5000})
        assert r.status_code == 422

    def test_el_turno_se_registra_para_el_panel(
        self, db, cliente, cuenta_mascotas, respuestas
    ):
        respuestas(texto("Hola 🐾"))
        cliente.post("/mascotas/chat", json={"message": "hola"})

        fila = db.query(models.BotLlmDecision).one()
        assert fila.source == "mascotas"
        assert fila.chat_ref, "sin chat_ref los turnos no se agrupan por conversación"
        assert fila.user_input == "hola"


class TestSubirFoto:
    def _jpeg(self):
        return ("foto.jpg", b"\xff\xd8\xff\xe0" + b"x" * 100, "image/jpeg")

    def test_guarda_la_foto_de_la_conversacion(self, cliente, db):
        r = cliente.post("/mascotas/foto", files={"file": self._jpeg()})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "session": None, "fotos": 1}
        assert db.query(models.MascotaFoto).count() == 1

    @pytest.mark.parametrize(
        "tipo", ["application/pdf", "text/html", "application/octet-stream"]
    )
    def test_solo_acepta_imagenes(self, cliente, tipo):
        r = cliente.post("/mascotas/foto", files={"file": ("x.pdf", b"%PDF", tipo)})
        assert r.status_code == 400
        assert "fotos" in r.json()["detail"]

    def test_una_foto_vacia_se_rechaza(self, cliente):
        r = cliente.post("/mascotas/foto", files={"file": ("x.jpg", b"", "image/jpeg")})
        assert r.status_code == 400

    def test_una_foto_gigante_se_rechaza(self, cliente):
        grande = b"\xff\xd8" + b"x" * (svc.MAX_PHOTO_BYTES + 10)
        r = cliente.post(
            "/mascotas/foto", files={"file": ("x.jpg", grande, "image/jpeg")}
        )
        assert r.status_code == 413

    def test_hay_un_techo_de_fotos_por_conversacion(
        self, cliente, db, cuenta_mascotas, respuestas
    ):
        # El techo es por conversación, así que hay que mandar siempre el mismo
        # token: sin `session`, cada subida abre un hilo nuevo y nunca se topa.
        respuestas(texto("Hola 🐾"))
        sesion = cliente.post("/mascotas/chat", json={"message": "hola"}).json()["session"]

        for _ in range(svc.MAX_FOTOS_POR_REPORTE):
            assert cliente.post(
                "/mascotas/foto", files={"file": self._jpeg()},
                data={"session": sesion},
            ).status_code == 200

        r = cliente.post(
            "/mascotas/foto", files={"file": self._jpeg()}, data={"session": sesion}
        )
        assert r.status_code == 400
        assert "suficientes" in r.json()["detail"]

    def test_un_fallo_del_storage_no_filtra_el_detalle(self, cliente, monkeypatch):
        """Regla de seguridad #6."""
        def explota(*_a, **_k):
            raise RuntimeError("s3://gloma-mascotas-747456040509 AccessDenied")

        monkeypatch.setattr(svc, "guardar_foto", explota)
        r = cliente.post("/mascotas/foto", files={"file": self._jpeg()})

        assert r.status_code == 503
        assert "747456040509" not in r.text
        assert "No pudimos guardar la foto" in r.json()["detail"]


class TestVerFoto:
    def test_sirve_la_imagen_sin_abrir_el_bucket(self, cliente, db, crear):
        mascota = crear(tipo_registro="encontrada", especie="perro")
        foto = svc.guardar_foto(db, b"\xff\xd8imagen", "image/jpeg", mascota=mascota)

        r = cliente.get(f"/mascotas/foto/{mascota.codigo}/{foto.id}")

        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")
        assert r.content

    def test_una_foto_que_no_es_de_ese_reporte_da_404(self, cliente, db, crear):
        mia = crear(tipo_registro="encontrada", especie="perro")
        ajena = crear(tipo_registro="encontrada", especie="gato")
        foto = svc.guardar_foto(db, b"\xff\xd8x", "image/jpeg", mascota=ajena)

        assert cliente.get(f"/mascotas/foto/{mia.codigo}/{foto.id}").status_code == 404

    def test_foto_inexistente(self, cliente, crear):
        mascota = crear(tipo_registro="encontrada", especie="perro")
        assert cliente.get(f"/mascotas/foto/{mascota.codigo}/999").status_code == 404


class TestDescargarListado:
    def _token(self, tipo="encontrada"):
        from app.services.crypto import encrypt_secret

        return encrypt_secret(json.dumps({"t": tipo, "exp": "listado"}))

    def test_con_token_valido_entrega_el_excel(self, cliente, crear):
        crear(tipo_registro="encontrada", especie="perro")
        r = cliente.get("/mascotas/listado.xlsx", params={"token": self._token()})

        assert r.status_code == 200
        assert r.content[:2] == b"PK", "un .xlsx es un zip"
        assert "attachment" in r.headers["content-disposition"]
        assert r.headers["cache-control"] == "no-store"

    def test_sin_token_no_se_descarga(self, cliente):
        assert cliente.get("/mascotas/listado.xlsx").status_code == 422

    @pytest.mark.parametrize("basura", ["x", "no-es-un-token", ""])
    def test_un_token_inventado_da_403(self, cliente, basura):
        r = cliente.get("/mascotas/listado.xlsx", params={"token": basura})
        assert r.status_code == 403

    def test_un_token_cifrado_por_nosotros_pero_de_otra_cosa_no_sirve(self, cliente):
        """Un token de sesión del chat no puede usarse para bajar el listado."""
        from app.services.crypto import encrypt_secret

        ajeno = encrypt_secret(json.dumps({"h": [], "n": 1}))
        r = cliente.get("/mascotas/listado.xlsx", params={"token": ajeno})
        assert r.status_code == 403
