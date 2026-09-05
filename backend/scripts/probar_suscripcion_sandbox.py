"""Prueba el flujo de suscripción contra el **sandbox real de Wompi**.

Los tests de `tests/pagos/` corren contra un Wompi de mentira: prueban nuestra
lógica, no que Wompi acepte lo que le mandamos. Este script cierra esa brecha —
recorre los cuatro pasos contra la caja de arena de verdad y dice en cuál se
rompe, si se rompe.

    export WOMPI_PUBLIC_KEY=pub_test_...
    export WOMPI_PRIVATE_KEY=prv_test_...
    export WOMPI_INTEGRITY_SECRET=test_integrity_...
    python backend/scripts/probar_suscripcion_sandbox.py

Se niega a correr con llaves `pub_prod_`: cobrar $350.000 de verdad por
equivocación es exactamente lo que este script no puede hacer. Para eso está el
`--forzar-produccion`, que además pide confirmación escrita.

Datos de prueba del sandbox (doc de Wompi, consultada 2026-09-05):

    4242 4242 4242 4242 → APPROVED
    4111 1111 1111 1111 → DECLINED
    cualquier otra      → ERROR

Cualquier fecha futura y cualquier CVC de tres dígitos sirven.

Nada de lo que imprime este script incluye una llave: se reporta el prefijo
(`pub_test`), nunca el valor.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, Optional

import httpx

# Mismo preámbulo que las migraciones: se busca el ARCHIVO `app/database.py`,
# no la carpeta `app` (desde `/`, Python 3 la tomaría como namespace package).
_CANDIDATOS = ["/app"]
if "__file__" in globals():
    _CANDIDATOS.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
for _ruta in _CANDIDATOS:
    if os.path.isfile(os.path.join(_ruta, "app", "database.py")):
        sys.path.insert(0, _ruta)
        break

from app.services import suscripciones as svc  # type: ignore  # noqa: E402
from app.services import wompi  # type: ignore  # noqa: E402

TARJETA_APROBADA = "4242424242424242"
TARJETA_RECHAZADA = "4111111111111111"

VERDE, ROJO, GRIS, FIN = "\033[92m", "\033[91m", "\033[90m", "\033[0m"


def ok(texto: str) -> None:
    print(f"  {VERDE}✓{FIN} {texto}")


def falla(texto: str) -> None:
    print(f"  {ROJO}✗{FIN} {texto}")


def nota(texto: str) -> None:
    print(f"    {GRIS}{texto}{FIN}")


def tokenizar(numero: str, public_key: str) -> Optional[str]:
    """Paso 1: la tarjeta → token. Es lo que hace el NAVEGADOR, con la llave
    pública. Se replica acá para poder probar el flujo entero sin abrir el
    navegador."""
    respuesta = httpx.post(
        f"{wompi.base_url().rstrip('/')}/tokens/cards",
        headers={"Authorization": f"Bearer {public_key}"},
        json={
            "number": numero,
            "cvc": "123",
            "exp_month": "08",
            "exp_year": "30",
            "card_holder": "PRUEBA GLOMA",
        },
        timeout=20.0,
    )
    if respuesta.status_code != 201:
        falla(f"tokenización: HTTP {respuesta.status_code}")
        nota(respuesta.text[:300])
        return None
    datos = (respuesta.json() or {}).get("data") or {}
    token = datos.get("id")
    ok(f"tarjeta tokenizada ({datos.get('brand')} ····{datos.get('last_four')})")
    return token


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tarjeta",
        default=TARJETA_APROBADA,
        help=f"Número a probar (default: {TARJETA_APROBADA}, que aprueba).",
    )
    parser.add_argument(
        "--rechazada",
        action="store_true",
        help="Usa la tarjeta que el sandbox rechaza, para probar ese camino.",
    )
    parser.add_argument(
        "--forzar-produccion",
        action="store_true",
        help="Permite correr con llaves pub_prod_. COBRA DINERO REAL.",
    )
    args = parser.parse_args()

    numero = TARJETA_RECHAZADA if args.rechazada else args.tarjeta

    public_key = os.getenv("WOMPI_PUBLIC_KEY", "").strip()
    if not public_key or not os.getenv("WOMPI_PRIVATE_KEY", "").strip():
        falla("Faltan WOMPI_PUBLIC_KEY y/o WOMPI_PRIVATE_KEY en el entorno.")
        return 2
    if not os.getenv("WOMPI_INTEGRITY_SECRET", "").strip():
        falla("Falta WOMPI_INTEGRITY_SECRET: sin él Wompi rechaza la transacción.")
        return 2

    if wompi.es_produccion() and not args.forzar_produccion:
        falla("Llave de PRODUCCIÓN detectada. Este script cobra de verdad con ella.")
        nota("Usa llaves pub_test_/prv_test_, o pasa --forzar-produccion.")
        return 2
    if wompi.es_produccion():
        print(f"{ROJO}Vas a hacer un cobro REAL de "
              f"{svc.PLAN_MENSUAL.amount_cop:,} COP.{FIN}")
        if input('Escribe "COBRAR DE VERDAD" para continuar: ') != "COBRAR DE VERDAD":
            print("Cancelado.")
            return 1

    print(f"\nAmbiente: {wompi.base_url()}")
    print(f"Llave:    {public_key[:8]}…  ({'PRODUCCIÓN' if wompi.es_produccion() else 'sandbox'})")
    print(f"Tarjeta:  ····{numero[-4:]}")
    print(f"Monto:    {svc.PLAN_MENSUAL.amount_cop:,} COP\n")

    # --- 1. tokens de aceptación -----------------------------------------
    print("1. Tokens de aceptación (habeas data)")
    try:
        aceptacion = wompi.tokens_de_aceptacion()
    except wompi.WompiError as error:
        falla(f"no se pudieron obtener ({error.codigo})")
        return 1
    ok("obtenidos")
    nota(f"reglamento: {aceptacion.get('acceptance_permalink')}")
    if not aceptacion.get("personal_auth_token"):
        nota("este comercio no expone presigned_personal_data_auth; no se manda")

    # --- 2. tokenización --------------------------------------------------
    print("\n2. Tokenización de la tarjeta (navegador → Wompi, llave pública)")
    token = tokenizar(numero, public_key)
    if not token:
        return 1

    # --- 3. fuente de pago ------------------------------------------------
    print("\n3. Fuente de pago (backend → Wompi, llave privada)")
    try:
        fuente = wompi.crear_fuente_de_pago(
            token_tarjeta=token,
            email_cliente="pruebas@glomacx.com",
            acceptance_token=aceptacion["acceptance_token"],
            personal_auth_token=aceptacion.get("personal_auth_token"),
        )
    except wompi.WompiError as error:
        falla(f"no se pudo crear ({error.codigo})")
        return 1
    if fuente.get("status") != "AVAILABLE":
        falla(f"la fuente quedó en {fuente.get('status')}, no sirve para cobrar")
        return 1
    ok(f"creada · {fuente.get('brand')} ····{fuente.get('last_four')}")

    # --- 4. cobro ---------------------------------------------------------
    print("\n4. Cobro recurrente")
    referencia = svc.nueva_referencia(0, __import__("datetime").datetime.utcnow())
    try:
        transaccion = wompi.cobrar_con_fuente_de_pago(
            payment_source_id=int(fuente["id"]),
            monto_centavos=svc.PLAN_MENSUAL.amount_cents,
            referencia=referencia,
            email_cliente="pruebas@glomacx.com",
            acceptance_token=aceptacion["acceptance_token"],
        )
    except wompi.WompiError as error:
        falla(f"el cobro no salió ({error.codigo})")
        return 1
    tx_id = transaccion.get("id")
    ok(f"transacción creada · {transaccion.get('status')}")
    nota(f"referencia {referencia}")

    # --- 5. estado final --------------------------------------------------
    print("\n5. Estado final (lo que confirmaría el webhook)")
    estado = str(transaccion.get("status") or "")
    for intento in range(6):
        if estado in ("APPROVED", "DECLINED", "ERROR", "VOIDED"):
            break
        time.sleep(2)
        real: Optional[Dict[str, Any]] = wompi.consultar_transaccion(str(tx_id))
        estado = str((real or {}).get("status") or estado)
        nota(f"intento {intento + 1}: {estado}")

    esperado = "DECLINED" if numero == TARJETA_RECHAZADA else "APPROVED"
    if estado == esperado:
        ok(f"{estado} — es lo que el sandbox debía responder para esta tarjeta")
    elif estado in ("APPROVED", "DECLINED"):
        falla(f"{estado}, pero se esperaba {esperado}")
        return 1
    else:
        falla(f"quedó en {estado}")
        nota("Con una tarjeta distinta a las de prueba, el sandbox da ERROR.")
        return 1

    print(f"\n{VERDE}El flujo completo funciona contra {wompi.base_url()}.{FIN}")
    print("Falta comprobar el webhook: Wompi tiene que poder llegar a")
    print("  POST https://api.glomacx.com/pagos/wompi/webhook")
    print("configurado en el panel, con WOMPI_EVENTS_SECRET en el backend.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
