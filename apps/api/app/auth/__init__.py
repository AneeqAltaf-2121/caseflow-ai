"""Authentication: OAuth login providers + JWT session tokens.

Flow: client hits GET /auth/{provider}/login, is redirected to the
provider's consent screen, the provider redirects back to
GET /auth/{provider}/callback with a code, we exchange it for the user's
profile (email/name/avatar), get-or-create a User row, and issue a JWT
access token the client sends as `Authorization: Bearer <token>` on every
subsequent request. See app/auth/jwt.py and app/auth/providers.py.
"""
