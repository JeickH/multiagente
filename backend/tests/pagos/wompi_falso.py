"""Un Wompi de mentira que habla HTTP de verdad.

Levanta un servidor real en `localhost` y responde los cuatro endpoints que
usa la suscripción, con la misma forma que documenta Wompi y **las mismas
reglas del sandbox** (la 4242 aprueba, la 4111 rechaza, cualquier otra da
error).

Por qué un servidor y no `monkeypatch` sobre `wompi.crear_fuente_de_pago`:
parchear las funciones prueba la lógica de negocio pero salta justo la parte
donde históricamente se rompen estas integraciones — el cliente HTTP, los
headers de autenticación, el `data` envolviendo la respuesta, el manejo del
status code. Con esto, `WOMPI_BASE_URL` apunta acá y el código bajo prueba es
el mismo que corre en producción, `httpx` incluido.

Lo que este doble NO simula, para que nadie lo confunda con el sandbox real:
3D Secure, los métodos que no son tarjeta (Nequi, PSE), y la demora real entre
el `PENDING` y el evento del webhook. Para eso está
`scripts/probar_suscripcion_sandbox.py`, que corre contra el sandbox de Wompi.
"""
from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional

#: Reglas de la caja de arena de Wompi (doc: "Datos de prueba en Sandbox").
TARJETA_APROBADA = "4242424242424242"
TARJETA_RECHAZADA = "4111111111111111"

#: Los tokens de aceptación reales son JWT. Acá basta con que tengan la forma
#: y sean distintos entre sí, para que un test pueda verificar que se mandó
#: cada uno en su campo y no el mismo dos veces.
ACCEPTANCE_TOKEN = "eyJhbGciOiJIUzI1NiJ9.FALSO_END_USER_POLICY.firma"
PERSONAL_AUTH_TOKEN = "eyJhbGciOiJIUzI1NiJ9.FALSO_PERSONAL_DATA_AUTH.firma"


class EstadoWompiFalso:
    """La memoria del servidor: qué tokens, fuentes y transacciones existen.

    También es el panel de control del test: `fallar_en` fuerza un error en un
    endpoint concreto, y `estado_forzado` hace que la próxima transacción
    responda lo que el test necesite sin depender del número de tarjeta.
    """

    def __init__(self) -> None:
        self.tokens: Dict[str, str] = {}            # token → número de tarjeta
        self.fuentes: Dict[int, Dict[str, Any]] = {}
        self.transacciones: Dict[str, Dict[str, Any]] = {}
        #: Todo lo que recibió, para poder assertar sobre el request.
        self.peticiones: List[Dict[str, Any]] = []
        #: Ruta → status HTTP con el que debe fallar. Ej. `{"payment_sources": 422}`.
        self.fallar_en: Dict[str, int] = {}
        #: Fuerza el status de las transacciones nuevas ("APPROVED", "PENDING"…).
        self.estado_forzado: Optional[str] = None
        self._siguiente_id = 1000

    def nuevo_id(self) -> int:
        self._siguiente_id += 1
        return self._siguiente_id

    def peticiones_a(self, ruta: str) -> List[Dict[str, Any]]:
        """Los cuerpos que recibió una ruta, en orden."""
        return [p["cuerpo"] for p in self.peticiones if p["ruta"].endswith(ruta)]


def _estado_por_tarjeta(numero: str) -> str:
    if numero == TARJETA_APROBADA:
        return "APPROVED"
    if numero == TARJETA_RECHAZADA:
        return "DECLINED"
    return "ERROR"


