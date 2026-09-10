"""The full retrieval pipeline (Phase 17): hybrid search's top ~20 fused
candidates, narrowed by a reranker to the 5-8 passages Phase 19's RAG
generation actually uses as context.
"""

import uuid
from dataclasses import dataclass

from app.models.chunk import DocumentChunk
from app.retrieval.reranker import DEFAULT_TOP_K, Reranker
from app.services.hybrid_search_service import HybridSearchService


@dataclass(frozen=True)
class RerankedResult:
    chunk: DocumentChunk
    score: float


class RetrievalService:
    def __init__(self, hybrid_search_service: HybridSearchService, reranker: Reranker) -> None:
        self._hybrid_search_service = hybrid_search_service
        self._reranker = reranker

    async def retrieve(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, query: str, top_k: int = DEFAULT_TOP_K
    ) -> list[RerankedResult]:
        fused = await self._hybrid_search_service.hybrid_search(
            project_id=project_id, user_id=user_id, query=query
        )
        candidates = [(result.chunk, result.fused_score) for result in fused]
        reranked = await self._reranker.rerank(query, candidates, top_k=top_k)
        return [RerankedResult(chunk=chunk, score=score) for chunk, score in reranked]
