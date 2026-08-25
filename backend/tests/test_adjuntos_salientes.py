"""El asesor le manda un archivo al cliente desde la ventana de Mensajes.

Antes solo se podía texto y plantillas: la foto de la habitación o el audio
explicando una tarifa salían del celular del asesor, por fuera de la
plataforma, y no quedaban en la conversación.

Lo que se protege acá no es que el archivo "se suba" —eso se ve a simple
vista— sino las cuatro cosas que se rompen calladas:

1. **La lista blanca.** Se acepta por lo que el archivo ES (su firma), no por
   lo que el navegador dice que es ni por cómo se llama. Un `.jpg` que no
   empieza con la firma de un JPEG no entra.
2. **El aislamiento entre tenants.** La conversación se resuelve siempre por
   `(team_id, id)` y el `team_id` va en la ruta del objeto guardado: pedir el
   adjunto de otro team con el `team_id` propio no devuelve nada.
3. **El endpoint público no es una ventana al bucket.** Es público a la fuerza
   (lo descarga el servidor de Meta/Twilio, que no manda token), así que lo
   único que lo sostiene es que el nombre tenga la forma exacta que emitimos.
4. **Un envío fallido deja rastro.** Si el proveedor rechaza el archivo, el
   mensaje se guarda como `failed` y al asesor le llega un texto genérico —
   el detalle del proveedor se queda en el log (regla de seguridad #6).

Nada de esto llama a WhatsApp ni a S3: el puerto de mensajería se reemplaza y
el storage escribe en una carpeta temporal.
"""
from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import datetime
from typing import Optional

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.routers import mensajes
from app.services import adjuntos, messaging

CLAVE = "Clave-De-Prueba-1"
# Repo público (regla #8): número inventado, ningún cliente real.
NUMERO_DE_PRUEBA = "573000000001"


# ---------------------------------------------------------------------------
# Mundo mínimo
# ---------------------------------------------------------------------------

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


def _equipo(db, correo: str, documento: str, nombre: str = "Agencia"):
    user = crud.create_user(
        db,
        schemas.UserCreate(
            nombre=nombre, correo=correo, tipo_documento="CC",
            documento=documento, password=CLAVE,
        ),
    )
    team = crud.create_team(db, nombre=nombre, owner=user)
    cuenta = models.MetaAccount(
        team_id=team.id,
        provider="twilio",
        display_phone="+57 300 000 0000",
        is_active=True,
        status="active",
    )
    db.add(cuenta)
    db.commit()
    return crud.get_membership_for_user(db, user)


@pytest.fixture
def equipo(db_session):
    return _equipo(db_session, "asesora@test.com", "ADJ-0001")


@pytest.fixture
def conversacion(db_session, equipo):
    conv = models.Conversation(
        team_id=equipo.team_id,
        contact_wa_id=NUMERO_DE_PRUEBA,
        contact_name="Clienta de prueba",
        status="open",
        last_message_at=datetime(2026, 8, 21, 9, 0, 0),
    )
    db_session.add(conv)
    db_session.commit()
    return conv


@pytest.fixture(autouse=True)
def storage_local(tmp_path, monkeypatch):
    """Disco en vez de S3, y en una carpeta que se borra sola.

    Los dos buckets se vacían a propósito: si la máquina que corre la suite
    tiene `MASCOTAS_BUCKET` en el entorno, un test escribiría en el bucket de
    producción.
    """
    monkeypatch.setenv("ADJUNTOS_MEDIA_DIR", str(tmp_path / "adjuntos"))
    monkeypatch.setenv("ADJUNTOS_BUCKET", "")
    monkeypatch.setenv("MASCOTAS_BUCKET", "")
    monkeypatch.setenv("ADJUNTOS_PUBLIC_BASE", "https://api.ejemplo.test")
    return tmp_path


