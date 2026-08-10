"""Credenciales y configuración de la conexión de Instagram (marketing).

Fuente de verdad: AWS SSM Parameter Store en `sa-east-1`, bajo el prefijo
`/gloma/marketing/instagram/`. El access token y el app secret se guardan como
SecureString (cifrados con KMS). Para desarrollo puntual se pueden sobreescribir
con variables de entorno `IG_*`.

Reglas de seguridad del proyecto que aplican aquí:
  #1  El token y el app secret NUNCA se imprimen ni se loggean. `Credentials`
      define un __repr__ que los redacta.
  #3  Son secretos que pertenecen a una cuenta concreta, así que van cifrados en
      un almacén de secretos, nunca en `.env` ni en el repo.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import boto3
from botocore.exceptions import ClientError

AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "sa-east-1")
SSM_PREFIX = "/gloma/marketing/instagram"

# Bucket donde viven las imágenes que Instagram descarga al publicar. Privado:
# el acceso se da con URLs prefirmadas de vida corta, nunca con ACL pública.
MEDIA_BUCKET = os.environ.get("IG_MEDIA_BUCKET", "gloma-marketing-media-747456040509")

# Versión de la Graph API. Configurable porque Meta rota versiones cada ~3 meses.
API_VERSION = os.environ.get("IG_API_VERSION", "v23.0")

# Los tokens de larga duración de Instagram viven 60 días y deben refrescarse
# cuando tienen al menos 24 h de antigüedad.
TOKEN_TTL_DAYS = 60
REFRESH_WHEN_DAYS_LEFT = 10


class ConfigError(RuntimeError):
    """Falta configuración o credenciales para operar."""


def _ssm():
    return boto3.client("ssm", region_name=AWS_REGION)


def _param(name: str, *, decrypt: bool = False) -> Optional[str]:
    """Lee un parámetro de SSM. Devuelve None si no existe."""
    try:
        resp = _ssm().get_parameter(Name=f"{SSM_PREFIX}/{name}", WithDecryption=decrypt)
        return resp["Parameter"]["Value"]
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ParameterNotFound":
            return None
        raise


def put_param(name: str, value: str, *, secret: bool = False) -> None:
    """Escribe un parámetro en SSM. Los secretos van como SecureString."""
    _ssm().put_parameter(
        Name=f"{SSM_PREFIX}/{name}",
        Value=value,
        Type="SecureString" if secret else "String",
        Overwrite=True,
    )


@dataclass
class Credentials:
    """Credenciales de la conexión. Nunca serializar tal cual."""

    app_id: str
    app_secret: str = field(repr=False)
    access_token: str = field(repr=False)
    ig_user_id: str
    username: Optional[str] = None
    expires_at: Optional[datetime] = None

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"<Credentials app_id={self.app_id!r} ig_user_id={self.ig_user_id!r} "
            f"username={self.username!r} app_secret=<REDACTED> "
            f"access_token=<REDACTED> expires_at={self.expires_at}>"
        )

    @property
    def days_left(self) -> Optional[int]:
        if not self.expires_at:
            return None
        return (self.expires_at - datetime.now(timezone.utc)).days

    @property
    def needs_refresh(self) -> bool:
        left = self.days_left
        return left is not None and left <= REFRESH_WHEN_DAYS_LEFT


def _env_or_ssm(env_key: str, ssm_key: str, *, decrypt: bool = False) -> Optional[str]:
    return os.environ.get(env_key) or _param(ssm_key, decrypt=decrypt)


def load_app() -> tuple[str, str]:
    """Devuelve (app_id, app_secret). Necesario para el flujo OAuth."""
    app_id = _env_or_ssm("IG_APP_ID", "APP_ID")
    app_secret = _env_or_ssm("IG_APP_SECRET", "APP_SECRET", decrypt=True)
    if not app_id or not app_secret:
        raise ConfigError(
            "Faltan las credenciales de la app de Meta. Corre primero:\n"
            "  igpost.py setup-app --app-id <ID> --app-secret <SECRET>"
        )
    return app_id, app_secret


def load() -> Credentials:
    """Carga las credenciales completas. Lanza ConfigError si falta el token."""
    app_id, app_secret = load_app()
    token = _env_or_ssm("IG_ACCESS_TOKEN", "ACCESS_TOKEN", decrypt=True)
    ig_user_id = _env_or_ssm("IG_USER_ID", "IG_USER_ID")
    if not token or not ig_user_id:
        raise ConfigError(
            "La cuenta de Instagram todavía no está conectada. Corre:\n"
            "  igpost.py auth-url        # genera el enlace de autorización\n"
            "  igpost.py connect --code <CODE>"
        )
    raw_exp = _param("TOKEN_EXPIRES_AT")
    expires_at = datetime.fromisoformat(raw_exp) if raw_exp else None
    return Credentials(
        app_id=app_id,
        app_secret=app_secret,
        access_token=token,
        ig_user_id=ig_user_id,
        username=_param("USERNAME"),
        expires_at=expires_at,
    )


def save_token(token: str, expires_in: int, ig_user_id: str, username: str) -> datetime:
    """Persiste el token de larga duración y los datos de la cuenta."""
    expires_at = datetime.now(timezone.utc).astimezone() + _timedelta_seconds(expires_in)
    put_param("ACCESS_TOKEN", token, secret=True)
    put_param("IG_USER_ID", ig_user_id)
    put_param("USERNAME", username)
    put_param("TOKEN_EXPIRES_AT", expires_at.isoformat())
    return expires_at


def _timedelta_seconds(seconds: int):
    from datetime import timedelta

    return timedelta(seconds=seconds)
