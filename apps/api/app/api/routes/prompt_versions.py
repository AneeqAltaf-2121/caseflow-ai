"""Prompt version tracking (Phase 22), nested under a project."""

import uuid

from fastapi import APIRouter

from app.dependencies import CurrentUserIdDep, DbSessionDep
from app.models.prompt_version import PromptVersion
from app.repositories.project_repository import ProjectRepository
from app.repositories.prompt_version_repository import PromptVersionRepository
from app.schemas.prompt_version import PromptVersionCreate, PromptVersionRead
from app.services.project_service import ProjectService
from app.services.prompt_version_service import PromptVersionService

router = APIRouter(prefix="/projects/{project_id}/prompts", tags=["prompts"])


def _service(db: DbSessionDep) -> PromptVersionService:
    return PromptVersionService(PromptVersionRepository(db), ProjectService(ProjectRepository(db)))


def _read(version: PromptVersion) -> PromptVersionRead:
    return PromptVersionRead(
        id=version.id,
        project_id=version.project_id,
        name=version.name,
        version=version.version,
        template=version.template,
        is_active=version.is_active,
        created_by=version.created_by,
        created_at=version.created_at,
    )


@router.post("", response_model=PromptVersionRead, status_code=201)
async def create_prompt_version(
    project_id: uuid.UUID,
    payload: PromptVersionCreate,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> PromptVersionRead:
    version = await _service(db).create_version(
        project_id=project_id,
        user_id=current_user_id,
        name=payload.name,
        template=payload.template,
        activate=payload.activate,
    )
    return _read(version)


@router.get("/{name}", response_model=list[PromptVersionRead])
async def list_prompt_versions(
    project_id: uuid.UUID, name: str, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> list[PromptVersionRead]:
    versions = await _service(db).list_versions(
        project_id=project_id, user_id=current_user_id, name=name
    )
    return [_read(v) for v in versions]


@router.post("/{prompt_version_id}/activate", response_model=PromptVersionRead)
async def activate_prompt_version(
    project_id: uuid.UUID,
    prompt_version_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> PromptVersionRead:
    version = await _service(db).activate_version(
        project_id=project_id, user_id=current_user_id, prompt_version_id=prompt_version_id
    )
    return _read(version)
