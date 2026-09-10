"""Keyword search (Phase 15) — same shape as SearchService (semantic),
so routes/frontend can treat them interchangeably until hybrid fusion
(Phase 16) combines both.
"""

import uuid
from dataclasses import dataclass

from app.models.chunk import DocumentChunk
from app.repositories.chunk_repository import DocumentChunkRepository
from app.retrieval.keyword import bm25_search
from app.services.project_service import ProjectService


@dataclass(frozen=True)
class KeywordSearchResult:
    chunk: DocumentChunk
    score: float


class KeywordSearchService:
    def __init__(
        self, chunk_repository: DocumentChunkRepository, project_service: ProjectService
    ) -> None:
        self._chunk_repository = chunk_repository
        self._project_service = project_service

    async def keyword_search(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, query: str, limit: int = 10
    ) -> list[KeywordSearchResult]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)

        chunks = await self._chunk_repository.list_for_project(project_id)
        pairs = bm25_search(chunks, query, limit=limit)
        return [KeywordSearchResult(chunk=chunk, score=score) for chunk, score in pairs]
