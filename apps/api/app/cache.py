"""Cache abstraction (Phase 33): query embeddings and retrieval results
are expensive to recompute (an embedding call, a hybrid search joining
vector similarity and BM25 across every chunk in a project) and cheap to
look up by a key built from the query and the exact configuration that
produced the cached value.

`ENVIRONMENT=test` gets an in-memory, process-local cache instead of a
real Redis connection (this sandbox has no Redis server), so the full
get/set/miss path is exercised in tests without a broker running — same
split as app/jobs/__init__.py's StubBroker for the job queue.

Every cache key built with `cache_key()` must include the versions of
whatever produced the value (embedding provider name + dimensions,
retriever version, ...): a version bump changes the key, so a stale
cached value is simply never looked up again rather than needing an
explicit invalidation step. Values still carry a TTL (default 5 minutes)
as a second line of defense against staleness this project doesn't
attempt to solve with write-time invalidation (a new upload should
arguably bust a project's retrieval cache immediately; here it just
expires) — a documented, deliberate simplification for a project with no
live production traffic to tune against.
"""

import hashlib
import time
from typing import Protocol

from redis.asyncio import Redis

from app.config import get_settings

DEFAULT_TTL_SECONDS = 300


def cache_key(*parts: str) -> str:
    """Joins `parts` with ":" — callers pass every version/identity that
    affects the cached value (embedding provider, retriever version,
    project id, ...) as separate parts so a version bump alone changes
    the key. Long or free-text parts (a raw query string) should be
    hashed by the caller before passing them in, to keep keys bounded and
    avoid leaking raw query text into a cache backend's key listing."""
    return ":".join(parts)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(
        self, key: str, value: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> None: ...
    async def delete(self, key: str) -> None: ...
    async def increment(self, key: str, *, ttl_seconds: int) -> int: ...


class RedisCache:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def increment(self, key: str, *, ttl_seconds: int) -> int:
        """Atomic INCR, with the expiry set only on the increment that
        creates the key — the standard Redis fixed-window counter
        pattern (Phase 38 rate limiting). A concurrent burst of requests
        racing this still gets a correct count: INCR itself is atomic,
        only the "was this the first one" expiry check reads back the
        result, and setting an already-set TTL again would just be a
        harmless no-op if two requests both saw value == 1."""
        value = await self._client.incr(key)
        if value == 1:
            await self._client.expire(key, ttl_seconds)
        return value


class InMemoryCache:
    """Dict-backed, process-local cache for tests/dev without a real
    Redis server. TTLs are tracked but not actively swept — a get() past
    expiry is treated as a miss, deleting the entry lazily, which mirrors
    Redis's own passive-expiry behavior closely enough for tests."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    async def set(self, key: str, value: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._store[key] = (value, time.monotonic() + ttl_seconds)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def increment(self, key: str, *, ttl_seconds: int) -> int:
        """Not atomic (no concurrent access within a single test process
        needs it to be) and, unlike RedisCache, resets the TTL on every
        call rather than only the first — a documented simplification
        that's harmless for this backend's only real use, single-process
        tests, where windows aren't asserted down to the second."""
        current = await self.get(key)
        new_value = int(current) + 1 if current is not None else 1
        await self.set(key, str(new_value), ttl_seconds=ttl_seconds)
        return new_value


def _create_cache() -> Cache:
    settings = get_settings()
    if settings.environment == "test":
        return InMemoryCache()
    from app.redis import create_redis_client

    return RedisCache(create_redis_client(settings))


_cache: Cache = _create_cache()


def get_cache() -> Cache:
    """The process-wide cache singleton — one InMemoryCache (tests) or
    one Redis connection (everywhere else), never a fresh instance per
    call, so entries actually persist between lookups."""
    return _cache
