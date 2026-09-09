# Contributing to CaseFlow AI

## Branch strategy

CaseFlow AI uses trunk-based development on `main`.

- `main` is always deployable. CI must pass before merge.
- Work happens on short-lived branches cut from `main`:
  - `feat/<short-description>` — new functionality
  - `fix/<short-description>` — bug fixes
  - `chore/<short-description>` — tooling, deps, docs, refactors
  - `spike/<short-description>` — throwaway exploration, not meant to merge as-is
- Open a PR into `main`; squash-merge once CI is green.
- Avoid long-running feature branches — prefer small, incremental PRs behind
  feature flags or additive schema changes over big-bang merges.
- Tag releases on `main` as `vX.Y.Z` (see `docs/decisions/` for versioning
  rationale once the project reaches a stable API).

## Commit messages

Use short, imperative subject lines (e.g. `Add document upload endpoint`).
Reference the relevant phase from the build plan in the body when useful.

## Code organization

See `docs/architecture.md` for the system architecture and
`docs/domain-model.md` for the core entities. Architecture decisions with
long-term consequences are recorded as ADRs under `docs/decisions/`.

## Local development

See the "Local Development" section of `README.md` once `apps/api` and
`apps/web` are runnable (Phase 2 / Phase 5).

## Testing

- Backend: `pytest` from `apps/api` (unit, repository, service, API layers).
- Frontend: `vitest` / React Testing Library from `apps/web`, Playwright for E2E.
- CI (`.github/workflows/`) runs lint, typecheck, and tests on every PR and
  blocks merge on failure (added in Phase 26).
