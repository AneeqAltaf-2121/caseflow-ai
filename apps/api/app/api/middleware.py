"""Request ID + structured access logging + rate limiting middleware."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.cache import get_cache
from app.config import get_settings
from app.observability import get_latency_tracker
from app.rate_limit import check_rate_limit

REQUEST_ID_HEADER = "X-Request-ID"

logger = structlog.get_logger("caseflow.request")


async def rate_limit_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Phase 38: rejects a request with 429 before it reaches any route
    handler once its identity has exceeded its tier's window (see
    app/rate_limit.py). Runs outside request_context_middleware so a
    rate-limited request still gets a request id and an access log line.
    """
    decision = await check_rate_limit(request, cache=get_cache(), settings=get_settings())
    if decision is not None and not decision.allowed:
        logger.warning(
            "rate_limit_exceeded",
            path=request.url.path,
            limit=decision.limit,
            reset_after_seconds=decision.reset_after_seconds,
        )
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "rate_limited",
                    "message": "Too many requests. Please slow down.",
                    "request_id": None,
                }
            },
            headers={"Retry-After": str(decision.reset_after_seconds)},
        )
    response = await call_next(request)
    if decision is not None:
        response.headers["X-RateLimit-Limit"] = str(decision.limit)
        response.headers["X-RateLimit-Remaining"] = str(decision.remaining)
    return response


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
