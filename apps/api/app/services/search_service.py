"""Semantic search (Phase 14): query -> query embedding -> pgvector
similarity, scoped to a project the requesting user is actually a member
of. Keyword search (Phase 15) and hybrid fusion (Phase 16) build on top of
this rather than replacing it.
"""

import uuid
from dataclasses import dataclass

from app.integrations.embeddings import EmbeddingProvider
from app.models.chunk import DocumentChunk
from app.repositories.chunk_repository import DocumentChunkRepository
from app.services.project_service import ProjectService


@dataclass(frozen=True)
class SearchResult:
    chunk: DocumentChunk
    score: float


class SearchService:
    def __init__(
        self,
        chunk_repository: DocumentChunkRepository,
        project_service: ProjectService,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._chunk_repository = chunk_repository
        self._project_service = project_service
        self._embedding_provider = embedding_provider

    async def semantic_search(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, query: str, limit: int = 10
    ) -> list[SearchResult]:
        # Membership check first — a non-member gets the same 404 as a
        # nonexistent project (see ProjectService.get_project_for_user),
        # never search results from a project they can't see.
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)

        [query_embedding] = await self._embedding_provider.embed([query])
        pairs = await self._chunk_repository.search_by_embedding(
            project_id=project_id, query_embedding=query_embedding, limit=limit
        )
        return [SearchResult(chunk=chunk, score=score) for chunk, score in pairs]
