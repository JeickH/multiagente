"""Integración con Wompi (Colombia) — Web Checkout y webhook de eventos.

Doc de referencia (consultada 2026-08-19):
  - https://docs.wompi.co/docs/colombia/widget-checkout-web/
  - https://docs.wompi.co/docs/colombia/eventos/

Cómo funciona el cobro, en dos actos:

1. **Web Checkout.** El navegador manda un `GET` a `https://checkout.wompi.co/p/`
   con el monto, la moneda, nuestra referencia y una **firma de integridad**.
   La firma es lo que impide que alguien edite el HTML y se compre el paquete
   de 5.000 mensajes por $1.000: Wompi recalcula el hash con el mismo secreto
   y rechaza la transacción si no cuadra.

2. **Webhook de eventos.** Cuando la transacción cambia de estado, Wompi hace
   `POST` a nuestra URL con un `checksum` firmado con OTRO secreto (el de
   eventos). Es la única fuente de verdad sobre si un pago se aprobó — el
   `redirect-url` al que vuelve el usuario NO lo es, porque lo controla el
   navegador y cualquiera puede visitarlo a mano.

===========================================================================
SECRETOS
===========================================================================

Las cuatro llaves salen de variables de entorno y **ninguna se escribe en el
código ni se loggea** (reglas 1 y 8 de CLAUDE.md — este repo es público):

  WOMPI_PUBLIC_KEY       `pub_test_...` / `pub_prod_...`. Es la única que
                         puede viajar al navegador: va en el form del checkout.
  WOMPI_PRIVATE_KEY      `prv_test_...`. Server-side. Consulta el estado real
                         de una transacción contra la API de Wompi.
  WOMPI_INTEGRITY_SECRET Firma el monto del checkout. NUNCA al frontend: con
                         él se pueden firmar montos arbitrarios.
  WOMPI_EVENTS_SECRET    Valida el `checksum` del webhook. Sin él, cualquiera
                         que conozca la URL puede regalarse créditos.
  WOMPI_BASE_URL         API de Wompi. Por defecto el **sandbox**: que haya
                         que pedir producción explícitamente, y no al revés.

Las llaves se leen **en cada llamada**, no al importar el módulo. Es
deliberado: si faltan, el que falla es el endpoint de pagos con un error
claro, no el arranque del backend — un despliegue sin llaves de Wompi debe
dejar la plataforma entera en pie, solo con el módulo de pagos fuera de
servicio. Además así los tests pueden ponerlas con `monkeypatch`.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: URL del Web Checkout. Es la misma en sandbox y en producción: lo que decide
#: el ambiente es el prefijo de la llave pública (`pub_test_` / `pub_prod_`).
CHECKOUT_URL = "https://checkout.wompi.co/p/"

#: API de Wompi. Sandbox por defecto (ver docstring del módulo).
BASE_URL_SANDBOX = "https://sandbox.wompi.co/v1"

#: Única moneda que acepta Wompi Colombia hoy.
MONEDA = "COP"


class WompiNoConfigurado(RuntimeError):
    """Falta alguna llave de Wompi en el entorno.

    Se levanta al usar el servicio, nunca al importarlo. El router la traduce
    a un 503 con mensaje genérico: al cliente no se le dice QUÉ variable falta
    (regla 6), eso va al log del servidor.
    """


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def _env(nombre: str) -> str:
    return (os.getenv(nombre) or "").strip()


def base_url() -> str:
    """La API de Wompi contra la que se trabaja."""
    return _env("WOMPI_BASE_URL") or BASE_URL_SANDBOX


def esta_configurado() -> bool:
    """¿Están las llaves mínimas para cobrar? (pública + secreto de integridad)

    No exige el secreto de eventos: sin él se puede generar un checkout, y el
    webhook por su lado ya es fail-closed. Sirve para que la pantalla avise
    "pagos no disponible" en vez de reventar al hacer clic en Comprar.
    """
    return bool(_env("WOMPI_PUBLIC_KEY") and _env("WOMPI_INTEGRITY_SECRET"))


def suscripciones_habilitadas() -> bool:
    """¿Se puede guardar una tarjeta y cobrarla todos los meses?

    Exige **también la llave privada**, que el checkout no necesita: crear la
    fuente de pago y cobrar cada mes son llamadas server-to-server autenticadas
    con ella. Sirve para que la pantalla muestre "no disponible por ahora" en
    vez de llevar al cliente a escribir su tarjeta en un formulario que va a
    fallar en el último paso, con el peor momento posible para fallar.
    """
    return bool(esta_configurado() and _env("WOMPI_PRIVATE_KEY"))


def _requerir(nombre: str) -> str:
    """El valor de la variable, o `WompiNoConfigurado`.

    El log dice qué FALTA (el nombre de la variable), nunca qué hay: el nombre
    de una env var no es un secreto, su contenido sí.
    """
    valor = _env(nombre)
    if not valor:
        logger.error("wompi: falta la variable de entorno %s", nombre)
        raise WompiNoConfigurado(f"Falta {nombre}")
    return valor


def es_produccion() -> bool:
    """True si se está cobrando de verdad (llave `pub_prod_`)."""
    return _env("WOMPI_PUBLIC_KEY").startswith("pub_prod")


def _app_en_produccion() -> bool:
    """`APP_ENV` productivo. Mismo criterio que `meta_webhook._is_production`."""
    return (os.getenv("APP_ENV", "development") or "").strip().lower() in (
        "production",
        "prod",
    )


# ---------------------------------------------------------------------------
# Referencia
# ---------------------------------------------------------------------------

def nueva_referencia(team_id: int, package_key: str) -> str:
    """Referencia única de un intento de pago.

    Formato: `gloma-<team>-<paquete>-<aleatorio>`. Wompi acepta alfanumérico
    con guiones y guiones bajos, y exige que sea única por comercio.

    El sufijo aleatorio es `secrets.token_hex`, no un contador ni el `id` de la
    fila: la referencia viaja en la URL del checkout y en el correo de Wompi,
    así que no debe dejar adivinar la referencia de otro cliente ni delatar
    cuántas compras lleva la plataforma.
    """
    limpio = "".join(c for c in (package_key or "") if c.isalnum() or c in "-_")
    return f"gloma-{int(team_id)}-{limpio}-{secrets.token_hex(8)}"


# ---------------------------------------------------------------------------
# Firma de integridad (checkout)
# ---------------------------------------------------------------------------

def firma_integridad(
    referencia: str,
    monto_centavos: int,
    moneda: str = MONEDA,
    expiracion: Optional[str] = None,
) -> str:
    """SHA256 de `<referencia><monto><moneda>[<expiracion>]<secreto>`.

    El orden de la concatenación es el que exige Wompi y no es negociable: un
    orden distinto produce un hash válido como hash pero que Wompi rechaza.
    Si se manda `expiration-time` en el checkout, entra en la cadena JUSTO
    antes del secreto; si no se manda, no va.

    Se calcula **en el servidor**. La doc de Wompi lo pide expresamente:
    hacerlo en el navegador expondría `WOMPI_INTEGRITY_SECRET`, y con ese
    secreto cualquiera firma el monto que se le antoje.
    """
    secreto = _requerir("WOMPI_INTEGRITY_SECRET")
    cadena = f"{referencia}{int(monto_centavos)}{moneda}"
    if expiracion:
        cadena += expiracion
    cadena += secreto
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest()


def datos_checkout(
    referencia: str,
    monto_centavos: int,
    *,
    moneda: str = MONEDA,
    redirect_url: Optional[str] = None,
    email_cliente: Optional[str] = None,
    expiracion: Optional[str] = None,
) -> Dict[str, Any]:
    """Los campos del form de Web Checkout, ya firmados.

    Devuelve las llaves con el nombre EXACTO que espera Wompi
    (`amount-in-cents`, `signature:integrity`, …) para que el frontend solo
    tenga que volcarlas en inputs ocultos o en un query string, sin traducir
    nada ni tener que conocer el protocolo.

    Lo único sensible que sale de acá es la **llave pública**, que es pública
    por definición. El secreto de integridad se queda en el servidor: lo que
    viaja es su resultado, el hash.
    """
    public_key = _requerir("WOMPI_PUBLIC_KEY")
    firma = firma_integridad(referencia, monto_centavos, moneda, expiracion)

    campos: Dict[str, Any] = {
        "public-key": public_key,
        "currency": moneda,
        "amount-in-cents": int(monto_centavos),
        "reference": referencia,
        "signature:integrity": firma,
    }
    if redirect_url:
        campos["redirect-url"] = redirect_url
    if expiracion:
        campos["expiration-time"] = expiracion
    if email_cliente:
        campos["customer-data:email"] = email_cliente

    return {"url": CHECKOUT_URL, "method": "GET", "fields": campos}


# ---------------------------------------------------------------------------
# Webhook de eventos
# ---------------------------------------------------------------------------

def _valor_anidado(datos: Dict[str, Any], ruta: str) -> str:
    """Baja por una ruta con puntos: `"transaction.id"` → `datos["transaction"]["id"]`.

    Wompi lista en `signature.properties` las propiedades que firmó, como rutas
    relativas a `data`. Un valor ausente se concatena como cadena vacía, que es
    lo que hace que el checksum no cuadre y el evento se rechace.
    """
    actual: Any = datos
    for parte in ruta.split("."):
        if not isinstance(actual, dict):
            return ""
        actual = actual.get(parte)
        if actual is None:
            return ""
    return str(actual)


def verificar_evento(payload: Dict[str, Any]) -> bool:
    """Valida el `checksum` del webhook. **Fail-closed en producción.**

    Receta de Wompi:
      1. tomar de `data` los valores de `signature.properties`, EN ESE ORDEN;
      2. concatenarlos;
      3. pegarle el `timestamp` del evento;
      4. pegarle el secreto de eventos;
      5. SHA256 y comparar contra `signature.checksum`.

    Reglas de CLAUDE.md #5 aplicadas acá:
      - prod y falta `WOMPI_EVENTS_SECRET` → False (una misconfiguración no
        puede convertirse en "cualquiera suma créditos gratis");
      - prod y falta la firma → False;
      - dev y falta el secreto → True, con `logger.warning` bien visible.

    La comparación va con `hmac.compare_digest` para no filtrar por tiempo
    cuánto prefijo del checksum acertó un atacante.
    """
    en_prod = _app_en_produccion() or es_produccion()
    secreto = _env("WOMPI_EVENTS_SECRET")

    if not secreto:
        if en_prod:
            logger.error(
                "wompi.webhook fail-closed: WOMPI_EVENTS_SECRET ausente en producción"
            )
            return False
        logger.warning(
            "FAIL-OPEN: firma del webhook de Wompi NO verificada — solo es "
            "aceptable en desarrollo (WOMPI_EVENTS_SECRET no configurado)"
        )
        return True

    firma = (payload or {}).get("signature") or {}
    checksum = firma.get("checksum")
    propiedades: List[str] = firma.get("properties") or []
    timestamp = (payload or {}).get("timestamp")

    if not checksum or not propiedades or timestamp is None:
        logger.error("wompi.webhook rechazado: evento sin firma o sin timestamp")
        return False

    datos = (payload or {}).get("data") or {}
    cadena = "".join(_valor_anidado(datos, p) for p in propiedades)
    cadena += str(timestamp) + secreto
    esperado = hashlib.sha256(cadena.encode("utf-8")).hexdigest()

    if not hmac.compare_digest(esperado, str(checksum)):
        logger.error("wompi.webhook rechazado: checksum inválido")
        return False
    return True


# ---------------------------------------------------------------------------
# Estados
# ---------------------------------------------------------------------------

#: Estados finales de una transacción de Wompi → estado de `CreditPurchase`.
#: `PENDING` no está: mientras Wompi no decida, la compra se queda como la
#: creamos (`pending`) y no se toca nada.
ESTADOS = {
    "APPROVED": "approved",
    "DECLINED": "declined",
    "VOIDED": "voided",
    "ERROR": "error",
}


def estado_interno(estado_wompi: str) -> Optional[str]:
    """Traduce el estado de Wompi al nuestro; `None` si no es uno final."""
    return ESTADOS.get((estado_wompi or "").strip().upper())


def consultar_transaccion_publica(transaccion_id: str) -> Optional[Dict[str, Any]]:
    """Estado de una transacción SIN llave privada.

    Es lo que hace falta con los **links de pago**: el cliente vuelve a la app
    con `?id=<transaccion>` y hay que decirle si el pago entró o no, pero por
    ese camino no hay llaves configuradas. El endpoint de consulta de Wompi es
    público (es el mismo que usa su propia pantalla de resultado), así que se
    llama sin `Authorization`; si hay llave privada, se manda igual porque no
    estorba.

    Sirve para INFORMAR, no para acreditar. Los créditos siguen dependiendo del
    webhook firmado: un `id` lo puede escribir cualquiera en la barra del
    navegador.

    `None` si no se pudo saber.
    """
    import httpx

    url = f"{base_url().rstrip('/')}/transactions/{transaccion_id}"
    headers: Dict[str, str] = {}
    llave = os.environ.get("WOMPI_PRIVATE_KEY", "").strip()
    if llave:
        headers["Authorization"] = f"Bearer {llave}"
    try:
        respuesta = httpx.get(url, headers=headers, timeout=10.0)
        if respuesta.status_code != 200:
            logger.warning(
                "wompi: consulta pública de transacción respondió %s",
                respuesta.status_code,
            )
            return None
        return (respuesta.json() or {}).get("data")
    except Exception:
        # Sin `str(e)`: el mensaje de httpx puede traer la URL con credenciales.
        logger.exception("wompi: error consultando la transacción (público)")
        return None


# ---------------------------------------------------------------------------
# Fuentes de pago (tarjeta guardada) y cobro recurrente
# ---------------------------------------------------------------------------
#
# Los tres pasos están explicados en `services/suscripciones.py`. Acá va el
# cliente HTTP de cada uno. Regla transversal en todo este bloque: **el cuerpo
# de la respuesta de Wompi nunca se loggea completo** — trae correo, nombre del
# tarjetahabiente y los últimos cuatro dígitos. Se loggea el `type` del error,
# que es un código como `INPUT_VALIDATION_ERROR`, y nada más.


class WompiError(RuntimeError):
    """Wompi rechazó la operación o no se pudo hablar con Wompi.

    `codigo` es el `error.type` de Wompi (o `SIN_RESPUESTA` si no contestó),
    para poder distinguir en el log qué pasó sin guardar el cuerpo. El router
    lo traduce a un mensaje genérico: al cliente no se le reenvía nunca el
    texto de la pasarela (regla 6).
    """

    def __init__(self, mensaje: str, codigo: str = "ERROR") -> None:
        super().__init__(mensaje)
        self.codigo = codigo


def _tipo_de_error(respuesta: Any) -> str:
    """El `error.type` de una respuesta de Wompi, sin arrastrar el cuerpo."""
    try:
        return str(((respuesta.json() or {}).get("error") or {}).get("type") or "ERROR")
    except Exception:
        return "ERROR"


def _post_privado(ruta: str, cuerpo: Dict[str, Any], *, timeout: float = 20.0) -> Dict[str, Any]:
    """`POST` autenticado con la llave privada. Devuelve `data` o levanta.

    Un timeout generoso (20 s) porque del otro lado hay un procesador de
    tarjetas: cortar a los 5 s convertiría cobros lentos pero exitosos en
    "no respondió", y un cobro que no se sabe si pasó es peor que uno lento.
    """
    import httpx

    private_key = _requerir("WOMPI_PRIVATE_KEY")
    url = f"{base_url().rstrip('/')}/{ruta.lstrip('/')}"
    try:
        respuesta = httpx.post(
            url,
            json=cuerpo,
            headers={"Authorization": f"Bearer {private_key}"},
            timeout=timeout,
        )
    except Exception:
        # Sin `str(e)`: el mensaje de httpx puede traer la URL con credenciales.
        logger.exception("wompi: no se pudo hablar con la API (%s)", ruta)
        raise WompiError("sin respuesta de la pasarela", "SIN_RESPUESTA")

    if respuesta.status_code not in (200, 201):
        codigo = _tipo_de_error(respuesta)
        logger.error(
            "wompi: %s respondió %s tipo=%s", ruta, respuesta.status_code, codigo
        )
        raise WompiError("la pasarela rechazó la operación", codigo)

    try:
        return (respuesta.json() or {}).get("data") or {}
    except Exception:
        logger.exception("wompi: respuesta de %s no es JSON", ruta)
        raise WompiError("respuesta ilegible de la pasarela", "RESPUESTA_INVALIDA")


def tokens_de_aceptacion() -> Dict[str, Any]:
    """Los dos tokens de aceptación del comercio, con sus permalinks.

    Colombia (habeas data) exige que el cliente acepte dos documentos antes de
    que se guarden sus datos: el reglamento del servicio y la autorización de
    tratamiento de datos personales. Wompi los entrega prefirmados como JWT y
    hay que reenviárselos al crear la fuente de pago; el `permalink` es el PDF
    que la pantalla tiene que mostrarle al cliente para que los lea.

    Se piden **frescos en cada activación** en vez de cachearlos: los JWT
    expiran, y la gracia del mecanismo es probar que al cliente se le mostró la
    versión vigente del contrato. Un token cacheado apuntaría a un contrato que
    quizá ya cambió.

    Devuelve `{"acceptance_token", "acceptance_permalink",
    "personal_auth_token", "personal_auth_permalink"}`.

    Nada de esto es secreto: los JWT son públicos por diseño (van a un
    formulario en el navegador) y los permalinks son PDFs abiertos.
    """
    import httpx

    public_key = _requerir("WOMPI_PUBLIC_KEY")
    raiz = base_url().rstrip("/")

    # Wompi expone lo mismo en dos rutas: la nueva (`/merchants/info` con el
    # header) y la clásica (`/merchants/<llave pública>`). Se intentan las dos
    # porque ambas están vivas hoy y la doc cita una u otra según la página;
    # si mañana retiran cualquiera de las dos, esto sigue funcionando.
    intentos = (
        (f"{raiz}/merchants/info", {"X-Merchant-Public-Key": public_key}),
        (f"{raiz}/merchants/{public_key}", {}),
    )

    datos: Optional[Dict[str, Any]] = None
    for url, headers in intentos:
        try:
            respuesta = httpx.get(url, headers=headers, timeout=10.0)
        except Exception:
            logger.exception("wompi: no se pudo consultar el comercio")
            continue
        if respuesta.status_code == 200:
            try:
                datos = (respuesta.json() or {}).get("data") or {}
            except Exception:
                logger.exception("wompi: respuesta del comercio no es JSON")
                continue
            break
        logger.warning(
            "wompi: consulta del comercio respondió %s", respuesta.status_code
        )

    if not datos:
        raise WompiError("no se pudieron obtener los términos", "SIN_RESPUESTA")

    aceptacion = datos.get("presigned_acceptance") or {}
    personales = datos.get("presigned_personal_data_auth") or {}

    token_aceptacion = aceptacion.get("acceptance_token")
    if not token_aceptacion:
        logger.error("wompi: el comercio no devolvió presigned_acceptance")
        raise WompiError("no se pudieron obtener los términos", "SIN_ACEPTACION")

    return {
        "acceptance_token": token_aceptacion,
        "acceptance_permalink": aceptacion.get("permalink"),
        # `presigned_personal_data_auth` no lo devuelven todos los comercios.
        # Si no viene, no se manda: mandarlo vacío hace fallar la creación.
        "personal_auth_token": personales.get("acceptance_token"),
        "personal_auth_permalink": personales.get("permalink"),
    }


def crear_fuente_de_pago(
    *,
    token_tarjeta: str,
    email_cliente: str,
    acceptance_token: str,
    personal_auth_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Convierte el token de una tarjeta en una fuente de pago permanente.

    `token_tarjeta` lo produjo el NAVEGADOR contra `/v1/tokens/cards` con la
    llave pública: el número de la tarjeta nunca pasa por acá (ver la nota de
    PCI en `services/suscripciones.py`). Un token es de un solo uso para esto;
    lo que queda reutilizable mes a mes es la fuente de pago.

    Devuelve `{"id", "status", "brand", "last_four"}`. `status` debe ser
    `AVAILABLE` para poder cobrar: cualquier otro valor significa que la fuente
    quedó creada pero no sirve todavía.
    """
    cuerpo: Dict[str, Any] = {
        "type": "CARD",
        "token": token_tarjeta,
        "customer_email": email_cliente,
        "acceptance_token": acceptance_token,
    }
    if personal_auth_token:
        cuerpo["accept_personal_auth"] = personal_auth_token

    datos = _post_privado("payment_sources", cuerpo)

    publico = datos.get("public_data") or {}
    return {
        "id": datos.get("id"),
        "status": (datos.get("status") or "").upper(),
        # Para pintar "Visa ····4242". Los últimos cuatro dígitos y la marca no
        # son datos protegidos por PCI y son lo único que hace reconocible la
        # tarjeta para su dueño.
        "brand": publico.get("brand") or publico.get("card_brand"),
        "last_four": publico.get("last_four") or publico.get("last_4"),
    }


