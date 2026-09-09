"""Session JWT issuance and verification.

Access tokens are short-lived and carry only the user id (`sub`) plus a
token type, so a stolen access token can't be replayed as a refresh token
and vice versa. Nothing here touches the database — callers still load the
User row via UserRepository once the id is verified.
"""

import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

import jwt

from app.config import Settings
from app.errors import UnauthorizedError


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


def _create_token(
    *, user_id: uuid.UUID, settings: Settings, token_type: TokenType, ttl: timedelta
) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type.value,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: uuid.UUID, settings: Settings) -> str:
    return _create_token(
        user_id=user_id,
        settings=settings,
        token_type=TokenType.ACCESS,
        ttl=timedelta(minutes=settings.jwt_access_token_ttl_minutes),
    )


def create_refresh_token(*, user_id: uuid.UUID, settings: Settings) -> str:
    return _create_token(
        user_id=user_id,
        settings=settings,
        token_type=TokenType.REFRESH,
        ttl=timedelta(days=settings.jwt_refresh_token_ttl_days),
    )


def decode_token(token: str, *, settings: Settings, expected_type: TokenType) -> uuid.UUID:
    """Verify signature/expiry/type and return the embedded user id.

    Raises UnauthorizedError (never a raw jwt exception) so route code
    doesn't need to know about PyJWT.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Session expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid session token.") from exc

    if payload.get("type") != expected_type.value:
        raise UnauthorizedError("Wrong token type for this operation.")

    try:
        return uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise UnauthorizedError("Invalid session token.") from exc
