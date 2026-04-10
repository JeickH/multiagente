"""Configuración centralizada del backend.

Carga variables de entorno con Pydantic Settings y FALLA AL ARRANQUE si faltan
variables críticas (hallazgo S-12 del informe de seguridad Sprint 7).

Uso:
    from app.config import settings
    print(settings.secret_key)
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings del backend.

    Todas las variables críticas son obligatorias. Si falta alguna, la app
    crashea al arranque con un mensaje claro.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== Auth =====
    secret_key: str = Field(..., description="JWT signing key")
    algorithm: str = Field(default="HS256", description="JWT algorithm")
    access_token_expire_minutes: int = Field(default=30, ge=1, le=240)

    # ===== Database =====
    database_url: str = Field(..., description="SQLAlchemy DATABASE_URL")

    # ===== Cifrado de secretos multi-tenant =====
    app_encryption_key: str = Field(..., description="Fernet key (ver crypto.py)")
    app_encryption_key_old: Optional[str] = Field(
        default=None, description="Clave Fernet anterior (solo rotación)"
    )

    # ===== Meta (globales, no per-tenant) =====
    meta_api_version: str = Field(default="v22.0")
    meta_app_secret: Optional[str] = Field(
        default=None,
        description="Secret de la app Meta para verificar HMAC del webhook. "
        "Obligatorio en producción.",
    )
    meta_webhook_verify_token: Optional[str] = Field(default=None)

    # ===== Entorno =====
    app_env: str = Field(default="development")

    @field_validator("secret_key")
    @classmethod
    def _secret_key_not_placeholder(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("SECRET_KEY no puede estar vacío")
        # Hallazgo S-25: rechazar placeholder en prod
        import os
        if (
            v == "cambia-este-secreto-en-produccion"
            and os.getenv("APP_ENV", "development") == "production"
        ):
            raise ValueError(
                "SECRET_KEY tiene el valor placeholder en producción. "
                "Genera uno con: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )
        return v

    @field_validator("app_encryption_key")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError(
                "APP_ENCRYPTION_KEY no puede estar vacío. "
                "Genera una con: python backend/scripts/gen_encryption_key.py"
            )
        # Validar formato Fernet
        try:
            from cryptography.fernet import Fernet
            Fernet(v.encode("utf-8"))
        except Exception as exc:
            raise ValueError(
                "APP_ENCRYPTION_KEY no tiene formato Fernet válido (32 bytes base64 url-safe)"
            ) from exc
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


# Instancia global para imports convenientes
settings = get_settings()
