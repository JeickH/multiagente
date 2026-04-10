from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas, crud
from ..dependencies import get_db, get_current_membership, require_permission
from ..services import meta_whatsapp

router = APIRouter(prefix="/mensajes", tags=["mensajes"])


@router.get("/conversaciones", response_model=List[schemas.ConversationOut])
def list_conversations(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    convs = crud.list_conversations(db, member.team_id)
    return [
        schemas.ConversationOut(
            id=c.id,
            contact_wa_id=c.contact_wa_id,
            contact_name=c.contact_name,
            status=c.status,
            last_message_at=c.last_message_at,
            last_message_preview=crud.last_message_preview(c),
        )
        for c in convs
    ]


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
        meta_id, _ = meta_whatsapp.send_text_message(
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
    except meta_whatsapp.MetaWhatsAppError as exc:
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
        raise HTTPException(status_code=502, detail=f"Error de Meta: {exc}")


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
        meta_id, _ = meta_whatsapp.send_template_message(
            account,
            payload.contact_wa_id,
            payload.template_name,
            payload.language_code,
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
    except meta_whatsapp.MetaWhatsAppError as exc:
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
        raise HTTPException(status_code=502, detail=f"Error de Meta: {exc}")
