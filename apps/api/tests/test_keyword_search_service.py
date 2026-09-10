import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.chunk import DocumentChunk
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.keyword_search_service import KeywordSearchService
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _seed(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="owner@x.com", display_name="Owner")
    outsider = await UserRepository(db_session).create(
        email="outsider@x.com", display_name="Outsider"
    )
    org = await OrganizationRepository(db_session).create(name="Co", slug="co")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Contracts", description=None, created_by=owner.id
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

    await DocumentChunkRepository(db_session).bulk_create(
        [
            DocumentChunk(
                document_id=document.id,
                document_version_id=document.versions[0].id,
                page_number=1,
                section=None,
                text="The indemnification clause survives termination.",
                token_count=6,
                start_offset=0,
                end_offset=10,
                embedding=None,
                chunk_metadata={},
            )
        ]
    )
    await db_session.commit()
    return owner, outsider, project


async def test_keyword_search_finds_exact_term(db_session: AsyncSession) -> None:
    owner, _outsider, project = await _seed(db_session)
    service = KeywordSearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session))
    )

    results = await service.keyword_search(
        project_id=project.id, user_id=owner.id, query="indemnification"
    )

    assert len(results) == 1
    assert "indemnification" in results[0].chunk.text.lower()


async def test_keyword_search_rejects_non_member(db_session: AsyncSession) -> None:
    _owner, outsider, project = await _seed(db_session)
    service = KeywordSearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session))
    )

    with pytest.raises(NotFoundError):
        await service.keyword_search(project_id=project.id, user_id=outsider.id, query="anything")
