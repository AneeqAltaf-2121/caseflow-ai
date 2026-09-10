"""Phase 35: reliability and failure handling. Exercises the specific
failure modes the phase spec calls out, most of which reuse
infrastructure already built in earlier phases (Job.attempt/max_attempts,
JobRepository.mark_failed/record_failure, each job's transient-vs-
permanent failure split) rather than inventing new machinery — this file
is about proving that infrastructure actually behaves correctly under
each named scenario, not building a second one.

Not covered here: a real Redis/Postgres outage. This sandbox has no live
Redis/Postgres to kill and restart (see docs/decisions on IaC-only
deployment) — the closest honest equivalent is the generic-exception
retry path every job already has, which duplicate_upload/embedding_error/
llm_timeout below all exercise via different injected failures.
"""

import hashlib
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import Settings, get_settings
from app.errors import ConflictError
from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import GenerationProvider, GenerationResult
from app.integrations.storage import LocalStorageBackend
from app.jobs.evaluations import run_evaluation
from app.jobs.ingestion import process_document
from app.jobs.reports import generate_report
from app.models.chunk import DocumentChunk
from app.models.document import DocumentStatus
from app.models.evaluation import EvaluationRunStatus
from app.models.job import JobStatus
from app.models.report import ReportStatus, ReportType
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.evaluation_repository import EvaluationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import MockReranker
from app.services.document_service import DocumentService, UploadedFile
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


class _AlwaysRaisingGenerationProvider:
    """Simulates an LLM timeout / rate limit / any upstream provider
    failure — every call raises the given exception, never returns."""

    model = "always-fails-v1"

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> GenerationResult:
        raise self._exc


# --- duplicate upload ------------------------------------------------


async def test_duplicate_upload_is_rejected_with_conflict(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="dup@x.com", display_name="Dup")
        org = await OrganizationRepository(session).create(name="Dup", slug="dup-corp")
        await session.commit()
    headers = _auth_headers(owner.id)
    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Dup project"},
            headers=headers,
        )
    ).json()["id"]

    payload = {"file": ("evidence.txt", b"the exact same bytes", "text/plain")}
    first = await api_client.post(
        f"/projects/{project_id}/documents", files=payload, headers=headers
    )
    assert first.status_code == 201

    second = await api_client.post(
        f"/projects/{project_id}/documents", files=payload, headers=headers
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"

    # Only one document actually exists — the duplicate never touched
    # storage or created a second ingestion job.
    listing = await api_client.get(f"/projects/{project_id}/documents", headers=headers)
    assert len(listing.json()) == 1


async def test_reupload_after_failure_with_matching_checksum_is_allowed(
    db_session: AsyncSession,
) -> None:
    owner = await UserRepository(db_session).create(email="dup3@x.com", display_name="Dup3")
    org = await OrganizationRepository(db_session).create(name="Dup3", slug="dup3-corp")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
    )
    await db_session.commit()

    class _FakeStorage:
        async def put(self, *, key: str, data: bytes) -> None:
            return None

        async def get(self, *, key: str) -> bytes:
            raise NotImplementedError

        async def delete(self, *, key: str) -> None:
            return None

    service = DocumentService(
        DocumentRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        _FakeStorage(),
    )
    settings = Settings(max_upload_size_mb=50)
    file = UploadedFile(filename="x.txt", content_type="text/plain", data=b"retry me")

    first = await service.upload_document(
        project_id=project.id, user_id=owner.id, file=file, settings=settings
    )
    # Immediately re-uploading the identical content is a real duplicate.
    with pytest.raises(ConflictError):
        await service.upload_document(
            project_id=project.id, user_id=owner.id, file=file, settings=settings
        )

    await DocumentRepository(db_session).update_status(first, DocumentStatus.FAILED)
    await db_session.commit()

    checksum = hashlib.sha256(file.data).hexdigest()
    assert first.checksum_sha256 == checksum
    # Now that it's FAILED, the same content can be retried.
    retried = await service.upload_document(
        project_id=project.id, user_id=owner.id, file=file, settings=settings
    )
    assert retried.id != first.id


