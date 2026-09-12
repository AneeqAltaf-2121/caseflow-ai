import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from starlette.requests import Request

from app.auth.jwt import create_access_token
from app.cache import InMemoryCache
from app.config import Settings, get_settings
from app.rate_limit import RateLimitTier, check_rate_limit
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.asyncio


def _fake_request(*, path: str, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "scheme": "http",
        "server": ("testserver", 80),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "client": ("203.0.113.1", 12345),
        "query_string": b"",
    }
    return Request(scope)


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def test_health_and_ready_are_exempt() -> None:
    cache = InMemoryCache()
    settings = Settings()
    for _ in range(10):
        decision = await check_rate_limit(
            _fake_request(path="/health"), cache=cache, settings=settings
        )
        assert decision is None


async def test_requests_within_the_limit_are_allowed() -> None:
    cache = InMemoryCache()
    settings = Settings()
    request = _fake_request(path="/projects")

    for _ in range(3):
        decision = await check_rate_limit(request, cache=cache, settings=settings)
        assert decision is not None
        assert decision.allowed is True


async def test_exceeding_the_limit_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.rate_limit as rate_limit_module

    monkeypatch.setattr(
        rate_limit_module,
        "DEFAULT_TIER",
        RateLimitTier(name="default", max_requests=2, window_seconds=60),
    )
    cache = InMemoryCache()
    settings = Settings()
    request = _fake_request(path="/projects")

    first = await check_rate_limit(request, cache=cache, settings=settings)
    second = await check_rate_limit(request, cache=cache, settings=settings)
    third = await check_rate_limit(request, cache=cache, settings=settings)

    assert first is not None and first.allowed is True
    assert second is not None and second.allowed is True
    assert third is not None and third.allowed is False
    assert third.remaining == 0


async def test_different_users_get_independent_buckets() -> None:
    cache = InMemoryCache()
    settings = Settings()
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    request_a = _fake_request(path="/projects", headers=_auth_headers(user_a))
    request_b = _fake_request(path="/projects", headers=_auth_headers(user_b))

    for _ in range(5):
        decision_a = await check_rate_limit(request_a, cache=cache, settings=settings)
        assert decision_a is not None and decision_a.allowed is True

    # user_b's own budget is untouched by user_a's requests.
    decision_b = await check_rate_limit(request_b, cache=cache, settings=settings)
    assert decision_b is not None
    assert decision_b.remaining == decision_b.limit - 1


async def test_auth_tier_is_stricter_than_default_tier() -> None:
    cache = InMemoryCache()
    settings = Settings()

    auth_decision = await check_rate_limit(
        _fake_request(path="/auth/google/login"), cache=cache, settings=settings
    )
    default_decision = await check_rate_limit(
        _fake_request(path="/projects"), cache=cache, settings=settings
    )
    assert auth_decision is not None and default_decision is not None
    assert auth_decision.limit < default_decision.limit


async def test_rate_limited_request_returns_429_with_retry_after_end_to_end(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.rate_limit as rate_limit_module

    monkeypatch.setattr(
        rate_limit_module,
        "DEFAULT_TIER",
        RateLimitTier(name="default", max_requests=2, window_seconds=60),
    )

    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="rl@x.com", display_name="RL")
        await session.commit()
    headers = _auth_headers(owner.id)

    first = await api_client.get("/projects", headers=headers)
    second = await api_client.get("/projects", headers=headers)
    third = await api_client.get("/projects", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limited"
    assert "Retry-After" in third.headers
