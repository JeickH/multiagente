"""Sprint "Ayuda a Cali": bot público de mascotas perdidas + panel privado.

Iniciativa solidaria para reunir mascotas con sus familias tras el terremoto en
Colombia. Vive en `mascotasperdidascali.glomabeauty.com` y tiene dos caras:

PÚBLICA (sin auth) — la usa cualquier ciudadano desde el chat web:
  - `POST /mascotas/chat`            un turno con el bot (mismo motor LLM que
                                     el resto de bots de la plataforma).
  - `POST /mascotas/foto`            adjuntar una foto durante la conversación.
  - `GET  /mascotas/foto/{codigo}/{id}`  servir una foto (el bucket es privado;
                                     el backend hace de proxy).
  - `GET  /mascotas/listado.xlsx`    descarga del listado (token firmado).

PRIVADA (JWT, solo la cuenta de la iniciativa):
  - `GET   /mascotas/access`         ¿esta sesión ve el módulo? (menú).
  - `GET   /mascotas/panel`          tablero: contadores + tabla completa.
  - `PATCH /mascotas/panel/{codigo}` marcar un caso como reunido o cerrado.
  - `GET   /mascotas/panel/export.xlsx`  el mismo Excel, ya autenticado.

Privacidad: el teléfono de quien reportó NO viaja en ninguna respuesta pública.
El bot solo lo entrega dentro de la conversación, con `entregar_contacto`, y
únicamente cuando la persona confirma que reconoce a la mascota.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime
from threading import Lock, Thread
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from .. import models
from ..dependencies import (
    MASCOTAS_EMAIL,
    get_current_user,
    get_db,
    require_mascotas_account,
)
from ..services import llm_engine, mascotas as svc, ratelimit
from ..services.crypto import CryptoError, decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mascotas", tags=["mascotas"])


# ---------------------------------------------------------------------------
# Límites del canal público
# ---------------------------------------------------------------------------

_MAX_MESSAGE_CHARS = 700       # lo que puede escribir el ciudadano por turno
_MAX_TURNS_PER_SESSION = 60    # un reporte completo toma bastantes turnos
_SESSION_TTL_SECONDS = 6 * 3600
_LISTADO_TTL_SECONDS = 24 * 3600

_chat_limiter = ratelimit.SlidingWindow(por_ip=80, global_=800)
_foto_limiter = ratelimit.SlidingWindow(por_ip=40, global_=400)

_TEXTO_SIN_BOT = (
    "En este momento no puedo atenderte por aquí 🙏 Vuelve a intentarlo en "
    "unos minutos, por favor."
)
_TEXTO_LIMITE = (
    "Hemos conversado bastante 🐾 Tu información ya quedó guardada. Si necesitas "
    "seguir, recarga la página para empezar un chat nuevo."
)
_TEXTO_OCUPADO = (
    "Estamos atendiendo muchas conversaciones en este momento 🙏 Intenta de "
    "nuevo en unos minutos."
)
_TEXTO_EN_PAUSA = (
    "Este chat está en pausa por unos minutos 🐾 Aquí solo ayudamos a *buscar* "
    "una mascota perdida, a *reportar* una que encontraste y a *descargar* el "
    "listado. Si necesitas alguna de esas tres, vuelve a escribirnos en un rato "
    "y con gusto te ayudamos 🤍"
)

# Canales en pausa tras un cierre por fuera de alcance: clave → momento en que
# vuelve a atenderse. Hoy la clave es la IP del chat web; cuando el bot se
# conecte a WhatsApp será el número. En memoria del proceso, igual que el
# rate-limit: si el backend reinicia, la pausa se levanta — es una molestia
# menor comparada con dejar a alguien sin atención por un estado persistido mal.
_pausas: Dict[str, float] = {}
_pausas_lock = Lock()


def _en_pausa(clave: str) -> bool:
    ahora = time.monotonic()
    with _pausas_lock:
        hasta = _pausas.get(clave)
        if hasta is None:
            return False
        if hasta <= ahora:
            _pausas.pop(clave, None)
            return False
        return True


def _pausar(clave: str, minutos: int) -> None:
    with _pausas_lock:
        if len(_pausas) > 5000:   # higiene: purga las pausas ya vencidas
            ahora = time.monotonic()
            for k in [k for k, v in _pausas.items() if v <= ahora]:
                _pausas.pop(k, None)
        _pausas[clave] = time.monotonic() + minutos * 60
    logger.info("mascotas: canal en pausa %s minutos", minutos)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ChatIn(BaseModel):
    """Turno del ciudadano. `session` es el token devuelto por el turno previo."""

    session: Optional[str] = Field(default=None, max_length=40000)
    message: Optional[str] = Field(default=None, max_length=_MAX_MESSAGE_CHARS)

    @field_validator("message")
    @classmethod
    def _clean_message(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v).strip()
        return v[:_MAX_MESSAGE_CHARS] or None


class ChatAction(BaseModel):
    type: str                        # say | say_media | say_file
    text: str = ""
    url: Optional[str] = None
    media_type: Optional[str] = None
    filename: Optional[str] = None
    label: Optional[str] = None


class ChatOut(BaseModel):
    actions: List[ChatAction]
    session: Optional[str] = None    # None cuando la conversación terminó
    finished: bool = False
    reporte_codigo: Optional[str] = None   # el chat lo muestra como confirmación


class FotoOut(BaseModel):
    ok: bool = True
    session: Optional[str] = None
    fotos: int = 0


class FotoPanelOut(BaseModel):
    """Una foto del reporte, con dónde quedó guardada.

    `storage_key` es la ruta real dentro del bucket (o del disco local en
    desarrollo): `mascotas/<codigo>/<archivo>`. El panel la muestra para que el
    equipo sepa exactamente dónde vive cada recurso.
    """

    id: int
    url: str
    storage_key: str
    storage_uri: str          # s3://bucket/clave, o file://... en local
    content_type: str
    bytes_size: Optional[int] = None


class MascotaPanelOut(BaseModel):
    """Fila del panel privado. Incluye PII: solo la ve la cuenta de la iniciativa."""

    id: int
    codigo: str
    tipo_registro: str
    especie: str
    especie_otra: Optional[str] = None
    raza: Optional[str] = None
    color: Optional[str] = None
    nombre: Optional[str] = None
    sexo: Optional[str] = None
    edad: Optional[str] = None
    tamano: Optional[str] = None
    senas: Optional[str] = None
    ubicacion: str
    maps_url: Optional[str] = None
    barrio: Optional[str] = None
    contacto_nombre: Optional[str] = None
    contacto_telefono: Optional[str] = None   # NULL en los reportes importados
    origen_url: Optional[str] = None
    origen_nombre: Optional[str] = None
    fecha_evento: Optional[str] = None
    estado: str
    notas: Optional[str] = None
    source: str
    created_at: datetime
    fotos: List[FotoPanelOut] = []


class ResumenOut(BaseModel):
    total: int
    perdidas: int
    encontradas: int
    activas: int
    reunidas: int
    cerradas: int
    fotos: int
    por_especie: Dict[str, int] = {}


class CoincidenciaOut(BaseModel):
    """Par candidato que detectó el cruce diario de las 12:00."""

    id: int
    score: int
    estado: str
    detalle: Dict[str, int] = {}
    notas: Optional[str] = None
    created_at: datetime
    perdida: MascotaPanelOut
    encontrada: MascotaPanelOut


class PanelOut(BaseModel):
    resumen: ResumenOut
    reportes: List[MascotaPanelOut]
    coincidencias: List[CoincidenciaOut] = []
    coincidencias_nuevas: int = 0


class CoincidenciaUpdate(BaseModel):
    estado: Optional[str] = Field(default=None, max_length=16)
    notas: Optional[str] = Field(default=None, max_length=2000)


class PanelUpdate(BaseModel):
    """Edición manual de un reporte. Todos los campos son opcionales (PATCH
    parcial); solo se toca lo que venga en el cuerpo.

    `ubicacion` y `contacto_telefono` se pueden **corregir pero no vaciar**: el
    servicio rechaza el cambio si llegan en blanco. Un reporte sin dónde ni a
    quién llamar no sirve para reunir a nadie.
    """

    tipo_registro: Optional[str] = Field(default=None, max_length=16)
    especie: Optional[str] = Field(default=None, max_length=24)
    especie_otra: Optional[str] = Field(default=None, max_length=60)
    raza: Optional[str] = Field(default=None, max_length=80)
    color: Optional[str] = Field(default=None, max_length=80)
    nombre: Optional[str] = Field(default=None, max_length=80)
    sexo: Optional[str] = Field(default=None, max_length=16)
    edad: Optional[str] = Field(default=None, max_length=40)
    tamano: Optional[str] = Field(default=None, max_length=24)
    senas: Optional[str] = Field(default=None, max_length=2000)
    ubicacion: Optional[str] = Field(default=None, max_length=255)
    maps_url: Optional[str] = Field(default=None, max_length=500)
    barrio: Optional[str] = Field(default=None, max_length=120)
    contacto_nombre: Optional[str] = Field(default=None, max_length=120)
    contacto_telefono: Optional[str] = Field(default=None, max_length=32)
    fecha_evento: Optional[str] = Field(default=None, max_length=10)
    estado: Optional[str] = Field(default=None, max_length=24)
    notas: Optional[str] = Field(default=None, max_length=2000)


class BorradoOut(BaseModel):
    ok: bool = True
    eliminados: int = 1


class AccesoOut(BaseModel):
    allowed: bool


# ---------------------------------------------------------------------------
# Sesión cifrada del chat
# ---------------------------------------------------------------------------

def _load_session(token: Optional[str]) -> Dict[str, Any]:
    """Descifra el estado del cliente. Token inválido/vencido → sesión nueva.

    El historial y el `upload_session` NUNCA los controla el visitante: viajan
    cifrados con Fernet (AEAD), así que no puede inyectar turnos falsos ni
    adueñarse de las fotos de otra conversación.
    """
    nueva = {"history": [], "turns": 0, "upload": uuid.uuid4().hex, "codigo": None}
    if not token:
        return nueva
    try:
        data = json.loads(decrypt_secret(token, ttl_seconds=_SESSION_TTL_SECONDS))
    except (CryptoError, ValueError, TypeError):
        return nueva
    if not isinstance(data, dict):
        return nueva
    history = data.get("h")
    return {
        "history": history if isinstance(history, list) else [],
        "turns": int(data.get("n") or 0),
        "upload": str(data.get("u") or "") or nueva["upload"],
        "codigo": data.get("c") or None,
    }


def _dump_session(sess: Dict[str, Any], history: List[Dict[str, str]]) -> str:
    return encrypt_secret(json.dumps(
        {
            "h": history,
            "n": sess["turns"] + 1,
            "u": sess["upload"],
            "c": sess.get("codigo"),
        },
        ensure_ascii=False,
    ))


def _bot(db: Session) -> Optional[models.Bot]:
    """El bot LLM activo de la cuenta de la iniciativa."""
    owner = (
        db.query(models.User)
        .filter(models.User.correo == MASCOTAS_EMAIL)
        .first()
    )
    if owner is None:
        return None
    return (
        db.query(models.Bot)
        .filter(
            models.Bot.user_id == owner.id,
            models.Bot.engine == "llm",
            models.Bot.status == "active",
        )
        .order_by(models.Bot.id.desc())
        .first()
    )


def _solo_texto(texto: str) -> ChatOut:
    return ChatOut(
        actions=[ChatAction(type="say", text=texto)], session=None, finished=True
    )


def _url_web(url: Optional[str]) -> Optional[str]:
    """El motor emite rutas del backend (`/mascotas/foto/...`); el frontend las
    consume por el rewrite `/api/*` de Next."""
    if not url:
        return url
    if url.startswith("/"):
        return f"/api{url}"
    return url


# ---------------------------------------------------------------------------
# Chat público
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn, request: Request, db: Session = Depends(get_db)):
    """Un turno de conversación con el bot de mascotas perdidas. Público.

    Mismo motor (`services/llm_engine`) que los demás bots de la plataforma: el
    día que este bot se conecte a un WhatsApp Business, atiende igual sin
    cambiar nada aquí. El ciudadano es anónimo — no se crea usuario ni
    conversación; el estado va cifrado en `session`.
    """
    bot = _bot(db)
    if bot is None:
        logger.error("mascotas chat: no hay bot activo para %s", MASCOTAS_EMAIL)
        return _solo_texto(_TEXTO_SIN_BOT)

    canal = ratelimit.client_ip(request)
    if _en_pausa(canal):
        # Cierre por fuera de alcance todavía vigente: no se gasta una llamada
        # al modelo, se responde con el recordatorio de los tres casos de uso.
        return _solo_texto(_TEXTO_EN_PAUSA)

    if not _chat_limiter.allow(canal):
        logger.warning("mascotas chat: rate-limit alcanzado")
        return _solo_texto(_TEXTO_OCUPADO)

    sess = _load_session(payload.session)
    if sess["turns"] >= _MAX_TURNS_PER_SESSION:
        return _solo_texto(_TEXTO_LIMITE)

    runtime: Dict[str, Any] = {
        "bot_id": bot.id,
        "source": "web",
        "upload_session": sess["upload"],
        "fotos_pendientes": svc.contar_fotos_pendientes(db, sess["upload"]),
        "reporte_codigo": sess.get("codigo"),
    }
    result = llm_engine.advance(
        bot,
        {"history": sess["history"]} if sess["history"] else None,
        payload.message,
        runtime=runtime,
    )
    llm_engine.record_decision(db, bot, result.get("telemetry"), source="mascotas")

    # `runtime` es de ida y vuelta: el motor deja ahí los reportes que creó.
    creados = runtime.get("reportes_creados") or []
    if creados:
        sess["codigo"] = creados[-1]

    actions: List[ChatAction] = []
    for act in result.get("actions") or []:
        kind = act.get("type")
        data = act.get("payload") or {}
        if kind == "say":
            texto = (data.get("text") or "").strip()
            if texto:
                actions.append(ChatAction(type="say", text=texto))
        elif kind == "say_media":
            actions.append(ChatAction(
                type="say_media",
                text=data.get("caption") or "",
                url=_url_web(data.get("url")),
                media_type=data.get("media_type") or "image",
            ))
        elif kind == "say_file":
            actions.append(ChatAction(
                type="say_file",
                text="",
                url=_url_web(data.get("url")),
                filename=data.get("filename") or "listado.xlsx",
                label=data.get("label") or "Descargar listado",
            ))
        elif kind == "end":
            # El bot cerró por fuera de alcance: el canal queda en pausa.
            minutos = int(data.get("cooldown_minutos") or 0)
            if minutos > 0:
                _pausar(canal, minutos)
        elif kind == "handoff":
            # Esta iniciativa no tiene bandeja humana: el bot registra el caso
            # y alguien de la fundación lo revisa desde el panel.
            actions.append(ChatAction(
                type="say",
                text=(
                    "Voy a dejar tu caso registrado para que una persona del "
                    "equipo lo revise 🤍"
                ),
            ))

    finished = bool(result.get("finished"))
    next_state = result.get("next_state") or {}
    history = next_state.get("history") if isinstance(next_state, dict) else None
    return ChatOut(
        actions=actions or [ChatAction(type="say", text=_TEXTO_SIN_BOT)],
        session=None if finished or not history else _dump_session(sess, history),
        finished=finished,
        reporte_codigo=sess.get("codigo"),
    )


@router.post("/foto", response_model=FotoOut)
async def subir_foto(
    request: Request,
    file: UploadFile = File(...),
    session: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
):
    """Adjunta una foto a la conversación en curso. Público.

    La foto se guarda contra el `upload_session` cifrado dentro de `session` y
    se mueve sola a la carpeta del reporte cuando el bot lo registra. Si el
    reporte YA existe en esta conversación, se asocia de una vez.
    """
    if not _foto_limiter.allow(ratelimit.client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Has enviado muchas fotos seguidas. Intenta en unos minutos.",
        )

    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in svc.ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo podemos recibir fotos (JPG, PNG, WEBP o HEIC).",
        )

    data = await file.read(svc.MAX_PHOTO_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="La foto llegó vacía.")
    if len(data) > svc.MAX_PHOTO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="La foto pesa demasiado. Envía una de menos de 8 MB.",
        )

    sess = _load_session(session)
    mascota = svc.obtener(db, sess["codigo"]) if sess.get("codigo") else None
    if mascota is not None and len(mascota.fotos or []) >= svc.MAX_FOTOS_POR_REPORTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya recibimos suficientes fotos de este reporte. ¡Gracias!",
        )
    if mascota is None and svc.contar_fotos_pendientes(db, sess["upload"]) >= svc.MAX_FOTOS_POR_REPORTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya recibimos suficientes fotos por ahora. ¡Gracias!",
        )

    try:
        svc.guardar_foto(
            db, data, content_type,
            upload_session=sess["upload"],
            mascota=mascota,
        )
    except Exception:
        # Detalle solo server-side (regla de seguridad #6).
        logger.exception("mascotas: no se pudo guardar la foto")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No pudimos guardar la foto. Intenta de nuevo, por favor.",
        )

    total = (
        len(mascota.fotos or []) if mascota is not None
        else svc.contar_fotos_pendientes(db, sess["upload"])
    )
    # El token de sesión no cambia con una foto; se devuelve el mismo para que
    # el cliente no tenga que rastrear dos estados.
    return FotoOut(ok=True, session=session, fotos=total)


@router.get("/foto/{codigo}/{foto_id}")
def ver_foto(codigo: str, foto_id: int, db: Session = Depends(get_db)):
    """Sirve una foto de un reporte. Público (el bucket de S3 sigue privado).

    Solo entrega la imagen: ni el nombre del archivo ni la respuesta revelan
    datos de contacto.
    """
    encontrada = svc.leer_foto(db, (codigo or "").strip().upper(), foto_id)
    if encontrada is None:
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    data, content_type = encontrada
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/listado.xlsx")
def descargar_listado(token: str, db: Session = Depends(get_db)):
    """Descarga del listado en Excel. Público, con token firmado por nosotros.

    El token lo emite la herramienta `descargar_listado` del bot dentro de una
    conversación; no es adivinable y caduca a las 24 horas.
    """
    try:
        data = json.loads(decrypt_secret(token, ttl_seconds=_LISTADO_TTL_SECONDS))
    except (CryptoError, ValueError, TypeError):
        raise HTTPException(status_code=403, detail="El enlace de descarga expiró")
    if not isinstance(data, dict) or data.get("exp") != "listado":
        raise HTTPException(status_code=403, detail="Enlace inválido")

    # El listado público es el de las mascotas ENCONTRADAS (el token lo trae,
    # pero se fija aquí también: es la lista útil para quien busca a la suya, y
    # los reportes de familias buscando no se reparten en un archivo).
    tipo = data.get("t") or models.MASCOTA_TIPO_ENCONTRADA
    contenido = svc.exportar_excel(db, tipo=tipo)
    hoy = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="mascotas_encontradas_{hoy}.xlsx"',
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------------------
# Panel privado (solo la cuenta de la iniciativa)
# ---------------------------------------------------------------------------

@router.get("/access", response_model=AccesoOut)
def check_access(
    user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """¿Esta sesión puede usar el módulo? Lo consulta el menú del frontend para
    mostrar la pestaña solo en la cuenta donde funciona. Responde 200 siempre."""
    try:
        require_mascotas_account(user=user, db=db)
    except HTTPException:
        return AccesoOut(allowed=False)
    return AccesoOut(allowed=True)


def _fila_panel(m: models.Mascota) -> MascotaPanelOut:
    return MascotaPanelOut(
        id=m.id,
        codigo=m.codigo,
        tipo_registro=m.tipo_registro,
        especie=m.especie,
        especie_otra=m.especie_otra,
        raza=m.raza,
        color=m.color,
        nombre=m.nombre,
        sexo=m.sexo,
        edad=m.edad,
        tamano=m.tamano,
        senas=m.senas,
        ubicacion=m.ubicacion,
        maps_url=m.maps_url,
        barrio=m.barrio,
        contacto_nombre=m.contacto_nombre,
        contacto_telefono=m.contacto_telefono,
        origen_url=m.origen_url,
        origen_nombre=svc.ORIGEN_NOMBRES.get(m.source) if m.origen_url else None,
        fecha_evento=m.fecha_evento.isoformat() if m.fecha_evento else None,
        estado=m.estado,
        notas=m.notas,
        source=m.source,
        created_at=m.created_at,
        fotos=[
            FotoPanelOut(
                id=f.id,
                url=f"/api/mascotas/foto/{m.codigo}/{f.id}",
                storage_key=f.storage_key,
                storage_uri=svc.storage_uri(f.storage_key),
                content_type=f.content_type or "image/jpeg",
                bytes_size=f.bytes_size,
            )
            for f in (m.fotos or [])
        ],
    )


def _fila_coincidencia(c: models.MascotaCoincidencia) -> CoincidenciaOut:
    return CoincidenciaOut(
        id=c.id,
        score=c.score,
        estado=c.estado,
        detalle=c.detalle or {},
        notas=c.notas,
        created_at=c.created_at,
        perdida=_fila_panel(c.perdida),
        encontrada=_fila_panel(c.encontrada),
    )


@router.get("/panel", response_model=PanelOut)
def panel(
    tipo: Optional[str] = None,
    estado: Optional[str] = None,
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """Tablero de la iniciativa: contadores, reportes y coincidencias del cruce."""
    coincidencias = svc.listar_coincidencias(db)
    return PanelOut(
        resumen=ResumenOut(**svc.resumen(db)),
        reportes=[_fila_panel(m) for m in svc.listar(db, tipo=tipo, estado=estado)],
        coincidencias=[_fila_coincidencia(c) for c in coincidencias],
        coincidencias_nuevas=sum(
            1 for c in coincidencias if c.estado == models.MATCH_ESTADO_NUEVA
        ),
    )


@router.patch("/panel/coincidencias/{coincidencia_id}", response_model=CoincidenciaOut)
def actualizar_coincidencia(
    coincidencia_id: int,
    payload: CoincidenciaUpdate,
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """Marca una coincidencia como revisada, confirmada o descartada.

    El cruce diario respeta este estado: lo que el equipo descartó no vuelve a
    aparecer como nuevo.
    """
    coincidencia = (
        db.query(models.MascotaCoincidencia)
        .filter(models.MascotaCoincidencia.id == coincidencia_id)
        .first()
    )
    if coincidencia is None:
        raise HTTPException(status_code=404, detail="Coincidencia no encontrada")

    if payload.estado is not None:
        if payload.estado not in models.AVAILABLE_MATCH_ESTADOS:
            raise HTTPException(status_code=400, detail="Estado inválido")
        coincidencia.estado = payload.estado
    if payload.notas is not None:
        coincidencia.notas = payload.notas.strip() or None
    coincidencia.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(coincidencia)
    logger.info(
        "mascotas panel: coincidencia %s estado=%s",
        coincidencia.id, coincidencia.estado,
    )
    return _fila_coincidencia(coincidencia)


# ---------------------------------------------------------------------------
# Sincronización con plataformas hermanas (mascotasporcolombia.com)
# ---------------------------------------------------------------------------

# Estado de la sincronización en curso. Vive en memoria del proceso porque es
# efímero por naturaleza (dura lo que dura la corrida) y el backend es una sola
# task ECS. Si algún día escala horizontalmente, el botón podría no ver el
# progreso de otra task — ahí tocaría moverlo a la BD.
_sync_estado: Dict[str, Any] = {"estado": "idle"}
_sync_lock = Lock()


class SyncOut(BaseModel):
    """Progreso de la importación. `estado`: idle | corriendo | ok | error."""

    estado: str
    mensaje: Optional[str] = None
    iniciada: Optional[datetime] = None
    terminada: Optional[datetime] = None
    contadores: Dict[str, int] = {}


def _correr_sincronizacion() -> None:
    """Importa en segundo plano. Lo lanza `POST /panel/sincronizar`.

    Va en un hilo porque recorrer ~300 fichas con pausa entre requests toma
    minutos y no cabe en el timeout de API Gateway (30 s). El panel consulta el
    avance con `GET /panel/sincronizacion`.
    """
    db = None
    try:
        # Los imports van DENTRO del try: si el módulo del importador falta o
        # falla al cargar, el estado tiene que quedar en 'error' — si el fallo
        # escapa, el botón se queda en 'corriendo' para siempre y no se puede
        # reintentar sin reiniciar el backend.
        from ..database import SessionLocal
        from ..services import mascotasporcolombia

        def _avance(parciales: Dict[str, int]) -> None:
            with _sync_lock:
                _sync_estado["contadores"] = dict(parciales)

        db = SessionLocal()
        contadores = mascotasporcolombia.sincronizar(db, progreso=_avance)
        with _sync_lock:
            _sync_estado.update({
                "estado": "ok",
                "mensaje": None,
                "terminada": datetime.utcnow(),
                "contadores": dict(contadores),
            })
        logger.info("mascotas sync: terminada %s", contadores)
    except BaseException:
        # Detalle solo server-side (regla de seguridad #6).
        logger.exception("mascotas sync: la importación falló")
        with _sync_lock:
            _sync_estado.update({
                "estado": "error",
                "mensaje": "No pudimos completar la sincronización. Intenta más tarde.",
                "terminada": datetime.utcnow(),
            })
    finally:
        if db is not None:
            db.close()
        # Red de seguridad: pase lo que pase, el estado no puede quedar en
        # 'corriendo', porque bloquearía todos los intentos siguientes.
        with _sync_lock:
            if _sync_estado.get("estado") == "corriendo":
                _sync_estado.update({
                    "estado": "error",
                    "mensaje": "La sincronización terminó de forma inesperada.",
                    "terminada": datetime.utcnow(),
                })


@router.post("/panel/sincronizar", response_model=SyncOut)
def sincronizar_panel(
    _: models.User = Depends(require_mascotas_account),
):
    """Trae los reportes nuevos de las plataformas hermanas.

    Responde de inmediato con `corriendo`: la importación sigue en segundo
    plano y el panel la consulta con `GET /panel/sincronizacion`. Si ya hay una
    corriendo, no lanza otra.
    """
    with _sync_lock:
        if _sync_estado.get("estado") == "corriendo":
            return SyncOut(**{k: v for k, v in _sync_estado.items()})
        _sync_estado.clear()
        _sync_estado.update({
            "estado": "corriendo",
            "iniciada": datetime.utcnow(),
            "contadores": {},
        })

    Thread(target=_correr_sincronizacion, name="mascotas-sync", daemon=True).start()
    logger.info("mascotas sync: importación lanzada")
    with _sync_lock:
        return SyncOut(**{k: v for k, v in _sync_estado.items()})


@router.get("/panel/sincronizacion", response_model=SyncOut)
def estado_sincronizacion(
    _: models.User = Depends(require_mascotas_account),
):
    """Avance de la última importación (o `idle` si nunca se corrió)."""
    with _sync_lock:
        return SyncOut(**{k: v for k, v in _sync_estado.items()})


@router.post("/panel/cruzar", response_model=Dict[str, int])
def cruzar_ahora(
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """Dispara el cruce a mano, sin esperar al job de las 12:00.

    Mismo código que corre el job: sirve para verificar el resultado apenas
    entra un reporte nuevo.
    """
    return svc.cruzar_reportes(db)


@router.patch("/panel/{codigo}", response_model=MascotaPanelOut)
def actualizar_panel(
    codigo: str,
    payload: PanelUpdate,
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """Edita un reporte: corrige cualquier dato, cambia el tipo o el estado.

    Solo se toca lo que venga en el cuerpo (PATCH parcial), así que el mismo
    endpoint sirve para el selector de estado de la tabla y para el formulario
    completo de edición.
    """
    mascota, problema = svc.editar_desde_panel(
        db, codigo, payload.model_dump(exclude_unset=True)
    )
    if mascota is None:
        if problema == "El reporte no existe":
            raise HTTPException(status_code=404, detail=problema)
        raise HTTPException(status_code=400, detail=problema)
    return _fila_panel(mascota)


@router.delete("/panel/{codigo}", response_model=BorradoOut)
def eliminar_panel(
    codigo: str,
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """Borra un reporte con sus fotos y sus coincidencias. No se puede deshacer."""
    if not svc.eliminar_reporte(db, codigo):
        raise HTTPException(status_code=404, detail="Reporte no encontrado")
    return BorradoOut()


@router.delete("/panel/{codigo}/fotos/{foto_id}", response_model=BorradoOut)
def eliminar_foto_panel(
    codigo: str,
    foto_id: int,
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """Borra una sola foto de un reporte (por ejemplo, una que salió movida)."""
    if not svc.eliminar_foto(db, codigo, foto_id):
        raise HTTPException(status_code=404, detail="Foto no encontrada")
    return BorradoOut()


@router.delete("/panel/purgar/{source}", response_model=BorradoOut)
def purgar_panel(
    source: str,
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """Borra de un golpe todos los reportes de un origen.

    Existe para dejar la base limpia de datos de prueba (`demo`) antes de abrir
    al público. Los reportes que entraron por el chat (`web`) o por WhatsApp no
    se pueden purgar así: esos se borran de a uno, a propósito.
    """
    if source not in ("demo",):
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden purgar los reportes de prueba (demo)",
        )
    return BorradoOut(eliminados=svc.purgar(db, source))


@router.get("/panel/export.xlsx")
def exportar_panel(
    tipo: Optional[str] = None,
    _: models.User = Depends(require_mascotas_account),
    db: Session = Depends(get_db),
):
    """El mismo Excel que entrega el bot, descargado desde el panel."""
    contenido = svc.exportar_excel(db, tipo=tipo)
    hoy = datetime.utcnow().strftime("%Y-%m-%d")
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="mascotas_{hoy}.xlsx"',
            "Cache-Control": "no-store",
        },
    )
