import uuid

import pytest

from app.evals.graders import (
    CitationSupportGrader,
    CompletenessGrader,
    FaithfulnessGrader,
    RelevanceGrader,
)
from app.integrations.generation import MockGenerationProvider
from app.rag.service import Citation, RagAnswer

pytestmark = pytest.mark.asyncio


def _citation(source_number: int = 1) -> Citation:
    return Citation(
        source_number=source_number,
        document_id=uuid.uuid4(),
        document_chunk_id=uuid.uuid4(),
        document_filename="contract.txt",
        page_number=1,
        quote="This agreement terminates after 90 days notice.",
    )


def _answer(
    *, text: str = "The agreement terminates after 90 days [1].", citations=None
) -> RagAnswer:
    citations = [_citation()] if citations is None else citations
    return RagAnswer(
        answer=text,
        citations=citations,
        sources_considered=1,
        model="mock-echo-v1",
        provider="MockGenerationProvider",
        insufficient_evidence=len(citations) == 0,
        input_tokens=10,
        output_tokens=5,
        latency_ms=12,
        temperature=0.0,
        retrieval_config={},
    )


async def test_faithfulness_grader_parses_valid_json_response() -> None:
    judge = MockGenerationProvider(
        canned_response='{"score": 0.9, "reason": "well supported", "failures": []}'
    )
    grader = FaithfulnessGrader(judge)

    result = await grader.grade(question="When does it terminate?", answer=_answer())

    assert result.grader == "faithfulness"
    assert result.score == 0.9
    assert result.reason == "well supported"
    assert result.failures == []
    assert result.passed is True
    assert result.judge_model == "mock-echo-v1"
    assert result.prompt_version == "faithfulness_v1"
    assert result.temperature == 0.0
    assert "90 days" in result.source_context


async def test_faithfulness_grader_reports_failures_from_judge() -> None:
    judge = MockGenerationProvider(
        canned_response=(
            '{"score": 0.2, "reason": "invents a fact", '
            '"failures": ["claims a $500 fee not in sources"]}'
        )
    )
    grader = FaithfulnessGrader(judge)

    result = await grader.grade(question="When does it terminate?", answer=_answer())

    assert result.score == 0.2
    assert result.passed is False
    assert result.failures == ["claims a $500 fee not in sources"]


async def test_malformed_judge_output_becomes_zero_score_not_a_crash() -> None:
    judge = MockGenerationProvider(canned_response="not valid json at all")
    grader = FaithfulnessGrader(judge)

    result = await grader.grade(question="q", answer=_answer())

    assert result.score == 0.0
    assert result.reason == "not valid json at all"
    assert result.failures == ["grader returned invalid JSON"]
    assert result.passed is False


async def test_score_outside_0_to_1_is_clamped() -> None:
    judge = MockGenerationProvider(canned_response='{"score": 1.7, "reason": "x", "failures": []}')
    grader = RelevanceGrader(judge)

    result = await grader.grade(question="q", answer=_answer())

    assert result.score == 1.0

    judge_negative = MockGenerationProvider(
        canned_response='{"score": -3, "reason": "x", "failures": []}'
    )
    result_negative = await RelevanceGrader(judge_negative).grade(question="q", answer=_answer())
    assert result_negative.score == 0.0


async def test_relevance_grader_scores_on_topic_answer() -> None:
    judge = MockGenerationProvider(
        canned_response='{"score": 1.0, "reason": "directly answers", "failures": []}'
    )
    result = await RelevanceGrader(judge).grade(
        question="When does the agreement terminate?", answer=_answer()
    )
    assert result.grader == "relevance"
    assert result.score == 1.0


async def test_completeness_grader_compares_against_expected_answer() -> None:
    judge = MockGenerationProvider(
        canned_response=(
            '{"score": 0.5, "reason": "missing renewal terms", '
            '"failures": ["renewal terms omitted"]}'
        )
    )
    result = await CompletenessGrader(judge).grade(
        question="Summarize the termination clause.",
        answer=_answer(),
        expected_answer="Terminates after 90 days notice and auto-renews unless cancelled.",
    )
    assert result.grader == "completeness"
    assert result.score == 0.5
    assert result.failures == ["renewal terms omitted"]


async def test_citation_support_grader_scores_each_citation() -> None:
    judge = MockGenerationProvider(
        canned_response='{"score": 1.0, "reason": "citation matches claim", "failures": []}'
    )
    result = await CitationSupportGrader(judge).grade(
        question="When does it terminate?", answer=_answer()
    )
    assert result.grader == "citation_support"
    assert result.score == 1.0


async def test_citation_support_grader_short_circuits_with_no_citations() -> None:
    judge = MockGenerationProvider(canned_response='{"score": 1.0, "reason": "x", "failures": []}')
    answer = _answer(text="No evidence found.", citations=[])

    result = await CitationSupportGrader(judge).grade(question="q", answer=answer)

    assert result.score == 0.0
    assert result.failures == ["no citations present"]
    assert result.judge_model == "none"
