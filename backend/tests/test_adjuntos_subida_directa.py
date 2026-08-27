"""El archivo sube directo a S3, sin pasar por nuestra API.

Por qué existe este camino, que es lo que hay que entender antes de tocarlo:
entre el navegador y ECS hay dos saltos con techo propio —el compute de
Amplify (~4,4 MB, porque el cuerpo viaja en base64 dentro del payload de una
Lambda) y el API Gateway HTTP (10 MB duros, cuota que AWS no deja subir)—. Un
video de 10 MB moría ahí con un 413, dijera lo que dijera el límite del código.
Subiendo contra S3 con un POST prefirmado no hay ninguno de los dos.

Lo que se protege acá son las cuatro cosas que ese rodeo pone en riesgo:

1. **La validación no se saltea.** El camino nuevo termina en la MISMA función
   que el viejo: firma real de los bytes, lista blanca, tope y bomba de
   descompresión. Un ejecutable que se subió a mano a la zona de tránsito no
   sale por WhatsApp por haber entrado por la puerta de atrás.
2. **La credencial que emitimos está acotada.** La key la elige el servidor, el
   `team_id` sale de la membresía autenticada (no del request), el tamaño va
   firmado en las condiciones y la URL expira.
3. **La zona de tránsito no es servible.** Lo que hay en `adjuntos-tmp/` son
   bytes de un desconocido; el endpoint público no puede alcanzarlos ni
   conociendo la referencia.
4. **No queda basura.** El temporal se borra pase lo que pase, incluso cuando
   la validación rechaza el archivo.

Acá no se habla con S3: el cliente de boto3 se reemplaza por uno de mentira que
guarda los objetos en un diccionario.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud, models, schemas
from app.routers import mensajes
from app.services import adjuntos, messaging

CLAVE = "Clave-De-Prueba-1"
# Repo público (regla #8): número inventado, ningún cliente real.
NUMERO_DE_PRUEBA = "573000000002"
BUCKET = "bucket-de-prueba"


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
    db.add(models.MetaAccount(
        team_id=team.id, provider="twilio", display_phone="+57 300 000 0000",
        is_active=True, status="active",
    ))
    db.commit()
    return crud.get_membership_for_user(db, user)


@pytest.fixture
def equipo(db_session):
    return _equipo(db_session, "asesora@directa.com", "DIR-0001")


@pytest.fixture
def conversacion(db_session, equipo):
    conv = models.Conversation(
        team_id=equipo.team_id,
        contact_wa_id=NUMERO_DE_PRUEBA,
        contact_name="Clienta de prueba",
        status="open",
        last_message_at=datetime(2026, 8, 27, 9, 0, 0),
    )
    db_session.add(conv)
    db_session.commit()
    return conv


class S3DeMentira:
    """Lo mínimo de la API de boto3 que usa el módulo, con los objetos en RAM.

    Registra además las condiciones con las que se firmó cada POST: son parte
    del contrato de seguridad, no un detalle de implementación.
    """

    def __init__(self):
        self.objetos: dict[str, bytes] = {}
        self.firmas: list[dict] = []
        self.borrados: list[str] = []

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):  # noqa: N803
        self.firmas.append({
            "bucket": Bucket, "key": Key, "campos": Fields,
            "condiciones": Conditions, "expira": ExpiresIn,
        })
        return {
            "url": f"https://{Bucket}.s3.amazonaws.com/",
            "fields": {"key": Key, "policy": "xxx", "x-amz-signature": "yyy"},
        }

    def put_object(self, Bucket, Key, Body, ContentType=None):  # noqa: N803
        self.objetos[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objetos:
            raise KeyError(Key)
        return {"Body": io.BytesIO(self.objetos[Key])}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.borrados.append(Key)
        self.objetos.pop(Key, None)


@pytest.fixture
def s3(monkeypatch):
    """S3 de mentira + el bucket configurado, que es lo que activa el camino."""
    falso = S3DeMentira()
    monkeypatch.setenv("ADJUNTOS_BUCKET", BUCKET)
    monkeypatch.setenv("ADJUNTOS_PUBLIC_BASE", "https://api.ejemplo.test")
    monkeypatch.setattr(adjuntos, "_s3", lambda: falso)
    return falso


@pytest.fixture
def enviados(monkeypatch):
    llamadas = []

    def _fake(account, to_wa_id, media_url, caption=None, media_type="image"):
        llamadas.append({
            "to": to_wa_id, "url": media_url,
            "caption": caption, "media_type": media_type,
        })
        return f"SM-directa-{len(llamadas)}", {"sandbox": True}

    monkeypatch.setattr(messaging, "send_media", _fake)
    return llamadas


def _jpeg(ancho: int = 80, alto: int = 60) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), (20, 120, 90)).save(buf, format="JPEG")
    return buf.getvalue()


def _mp4(tamano: int) -> bytes:
    """Contenedor ISO-BMFF: los 4 bytes de tamaño y luego `ftyp`."""
    cabecera = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8
    return cabecera + b"\x00" * max(0, tamano - len(cabecera))


def _preparar(db, member, conv_id, *, filename, content_type, size):
    return mensajes.prepare_attachment_upload(
        conversation_id=conv_id,
        datos=schemas.AdjuntoPrepararIn(
            filename=filename, content_type=content_type, size=size
        ),
        db=db, member=member,
    )


def _confirmar(db, member, conv_id, referencia, *, filename=None,
               content_type=None, caption: Optional[str] = None):
    return mensajes.confirm_attachment_upload(
        conversation_id=conv_id,
        datos=schemas.AdjuntoConfirmarIn(
            referencia=referencia, filename=filename,
            content_type=content_type, caption=caption,
        ),
        db=db, member=member,
    )


# ---------------------------------------------------------------------------
# El video de 10 MB, que es todo el motivo de este camino
# ---------------------------------------------------------------------------

class TestVideoGrande:
    def test_un_video_de_10_mb_sale_completo(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        """El caso que reportó el CEO: 10 MB, que por la API no pasaban nunca."""
        video = _mp4(10 * 1024 * 1024)

        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="tour.mp4", content_type="video/mp4", size=len(video),
        )
        assert plan.modo == "s3"

        # Lo que haría el navegador contra S3.
        s3.objetos[s3.firmas[0]["key"]] = video

        msg = _confirmar(
            db_session, equipo, conversacion.id, plan.referencia,
            filename="tour.mp4", content_type="video/mp4", caption="El tour",
        )

        assert msg.message_type == "video"
        assert msg.status == "sent"
        assert len(enviados) == 1
        assert enviados[0]["media_type"] == "video"
        assert enviados[0]["to"] == NUMERO_DE_PRUEBA
        # Lo guardado es el archivo entero, no un pedazo.
        guardado = [k for k in s3.objetos if k.startswith("adjuntos/")]
        assert len(guardado) == 1
        assert len(s3.objetos[guardado[0]]) == len(video)

    def test_a_los_12_mb_todavia_pasa(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        video = _mp4(12 * 1024 * 1024)
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="tour.mp4", content_type="video/mp4", size=len(video),
        )
        s3.objetos[s3.firmas[0]["key"]] = video
        msg = _confirmar(
            db_session, equipo, conversacion.id, plan.referencia,
            filename="tour.mp4", content_type="video/mp4",
        )
        assert msg.status == "sent"

    def test_pasados_los_12_mb_se_rechaza_antes_de_subir(
        self, db_session, equipo, conversacion, s3
    ):
        """Rebotar acá le ahorra al asesor la barra de progreso completa."""
        with pytest.raises(HTTPException) as exc:
            _preparar(
                db_session, equipo, conversacion.id,
                filename="tour.mp4", content_type="video/mp4",
                size=13 * 1024 * 1024,
            )
        assert exc.value.status_code == 400
        assert "12 MB" in exc.value.detail
        # Y no se firmó nada: no hay a dónde subir.
        assert s3.firmas == []


# ---------------------------------------------------------------------------
# La credencial que emitimos
# ---------------------------------------------------------------------------

class TestLoQueSeFirma:
    def test_la_key_la_elige_el_servidor_dentro_de_la_zona_de_transito(
        self, db_session, equipo, conversacion, s3
    ):
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        key = s3.firmas[0]["key"]
        assert key == f"adjuntos-tmp/{equipo.team_id}/{plan.referencia}"
        # Nada de lo que el cliente mandó (el nombre) llegó a la key.
        assert "foto" not in key

    def test_el_tamano_va_firmado_para_que_lo_haga_cumplir_s3(
        self, db_session, equipo, conversacion, s3
    ):
        """Sin esta condición, un cliente que ignore nuestro límite nos llena el
        bucket: el 400 del backend llega cuando el archivo ya está arriba."""
        _preparar(
            db_session, equipo, conversacion.id,
            filename="tour.mp4", content_type="video/mp4", size=1000,
        )
        assert ["content-length-range", 1, 12 * 1024 * 1024] in s3.firmas[0]["condiciones"]

    def test_no_se_firma_ningun_campo_libre(
        self, db_session, equipo, conversacion, s3
    ):
        assert _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        assert s3.firmas[0]["campos"] == {}

    def test_la_firma_expira(self, db_session, equipo, conversacion, s3):
        _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        assert 0 < s3.firmas[0]["expira"] <= 900

    def test_cada_subida_estrena_referencia(
        self, db_session, equipo, conversacion, s3
    ):
        uno = _preparar(
            db_session, equipo, conversacion.id,
            filename="a.jpg", content_type="image/jpeg", size=1000,
        )
        otro = _preparar(
            db_session, equipo, conversacion.id,
            filename="a.jpg", content_type="image/jpeg", size=1000,
        )
        assert uno.referencia != otro.referencia

    def test_un_tipo_que_no_aceptamos_no_se_firma(
        self, db_session, equipo, conversacion, s3
    ):
        with pytest.raises(HTTPException) as exc:
            _preparar(
                db_session, equipo, conversacion.id,
                filename="virus.exe", content_type="application/x-msdownload",
                size=1000,
            )
        assert exc.value.status_code == 400
        assert s3.firmas == []

    def test_sin_bucket_se_manda_al_camino_de_un_solo_paso(
        self, db_session, equipo, conversacion, monkeypatch
    ):
        """En local no hay a dónde prefirmar — y tampoco hay saltos en medio."""
        monkeypatch.setenv("ADJUNTOS_BUCKET", "")
        monkeypatch.setenv("MASCOTAS_BUCKET", "")
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        assert plan.modo == "directo"
        assert plan.url is None and plan.referencia is None


# ---------------------------------------------------------------------------
# La validación no se saltea
# ---------------------------------------------------------------------------

class TestLaPuertaDeAtras:
    def test_un_ejecutable_en_la_zona_de_transito_no_sale(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        """El escenario completo: alguien firma una subida diciendo que es un
        JPEG y sube otra cosa. Los bytes son los que mandan, siempre."""
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        s3.objetos[s3.firmas[0]["key"]] = b"MZ\x90\x00" + b"\x00" * 1000

        with pytest.raises(HTTPException) as exc:
            _confirmar(
                db_session, equipo, conversacion.id, plan.referencia,
                filename="foto.jpg", content_type="image/jpeg",
            )
        assert exc.value.status_code == 400
        assert enviados == []

    def test_mentir_en_el_tipo_declarado_no_ayuda(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        """Firmarse el tope de audio (16 MB) para colar un video de 13 no sirve:
        `preparar` mira los bytes, ve un video y le aplica el tope del video."""
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="nota.mp3", content_type="audio/mpeg", size=13 * 1024 * 1024,
        )
        s3.objetos[s3.firmas[0]["key"]] = _mp4(13 * 1024 * 1024)

        with pytest.raises(HTTPException) as exc:
            _confirmar(
                db_session, equipo, conversacion.id, plan.referencia,
                filename="tour.mp4", content_type="video/mp4",
            )
        assert exc.value.status_code == 400
        assert "12 MB" in exc.value.detail
        assert enviados == []

    def test_confirmar_sin_haber_subido_nada_no_revienta(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        with pytest.raises(HTTPException) as exc:
            _confirmar(db_session, equipo, conversacion.id, plan.referencia)
        assert exc.value.status_code == 409
        assert enviados == []

    @pytest.mark.parametrize("referencia", [
        "../../mascotas/foto",
        "adjuntos/5/otra",
        "",
        "NO-ES-HEX",
        "a" * 31,
        "a" * 33,
    ])
    def test_una_referencia_que_no_emitimos_no_lee_nada(
        self, db_session, equipo, conversacion, s3, referencia
    ):
        """La referencia entra en una key de S3: sin el regex, un `../` saldría
        del prefijo de tránsito y leería objetos de otro lado del bucket."""
        with pytest.raises(HTTPException) as exc:
            _confirmar(db_session, equipo, conversacion.id, referencia)
        assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# Aislamiento entre tenants
# ---------------------------------------------------------------------------

class TestAislamiento:
    def test_no_se_puede_confirmar_la_subida_de_otro_team(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        """El `team_id` de la key sale de la membresía, nunca del request: la
        referencia de otro equipo apunta a una key que para mí no existe."""
        otro = _equipo(db_session, "otra@directa.com", "DIR-0002", "Otra Agencia")
        conv_otro = models.Conversation(
            team_id=otro.team_id, contact_wa_id="573000000003",
            status="open", last_message_at=datetime(2026, 8, 27, 9, 0, 0),
        )
        db_session.add(conv_otro)
        db_session.commit()

        # La otra agencia firma y sube su archivo.
        plan_ajeno = _preparar(
            db_session, otro, conv_otro.id,
            filename="privado.jpg", content_type="image/jpeg", size=1000,
        )
        s3.objetos[s3.firmas[-1]["key"]] = _jpeg()

        # Yo intento confirmarlo con su referencia, en MI conversación.
        with pytest.raises(HTTPException) as exc:
            _confirmar(
                db_session, equipo, conversacion.id, plan_ajeno.referencia,
                filename="privado.jpg", content_type="image/jpeg",
            )
        assert exc.value.status_code == 409
        assert enviados == []
        # Y el archivo ajeno sigue intacto donde estaba.
        assert s3.firmas[-1]["key"] in s3.objetos

    def test_no_se_firma_una_subida_para_una_conversacion_ajena(
        self, db_session, equipo, conversacion, s3
    ):
        otro = _equipo(db_session, "tercera@directa.com", "DIR-0003", "Tercera")
        conv_otro = models.Conversation(
            team_id=otro.team_id, contact_wa_id="573000000004",
            status="open", last_message_at=datetime(2026, 8, 27, 9, 0, 0),
        )
        db_session.add(conv_otro)
        db_session.commit()

        with pytest.raises(HTTPException) as exc:
            _preparar(
                db_session, equipo, conv_otro.id,
                filename="foto.jpg", content_type="image/jpeg", size=1000,
            )
        assert exc.value.status_code == 404
        assert s3.firmas == []


# ---------------------------------------------------------------------------
# La zona de tránsito no se sirve, y no queda basura
# ---------------------------------------------------------------------------

class TestZonaDeTransito:
    def test_el_endpoint_publico_no_alcanza_la_zona_de_transito(
        self, db_session, equipo, conversacion, s3
    ):
        """Aunque se conozca la referencia: `adjuntos-tmp/` está fuera de la
        forma de ruta que sirve `ver_adjunto`, no es cuestión de adivinar."""
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        s3.objetos[s3.firmas[0]["key"]] = _jpeg()

        with pytest.raises(HTTPException) as exc:
            mensajes.ver_adjunto(
                team_id=equipo.team_id, carpeta=plan.referencia, nombre="foto.jpg"
            )
        assert exc.value.status_code == 404

    def test_el_temporal_se_borra_despues_de_enviar(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        key_tmp = s3.firmas[0]["key"]
        s3.objetos[key_tmp] = _jpeg()

        _confirmar(
            db_session, equipo, conversacion.id, plan.referencia,
            filename="foto.jpg", content_type="image/jpeg",
        )
        assert key_tmp in s3.borrados
        assert key_tmp not in s3.objetos

    def test_el_temporal_se_borra_tambien_cuando_el_archivo_se_rechaza(
        self, db_session, equipo, conversacion, s3
    ):
        """Si no pasó la validación, con más razón: son bytes que no queremos."""
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        key_tmp = s3.firmas[0]["key"]
        s3.objetos[key_tmp] = b"MZ\x90\x00" + b"\x00" * 1000

        with pytest.raises(HTTPException):
            _confirmar(
                db_session, equipo, conversacion.id, plan.referencia,
                filename="foto.jpg", content_type="image/jpeg",
            )
        assert key_tmp in s3.borrados

    def test_una_referencia_no_se_puede_usar_dos_veces(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="foto.jpg", content_type="image/jpeg", size=1000,
        )
        s3.objetos[s3.firmas[0]["key"]] = _jpeg()
        _confirmar(
            db_session, equipo, conversacion.id, plan.referencia,
            filename="foto.jpg", content_type="image/jpeg",
        )
        with pytest.raises(HTTPException) as exc:
            _confirmar(
                db_session, equipo, conversacion.id, plan.referencia,
                filename="foto.jpg", content_type="image/jpeg",
            )
        assert exc.value.status_code == 409
        assert len(enviados) == 1


# ---------------------------------------------------------------------------
# Lo que ve el asesor es lo mismo por los dos caminos
# ---------------------------------------------------------------------------

class TestParidadConElCaminoViejo:
    def test_el_mensaje_queda_igual_que_subiendo_por_la_api(
        self, db_session, equipo, conversacion, s3, enviados
    ):
        """Mismo formato `pie\\nURL` y mismo `message_type`: la burbuja del
        frontend no distingue por dónde subió el archivo."""
        plan = _preparar(
            db_session, equipo, conversacion.id,
            filename="hotel.jpg", content_type="image/jpeg", size=1000,
        )
        s3.objetos[s3.firmas[0]["key"]] = _jpeg()

        msg = _confirmar(
            db_session, equipo, conversacion.id, plan.referencia,
            filename="hotel.jpg", content_type="image/jpeg",
            caption="Así es la habitación",
        )

        pie, url = msg.content.split("\n")
        assert pie == "Así es la habitación"
        assert url.startswith("https://api.ejemplo.test/mensajes/adjunto/")
        assert f"/{equipo.team_id}/" in url
        assert url.endswith("hotel.jpg")
        assert msg.sent_by_user_id == equipo.user_id
        assert enviados[0]["caption"] == "Así es la habitación"

    def test_el_texto_del_tope_es_el_mismo_por_los_dos_lados(self):
        """El número sale de `LIMITES` en los dos casos: si alguien sube el
        tope y solo toca un texto, esto lo caza."""
        previo, problema = adjuntos.preparar(
            _mp4(13 * 1024 * 1024), "video/mp4", "tour.mp4"
        )
        assert previo is None
        assert problema == adjuntos.texto_excede(adjuntos.VIDEO)
        assert "12 MB" in problema
