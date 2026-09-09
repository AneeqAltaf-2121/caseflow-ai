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
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberInvite,
    ProjectMemberRead,
    ProjectRead,
)
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(
    payload: ProjectCreate, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> ProjectRead:
    service = ProjectService(ProjectRepository(db))
    project = await service.create_project(
        organization_id=payload.organization_id,
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

    service = ProjectService(ProjectRepository(db))
    member = await service.invite_member(
        project_id=project_id,
        inviter_user_id=current_user_id,
        invitee_user_id=invitee.id,
        role=payload.role,
    )
    return ProjectMemberRead.model_validate(member)
