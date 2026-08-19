"""Router de Contactos y Grupos de Contactos (Sprint 13 — tarea #159).

Endpoints multi-tenant: TODOS filtran por `team_id` del usuario autenticado.
Se aplica el patrón anti-IDOR S13-001: 404 (no 403) cuando un recurso no
pertenece al team del usuario. Errores al cliente sanitizados (regla 6 de
CLAUDE.md): los detalles van a `logger.exception` server-side.
"""
import logging
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import crud, models, schemas
from ..dependencies import get_current_membership, get_db
from ..services import contactos_excel

logger = logging.getLogger(__name__)

# Un único router con dos prefijos lógicos; FastAPI los expone como rutas
# distintas. Se sigue el patrón de `bots.py`/`mensajes.py` (router por archivo).
router = APIRouter(tags=["contacts"])

# S13-009: límite estricto del CSV en bytes (2 MB del wireframe).
MAX_CSV_BYTES = 2 * 1024 * 1024
ALLOWED_CSV_MIMES = {"text/csv", "application/vnd.ms-excel", "application/octet-stream"}

# El navegador manda el MIME del .xlsx; algunos clientes mandan octet-stream.
ALLOWED_XLSX_MIMES = {
    contactos_excel.MIME_XLSX,
    "application/vnd.ms-excel",
    "application/octet-stream",
    "application/zip",
}


# ===================== Contactos =====================

