import pytest

from app.cache import InMemoryCache, cache_key, hash_text


@pytest.mark.asyncio
async def test_in_memory_cache_get_set_roundtrip() -> None:
    cache = InMemoryCache()
    await cache.set("k", "v")
    assert await cache.get("k") == "v"


@pytest.mark.asyncio
async def test_in_memory_cache_miss_returns_none() -> None:
    cache = InMemoryCache()
    assert await cache.get("missing") is None


@pytest.mark.asyncio
async def test_in_memory_cache_delete() -> None:
    cache = InMemoryCache()
    await cache.set("k", "v")
    await cache.delete("k")
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_in_memory_cache_expires_past_ttl() -> None:
    cache = InMemoryCache()
    await cache.set("k", "v", ttl_seconds=-1)  # already expired
    assert await cache.get("k") is None


def test_cache_key_joins_parts_with_colon() -> None:
    assert cache_key("a", "b", "c") == "a:b:c"


def test_hash_text_is_deterministic_and_bounded() -> None:
    first = hash_text("hello world")
    second = hash_text("hello world")
    assert first == second
    assert len(first) == 16


def test_hash_text_differs_for_different_input() -> None:
    assert hash_text("a") != hash_text("b")
