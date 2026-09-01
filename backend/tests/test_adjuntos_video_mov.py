"""Videos .mov: el formato que la asesora tiene a mano y WhatsApp no acepta.

El .mov es lo que graba un iPhone y lo que exporta un Mac, así que es el video
que una asesora va a intentar mandar. WhatsApp sólo recibe MP4 y 3GP, de modo
que el archivo entra a la lista blanca **para poder convertirlo**, no para
mandarlo tal cual.

Lo que se protege acá:

1. **Un .mov se reconoce como .mov.** Antes la firma no miraba la marca del
   contenedor: devolvía "es un ftyp cualquiera" y `_tipo_real` caía en su
   respaldo ("un ftyp raro debe ser un mp4"). Resultado: el archivo se guardaba
   con extensión `.mp4` y etiquetado `video/mp4` teniendo bytes de QuickTime
   adentro. No fallaba nada de este lado — lo rechazaba WhatsApp después.

2. **Nunca sale un .mov hacia WhatsApp.** Lo que se guarda y se envía siempre
   termina siendo `video/mp4`.

3. **Si la conversión no se puede, se rechaza con un texto que dice qué hacer.**
   Un HEVC de tres minutos no cabe en el presupuesto de CPU de la task (0,25
   vCPU detrás de un API Gateway con 30 s de timeout), y en ese caso es mejor
   decirlo que devolver un 504 del gateway.

4. **Los mp4 de siempre no cambian de camino.** El video que hoy funciona no
   puede empezar a pasar por ffmpeg por culpa de este sprint.

Nada de esto ejecuta ffmpeg: el binario no está en la máquina de desarrollo, y
lo que interesa probar es la decisión, no la conversión.
"""
from __future__ import annotations

import subprocess

import pytest

from app.services import adjuntos


# ---------------------------------------------------------------------------
# Contenedores de mentira, con la sola cabecera que mira la firma
# ---------------------------------------------------------------------------

def _ftyp(marca: bytes, tamano: int = 4096) -> bytes:
    """Un ISO-BMFF con la `major_brand` pedida: tamaño, `ftyp` y la marca."""
    cabecera = b"\x00\x00\x00\x18ftyp" + marca + b"\x00" * 8
    return cabecera + b"\x00" * max(0, tamano - len(cabecera))


def _mov(tamano: int = 4096) -> bytes:
    return _ftyp(b"qt  ", tamano)


def _mp4(tamano: int = 4096) -> bytes:
    return _ftyp(b"mp42", tamano)


# ---------------------------------------------------------------------------
# 1. La firma reconoce la marca del contenedor
# ---------------------------------------------------------------------------

class TestLaFirmaDistingueElContenedor:
    def test_un_mov_se_reconoce_como_quicktime(self):
        assert adjuntos._firma(_mov()) == "video/quicktime"

    def test_un_mp4_sigue_siendo_ambiguo_a_proposito(self):
        """`mp42`/`isom` las comparten un mp4 de video y un m4a de sólo audio.
        Ahí sigue decidiendo el `Content-Type`, como siempre."""
        assert adjuntos._firma(_mp4()) == adjuntos._FTYP

    def test_un_m4a_se_reconoce_como_audio(self):
        assert adjuntos._firma(_ftyp(b"M4A ")) == "audio/mp4"

    def test_el_mov_ya_no_se_confunde_con_un_mp4(self):
        """El bug de fondo: sin la marca, un .mov entraba etiquetado video/mp4."""
        mime, firma = adjuntos._tipo_real(_mov(), "video/quicktime", "clip.mov")
        assert mime == "video/quicktime"
        assert firma == "video/quicktime"

    def test_un_mov_sin_content_type_ni_nombre_tambien(self):
        """Es el caso del webhook: `guardar_entrante` no recibe filename."""
        mime, _ = adjuntos._tipo_real(_mov(), "", None)
        assert mime == "video/quicktime"


# ---------------------------------------------------------------------------
# 2. Lo que sale hacia WhatsApp siempre es MP4
# ---------------------------------------------------------------------------

