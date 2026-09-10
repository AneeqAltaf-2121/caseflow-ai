"""Prompt version tracking (Phase 22): named, versioned, immutable prompt
templates per project. Editing a prompt is creating a new version, never
mutating an existing row — that's what makes before/after comparisons
(Phase 26+) meaningful.
"""

import uuid

from app.errors import NotFoundError
from app.models.project import ProjectRole
from app.models.prompt_version import PromptVersion
from app.repositories.prompt_version_repository import PromptVersionRepository
from app.services.project_service import ProjectService

RAG_ANSWER_PROMPT_NAME = "rag_answer"


class PromptVersionService:
    def __init__(
        self, repository: PromptVersionRepository, project_service: ProjectService
    ) -> None:
        self._repository = repository
        self._project_service = project_service

    async def create_version(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        template: str,
        activate: bool = True,
    ) -> PromptVersion:
        await self._project_service.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        return await self._repository.create(
            project_id=project_id,
            name=name,
            template=template,
            created_by=user_id,
            activate=activate,
        )

    async def list_versions(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, name: str
    ) -> list[PromptVersion]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.list_for_name(project_id=project_id, name=name)

    async def activate_version(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, prompt_version_id: uuid.UUID
    ) -> PromptVersion:
        await self._project_service.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )
        version = await self._repository.get_by_id(prompt_version_id)
        if version is None or version.project_id != project_id:
            raise NotFoundError(f"Prompt version {prompt_version_id} not found.")
        return await self._repository.activate(version)

    async def get_or_seed_active(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, name: str, default_template: str
    ) -> PromptVersion:
        """The active version for `name`, auto-creating v1 from
        `default_template` the first time a project needs a prompt it's
        never customized — same "auto-provision a sane default" pattern as
        OrganizationRepository.get_or_create_personal."""
        active = await self._repository.get_active(project_id=project_id, name=name)
        if active is not None:
            return active
        return await self._repository.create(
            project_id=project_id,
            name=name,
            template=default_template,
            created_by=user_id,
            activate=True,
        )
