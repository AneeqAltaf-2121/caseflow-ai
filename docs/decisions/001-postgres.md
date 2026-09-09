# 001 — Use PostgreSQL as the primary datastore

## Status
Accepted

## Context
CaseFlow needs a system of record for relational, transactional data:
users, organizations, projects, memberships, documents, conversations,
messages, evaluation results, and audit events. It also needs strong
consistency guarantees for authorization-sensitive data (who can see what).

## Decision
Use PostgreSQL, accessed through SQLAlchemy 2 (async) and versioned with
Alembic migrations.

## Rationale
- Mature, well-understood relational semantics for entities with real
  foreign-key relationships (see `docs/domain-model.md`).
- Strong transactional guarantees matter for authorization and billing/cost
  data — eventual consistency is not acceptable there.
- `pgvector` (see ADR 002) lets us keep vector embeddings in the same
  database as the relational data they describe, avoiding a second system
  to keep in sync.
- Wide managed-hosting support (AWS RDS) simplifies the production path.

## Consequences
- We accept Postgres's write-scaling limits; this is acceptable at the
  scale of a research/portfolio platform and can be revisited (read
  replicas, sharding) if it becomes a bottleneck.
- All schema changes go through Alembic migrations, checked in CI.