class TestElMovSaleConvertido:
    def test_un_mov_valido_queda_como_mp4(self, monkeypatch):
        monkeypatch.setattr(
            adjuntos, "transcodificar_a_mp4", lambda data: _mp4(1024)
        )

        preparado, problema = adjuntos.preparar(
            _mov(), "video/quicktime", "clip.mov"
        )

        assert problema == ""
        assert preparado.content_type == "video/mp4"
        assert preparado.extension == ".mp4"
        assert preparado.categoria == adjuntos.VIDEO

    def test_el_nombre_visible_pierde_la_extension_vieja(self, monkeypatch):
        """Quien recibe ve el último tramo de la URL: no puede decir `.mov` si
        lo que va adentro ya es un MP4."""
        monkeypatch.setattr(
            adjuntos, "transcodificar_a_mp4", lambda data: _mp4(1024)
        )
        preparado, _ = adjuntos.preparar(_mov(), "video/quicktime", "Playa.mov")

        assert adjuntos.nombre_visible(
            "Playa.mov", preparado.categoria, preparado.extension
        ) == "Playa.mp4"

    def test_si_no_se_puede_convertir_se_rechaza_con_instrucciones(self, monkeypatch):
        monkeypatch.setattr(adjuntos, "transcodificar_a_mp4", lambda data: None)

        preparado, problema = adjuntos.preparar(
            _mov(), "video/quicktime", "clip.mov"
        )

        assert preparado is None
        assert "MP4" in problema, problema

    def test_si_al_convertir_se_pasa_del_tope_se_avisa(self, monkeypatch):
        """Copiar las pistas a otro contenedor no achica el archivo: un .mov al
        filo del límite puede pasarse por poco una vez convertido."""
        gordo = _mp4(adjuntos.LIMITES[adjuntos.VIDEO] + 1024)
        monkeypatch.setattr(adjuntos, "transcodificar_a_mp4", lambda data: gordo)

        preparado, problema = adjuntos.preparar(
            _mov(), "video/quicktime", "clip.mov"
        )

        assert preparado is None
        assert "pesa demasiado" in problema

    def test_un_mov_gigante_se_rechaza_antes_de_llamar_a_ffmpeg(self, monkeypatch):
        """El tope se mira sobre los bytes que llegaron. Convertir primero
        sería gastar CPU en algo que ya se sabe que no se puede mandar."""
        llamadas = []
        monkeypatch.setattr(
            adjuntos, "transcodificar_a_mp4",
            lambda data: llamadas.append(1) or _mp4(1024),
        )

        preparado, problema = adjuntos.preparar(
            _mov(adjuntos.LIMITES[adjuntos.VIDEO] + 1024), "video/quicktime", "x.mov"
        )

        assert preparado is None
        assert "pesa demasiado" in problema
        assert llamadas == [], "no se debería haber llamado a ffmpeg"


class TestElVideoEntranteNoPasaPorFfmpeg:
    """Lo que manda el CLIENTE se guarda tal cual, sin convertir.

    No es una optimización: `guardar_entrante` corre dentro del webhook, y
    Twilio da unos 15 segundos para contestarlo. Recodificar un HEVC puede
    tomar veinte. Convertir ahí cambiaría "el asesor ve un video que su
    navegador quizá no reproduce" por "el webhook se pasa de tiempo y el
    mensaje se pierde".
    """

    def test_un_mov_entrante_se_guarda_sin_convertir(self, monkeypatch):
        def _explotar(data):
            raise AssertionError("el webhook no puede esperar a ffmpeg")

        monkeypatch.setattr(adjuntos, "transcodificar_a_mp4", _explotar)

        preparado, problema = adjuntos.preparar(
            _mov(), "video/quicktime", None, convertir_video=False
        )

        assert problema == ""
        assert preparado.content_type == "video/quicktime"
        assert preparado.extension == ".mov"

    def test_guardar_entrante_usa_ese_camino(self, monkeypatch, tmp_path):
        def _explotar(data):
            raise AssertionError("el webhook no puede esperar a ffmpeg")

        monkeypatch.setattr(adjuntos, "transcodificar_a_mp4", _explotar)
        monkeypatch.setenv("ADJUNTOS_MEDIA_DIR", str(tmp_path))
        monkeypatch.delenv("ADJUNTOS_BUCKET", raising=False)
        monkeypatch.delenv("MASCOTAS_BUCKET", raising=False)

        guardado = adjuntos.guardar_entrante(7, _mov(), "video/quicktime")

        assert guardado is not None
        assert guardado.nombre.endswith(".mov")
        assert guardado.categoria == adjuntos.VIDEO


