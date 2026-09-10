import re

from rank_bm25 import BM25Okapi

from app.models.chunk import DocumentChunk

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def bm25_search(
    chunks: list[DocumentChunk], query: str, *, limit: int = 10
) -> list[tuple[DocumentChunk, float]]:
    """Rank `chunks` against `query` by BM25 score, highest first,
    excluding chunks that share no query term at all.

    Exclusion is based on literal term overlap, not the BM25 score's sign:
    BM25's IDF term goes to zero (or negative) for a term that isn't rare
    relative to corpus size — trivially true for a brand-new project with
    only one or two chunks, where any term "appears in most of the
    corpus" by construction. Filtering on score > 0 would then wrongly
    drop a chunk that plainly matches, so relevance is judged by overlap
    and the (possibly negative-in-a-tiny-corpus) score is used only to
    order genuine matches against each other.
    """
    if not chunks:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    query_token_set = set(query_tokens)

    corpus = [tokenize(chunk.text) for chunk in chunks]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(query_tokens)

    ranked = sorted(
        zip(chunks, corpus, scores, strict=True), key=lambda item: item[2], reverse=True
    )
    results = [
        (chunk, float(score))
        for chunk, tokens, score in ranked
        if query_token_set.intersection(tokens)
    ]
    return results[:limit]
