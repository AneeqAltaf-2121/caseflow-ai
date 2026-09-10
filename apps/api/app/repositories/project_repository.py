import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.project import Project, ProjectMember, ProjectRole


class ProjectRepository:
    """Data access for Project and ProjectMember.

    No authorization decisions here — "can this user see this project" is a
    service-layer concern (see app/services/project_service.py).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        organization_id: uuid.UUID,
        name: str,
        description: str | None,
        created_by: uuid.UUID,
    ) -> Project:
        project = Project(
            organization_id=organization_id,
            name=name,
            description=description,
            created_by=created_by,
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None:
        return await self._session.get(Project, project_id)

    async def list_for_user(self, user_id: uuid.UUID) -> list[Project]:
        result = await self._session.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(ProjectMember.user_id == user_id)
            .options(selectinload(Project.members))
            .order_by(Project.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_member(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        role: ProjectRole,
        invited_by: uuid.UUID | None,
    ) -> ProjectMember:
        member = ProjectMember(
            project_id=project_id, user_id=user_id, role=role, invited_by=invited_by
        )
        self._session.add(member)
        await self._session.flush()
        return member

    async def get_member(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> ProjectMember | None:
        result = await self._session.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id, ProjectMember.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list_members(self, project_id: uuid.UUID) -> list[ProjectMember]:
        result = await self._session.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at.asc())
        )
        return list(result.scalars().all())

    async def update(
        self, project: Project, *, name: str | None, description: str | None, has_description: bool
    ) -> Project:
        if name is not None:
            project.name = name
        if has_description:
            project.description = description
        await self._session.flush()
        # `updated_at` is set by an onupdate=func.now() DB-side default, so
        # after an UPDATE (unlike an INSERT) SQLAlchemy doesn't know its new
        # value and marks it expired — refresh it now rather than leaving a
        # lazy-load for whoever reads it next (e.g. Pydantic serialization),
        # which would fail outside of a greenlet context.
        await self._session.refresh(project, attribute_names=["updated_at"])
        return project

    async def delete(self, project: Project) -> None:
        await self._session.delete(project)
        await self._session.flush()

    async def remove_member(self, member: ProjectMember) -> None:
        await self._session.delete(member)
        await self._session.flush()
