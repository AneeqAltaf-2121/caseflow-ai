"""Deterministic answer evaluation (Phase 27): checks that don't need a
judgment call — either a citation points somewhere real or it doesn't,
either the answer is well-formed JSON or it isn't. Complements Phase
28's LLM-as-a-judge graders, which handle the checks that do need
judgment (faithfulness, relevance, completeness). Runs directly against
a RagAnswer plus the DB state it claims to be grounded in, so it works
equally well as a post-hoc regression check over an EvaluationRun
(Phase 29) or a live sanity check on a fresh answer.
"""

import uuid
from dataclasses import dataclass, field

from pydantic import ValidationError

from app.rag.service import Citation, RagAnswer
from app.repositories.chunk_repository import DocumentChunkRepository
from app.schemas.rag import AskAnswerRead, CitationRead

DEFAULT_LATENCY_THRESHOLD_MS = 10_000


@dataclass(frozen=True)
class CitationCheckResult:
    source_number: int
    # The source_number falls within the range of sources actually
    # offered as context (1..sources_considered) — guards against a
    # malformed/out-of-range citation reaching evaluation independent of
    # RagService's own extraction bounds (e.g. re-scoring stored data).
    citation_exists: bool
    references_real_chunk: bool
    belongs_to_project: bool

    @property
    def passed(self) -> bool:
        return self.citation_exists and self.references_real_chunk and self.belongs_to_project


@dataclass(frozen=True)
class DeterministicCheckResult:
    json_schema_valid: bool
    has_required_citations: bool
    within_latency_threshold: bool
    citation_results: list[CitationCheckResult] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _check_json_schema_valid(answer: RagAnswer) -> bool:
    try:
        AskAnswerRead(
            answer=answer.answer,
            citations=[
                CitationRead(
                    source_number=c.source_number,
                    document_id=c.document_id,
                    document_chunk_id=c.document_chunk_id,
                    document_filename=c.document_filename,
                    page_number=c.page_number,
                    quote=c.quote,
                )
                for c in answer.citations
            ],
            sources_considered=answer.sources_considered,
            model=answer.model,
            insufficient_evidence=answer.insufficient_evidence,
        )
        return True
    except ValidationError:
        return False


async def _check_citation(
    citation: Citation,
    *,
    sources_considered: int,
    project_id: uuid.UUID,
    chunk_repository: DocumentChunkRepository,
) -> CitationCheckResult:
    citation_exists = 1 <= citation.source_number <= sources_considered

    chunk = await chunk_repository.get_by_id_with_document(citation.document_chunk_id)
    references_real_chunk = chunk is not None
    belongs_to_project = chunk is not None and chunk.document.project_id == project_id

    return CitationCheckResult(
        source_number=citation.source_number,
        citation_exists=citation_exists,
        references_real_chunk=references_real_chunk,
        belongs_to_project=belongs_to_project,
    )


async def run_deterministic_checks(
    *,
    answer: RagAnswer,
    project_id: uuid.UUID,
    chunk_repository: DocumentChunkRepository,
    latency_threshold_ms: int = DEFAULT_LATENCY_THRESHOLD_MS,
) -> DeterministicCheckResult:
    json_schema_valid = _check_json_schema_valid(answer)

    # An answer that claims to be grounded (insufficient_evidence is
    # False) must actually cite something; an answer that admits it has
    # no evidence is correct to cite nothing.
    has_required_citations = answer.insufficient_evidence or len(answer.citations) > 0

    within_latency_threshold = answer.latency_ms <= latency_threshold_ms

    citation_results = [
        await _check_citation(
            citation,
            sources_considered=answer.sources_considered,
            project_id=project_id,
            chunk_repository=chunk_repository,
        )
        for citation in answer.citations
    ]

    failures: list[str] = []
    if not json_schema_valid:
        failures.append("json_schema_valid: answer does not match AskAnswerRead schema")
    if not has_required_citations:
        failures.append("has_required_citations: answer is grounded but cites no sources")
    if not within_latency_threshold:
        failures.append(
            f"within_latency_threshold: {answer.latency_ms}ms exceeds {latency_threshold_ms}ms"
        )
    for result in citation_results:
        if not result.citation_exists:
            failures.append(f"citation_exists: source [{result.source_number}] is out of range")
        if not result.references_real_chunk:
            failures.append(
                f"citation_references_real_chunk: source [{result.source_number}] "
                "chunk does not exist"
            )
        elif not result.belongs_to_project:
            failures.append(
                f"citation_belongs_to_project: source [{result.source_number}] "
                "chunk belongs to a different project"
            )

    return DeterministicCheckResult(
        json_schema_valid=json_schema_valid,
        has_required_citations=has_required_citations,
        within_latency_threshold=within_latency_threshold,
        citation_results=citation_results,
        failures=failures,
    )
