"""Request ID + structured access logging middleware."""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-ID"

logger = structlog.get_logger("caseflow.request")


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Assign a request ID, bind it to log context, and log the access line."""
    request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
    request.state.request_id = request_id

    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    response.headers[REQUEST_ID_HEADER] = request_id

    logger.info(
        "request_completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
    )
    return response
