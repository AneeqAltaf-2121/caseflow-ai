"""Hybrid retrieval (Phase 16): vector + keyword candidates, combined by
reciprocal rank fusion. Neither retriever is replaced — semantic search
(Phase 14) and keyword search (Phase 15) stay available on their own.
"""

import uuid

from app.integrations.embeddings import EmbeddingProvider
from app.repositories.chunk_repository import DocumentChunkRepository
from app.retrieval.fusion import FusedResult, reciprocal_rank_fusion
from app.retrieval.keyword import bm25_search
from app.services.project_service import ProjectService

DEFAULT_CANDIDATE_LIMIT = 30
DEFAULT_RESULT_LIMIT = 20


class HybridSearchService:
    def __init__(
        self,
        chunk_repository: DocumentChunkRepository,
        project_service: ProjectService,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self._chunk_repository = chunk_repository
        self._project_service = project_service
        self._embedding_provider = embedding_provider

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        """Exposed so callers (RetrievalService.describe_config, for
        ModelRun.retrieval_config — Phase 23) can identify which embedding
        model produced a given answer's context, without reaching into a
        private attribute."""
        return self._embedding_provider

    async def hybrid_search(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        query: str,
        candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
        limit: int = DEFAULT_RESULT_LIMIT,
    ) -> list[FusedResult]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)

        [query_embedding] = await self._embedding_provider.embed([query])
        vector_results = await self._chunk_repository.search_by_embedding(
            project_id=project_id, query_embedding=query_embedding, limit=candidate_limit
        )

        all_chunks = await self._chunk_repository.list_for_project(project_id)
        keyword_results = bm25_search(all_chunks, query, limit=candidate_limit)

        return reciprocal_rank_fusion(vector_results, keyword_results, limit=limit)
