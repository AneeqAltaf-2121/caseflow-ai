import uuid

from app.models.chunk import DocumentChunk
from app.retrieval.keyword import bm25_search, tokenize


def _chunk(text: str) -> DocumentChunk:
    return DocumentChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        page_number=1,
        section=None,
        text=text,
        token_count=len(text.split()),
        start_offset=0,
        end_offset=len(text),
        embedding=None,
        chunk_metadata={},
    )


def test_tokenize_lowercases_and_strips_punctuation() -> None:
    assert tokenize("The Cat, sat!") == ["the", "cat", "sat"]


def test_bm25_search_ranks_exact_term_match_above_unrelated_text() -> None:
    chunks = [
        _chunk("The termination clause applies after ninety days."),
        _chunk("Payment terms are net thirty days from invoice."),
        _chunk("Unrelated text about weather and clouds."),
    ]

    results = bm25_search(chunks, "termination clause", limit=10)

    assert results[0][0].text.startswith("The termination clause")
    assert len(results) == 1  # only the matching chunk shares any query term


def test_bm25_search_excludes_chunks_with_no_term_overlap() -> None:
    chunks = [_chunk("apples and oranges"), _chunk("completely different subject matter")]
    results = bm25_search(chunks, "apples", limit=10)
    assert len(results) == 1
    assert results[0][0].text == "apples and oranges"


def test_bm25_search_matches_even_a_single_chunk_corpus() -> None:
    # A brand-new project with exactly one document: BM25's IDF is
    # mathematically negative here (the term appears in 100% of the
    # corpus), which must not be mistaken for "not a match" — see
    # bm25_search's docstring.
    chunks = [_chunk("The indemnification clause survives termination.")]
    results = bm25_search(chunks, "indemnification", limit=10)
    assert len(results) == 1


def test_bm25_search_handles_empty_corpus() -> None:
    assert bm25_search([], "anything", limit=10) == []


def test_bm25_search_handles_empty_query() -> None:
    assert bm25_search([_chunk("some text")], "", limit=10) == []


def test_bm25_search_respects_limit() -> None:
    chunks = [_chunk(f"shared keyword occurrence number {i}") for i in range(5)]
    results = bm25_search(chunks, "keyword", limit=2)
    assert len(results) == 2