@router.get("/contacts", response_model=List[schemas.ContactOut])
def list_contacts_endpoint(
    q: Optional[str] = Query(default=None, max_length=120),
    group_id: Optional[int] = Query(default=None, ge=1),
    opt_in_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Lista paginada de contactos del team del usuario."""
    if group_id is not None:
        # S13-001: confirmar que el grupo pertenece al team antes de filtrar
        # por él. Si no, 404 silencioso.
        grp = crud.get_contact_group(db, member.team_id, group_id)
        if grp is None:
            raise HTTPException(status_code=404, detail="Recurso no encontrado")

    contacts = crud.list_contacts(
        db,
        member.team_id,
        q=q,
        group_id=group_id,
        opt_in_only=opt_in_only,
        limit=limit,
        offset=offset,
    )
    return [schemas.ContactOut.model_validate(c) for c in contacts]


@router.post(
    "/contacts",
    response_model=schemas.ContactOut,
    status_code=status.HTTP_201_CREATED,
)
def create_contact_endpoint(
    payload: schemas.ContactCreate,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Crea o actualiza un contacto (upsert por (team_id, phone_e164))."""
    try:
        contact, _created = crud.create_contact(db, member.team_id, payload)
    except IntegrityError:
        db.rollback()
        # No exponer el SQL ni el detalle del constraint al cliente.
        logger.exception(
            "create_contact: IntegrityError (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=409,
            detail="No se pudo guardar el contacto (conflicto).",
        )
    except Exception:
        db.rollback()
        logger.exception("create_contact: error inesperado (team_id=%s)", member.team_id)
        raise HTTPException(status_code=500, detail="Error temporal al guardar.")
    return schemas.ContactOut.model_validate(contact)


# ── Excel: plantilla, importación y catálogo de campos ──────────────────
#
# OJO con el orden: estas rutas van ANTES de `/contacts/{contact_id}`. FastAPI
# resuelve por orden de declaración y `{contact_id}` es un int — si estuviera
# primero, `/contacts/plantilla` se intentaría parsear como id y devolvería 422.

@router.get("/contacts/plantilla")
def download_contacts_template_endpoint(
    member: models.TeamMember = Depends(get_current_membership),
):
    """Descarga el .xlsx de guía para cargar contactos.

    Autenticado a propósito aunque el archivo no tenga datos de nadie: es una
    pantalla de la plataforma, no un recurso público.
    """
    try:
        contenido = contactos_excel.construir_plantilla()
    except Exception:
        logger.exception(
            "contacts_template: no se pudo generar (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=500,
            detail="Error temporal al generar la plantilla. Inténtalo de nuevo.",
        )
    return Response(
        content=contenido,
        media_type=contactos_excel.MIME_XLSX,
        headers={
            "Content-Disposition": (
                'attachment; filename="plantilla-contactos-gloma.xlsx"'
            ),
        },
    )


@router.get("/contacts/campos", response_model=schemas.ContactFieldsOut)
def list_contact_fields_endpoint(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Campos con los que se puede personalizar un mensaje de campaña.

    Nombre y teléfono siempre, más los atributos que existan en los contactos
    del team. Devuelve el catálogo, nunca los valores (regla 2).
    """
    try:
        return contactos_excel.campos_disponibles(db, member.team_id)
    except Exception:
        logger.exception(
            "contact_fields: error inesperado (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=500, detail="Error temporal al leer los campos."
        )


@router.post(
    "/contacts/import-excel",
    response_model=schemas.ContactExcelImportResult,
)
async def import_contacts_excel_endpoint(
    file: UploadFile = File(...),
    pais_default: str = Form(default=""),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Importa contactos desde el .xlsx de la plantilla.

    `pais_default` es el código de país (solo dígitos, p. ej. `57`) con el que
    se completan los números que vengan sin él. Vacío = no completar nada y
    rechazar esas filas con un motivo claro.

    El contenido del archivo NO se loguea; solo su tamaño (regla 1).
    """
    if file.content_type and file.content_type not in ALLOWED_XLSX_MIMES:
        logger.warning(
            "import_excel: MIME no permitido (team_id=%s, mime=%s)",
            member.team_id,
            file.content_type,
        )
        raise HTTPException(
            status_code=415,
            detail="Tipo de archivo no soportado. Sube el archivo .xlsx de la plantilla.",
        )

    prefijo = (pais_default or "").strip().lstrip("+")
    if prefijo and (not prefijo.isdigit() or len(prefijo) > 4):
        raise HTTPException(
            status_code=400,
            detail="El código de país debe tener solo dígitos (por ejemplo 57).",
        )

    try:
        raw = await file.read()
    except Exception:
        logger.exception(
            "import_excel: error al leer upload (team_id=%s)", member.team_id
        )
        raise HTTPException(status_code=400, detail="No se pudo leer el archivo.")

    if not raw:
        raise HTTPException(status_code=400, detail="El archivo está vacío.")

    if len(raw) > contactos_excel.MAX_EXCEL_BYTES:
        raise HTTPException(
            status_code=413,
            detail="El archivo excede el tamaño máximo permitido (2 MB).",
        )

    logger.info("import_excel: team_id=%s bytes=%d", member.team_id, len(raw))

    try:
        return contactos_excel.importar(db, member.team_id, raw, prefijo or None)
    except Exception:
        db.rollback()
        logger.exception(
            "import_excel: error inesperado al procesar (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=500,
            detail="Error temporal al procesar el archivo.",
        )


@router.get("/contacts/{contact_id}", response_model=schemas.ContactOut)
def get_contact_endpoint(
    contact_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Detalle del contacto. S13-001: 404 si no pertenece al team."""
    contact = crud.get_contact(db, member.team_id, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return schemas.ContactOut.model_validate(contact)


@router.patch("/contacts/{contact_id}", response_model=schemas.ContactOut)
def update_contact_endpoint(
    contact_id: int,
    payload: schemas.ContactUpdate,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    contact = crud.update_contact(db, member.team_id, contact_id, payload)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return schemas.ContactOut.model_validate(contact)


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact_endpoint(
    contact_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    ok = crud.delete_contact(db, member.team_id, contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Contacto no encontrado")
    return None


@router.post(
    "/contacts/import-csv",
    response_model=schemas.ContactBulkImportResult,
)
async def import_contacts_csv_endpoint(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Importa contactos desde un CSV (multipart).

    S13-009: valida MIME, tamaño, número de filas. El contenido NO se loguea.
    Columnas requeridas: `phone_e164`. Opcionales: `name`, `email`, `opt_in`,
    `opt_in_source`.
    """
    # Validación de MIME (defensa, el contenido aún se valida después).
    if file.content_type and file.content_type not in ALLOWED_CSV_MIMES:
        logger.warning(
            "import_csv: MIME no permitido (team_id=%s, mime=%s)",
            member.team_id,
            file.content_type,
        )
        raise HTTPException(
            status_code=415,
            detail="Tipo de archivo no soportado. Sube un CSV.",
        )

    try:
        raw = await file.read()
    except Exception:
        logger.exception("import_csv: error al leer upload (team_id=%s)", member.team_id)
        raise HTTPException(status_code=400, detail="No se pudo leer el archivo.")

    if not raw:
        raise HTTPException(status_code=400, detail="Archivo vacío.")

    if len(raw) > MAX_CSV_BYTES:
        raise HTTPException(
            status_code=413,
            detail="El archivo excede el tamaño máximo permitido (2 MB).",
        )

    # Decodifica de forma tolerante; si falla, mensaje genérico.
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("latin-1")
        except Exception:
            logger.exception(
                "import_csv: encoding inválido (team_id=%s)", member.team_id
            )
            raise HTTPException(
                status_code=400,
                detail="No se pudo decodificar el archivo. Usa UTF-8.",
            )

    # NO loguear `text`. Solo metadata.
    logger.info(
        "import_csv: team_id=%s bytes=%d",
        member.team_id,
        len(raw),
    )

    try:
        result = crud.import_contacts_csv(db, member.team_id, text)
    except Exception:
        logger.exception(
            "import_csv: error inesperado al procesar (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=500,
            detail="Error temporal al procesar el archivo.",
        )

    return result


# ===================== Grupos de Contactos =====================

@router.get("/contact-groups", response_model=List[schemas.ContactGroupOut])
def list_contact_groups_endpoint(
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    rows = crud.list_contact_groups(db, member.team_id)
    return [
        schemas.ContactGroupOut(
            id=g.id,
            name=g.name,
            description=g.description,
            member_count=int(count or 0),
            created_at=g.created_at,
        )
        for g, count in rows
    ]


@router.post(
    "/contact-groups",
    response_model=schemas.ContactGroupOut,
    status_code=status.HTTP_201_CREATED,
)
def create_contact_group_endpoint(
    payload: schemas.ContactGroupCreate,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    try:
        group = crud.create_contact_group(db, member.team_id, payload)
    except IntegrityError:
        db.rollback()
        logger.exception(
            "create_contact_group: IntegrityError (team_id=%s)", member.team_id
        )
        raise HTTPException(
            status_code=409,
            detail="Ya existe un grupo con ese nombre en este equipo.",
        )
    except Exception:
        db.rollback()
        logger.exception(
            "create_contact_group: error inesperado (team_id=%s)", member.team_id
        )
        raise HTTPException(status_code=500, detail="Error temporal al guardar.")
    return schemas.ContactGroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        member_count=0,
        created_at=group.created_at,
    )


@router.get(
    "/contact-groups/{group_id}",
    response_model=schemas.ContactGroupDetailOut,
)
def get_contact_group_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    row = crud.get_contact_group_with_count(db, member.team_id, group_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    group, count = row
    members = [m.contact for m in group.members]
    return schemas.ContactGroupDetailOut(
        id=group.id,
        name=group.name,
        description=group.description,
        member_count=int(count or 0),
        created_at=group.created_at,
        members=[schemas.ContactOut.model_validate(c) for c in members],
    )


@router.patch(
    "/contact-groups/{group_id}",
    response_model=schemas.ContactGroupOut,
)
def update_contact_group_endpoint(
    group_id: int,
    payload: schemas.ContactGroupUpdate,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    try:
        group = crud.update_contact_group(db, member.team_id, group_id, payload)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Ya existe un grupo con ese nombre en este equipo.",
        )
    if group is None:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    # Calcular member_count cheap (separado para no romper el commit).
    row = crud.get_contact_group_with_count(db, member.team_id, group_id)
    count = (row[1] if row else 0) or 0
    return schemas.ContactGroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        member_count=int(count),
        created_at=group.created_at,
    )


@router.delete(
    "/contact-groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_contact_group_endpoint(
    group_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    ok = crud.delete_contact_group(db, member.team_id, group_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    return None


@router.post(
    "/contact-groups/{group_id}/members",
    response_model=schemas.ContactGroupDetailOut,
)
def add_group_members_endpoint(
    group_id: int,
    payload: schemas.ContactGroupAddMembersIn,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """Añade contactos al grupo.

    S13-001: si CUALQUIER `contact_id` no pertenece al team del usuario,
    se rechaza la operación completa con 404 (no se hace insert parcial).
    No se devuelve cuáles eran ajenos para no revelar existencia.
    """
    group, _added, invalid = crud.add_group_members(
        db, member.team_id, group_id, payload.contact_ids
    )
    if group is None:
        raise HTTPException(status_code=404, detail="Grupo no encontrado")
    if invalid:
        # 404 genérico — no revelamos cuáles IDs eran reales en otro team.
        raise HTTPException(
            status_code=404,
            detail="Uno o más contactos no fueron encontrados",
        )
    # Devolver detalle actualizado.
    row = crud.get_contact_group_with_count(db, member.team_id, group_id)
    grp, count = row
    members = [m.contact for m in grp.members]
    return schemas.ContactGroupDetailOut(
        id=grp.id,
        name=grp.name,
        description=grp.description,
        member_count=int(count or 0),
        created_at=grp.created_at,
        members=[schemas.ContactOut.model_validate(c) for c in members],
    )


@router.delete(
    "/contact-groups/{group_id}/members/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_group_member_endpoint(
    group_id: int,
    contact_id: int,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(get_current_membership),
):
    """S13-001: 404 si grupo o contacto no pertenecen al team, o no son miembros."""
    ok = crud.remove_group_member(db, member.team_id, group_id, contact_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Recurso no encontrado")
    return None
