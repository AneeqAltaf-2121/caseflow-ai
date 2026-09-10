import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_version import PromptVersion


class PromptVersionRepository:
    """Data access for PromptVersion. No authorization here — see
    app/services/prompt_version_service.py."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self, *, project_id: uuid.UUID, name: str) -> PromptVersion | None:
        result = await self._session.execute(
            select(PromptVersion).where(
                PromptVersion.project_id == project_id,
                PromptVersion.name == name,
                PromptVersion.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, prompt_version_id: uuid.UUID) -> PromptVersion | None:
        return await self._session.get(PromptVersion, prompt_version_id)

    async def list_for_name(self, *, project_id: uuid.UUID, name: str) -> list[PromptVersion]:
        result = await self._session.execute(
            select(PromptVersion)
            .where(PromptVersion.project_id == project_id, PromptVersion.name == name)
            .order_by(PromptVersion.version.desc())
        )
        return list(result.scalars().all())

    async def _next_version_number(self, *, project_id: uuid.UUID, name: str) -> int:
        result = await self._session.execute(
            select(func.max(PromptVersion.version)).where(
                PromptVersion.project_id == project_id, PromptVersion.name == name
            )
        )
        current_max = result.scalar_one_or_none()
        return (current_max or 0) + 1

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        name: str,
        template: str,
        created_by: uuid.UUID,
        activate: bool = True,
    ) -> PromptVersion:
        """Create the next version for `(project_id, name)`. If `activate`
        (the default), deactivates any currently-active version of the
        same name first, so at most one stays active."""
        version_number = await self._next_version_number(project_id=project_id, name=name)
        if activate:
            await self._deactivate_all(project_id=project_id, name=name)

        prompt_version = PromptVersion(
            project_id=project_id,
            name=name,
            version=version_number,
            template=template,
            is_active=activate,
            created_by=created_by,
        )
        self._session.add(prompt_version)
        await self._session.flush()
        return prompt_version

    async def _deactivate_all(self, *, project_id: uuid.UUID, name: str) -> None:
        for version in await self.list_for_name(project_id=project_id, name=name):
            version.is_active = False
        await self._session.flush()

    async def activate(self, prompt_version: PromptVersion) -> PromptVersion:
        await self._deactivate_all(project_id=prompt_version.project_id, name=prompt_version.name)
        prompt_version.is_active = True
        await self._session.flush()
        return prompt_version
