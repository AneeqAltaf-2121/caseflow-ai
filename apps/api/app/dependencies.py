"""FastAPI dependency providers.

Routes depend on these functions rather than importing settings/engine/
session objects directly, so tests can override them via
`app.dependency_overrides`.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import TokenType, decode_token
from app.config import Settings, get_settings
from app.errors import UnauthorizedError
from app.integrations.embeddings import EmbeddingProvider, get_embedding_provider
from app.integrations.storage import StorageBackend


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped DB session bound to the app's session factory.

    The session factory is created once at startup (see app/main.py lifespan)
    and stored on `app.state`, rather than recreated per request.
    """
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


SettingsDep = Annotated[Settings, Depends(get_settings)]
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: SettingsDep,
) -> uuid.UUID:
    """Resolve the authenticated user id from the `Authorization: Bearer`
    header. This is the only place request handlers should learn "who is
    calling" — see app/auth/jwt.py for token verification.
    """
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")
    return decode_token(credentials.credentials, settings=settings, expected_type=TokenType.ACCESS)


CurrentUserIdDep = Annotated[uuid.UUID, Depends(get_current_user_id)]


async def get_storage(request: Request) -> StorageBackend:
    """The storage backend created once at startup (see app/main.py
    lifespan) — local disk or S3 depending on `settings.storage_backend`."""
    return request.app.state.storage_backend  # type: ignore[no-any-return]


StorageDep = Annotated[StorageBackend, Depends(get_storage)]


def get_embedding_provider_dep(settings: SettingsDep) -> EmbeddingProvider:
    """Constructed per-request rather than cached on app.state: every
    implementation is either stateless (mock/local) or opens its own
    short-lived HTTP client per call (OpenAI) — see
    app/integrations/embeddings.py."""
    return get_embedding_provider(settings)


EmbeddingProviderDep = Annotated[EmbeddingProvider, Depends(get_embedding_provider_dep)]
