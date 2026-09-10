import uuid

from app.models.chunk import DocumentChunk
from app.retrieval.fusion import reciprocal_rank_fusion


def _chunk(text: str = "text") -> DocumentChunk:
    return DocumentChunk(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_version_id=uuid.uuid4(),
        page_number=1,
        section=None,
        text=text,
        token_count=1,
        start_offset=0,
        end_offset=len(text),
        embedding=None,
        chunk_metadata={},
    )


def test_chunk_found_by_both_retrievers_outranks_single_retriever_hit() -> None:
    a, b, c = _chunk("a"), _chunk("b"), _chunk("c")
    # a: rank 1 in both. b: rank 2 in vector only. c: rank 1 in keyword
    # only but rank 3 in vector (weaker signal than b's single strong hit).
    vector_results = [(a, 0.9), (b, 0.8), (c, 0.3)]
    keyword_results = [(a, 5.0)]

    fused = reciprocal_rank_fusion(vector_results, keyword_results, limit=10)

    assert fused[0].chunk is a
    assert fused[0].vector_rank == 1
    assert fused[0].keyword_rank == 1


def test_diagnostics_are_null_for_the_retriever_that_missed_a_chunk() -> None:
    only_vector = _chunk("v")
    only_keyword = _chunk("k")

    fused = reciprocal_rank_fusion([(only_vector, 0.5)], [(only_keyword, 1.0)], limit=10)
    by_chunk = {result.chunk: result for result in fused}

    assert by_chunk[only_vector].keyword_rank is None
    assert by_chunk[only_vector].keyword_score is None
    assert by_chunk[only_vector].vector_rank == 1

    assert by_chunk[only_keyword].vector_rank is None
    assert by_chunk[only_keyword].keyword_rank == 1


def test_fusion_respects_limit() -> None:
    chunks = [_chunk(str(i)) for i in range(5)]
    vector_results = [(chunk, 1.0) for chunk in chunks]

    fused = reciprocal_rank_fusion(vector_results, [], limit=2)

    assert len(fused) == 2


def test_empty_inputs_produce_no_results() -> None:
    assert reciprocal_rank_fusion([], [], limit=10) == []


def test_rrf_score_matches_formula() -> None:
    chunk = _chunk()
    fused = reciprocal_rank_fusion([(chunk, 0.9)], [(chunk, 5.0)], k=60, limit=10)
    expected = 1 / (60 + 1) + 1 / (60 + 1)
    assert fused[0].fused_score == expected
