import uuid

import pytest

from app.integrations.generation import MockGenerationProvider
from app.models.chunk import DocumentChunk
from app.retrieval.reranker import CrossEncoderReranker, LLMReranker, MockReranker

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


async def test_llm_reranker_applies_valid_model_ordering() -> None:
    a, b, c = _chunk("a"), _chunk("b"), _chunk("c")
    candidates = [(a, 0.0), (b, 0.0), (c, 0.0)]
    provider = MockGenerationProvider(canned_response="[2, 0, 1]")

    reranked = await LLMReranker(provider).rerank("query", candidates, top_k=10)

    assert [chunk for chunk, _score in reranked] == [c, a, b]


async def test_llm_reranker_falls_back_to_input_order_on_malformed_json() -> None:
    candidates = [(_chunk("a"), 0.0), (_chunk("b"), 0.0)]
    provider = MockGenerationProvider(canned_response="not valid json at all")

    reranked = await LLMReranker(provider).rerank("query", candidates, top_k=10)

    assert reranked == candidates


async def test_llm_reranker_falls_back_when_indices_are_not_a_full_permutation() -> None:
    candidates = [(_chunk("a"), 0.0), (_chunk("b"), 0.0), (_chunk("c"), 0.0)]
    # Missing index 2, repeats index 0 — not a valid permutation of [0,1,2].
    provider = MockGenerationProvider(canned_response="[0, 0, 1]")

    reranked = await LLMReranker(provider).rerank("query", candidates, top_k=10)

    assert reranked == candidates


async def test_llm_reranker_respects_top_k() -> None:
    candidates = [(_chunk(str(i)), 0.0) for i in range(5)]
    provider = MockGenerationProvider(canned_response="[0, 1, 2, 3, 4]")

    reranked = await LLMReranker(provider).rerank("query", candidates, top_k=2)

    assert len(reranked) == 2


async def test_llm_reranker_handles_empty_candidates() -> None:
    provider = MockGenerationProvider(canned_response="[]")
    assert await LLMReranker(provider).rerank("query", [], top_k=5) == []
