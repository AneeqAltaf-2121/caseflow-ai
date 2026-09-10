import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import MockGenerationProvider
from app.jobs.reports import generate_report
from app.models.chunk import DocumentChunk
from app.models.job import JobStatus
from app.models.report import ReportStatus, ReportType
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.job_repository import JobRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import MockReranker
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _seed(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="r@x.com", display_name="Reporter")
    org = await OrganizationRepository(db_session).create(name="Co", slug="co")
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


async def test_generate_report_succeeds_and_persists_sections(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with db_session_factory() as session:
        owner, project, embedder = await _seed(session)
        report = await ReportRepository(session).create(
            project_id=project.id,
            report_type=ReportType.EXECUTIVE_SUMMARY,
            title="Q1 Summary",
            created_by=owner.id,
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
        generation_provider=MockGenerationProvider(canned_response="Summary text [1]."),
    )

    async with db_session_factory() as session:
        refreshed_report = await ReportRepository(session).get_by_id(report_id)
        refreshed_job = await JobRepository(session).get_by_id(job_id)
        assert refreshed_report is not None and refreshed_job is not None
        assert refreshed_report.status == ReportStatus.READY
        assert refreshed_job.status == JobStatus.SUCCEEDED
        assert len(refreshed_report.sections) == 1
        assert refreshed_report.sections[0].heading == "Overview"
        assert refreshed_report.sections[0].content == "Summary text [1]."
        assert len(refreshed_report.sections[0].citations) == 1
        assert refreshed_report.sections[0].citations[0].document.filename == "contract.txt"


async def test_generate_report_handles_missing_report(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    import uuid

    async with db_session_factory() as session:
        job = await JobRepository(session).create(
            type="report_generation", payload={"report_id": str(uuid.uuid4())}
        )
        await session.commit()
        job_id = job.id

    # Should mark the job failed rather than raise.
    await generate_report(
        job_id=job_id,
        report_id=uuid.uuid4(),
        session_factory=db_session_factory,
        embedding_provider=LocalEmbeddingProvider(dimensions=8),
        reranker=MockReranker(),
        generation_provider=MockGenerationProvider(),
    )

    async with db_session_factory() as session:
        job = await JobRepository(session).get_by_id(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
