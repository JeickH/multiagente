"""Compresión de fotos: el archivo más liviano que todavía se ve igual.

Lo mismo que hace TinyPNG o Squoosh, pero acá adentro: son fotos de mascotas de
familias reales y no tienen por qué pasar por un tercero.

Dos caminos, según quién llame:

- `comprimir()` — camino rápido, el de la subida. Una sola pasada a calidad
  fija: lo atiende un request HTTP de alguien que está esperando, así que no
  puede darse el lujo de probar seis calidades. Usa el modo `draft` de Pillow,
  que aprovecha el DCT del JPEG para decodificar ya reducido en vez de armar la
  imagen completa para después achicarla.
- `comprimir_buscando()` — camino lento, el del script que barre el bucket
  (`scripts/optimizar_fotos_mascotas.py`). Prueba calidades de menor a mayor y
  se queda con la primera que pasa un umbral de SSIM.

El módulo no importa nada de la app a propósito: el script lo usa desde fuera
del contenedor. `numpy` sólo hace falta para el SSIM y se importa adentro de la
función, para que la imagen del backend no tenga que cargarlo.
"""

from __future__ import annotations

import io
import logging
from typing import Dict, Optional, Sequence, Tuple

from PIL import Image, ImageFile, ImageOps

logger = logging.getLogger(__name__)

MAX_LADO = 2000       # px del lado largo; nadie ve una foto de mascota a 4000px
CALIDAD_SUBIDA = 85   # calidad fija del camino rápido
# Escalera del camino lento, de menor a mayor: gana la primera que pasa el SSIM.
CALIDADES = (78, 82, 85, 88, 92, 95)
# Umbral calibrado sobre las fotos reales del bucket (BITACORA #359). El SSIM se
# mide contra el original ya redimensionado, y el ruido de sensor de un celular
# no lo conserva ninguna recompresión: en las fotos más pesadas ni calidad 95
# pasa de 0.983. 0.96 es donde la diferencia deja de verse.
SSIM_MIN = 0.96


# ---------------------------------------------------------------------------
# Apertura
# ---------------------------------------------------------------------------

def _cola_en_blanco(img: Image.Image) -> bool:
    """¿Las últimas filas quedaron en gris plano? Es como Pillow rellena lo que
    no alcanzó a decodificar: si pasa, la imagen está de verdad mutilada y no se
    puede recomprimir sin dejarla así para siempre."""
    import numpy as np

    alto = max(1, round(img.height * 0.03))
    cola = np.asarray(img.convert("L"), dtype=np.float64)[-alto:, :]
    return float(cola.std()) < 1.0


def abrir(data: bytes, lado_objetivo: Optional[int] = None) -> Image.Image:
    """Decodifica a RGB, con la orientación del EXIF ya aplicada.

    `lado_objetivo` activa el modo `draft`: en un JPEG, Pillow decodifica
    directamente a 1/2, 1/4 u 1/8 del tamaño. Es varias veces más rápido que
    decodificar completo y achicar después, que es lo que importa cuando esto
    corre dentro de un request.
    """
    img = Image.open(io.BytesIO(data))
    if lado_objetivo:
        img.draft("RGB", (lado_objetivo, lado_objetivo))
    try:
        img.load()
    except OSError as exc:
        # Varias fotos del bucket llegaron sin el marcador de fin (les faltan
        # 1-3 bytes). El navegador las pinta igual; Pillow es más estricto.
        if "truncated" not in str(exc):
            raise
        ImageFile.LOAD_TRUNCATED_IMAGES = True
        try:
            img = Image.open(io.BytesIO(data))
            if lado_objetivo:
                img.draft("RGB", (lado_objetivo, lado_objetivo))
            img.load()
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = False
        if _cola_en_blanco(img):
            raise OSError("truncada de verdad: la parte final se perdió") from exc

    # La orientación viaja en el EXIF y el EXIF se descarta al recomprimir: hay
    # que aplicarla ANTES, o las fotos verticales salen acostadas.
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        # JPEG no tiene transparencia: lo que era transparente va sobre blanco.
        fondo = Image.new("RGB", img.size, (255, 255, 255))
        conv = img.convert("RGBA")
        fondo.paste(conv, mask=conv.split()[-1])
        img = fondo
    elif img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _encoger(img: Image.Image, max_lado: int) -> Image.Image:
    if max(img.size) <= max_lado:
        return img
    escala = max_lado / max(img.size)
    return img.resize(
        (round(img.width * escala), round(img.height * escala)), Image.LANCZOS
    )


