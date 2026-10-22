"""Notas de voz a texto con Amazon Transcribe (CEO, 2026-10-21).

En tres días de pauta, 12 personas le hablaron al bot por audio y el bot solo
podía contestar «no puedo escuchar notas de voz». Aquí el audio que ya está en
el bucket de adjuntos se pasa por Transcribe (sa-east-1, español) y el bot
recibe el texto.

Se usa un trabajo por lotes y no streaming porque el audio ya está entero en S3
y una nota de WhatsApp dura segundos: medido el 2026-10-21, un audio corto
termina en ~4 s de proceso y ~10 s en total. Igual hay un tope (`timeout`): si
Transcribe tarda o falla, se devuelve None y el bot responde como siempre.

Privacidad (regla #1): el texto transcrito es lo que dijo un cliente. No se
escribe en ningún log; solo el estado del trabajo.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

#: Formatos que Transcribe acepta, por extensión del archivo guardado.
_FORMATOS = {
    "ogg": "ogg", "oga": "ogg", "opus": "ogg", "mp3": "mp3", "m4a": "m4a",
    "mp4": "mp4", "wav": "wav", "flac": "flac", "amr": "amr", "webm": "webm",
}


def habilitada() -> bool:
    """Se enciende con `TRANSCRIBIR_NOTAS_DE_VOZ=1` en la task-def: apagarla no
    necesita deploy, solo una revisión nueva sin la variable."""
    return os.getenv("TRANSCRIBIR_NOTAS_DE_VOZ", "").strip() == "1"


def formato_de(nombre: str) -> Optional[str]:
    return _FORMATOS.get(nombre.rsplit(".", 1)[-1].lower()) if "." in nombre else None


def _cliente():
    import boto3

    return boto3.client(
        "transcribe", region_name=os.getenv("TRANSCRIBE_REGION", "sa-east-1")
    )


def transcribir(uri_s3: str, formato: str, *, timeout: float = 25.0) -> Optional[str]:
    """El texto del audio en `uri_s3`, o None si no se pudo a tiempo."""
    cliente = _cliente()
    trabajo = f"nota-voz-{uuid.uuid4().hex}"
    try:
        cliente.start_transcription_job(
            TranscriptionJobName=trabajo,
            LanguageCode=os.getenv("TRANSCRIBE_IDIOMA", "es-US"),
            MediaFormat=formato,
            Media={"MediaFileUri": uri_s3},
        )
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            job = cliente.get_transcription_job(TranscriptionJobName=trabajo)["TranscriptionJob"]
            estado = job.get("TranscriptionJobStatus")
            if estado == "COMPLETED":
                url = job["Transcript"]["TranscriptFileUri"]
                with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (URL prefirmada de AWS)
                    datos = json.loads(resp.read().decode("utf-8"))
                textos = [t.get("transcript", "") for t in datos["results"]["transcripts"]]
                texto = " ".join(t.strip() for t in textos if t and t.strip())
                return texto or None
            if estado == "FAILED":
                logger.warning("transcripcion: el trabajo falló (%s)", job.get("FailureReason", "")[:120])
                return None
            time.sleep(1.5)
        logger.warning("transcripcion: se pasó del tope de %.0f s", timeout)
        return None
    except Exception:
        logger.exception("transcripcion: error llamando a Transcribe")
        return None
    finally:
        try:
            cliente.delete_transcription_job(TranscriptionJobName=trabajo)
        except Exception:
            pass
