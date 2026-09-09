# CaseFlow AI

CaseFlow AI is a full-stack AI research and document intelligence platform for organizing document collections, performing semantic search, generating citation-grounded answers and reports, and evaluating AI system quality across models, prompts, and retrieval strategies.

## Planned Capabilities

- Multi-user project workspaces
- Document ingestion and asynchronous processing
- Semantic and hybrid search
- Retrieval-augmented generation (RAG)
- Source-grounded citations
- Report generation
- Prompt and model version tracking
- LLM-as-a-judge evaluations
- Model comparison
- Cost and latency tracking
- Human review workflows
- PostgreSQL persistence
- Redis-backed background jobs and caching
- Dockerized local development
- AWS deployment
- Automated testing and CI/CD

## Architecture

CaseFlow AI is being developed as a monorepo containing:

- `apps/web` — Next.js / React / TypeScript frontend
- `apps/api` — FastAPI backend
- `packages/evals` — AI evaluation framework
- `packages/shared` — shared schemas and utilities
- `infra` — Docker and cloud infrastructure
- `docs` — architecture and engineering documentation

## Development Status

Phase 0 — Repository and development environment setup.