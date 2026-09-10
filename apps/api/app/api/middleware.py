"""Request ID + structured access logging middleware."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

from app.observability import get_latency_tracker

REQUEST_ID_HEADER = "X-Request-ID"

logger = structlog.get_logger("caseflow.request")


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request ID, bind it to log context, log the access line,
    and record the request's duration into the process-wide P50/P95
    latency tracker (Phase 34) keyed by "METHOD /path"."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    response.headers[REQUEST_ID_HEADER] = request_id

    # request.url.path (not request.scope["route"].path) so unmatched
    # 404s still get a key, at the cost of one key per distinct id in a
    # path — acceptable for this project's route count and window size.
    route_key = f"{request.method} {request.url.path}"
    get_latency_tracker().record(route_key, duration_ms)

    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response
