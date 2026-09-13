# End-to-end tests (Phase 41)

Playwright drives a real browser against a real, running frontend +
backend — nothing here mocks the network. Start both before running the
suite.

## Option A — Docker Compose (Phase 39)

```bash
docker compose up --build -d
npm --prefix apps/web run test:e2e
```

## Option B — no Docker, zero external infrastructure

The backend can run standalone against a throwaway SQLite file and an
in-process background worker (`RUN_INLINE_WORKER=true` — see
`app/jobs/inline_worker.py`), so a real upload actually finishes
processing without a separate worker process or a real Redis:

```bash
# Terminal 1 — backend
cd apps/api
DATABASE_URL=sqlite+aiosqlite:///./e2e.db \
ENVIRONMENT=test ALLOW_MOCK_OAUTH=true RUN_INLINE_WORKER=true \
LLM_PROVIDER=mock EMBEDDING_PROVIDER=local \
CORS_ORIGINS=http://localhost:3000 \
  alembic upgrade head
DATABASE_URL=sqlite+aiosqlite:///./e2e.db \
ENVIRONMENT=test ALLOW_MOCK_OAUTH=true RUN_INLINE_WORKER=true \
LLM_PROVIDER=mock EMBEDDING_PROVIDER=local \
CORS_ORIGINS=http://localhost:3000 \
  uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2 — frontend (production build, so NEXT_PUBLIC_API_URL is
# actually inlined — see next.config.ts's comment on that)
cd apps/web
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run build
npm run start

# Terminal 3 — the suite itself
npm --prefix apps/web run test:e2e
```

`ENVIRONMENT=test` here also selects the in-memory cache and stub job
broker (Phase 33/Phase 7) — fine for this since `RUN_INLINE_WORKER=true`
means one process handles both serving requests and running jobs.
`EMBEDDING_PROVIDER=local` (not `mock`) is real, lexical (hashing-trick)
similarity — enough for the sample PDF's question to actually retrieve
the right passage, unlike the zero-signal mock provider.

## What's covered

`full-journey.spec.ts`: login (dev/mock OAuth) -> create a project ->
upload a PDF -> wait for ingestion to finish -> ask a question ->
receive a grounded, cited answer -> open the citation. Each run uses a
fresh email and project name so it can run repeatedly against a
persistent dev database without colliding with a previous run.
