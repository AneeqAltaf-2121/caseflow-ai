"""Phase 58: RAG regression suite.

Runs the real evaluation pipeline (app/jobs/evaluations.py's
run_evaluation — real retrieval, real hybrid fusion, real reranking,
real citation extraction/validation; only the LLM call itself is
mocked, since this environment has no LLM API keys, same constraint
every other test in this suite already lives with) against a golden
dataset built here from an intentionally noisy 20-chunk corpus, and
asserts hard regression thresholds on the result.

Only retrieval metrics (recall/precision/MRR/NDCG) and the
deterministic citation checks are genuinely meaningful regression
signals here — LLM-as-judge scores (faithfulness/relevance/
completeness/citation_support) come from a canned mock response and
don't vary with real answer quality, so this suite doesn't assert
thresholds on them (see test_evaluation_job.py, which already checks
that plumbing is wired correctly).

A failure here means retrieval, fusion, reranking, or citation
handling got measurably worse — that's the point: this test is
supposed to start failing the day someone breaks one of those.
"""

import uuid
from pathlib import Path

import pytest
from caseflow_evals import EvaluationDataset, EvaluationExample, save_dataset
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import MockGenerationProvider
from app.jobs.evaluations import run_evaluation
from app.models.chunk import DocumentChunk
from app.models.evaluation import EvaluationRunStatus
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import CrossEncoderReranker
from app.services.project_service import ProjectService

DATASET_NAME = "rag_regression_suite"

# One clearly on-topic "signal" chunk per question, buried among 16
# lexically distinct "noise" chunks (20 total) — recall@5 only comes
# out to 1.0 if retrieval genuinely ranks the right chunk into the top
# 5 out of 20, not merely "top 5 out of 5".
SIGNAL_CHUNKS = {
    "termination": "This agreement will terminate ninety days after written notice.",
    "payment": "The payment term is net thirty days from the date of the invoice.",
    "indemnification": "The indemnification clause survives termination of this agreement.",
    "governing_law": "New York law governs this agreement in all respects.",
}

# Questions deliberately reuse the chunk's own literal key terms — both
# BM25 (app/retrieval/keyword.py) and LocalEmbeddingProvider
# (app/integrations/embeddings.py) tokenize without stemming, so
# "terminate" and "terminates" are unrelated tokens to either. This
# mirrors how a real user would phrase a question about their own
# document, not an adversarial paraphrase.
QUESTIONS = {
    "termination": "When does this agreement terminate?",
    "payment": "What is the payment term?",
    "indemnification": "Does the indemnification clause survive termination?",
    "governing_law": "What law governs this agreement?",
}

NOISE_SUBJECTS = [
    "the marketing team",
    "the office lease",
    "the software license",
    "the delivery schedule",
    "the onboarding process",
    "the warranty period",
    "the confidentiality provision",
    "the escalation procedure",
]
NOISE_PREDICATES = [
    "was updated last quarter after a routine review.",
    "does not apply outside normal business hours.",
    "requires sign-off from two separate departments.",
    "is renewed automatically every calendar year.",
    "excludes any liability for third-party integrations.",
    "was discussed in the most recent planning meeting.",
    "has no bearing on unrelated vendor agreements.",
    "is tracked separately in the project management system.",
]

CANNED_ANSWER = "Based on the provided context, here is the answer [1]."
CANNED_JUDGE_RESPONSE = '{"score": 0.8, "reason": "looks fine", "failures": []}'

RECALL_AT_K_THRESHOLD = 1.0
MRR_THRESHOLD = 0.5
NDCG_AT_K_THRESHOLD = 0.5


async def _seed_corpus(
    db_session: AsyncSession, provider: LocalEmbeddingProvider
) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """Returns (project_id, user_id, {topic: chunk_id})."""
    owner = await UserRepository(db_session).create(
        email="rag-regression@example.com", display_name="Regression"
    )
    org = await OrganizationRepository(db_session).create(name="Co", slug="co-rag-regression")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Regression Suite", description=None, created_by=owner.id
    )
    document_repository = DocumentRepository(db_session)
    document = await document_repository.create(
        project_id=project.id,
        filename="corpus.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="x",
        storage_key="corpus.txt",
        uploaded_by=owner.id,
    )
    await db_session.commit()
    document = await document_repository.get_by_id(document.id)
    assert document is not None
    version_id = document.versions[0].id

    noise_texts = [
        f"{NOISE_SUBJECTS[i % len(NOISE_SUBJECTS)].capitalize()} "
        f"{NOISE_PREDICATES[(i * 5) % len(NOISE_PREDICATES)]}"
        for i in range(16)
    ]
    all_texts = list(SIGNAL_CHUNKS.values()) + noise_texts
    embeddings = await provider.embed(all_texts)

    chunk_repository = DocumentChunkRepository(db_session)
    chunks = [
        DocumentChunk(
            document_id=document.id,
            document_version_id=version_id,
            page_number=1,
            section=None,
            text=text,
            token_count=len(text.split()),
            start_offset=i * 100,
            end_offset=i * 100 + len(text),
            embedding=embedding,
            chunk_metadata={},
        )
        for i, (text, embedding) in enumerate(zip(all_texts, embeddings, strict=True))
    ]
    created = await chunk_repository.bulk_create(chunks)
    await db_session.commit()

    signal_chunk_ids = {topic: str(created[i].id) for i, topic in enumerate(SIGNAL_CHUNKS)}
    return project.id, owner.id, signal_chunk_ids


