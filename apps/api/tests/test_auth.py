import uuid

import httpx
import pytest

from app.auth.jwt import TokenType, create_access_token, create_refresh_token, decode_token
from app.config import get_settings
from app.errors import UnauthorizedError


def test_access_token_round_trips_user_id() -> None:
    settings = get_settings()
    user_id = uuid.uuid4()
    token = create_access_token(user_id=user_id, settings=settings)
    assert decode_token(token, settings=settings, expected_type=TokenType.ACCESS) == user_id


def test_refresh_token_rejected_as_access_token() -> None:
    settings = get_settings()
    token = create_refresh_token(user_id=uuid.uuid4(), settings=settings)
    with pytest.raises(UnauthorizedError):
        decode_token(token, settings=settings, expected_type=TokenType.ACCESS)


def test_garbage_token_is_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        decode_token("not-a-jwt", settings=get_settings(), expected_type=TokenType.ACCESS)


async def test_mock_login_flow_issues_working_session(api_client: httpx.AsyncClient) -> None:
    login_response = await api_client.get(
        "/auth/mock/login", params={"email": "newuser@example.com"}
    )
    # The mock provider ignores the query param and takes the email as the
    # "code" via authorize_url's state; simulate the redirect target directly.
    assert login_response.status_code == 200
    authorize_url = login_response.json()["authorize_url"]
    assert "/auth/mock/" in authorize_url

    callback_response = await api_client.get(
        "/auth/mock/callback", params={"code": "newuser@example.com"}
    )
    assert callback_response.status_code == 200
    tokens = callback_response.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    me_response = await api_client.get(
        "/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "newuser@example.com"

    refresh_response = await api_client.post(
        "/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_response.status_code == 200
    assert refresh_response.json()["access_token"]


async def test_mock_provider_disabled_in_production(api_client: httpx.AsyncClient) -> None:
    get_settings().environment = "production"  # cached singleton; restore after
    try:
        response = await api_client.get("/auth/mock/login", params={"email": "x@example.com"})
        assert response.status_code == 422
    finally:
        get_settings().environment = "development"


async def test_me_without_token_is_unauthorized(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/auth/me")
    assert response.status_code == 401
