import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import MockGenerationProvider
from app.jobs.evaluations import run_evaluation
from app.models.chunk import DocumentChunk
from app.models.evaluation import EvaluationRunStatus
from app.models.job import JobStatus
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import MockReranker
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio

SAMPLE_DATASET_NAME = "sample_contract_qa"
CANNED_JUDGE_RESPONSE = '{"score": 0.8, "reason": "looks fine", "failures": []}'


async def _seed(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="evaluator@x.com", display_name="Eval")
    org = await OrganizationRepository(db_session).create(name="Co", slug="co-eval-job")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Legal", description=None, created_by=owner.id
    )
    document_repository = DocumentRepository(db_session)
    document = await document_repository.create(
        project_id=project.id,
        filename="contract.txt",
        content_type="text/plain",
        size_bytes=1,
        checksum_sha256="x",
        storage_key="contract.txt",
        uploaded_by=owner.id,
    )
    await db_session.commit()
    document = await document_repository.get_by_id(document.id)

    embedder = LocalEmbeddingProvider(dimensions=32)
    text = "The agreement terminates after 90 days notice."
    [embedding] = await embedder.embed([text])
    await DocumentChunkRepository(db_session).bulk_create(
        [
            DocumentChunk(
                document_id=document.id,
                document_version_id=document.versions[0].id,
                page_number=1,
                section=None,
                text=text,
                token_count=7,
                start_offset=0,
                end_offset=len(text),
                embedding=embedding,
                chunk_metadata={},
            )
        ]
    )
    await db_session.commit()
    return owner, project, embedder


async def test_run_evaluation_succeeds_and_persists_results(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        owner, project, embedder = await _seed(session)
        run = await EvaluationRunRepository(session).create(
            project_id=project.id,
            dataset_name=SAMPLE_DATASET_NAME,
            dataset_version=1,
            prompt_version_id=None,
            model="mock-echo-v1",
            retriever_version="hybrid_rrf_v1",
            created_by=owner.id,
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
        embedding_provider=embedder,
        reranker=MockReranker(),
        generation_provider=MockGenerationProvider(
            canned_response="The agreement terminates after 90 days [1]."
        ),
        judge_provider=MockGenerationProvider(canned_response=CANNED_JUDGE_RESPONSE),
    )

    async with db_session_factory() as session:
        refreshed_run = await EvaluationRunRepository(session).get_by_id(run_id)
        refreshed_job = await JobRepository(session).get_by_id(job_id)
        assert refreshed_run is not None and refreshed_job is not None
        assert refreshed_run.status == EvaluationRunStatus.SUCCEEDED
        assert refreshed_job.status == JobStatus.SUCCEEDED
        assert refreshed_run.started_at is not None
        assert refreshed_run.finished_at is not None

        results = sorted(refreshed_run.results, key=lambda r: r.example_id)
        assert [r.example_id for r in results] == ["ex-001", "ex-002", "ex-003"]

        first = results[0]
        assert first.question == "When does the agreement terminate?"
        assert first.generated_answer == "The agreement terminates after 90 days [1]."
        assert first.faithfulness_score == 0.8
        assert first.relevance_score == 0.8
        assert first.completeness_score == 0.8  # every example has an expected_answer
        assert first.citation_support_score == 0.8
        assert first.citation_correct is True
        assert first.model_run_id is not None
        # Dataset examples all have empty relevant_chunk_ids -> nothing to
        # score retrieval against.
        assert first.recall_at_k is None
        assert first.precision_at_k is None
        assert first.mrr is None
        assert first.ndcg_at_k is None
        assert first.grader_details["faithfulness"]["reason"] == "looks fine"
        assert first.grader_details["completeness"] is not None


async def test_run_evaluation_handles_missing_run(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        job = await JobRepository(session).create(
            type="evaluation_run", payload={"evaluation_run_id": str(uuid.uuid4())}
        )
        await session.commit()
        job_id = job.id

    await run_evaluation(
        job_id=job_id,
        evaluation_run_id=uuid.uuid4(),
        session_factory=db_session_factory,
        embedding_provider=LocalEmbeddingProvider(dimensions=8),
        reranker=MockReranker(),
        generation_provider=MockGenerationProvider(),
        judge_provider=MockGenerationProvider(canned_response=CANNED_JUDGE_RESPONSE),
    )

    async with db_session_factory() as session:
        job = await JobRepository(session).get_by_id(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED


async def test_run_evaluation_handles_missing_dataset(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        owner, project, embedder = await _seed(session)
        run = await EvaluationRunRepository(session).create(
            project_id=project.id,
            dataset_name="does_not_exist_dataset",
            dataset_version=1,
            prompt_version_id=None,
            model="mock-echo-v1",
            retriever_version="hybrid_rrf_v1",
            created_by=owner.id,
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
        embedding_provider=embedder,
        reranker=MockReranker(),
        generation_provider=MockGenerationProvider(),
        judge_provider=MockGenerationProvider(canned_response=CANNED_JUDGE_RESPONSE),
    )

    async with db_session_factory() as session:
        refreshed_run = await EvaluationRunRepository(session).get_by_id(run_id)
        refreshed_job = await JobRepository(session).get_by_id(job_id)
        assert refreshed_run is not None and refreshed_job is not None
        assert refreshed_run.status == EvaluationRunStatus.FAILED
        assert refreshed_job.status == JobStatus.FAILED
        assert refreshed_run.error is not None
