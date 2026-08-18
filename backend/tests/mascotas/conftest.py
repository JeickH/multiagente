"""Fixtures del módulo Recupera Tu Mascota (mascotasperdidascolombia.com).

Todo corre contra **SQLite en memoria**: la suite no necesita Postgres, ni
Docker, ni red — condición para que el CI la corra en cada push sin costo.

Tres cosas que hay que saber para escribir un test aquí:

- **El storage es un directorio temporal.** Sin `MASCOTAS_BUCKET`, el servicio
  escribe las fotos en disco (`_LOCAL_MEDIA_ROOT`). La fixture `medios` lo
  apunta a un `tmp_path` y borra la variable de entorno, así que ningún test
  puede tocar el bucket real por accidente.
- **El motor abre su propia sesión.** `llm_engine._mascotas_db()` no recibe la
  del request (contrato `advance(bot, state, input)`), así que la fixture
  `motor_conectado` lo apunta al engine del test. Sin eso, las tools irían a
  buscar Postgres.
- **Nunca se llama a Bedrock.** `_invoke_model` se parchea con `respuestas()`.
  Lo que sí llama al modelo vive en `tests/mascotas/costo/` y lleva la marca
  `costo`.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    """SQLite en memoria compartida por todas las sesiones del test.

    `StaticPool` + una sola conexión es lo que hace que la sesión del request y
    la que abre el motor por su cuenta vean la MISMA base: con el pool normal,
    cada sesión estrenaría una base vacía y las tools no encontrarían nada.
    """
    from app.database import Base

    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def Sesion(engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(Sesion):
    sesion = Sesion()
    yield sesion
    sesion.close()


@pytest.fixture(autouse=True)
def medios(tmp_path, monkeypatch):
    """Storage de fotos en un temporal. Autouse: ningún test toca S3."""
    from app.services import mascotas as svc

    monkeypatch.delenv("MASCOTAS_BUCKET", raising=False)
    monkeypatch.delenv("MASCOTAS_PUBLIC_BASE", raising=False)
    raiz = tmp_path / "media"
    raiz.mkdir()
    monkeypatch.setattr(svc, "_LOCAL_MEDIA_ROOT", raiz)
    return raiz


@pytest.fixture(autouse=True)
def motor_conectado(Sesion, monkeypatch):
    """Las tools del bot abren su sesión contra la base del test."""
    from app.services import llm_engine

    monkeypatch.setattr(llm_engine, "_mascotas_db", Sesion)


@pytest.fixture(autouse=True)
def cifrado_estable(monkeypatch):
    """Una clave de cifrado coherente durante todo el test.

    `crypto._get_fernet()` está cacheado con `lru_cache` y su docstring avisa
    que si la env var cambia en runtime hay que reiniciar el proceso. En la
    suite sí cambia: `test_crypto` y `test_meta_account_flow` la reemplazan y
    recargan el módulo. Sin esto, un token que el bot cifra (`descargar_listado`)
    y que el test descifra podían quedar con claves distintas — y el fallo solo
    aparecía al correr la suite entera, nunca el archivo suelto.

    `test_crypto` además **recarga** el módulo: los que hicieron
    `from ..services.crypto import encrypt_secret` se quedan apuntando a la
    copia vieja, con su propio `lru_cache` y su propia clave. Por eso no alcanza
    con limpiar el caché del módulo actual — hay que limpiarlo en cada copia
    viva, y a esas se llega por los `__globals__` de las funciones ya enlazadas.
    """
    from cryptography.fernet import Fernet

    from app.routers import mascotas as router_mascotas
    from app.services import crypto, llm_engine

    monkeypatch.setenv("APP_ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.delenv("APP_ENCRYPTION_KEY_OLD", raising=False)

    def _limpiar_todas():
        vistos = set()
        for fn in (
            crypto.encrypt_secret,
            llm_engine.encrypt_secret,
            router_mascotas.encrypt_secret,
            router_mascotas.decrypt_secret,
        ):
            constructor = fn.__globals__.get("_get_fernet")
            if constructor is not None and id(constructor) not in vistos:
                vistos.add(id(constructor))
                constructor.cache_clear()

    _limpiar_todas()
    yield
    _limpiar_todas()


@pytest.fixture(autouse=True)
def canal_limpio():
    """Los límites y las pausas del chat viven en el proceso, no en la base.

    Sin esto, el test que provoca una pausa por «fuera de alcance» se la deja
    puesta al siguiente y el chat le responde con el aviso en vez de atenderlo.
    """
    from app.routers import mascotas as router

    router._pausas.clear()
    router._chat_limiter._por_clave.clear()
    router._chat_limiter._todos.clear()
    router._foto_limiter._por_clave.clear()
    router._foto_limiter._todos.clear()
    yield
    router._pausas.clear()


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

# Un reporte mínimo válido. Los tests cambian solo lo que están probando, para
# que el motivo de cada caso se lea en el diff de sus kwargs.
_BASE = {
    "tipo_registro": "encontrada",
    "especie": "perro",
    "ubicacion": "Barrio San Fernando, Cali",
    "contacto_telefono": "3001234567",
}


@pytest.fixture
def crear(db):
    """Crea un reporte por la vía real (`svc.crear_reporte`) y lo devuelve.

    Se usa el servicio y no un `models.Mascota(...)` a pelo para que los tests
    hereden la normalización de verdad (especie, sexo, códigos `MC-000NN`).
    """
    from app.services import mascotas as svc

    def _crear(**campos: Any):
        datos = {**_BASE, **campos}
        source = datos.pop("source", "web")
        mascota, problema = svc.crear_reporte(db, datos, source=source)
        assert mascota is not None, f"la fixture no pudo crear el reporte: {problema}"
        return mascota

    return _crear


@pytest.fixture
def usuaria_iniciativa(db):
    """La cuenta `recuperatumascota@gmail.com`, creada una sola vez.

    Varias fixtures la necesitan (el bot del chat, el portero del panel) y el
    correo es único: si cada una insertara la suya, combinarlas reventaría.
    """
    from app import models
    from app.dependencies import MASCOTAS_EMAIL

    existente = (
        db.query(models.User).filter(models.User.correo == MASCOTAS_EMAIL).first()
    )
    if existente is not None:
        return existente
    user = models.User(
        nombre="Recupera Tu Mascota",
        tipo_documento="CC",
        documento="900000000",
        correo=MASCOTAS_EMAIL,
        hashed_password="x",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def cuenta_mascotas(db, usuaria_iniciativa):
    """El bot LLM activo de la iniciativa.

    `routers.mascotas._bot()` busca exactamente esto: el bot `llm` activo del
    usuario cuyo correo es `MASCOTAS_EMAIL`. Sin esta fila, el chat responde
    "no puedo atenderte" y cualquier test del endpoint sería un falso verde.
    """
    from app import models

    bot = models.Bot(
        user_id=usuaria_iniciativa.id,
        name="Huella",
        status="active",
        engine="llm",
        llm_config=json.dumps({"context_key": "mascotas_cali", "mascotas": {}}),
    )
    db.add(bot)
    db.commit()
    db.refresh(bot)
    return bot


# ---------------------------------------------------------------------------
# Doble del modelo
# ---------------------------------------------------------------------------

class BotFalso:
    """Bot de mascotas sin base de datos, para los tests del motor."""

    id = 42
    engine = "llm"

    def __init__(self, **extra: Any) -> None:
        cfg: Dict[str, Any] = {"context_key": "mascotas_cali", "mascotas": {}}
        cfg.update(extra)
        self.llm_config = json.dumps(cfg)


def texto(mensaje: str, stop_reason: str = "end_turn") -> Dict[str, Any]:
    """Una respuesta del modelo que solo dice algo."""
    return {"content": [{"type": "text", "text": mensaje}], "stop_reason": stop_reason}


def usa_tool(
    nombre: str,
    entrada: Optional[Dict[str, Any]] = None,
    dice: str = "",
    tool_id: str = "t1",
) -> Dict[str, Any]:
    """Una respuesta del modelo que llama una herramienta (y quizá habla)."""
    contenido: List[Dict[str, Any]] = []
    if dice:
        contenido.append({"type": "text", "text": dice})
    contenido.append(
        {"type": "tool_use", "id": tool_id, "name": nombre, "input": entrada or {}}
    )
    return {"content": contenido, "stop_reason": "tool_use"}


@pytest.fixture
def respuestas(monkeypatch):
    """Guioniza al modelo: `respuestas(usa_tool(...), texto(...))`.

    Devuelve el mock, así el test puede afirmar sobre lo que se le mandó a
    Bedrock (cuántas rondas, qué llevaba el system prompt, qué tool_result vio).
    """
    from unittest.mock import MagicMock

    from app.services import llm_engine

    def _guion(*turnos: Dict[str, Any]) -> MagicMock:
        mock = MagicMock(side_effect=list(turnos))
        monkeypatch.setattr(llm_engine, "_invoke_model", mock)
        return mock

    return _guion


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@pytest.fixture
def cliente(Sesion):
    """TestClient sobre el router de mascotas, con la base del test en `get_db`.

    Se monta el router en una app propia en vez de importar `app.main`: ese
    módulo hace `Base.metadata.create_all(bind=engine)` **al importarse**, o sea
    que exigiría un Postgres vivo solo para levantar el cliente. Lo que se
    prueba aquí son las rutas de `/mascotas`, que es exactamente lo que se monta.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_db
    from app.routers import mascotas as router_mascotas

    app = FastAPI()
    app.include_router(router_mascotas.router)

    def _get_db():
        sesion = Sesion()
        try:
            yield sesion
        finally:
            sesion.close()

    app.dependency_overrides[get_db] = _get_db
    with TestClient(app) as c:
        yield c
