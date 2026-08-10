"""Tests del lector de la cola de publicaciones de Instagram.

Cubre el parseo del JSON que escribe `marketing/instagram/igpost.py`, el orden
en que se muestra en el panel y el manejo de errores de S3. No tocan red: el
cliente de boto3 se sustituye por un doble.
"""
from __future__ import annotations

import json
import os
import unittest
from datetime import datetime, timezone
from unittest import mock

from botocore.exceptions import ClientError
from cryptography.fernet import Fernet

# El módulo de cifrado hace fail-fast al importarse: clave efímera en tests.
os.environ.setdefault("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())

from app.services import instagram_queue  # noqa: E402


def _item(**over):
    base = {
        "id": "abc123",
        "slug": "01_mensaje_1147pm",
        "caption": "Texto de la pieza",
        "media_keys": ["posts/01_mensaje_1147pm/01-aaa.jpg"],
        "publish_at": "2026-08-20T09:00:00-05:00",
        "status": "pending",
        "created_at": "2026-08-09T10:00:00-05:00",
        "attempts": 0,
    }
    base.update(over)
    return base


class _FakeS3:
    """Doble del cliente S3: sirve un cuerpo fijo y firma URLs deterministas."""

    def __init__(self, body=None, error=None):
        self._body = body
        self._error = error

    def get_object(self, **_kw):
        if self._error:
            raise self._error
        return {"Body": mock.Mock(read=lambda: json.dumps(self._body).encode())}

    def generate_presigned_url(self, _op, Params, ExpiresIn):  # noqa: N803
        return f"https://s3.test/{Params['Key']}?ttl={ExpiresIn}"


def _patch(fake):
    return mock.patch.object(instagram_queue, "_client", return_value=fake)


def _client_error(code):
    return ClientError({"Error": {"Code": code, "Message": code}}, "GetObject")


class TestLoadQueue(unittest.TestCase):
    def test_cola_inexistente_es_lista_vacia(self):
        """Que nadie haya programado nada todavía es un estado válido."""
        with _patch(_FakeS3(error=_client_error("NoSuchKey"))):
            self.assertEqual(instagram_queue.load_queue(), [])

    def test_parsea_publicacion_y_firma_slides(self):
        with _patch(_FakeS3(body=[_item(media_keys=["posts/p/01-a.jpg", "posts/p/02-b.jpg"])])):
            posts = instagram_queue.load_queue()

        self.assertEqual(len(posts), 1)
        post = posts[0]
        self.assertEqual(post.id, "abc123")
        self.assertEqual(post.status, "pending")
        self.assertEqual(post.publish_at, datetime.fromisoformat("2026-08-20T09:00:00-05:00"))
        self.assertEqual(len(post.slides), 2)
        self.assertEqual(post.slides[0].index, 1)
        self.assertEqual(post.slides[0].filename, "01-a.jpg")
        self.assertIn("posts/p/01-a.jpg", post.slides[0].download_url)

    def test_orden_pendientes_primero_por_fecha(self):
        body = [
            _item(id="ya", status="published", publish_at="2026-08-10T09:00:00-05:00"),
            _item(id="tarde", publish_at="2026-08-25T09:00:00-05:00"),
            _item(id="pronto", publish_at="2026-08-12T09:00:00-05:00"),
        ]
        with _patch(_FakeS3(body=body)):
            ids = [p.id for p in instagram_queue.load_queue()]

        # Lo próximo a salir arriba; lo ya publicado al final.
        self.assertEqual(ids, ["pronto", "tarde", "ya"])

    def test_publicacion_sin_fecha_no_rompe_el_orden(self):
        """Regresión: el fallback de orden debe ser aware, no `datetime.min`
        naive, o comparar contra fechas con zona horaria lanza TypeError."""
        body = [_item(id="sin", publish_at=None), _item(id="con")]
        with _patch(_FakeS3(body=body)):
            posts = instagram_queue.load_queue()

        self.assertEqual([p.id for p in posts], ["sin", "con"])
        self.assertIsNone(posts[0].publish_at)

    def test_fecha_ilegible_no_tumba_la_cola(self):
        with _patch(_FakeS3(body=[_item(publish_at="ayer por la tarde")])):
            posts = instagram_queue.load_queue()
        self.assertIsNone(posts[0].publish_at)

    def test_error_de_s3_se_traduce_a_mensaje_limpio(self):
        """Regla de seguridad #6: al cliente no le llega el detalle de AWS."""
        with _patch(_FakeS3(error=_client_error("AccessDenied"))):
            with self.assertRaises(instagram_queue.QueueUnavailable) as ctx:
                instagram_queue.load_queue()

        mensaje = str(ctx.exception)
        self.assertNotIn("AccessDenied", mensaje)
        self.assertIn("No se pudo leer la cola", mensaje)

    def test_bucket_ausente_avisa_que_falta_configurar(self):
        with _patch(_FakeS3(error=_client_error("NoSuchBucket"))):
            with self.assertRaises(instagram_queue.QueueUnavailable) as ctx:
                instagram_queue.load_queue()
        self.assertIn("no está configurada", str(ctx.exception))

    def test_json_corrupto_no_propaga_la_excepcion_cruda(self):
        fake = _FakeS3(body=None)
        fake.get_object = lambda **_kw: {"Body": mock.Mock(read=lambda: b"{no es json")}
        with _patch(fake):
            with self.assertRaises(instagram_queue.QueueUnavailable):
                instagram_queue.load_queue()

    def test_descarga_forzada_con_nombre_legible(self):
        """El enlace debe descargar el archivo, no abrirlo en el navegador."""
        capturado = {}

        fake = _FakeS3(body=[_item()])
        original = fake.generate_presigned_url

        def espia(op, Params, ExpiresIn):  # noqa: N803
            capturado.update(Params)
            return original(op, Params, ExpiresIn)

        fake.generate_presigned_url = espia
        with _patch(fake):
            instagram_queue.load_queue()

        disp = capturado.get("ResponseContentDisposition", "")
        self.assertIn("attachment", disp)
        self.assertIn("01_mensaje_1147pm_01.jpg", disp)


class TestRouter(unittest.TestCase):
    """Contrato del endpoint `/instagram`, sin BD: se monta solo el router y se
    sustituye el portero de autorización."""

    def _app(self, autorizado=True):
        from fastapi import FastAPI, HTTPException

        from app.dependencies import require_gloma_account
        from app.routers import instagram as router_mod

        app = FastAPI()
        app.include_router(router_mod.router)

        def _gate():
            if not autorizado:
                raise HTTPException(status_code=403, detail="No tienes acceso a este módulo")
            return mock.Mock(correo="gloma@glomabeauty.com")

        app.dependency_overrides[require_gloma_account] = _gate
        return app

    def _client(self, app):
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_lista_cola_con_resumen(self):
        body = [
            _item(id="a"),
            _item(id="b", status="published", permalink="https://instagram.com/p/x"),
            _item(id="c", status="failed", error="Instagram rechazó el contenido"),
        ]
        with _patch(_FakeS3(body=body)):
            resp = self._client(self._app()).get("/instagram")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["resumen"], {
            "total": 3, "programadas": 1, "publicadas": 1, "fallidas": 1, "canceladas": 0,
        })
        publicadas = {p["id"]: p for p in data["publicaciones"]}
        self.assertEqual(publicadas["b"]["permalink"], "https://instagram.com/p/x")
        self.assertEqual(publicadas["c"]["error"], "Instagram rechazó el contenido")
        self.assertTrue(publicadas["a"]["slides"][0]["download_url"].startswith("https://"))

    def test_cuenta_ajena_recibe_403(self):
        with _patch(_FakeS3(body=[])):
            resp = self._client(self._app(autorizado=False)).get("/instagram")
        self.assertEqual(resp.status_code, 403)

    def test_cola_inaccesible_devuelve_503(self):
        with _patch(_FakeS3(error=_client_error("AccessDenied"))):
            resp = self._client(self._app()).get("/instagram")
        self.assertEqual(resp.status_code, 503)
        self.assertNotIn("AccessDenied", resp.json()["detail"])


