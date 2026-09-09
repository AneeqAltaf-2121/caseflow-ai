# 003 — Use Redis + Dramatiq for background jobs

## Status
Accepted

## Context
Document ingestion (extraction, chunking, embedding) and evaluation runs
are too slow to run inline in an HTTP request. CaseFlow needs a job queue
with retries, backoff, and dead-lettering. Options considered: Celery,
Dramatiq, RQ, all backed by Redis.

## Decision
Use Redis as the broker/result backend, with Dramatiq as the task runner.

## Rationale
- Dramatiq has a simpler API surface than Celery (no separate result
  backend config, fewer footguns) while still supporting retries with
  backoff, rate limiting, and dead-letter queues out of the box.
- Redis is already in the stack as a cache (see `docs/architecture.md`),
  so no new infrastructure component is introduced — only a new logical
  use (namespaced separately from cache keys).
- RQ was considered but has weaker retry/backoff ergonomics than Dramatiq
  for this project's needs (multi-attempt ingestion with exponential
  backoff, per Phase 7/22).

## Consequences
- Job payloads and results must be JSON-serializable.
- Worker processes are a separate deployable (`apps/api/app/jobs` run via
  a Dramatiq worker entrypoint), containerized separately from the API in
  Phase 24 and scaled independently in Phase 27.
- If job volume or fan-out patterns outgrow Redis-backed Dramatiq, a
  managed queue (SQS) is a future ADR — job definitions are kept in
  `app/jobs` behind a thin interface for that reason.
