"""Crea la plantilla Content API `twilio/catalog` para el bot de Talulah (#264).

El catálogo vive en Meta Commerce Manager (id 176204398531184) y debe estar
VINCULADO a la WABA en WhatsApp Manager. Dentro de la ventana de servicio de
24h (siempre el caso del bot, que responde mensajes entrantes) el catálogo se
envía SIN aprobación de Meta; la aprobación (--approve) solo hace falta para
iniciar conversaciones fuera de ventana.

Uso (cuando existan las claves Twilio):

    TWILIO_ACCOUNT_SID=ACxxx TWILIO_AUTH_TOKEN=xxx \
    python backend/scripts/create_twilio_catalog_template.py

    # opcional: someter a aprobación de Meta para uso fuera de ventana
    ... --approve

Imprime el ContentSid (HX...). Después, re-correr el seed con:

    TALULAH_CATALOG_CONTENT_SID=HXxxx ... python scripts/seed_bot_talulah.py

y el bot enviará el catálogo como mensaje nativo por Twilio (mientras tanto
usa fallback de texto).
"""
from __future__ import annotations

import os
import sys

import httpx

CATALOG_ID = os.environ.get("TALULAH_CATALOG_ID", "176204398531184")
FRIENDLY_NAME = os.environ.get("CATALOG_TEMPLATE_NAME", "talulah_catalogo_completo")


def main() -> int:
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "")
    token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not (sid and token):
        print("ERROR: faltan TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN en el entorno.")
        return 1

    payload = {
        "friendly_name": FRIENDLY_NAME,
        "language": "es",
        "types": {
            "twilio/catalog": {
                # Catálogo COMPLETO de la marca (sin items => catálogo entero).
                "id": CATALOG_ID,
                "title": "Colección Talulah 🤍",
                "body": "Explora nuestra colección y encuentra tu prenda "
                        "perfecta 🌿✨",
            }
        },
    }
    resp = httpx.post(
        "https://content.twilio.com/v1/Content",
        json=payload, auth=(sid, token), timeout=20,
    )
    if resp.status_code not in (200, 201):
        print(f"ERROR {resp.status_code}: {resp.text[:400]}")
        return 1
    content_sid = resp.json().get("sid")
    print(f"OK: ContentSid = {content_sid}")

    if "--approve" in sys.argv:
        ar = httpx.post(
            f"https://content.twilio.com/v1/Content/{content_sid}/ApprovalRequests/whatsapp",
            json={"name": FRIENDLY_NAME, "category": "MARKETING"},
            auth=(sid, token), timeout=20,
        )
        print(f"Aprobación Meta: {ar.status_code} {ar.text[:200]}")

    print()
    print("Siguiente paso: re-correr seed_bot_talulah.py con "
          f"TALULAH_CATALOG_CONTENT_SID={content_sid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
