"""Authentication routes: OAuth login/callback, token refresh, current user.

routes -> AuthService -> UserRepository, same layering as every other
resource (see docs/domain-model.md). Provider selection and JWT mechanics
live in app/auth/ rather than here.
"""

from fastapi import APIRouter

from app.auth.jwt import TokenType, decode_token
from app.auth.providers import get_provider, new_state
from app.dependencies import CurrentUserIdDep, DbSessionDep, SettingsDep
from app.errors import NotFoundError
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthorizeUrlRead, RefreshRequest, TokenPair, UserRead
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/{provider_name}/login", response_model=AuthorizeUrlRead)
async def login(
    provider_name: str, settings: SettingsDep, email: str | None = None
) -> AuthorizeUrlRead:
    """Return the URL to redirect the browser to for login.

    `email` is honored only by the mock provider (dev/test convenience —
    it becomes the "code" the mock callback resolves to a user); real
    providers always get a fresh random anti-CSRF state instead.
    """
    provider = get_provider(provider_name, settings)
    state = email if (provider_name == "mock" and email) else new_state()
    return AuthorizeUrlRead(authorize_url=provider.authorize_url(state=state), state=state)


@router.get("/{provider_name}/callback", response_model=TokenPair)
async def callback(
    provider_name: str, code: str, settings: SettingsDep, db: DbSessionDep
) -> TokenPair:
    provider = get_provider(provider_name, settings)
    info = await provider.exchange_code(code=code)

    service = AuthService(UserRepository(db))
    user = await service.get_or_create_user(info)
    return service.issue_tokens(user, settings=settings)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, settings: SettingsDep, db: DbSessionDep) -> TokenPair:
    user_id = decode_token(
        payload.refresh_token, settings=settings, expected_type=TokenType.REFRESH
    )
    repository = UserRepository(db)
    user = await repository.get_by_id(user_id)
    if user is None:
        raise NotFoundError("User no longer exists.")

    service = AuthService(repository)
    return service.issue_tokens(user, settings=settings)


@router.get("/me", response_model=UserRead)
async def me(current_user_id: CurrentUserIdDep, db: DbSessionDep) -> UserRead:
    user = await UserRepository(db).get_by_id(current_user_id)
    if user is None:
        raise NotFoundError("User no longer exists.")
    return UserRead.model_validate(user)
