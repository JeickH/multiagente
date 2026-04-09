from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas, crud
from ..dependencies import get_db, get_current_user, get_current_membership, require_permission

router = APIRouter(prefix="/teams", tags=["teams"])


def _serialize_member(member: models.TeamMember) -> schemas.TeamMemberOut:
    return schemas.TeamMemberOut(
        id=member.id,
        user_id=member.user_id,
        role=member.role,
        nombre=member.user.nombre if member.user else None,
        correo=member.user.correo if member.user else None,
        permissions=crud.permissions_dict(member),
    )


@router.get("/me", response_model=schemas.TeamMeOut)
def get_my_team(
    member: models.TeamMember = Depends(get_current_membership),
):
    return schemas.TeamMeOut(
        team=schemas.TeamOut(
            id=member.team.id,
            nombre=member.team.nombre,
            owner_user_id=member.team.owner_user_id,
        ),
        member=_serialize_member(member),
    )


@router.get("/me/members", response_model=List[schemas.TeamMemberOut])
def list_my_team_members(
    member: models.TeamMember = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    members = crud.get_team_members(db, member.team_id)
    return [_serialize_member(m) for m in members]


@router.post("/me/members", response_model=schemas.TeamMemberOut)
def invite_team_member(
    payload: schemas.TeamMemberInvite,
    db: Session = Depends(get_db),
    member: models.TeamMember = Depends(require_permission("can_manage_team")),
):
    if crud.get_user_by_email(db, payload.correo):
        raise HTTPException(status_code=400, detail="El correo ya está registrado")

    new_user = crud.create_user(
        db,
        schemas.UserCreate(
            nombre=payload.nombre,
            tipo_documento="CC",
            documento=f"team-{member.team_id}-{payload.correo}",
            correo=payload.correo,
            password=payload.password,
        ),
    )
    new_member = crud.add_member_to_team(
        db, member.team, new_user, role=payload.role, permissions=payload.permissions
    )
    return _serialize_member(new_member)


@router.put("/me/members/{member_id}/permissions", response_model=schemas.TeamMemberOut)
def update_member_permissions(
    member_id: int,
    payload: schemas.PermissionUpdate,
    db: Session = Depends(get_db),
    current_member: models.TeamMember = Depends(require_permission("can_manage_team")),
):
    target = (
        db.query(models.TeamMember)
        .filter(
            models.TeamMember.id == member_id,
            models.TeamMember.team_id == current_member.team_id,
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Miembro no encontrado en el equipo")
    if target.role == "owner":
        raise HTTPException(status_code=400, detail="No se pueden modificar los permisos del owner")

    crud.set_member_permissions(db, target, payload.permissions)
    return _serialize_member(target)