def _a_jpeg(img: Image.Image, calidad: int) -> bytes:
    buf = io.BytesIO()
    # `optimize` recalcula las tablas Huffman y `progressive` hace que la foto
    # se vea de una vez en el celular aunque la conexión sea mala. Los dos
    # ahorran bytes sin tocar un solo píxel. El EXIF no se copia: de paso se va
    # la geolocalización que traen las fotos de celular.
    img.save(buf, format="JPEG", quality=calidad, optimize=True, progressive=True)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# SSIM (implementación estándar: ventana gaussiana 11x11, sigma 1.5)
# ---------------------------------------------------------------------------

def ssim(a: Image.Image, b: Image.Image) -> float:
    """Similitud estructural entre dos imágenes del mismo tamaño (0..1).

    1.0 = idénticas píxel a píxel. En la literatura, >0.98 se considera
    indistinguible a simple vista.
    """
    import numpy as np

    def gauss(n: int = 11, sigma: float = 1.5):
        ejes = np.arange(n) - (n - 1) / 2
        k = np.exp(-(ejes ** 2) / (2 * sigma ** 2))
        return k / k.sum()

    def conv(x, k, eje):
        """Convolución 1-D 'valid' como suma de desplazamientos: sin scipy y sin
        reventar la memoria con ventanas deslizantes."""
        r = len(k) - 1
        alto = x.shape[0] - (r if eje == 0 else 0)
        ancho = x.shape[1] - (r if eje == 1 else 0)
        out = np.zeros((alto, ancho))
        for i, ki in enumerate(k):
            out += ki * (x[i:i + alto, :] if eje == 0 else x[:, i:i + ancho])
        return out

    def filtrar(x, k):
        return conv(conv(x, k, 0), k, 1)

    x = np.asarray(a.convert("L"), dtype=np.float64)
    y = np.asarray(b.convert("L"), dtype=np.float64)
    if x.shape != y.shape:
        raise ValueError("SSIM: las imágenes deben tener el mismo tamaño")
    k = gauss()
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2

    mx, my = filtrar(x, k), filtrar(y, k)
    vx = filtrar(x * x, k) - mx * mx
    vy = filtrar(y * y, k) - my * my
    vxy = filtrar(x * y, k) - mx * my

    mapa = ((2 * mx * my + c1) * (2 * vxy + c2)) / (
        (mx * mx + my * my + c1) * (vx + vy + c2)
    )
    return float(mapa.mean())


# ---------------------------------------------------------------------------
# Los dos caminos
# ---------------------------------------------------------------------------

def comprimir(
    data: bytes, max_lado: int = MAX_LADO, calidad: int = CALIDAD_SUBIDA
) -> Optional[bytes]:
    """Camino rápido (subida): JPEG a calidad fija, en una sola pasada.

    Devuelve `None` si no hay nada que ganar o si la imagen no se puede
    procesar — quien llama se queda con el original. Nunca levanta excepción:
    perder la foto de alguien por un error de compresión sería mucho peor que
    guardarla pesada.
    """
    try:
        img = _encoger(abrir(data, lado_objetivo=max_lado), max_lado)
        salida = _a_jpeg(img, calidad)
    except Exception:
        logger.exception("imagenes: no se pudo comprimir (%d bytes)", len(data))
        return None
    return salida if len(salida) < len(data) else None


def comprimir_buscando(
    data: bytes,
    max_lado: int = MAX_LADO,
    ssim_min: float = SSIM_MIN,
    calidades: Sequence[int] = CALIDADES,
) -> Tuple[bytes, Dict[str, object]]:
    """Camino lento (barrido del bucket): la calidad más baja que aún se ve igual.

    El SSIM se mide contra el original ya redimensionado, así que el número
    refleja lo que pierde la COMPRESIÓN, no el redimensionado. Levanta excepción
    si la imagen no se puede abrir: ahí sí conviene enterarse.
    """
    original = abrir(data)
    dim_antes = original.size
    referencia = _encoger(original, max_lado)

    mejor: Optional[Tuple[bytes, int, float]] = None
    for q in calidades:
        salida = _a_jpeg(referencia, q)
        puntaje = ssim(referencia, abrir(salida))
        if mejor is None or puntaje > mejor[2]:
            mejor = (salida, q, puntaje)
        if puntaje >= ssim_min:
            mejor = (salida, q, puntaje)
            break

    salida, q, puntaje = mejor  # type: ignore[misc]
    return salida, {
        "dim_antes": f"{dim_antes[0]}x{dim_antes[1]}",
        "dim_despues": f"{referencia.width}x{referencia.height}",
        "calidad_jpeg": q,
        "ssim": round(puntaje, 5),
    }
