# Architecture

## Overview

CaseFlow AI is a multi-user AI research and document intelligence platform.
Users organize documents into projects, ask citation-grounded questions over
those documents, generate reports, and evaluate AI answer quality across
prompts, retrievers, and models.

```
Browser
  |
Next.js / React / TypeScript frontend
  |
FastAPI backend
  |
PostgreSQL (+ pgvector) ---- Redis
  |                           |
Users/Projects              Cache / Job queue
Documents
Chats
Evals
Prompts
  |
Object Storage (S3 / local filesystem in dev)
  |
Ingestion workers (Redis-queued)
  |
Extraction -> Chunking -> Embeddings -> Vector index
  |
Retrieval (hybrid: vector + keyword) + reranking
  |
LLM (provider-agnostic)
  |
Citations + answer
  |
Evaluation / observability
```

## Components

### `apps/web` — Next.js frontend
Server-rendered React app. Talks to the backend exclusively over the
documented HTTP API — no direct DB or storage access. Owns auth session
handling, project/document UI, chat UI, evaluation dashboards.

### `apps/api` — FastAPI backend
The single source of truth for business logic and authorization. Structured
as `routes -> services -> repositories -> models`, so no route issues SQL
directly (see `docs/domain-model.md`). Hosts the RAG pipeline, evaluation
framework hooks, and integrations with LLM/embedding providers.

### PostgreSQL
System of record for all relational data: users, projects, documents,
chunks, conversations, evaluation results, audit events. Also hosts vector
embeddings via `pgvector` rather than a separate vector database — see
`docs/decisions/002-vector-storage.md`.

### Redis
Two responsibilities, namespaced separately: (1) broker/result-backend for
the background job queue (document ingestion, evaluation runs), and (2)
cache for expensive, deterministic reads (embeddings, search results),
keyed to include model/retriever versions so cache entries never outlive
their assumptions.

### Object storage
Raw uploaded files (PDF/DOCX/TXT) live in object storage, not in Postgres.
Local development uses the filesystem (or MinIO); production uses S3 with
signed URLs. Postgres stores only metadata and a `storage_key` pointer.

### Ingestion workers
Consume jobs from Redis, run the ingestion pipeline (extract -> normalize
-> chunk -> embed -> index), and update document status. Retried with
exponential backoff; failures are dead-lettered rather than retried
forever.

### Retrieval + reranking
Hybrid retrieval (vector similarity + BM25/keyword) merged via reciprocal
rank fusion, then reranked. Every retrieved passage carries enough metadata
(document, page, chunk offsets) to support citations.

### Evaluation / observability
Every model call and retrieval is logged with enough structure (prompt
version, model, tokens, latency, cost) to support offline evaluation,
regression comparisons across prompt/model/retriever versions, and cost
dashboards. See `packages/evals`.

## Cross-cutting principles

- **Authorization is enforced server-side, always**, scoped to
  project membership and role (Owner/Editor/Viewer). The frontend never
  makes an authorization decision the backend trusts blindly.
- **Documents are untrusted evidence, not instructions.** Retrieved text is
  passed to the LLM as data; prompts are structured to resist prompt
  injection from document content (see `docs/decisions/` and Phase 28).
- **Every AI operation is attributable**: prompt version, model, and
  retriever version are recorded so behavior changes are traceable and
  regression-testable, not silent.
- **No feature skips the persistence/service/repository layering** described
  in `docs/domain-model.md` — this keeps routes thin and testable.

## Repository layout

```
caseflow-ai/
├── apps/
│   ├── web/       Next.js frontend
│   └── api/       FastAPI backend
├── packages/
│   ├── shared/    Shared schemas/types
│   └── evals/     Evaluation datasets, graders, runner
├── infra/
│   ├── docker/    Dockerfiles
│   └── aws/       Deployment infrastructure
├── docs/          Architecture, domain model, ADRs
├── scripts/       Dev/ops scripts
└── docker-compose.yml
```