@pytest.fixture
def enviados(monkeypatch):
    """Reemplaza el puerto de mensajería y guarda lo que se le pidió enviar."""
    llamadas = []

    def _fake(account, to_wa_id, media_url, caption=None, media_type="image"):
        llamadas.append({
            "to": to_wa_id, "url": media_url,
            "caption": caption, "media_type": media_type,
        })
        return f"SM-prueba-{len(llamadas)}", {"sandbox": True}

    monkeypatch.setattr(messaging, "send_media", _fake)
    return llamadas


@pytest.fixture
def proveedor_caido(monkeypatch):
    def _fake(*args, **kwargs):
        raise messaging.MessagingError(
            "media download failed: 415 desde el CDN del proveedor",
            provider="twilio", status_code=400,
        )

    monkeypatch.setattr(messaging, "send_media", _fake)


# ---------------------------------------------------------------------------
# Archivos de juguete
# ---------------------------------------------------------------------------

def _jpeg(ancho: int = 80, alto: int = 60) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), (20, 120, 90)).save(buf, format="JPEG")
    return buf.getvalue()


def _png() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


def _ogg(tamano: int = 4096) -> bytes:
    """Un OGG de mentira: al audio nadie lo decodifica, solo se mira la firma."""
    return b"OggS" + b"\x00" * (tamano - 4)


def _webm(tamano: int = 4096) -> bytes:
    """Lo que graba Chrome con `MediaRecorder` (cabecera Matroska)."""
    return b"\x1a\x45\xdf\xa3" + b"\x00" * (tamano - 4)


def _pdf(tamano: int = 2048) -> bytes:
    return b"%PDF-1.7\n" + b"0" * (tamano - 9)


