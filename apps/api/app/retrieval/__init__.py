"""Retrieval: keyword search (Phase 15), hybrid fusion (Phase 16), and
reranking (Phase 17) — everything RAG generation (Phase 19) retrieves
context through.

Keyword search uses BM25 (rank_bm25) over an in-memory corpus rather than
PostgreSQL's native tsvector/GIN full-text search. That's a real tradeoff:
tsvector+GIN would scale better (index maintained by Postgres, no
per-query corpus scan) but is Postgres-only, same problem pgvector search
has on SQLite (see DocumentChunkRepository.search_by_embedding) — except
here there's a dialect-agnostic alternative that's still a legitimate,
well-established ranking algorithm, so it's used everywhere (tests and
production alike) instead of branching. Revisit if corpus size ever makes
per-query BM25 the bottleneck.
"""
