"""Project routes.

routes -> ProjectService -> ProjectRepository -> PostgreSQL (see
docs/domain-model.md). No route in this file touches the ORM or issues SQL
directly.

Auth note: `user_id` is accepted as an explicit parameter until Phase 4
(OAuth) exists to supply it from a session. The service-layer scoping these
routes exercise (`get_project_for_user`, `require_role`) does not change
once Phase 4 lands.
"""

import uuid

from fastapi import APIRouter

from app.dependencies import DbSessionDep
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectRead
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead, status_code=201)
async def create_project(payload: ProjectCreate, db: DbSessionDep) -> ProjectRead:
    service = ProjectService(ProjectRepository(db))
    project = await service.create_project(
        organization_id=payload.organization_id,
        name=payload.name,
        description=payload.description,
        created_by=payload.created_by,
    )
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(user_id: uuid.UUID, db: DbSessionDep) -> list[ProjectRead]:
    service = ProjectService(ProjectRepository(db))
    projects = await service.list_projects_for_user(user_id)
    return [ProjectRead.model_validate(p) for p in projects]


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: uuid.UUID, user_id: uuid.UUID, db: DbSessionDep) -> ProjectRead:
    service = ProjectService(ProjectRepository(db))
    project = await service.get_project_for_user(project_id=project_id, user_id=user_id)
    return ProjectRead.model_validate(project)
