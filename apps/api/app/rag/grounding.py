"""Grounding (Phase 20): the system should say "I don't have enough
evidence" instead of guessing.

A numeric similarity/rerank-score threshold was considered and rejected:
CrossEncoderReranker's phrase-overlap score and a cosine-similarity score
aren't on comparable scales, and a hardcoded cutoff would be reranker-
implementation-dependent (see app/retrieval/reranker.py — swapping
CrossEncoderReranker for LLMReranker changes what "score" even means).
Citation presence is used instead: it's the one provider-agnostic signal
available at this layer — either the model found something worth citing
in what it was given, or it didn't.
"""

INSUFFICIENT_EVIDENCE_MESSAGE = (
    "The uploaded documents do not contain enough evidence to answer this question."
)
