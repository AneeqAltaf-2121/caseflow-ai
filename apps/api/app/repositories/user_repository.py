import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Data access for User. No business logic or authorization here —
    that belongs in a service (see docs/domain-model.md)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def create(self, *, email: str, display_name: str, avatar_url: str | None = None) -> User:
        user = User(email=email, display_name=display_name, avatar_url=avatar_url)
        self._session.add(user)
        await self._session.flush()
        return user
