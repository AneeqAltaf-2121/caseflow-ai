# CaseFlow AI

[![CI](https://github.com/AneeqAltaf-2121/caseflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/AneeqAltaf-2121/caseflow-ai/actions/workflows/ci.yml)

**CaseFlow AI** is a full-stack AI research and document intelligence platform for organizing document collections, performing semantic and hybrid search, generating citation-grounded answers and reports, and evaluating AI system quality across models, prompts, and retrieval strategies.

The project is built as a production-oriented AI platform rather than a standalone "chat with documents" demo. Its architecture is organized around multi-user workspaces, asynchronous document processing, retrieval-augmented generation (RAG), AI evaluation, observability, and reproducible model experimentation.

> **Status:** v1.0.0. Every layer described below — auth, document ingestion, hybrid RAG, evaluation, human review, observability, the frontend, Docker, CI, and AWS infrastructure-as-code — is implemented and tested. See [Current Development Status](#current-development-status) for what shipped and [Roadmap](#roadmap) for the full milestone history.

---

## Why CaseFlow AI?

Modern document AI systems need more than an LLM connected to a vector database.

CaseFlow AI is designed to provide the infrastructure required to build, inspect, evaluate, and improve document-grounded AI workflows:

- organize documents into isolated project workspaces;
- process large document uploads asynchronously;
- retrieve relevant evidence using semantic and hybrid search;
- generate answers grounded in source material;
- trace answers back to source passages through citations;
- compare models, prompts, and retrieval strategies;
- measure faithfulness, relevance, completeness, hallucinations, latency, and cost;
- review low-confidence AI outputs;
- track failures and system behavior through structured observability.

---

## Core Capabilities

### Document Intelligence

- Multi-user project workspaces
- Document upload and management
- Asynchronous document ingestion
- Text extraction and normalization
- Token-aware chunking
- Embedding generation
- Semantic vector search
- Hybrid retrieval
- Reranking

### Grounded AI

- Retrieval-augmented generation (RAG)
- Citation-grounded question answering
- Source passage inspection
- Persistent research conversations
- Citation-grounded summaries and reports
- Insufficient-evidence handling

### AI Evaluation

- Prompt and model version tracking
- Retrieval quality metrics
- LLM-as-a-judge evaluation
- Faithfulness scoring
- Completeness scoring
- Relevance scoring
- Hallucination analysis
- Citation validation
- Model and prompt comparison
- Evaluation regression tracking

### Production Engineering

- OAuth authentication
- Role-based project authorization
- PostgreSQL persistence
- Redis-backed background jobs
- Redis caching
- Retry and failure handling
- Structured logging
- Cost and latency tracking
- Human review workflows
- Dockerized local development
- Automated testing (backend, frontend, Docker, Terraform, end-to-end)
- CI/CD (GitHub Actions)
- AWS infrastructure as code (Terraform — validated, no live deployment; see `infra/aws/README.md` and `docs/deployment.md`)

---

## Architecture

CaseFlow AI is organized as a monorepo:

```text
caseflow-ai/
├── apps/
│   ├── api/              # FastAPI backend (+ Dockerfile — shared by api/worker/migrate)
│   └── web/              # Next.js / React / TypeScript frontend (+ Dockerfile)
│
├── packages/
│   ├── evals/            # AI evaluation framework (installable standalone)
│   └── shared/           # Shared schemas and utilities
│
├── infra/
│   └── aws/              # Terraform IaC — modules/ + environments/dev (validated, not deployed)
│
├── docs/
│   ├── decisions/        # Architecture Decision Records (ADRs)
│   ├── architecture.md
│   ├── domain-model.md
│   ├── deployment.md
│   └── benchmarks.md
│
├── scripts/               # Development and operational scripts (demo seeding, benchmarking)
│
├── .github/
│   └── workflows/        # CI/CD workflows
│
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

The target application flow is:

```text
                       ┌─────────────────────┐
                       │      Next.js        │
                       │  React / TypeScript │
                       └──────────┬──────────┘
                                  │
                                  ▼
                       ┌─────────────────────┐
                       │       FastAPI       │
                       │     Backend API     │
                       └──────────┬──────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
             ┌──────────────┐            ┌──────────────┐
             │ PostgreSQL   │            │    Redis     │
             │ + pgvector   │            │ Jobs / Cache │
             └──────┬───────┘            └──────┬───────┘
                    │                           │
                    └─────────────┬─────────────┘
                                  ▼
                       ┌─────────────────────┐
                       │ Background Workers  │
                       └──────────┬──────────┘
                                  │
                                  ▼
                Document Ingestion & Chunking
                                  │
                                  ▼
                    Embeddings / Vector Index
                                  │
                                  ▼
                   Retrieval + Reranking
                                  │
                                  ▼
                         LLM Generation
                                  │
                                  ▼
                    Grounded Answer + Citations
                                  │
                                  ▼
                     Evaluation / Observability
```

---

## Technology Stack

### Frontend

- Next.js
- React
- TypeScript

### Backend

- Python
- FastAPI
- Pydantic
- SQLAlchemy
- Alembic

### Data & Infrastructure

- PostgreSQL
- pgvector
- Redis
- Docker
- AWS

### AI / Retrieval

- Embeddings
- Vector search
- Hybrid retrieval
- Reranking
- Retrieval-augmented generation
- LLM-as-a-judge evaluation

### Engineering

- pytest
- Ruff
- mypy
- GitHub Actions
- Structured logging
- CI/CD

---

## Current Development Status

CaseFlow AI was built incrementally, each layer tested before the next was introduced — 58 phases, each landing as its own commit with passing tests, lint, and typecheck before moving on. All of the following is implemented and tested, not planned:

**Foundation** — monorepo structure, FastAPI application skeleton, structured logging, error handling, health/readiness endpoints, PostgreSQL + SQLAlchemy + Alembic, repository/service layering, domain model and ADRs.

**Authentication & authorization** — OAuth login (Google, plus a mock provider for local dev/tests), JWT sessions, project membership, owner/editor/viewer roles enforced server-side.

**Document intelligence** — Next.js frontend, S3-compatible object storage, Redis-backed async jobs (Dramatiq), document ingestion and chunking, embeddings, semantic vector search (pgvector), hybrid retrieval (vector + BM25 via reciprocal rank fusion), reranking.

**Grounded AI** — citation-grounded RAG chat, persistent conversations, insufficient-evidence handling, citation-grounded report generation.

**AI evaluation** — prompt/model version tracking, reproducible evaluation datasets, retrieval metrics (Recall@K, Precision@K, MRR, NDCG), deterministic answer checks, LLM-as-a-judge graders (faithfulness, relevance, completeness, citation support), model comparison, a RAG regression suite with hard quality thresholds.

**Production engineering** — cost/latency tracking, Redis caching, retry and failure handling, structured observability, audit logging, human review workflows, rate limiting and security hardening, Dockerized local development, GitHub Actions CI (backend, frontend, Docker, Terraform, end-to-end), integration and end-to-end tests.

**Infrastructure as code** — Terraform for the full target AWS architecture (networking, RDS, ElastiCache, S3, IAM, ECS/Fargate, ALB, Secrets Manager, CloudWatch alarms) — validated (`fmt`/`validate` in CI) but never deployed; see [Security](#security) and `docs/deployment.md`.

**Polish & tooling** — frontend UX polish, a demo dataset seeder (`scripts/seed_demo.py`), a performance benchmarking harness (`scripts/benchmark.py`), a full documentation pass, and the `v1.0.0` release itself: a full test-suite run across both Python packages, the frontend, Terraform, and end-to-end, then a tagged GitHub release.

---

## Backend Development

The backend currently lives in:

```text
apps/api/
```

### Create a virtual environment

From the repository root:

```bash
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell prevents activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### Install backend dependencies

Install `packages/evals` first — `apps/api` imports `caseflow_evals` at
import time (see `apps/api/app/evals/`):

```bash
pip install -e "packages/evals[dev]"
pip install -e "apps/api[dev]"
```

`packages/evals` is CaseFlow's evaluation framework — dataset format,
retrieval metrics, and graders — a separate installable package, usable
standalone (a notebook, a CI script) without pulling in the whole
FastAPI app.

### Run the test suite

```bash
cd apps/api && pytest
cd packages/evals && pytest
```

Both are wired into CI (`.github/workflows/ci.yml`'s `backend` job) —
see the CI badge at the top of this file for current status rather than
a test count here, which would go stale the moment either suite grows.

### Lint

```bash
ruff check .
ruff format --check .
```

### Type check

```bash
mypy app
```

---

## Frontend Development

The frontend lives in `apps/web` (Next.js / React / TypeScript). It talks
to the backend over the HTTP API only — set `NEXT_PUBLIC_API_URL` (see
`apps/web/.env.example`) to point it at a running `apps/api` (either
`uvicorn app.main:app` directly or the Docker stack below).

```bash
cd apps/web
npm install
npm run dev            # http://localhost:3000
npm run lint            # ESLint
npx tsc --noEmit         # TypeScript
npm run build            # production build
npm run test:e2e         # Playwright — needs a running api + web (see e2e/README.md)
```

---

## Docker

The entire stack — Postgres (with pgvector), Redis, the API, the
background worker, and the frontend — runs with one command and no local
Python/Node toolchain, database, or API credentials (every AI provider
defaults to `mock`):

```bash
docker compose up --build
```

This boots six services: `postgres` and `redis` (with health checks),
`migrate` (a one-shot `alembic upgrade head`, so `api`/`worker` never race
to apply the same revision), `api` (http://localhost:8000), `worker`
(the Dramatiq consumer — same image as `api`, different command), and
`web` (http://localhost:3000). `api`/`worker` wait for `migrate` to exit
successfully and for Postgres/Redis to report healthy before starting;
`web` waits for `api`'s own `/health` check.

Override any provider/credential via a `.env` file at the repo root
(read by `docker compose` automatically) — e.g. `LLM_PROVIDER=openai` and
`OPENAI_API_KEY=...` to use a real model instead of the mock provider.

```bash
docker compose down          # stop everything
docker compose down -v       # also delete the Postgres/Redis/storage volumes
```

### Demo data

Once the stack above is running, `scripts/seed_demo.py` populates it
through the same public API the frontend uses — a demo user, a project
with a sample contract uploaded and ingested, a chat conversation with
grounded answers, a flagged human review, an evaluation run, and a
generated report — so there's something to explore immediately instead
of an empty dashboard:

```bash
python scripts/seed_demo.py
```

Log in at http://localhost:3000/login as `demo@caseflow.example` (mock
OAuth) to see it. Safe to run more than once — it reuses the existing
demo project and document rather than duplicating them.

---

## Environment Configuration

Copy the environment template:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Then configure the required local values.

The `.env` file is intentionally excluded from Git and must never contain credentials that are committed to the repository.

---

## Engineering Principles

CaseFlow AI follows several design principles throughout development:

**Separation of concerns** — API routes, services, repositories, AI workflows, persistence, and infrastructure remain separate.

**Dependency boundaries** — application business logic should not depend directly on framework or provider-specific implementation details where avoidable.

**Grounded generation** — AI-generated factual claims should be traceable to retrieved source evidence.

**Evaluation before optimization** — changes to retrieval, prompts, and models should be measured rather than assumed to improve quality.

**Asynchronous processing** — expensive document-processing operations should run outside request/response cycles.

**Configuration over hardcoding** — environment-specific settings, providers, models, and infrastructure configuration should remain external to business logic.

**Observability by design** — model runs, jobs, failures, latency, token usage, and cost should be measurable.

**Secure multi-tenancy** — authorization must be enforced by the backend at the resource level rather than relying on frontend visibility.

---

## Testing Strategy

Every layer below is implemented and runs in CI on every push/PR (see
`.github/workflows/ci.yml` and the CI badge above):

```text
Unit Tests
    ↓
Repository / Service Tests
    ↓
API Integration Tests
    ↓
RAG & Retrieval Evaluation (packages/evals + a hard-threshold regression suite)
    ↓
Docker Build Validation
    ↓
Terraform Validation (fmt/validate)
    ↓
End-to-End Tests (Playwright, over a real Docker Compose stack)
```

The AI evaluation layer additionally measures retrieval and generation
behavior using reproducible, versioned datasets and graders — see
`packages/evals` and `apps/api/app/evals/`.

---

## AI Evaluation Strategy

CaseFlow AI treats AI quality as a first-class, measured concern rather than assuming model output is correct.

Evaluation dimensions implemented and covered by
`apps/api/tests/test_rag_regression.py`'s regression thresholds and
`apps/api/app/evals/`:

- retrieval Recall@K, Precision@K, mean reciprocal rank, NDCG@K;
- answer faithfulness, completeness, relevance (LLM-as-a-judge);
- citation correctness (deterministic — every citation is checked
  against the project's real chunks, not just judged);
- latency, token usage, and estimated model cost (recorded on every
  `ModelRun`).

LLM-as-a-judge graders are combined with deterministic validation where
possible (see `app/evals/deterministic_checks.py` vs.
`app/evals/graders.py`), and every judge call records its model, prompt
version, and temperature so evaluation runs stay reproducible.

---

## Security

Implemented, not merely designed for:

- OAuth-based authentication (Google, plus a mock provider gated to
  non-production environments — see `docs/decisions/004-authentication.md`)
- backend-enforced, resource-level project authorization (owner/editor/viewer)
- environment-based secret management — no literal secret ever committed;
  the AWS Terraform's `secrets` module goes further, generating what it
  can itself and leaving externally-issued credentials as empty Secrets
  Manager containers populated out-of-band (`docs/decisions/009-security-hardening.md`)
- secure file upload validation (size/type limits, content sniffing)
- rate limiting
- resource isolation between projects
- audit logging of authorization-sensitive actions
- secure object-storage access (signed URLs in the S3 backend)
- prompt-injection boundaries for retrieved documents

Uploaded documents are treated as untrusted data passed to the LLM as
context, never as privileged system instructions.

---

## Roadmap

CaseFlow AI's long-term goal — a complete platform for both **document intelligence** and **AI system evaluation** — is implemented end to end:

```text
Multi-user projects                    ✅
        ↓
Asynchronous document ingestion        ✅
        ↓
Semantic + hybrid retrieval            ✅
        ↓
Citation-grounded RAG                  ✅
        ↓
Prompt/model tracking                  ✅
        ↓
Automated AI evaluation                ✅
        ↓
Model comparison                       ✅
        ↓
Human review                           ✅
        ↓
Production observability               ✅
        ↓
AWS infrastructure as code             ✅ (validated, not deployed)
        ↓
v1.0.0 release                         ✅
```

---

## Project Status

✅ **CaseFlow AI has reached v1.0.0.**

Every capability described above — auth, document intelligence, grounded RAG, AI evaluation, human review, observability, the frontend, Docker, CI, and AWS infrastructure-as-code — is implemented, tested, and merged.