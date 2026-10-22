"""Da de baja una dirección del correo de la promoción de la demo (#647).

El pie del correo pide responder a contacto@glomacx.com para no recibir más.
La baja se hace en la lista de supresión de SES de la CUENTA (que suprime
BOUNCE y COMPLAINT): SES no le vuelve a entregar nada a esa dirección desde
ningún remitente de la cuenta, sin columna nuestra.

Uso (con credenciales que permitan `ses:PutSuppressedDestination`; región
`SES_REGION`, default us-east-1, donde está verificado glomacx.com):
    python backend/scripts/baja_correo_promo.py persona@dominio.com
    python backend/scripts/baja_correo_promo.py --consultar persona@dominio.com

Equivale a:
    aws sesv2 put-suppressed-destination --email-address persona@dominio.com \\
        --reason COMPLAINT --region us-east-1

No imprime la dirección (la salida puede quedar en logs).
"""
from __future__ import annotations

import argparse
import os
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Baja del correo de la promoción (supresión SES).")
    parser.add_argument("correo")
    parser.add_argument("--consultar", action="store_true", help="solo dice si ya está suprimida")
    args = parser.parse_args(argv)
    correo = args.correo.strip().lower()
    if "@" not in correo or any(c.isspace() for c in correo):
        sys.exit("correo inválido")

    import boto3

    region = os.getenv("SES_REGION") or "us-east-1"
    ses = boto3.client("sesv2", region_name=region)
    if args.consultar:
        try:
            r = ses.get_suppressed_destination(EmailAddress=correo)
            print(f"suprimida: sí (motivo {r['SuppressedDestination']['Reason']}, región {region})")
        except ses.exceptions.NotFoundException:
            print(f"suprimida: no (región {region})")
        return 0
    ses.put_suppressed_destination(EmailAddress=correo, Reason="COMPLAINT")
    print(f"ok: dirección agregada a la lista de supresión de SES (región {region})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
