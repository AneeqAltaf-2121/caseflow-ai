"""Project routes.

routes -> ProjectService -> ProjectRepository -> PostgreSQL (see
docs/domain-model.md). No route in this file touches the ORM or issues SQL
directly. The acting user always comes from CurrentUserIdDep (the verified
JWT subject) — never from a client-supplied field.
"""

import uuid

from fastapi import APIRouter

from app.dependencies import CurrentUserIdDep, DbSessionDep
from app.errors import NotFoundError
from app.repositories.audit_event_repository import AuditEventRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.schemas.audit_event import AuditEventRead
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberInvite,
    ProjectMemberRead,
    ProjectMemberRoleUpdate,
    ProjectRead,
    ProjectUpdate,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


def _audited_service(db: DbSessionDep) -> ProjectService:
    """Wires an AuditEventRepository in — used only by routes that
    perform one of Phase 36's audited actions."""
    return ProjectService(ProjectRepository(db), AuditEventRepository(db))


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    payload: ProjectCreate, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> ProjectRead:
    organization_id = payload.organization_id
    if organization_id is None:
        user = await UserRepository(db).get_by_id(current_user_id)
        assert user is not None  # current_user_id came from a verified token
        organization = await OrganizationRepository(db).get_or_create_personal(
            user_id=user.id, display_name=user.display_name
        )
        organization_id = organization.id

    project = await _audited_service(db).create_project(
        organization_id=organization_id,
        name=payload.name,
        description=payload.description,
        created_by=current_user_id,
    )
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(current_user_id: CurrentUserIdDep, db: DbSessionDep) -> list[ProjectRead]:
    service = ProjectService(ProjectRepository(db))
    projects = await service.list_projects_for_user(current_user_id)
    return [ProjectRead.model_validate(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> ProjectRead:
    service = ProjectService(ProjectRepository(db))
    project = await service.get_project_for_user(project_id=project_id, user_id=current_user_id)
    return ProjectRead.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> ProjectRead:
    service = ProjectService(ProjectRepository(db))
    project = await service.update_project(
        project_id=project_id,
        user_id=current_user_id,
        name=payload.name,
        description=payload.description,
        description_set="description" in payload.model_fields_set,
    )
    return ProjectRead.model_validate(project)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> None:
    service = ProjectService(ProjectRepository(db))
    await service.delete_project(project_id=project_id, user_id=current_user_id)


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
async def list_members(
    project_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> list[ProjectMemberRead]:
    service = ProjectService(ProjectRepository(db))
    members = await service.list_members(project_id=project_id, user_id=current_user_id)
    return [ProjectMemberRead.model_validate(m) for m in members]


@router.post("/{project_id}/members", response_model=ProjectMemberRead, status_code=201)
async def invite_member(
    project_id: uuid.UUID,
    payload: ProjectMemberInvite,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> ProjectMemberRead:
    invitee = await UserRepository(db).get_by_email(payload.email)
    if invitee is None:
        raise NotFoundError(f"No user found with email {payload.email!r}.")

    member = await _audited_service(db).invite_member(
        project_id=project_id,
        inviter_user_id=current_user_id,
        invitee_user_id=invitee.id,
        role=payload.role,
    )
    return ProjectMemberRead.model_validate(member)


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberRead)
async def change_member_role(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: ProjectMemberRoleUpdate,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> ProjectMemberRead:
    member = await _audited_service(db).change_member_role(
        project_id=project_id,
        actor_user_id=current_user_id,
        target_user_id=user_id,
        role=payload.role,
    )
    return ProjectMemberRead.model_validate(member)


@router.delete("/{project_id}/members/{user_id}", status_code=204)
async def remove_member(
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> None:
    await _audited_service(db).remove_member(
        project_id=project_id, actor_user_id=current_user_id, target_user_id=user_id
    )


@router.get("/{project_id}/audit-events", response_model=list[AuditEventRead])
async def list_audit_events(
    project_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> list[AuditEventRead]:
    # Any member can view the log — same "read is membership-gated,
    # write is role-gated" split as everywhere else. get_project_for_user
    # is enough here since this route makes no writes of its own.
    await ProjectService(ProjectRepository(db)).get_project_for_user(
        project_id=project_id, user_id=current_user_id
    )
    events = await AuditEventRepository(db).list_for_project(project_id)
    return [AuditEventRead.model_validate(e) for e in events]
