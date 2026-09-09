"""Structured application errors.

Routes/services raise `CaseFlowError` subclasses instead of returning ad-hoc
error dicts or raw HTTPException, so every error response has a consistent
shape: {"error": {"code": ..., "message": ..., "request_id": ...}}.
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse


class CaseFlowError(Exception):
    """Base class for all application-raised errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    code: str = "internal_error"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or "An unexpected error occurred."
        super().__init__(self.message)


class NotFoundError(CaseFlowError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ValidationError(CaseFlowError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    code = "validation_error"


class UnauthorizedError(CaseFlowError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(CaseFlowError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class ConflictError(CaseFlowError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


def _error_body(code: str, message: str, request_id: str | None) -> dict:
    return {"error": {"code": code, "message": message, "request_id": request_id}}


async def caseflow_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, CaseFlowError)  # noqa: S101 - registered only for CaseFlowError
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, request_id),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body("internal_error", "An unexpected error occurred.", request_id),
    )
