# 002 — Use PostgreSQL + pgvector for vector storage

## Status
Accepted

## Context
Semantic search (Phase 9) requires storing and querying embedding vectors
for `DocumentChunk`. Options considered: a dedicated vector database
(Pinecone, Weaviate, Qdrant) vs. `pgvector` inside the existing PostgreSQL
instance.

## Decision
Use PostgreSQL with the `pgvector` extension, in the same database as the
relational schema.

## Rationale
- Keeps chunk metadata (document, page, section, offsets — needed for
  citations) and its embedding in one row, one transaction, one query
  engine. No dual-write/sync problem between a relational store and a
  separate vector store.
- `pgvector` supports both approximate (HNSW/IVFFlat) and exact search,
  which is sufficient for the corpus sizes this project targets.
- One fewer piece of infrastructure to operate, deploy, and pay for —
  appropriate for a portfolio-scale system that still wants a production
  architecture.
- Filtering vector search by project/document metadata is a native SQL
  `WHERE` clause instead of a second query language.

## Consequences
- If corpus size or query volume outgrows what `pgvector` handles well, a
  dedicated vector database becomes a future ADR — the repository layer
  boundary (`DocumentChunkRepository`) is designed so that swap would not
  ripple into services or routes.
- The `postgres` service in `docker-compose.yml` uses the
  `pgvector/pgvector` image rather than plain `postgres`.