# --- embedding error (ingestion) --------------------------------------


class _AlwaysFailingEmbeddingProvider:
    dimensions = 8

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError("embedding provider unavailable")


async def test_embedding_failure_retries_then_fails_permanently(
    db_session_factory: async_sessionmaker[AsyncSession], tmp_path
) -> None:
    storage = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))

    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="emb@x.com", display_name="Emb")
        org = await OrganizationRepository(session).create(name="Emb", slug="emb-corp")
        project = await ProjectService(ProjectRepository(session)).create_project(
            organization_id=org.id, name="P", description=None, created_by=owner.id
        )
        document = await DocumentRepository(session).create(
            project_id=project.id,
            filename="notes.txt",
            content_type="text/plain",
            size_bytes=5,
            checksum_sha256="x",
            storage_key="k",
            uploaded_by=owner.id,
        )
        await session.commit()
        document_id = document.id

    await storage.put(key="k", data=b"hello world, this is a real document")

    async with db_session_factory() as session:
        job = await JobRepository(session).create(
            type="document_ingestion", payload={"document_id": str(document_id)}, max_attempts=1
        )
        await session.commit()
        job_id = job.id

    await process_document(
        job_id=job_id,
        document_id=document_id,
        session_factory=db_session_factory,
        storage=storage,
        embedding_provider=_AlwaysFailingEmbeddingProvider(),
    )

    async with db_session_factory() as session:
        final_document = await DocumentRepository(session).get_by_id(document_id)
        final_job = await JobRepository(session).get_by_id(job_id)
        assert final_document is not None and final_job is not None
        assert final_document.status == DocumentStatus.FAILED
        assert final_job.status == JobStatus.FAILED


# --- LLM timeout / rate limit (report generation) ----------------------


async def _seed_report_project(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="rel-rep@x.com", display_name="R")
    org = await OrganizationRepository(db_session).create(name="RelRep", slug="rel-rep-corp")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="P", description=None, created_by=owner.id
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

    embedder = LocalEmbeddingProvider(dimensions=16)
    text = "This agreement terminates after 90 days notice."
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


