# 004 — OAuth login + stateless JWT sessions

## Status
Accepted

## Context
Phase 4 needs to turn "an anonymous caller" into "an authenticated User row"
so routes stop trusting a client-supplied `user_id` (see
`app/services/project_service.py`'s pre-Phase-4 note). Options considered
for session state: server-side sessions (Redis-backed) vs. stateless JWTs;
options for identity: CaseFlow-managed passwords vs. OAuth against a
third-party identity provider.

## Decision
- Identity comes from OAuth (Google to start; `app/auth/providers.py` is a
  small `OAuthProvider` protocol so a second provider is a new class, not a
  rewrite). CaseFlow never stores a password, matching `docs/domain-model.md`.
- Sessions are stateless HS256 JWTs: a short-lived access token (60 min
  default) and a longer-lived refresh token (30 days), distinguished by a
  `type` claim so one can't be replayed as the other. No server-side session
  table or Redis lookup is needed to validate a request.
- A `MockOAuthProvider` (`app/auth/providers.py`) is wired in for
  development and tests, gated off in production regardless of
  configuration, so the full login flow — and everything built on top of
  it — is testable without a registered OAuth app or network access.

## Rationale
- Stateless JWTs avoid a Redis round-trip on every authenticated request
  and keep the API horizontally scalable with no shared session store —
  consistent with Redis being reserved for jobs/cache (ADR 003), not auth.
- OAuth avoids owning credential storage, password reset flows, and the
  breach surface that comes with them, appropriate for a platform whose
  users are already Google/Microsoft-identified in most target
  organizations.
- Access/refresh separation bounds the blast radius of a leaked access
  token (short TTL) while keeping the refresh flow low-friction.

## Consequences
- Revoking a single compromised access token before it expires isn't
  possible without adding a denylist; the short access-token TTL is the
  mitigation until that's needed.
- Every authorization decision downstream (`ProjectService.require_role`,
  and the same pattern for documents/conversations/evaluations in later
  phases) can assume `user_id` is already verified — routes never accept
  it as a parameter again.
- Adding a second real provider (e.g. Microsoft/GitHub) is additive: a new
  `OAuthProvider` implementation registered in `get_provider`, no schema
  change.
