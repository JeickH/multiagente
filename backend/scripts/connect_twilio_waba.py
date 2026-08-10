"""Sprint 22 — Conecta una cuenta WABA (vía Twilio como BSP) a un team.

Crea o actualiza la fila de `meta_accounts` del team indicado con
`provider='twilio'` y las credenciales del tenant: Account SID, Auth Token
cifrado con Fernet, y el emisor (`twilio_from` o `twilio_messaging_service_sid`).

Reglas de seguridad aplicadas:
  - #1 el Auth Token nunca se imprime ni se loggea.
  - #3 el secreto de tenant queda en BD cifrado, no en `.env`.

Env vars:
    TEAM_ID                        (obligatoria) id del team dueño del WABA
    TW_ACCOUNT_SID                 (obligatoria) AC... de la cuenta/subcuenta
    TW_AUTH_TOKEN                  Auth Token en claro (se cifra aquí)
    TW_AUTH_TOKEN_ENC              …o el ciphertext Fernet ya calculado
    TW_FROM                        p.ej. '+14155238886' (se normaliza a whatsapp:)
    TW_MESSAGING_SERVICE_SID       MG... (tiene prioridad sobre TW_FROM en el envío)
    TW_DISPLAY_PHONE               teléfono visible (default: TW_FROM)
    TW_VERIFIED_NAME               nombre visible en WhatsApp
    TW_WABA_ID                     id del WhatsApp Business Account (informativo)

Uso local:
    docker compose exec -T -e TEAM_ID=9 -e TW_ACCOUNT_SID=AC... \
        -e TW_AUTH_TOKEN=... -e TW_FROM=+57... backend \
        python scripts/connect_twilio_waba.py

Uso en RDS (pasando el token YA cifrado, nunca el plaintext por CloudTrail):
    ./backend/scripts/rds_exec.sh backend/scripts/connect_twilio_waba.py \
        TEAM_ID=5 TW_ACCOUNT_SID=AC... TW_AUTH_TOKEN_ENC=gAAAA... TW_FROM=+57...
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

if "__file__" in globals():  # no existe cuando corre vía `python -c`
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal  # type: ignore
from app import models  # type: ignore
from app.services.crypto import encrypt_secret  # type: ignore


def _norm_from(value: str | None) -> str | None:
    """Normaliza a `whatsapp:+E164`, que es lo que espera el adapter."""
    if not value:
        return None
    v = value.strip()
    if v.startswith("whatsapp:"):
        return v
    if not v.startswith("+"):
        v = "+" + v
    return f"whatsapp:{v}"


def main() -> int:
    team_id = os.environ.get("TEAM_ID")
    account_sid = os.environ.get("TW_ACCOUNT_SID")
    token_plain = os.environ.get("TW_AUTH_TOKEN")
    token_enc = os.environ.get("TW_AUTH_TOKEN_ENC")
    tw_from = _norm_from(os.environ.get("TW_FROM"))
    msg_sid = os.environ.get("TW_MESSAGING_SERVICE_SID") or None

    if not team_id or not account_sid:
        print("ERROR: faltan TEAM_ID y/o TW_ACCOUNT_SID.")
        return 1
    if not token_plain and not token_enc:
        print("ERROR: falta TW_AUTH_TOKEN (o TW_AUTH_TOKEN_ENC).")
        return 1
    if not tw_from and not msg_sid:
        print("ERROR: falta TW_FROM o TW_MESSAGING_SERVICE_SID.")
        return 1

    display_phone = os.environ.get("TW_DISPLAY_PHONE") or (
        (tw_from or "").replace("whatsapp:", "") or account_sid
    )
    verified_name = os.environ.get("TW_VERIFIED_NAME") or None
    waba_id = os.environ.get("TW_WABA_ID") or None

    db = SessionLocal()
    try:
        team = db.get(models.Team, int(team_id))
        if team is None:
            print(f"ERROR: no existe el team {team_id}.")
            return 1

        acc = (
            db.query(models.MetaAccount)
            .filter(models.MetaAccount.team_id == int(team_id))
            .one_or_none()
        )
        accion = "update" if acc else "create"
        if acc is None:
            acc = models.MetaAccount(team_id=int(team_id))
            db.add(acc)

        acc.provider = "twilio"
        acc.twilio_account_sid = account_sid
        acc.encrypted_twilio_auth_token = token_enc or encrypt_secret(token_plain)
        acc.twilio_from = tw_from
        acc.twilio_messaging_service_sid = msg_sid
        acc.display_phone = display_phone
        if verified_name:
            acc.verified_name = verified_name
        if waba_id:
            acc.waba_id = waba_id
        acc.is_active = True
        acc.status = "active"
        acc.last_validated_at = datetime.utcnow()
        acc.validation_error = None

        db.commit()
        db.refresh(acc)
        print(
            f"OK ({accion}) meta_account_id={acc.id} team_id={acc.team_id} "
            f"provider={acc.provider} display_phone={acc.display_phone} "
            f"from={acc.twilio_from} msg_service={acc.twilio_messaging_service_sid} "
            f"status={acc.status} token=<REDACTED>"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