async def test_llm_timeout_during_report_generation_retries_then_fails_permanently(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        owner, project, embedder = await _seed_report_project(session)
        report = await ReportRepository(session).create(
            project_id=project.id,
            report_type=ReportType.EXECUTIVE_SUMMARY,
            title="Times Out",
            created_by=owner.id,
        )
        job = await JobRepository(session).create(
            type="report_generation", payload={"report_id": str(report.id)}, max_attempts=2
        )
        await session.commit()
        job_id, report_id = job.id, report.id

    timeout_provider: GenerationProvider = _AlwaysRaisingGenerationProvider(
        TimeoutError("LLM request timed out")
    )

    with pytest.raises(TimeoutError):
        await generate_report(
            job_id=job_id,
            report_id=report_id,
            session_factory=db_session_factory,
            embedding_provider=embedder,
            reranker=MockReranker(),
            generation_provider=timeout_provider,
        )

    async with db_session_factory() as session:
        job_after_first = await JobRepository(session).get_by_id(job_id)
        assert job_after_first is not None
        assert job_after_first.status == JobStatus.RUNNING
        assert job_after_first.attempt == 1

    # Second, final attempt: fails permanently, does not re-raise.
    await generate_report(
        job_id=job_id,
        report_id=report_id,
        session_factory=db_session_factory,
        embedding_provider=embedder,
        reranker=MockReranker(),
        generation_provider=timeout_provider,
    )

    async with db_session_factory() as session:
        final_report = await ReportRepository(session).get_by_id(report_id)
        final_job = await JobRepository(session).get_by_id(job_id)
        assert final_report is not None and final_job is not None
        assert final_report.status == ReportStatus.FAILED
        assert "timed out" in (final_report.error or "")
        assert final_job.status == JobStatus.FAILED
        assert final_job.attempt == 2


async def test_rate_limit_during_evaluation_run_retries_then_fails_permanently(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        owner, project, embedder = await _seed_report_project(session)
        run = await EvaluationRunRepository(session).create(
            project_id=project.id,
            dataset_name="sample_contract_qa",
            dataset_version=1,
            prompt_version_id=None,
            model="always-fails-v1",
            retriever_version="hybrid_rrf_v1",
            created_by=owner.id,
        )
        job = await JobRepository(session).create(
            type="evaluation_run", payload={"evaluation_run_id": str(run.id)}, max_attempts=2
        )
        await session.commit()
        job_id, run_id = job.id, run.id

    class RateLimitError(Exception):
        pass

    rate_limited_provider: GenerationProvider = _AlwaysRaisingGenerationProvider(
        RateLimitError("429: rate limit exceeded")
    )

    with pytest.raises(RateLimitError):
        await run_evaluation(
            job_id=job_id,
            evaluation_run_id=run_id,
            session_factory=db_session_factory,
            embedding_provider=embedder,
            reranker=MockReranker(),
            generation_provider=rate_limited_provider,
            judge_provider=rate_limited_provider,
        )

    async with db_session_factory() as session:
        run_after_first = await EvaluationRunRepository(session).get_by_id(run_id)
        job_after_first = await JobRepository(session).get_by_id(job_id)
        assert run_after_first is not None and job_after_first is not None
        assert run_after_first.status == EvaluationRunStatus.RUNNING
        assert job_after_first.attempt == 1

    await run_evaluation(
        job_id=job_id,
        evaluation_run_id=run_id,
        session_factory=db_session_factory,
        embedding_provider=embedder,
        reranker=MockReranker(),
        generation_provider=rate_limited_provider,
        judge_provider=rate_limited_provider,
    )

    async with db_session_factory() as session:
        final_run = await EvaluationRunRepository(session).get_by_id(run_id)
        final_job = await JobRepository(session).get_by_id(job_id)
        assert final_run is not None and final_job is not None
        assert final_run.status == EvaluationRunStatus.FAILED
        assert "rate limit" in (final_run.error or "")
        assert final_job.status == JobStatus.FAILED
        assert final_job.attempt == 2


# --- worker crash / partial write -> idempotent retry -------------------


async def test_worker_crash_mid_report_is_idempotent_on_retry(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Simulates a worker crashing after writing some sections but before
    marking the report READY: a naive retry would double the sections.
    generate_report clears previous sections before writing the fresh set
    (see its docstring), so the retried report ends up with exactly the
    right sections, not stale + fresh combined."""
    async with db_session_factory() as session:
        owner, project, embedder = await _seed_report_project(session)
        report = await ReportRepository(session).create(
            project_id=project.id,
            report_type=ReportType.EXECUTIVE_SUMMARY,
            title="Crash Recovery",
            created_by=owner.id,
        )
        # Simulate a section written by a first attempt that crashed
        # before the job/report were marked done.
        await ReportRepository(session).add_section(
            report_id=report.id, heading="Stale", content="From a crashed attempt", position=1
        )
        job = await JobRepository(session).create(
            type="report_generation", payload={"report_id": str(report.id)}
        )
        await session.commit()
        job_id, report_id = job.id, report.id

    await generate_report(
        job_id=job_id,
        report_id=report_id,
        session_factory=db_session_factory,
        embedding_provider=embedder,
        reranker=MockReranker(),
        generation_provider=_StaticAnswerProvider("Fresh summary [1]."),
    )

    async with db_session_factory() as session:
        final_report = await ReportRepository(session).get_by_id(report_id)
        assert final_report is not None
        assert final_report.status == ReportStatus.READY
        assert len(final_report.sections) == 1
        assert final_report.sections[0].heading == "Overview"
        assert final_report.sections[0].content == "Fresh summary [1]."


class _StaticAnswerProvider:
    model = "static-v1"

    def __init__(self, text: str) -> None:
        self._text = text

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> GenerationResult:
        return GenerationResult(text=self._text, model=self.model, input_tokens=5, output_tokens=5)
