from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Import models so Base.metadata is fully populated before create_all runs.
import app.models  # noqa: F401,E402
from app.database import Base
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


@pytest_asyncio.fixture
async def db_session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """An in-memory SQLite session factory with the full schema applied.

    Used for repository/service unit tests and for overriding the app's
    real (Postgres-bound) session factory in route-level tests, so neither
    needs a live Postgres instance.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(bind=engine, expire_on_commit=False)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    async with db_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def api_client(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """An async client whose DB-backed routes read/write the in-memory
    SQLite schema from `db_session_factory` instead of the real Postgres
    URL. Skips the app's lifespan (no real engine/Redis needed for routes
    that only touch app.state.session_factory) and stays on the same event
    loop as the async fixtures it composes with, unlike the sync TestClient.
    """
    app = create_app()
    app.state.session_factory = db_session_factory

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