def _docx() -> bytes:
    """Un .docx real es un ZIP. Con la firma alcanza: no lo abrimos."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


def _xls() -> bytes:
    """Office viejo: contenedor OLE2."""
    return b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 2048


_MIME_DOCX = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
_MIME_XLSX = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


def _subir(
    db,
    member,
    conversation_id: int,
    data: bytes,
    content_type: str,
    filename: str = "archivo.bin",
    caption: Optional[str] = None,
):
    """Llama al endpoint como lo haría el frontend (multipart).

    El endpoint es `def` (no `async`) a propósito —FastAPI lo corre en el
    threadpool para no bloquear el event loop, ver auditoría de seguridad #2—,
    así que se invoca directo, sin `asyncio.run`.
    """
    archivo = UploadFile(
        file=io.BytesIO(data),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )
    return mensajes.send_attachment_in_conversation(
        conversation_id=conversation_id,
        archivo=archivo,
        caption=caption,
        db=db,
        member=member,
    )


# ---------------------------------------------------------------------------
# Camino feliz
# ---------------------------------------------------------------------------

class TestEnviarImagen:
    def test_la_imagen_sale_y_queda_en_la_conversacion(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(
            db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "hotel.jpg",
            caption="Así es la habitación",
        )

        assert msg.message_type == "image"
        assert msg.status == "sent"
        assert msg.direction == "outbound"
        assert msg.sent_by_user_id == equipo.user_id
        assert msg.meta_message_id == "SM-prueba-1"

        # Una sola llamada al proveedor, con el número de ESTA conversación.
        assert len(enviados) == 1
        assert enviados[0]["to"] == NUMERO_DE_PRUEBA
        assert enviados[0]["media_type"] == "image"
        assert enviados[0]["caption"] == "Así es la habitación"

    def test_el_contenido_es_pie_mas_url_como_el_del_bot(
        self, db_session, equipo, conversacion, enviados
    ):
        """El frontend ya sabe leer este formato (`TIPOS_VISIBLES`): mismo
        camino que usa el bot al mandar un tarifario, cero columnas nuevas."""
        msg = _subir(
            db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "hotel.jpg",
            caption="Así es la habitación",
        )
        pie, url = msg.content.split("\n")
        assert pie == "Así es la habitación"
        assert url == enviados[0]["url"]

    def test_la_url_es_absoluta_y_apunta_al_endpoint_publico(
        self, db_session, equipo, conversacion, enviados
    ):
        """Absoluta porque quien la descarga es el servidor del proveedor, no
        el navegador del asesor."""
        _subir(db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg")
        url = enviados[0]["url"]
        assert url.startswith(
            f"https://api.ejemplo.test/mensajes/adjunto/{equipo.team_id}/"
        )

    def test_sin_pie_el_contenido_es_solo_la_url(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(db_session, equipo, conversacion.id, _png(), "image/png", "a.png")
        assert msg.content == enviados[0]["url"]
        assert "\n" not in msg.content

    def test_el_pie_se_recorta(self, db_session, equipo, conversacion, enviados):
        msg = _subir(
            db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg",
            caption="x" * 2000,
        )
        assert len(msg.content.split("\n")[0]) == adjuntos.MAX_CAPTION

    def test_el_archivo_queda_donde_lo_va_a_buscar_el_proveedor(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(
            db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg"
        )
        carpeta, nombre = msg.content.rsplit("/", 2)[-2:]

        encontrado = adjuntos.leer(equipo.team_id, carpeta, nombre)
        assert encontrado is not None
        data, content_type = encontrado
        assert data[:3] == b"\xff\xd8\xff"
        assert content_type == "image/jpeg"


class TestBombaDeDescompresion:
    """Auditoría de seguridad #1: una imagen de pocos bytes pero millones de
    píxeles decodifica a cientos de MB y tumba la task de 512 MB —y con ella a
    todos los tenants—. El tope en bytes (5 MB) no la ve; el de píxeles sí."""

    @staticmethod
    def _bomba_png(ancho: int = 13000, alto: int = 8400) -> bytes:
        """PNG de color sólido: se comprime a pocos KB pero pesa `ancho×alto`
        píxeles. 13000×8400 ≈ 109 MP, por encima de los 100 MP en que Pillow
        rompe al abrir: prueba que la resolución se mide igual (header, sin
        decodificar) en vez de tragarse el error y dejar pasar la bomba."""
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (ancho, alto), (0, 0, 0)).save(
            buf, format="PNG", compress_level=9
        )
        return buf.getvalue()

    def test_la_bomba_se_rechaza_y_no_se_guarda_el_original(
        self, db_session, equipo, conversacion, enviados
    ):
        from app.services import imagenes

        bomba = self._bomba_png()
        assert len(bomba) < adjuntos.LIMITES[adjuntos.IMAGEN], (
            "la bomba pasa el tope de bytes: por eso hace falta el de píxeles"
        )
        # El header se lee aunque el área supere el 2× de Pillow.
        assert imagenes.excede_resolucion(bomba) is True

        with pytest.raises(HTTPException) as e:
            _subir(db_session, equipo, conversacion.id, bomba, "image/png", "b.png")

        assert e.value.status_code == 400
        assert "resolución" in e.value.detail.lower()
        assert not enviados, "no debió salir nada al cliente"

    def test_una_imagen_normal_grande_sigue_pasando(
        self, db_session, equipo, conversacion, enviados
    ):
        """El guardarraíl caza bombas, no fotos legítimas: una foto de 8 MP
        (con contenido real, no color plano) entra sin problema."""
        import os

        from PIL import Image

        buf = io.BytesIO()
        # Ruido: no se comprime como el color plano, pero 8 MP < 50 MP de tope.
        Image.frombytes("RGB", (3264, 2448), os.urandom(3264 * 2448 * 3)).save(
            buf, format="JPEG", quality=70
        )
        foto = buf.getvalue()
        # Si la foto se pasara de 5 MB la cortaría el tope de bytes, no el de px.
        assert len(foto) < adjuntos.LIMITES[adjuntos.IMAGEN]

        msg = _subir(db_session, equipo, conversacion.id, foto, "image/jpeg", "f.jpg")
        assert msg.message_type == "image"
        assert enviados, "una foto legítima sí debe salir"


class TestEnviarAudio:
    def test_una_nota_de_voz_en_ogg_sale_tal_cual(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(
            db_session, equipo, conversacion.id, _ogg(), "audio/ogg", "nota.ogg"
        )
        assert msg.message_type == "audio"
        assert msg.status == "sent"
        assert enviados[0]["media_type"] == "audio"
        assert msg.content.endswith(".ogg")

    def test_el_webm_del_navegador_se_convierte_antes_de_salir(
        self, db_session, equipo, conversacion, enviados, monkeypatch
    ):
        """Chrome graba `audio/webm` y WhatsApp no lo acepta: si esto se
        rompiera, el asesor vería "enviado" y al cliente no le llega nada."""
        convertidos = []

        def _fake_ffmpeg(data: bytes):
            convertidos.append(len(data))
            return _ogg(1024)

        monkeypatch.setattr(adjuntos, "transcodificar_a_ogg", _fake_ffmpeg)

        msg = _subir(
            db_session, equipo, conversacion.id, _webm(), "audio/webm", "nota.webm"
        )

        assert convertidos, "el webm salió sin convertir"
        assert msg.message_type == "audio"
        assert msg.content.endswith(".ogg")

    def test_sin_ffmpeg_se_dice_qué_hacer_en_vez_de_reventar(
        self, db_session, equipo, conversacion, enviados, monkeypatch
    ):
        monkeypatch.setattr(adjuntos, "transcodificar_a_ogg", lambda data: None)

        with pytest.raises(HTTPException) as e:
            _subir(db_session, equipo, conversacion.id, _webm(), "audio/webm", "n.webm")

        assert e.value.status_code == 400
        assert "MP3" in e.value.detail
        assert not enviados

    def test_el_audio_va_sin_pie(
        self, db_session, equipo, conversacion, enviados
    ):
        """WhatsApp no muestra caption en una nota de voz: prometerlo sería
        mentirle al asesor."""
        _subir(
            db_session, equipo, conversacion.id, _ogg(), "audio/ogg", "n.ogg",
            caption="esto no se ve en una nota de voz",
        )
        assert enviados[0]["caption"] is None


class TestOtrosTipos:
    def test_un_pdf_sale_como_documento(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(
            db_session, equipo, conversacion.id, _pdf(), "application/pdf",
            "itinerario.pdf",
        )
        assert msg.message_type == "document"
        assert enviados[0]["media_type"] == "document"

    def test_un_octet_stream_se_resuelve_por_el_contenido(
        self, db_session, equipo, conversacion, enviados
    ):
        """Hay navegadores que mandan `application/octet-stream` y ya. Con la
        firma alcanza: el `Content-Type` es una pista, no la fuente de verdad."""
        msg = _subir(
            db_session, equipo, conversacion.id, _pdf(),
            "application/octet-stream", "itinerario.pdf",
        )
        assert msg.message_type == "document"


class TestLaConversionDeAudioNuncaRevienta:
    """`transcodificar_a_ogg` corre un binario externo: si algo sale mal tiene
    que devolver `None`, no tumbar el request del asesor. Vale igual en una
    máquina con ffmpeg (falla al convertir basura) y en una sin él."""

    def test_un_archivo_que_no_es_audio_devuelve_none(self):
        assert adjuntos.transcodificar_a_ogg(b"esto no es audio" * 50) is None

    def test_sin_ffmpeg_instalado_tampoco_revienta(self, monkeypatch):
        def _no_existe(*args, **kwargs):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(adjuntos.subprocess, "run", _no_existe)
        assert adjuntos.transcodificar_a_ogg(_webm()) is None


# ---------------------------------------------------------------------------
# Lo que no entra
# ---------------------------------------------------------------------------

class TestListaBlanca:
    def test_un_ejecutable_no_entra(
        self, db_session, equipo, conversacion, enviados
    ):
        with pytest.raises(HTTPException) as e:
            _subir(
                db_session, equipo, conversacion.id,
                b"MZ\x90\x00" + b"\x00" * 500, "application/x-msdownload", "virus.exe",
            )
        assert e.value.status_code == 400
        assert not enviados

    def test_un_svg_tampoco_aunque_sea_imagen(
        self, db_session, equipo, conversacion, enviados
    ):
        """SVG es XML con scripts adentro y el endpoint que lo serviría es
        público: no está en la lista blanca y no se cuela por llamarse imagen."""
        with pytest.raises(HTTPException) as e:
            _subir(
                db_session, equipo, conversacion.id,
                b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>",
                "image/svg+xml", "logo.svg",
            )
        assert e.value.status_code == 400
        assert not enviados

    def test_renombrar_un_archivo_a_jpg_no_lo_vuelve_una_imagen(
        self, db_session, equipo, conversacion, enviados
    ):
        """El `Content-Type` lo pone el navegador y el nombre lo pone quien
        sube: los dos se pueden mentir. La firma no."""
        with pytest.raises(HTTPException) as e:
            _subir(
                db_session, equipo, conversacion.id,
                b"esto es texto plano, no una foto" * 20, "image/jpeg", "foto.jpg",
            )
        assert e.value.status_code == 400
        assert "no parece una imagen" in e.value.detail
        assert not enviados

    def test_un_archivo_vacio_no_entra(self, db_session, equipo, conversacion):
        with pytest.raises(HTTPException) as e:
            _subir(db_session, equipo, conversacion.id, b"", "image/jpeg", "v.jpg")
        assert e.value.status_code == 400

    def test_una_imagen_de_mas_de_5_mb_no_entra(
        self, db_session, equipo, conversacion, enviados
    ):
        """El tope de Meta para imágenes. Se corta antes de comprimir: no se
        gasta CPU en un archivo que igual no se va a poder enviar."""
        pesada = b"\xff\xd8\xff" + b"\x00" * (adjuntos.LIMITES[adjuntos.IMAGEN])

        with pytest.raises(HTTPException) as e:
            _subir(db_session, equipo, conversacion.id, pesada, "image/jpeg", "g.jpg")

        assert e.value.status_code == 400
        assert "pesa demasiado" in e.value.detail
        assert not enviados

    def test_un_audio_de_mas_de_16_mb_tampoco(
        self, db_session, equipo, conversacion, enviados
    ):
        pesado = _ogg(adjuntos.LIMITES[adjuntos.AUDIO] + 10)
        with pytest.raises(HTTPException) as e:
            _subir(db_session, equipo, conversacion.id, pesado, "audio/ogg", "n.ogg")
        assert e.value.status_code == 400
        assert not enviados

    def test_nada_de_esto_deja_mensajes_a_medias(
        self, db_session, equipo, conversacion, enviados
    ):
        """Un archivo rechazado no es un envío fallido: no tiene por qué
        aparecer en el chat del cliente ni en la bandeja."""
        for data, tipo, nombre in (
            (b"MZ\x90\x00" + b"\x00" * 500, "application/x-msdownload", "v.exe"),
            (b"no soy una foto" * 40, "image/jpeg", "f.jpg"),
            (b"", "image/jpeg", "v.jpg"),
        ):
            with pytest.raises(HTTPException):
                _subir(db_session, equipo, conversacion.id, data, tipo, nombre)

        assert db_session.query(models.Message).count() == 0


# ---------------------------------------------------------------------------
# Aislamiento y errores del proveedor
# ---------------------------------------------------------------------------

class TestAislamiento:
    def test_la_conversacion_de_otro_team_no_existe_para_mi(
        self, db_session, equipo, enviados
    ):
        ajeno = _equipo(db_session, "ajena@test.com", "ADJ-0002", nombre="Otra agencia")
        conv_ajena = models.Conversation(
            team_id=ajeno.team_id,
            contact_wa_id="573000000009",
            status="open",
            last_message_at=datetime(2026, 8, 21, 9, 0, 0),
        )
        db_session.add(conv_ajena)
        db_session.commit()

        with pytest.raises(HTTPException) as e:
            _subir(
                db_session, equipo, conv_ajena.id, _jpeg(), "image/jpeg", "h.jpg"
            )

        assert e.value.status_code == 404
        assert not enviados
        assert db_session.query(models.Message).count() == 0

    def test_el_adjunto_de_otro_team_no_se_lee_con_mi_team_id(
        self, db_session, equipo, conversacion, enviados
    ):
        """El `team_id` va en la ruta del objeto: conocer el nombre no alcanza
        para sacarlo de la carpeta de su dueño."""
        msg = _subir(db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg")
        carpeta, nombre = msg.content.rsplit("/", 2)[-2:]

        assert adjuntos.leer(equipo.team_id, carpeta, nombre) is not None
        assert adjuntos.leer(equipo.team_id + 1, carpeta, nombre) is None

    def test_sin_cuenta_de_whatsapp_activa_no_se_envia(
        self, db_session, equipo, conversacion, enviados
    ):
        cuenta = crud.get_meta_account_for_team(db_session, equipo.team_id)
        cuenta.status = "invalid"
        db_session.commit()

        with pytest.raises(HTTPException) as e:
            _subir(db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg")

        assert e.value.status_code == 409
        assert not enviados


class TestElProveedorFalla:
    def test_responde_502_y_el_mensaje_queda_marcado_failed(
        self, db_session, equipo, conversacion, proveedor_caido
    ):
        with pytest.raises(HTTPException) as e:
            _subir(
                db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg",
                caption="Mira",
            )

        assert e.value.status_code == 502

        guardado = db_session.query(models.Message).one()
        assert guardado.status == "failed"
        assert guardado.message_type == "image"
        assert guardado.content.startswith("Mira\n")
        assert guardado.sent_by_user_id == equipo.user_id

    def test_al_asesor_no_le_llega_el_detalle_del_proveedor(
        self, db_session, equipo, conversacion, proveedor_caido
    ):
        """Regla de seguridad #6: el detalle vive en `logger.exception` y en
        `error_detail`, nunca en la respuesta."""
        with pytest.raises(HTTPException) as e:
            _subir(db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg")

        assert e.value.detail == "Error del proveedor de WhatsApp al enviar el archivo"
        assert "415" not in e.value.detail
        assert "CDN" not in e.value.detail

        guardado = db_session.query(models.Message).one()
        assert "415" in (guardado.error_detail or "")


# ---------------------------------------------------------------------------
# Documentos (Word, Excel, PowerPoint, texto) — pedido del CEO
# ---------------------------------------------------------------------------

class TestEnviarDocumentos:
    """Un asesor manda un itinerario en Word o una cotización en Excel tan
    seguido como un PDF; antes solo pasaba el PDF."""

    @pytest.mark.parametrize("data,mime,filename", [
        (_docx(), _MIME_DOCX, "itinerario.docx"),
        (_docx(), _MIME_XLSX, "cotizacion.xlsx"),
        (_xls(), "application/vnd.ms-excel", "tarifas.xls"),
        (_xls(), "application/msword", "contrato.doc"),
        (b"Hola, esto es texto plano.\n", "text/plain", "notas.txt"),
        (b"hotel,precio\nAmor de Dios,459000\n", "text/csv", "precios.csv"),
    ])
    def test_los_documentos_de_oficina_se_envian(
        self, db_session, equipo, conversacion, enviados, data, mime, filename
    ):
        msg = _subir(db_session, equipo, conversacion.id, data, mime, filename)

        assert msg.message_type == "document"
        assert msg.status == "sent"
        assert enviados[0]["media_type"] == "document"

    def test_un_ejecutable_disfrazado_de_word_no_pasa(
        self, db_session, equipo, conversacion, enviados
    ):
        """El `Content-Type` lo pone quien sube el archivo: si no exigiéramos
        que además *sea* un ZIP, bastaría con renombrar cualquier cosa."""
        with pytest.raises(HTTPException) as e:
            _subir(
                db_session, equipo, conversacion.id,
                b"MZ\x90\x00" + b"\x00" * 2048, _MIME_DOCX, "factura.docx",
            )
        assert e.value.status_code == 400
        assert "no parece un documento" in e.value.detail
        assert enviados == []

    def test_un_binario_disfrazado_de_txt_no_pasa(
        self, db_session, equipo, conversacion, enviados
    ):
        with pytest.raises(HTTPException) as e:
            _subir(
                db_session, equipo, conversacion.id,
                b"\x00\x01\x02\x03" * 64, "text/plain", "notas.txt",
            )
        assert e.value.status_code == 400
        assert enviados == []

    def test_el_csv_que_windows_declara_como_excel_igual_pasa(
        self, db_session, equipo, conversacion, enviados
    ):
        """Windows manda los .csv como `application/vnd.ms-excel`, que pide
        firma OLE2 y no la tiene. Rechazarlo sería rechazar un archivo bueno."""
        msg = _subir(
            db_session, equipo, conversacion.id,
            b"hotel,precio\nPiedra Mar,469000\n",
            "application/vnd.ms-excel", "precios.csv",
        )
        assert msg.message_type == "document"
        assert msg.content.endswith(".csv")

    def test_un_documento_lleva_pie_pero_la_nota_de_voz_no(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(
            db_session, equipo, conversacion.id, _pdf(), "application/pdf",
            "plan.pdf", caption="Te mando el plan completo",
        )
        assert msg.content.startswith("Te mando el plan completo\n")


# ---------------------------------------------------------------------------
# Emojis — pedido del CEO
# ---------------------------------------------------------------------------

class TestEmojis:
    """El bot escribe con emojis desde siempre; el asesor tenía que copiarlos de
    otro lado. Lo que se prueba acá es que no se rompan en el camino: los que
    llevan modificador (🏝️) y los compuestos por varios puntos de código
    (🇨🇴, 👩‍💻) son los que se parten cuando algo del camino no es UTF-8."""

    @pytest.mark.parametrize("texto", [
        "¡Listo! 😊🌴",
        "Te espero 🏝️ con el plan ✨",
        "Desde Colombia 🇨🇴",
        "Te atiende 👩‍💻 al instante",
    ])
    def test_el_emoji_llega_igual_al_proveedor(
        self, db_session, equipo, conversacion, monkeypatch, texto
    ):
        enviados = []

        def _fake(account, to_wa_id, body):
            enviados.append(body)
            return "SM-texto", {"sandbox": True}

        monkeypatch.setattr(messaging, "send_text", _fake)

        msg = mensajes.send_message_in_conversation(
            conversation_id=conversacion.id,
            payload=schemas.MessageSendIn(content=texto),
            db=db_session,
            member=equipo,
        )

        assert enviados == [texto]
        assert msg.content == texto

    def test_el_emoji_tambien_vale_como_pie_de_una_imagen(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(
            db_session, equipo, conversacion.id, _jpeg(), "image/jpeg", "h.jpg",
            caption="La habitación 😍🌴",
        )
        assert enviados[0]["caption"] == "La habitación 😍🌴"
        assert msg.content.startswith("La habitación 😍🌴\n")


# ---------------------------------------------------------------------------
# El endpoint público
# ---------------------------------------------------------------------------

class TestServirElAdjunto:
    def test_entrega_el_archivo_con_su_tipo_real(
        self, db_session, equipo, conversacion, enviados
    ):
        msg = _subir(db_session, equipo, conversacion.id, _pdf(), "application/pdf", "i.pdf")
        carpeta, nombre = msg.content.rsplit("/", 2)[-2:]

        resp = mensajes.ver_adjunto(equipo.team_id, carpeta, nombre)

        assert resp.status_code == 200
        assert resp.media_type == "application/pdf"
        assert resp.body.startswith(b"%PDF-")
        assert resp.headers["x-content-type-options"] == "nosniff"

    def test_el_documento_conserva_el_nombre_que_le_puso_el_asesor(
        self, db_session, equipo, conversacion, enviados
    ):
        """Lo que WhatsApp le muestra a quien recibe un documento es el último
        tramo de la URL. Un uuid ahí parece un archivo basura, no la cotización
        que le acaban de mandar."""
        msg = _subir(
            db_session, equipo, conversacion.id, _pdf(), "application/pdf",
            "Itinerario Coveñas 2026.pdf",
        )
        carpeta, nombre = msg.content.rsplit("/", 2)[-2:]

        assert nombre == "Itinerario-Covenas-2026.pdf"
        # La carpeta sigue siendo el uuid: es lo que lo hace impredecible.
        assert adjuntos.CARPETA_RE.match(carpeta)
        resp = mensajes.ver_adjunto(equipo.team_id, carpeta, nombre)
        assert resp.headers["content-disposition"].endswith(
            'filename="Itinerario-Covenas-2026.pdf"'
        )

    @pytest.mark.parametrize("carpeta,nombre", [
        ("..", "../etc/passwd"),
        ("../otro-team", "a" * 32 + ".jpg"),
        ("..%2f..%2fmascotas", "MC-00001%2ffoto.jpg"),
        ("a" * 32, "foto.jpg/../../secreto"),
        ("a" * 32, "archivo.php"),
        ("a" * 32, "sin-extension"),
        ("a" * 31, "foto.jpg"),          # uuid incompleto
        ("A" * 32, "foto.jpg"),          # hex en mayúsculas: no es lo que emitimos
        ("", "foto.jpg"),
        ("a" * 32, ""),
        ("a" * 32, "x" * 61 + ".jpg"),   # nombre más largo del que emitimos
    ])
    def test_una_ruta_que_no_emitimos_nosotros_no_se_sirve(self, carpeta, nombre):
        """El endpoint es público a la fuerza (lo descarga el servidor del
        proveedor, que no manda token). Lo único que impide que sea una ventana
        al bucket es exigir la forma exacta de la ruta."""
        with pytest.raises(HTTPException) as e:
            mensajes.ver_adjunto(1, carpeta, nombre)
        assert e.value.status_code == 404

    def test_una_ruta_bien_formada_que_no_existe_es_404(self):
        with pytest.raises(HTTPException) as e:
            mensajes.ver_adjunto(1, "0" * 32, "foto.jpg")
        assert e.value.status_code == 404

    def test_no_se_puede_pedir_una_foto_de_mascotas_desde_aca(
        self, db_session, equipo, conversacion, enviados
    ):
        """Los dos módulos comparten bucket con prefijos distintos: la key
        siempre se arma acá, nunca llega desde afuera."""
        assert adjuntos.key_de(equipo.team_id, "x", "y.jpg").startswith("adjuntos/")
        assert adjuntos.leer(equipo.team_id, "mascotas", "MC-00001/foto.jpg") is None
        assert adjuntos.leer(equipo.team_id, "../mascotas", "foto.jpg") is None


# ---------------------------------------------------------------------------
# La bandeja sigue funcionando (el campo `etiqueta` que pidió el frontend)
# ---------------------------------------------------------------------------

class TestLaBandejaNoSeRompe:
    def test_la_lista_responde_aunque_la_columna_etiqueta_no_exista(
        self, db_session, equipo, conversacion
    ):
        """`getattr(c, "etiqueta", None)`: la columna la agrega otra migración y
        la bandeja tiene que seguir sirviendo mientras tanto."""
        salida = mensajes.list_conversations(
            estado=None, busqueda=None, limite=20, pagina=1,
            db=db_session, member=equipo,
        )
        assert [c.id for c in salida.conversaciones] == [conversacion.id]

    def test_el_detalle_también(self, db_session, equipo, conversacion):
        detalle = mensajes.get_conversation(
            conversation_id=conversacion.id, db=db_session, member=equipo
        )
        assert detalle.id == conversacion.id
