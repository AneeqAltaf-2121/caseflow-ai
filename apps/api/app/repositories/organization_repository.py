import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, organization_id: uuid.UUID) -> Organization | None:
        return await self._session.get(Organization, organization_id)

    async def get_by_slug(self, slug: str) -> Organization | None:
        result = await self._session.execute(select(Organization).where(Organization.slug == slug))
        return result.scalar_one_or_none()

    async def create(self, *, name: str, slug: str) -> Organization:
        organization = Organization(name=name, slug=slug)
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def get_or_create_personal(
        self, *, user_id: uuid.UUID, display_name: str
    ) -> Organization:
        """Every user needs at least one Organization to create a project
        under (see docs/domain-model.md) but there's no organizations UI/API
        yet — so the first time a user needs one, they get a personal one
        keyed deterministically off their own id, instead of a shared
        onboarding flow that doesn't exist yet."""
        slug = f"user-{user_id.hex[:12]}"
        existing = await self.get_by_slug(slug)
        if existing is not None:
            return existing
        return await self.create(name=f"{display_name}'s workspace", slug=slug)
