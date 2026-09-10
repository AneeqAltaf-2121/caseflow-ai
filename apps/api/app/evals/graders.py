"""LLM-as-a-judge graders (Phase 28). Where Phase 27's deterministic
checks end (things a database query can confirm), these graders start —
faithfulness, relevance, completeness, and citation support all require
judgment, so a second LLM call scores the primary answer against its own
cited context. Every judge call is logged with the judge model, prompt
version, and temperature that produced it (GradeResult) so a judgment is
reproducible and auditable, the same way ModelRun (Phase 23) makes a
generation reproducible.

Structured, not free text: a judge is always asked for JSON —
{"score": <0.0-1.0>, "reason": "...", "failures": ["..."]}. Malformed
judge output is a *result*, not a crash: score 0.0, the raw text
preserved in `reason`, and a "grader returned invalid JSON" failure — a
flaky/hallucinating judge lowers the score rather than breaking the
evaluation run around it.

Deliberately API-side (not packages/evals): grading operates on
RagAnswer/Citation, apps/api's own RAG types, and reuses the same
GenerationProvider abstraction RagService generates answers with (any
provider works as a judge, including the zero-cost MockGenerationProvider
in tests/dev).
"""

import json
from dataclasses import dataclass, field

from app.integrations.generation import GenerationProvider
from app.rag.service import Citation, RagAnswer

JUDGE_TEMPERATURE = 0.0

JUDGE_SYSTEM_PROMPT = (
    "You are an impartial evaluator scoring an AI assistant's answer "
    "against the source evidence it was given. Respond with JSON only, "
    "no other text: "
    '{"score": <float 0.0-1.0>, "reason": "<one or two sentence '
    'explanation>", "failures": ["<specific problem>", ...]}. '
    '"failures" should be an empty list when the answer has no problems.'
)


@dataclass(frozen=True)
class GradeResult:
    grader: str
    score: float
    reason: str
    failures: list[str] = field(default_factory=list)
    judge_model: str = ""
    prompt_version: str = "v1"
    temperature: float = JUDGE_TEMPERATURE
    source_context: str = ""

    @property
    def passed(self) -> bool:
        return not self.failures


def _clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))


def _build_source_context(citations: list[Citation]) -> str:
    """Judges are scored against what the answer actually cited, not the
    full retrieved candidate set — RagAnswer doesn't retain uncited
    context, and grading faithfulness to sources that weren't even used
    to answer wouldn't be meaningful anyway."""
    if not citations:
        return "(no sources were cited)"
    return "\n\n".join(
        f"[{c.source_number}] (from {c.document_filename}, page {c.page_number})\n{c.quote}"
        for c in citations
    )


async def _run_judge(
    *,
    grader_name: str,
    generation_provider: GenerationProvider,
    user_prompt: str,
    prompt_version: str,
    source_context: str,
) -> GradeResult:
    result = await generation_provider.generate(
        system_prompt=JUDGE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        temperature=JUDGE_TEMPERATURE,
    )
    try:
        payload = json.loads(result.text)
        score = _clamp_score(float(payload["score"]))
        reason = str(payload.get("reason", ""))
        failures = [str(f) for f in payload.get("failures", [])]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        score = 0.0
        reason = result.text
        failures = ["grader returned invalid JSON"]

    return GradeResult(
        grader=grader_name,
        score=score,
        reason=reason,
        failures=failures,
        judge_model=result.model,
        prompt_version=prompt_version,
        temperature=JUDGE_TEMPERATURE,
        source_context=source_context,
    )


class FaithfulnessGrader:
    """Is every factual claim in the answer actually supported by its
    cited sources? (Hallucination detection — the answer may be well
    written and on-topic while still inventing facts the sources don't
    contain.)"""

    NAME = "faithfulness"
    PROMPT_VERSION = "faithfulness_v1"

    def __init__(self, generation_provider: GenerationProvider) -> None:
        self._generation_provider = generation_provider

    async def grade(self, *, question: str, answer: RagAnswer) -> GradeResult:
        source_context = _build_source_context(answer.citations)
        user_prompt = (
            f"Question: {question}\n\n"
            f"Answer: {answer.answer}\n\n"
            f"Cited sources:\n{source_context}\n\n"
            "Score how faithful the answer is to ONLY the cited sources above. "
            "1.0 means every factual claim is directly supported by a cited "
            "source; 0.0 means the answer contradicts the sources or invents "
            "facts not present in them. List any specific unsupported or "
            'contradicted claims in "failures".'
        )
        return await _run_judge(
            grader_name=self.NAME,
            generation_provider=self._generation_provider,
            user_prompt=user_prompt,
            prompt_version=self.PROMPT_VERSION,
            source_context=source_context,
        )


