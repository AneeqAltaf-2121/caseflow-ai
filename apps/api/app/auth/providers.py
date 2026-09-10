"""OAuth provider abstraction.

`OAuthProvider` is the interface routes depend on; `GoogleOAuthProvider` is
the real implementation (authorization-code flow against Google's OpenID
endpoints). `MockOAuthProvider` is a stand-in used in development and tests
so the whole login flow is exercisable without registering a real OAuth
app or holding network access. `get_provider()` is the single place that
decides which one a request gets, and it refuses to hand out the mock in
production even if misconfigured.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.errors import ValidationError

GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass(frozen=True)
class OAuthUserInfo:
    email: str
    display_name: str
    avatar_url: str | None = None


class OAuthProvider(Protocol):
    name: str

    def authorize_url(self, *, state: str) -> str: ...

    async def exchange_code(self, *, code: str) -> OAuthUserInfo: ...


class GoogleOAuthProvider:
    name = "google"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authorize_url(self, *, state: str) -> str:
        params = {
            "client_id": self._settings.oauth_client_id,
            "redirect_uri": self._settings.oauth_redirect_url,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
        }
        return f"{GOOGLE_AUTHORIZE_URL}?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> OAuthUserInfo:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": self._settings.oauth_client_id,
                    "client_secret": self._settings.oauth_client_secret,
                    "redirect_uri": self._settings.oauth_redirect_url,
                    "grant_type": "authorization_code",
                },
            )
            if token_response.status_code != 200:
                raise ValidationError("Failed to exchange authorization code with Google.")
            access_token = token_response.json()["access_token"]

            userinfo_response = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_response.status_code != 200:
                raise ValidationError("Failed to fetch user profile from Google.")
            profile = userinfo_response.json()

        return OAuthUserInfo(
            email=profile["email"],
            display_name=profile.get("name") or profile["email"],
            avatar_url=profile.get("picture"),
        )


class MockOAuthProvider:
    """Dev/test-only provider: treats the "code" as the desired email.

    `GET /auth/mock/login?email=you@example.com` returns an authorize_url
    that, when followed, calls back with that email as the code — no
    network access, no registered OAuth app. Never selected in production
    (see get_provider below), regardless of `allow_mock_oauth`.
    """

    name = "mock"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authorize_url(self, *, state: str) -> str:
        # Unlike Google, the mock "provider" never actually redirects a
        # browser anywhere — the frontend's dev login calls
        # exchange_code("mock", email) directly (see lib/auth-context.tsx).
        # This URL exists only so /auth/mock/login has the same response
        # shape as a real provider for anything that does call it (tests).
        params = {"code": state, "state": state}
        return f"/auth/mock/callback?{urlencode(params)}"

    async def exchange_code(self, *, code: str) -> OAuthUserInfo:
        email = code.strip()
        if "@" not in email:
            raise ValidationError("Mock provider expects the code to look like an email.")
        return OAuthUserInfo(email=email, display_name=email.split("@")[0], avatar_url=None)


_PROVIDERS: dict[str, type] = {
    "google": GoogleOAuthProvider,
    "mock": MockOAuthProvider,
}


def get_provider(name: str, settings: Settings) -> OAuthProvider:
    provider_cls = _PROVIDERS.get(name)
    if provider_cls is None:
        raise ValidationError(f"Unknown auth provider '{name}'.")

    if provider_cls is MockOAuthProvider and settings.is_production:
        raise ValidationError("The mock auth provider is disabled in production.")
    if provider_cls is MockOAuthProvider and not settings.allow_mock_oauth:
        raise ValidationError("The mock auth provider is disabled.")

    return provider_cls(settings)


def new_state() -> str:
    return uuid.uuid4().hex
