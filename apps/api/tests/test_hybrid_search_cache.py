"""Phase 33: confirms HybridSearchService actually consults the cache
(not just that results look the same, which would be true regardless
since the underlying data doesn't change) by counting embedding-provider
calls — a cache hit should mean the embedding provider and DB search are
never invoked a second time for an identical query."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import InMemoryCache
from app.integrations.embeddings import LocalEmbeddingProvider
from app.models.chunk import DocumentChunk
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


class _CountingEmbeddingProvider:
    """Wraps a real embedding provider, counting .embed() calls."""

    def __init__(self, inner: LocalEmbeddingProvider) -> None:
        self._inner = inner
        self.dimensions = inner.dimensions
        self.call_count = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.call_count += 1
        return await self._inner.embed(texts)


async def _seed(db_session: AsyncSession, embedder: LocalEmbeddingProvider):
    owner = await UserRepository(db_session).create(email="cache-test@x.com", display_name="C")
    org = await OrganizationRepository(db_session).create(name="Co", slug="co-hybrid-cache")
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
    return owner, project


async def test_second_identical_query_is_served_from_cache(db_session: AsyncSession) -> None:
    embedder = LocalEmbeddingProvider(dimensions=32)
    owner, project = await _seed(db_session, embedder)
    counting_embedder = _CountingEmbeddingProvider(embedder)
    cache = InMemoryCache()
    service = HybridSearchService(
        DocumentChunkRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        counting_embedder,
        cache,
    )

    first = await service.hybrid_search(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )
    assert counting_embedder.call_count == 1
    assert len(first) == 1

    second = await service.hybrid_search(
        project_id=project.id, user_id=owner.id, query="agreement terminates"
    )
    # No second embed() call at all -> served entirely from cache.
    assert counting_embedder.call_count == 1
    assert [r.chunk.id for r in second] == [r.chunk.id for r in first]
    assert second[0].fused_score == first[0].fused_score


async def test_different_query_is_not_a_cache_hit(db_session: AsyncSession) -> None:
    embedder = LocalEmbeddingProvider(dimensions=32)
    owner, project = await _seed(db_session, embedder)
    counting_embedder = _CountingEmbeddingProvider(embedder)
    cache = InMemoryCache()
    service = HybridSearchService(
        DocumentChunkRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        counting_embedder,
        cache,
    )

    await service.hybrid_search(project_id=project.id, user_id=owner.id, query="agreement")
    await service.hybrid_search(project_id=project.id, user_id=owner.id, query="payment terms")

    assert counting_embedder.call_count == 2


async def test_without_a_cache_every_call_recomputes(db_session: AsyncSession) -> None:
    embedder = LocalEmbeddingProvider(dimensions=32)
    owner, project = await _seed(db_session, embedder)
    counting_embedder = _CountingEmbeddingProvider(embedder)
    service = HybridSearchService(
        DocumentChunkRepository(db_session),
        ProjectService(ProjectRepository(db_session)),
        counting_embedder,
        # No cache passed -> defaults to None, caching opt-out preserved.
    )

    await service.hybrid_search(project_id=project.id, user_id=owner.id, query="agreement")
    await service.hybrid_search(project_id=project.id, user_id=owner.id, query="agreement")

    assert counting_embedder.call_count == 2
