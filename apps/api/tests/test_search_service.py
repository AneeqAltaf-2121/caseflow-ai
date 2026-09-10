import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.integrations.embeddings import LocalEmbeddingProvider
from app.models.chunk import DocumentChunk
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.project_service import ProjectService
from app.services.search_service import SearchService

pytestmark = pytest.mark.asyncio


async def _seed(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="owner@x.com", display_name="Owner")
    outsider = await UserRepository(db_session).create(
        email="outsider@x.com", display_name="Outsider"
    )
    org = await OrganizationRepository(db_session).create(name="Co", slug="co")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Legal Docs", description=None, created_by=owner.id
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

    provider = LocalEmbeddingProvider(dimensions=64)
    [about_termination, about_payment] = await provider.embed(
        ["This agreement terminates after 90 days notice.", "Payment is due net 30."]
    )
    await DocumentChunkRepository(db_session).bulk_create(
        [
            DocumentChunk(
                document_id=document.id,
                document_version_id=document.versions[0].id,
                page_number=1,
                section=None,
                text="This agreement terminates after 90 days notice.",
                token_count=7,
                start_offset=0,
                end_offset=10,
                embedding=about_termination,
                chunk_metadata={},
            ),
            DocumentChunk(
                document_id=document.id,
                document_version_id=document.versions[0].id,
                page_number=1,
                section=None,
                text="Payment is due net 30.",
                token_count=5,
                start_offset=10,
                end_offset=20,
                embedding=about_payment,
                chunk_metadata={},
            ),
        ]
    )
    await db_session.commit()
    return owner, outsider, project, provider


async def test_semantic_search_ranks_the_more_relevant_chunk_first(
    db_session: AsyncSession,
) -> None:
    owner, _outsider, project, provider = await _seed(db_session)
    service = SearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session)), provider
    )

    # LocalEmbeddingProvider is lexical (see ADR 007), not deep-semantic —
    # the query needs literal word overlap with the target passage.
    results = await service.semantic_search(
        project_id=project.id, user_id=owner.id, query="when does this agreement terminate?"
    )

    assert results[0].chunk.text.startswith("This agreement terminates")
    assert results[0].score > results[1].score


async def test_semantic_search_rejects_non_member(db_session: AsyncSession) -> None:
    _owner, outsider, project, provider = await _seed(db_session)
    service = SearchService(
        DocumentChunkRepository(db_session), ProjectService(ProjectRepository(db_session)), provider
    )

    with pytest.raises(NotFoundError):
        await service.semantic_search(project_id=project.id, user_id=outsider.id, query="anything")
