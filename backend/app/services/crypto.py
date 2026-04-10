"""Servicio de cifrado para secretos per-tenant.

Usa Fernet (AES-128-CBC + HMAC-SHA256) via MultiFernet para soportar rotación
de claves sin downtime.

Variables de entorno:
- APP_ENCRYPTION_KEY: clave Fernet actual (obligatoria). Generar con:
  python backend/scripts/gen_encryption_key.py
- APP_ENCRYPTION_KEY_OLD: clave Fernet anterior (opcional, solo durante rotación).
  Permite descifrar datos aún cifrados con la clave vieja.

Procedimiento de rotación de claves:
1. Generar nueva clave con gen_encryption_key.py.
2. Setear APP_ENCRYPTION_KEY_OLD = clave actual, APP_ENCRYPTION_KEY = clave nueva.
3. Reiniciar backend. MultiFernet ahora cifra con la nueva y descifra con ambas.
4. Ejecutar script de re-cifrado (pendiente de implementar) para migrar todos los
   registros a la nueva clave.
5. Remover APP_ENCRYPTION_KEY_OLD del entorno y reiniciar.

IMPORTANTE:
- Prohibido loggear plaintext ni ciphertext.
- Prohibido imprimir las claves.
- Si APP_ENCRYPTION_KEY no está seteada o es inválida, el módulo crashea al
  importarse (fail-fast).
"""

from functools import lru_cache
from typing import List
import os

from cryptography.fernet import Fernet, MultiFernet, InvalidToken


class CryptoError(Exception):
    """Error opaco de cifrado/descifrado. NUNCA incluir plaintext ni ciphertext."""


def _load_keys() -> List[bytes]:
    """Carga claves Fernet desde env vars. Falla ruidosamente si no están.

    Orden: la clave "actual" (APP_ENCRYPTION_KEY) va primero — MultiFernet usa
    la primera para cifrar y todas para descifrar.
    """
    primary = os.getenv("APP_ENCRYPTION_KEY")
    if not primary:
        raise CryptoError(
            "APP_ENCRYPTION_KEY no está configurada. Genera una clave con "
            "'python backend/scripts/gen_encryption_key.py' y añádela al .env."
        )

    keys: List[bytes] = []
    for raw in (primary, os.getenv("APP_ENCRYPTION_KEY_OLD")):
        if not raw:
            continue
        try:
            # Fernet valida el formato al instanciar
            Fernet(raw.encode("utf-8"))
            keys.append(raw.encode("utf-8"))
        except (ValueError, TypeError) as exc:
            raise CryptoError(
                "Una de las APP_ENCRYPTION_KEY no tiene el formato Fernet válido "
                "(debe ser 32 bytes base64 url-safe)."
            ) from exc

    return keys


@lru_cache(maxsize=1)
def _get_fernet() -> MultiFernet:
    """Devuelve el MultiFernet cacheado para este proceso.

    Si las env vars cambian en runtime, hay que reiniciar el proceso.
    """
    keys = _load_keys()
    return MultiFernet([Fernet(k) for k in keys])


def encrypt_secret(plaintext: str) -> str:
    """Cifra un secreto de texto plano. Devuelve ciphertext como string utf-8."""
    if not isinstance(plaintext, str):
        raise CryptoError("plaintext debe ser str")
    if not plaintext:
        raise CryptoError("plaintext vacío no permitido")
    try:
        token = _get_fernet().encrypt(plaintext.encode("utf-8"))
        return token.decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise CryptoError("No se pudo cifrar el secreto") from exc


def decrypt_secret(ciphertext: str) -> str:
    """Descifra un ciphertext Fernet. Lanza CryptoError opaco en caso de fallo."""
    if not isinstance(ciphertext, str):
        raise CryptoError("ciphertext debe ser str")
    if not ciphertext:
        raise CryptoError("ciphertext vacío no permitido")
    try:
        return _get_fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise CryptoError("No se pudo descifrar el secreto") from exc
    except Exception as exc:
        # Cualquier otro error también opaco — NO filtrar causa
        raise CryptoError("Error de cifrado") from exc


# Fail-fast al importar el módulo: si la clave no está, queremos crashear
# al arranque del backend, no en el primer request.
_get_fernet()