def cobrar_con_fuente_de_pago(
    *,
    payment_source_id: int,
    monto_centavos: int,
    referencia: str,
    email_cliente: str,
    acceptance_token: str,
    moneda: str = MONEDA,
    cuotas: int = 1,
    recurrente: bool = True,
) -> Dict[str, Any]:
    """Cobra a una tarjeta ya guardada. Es el cobro del mes.

    `recurrent=True` le dice a la franquicia que esto es un cobro periódico
    autorizado por el tarjetahabiente (COF, *credential on file*), por el mismo
    monto cada vez. Sin esa marca, los bancos rechazan cobros sin titular
    presente con mucha más frecuencia.

    La **firma de integridad es obligatoria** también acá, no solo en el Web
    Checkout, y se calcula igual: `<referencia><monto><moneda><secreto>`.

    Devuelve la transacción como la entrega Wompi (`id`, `status`, …). Suele
    volver en `PENDING`: el estado final lo confirma el webhook firmado, que es
    la única fuente de verdad. Quien llama NO debe dar el cobro por bueno
    porque esta llamada haya respondido 201.
    """
    cuerpo: Dict[str, Any] = {
        "amount_in_cents": int(monto_centavos),
        "currency": moneda,
        "customer_email": email_cliente,
        "reference": referencia,
        "payment_source_id": int(payment_source_id),
        "payment_method": {"installments": int(cuotas)},
        "recurrent": bool(recurrente),
        "acceptance_token": acceptance_token,
        "signature": firma_integridad(referencia, monto_centavos, moneda),
    }
    return _post_privado("transactions", cuerpo)


