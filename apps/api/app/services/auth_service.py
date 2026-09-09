"""Login business logic: OAuth code -> User row -> session tokens.

Kept separate from app/auth/ (which knows about providers and JWTs but
never touches the database) so the DB-touching half of login is testable
like every other service, through a repository.
"""

from app.auth.jwt import create_access_token, create_refresh_token
from app.auth.providers import OAuthUserInfo
from app.config import Settings
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair


class AuthService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    async def get_or_create_user(self, info: OAuthUserInfo) -> User:
        user = await self._repository.get_by_email(info.email)
        if user is not None:
            return user
        return await self._repository.create(
            email=info.email,
            display_name=info.display_name,
            avatar_url=info.avatar_url,
        )

    def issue_tokens(self, user: User, *, settings: Settings) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(user_id=user.id, settings=settings),
            refresh_token=create_refresh_token(user_id=user.id, settings=settings),
        )