def _build_dataset(signal_chunk_ids: dict[str, str]) -> EvaluationDataset:
    examples = [
        EvaluationExample(
            id=topic,
            question=QUESTIONS[topic],
            expected_answer=SIGNAL_CHUNKS[topic],
            relevant_chunk_ids=[signal_chunk_ids[topic]],
        )
        for topic in SIGNAL_CHUNKS
    ]
    return EvaluationDataset(
        name=DATASET_NAME, version=1, description="Phase 58 regression suite", examples=examples
    )


async def test_rag_pipeline_meets_retrieval_regression_thresholds(
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # More buckets than test_search_service.py's 64 — this corpus has 16
    # noise chunks with their own vocabulary, and fewer hash buckets
    # means more spurious collisions between unrelated words diluting
    # the real signal.
    provider = LocalEmbeddingProvider(dimensions=256)

    async with db_session_factory() as session:
        project_id, user_id, signal_chunk_ids = await _seed_corpus(session, provider)

    dataset = _build_dataset(signal_chunk_ids)
    dataset_path = tmp_path / f"{DATASET_NAME}.json"
    save_dataset(dataset, dataset_path)

    # run_evaluation resolves the dataset by name via resolve_dataset_path,
    # imported directly into app.jobs.evaluations's namespace — patch it
    # there (not on app.evals.dataset_paths) so the running job actually
    # picks up this test's on-disk dataset instead of the real one.
    monkeypatch.setattr("app.jobs.evaluations.resolve_dataset_path", lambda _name: dataset_path)

    async with db_session_factory() as session:
        run = await EvaluationRunRepository(session).create(
            project_id=project_id,
            dataset_name=DATASET_NAME,
            dataset_version=1,
            prompt_version_id=None,
            model="mock-echo-v1",
            retriever_version="hybrid_rrf_v1",
            created_by=user_id,
        )
        job = await JobRepository(session).create(
            type="evaluation_run", payload={"evaluation_run_id": str(run.id)}
        )
        await session.commit()
        job_id, run_id = job.id, run.id

    await run_evaluation(
        job_id=job_id,
        evaluation_run_id=run_id,
        session_factory=db_session_factory,
        embedding_provider=provider,
        reranker=CrossEncoderReranker(),
        generation_provider=MockGenerationProvider(canned_response=CANNED_ANSWER),
        judge_provider=MockGenerationProvider(canned_response=CANNED_JUDGE_RESPONSE),
    )

    async with db_session_factory() as session:
        refreshed_run = await EvaluationRunRepository(session).get_by_id(run_id)
        assert refreshed_run is not None
        assert refreshed_run.status == EvaluationRunStatus.SUCCEEDED

        results = {r.example_id: r for r in refreshed_run.results}
        assert set(results) == set(SIGNAL_CHUNKS)

        for topic, result in results.items():
            # Deterministic citation checks: a real RagService answer,
            # over real retrieved/reranked context, must cite a real
            # chunk that really belongs to this project.
            assert result.citation_correct is True, f"{topic}: citations failed validation"

            # Retrieval regression thresholds: the one relevant chunk
            # (out of 20, 16 of them noise) must be found, and found
            # near the top — this is what actually breaks if hybrid
            # fusion, embeddings, or reranking regress.
            assert result.recall_at_k is not None and result.recall_at_k >= RECALL_AT_K_THRESHOLD, (
                f"{topic}: recall@k {result.recall_at_k} below {RECALL_AT_K_THRESHOLD}"
            )
            assert result.mrr is not None and result.mrr >= MRR_THRESHOLD, (
                f"{topic}: MRR {result.mrr} below {MRR_THRESHOLD}"
            )
            assert result.ndcg_at_k is not None and result.ndcg_at_k >= NDCG_AT_K_THRESHOLD, (
                f"{topic}: NDCG@k {result.ndcg_at_k} below {NDCG_AT_K_THRESHOLD}"
            )
