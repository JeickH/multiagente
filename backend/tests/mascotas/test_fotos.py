"""Fotos: compresión, privacidad del EXIF y storage.

Las fotos son lo único irrecuperable de este módulo — el bucket **no tiene
versionado** (manual §3). Dos cosas se prueban con especial cuidado:

1. **El EXIF se descarta**, y con él la geolocalización que traen las fotos de
   celular. Una foto de una mascota perdida publicada con las coordenadas de la
   casa de quien la reportó es una fuga de datos personales.
2. **Nunca se pierde una foto por un error de compresión.** Si algo falla,
   `comprimir()` devuelve `None` y se guarda el original.
"""
from __future__ import annotations

import io

import pytest

from app.services import imagenes, mascotas as svc

PIL = pytest.importorskip("PIL", reason="Pillow es dependencia del backend")


def foto_jpeg(ancho=3000, alto=2000, color=(120, 60, 30), exif=None) -> bytes:
    """Una foto sintética con textura, del tamaño que manda un celular.

    Con un color plano el JPEG comprime tanto que no se puede medir nada, así
    que se le mete ruido determinista.
    """
    from PIL import Image

    img = Image.new("RGB", (ancho, alto), color)
    pixeles = img.load()
    for y in range(0, alto, 7):
        for x in range(0, ancho, 7):
            pixeles[x, y] = ((x * 7) % 256, (y * 13) % 256, (x + y) % 256)
    buf = io.BytesIO()
    if exif is not None:
        img.save(buf, format="JPEG", quality=95, exif=exif)
    else:
        img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


class TestComprimir:
    def test_una_foto_de_celular_pesa_menos(self):
        original = foto_jpeg()
        comprimida = imagenes.comprimir(original)
        assert comprimida is not None
        assert len(comprimida) < len(original)

    def test_baja_el_lado_largo_al_maximo(self):
        from PIL import Image

        comprimida = imagenes.comprimir(foto_jpeg(4000, 3000))
        img = Image.open(io.BytesIO(comprimida))
        assert max(img.size) == imagenes.MAX_LADO
        # Y conserva la proporción: 4:3 sigue siendo 4:3.
        assert round(img.width / img.height, 2) == round(4000 / 3000, 2)

    def test_una_foto_pequeña_no_se_agranda(self):
        from PIL import Image

        comprimida = imagenes.comprimir(foto_jpeg(400, 300))
        if comprimida is not None:
            assert max(Image.open(io.BytesIO(comprimida)).size) <= 400

    def test_el_resultado_es_jpeg_progresivo(self):
        from PIL import Image

        img = Image.open(io.BytesIO(imagenes.comprimir(foto_jpeg())))
        assert img.format == "JPEG"
        assert "progression" in img.info or img.info.get("progressive")

    def test_una_imagen_corrupta_no_revienta(self):
        """Se prefiere guardar la foto pesada antes que perderla."""
        assert imagenes.comprimir(b"esto no es una imagen") is None
        assert imagenes.comprimir(b"") is None

    def test_si_no_hay_nada_que_ganar_devuelve_none(self):
        ya_chica = imagenes.comprimir(foto_jpeg(200, 150))
        segunda = imagenes.comprimir(ya_chica or foto_jpeg(200, 150))
        assert segunda is None or len(segunda) < len(ya_chica or b"")

    def test_un_png_con_transparencia_sale_sobre_blanco(self):
        """JPEG no tiene canal alfa: lo transparente va sobre blanco, no sobre
        negro (que es lo que sale si uno convierte a RGB sin más)."""
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGBA", (400, 300), (255, 0, 0, 0)).save(buf, format="PNG")

        img = imagenes.abrir(buf.getvalue())

        assert img.mode == "RGB"
        assert img.getpixel((10, 10)) == (255, 255, 255)


class TestPrivacidadDelExif:
    def test_la_geolocalizacion_no_sobrevive(self):
        """Lo que más importa de todo el archivo: la foto que sube alguien
        desde su casa no puede salir publicada con sus coordenadas."""
        from PIL import Image

        exif = Image.Exif()
        exif[0x8825] = {1: "N", 2: (3.0, 26.0, 0.0), 3: "W", 4: (76.0, 32.0, 0.0)}
        con_gps = foto_jpeg(1200, 900, exif=exif.tobytes())

        comprimida = imagenes.comprimir(con_gps)

        assert comprimida is not None
        salida = Image.open(io.BytesIO(comprimida))
        assert not salida.getexif().get_ifd(0x8825), "la geolocalización sobrevivió"

    def test_la_orientacion_se_aplica_antes_de_descartar_el_exif(self):
        """El EXIF se tira, así que la rotación hay que aplicarla antes o las
        fotos verticales salen acostadas."""
        from PIL import Image

        exif = Image.Exif()
        exif[0x0112] = 6           # "rotar 90°"
        vertical = foto_jpeg(900, 1200, exif=exif.tobytes())

        comprimida = imagenes.comprimir(vertical)

        img = Image.open(io.BytesIO(comprimida))
        assert img.width > img.height, "no se aplicó la rotación del EXIF"


