"""Hosting de imágenes para la publicación en Instagram.

Instagram no acepta subida de archivos: descarga la imagen desde una URL pública
HTTPS en el momento de publicar. Por eso subimos cada slide a S3 (bucket privado)
y le pasamos a Meta una **URL prefirmada** de vida corta. Así no hace falta un
bucket público.

Las imágenes se suben en el momento de *programar*, no de publicar, para que el
runner que dispara la publicación no dependa de que los archivos locales del Mac
estén disponibles.
"""
from __future__ import annotations

import hashlib
import io
import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from PIL import Image

from .config import AWS_REGION, MEDIA_BUCKET

logger = logging.getLogger(__name__)

# Requisitos de Instagram para imágenes de feed publicadas por API.
MAX_WIDTH = 1440           # Meta reescala por encima de esto; lo hacemos nosotros
MIN_RATIO = 4 / 5          # 0.80 — vertical máximo permitido
MAX_RATIO = 1.91           # horizontal máximo permitido
MAX_BYTES = 8 * 1024 * 1024
PRESIGN_TTL = 3600         # 1 h: suficiente, el contenedor se crea de inmediato


class MediaError(RuntimeError):
    """La imagen no cumple los requisitos de Instagram o falló el hosting."""


def _s3():
    return boto3.client("s3", region_name=AWS_REGION)


def ensure_bucket() -> str:
    """Crea el bucket privado si no existe. Idempotente."""
    s3 = _s3()
    try:
        s3.head_bucket(Bucket=MEDIA_BUCKET)
        return MEDIA_BUCKET
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
            raise

    s3.create_bucket(
        Bucket=MEDIA_BUCKET,
        CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
    )
    # Privado por defecto y cifrado en reposo.
    s3.put_public_access_block(
        Bucket=MEDIA_BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_encryption(
        Bucket=MEDIA_BUCKET,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
        },
    )
    # Las imágenes solo hacen falta hasta que Meta las descarga; 30 días es de
    # sobra y evita que el bucket crezca sin control.
    s3.put_bucket_lifecycle_configuration(
        Bucket=MEDIA_BUCKET,
        LifecycleConfiguration={
            "Rules": [
                {
                    "ID": "expire-media",
                    "Status": "Enabled",
                    "Filter": {"Prefix": "posts/"},
                    "Expiration": {"Days": 30},
                }
            ]
        },
    )
    logger.info("Bucket %s creado en %s", MEDIA_BUCKET, AWS_REGION)
    return MEDIA_BUCKET


def prepare(path: Path) -> tuple[bytes, tuple[int, int]]:
    """Normaliza una imagen a lo que Instagram acepta: JPEG RGB, ancho <= 1440.

    Devuelve (bytes_jpeg, (ancho, alto)). Lanza MediaError si el aspect ratio
    queda fuera del rango permitido, porque Meta rechazaría el contenedor.
    """
    try:
        img = Image.open(path)
    except Exception as exc:  # noqa: BLE001 - detalle al log, mensaje limpio afuera
        logger.exception("No se pudo abrir la imagen %s", path)
        raise MediaError(f"No se pudo leer la imagen: {path.name}") from exc

    img = img.convert("RGB")
    ratio = img.width / img.height
    if not (MIN_RATIO - 0.01 <= ratio <= MAX_RATIO + 0.01):
        raise MediaError(
            f"{path.name}: proporción {ratio:.2f} fuera del rango que acepta "
            f"Instagram ({MIN_RATIO:.2f}–{MAX_RATIO:.2f}). "
            "Recorta la imagen a 4:5, 1:1 o 1.91:1."
        )

    if img.width > MAX_WIDTH:
        new_h = round(img.height * MAX_WIDTH / img.width)
        img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)

    # Baja la calidad progresivamente hasta entrar en el límite de 8 MB.
    for quality in (92, 85, 78, 70):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_BYTES:
            return data, img.size

    raise MediaError(f"{path.name}: no baja de 8 MB ni con calidad 70.")


def upload(path: Path, slug: str, index: int) -> str:
    """Sube una slide ya normalizada a S3 y devuelve su key."""
    data, size = prepare(path)
    digest = hashlib.sha256(data).hexdigest()[:12]
    key = f"posts/{slug}/{index:02d}-{digest}.jpg"
    _s3().put_object(
        Bucket=MEDIA_BUCKET,
        Key=key,
        Body=data,
        ContentType="image/jpeg",
    )
    logger.info("Subida %s (%dx%d, %d KB)", key, size[0], size[1], len(data) // 1024)
    return key


def presign(key: str, ttl: int = PRESIGN_TTL) -> str:
    """URL temporal que Meta usará para descargar la imagen."""
    return _s3().generate_presigned_url(
        "get_object",
        Params={"Bucket": MEDIA_BUCKET, "Key": key},
        ExpiresIn=ttl,
    )
