import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.embeddings import LocalEmbeddingProvider
from app.integrations.generation import MockGenerationProvider
from app.models.chunk import DocumentChunk
from app.models.report import ReportType
from app.rag.service import RagService
from app.reports.generator import generate_sections
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import MockReranker
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService
from app.services.retrieval_service import RetrievalService

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

    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session)), embedder
    )
    retrieval_service = RetrievalService(hybrid_service, MockReranker())
    generation_provider = MockGenerationProvider(canned_response="Answer [1].")
    rag_service = RagService(retrieval_service, generation_provider)
    return owner, project, rag_service


async def test_generate_sections_single_section_report(db_session: AsyncSession) -> None:
    owner, project, rag_service = await _seed(db_session)

    sections = await generate_sections(
        rag_service=rag_service,
        project_id=project.id,
        user_id=owner.id,
        report_type=ReportType.EXECUTIVE_SUMMARY,
    )

    assert len(sections) == 1
    assert sections[0].heading == "Overview"
    assert sections[0].content == "Answer [1]."
    assert len(sections[0].citations) == 1
    assert sections[0].citations[0].document_filename == "contract.txt"


async def test_generate_sections_multi_section_report(db_session: AsyncSession) -> None:
    owner, project, rag_service = await _seed(db_session)

    sections = await generate_sections(
        rag_service=rag_service,
        project_id=project.id,
        user_id=owner.id,
        report_type=ReportType.RESEARCH_MEMO,
    )

    assert [s.heading for s in sections] == ["Summary", "Analysis", "Recommendations"]
    for section in sections:
        assert len(section.citations) == 1
