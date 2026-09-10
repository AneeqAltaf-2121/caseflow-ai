"""Retrieval quality metrics (Phase 26), independent of generation: given
what a retriever returned for a query and which chunk ids were actually
relevant (EvaluationExample.relevant_chunk_ids), how good was the
ranking? Pure functions, no I/O — apps/api's app/evals/ orchestrates
running these against a real project's retriever.
"""

import math
from collections.abc import Iterable


def recall_at_k(retrieved_ids: list[str], relevant_ids: Iterable[str], k: int) -> float:
    """Fraction of all relevant chunks that appear in the top k results.
    0.0 when there are no relevant ids at all — a caller should skip
    scoring an example with no ground truth rather than treat this as a
    real 0."""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    hits = len(set(retrieved_ids[:k]) & relevant)
    return hits / len(relevant)


def precision_at_k(retrieved_ids: list[str], relevant_ids: Iterable[str], k: int) -> float:
    """Fraction of the top k results that were actually relevant."""
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    relevant = set(relevant_ids)
    hits = len(set(top_k) & relevant)
    return hits / len(top_k)


def reciprocal_rank(retrieved_ids: list[str], relevant_ids: Iterable[str]) -> float:
    """1/rank of the first relevant result (1-indexed), 0.0 if none of the
    retrieved results were relevant. Averaging this across queries gives
    Mean Reciprocal Rank (MRR)."""
    relevant = set(relevant_ids)
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(retrieved_ids: list[str], relevant_ids: Iterable[str], k: int) -> float:
    """Normalized Discounted Cumulative Gain at k, with binary relevance
    (a chunk either is or isn't in relevant_ids — no graded relevance
    scores in the dataset format, Phase 25). 0.0 when there's nothing to
    normalize against (no relevant ids)."""
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0

    top_k = retrieved_ids[:k]
    dcg = sum(
        (1.0 if doc_id in relevant else 0.0) / math.log2(rank + 1)
        for rank, doc_id in enumerate(top_k, start=1)
    )

    ideal_hit_count = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hit_count + 1))
    if idcg == 0:
        return 0.0
    return dcg / idcg