def consultar_transaccion(transaccion_id: str) -> Optional[Dict[str, Any]]:
    """Le pregunta a Wompi por una transacción. `None` si no se pudo saber.

    Es la verificación de segunda vuelta: el webhook ya viene firmado, pero
    preguntarle directamente a Wompi con la llave privada es lo que convierte
    "un POST que dice APPROVED" en "Wompi dice que está APPROVED". Se usa
    antes de acreditar en producción.

    Devuelve `None` (en vez de levantar) si la API no responde: quien llama
    decide si eso es motivo para no acreditar. El detalle del fallo va al log,
    nunca al cliente (regla 6), y el cuerpo de la respuesta NO se loggea
    porque trae datos del pagador.
    """
    import httpx

    private_key = _requerir("WOMPI_PRIVATE_KEY")
    url = f"{base_url().rstrip('/')}/transactions/{transaccion_id}"
    try:
        respuesta = httpx.get(
            url,
            headers={"Authorization": f"Bearer {private_key}"},
            timeout=10.0,
        )
        if respuesta.status_code != 200:
            logger.error(
                "wompi: consulta de transacción respondió %s", respuesta.status_code
            )
            return None
        return (respuesta.json() or {}).get("data")
    except Exception:
        # Sin `str(e)`: el mensaje de httpx puede traer la URL con credenciales.
        logger.exception("wompi: error consultando la transacción")
        return None
