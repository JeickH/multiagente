import logging

from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
)
from sqlalchemy.orm import Session
from typing import List, Optional

from .. import models, schemas, crud
from ..dependencies import get_db, get_current_membership, require_permission
from ..services import adjuntos, messaging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mensajes", tags=["mensajes"])


@router.get("/conversaciones", response_model=schemas.ConversationPageOut)
def list_conversations(
    estado: Optional[str] = Query(
        None, description="open | pending | closed. Vacío = todas."
    ),
    busqueda: Optional[str] = Query(
        None, description="nombre o número del contacto"
    ),
    limite: int = Query(
        20, ge=1, le=crud.MAX_CONVERSACIONES_POR_PAGINA,
        description="cuántas conversaciones por página",
    ),
    pagina: int = Query(1, ge=1, description="página, empezando en 1"),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Una página de la bandeja del team, de la más reciente a la más vieja.

    El filtro y la búsqueda se resuelven en la base junto con la paginación: son
    parte de la misma consulta, así que "20 por página" siempre significa las 20
    primeras de lo filtrado.
    """
    if estado and estado not in crud.ESTADOS_CONVERSACION:
        raise HTTPException(status_code=400, detail="Estado no válido")

    convs, total = crud.list_conversations(
        db,
        member.team_id,
        estado=estado,
        busqueda=busqueda,
        limite=limite,
        offset=(pagina - 1) * limite,
    )
    # Un solo golpe a `messages` para los adelantos de toda la página, en vez de
    # uno por conversación.
    previews = crud.previews_de_conversaciones(db, [c.id for c in convs])
    return schemas.ConversationPageOut(
        conversaciones=[
            schemas.ConversationOut(
                id=c.id,
                contact_wa_id=c.contact_wa_id,
                contact_name=c.contact_name,
                status=c.status,
                assigned_to=getattr(c, "assigned_to", "bot") or "bot",
                # `getattr` con default: la columna la agrega la migración de
                # `etiqueta` y el backend tiene que seguir sirviendo la bandeja
                # aunque todavía no esté aplicada.
                etiqueta=getattr(c, "etiqueta", None),
                last_message_at=c.last_message_at,
                last_message_preview=previews.get(c.id),
            )
            for c in convs
        ],
        total=total,
        pagina=pagina,
        por_pagina=limite,
    )


@router.get("/conversaciones/{conversation_id}", response_model=schemas.ConversationWithMessages)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    conv = crud.get_conversation(db, member.team_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")
    return schemas.ConversationWithMessages(
        id=conv.id,
        contact_wa_id=conv.contact_wa_id,
        contact_name=conv.contact_name,
        status=conv.status,
        assigned_to=getattr(conv, "assigned_to", "bot") or "bot",
        etiqueta=getattr(conv, "etiqueta", None),
        last_message_at=conv.last_message_at,
        messages=[schemas.MessageOut.model_validate(m) for m in conv.messages],
    )


@router.post("/conversaciones/{conversation_id}/enviar", response_model=schemas.MessageOut)
def send_message_in_conversation(
    conversation_id: int,
    payload: schemas.MessageSendIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_permission("can_reply_messages")),
):
    conv = crud.get_conversation(db, member.team_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    account = crud.get_meta_account_for_team(db, member.team_id)
    if not crud.is_meta_account_usable(account):
        raise HTTPException(
            status_code=409,
            detail="La cuenta de WhatsApp no está activa. El propietario debe conectarla desde Mi Plan.",
        )

    try:
        # Sprint 19 (#254): envío por el puerto multi-proveedor (Meta o Twilio
        # según account.provider) — mismo cambio que campañas/bots en Sprint 18.
        meta_id, _ = messaging.send_text(
            account, conv.contact_wa_id, payload.content
        )
        msg = crud.add_message(
            db,
            conv,
            direction="outbound",
            content=payload.content,
            message_type="text",
            meta_message_id=meta_id,
            sent_by_user_id=member.user_id,
            status="sent",
        )
        return schemas.MessageOut.model_validate(msg)
    except messaging.MessagingError as exc:
        crud.add_message(
            db,
            conv,
            direction="outbound",
            content=payload.content,
            message_type="text",
            sent_by_user_id=member.user_id,
            status="failed",
            error_detail=str(exc),
        )
        raise HTTPException(
            status_code=502, detail="Error del proveedor de WhatsApp al enviar el mensaje"
        )


@router.post("/conversaciones/{conversation_id}/adjunto", response_model=schemas.MessageOut)
async def send_attachment_in_conversation(
    conversation_id: int,
    archivo: UploadFile = File(...),
    caption: Optional[str] = Form(default=None),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_permission("can_reply_messages")),
):
    """Le manda al cliente una imagen, una nota de voz, un video o un PDF.

    Hasta acá solo se podía responder con texto: la foto de la habitación o el
    audio explicando una tarifa había que mandarlos desde el celular, por fuera
    de la plataforma, y no quedaban en la conversación.

    El archivo se guarda en nuestro storage y lo que viaja al proveedor es una
    URL pública (`GET /mensajes/adjunto/...`): así lo hacen Meta y Twilio, que
    descargan el archivo ellos mismos en vez de recibir el binario.

    El mensaje se persiste con `content = "pie\\nURL"` y `message_type` igual a
    la categoría (`image` | `audio` | `video` | `document`), que es exactamente
    lo que ya hace el bot cuando manda un tarifario: la burbuja del asesor se
    renderiza igual, sin columnas nuevas.
    """
    conv = crud.get_conversation(db, member.team_id, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversación no encontrada")

    account = crud.get_meta_account_for_team(db, member.team_id)
    if not crud.is_meta_account_usable(account):
        raise HTTPException(
            status_code=409,
            detail="La cuenta de WhatsApp no está activa. El propietario debe conectarla desde Mi Plan.",
        )

    # Un byte más que el tope: alcanza para saber que se pasó sin cargar en
    # memoria un archivo de cualquier tamaño.
    data = await archivo.read(adjuntos.MAX_BYTES + 1)
    preparado, problema = adjuntos.preparar(
        data, archivo.content_type, archivo.filename
    )
    if preparado is None:
        raise HTTPException(status_code=400, detail=problema)

    try:
        guardado = adjuntos.guardar(member.team_id, preparado, archivo.filename)
    except Exception:
        # Detalle solo server-side (regla de seguridad #6).
        logger.exception(
            "mensajes: no se pudo guardar el adjunto team=%s conv=%s",
            member.team_id, conv.id,
        )
        raise HTTPException(
            status_code=503,
            detail="No pudimos guardar el archivo. Intenta de nuevo, por favor.",
        )

    pie = adjuntos.limpiar_caption(caption, preparado.categoria)
    contenido = f"{pie}\n{guardado.url}" if pie else guardado.url

    try:
        meta_id, _ = messaging.send_media(
            account,
            conv.contact_wa_id,
            guardado.url,
            caption=pie or None,
            media_type=preparado.categoria,
        )
    except Exception as exc:
        # El mensaje queda igual en la conversación, marcado `failed`: el asesor
        # tiene que ver que lo intentó y no salió. El detalle del proveedor va
        # al log, nunca a la respuesta (regla #6).
        logger.exception(
            "mensajes: el proveedor rechazó el adjunto conv=%s tipo=%s",
            conv.id, preparado.categoria,
        )
        crud.add_message(
            db,
            conv,
            direction="outbound",
            content=contenido,
            message_type=preparado.categoria,
            sent_by_user_id=member.user_id,
            status="failed",
            error_detail=str(exc)[:500],
        )
        raise HTTPException(
            status_code=502, detail="Error del proveedor de WhatsApp al enviar el archivo"
        )

    msg = crud.add_message(
        db,
        conv,
        direction="outbound",
        content=contenido,
        message_type=preparado.categoria,
        meta_message_id=meta_id,
        sent_by_user_id=member.user_id,
        status="sent",
    )
    return schemas.MessageOut.model_validate(msg)


@router.get("/adjunto/{team_id}/{carpeta}/{nombre}")
def ver_adjunto(team_id: int, carpeta: str, nombre: str):
    """Sirve un adjunto que el asesor envió. **Público, sin auth.**

    Quien lo descarga es el servidor de Meta o de Twilio, que no manda ningún
    token: por eso no hay portero. Lo que sostiene el aislamiento es la forma
    de la ruta — una carpeta uuid4 a la que se le exige el formato exacto en
    `adjuntos.leer` — y que el `team_id` esté en la ruta del objeto. El bucket
    sigue privado, igual que el de las fotos de mascotas.

    El último tramo es el nombre legible del archivo porque es justo lo que
    WhatsApp le muestra a quien recibe un documento.
    """
    encontrado = adjuntos.leer(team_id, carpeta, nombre)
    if encontrado is None:
        raise HTTPException(status_code=404, detail="Adjunto no encontrado")
    data, content_type = encontrado
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            # El tipo lo fija la lista blanca; `nosniff` evita que el navegador
            # decida por su cuenta que algo es HTML y lo ejecute.
            "X-Content-Type-Options": "nosniff",
            # `nombre` ya pasó por `NOMBRE_RE`, así que no puede traer comillas
            # ni saltos con los que romper la cabecera.
            "Content-Disposition": f'inline; filename="{nombre}"',
        },
    )


@router.post("/conversaciones/nueva", response_model=schemas.MessageOut)
def start_new_conversation(
    payload: schemas.NewConversationMessageIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_permission("can_reply_messages")),
):
    """
    Inicia una conversación nueva enviando un template aprobado.
    Necesario cuando no hay ventana de 24h abierta con el contacto.
    """
    account = crud.get_meta_account_for_team(db, member.team_id)
    if not crud.is_meta_account_usable(account):
        raise HTTPException(
            status_code=409,
            detail="La cuenta de WhatsApp no está activa. El propietario debe conectarla desde Mi Plan.",
        )

    conv = crud.get_or_create_conversation(
        db,
        team_id=member.team_id,
        contact_wa_id=payload.contact_wa_id,
        contact_name=payload.contact_name,
    )

    try:
        # Sprint 19 (#254): plantilla por el puerto multi-proveedor.
        meta_id, _ = messaging.send_template(
            account,
            payload.contact_wa_id,
            payload.template_name,
            language_code=payload.language_code,
        )
        content_repr = f"[plantilla] {payload.template_name}"
        msg = crud.add_message(
            db,
            conv,
            direction="outbound",
            content=content_repr,
            message_type="template",
            meta_message_id=meta_id,
            sent_by_user_id=member.user_id,
            status="sent",
        )
        return schemas.MessageOut.model_validate(msg)
    except messaging.MessagingError as exc:
        crud.add_message(
            db,
            conv,
            direction="outbound",
            content=f"[plantilla] {payload.template_name}",
            message_type="template",
            sent_by_user_id=member.user_id,
            status="failed",
            error_detail=str(exc),
        )
        raise HTTPException(
            status_code=502, detail="Error del proveedor de WhatsApp al enviar la plantilla"
        )
