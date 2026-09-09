"""Liveness/readiness endpoints.

/health — process is up. Never touches dependencies; used by orchestrators
for liveness probes.
/ready — process can actually serve traffic (DB + Redis reachable). Used
for readiness probes / load balancer health checks.
"""

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.errors import CaseFlowError

router = APIRouter(tags=["health"])


class DependencyUnavailableError(CaseFlowError):
    status_code = 503
    code = "dependency_unavailable"


@router.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
async def ready(request: Request) -> dict:
    checks: dict[str, str] = {}

    session_factory = request.app.state.session_factory
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure as not-ready
        checks["database"] = f"error: {exc}"

    redis_client = request.app.state.redis_client
    try:
        await redis_client.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    if any(v != "ok" for v in checks.values()):
        raise DependencyUnavailableError(f"Not ready: {checks}")

    return {"status": "ready", "checks": checks}
