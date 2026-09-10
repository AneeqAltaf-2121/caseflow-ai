"""Reranking (Phase 17): a second, more precise pass over hybrid
retrieval's top candidates, narrowing 20-ish fused results down to the
5-8 passages that actually go into the generation prompt (Phase 19).
"""

from typing import Protocol

from app.models.chunk import DocumentChunk
from app.retrieval.keyword import tokenize

DEFAULT_TOP_K = 6

Candidates = list[tuple[DocumentChunk, float]]


class Reranker(Protocol):
    async def rerank(
        self, query: str, candidates: Candidates, *, top_k: int = DEFAULT_TOP_K
    ) -> Candidates: ...


class MockReranker:
    """No-op: passes candidates through in their existing order, truncated
    to top_k. Default/test double — makes no relevance judgement at all."""

    async def rerank(
        self, query: str, candidates: Candidates, *, top_k: int = DEFAULT_TOP_K
    ) -> Candidates:
        return candidates[:top_k]


def _ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _phrase_overlap_score(
    query_tokens: list[str], candidate_tokens: list[str], max_ngram: int
) -> float:
    score = 0.0
    for n in range(1, max_ngram + 1):
        query_ngrams = _ngrams(query_tokens, n)
        if not query_ngrams:
            continue
        # Weight longer phrase matches more: a candidate containing the
        # literal bigram "termination clause" should outrank one that
        # only shares "termination" and "clause" as separate unigrams —
        # unigram-based BM25/vector fusion can't make that distinction.
        score += len(query_ngrams & _ngrams(candidate_tokens, n)) * n
    return score


class CrossEncoderReranker:
    """A lightweight, dependency-free approximation of a real cross-encoder
    (e.g. ms-marco-MiniLM-L-6-v2): scores each (query, candidate) pair
    jointly by exact n-gram (phrase) overlap, rather than a transformer's
    joint attention — no torch/sentence-transformers dependency, matching
    the tradeoff already made for LocalEmbeddingProvider (ADR 007). A real
    transformer cross-encoder is a drop-in replacement behind this same
    interface if retrieval quality ever needs it.
    """

    def __init__(self, *, max_ngram: int = 3) -> None:
        self._max_ngram = max_ngram

    async def rerank(
        self, query: str, candidates: Candidates, *, top_k: int = DEFAULT_TOP_K
    ) -> Candidates:
        query_tokens = tokenize(query)
        scored = [
            (chunk, _phrase_overlap_score(query_tokens, tokenize(chunk.text), self._max_ngram))
            for chunk, _score in candidates
        ]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored[:top_k]