class RelevanceGrader:
    """Does the answer actually address the question that was asked, as
    opposed to being faithful-but-off-topic or padded with tangents?"""

    NAME = "relevance"
    PROMPT_VERSION = "relevance_v1"

    def __init__(self, generation_provider: GenerationProvider) -> None:
        self._generation_provider = generation_provider

    async def grade(self, *, question: str, answer: RagAnswer) -> GradeResult:
        source_context = _build_source_context(answer.citations)
        user_prompt = (
            f"Question: {question}\n\n"
            f"Answer: {answer.answer}\n\n"
            "Score how directly and completely the answer addresses the "
            "question being asked. 1.0 means the answer is squarely on-topic "
            "and responsive; 0.0 means it is off-topic, evasive, or answers "
            'a different question. List specific relevance problems in "failures".'
        )
        return await _run_judge(
            grader_name=self.NAME,
            generation_provider=self._generation_provider,
            user_prompt=user_prompt,
            prompt_version=self.PROMPT_VERSION,
            source_context=source_context,
        )


class CompletenessGrader:
    """Does the answer cover what a known-good expected answer covers?
    Needs an EvaluationExample's expected_answer (Phase 25's dataset
    format) — unlike the other graders, there's no meaningful completeness
    score without something to compare against."""

    NAME = "completeness"
    PROMPT_VERSION = "completeness_v1"

    def __init__(self, generation_provider: GenerationProvider) -> None:
        self._generation_provider = generation_provider

    async def grade(self, *, question: str, answer: RagAnswer, expected_answer: str) -> GradeResult:
        source_context = _build_source_context(answer.citations)
        user_prompt = (
            f"Question: {question}\n\n"
            f"Expected answer (ground truth): {expected_answer}\n\n"
            f"Actual answer: {answer.answer}\n\n"
            "Score how completely the actual answer covers the key points in "
            "the expected answer. 1.0 means every key point is covered; 0.0 "
            "means the actual answer is missing most or all of them (partial "
            "credit for partial coverage). List specific missing points in "
            '"failures".'
        )
        return await _run_judge(
            grader_name=self.NAME,
            generation_provider=self._generation_provider,
            user_prompt=user_prompt,
            prompt_version=self.PROMPT_VERSION,
            source_context=source_context,
        )


class CitationSupportGrader:
    """For each individual citation: does the specific passage it points
    to actually support the claim it's attached to? Narrower than
    FaithfulnessGrader, which judges the answer as a whole — this catches
    a citation marker attached to the wrong sentence, or a real quote used
    to support a claim it doesn't actually back up."""

    NAME = "citation_support"
    PROMPT_VERSION = "citation_support_v1"

    def __init__(self, generation_provider: GenerationProvider) -> None:
        self._generation_provider = generation_provider

    async def grade(self, *, question: str, answer: RagAnswer) -> GradeResult:
        source_context = _build_source_context(answer.citations)
        if not answer.citations:
            return GradeResult(
                grader=self.NAME,
                score=0.0,
                reason="Answer has no citations to check support for.",
                failures=["no citations present"],
                judge_model="none",
                prompt_version=self.PROMPT_VERSION,
                temperature=JUDGE_TEMPERATURE,
                source_context=source_context,
            )

        user_prompt = (
            f"Question: {question}\n\n"
            f"Answer: {answer.answer}\n\n"
            f"Cited sources (numbered to match the [n] markers in the answer):\n"
            f"{source_context}\n\n"
            "For each [n] citation marker in the answer, check whether the "
            "text immediately around that marker is actually supported by "
            "source [n]'s content — not just topically related, but a "
            "genuine match. Score the overall fraction of citations that are "
            "properly supported (1.0 = all citations check out, 0.0 = none "
            'do). List each unsupported or mismatched citation in "failures", '
            "identified by its [n] number."
        )
        return await _run_judge(
            grader_name=self.NAME,
            generation_provider=self._generation_provider,
            user_prompt=user_prompt,
            prompt_version=self.PROMPT_VERSION,
            source_context=source_context,
        )
