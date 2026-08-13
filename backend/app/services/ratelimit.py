"""Rate-limit en memoria del proceso (ventana deslizante de 1 hora).

Protege los endpoints PÚBLICOS (sin auth) del backend: el chat del bot de la
landing y el de mascotas perdidas, donde cada turno cuesta una llamada a
Bedrock. El backend corre como una sola task ECS; si algún día escala
horizontalmente esto pasa a ser un límite por task — más permisivo, nunca menos
seguro que no tener nada. Se complementa con topes que sí viajan firmados
dentro del token de sesión (turnos por conversación).
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Tuple

_VENTANA_SEGUNDOS = 3600
_MAX_IPS_RASTREADAS = 5000


class SlidingWindow:
    """Contador por clave (IP) + techo global, ambos por hora."""

    def __init__(self, por_ip: int, global_: int) -> None:
        self._por_ip = por_ip
        self._global = global_
        self._por_clave: Dict[str, Deque[float]] = {}
        self._todos: Deque[float] = deque()
        self._lock = Lock()

    def allow(self, clave: str) -> bool:
        """Registra un intento. False si la clave o el proceso ya llegaron al tope."""
        ahora = time.monotonic()
        corte = ahora - _VENTANA_SEGUNDOS
        with self._lock:
            while self._todos and self._todos[0] < corte:
                self._todos.popleft()
            bucket = self._por_clave.setdefault(clave, deque())
            while bucket and bucket[0] < corte:
                bucket.popleft()
            if not bucket and len(self._por_clave) > _MAX_IPS_RASTREADAS:
                # Higiene del diccionario: purga claves sin actividad reciente.
                for k in [k for k, v in self._por_clave.items() if not v]:
                    self._por_clave.pop(k, None)
                bucket = self._por_clave.setdefault(clave, deque())
            if len(bucket) >= self._por_ip or len(self._todos) >= self._global:
                return False
            bucket.append(ahora)
            self._todos.append(ahora)
            return True

    def stats(self) -> Tuple[int, int]:
        """(claves rastreadas, intentos en la ventana). Para diagnóstico."""
        with self._lock:
            return len(self._por_clave), len(self._todos)


def client_ip(request) -> str:
    """IP del visitante. Detrás de API Gateway la real viene en X-Forwarded-For."""
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        return xff.split(",")[0].strip()[:60]
    return (request.client.host if request.client else "unknown")[:60]
