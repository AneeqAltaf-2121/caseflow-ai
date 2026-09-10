"""Reciprocal Rank Fusion (Phase 16): combine independently-ranked vector
and keyword result lists into one ranking, without needing their scores
to be on comparable scales (cosine similarity and BM25 scores aren't).
"""

from dataclasses import dataclass

from app.models.chunk import DocumentChunk

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class FusedResult:
    """Carries the original per-retriever diagnostics (rank + raw score in
    each list, or None if a retriever didn't surface this chunk at all)
    alongside the fused score, so a caller can show *why* a result ranked
    where it did rather than just the final number.
    """

    chunk: DocumentChunk
    fused_score: float
    vector_rank: int | None
    vector_score: float | None
    keyword_rank: int | None
    keyword_score: float | None


def reciprocal_rank_fusion(
    vector_results: list[tuple[DocumentChunk, float]],
    keyword_results: list[tuple[DocumentChunk, float]],
    *,
    k: int = DEFAULT_RRF_K,
    limit: int = 20,
) -> list[FusedResult]:
    """RRF score for a chunk is `sum(1 / (k + rank))` over every ranked
    list (1-indexed) it appears in — a chunk found by both retrievers
    outranks one found by only one, without either retriever's raw score
    needing to mean the same thing.
    """
    vector_by_id = {
        chunk.id: (rank, score) for rank, (chunk, score) in enumerate(vector_results, 1)
    }
    keyword_by_id = {
        chunk.id: (rank, score) for rank, (chunk, score) in enumerate(keyword_results, 1)
    }

    chunks_by_id: dict = {}
    for chunk, _score in vector_results:
        chunks_by_id[chunk.id] = chunk
    for chunk, _score in keyword_results:
        chunks_by_id[chunk.id] = chunk

    fused: list[FusedResult] = []
    for chunk_id, chunk in chunks_by_id.items():
        vector_hit = vector_by_id.get(chunk_id)
        keyword_hit = keyword_by_id.get(chunk_id)

        fused_score = 0.0
        if vector_hit is not None:
            fused_score += 1.0 / (k + vector_hit[0])
        if keyword_hit is not None:
            fused_score += 1.0 / (k + keyword_hit[0])

        fused.append(
            FusedResult(
                chunk=chunk,
                fused_score=fused_score,
                vector_rank=vector_hit[0] if vector_hit else None,
                vector_score=vector_hit[1] if vector_hit else None,
                keyword_rank=keyword_hit[0] if keyword_hit else None,
                keyword_score=keyword_hit[1] if keyword_hit else None,
            )
        )

    fused.sort(key=lambda result: result.fused_score, reverse=True)
    return fused[:limit]
