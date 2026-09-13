# CaseFlow AI

[![CI](https://github.com/AneeqAltaf-2121/caseflow-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/AneeqAltaf-2121/caseflow-ai/actions/workflows/ci.yml)

**CaseFlow AI** is a full-stack AI research and document intelligence platform for organizing document collections, performing semantic and hybrid search, generating citation-grounded answers and reports, and evaluating AI system quality across models, prompts, and retrieval strategies.

The project is being built as a production-oriented AI platform rather than a standalone "chat with documents" demo. Its architecture is designed around multi-user workspaces, asynchronous document processing, retrieval-augmented generation (RAG), AI evaluation, observability, and reproducible model experimentation.

> **Status:** Active development. The backend foundation and persistence layers are implemented, with authentication and authorization currently under development.

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
- Automated testing
- CI/CD
- AWS deployment

---

## Architecture

CaseFlow AI is organized as a monorepo:

```text
caseflow-ai/
├── apps/
│   ├── api/              # FastAPI backend
│   └── web/              # Next.js / React / TypeScript frontend
│
├── packages/
│   ├── evals/            # AI evaluation framework
│   └── shared/           # Shared schemas and utilities
│
├── infra/
│   ├── aws/              # AWS infrastructure
│   └── docker/           # Container configuration
│
├── docs/
│   └── decisions/        # Architecture Decision Records (ADRs)
│
├── scripts/              # Development and operational scripts
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

CaseFlow AI is being developed incrementally so that each layer is tested before higher-level AI functionality is introduced.

### Completed

**Phase 0 — Repository & Engineering Foundation**

- Monorepo structure
- Git/GitHub workflow
- Local development environment
- Environment variable template
- Initial documentation structure

**Phase 1 — Architecture & Domain Model**

- System architecture documentation
- Core domain model
- Architecture Decision Records

**Phase 2 — FastAPI Foundation**

- Application configuration
- Structured backend organization
- Logging foundation
- Error handling
- Health endpoint
- Readiness endpoint
- Backend testing infrastructure

**Phase 3 — PostgreSQL Persistence**

- PostgreSQL integration
- SQLAlchemy persistence layer
- Alembic migrations
- Repository/service boundaries
- Persistence tests

### In Progress

**Phase 4 — Authentication & Authorization**

- User authentication
- OAuth integration
- Project membership
- Role-based access control
- Resource-level authorization

### Upcoming

Later phases will introduce:

1. Next.js application shell
2. Document upload and object storage
3. Redis-backed asynchronous jobs
4. Document ingestion and chunking
5. Embeddings and vector search
6. Hybrid retrieval and reranking
7. Citation-grounded RAG
8. Persistent conversations
9. Report generation
10. Prompt and model version tracking
11. AI evaluation framework
12. LLM-as-a-judge graders
13. Evaluation dashboards
14. Model comparison
15. Cost and latency instrumentation
16. Observability and reliability
17. Human review workflows
18. Docker and CI/CD
19. AWS deployment
20. Security hardening

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

```bash
pip install -e "apps/api[dev]"
pip install -e "packages/evals[dev]"
```

`packages/evals` is CaseFlow's evaluation framework (dataset format now;
graders and evaluation-run orchestration in later phases) — a separate
installable package, usable independently of the FastAPI app, that
`apps/api` depends on at import time (see `apps/api/app/evals/`).

### Run the test suite

From `apps/api`:

```bash
pytest
```

Current backend status:

```text
12 tests passing
```

### Lint

```bash
ruff check .
```

### Type check

```bash
mypy app
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

The project will use multiple testing layers as development progresses:

```text
Unit Tests
    ↓
Repository / Service Tests
    ↓
API Integration Tests
    ↓
RAG & Retrieval Evaluation
    ↓
Frontend Component Tests
    ↓
End-to-End Tests
```

The AI evaluation layer will additionally measure retrieval and generation behavior using reproducible datasets and versioned graders.

---

## AI Evaluation Strategy

CaseFlow AI is designed to evaluate AI quality as a first-class feature rather than treating model output as inherently correct.

Planned evaluation dimensions include:

- retrieval Recall@K;
- retrieval Precision@K;
- mean reciprocal rank;
- answer faithfulness;
- answer completeness;
- answer relevance;
- citation correctness;
- hallucination rate;
- latency;
- token usage;
- estimated model cost.

LLM-as-a-judge graders will be combined with deterministic validation where possible, and judge model/prompt versions will be recorded to make evaluation runs reproducible.

---

## Security

The project is designed with production security requirements in mind, including:

- OAuth-based authentication
- backend-enforced project authorization
- environment-based secret management
- secure file upload validation
- rate limiting
- resource isolation between projects
- audit logging
- secure object-storage access
- prompt-injection boundaries for retrieved documents

Uploaded documents will be treated as untrusted data and never as privileged system instructions.

---

## Roadmap

The long-term goal is to make CaseFlow AI a complete platform for both **document intelligence** and **AI system evaluation**.

The key development milestones are:

```text
Multi-user projects
        ↓
Asynchronous document ingestion
        ↓
Semantic + hybrid retrieval
        ↓
Citation-grounded RAG
        ↓
Prompt/model tracking
        ↓
Automated AI evaluation
        ↓
Model comparison
        ↓
Human review
        ↓
Production observability
        ↓
AWS deployment
```

---

## Project Status

🚧 **CaseFlow AI is currently under active development.**

The current focus is authentication and authorization. RAG, evaluation, frontend, and deployment capabilities described above are part of the planned architecture and will be added incrementally as their corresponding phases are completed.