class _Handler(BaseHTTPRequestHandler):
    estado: EstadoWompiFalso  # lo inyecta `servidor_wompi_falso`

    # Silencia el log a stderr: un test que pasa no tiene por qué escribir.
    def log_message(self, *args: Any) -> None:  # noqa: D102
        return

    # --- utilidades ------------------------------------------------------

    def _responder(self, codigo: int, cuerpo: Dict[str, Any]) -> None:
        crudo = json.dumps(cuerpo).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(crudo)))
        self.end_headers()
        self.wfile.write(crudo)

    def _error(self, codigo: int, tipo: str = "INPUT_VALIDATION_ERROR") -> None:
        self._responder(codigo, {"error": {"type": tipo, "reason": "falso"}})

    def _cuerpo(self) -> Dict[str, Any]:
        largo = int(self.headers.get("Content-Length") or 0)
        if not largo:
            return {}
        try:
            return json.loads(self.rfile.read(largo).decode("utf-8"))
        except Exception:
            return {}

    def _anotar(self, cuerpo: Dict[str, Any]) -> None:
        self.estado.peticiones.append(
            {
                "ruta": self.path,
                "metodo": self.command,
                "cuerpo": cuerpo,
                "auth": self.headers.get("Authorization"),
            }
        )

    def _forzado(self) -> Optional[int]:
        for fragmento, codigo in self.estado.fallar_en.items():
            if fragmento in self.path:
                return codigo
        return None

    # --- GET -------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 - lo exige BaseHTTPRequestHandler
        self._anotar({})
        forzado = self._forzado()
        if forzado:
            return self._error(forzado)

        if "/merchants" in self.path:
            # La llave pública llega por header (ruta nueva) o en la URL
            # (ruta clásica). El servicio prueba las dos; acá se aceptan ambas.
            por_header = self.headers.get("X-Merchant-Public-Key")
            por_url = self.path.rstrip("/").rsplit("/", 1)[-1]
            if not por_header and not por_url.startswith("pub_"):
                return self._error(400)
            return self._responder(
                200,
                {
                    "data": {
                        "presigned_acceptance": {
                            "acceptance_token": ACCEPTANCE_TOKEN,
                            "permalink": "https://wompi.co/terminos-falsos.pdf",
                            "type": "END_USER_POLICY",
                        },
                        "presigned_personal_data_auth": {
                            "acceptance_token": PERSONAL_AUTH_TOKEN,
                            "permalink": "https://wompi.co/datos-falsos.pdf",
                            "type": "PERSONAL_DATA_AUTH",
                        },
                    }
                },
            )

        m = re.search(r"/transactions/([^/?]+)", self.path)
        if m:
            tx = self.estado.transacciones.get(m.group(1))
            if not tx:
                return self._error(404, "NOT_FOUND_ERROR")
            return self._responder(200, {"data": tx})

        self._error(404, "NOT_FOUND_ERROR")

    # --- POST ------------------------------------------------------------

    def do_POST(self) -> None:  # noqa: N802
        cuerpo = self._cuerpo()
        self._anotar(cuerpo)

        forzado = self._forzado()
        if forzado:
            return self._error(forzado)

        if self.path.endswith("/tokens/cards"):
            return self._tokenizar(cuerpo)
        if self.path.endswith("/payment_sources"):
            return self._crear_fuente(cuerpo)
        if self.path.endswith("/transactions"):
            return self._cobrar(cuerpo)

        self._error(404, "NOT_FOUND_ERROR")

    def _tokenizar(self, cuerpo: Dict[str, Any]) -> None:
        """`POST /tokens/cards` — lo llama el navegador con la llave PÚBLICA."""
        auth = self.headers.get("Authorization") or ""
        if "pub_" not in auth:
            # Tokenizar con la llave privada es un error de integración, no un
            # detalle: si pasa, es que el secreto se filtró al frontend.
            return self._error(401, "INVALID_ACCESS_TOKEN")

        numero = str(cuerpo.get("number") or "")
        if not numero or not cuerpo.get("cvc"):
            return self._error(422)

        token = f"tok_test_{self.estado.nuevo_id()}_falso"
        self.estado.tokens[token] = numero
        self._responder(
            201,
            {
                "status": "CREATED",
                "data": {
                    "id": token,
                    "brand": "VISA",
                    "last_four": numero[-4:],
                    "name": f"VISA-{numero[-4:]}",
                },
            },
        )

    def _crear_fuente(self, cuerpo: Dict[str, Any]) -> None:
        """`POST /payment_sources` — server-to-server con la llave PRIVADA."""
        auth = self.headers.get("Authorization") or ""
        if "prv_" not in auth:
            return self._error(401, "INVALID_ACCESS_TOKEN")

        token = str(cuerpo.get("token") or "")
        numero = self.estado.tokens.get(token)
        if numero is None:
            return self._error(422)
        if not cuerpo.get("acceptance_token"):
            # Wompi no guarda una tarjeta sin el consentimiento de habeas data.
            return self._error(422)

        fuente_id = self.estado.nuevo_id()
        self.estado.fuentes[fuente_id] = {"numero": numero}
        self._responder(
            201,
            {
                "data": {
                    "id": fuente_id,
                    "type": "CARD",
                    "status": "AVAILABLE",
                    "public_data": {"brand": "VISA", "last_four": numero[-4:]},
                }
            },
        )

    def _cobrar(self, cuerpo: Dict[str, Any]) -> None:
        """`POST /transactions` — el cobro contra una fuente guardada."""
        auth = self.headers.get("Authorization") or ""
        if "prv_" not in auth:
            return self._error(401, "INVALID_ACCESS_TOKEN")

        # Wompi exige la firma de integridad también por API, no solo en el
        # Web Checkout. Sin ella, rechaza.
        if not cuerpo.get("signature"):
            return self._error(422)

        fuente = self.estado.fuentes.get(int(cuerpo.get("payment_source_id") or 0))
        if fuente is None:
            return self._error(422)

        estado = self.estado.estado_forzado or _estado_por_tarjeta(fuente["numero"])
        tx_id = f"{self.estado.nuevo_id()}-1600000000-00000"
        transaccion = {
            "id": tx_id,
            "status": estado,
            "reference": cuerpo.get("reference"),
            "amount_in_cents": cuerpo.get("amount_in_cents"),
            "currency": cuerpo.get("currency"),
            "customer_email": cuerpo.get("customer_email"),
            "payment_method_type": "CARD",
        }
        self.estado.transacciones[tx_id] = transaccion
        self._responder(201, {"data": transaccion})


class ServidorWompiFalso:
    """Context manager: levanta el servidor y devuelve su URL base."""

    def __init__(self) -> None:
        self.estado = EstadoWompiFalso()
        self._servidor: Optional[ThreadingHTTPServer] = None
        self._hilo: Optional[threading.Thread] = None

    def __enter__(self) -> "ServidorWompiFalso":
        handler = type("HandlerConEstado", (_Handler,), {"estado": self.estado})
        # Puerto 0 = que el sistema operativo elija uno libre. Con un puerto
        # fijo, dos corridas en paralelo (o un test anterior que no cerró) se
        # pisan y el fallo aparece en un test que no tiene nada que ver.
        self._servidor = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._hilo = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._hilo.start()
        return self

    def __exit__(self, *_: Any) -> None:
        if self._servidor is not None:
            self._servidor.shutdown()
            self._servidor.server_close()
        if self._hilo is not None:
            self._hilo.join(timeout=5)

    @property
    def base_url(self) -> str:
        assert self._servidor is not None
        host, puerto = self._servidor.server_address[:2]
        return f"http://{host}:{puerto}/v1"
