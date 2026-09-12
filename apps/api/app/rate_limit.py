"""Rate limiting (Phase 38): a fixed-window counter per (client identity,
limit tier) built on Phase 33's Cache abstraction — Redis in production,
in-memory in tests, both already wired to a process-wide singleton via
app.cache.get_cache(), so this needs no infrastructure of its own.

Two tiers, not one uniform limit:
- AUTH: a strict cap on the OAuth/token endpoints, keyed by client IP
  (there's no authenticated user yet at that point) — brute-force /
  credential-stuffing protection.
- DEFAULT: a generous cap on everything else, keyed by user id when a
  valid access token is present (so one user's usage doesn't get
  conflated with another behind the same IP/NAT), falling back to IP
  when it isn't.

A window is a fixed wall-clock bucket (`now // window_seconds`), not a
sliding one — simpler, and precise enough for abuse protection rather
than perfectly smooth throttling.
"""

import time
from dataclasses import dataclass

from fastapi import Request

from app.auth.jwt import TokenType, decode_token
from app.cache import Cache, cache_key
from app.config import Settings


@dataclass(frozen=True)
class RateLimitTier:
    name: str
    max_requests: int
    window_seconds: int


AUTH_TIER = RateLimitTier(name="auth", max_requests=20, window_seconds=60)
DEFAULT_TIER = RateLimitTier(name="default", max_requests=300, window_seconds=60)

# Path prefixes that get the strict AUTH tier instead of DEFAULT.
AUTH_PATH_PREFIX = "/auth"

# Never rate limited — an orchestrator hammering /health for liveness
# probes shouldn't be treated as abuse.
EXEMPT_PATHS = {"/health", "/ready"}


def _client_identity(request: Request, settings: Settings) -> str:
    """A verified user id when the request carries one, else the client
    IP. Decoding is best-effort and silent — an invalid/missing/expired
    token here just falls back to IP-based limiting; rejecting the
    request for a bad token is the auth dependency's job, not this one's.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        try:
            user_id = decode_token(token, settings=settings, expected_type=TokenType.ACCESS)
            return f"user:{user_id}"
        except Exception:  # noqa: BLE001 - any decode failure just falls through to IP
            pass
    client = request.client
    return f"ip:{client.host}" if client else "ip:unknown"


def _tier_for_path(path: str) -> RateLimitTier | None:
    if path in EXEMPT_PATHS:
        return None
    if path.startswith(AUTH_PATH_PREFIX):
        return AUTH_TIER
    return DEFAULT_TIER


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


async def check_rate_limit(
    request: Request, *, cache: Cache, settings: Settings
) -> RateLimitDecision | None:
    """Returns None for an exempt path, else the decision for this
    request — callers increment the counter as a side effect of calling
    this, so this must be called at most once per request."""
    tier = _tier_for_path(request.url.path)
    if tier is None:
        return None

    identity = _client_identity(request, settings)
    window = int(time.time()) // tier.window_seconds
    key = cache_key("rate_limit", tier.name, identity, str(window))

    count = await cache.increment(key, ttl_seconds=tier.window_seconds)
    reset_after = tier.window_seconds - (int(time.time()) % tier.window_seconds)

    return RateLimitDecision(
        allowed=count <= tier.max_requests,
        limit=tier.max_requests,
        remaining=max(0, tier.max_requests - count),
        reset_after_seconds=reset_after,
    )