class _FakeQueueS3:
    """Doble de S3 para el publicador: cola en memoria con ETag simulado."""

    def __init__(self, items, conflict_on_put=False):
        self.items = items
        self.etag = "v1"
        self.conflict_on_put = conflict_on_put
        self.puts = 0

    def get_object(self, **_kw):
        body = json.dumps(self.items).encode()
        return {"Body": mock.Mock(read=lambda: body), "ETag": self.etag}

    def put_object(self, **kw):
        if self.conflict_on_put:
            raise _client_error("PreconditionFailed")
        self.puts += 1
        self.items = json.loads(kw["Body"])
        self.etag = f"v{self.puts + 1}"
        return {}

    def generate_presigned_url(self, _op, Params, ExpiresIn):  # noqa: N803
        return f"https://s3.test/{Params['Key']}"


class TestPublisher(unittest.TestCase):
    """Claim atómico y transiciones de estado del botón 'Publicar ahora'."""

    def _patch_s3(self, fake):
        from app.services import instagram_publisher as pub

        return mock.patch.object(pub, "_s3", return_value=fake)

    def test_claim_pieza_pendiente(self):
        from app.services import instagram_publisher as pub

        fake = _FakeQueueS3([_item()])
        with self._patch_s3(fake):
            claimed = pub._claim("abc123")
        self.assertEqual(claimed["status"], "publishing")
        self.assertEqual(fake.items[0]["status"], "publishing")

    def test_claim_rechaza_ya_publicada(self):
        from app.services import instagram_publisher as pub

        with self._patch_s3(_FakeQueueS3([_item(status="published")])):
            with self.assertRaises(pub.NotPublishable):
                pub._claim("abc123")

    def test_claim_rechaza_en_vuelo(self):
        """Si el cron la está publicando ahora mismo → AlreadyClaimed (409)."""
        from app.services import instagram_publisher as pub

        with self._patch_s3(_FakeQueueS3([_item(status="publishing")])):
            with self.assertRaises(pub.AlreadyClaimed):
                pub._claim("abc123")

    def test_claim_pierde_la_carrera_del_etag(self):
        """El cron escribió entre nuestra lectura y escritura → AlreadyClaimed."""
        from app.services import instagram_publisher as pub

        with self._patch_s3(_FakeQueueS3([_item()], conflict_on_put=True)):
            with self.assertRaises(pub.AlreadyClaimed):
                pub._claim("abc123")

    def test_publish_now_publica_y_marca(self):
        from app.services import instagram_publisher as pub

        fake = _FakeQueueS3([_item()])
        with self._patch_s3(fake), mock.patch.object(
            pub, "_credentials", return_value=("tok", "999")
        ), mock.patch.object(pub, "_publish_media", return_value="MEDIA1"), mock.patch.object(
            pub, "_graph", return_value={"permalink": "https://instagram.com/p/x"}
        ):
            resultado = pub.publish_now("abc123")

        self.assertEqual(resultado["status"], "published")
        self.assertEqual(resultado["media_id"], "MEDIA1")
        self.assertEqual(fake.items[0]["status"], "published")

    def test_publish_now_fallo_vuelve_a_pending(self):
        from app.services import instagram_publisher as pub

        fake = _FakeQueueS3([_item()])
        with self._patch_s3(fake), mock.patch.object(
            pub, "_credentials", return_value=("tok", "999")
        ), mock.patch.object(
            pub, "_publish_media", side_effect=pub.PublishError("Instagram rechazó")
        ):
            with self.assertRaises(pub.PublishError):
                pub.publish_now("abc123")

        self.assertEqual(fake.items[0]["status"], "pending")
        self.assertEqual(fake.items[0]["attempts"], 1)

    def test_endpoint_mapea_conflicto_a_409(self):
        from app.services import instagram_publisher as pub

        router_test = TestRouter()
        app = router_test._app()
        with mock.patch.object(
            pub, "publish_now", side_effect=pub.AlreadyClaimed("en vuelo")
        ):
            resp = router_test._client(app).post("/instagram/abc123/publish")
        self.assertEqual(resp.status_code, 409)

    def test_endpoint_publica(self):
        from app.services import instagram_publisher as pub

        router_test = TestRouter()
        app = router_test._app()
        publicado = _item(status="published", media_id="M1", permalink="https://ig/p")
        with mock.patch.object(pub, "publish_now", return_value=publicado):
            resp = router_test._client(app).post("/instagram/abc123/publish")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["media_id"], "M1")


if __name__ == "__main__":
    unittest.main()