# ---------------------------------------------------------------------------
# 3. El camino del MP4 no se toca
# ---------------------------------------------------------------------------

class TestElMp4NoCambiaDeCamino:
    def test_un_mp4_no_pasa_por_ffmpeg(self, monkeypatch):
        def _explotar(data):
            raise AssertionError("un mp4 no tiene nada que convertir")

        monkeypatch.setattr(adjuntos, "transcodificar_a_mp4", _explotar)

        preparado, problema = adjuntos.preparar(_mp4(), "video/mp4", "clip.mp4")

        assert problema == ""
        assert preparado.content_type == "video/mp4"
        assert preparado.extension == ".mp4"

    def test_un_3gp_tampoco(self, monkeypatch):
        def _explotar(data):
            raise AssertionError("el 3gp también lo acepta WhatsApp")

        monkeypatch.setattr(adjuntos, "transcodificar_a_mp4", _explotar)

        preparado, problema = adjuntos.preparar(
            _ftyp(b"3gp4"), "video/3gpp", "clip.3gp"
        )

        assert problema == ""
        assert preparado.categoria == adjuntos.VIDEO


# ---------------------------------------------------------------------------
# 4. La subida directa acepta el .mov con el tope de video
# ---------------------------------------------------------------------------

class TestLaSubidaDirectaLoDejaPasar:
    def test_el_mov_declarado_es_video(self):
        """`preparar` mira bytes, pero para firmar el POST hay que decidir el
        tope antes de tener el archivo."""
        assert adjuntos.categoria_declarada(
            "video/quicktime", "clip.mov"
        ) == adjuntos.VIDEO

    def test_tambien_por_la_extension_cuando_el_navegador_no_lo_dice(self):
        assert adjuntos.categoria_declarada(
            "application/octet-stream", "clip.mov"
        ) == adjuntos.VIDEO


# ---------------------------------------------------------------------------
# 5. La conversión nunca revienta el request
# ---------------------------------------------------------------------------

class TestLaConversionFallaEnSilencio:
    """`transcodificar_a_mp4` corre un binario externo. Si algo sale mal tiene
    que devolver None, nunca levantar: el llamador decide qué contarle a la
    asesora."""

    def test_sin_ffmpeg_instalado_devuelve_none(self, monkeypatch):
        def _no_existe(*a, **k):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(adjuntos.subprocess, "run", _no_existe)
        assert adjuntos.transcodificar_a_mp4(_mov()) is None

    def test_si_se_pasa_del_tiempo_devuelve_none(self, monkeypatch):
        """El caso caro: un HEVC largo en 0,25 vCPU. Mejor un mensaje que un
        504 del API Gateway a los 30 s."""
        def _se_cuelga(*a, **k):
            raise subprocess.TimeoutExpired(cmd="ffmpeg", timeout=20)

        monkeypatch.setattr(adjuntos.subprocess, "run", _se_cuelga)
        assert adjuntos.transcodificar_a_mp4(_mov()) is None

    def test_si_ffmpeg_falla_devuelve_none(self, monkeypatch):
        class _Fallo:
            returncode = 1
            stdout = b""
            stderr = b"nope"

        monkeypatch.setattr(adjuntos.subprocess, "run", lambda *a, **k: _Fallo())
        assert adjuntos.transcodificar_a_mp4(_mov()) is None

    def test_el_timeout_de_recodificar_cabe_en_el_del_gateway(self):
        """El API Gateway corta a los 30 s y no se puede subir sin pedir cuota.
        Si alguien sube este número por encima, el asesor deja de recibir el
        mensaje que le dice qué hacer."""
        assert adjuntos._FFMPEG_RECODIFICAR_TIMEOUT < 30


