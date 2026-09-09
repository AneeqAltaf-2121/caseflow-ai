"""FastAPI dependency providers.

Routes depend on these functions rather than importing settings/engine/
session objects directly, so tests can override them via
`app.dependency_overrides`.
"""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings


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
