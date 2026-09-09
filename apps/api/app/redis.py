"""Redis client setup (cache + job broker connectivity checks).

Cache-key and job-queue usage are added in Phase 7 / Phase 20. For now this
module only provides the connection used by the /ready health check.
"""

from redis.asyncio import Redis

from app.config import Settings


def create_redis_client(settings: Settings) -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)
