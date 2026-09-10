"""Document extraction pipeline (Phase 9).

Turns raw uploaded bytes into normalized, page-aware text without losing
the positional metadata (page number) that citations depend on later
(Phase 11+). Chunking (Phase 10) and persistence into DocumentChunk
(Phase 11, once that model/pgvector exist) build on top of this.
"""
