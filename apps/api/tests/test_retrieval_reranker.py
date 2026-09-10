import uuid

import pytest

from app.models.chunk import DocumentChunk
from app.retrieval.reranker import CrossEncoderReranker, MockReranker

pytestmark = pytest.mark.asyncio


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


async def test_mock_reranker_passes_through_unchanged_order() -> None:
    a, b, c = _chunk("a"), _chunk("b"), _chunk("c")
    candidates = [(a, 0.1), (b, 0.9), (c, 0.5)]

    result = await MockReranker().rerank("query", candidates, top_k=10)

    assert result == candidates


async def test_mock_reranker_respects_top_k() -> None:
    candidates = [(_chunk(str(i)), 1.0) for i in range(5)]
    result = await MockReranker().rerank("query", candidates, top_k=2)
    assert len(result) == 2


async def test_cross_encoder_reranker_prefers_exact_phrase_match() -> None:
    exact_phrase = _chunk("The termination clause applies after ninety days.")
    scattered_words = _chunk(
        "Termination is discussed on page one; the clause about payment is on page two."
    )
    unrelated = _chunk("This document discusses shipping logistics only.")

    candidates = [(scattered_words, 0.5), (exact_phrase, 0.5), (unrelated, 0.5)]
    reranked = await CrossEncoderReranker().rerank("termination clause", candidates, top_k=3)

    assert reranked[0][0] is exact_phrase
    assert reranked[0][1] > reranked[1][1]


async def test_cross_encoder_reranker_respects_top_k() -> None:
    candidates = [(_chunk(f"apple banana {i}"), 0.0) for i in range(5)]
    reranked = await CrossEncoderReranker().rerank("apple banana", candidates, top_k=2)
    assert len(reranked) == 2