class TestBusquedaDeCalidad:
    """El camino lento, el del barrido del bucket."""

    def test_se_queda_con_algo_que_todavia_se_ve_igual(self):
        salida, info = imagenes.comprimir_buscando(foto_jpeg(1200, 900))
        assert info["ssim"] >= imagenes.SSIM_MIN
        assert info["calidad_jpeg"] in imagenes.CALIDADES
        assert len(salida) > 0

    def test_informa_las_dimensiones_de_antes_y_despues(self):
        _, info = imagenes.comprimir_buscando(foto_jpeg(4000, 3000))
        assert info["dim_antes"] == "4000x3000"
        assert info["dim_despues"] == "2000x1500"

    def test_el_ssim_de_una_imagen_consigo_misma_es_uno(self):
        from PIL import Image

        img = Image.open(io.BytesIO(foto_jpeg(300, 200)))
        assert imagenes.ssim(img, img) == pytest.approx(1.0, abs=1e-6)

    def test_el_ssim_baja_con_una_imagen_distinta(self):
        from PIL import Image

        una = Image.open(io.BytesIO(foto_jpeg(300, 200, color=(10, 10, 10))))
        otra = Image.open(io.BytesIO(foto_jpeg(300, 200, color=(240, 240, 240))))
        assert imagenes.ssim(una, otra) < 0.99

    def test_dos_imagenes_de_distinto_tamaño_no_se_comparan(self):
        from PIL import Image

        with pytest.raises(ValueError):
            imagenes.ssim(
                Image.open(io.BytesIO(foto_jpeg(300, 200))),
                Image.open(io.BytesIO(foto_jpeg(200, 300))),
            )


class TestGuardarEnElStorage:
    def test_la_foto_nace_comprimida_y_marcada(self, db, crear):
        mascota = crear(tipo_registro="encontrada", especie="perro")
        original = foto_jpeg()

        foto = svc.guardar_foto(db, original, "image/jpeg", mascota=mascota)

        assert foto.optimizada is True
        assert foto.bytes_original == len(original)
        assert foto.bytes_size < foto.bytes_original
        assert foto.optimizada_at is not None

    def test_lo_que_no_se_pudo_comprimir_queda_sin_marcar(self, db, crear):
        """Así el barrido del bucket la toma después: nunca se pierde una foto
        por un error de compresión."""
        mascota = crear(tipo_registro="encontrada", especie="perro")
        foto = svc.guardar_foto(db, b"\xff\xd8no-es-jpeg", "image/jpeg", mascota=mascota)
        assert foto.optimizada is False

    def test_se_guarda_bajo_la_carpeta_del_reporte(self, db, crear, medios):
        mascota = crear(tipo_registro="encontrada", especie="perro")
        foto = svc.guardar_foto(db, foto_jpeg(600, 400), "image/jpeg", mascota=mascota)

        assert foto.storage_key.startswith(f"mascotas/{mascota.codigo}/")
        assert (medios / foto.storage_key).exists()

    def test_sin_reporte_queda_en_el_limbo(self, db, medios):
        foto = svc.guardar_foto(
            db, foto_jpeg(600, 400), "image/jpeg", upload_session="abc"
        )
        assert foto.storage_key.startswith("pendientes/abc/")
        assert foto.mascota_id is None

    def test_leer_valida_que_la_foto_sea_del_reporte(self, db, crear):
        mia = crear(tipo_registro="encontrada", especie="perro")
        ajena = crear(tipo_registro="encontrada", especie="gato")
        foto = svc.guardar_foto(db, foto_jpeg(400, 300), "image/jpeg", mascota=ajena)

        assert svc.leer_foto(db, mia.codigo, foto.id) is None
        assert svc.leer_foto(db, ajena.codigo, foto.id) is not None

    def test_sin_bucket_la_ruta_es_local(self, medios):
        assert svc.storage_uri("mascotas/MC-1/x.jpg").startswith("file://")

    def test_con_bucket_la_ruta_es_s3(self, monkeypatch):
        monkeypatch.setenv("MASCOTAS_BUCKET", "gloma-mascotas-747456040509")
        assert svc.storage_uri("mascotas/MC-1/x.jpg") == (
            "s3://gloma-mascotas-747456040509/mascotas/MC-1/x.jpg"
        )