# ---------------------------------------------------------------------------
# 6. Copiar vs recodificar: la decisión que hace que esto quepa en el request
# ---------------------------------------------------------------------------

class TestCopiarORecodificar:
    def _capturar(self, monkeypatch, codecs):
        """Deja pasar el ffprobe con `codecs` y captura el comando de ffmpeg."""
        comandos = []

        def _run(comando, *a, **k):
            if comando[0] == "ffprobe":
                class _Ok:
                    returncode = 0
                    stdout = codecs
                    stderr = b""
                return _Ok()
            comandos.append(comando)

            class _Fallo:  # no hay ffmpeg de verdad: interesa el comando
                returncode = 1
                stdout = b""
                stderr = b""
            return _Fallo()

        monkeypatch.setattr(adjuntos.subprocess, "run", _run)
        return comandos

    def test_h264_con_aac_se_copia_sin_recodificar(self, monkeypatch):
        """El caso corriente (un .mov de Mac, o de iPhone en «Más compatible»):
        se copian las pistas al contenedor MP4. No se decodifica ni un frame."""
        comandos = self._capturar(
            monkeypatch,
            b'{"streams":[{"codec_type":"video","codec_name":"h264"},'
            b'{"codec_type":"audio","codec_name":"aac"}]}',
        )

        adjuntos.transcodificar_a_mp4(_mov())

        assert comandos, "no se llamó a ffmpeg"
        assert "copy" in comandos[0]
        assert "libx264" not in comandos[0]

    def test_sin_pista_de_audio_tambien_se_copia(self, monkeypatch):
        comandos = self._capturar(
            monkeypatch,
            b'{"streams":[{"codec_type":"video","codec_name":"h264"}]}',
        )

        adjuntos.transcodificar_a_mp4(_mov())

        assert "copy" in comandos[0]

    def test_hevc_obliga_a_recodificar(self, monkeypatch):
        """Un iPhone en «Alta eficiencia» graba HEVC, y WhatsApp pide H.264.
        Reetiquetarlo no sirve: hay que volver a codificar."""
        comandos = self._capturar(
            monkeypatch,
            b'{"streams":[{"codec_type":"video","codec_name":"hevc"},'
            b'{"codec_type":"audio","codec_name":"aac"}]}',
        )

        adjuntos.transcodificar_a_mp4(_mov())

        assert "libx264" in comandos[0]
        assert "copy" not in comandos[0]

    def test_si_ffprobe_no_esta_se_recodifica(self, monkeypatch):
        """Ante la duda, la opción segura: convertir de más cuesta tiempo,
        mandar HEVC cuesta un mensaje no entregado."""
        comandos = []

        def _run(comando, *a, **k):
            if comando[0] == "ffprobe":
                raise FileNotFoundError("ffprobe")
            comandos.append(comando)

            class _Fallo:
                returncode = 1
                stdout = b""
                stderr = b""
            return _Fallo()

        monkeypatch.setattr(adjuntos.subprocess, "run", _run)
        adjuntos.transcodificar_a_mp4(_mov())

        assert "libx264" in comandos[0]

    def test_el_indice_va_al_principio_en_los_dos_caminos(self, monkeypatch):
        """`+faststart`: quien descarga esto es el servidor de Meta o el de
        Twilio, y con el índice al final tiene que bajar el archivo entero
        antes de poder empezar."""
        for codecs in (
            b'{"streams":[{"codec_type":"video","codec_name":"h264"}]}',
            b'{"streams":[{"codec_type":"video","codec_name":"hevc"}]}',
        ):
            comandos = self._capturar(monkeypatch, codecs)
            adjuntos.transcodificar_a_mp4(_mov())
            assert "+faststart" in comandos[0]
