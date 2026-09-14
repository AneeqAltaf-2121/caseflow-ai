"""Hybrid retrieval (Phase 16): vector + keyword candidates, combined by
reciprocal rank fusion. Neither retriever is replaced — semantic search
(Phase 14) and keyword search (Phase 15) stay available on their own.

Phase 33 caching: both the query embedding and the full fused result are
cached (when a `cache` is given — optional and defaulting to None so
every existing caller/test that doesn't care about caching is
unaffected). Cache keys include the embedding provider's identity and
dimensions plus the retrieval candidate/result limits, so a config
change (switching embedding providers, say) simply never hits a stale
key rather than needing explicit invalidation.
"""

import json
import uuid

from app.cache import Cache, cache_key, hash_text
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
        cache: Cache | None = None,
    ) -> None:
        self._chunk_repository = chunk_repository
        self._project_service = project_service
        self._embedding_provider = embedding_provider
        self._cache = cache

    @property
    def embedding_provider(self) -> EmbeddingProvider:
        """Exposed so callers (RetrievalService.describe_config, for
        ModelRun.retrieval_config — Phase 23) can identify which embedding
        model produced a given answer's context, without reaching into a
        private attribute."""
        return self._embedding_provider

    def _embedding_provider_identity(self) -> str:
        return f"{type(self._embedding_provider).__name__}:{self._embedding_provider.dimensions}"

    async def _embed_query(self, query: str) -> list[float]:
        if self._cache is None:
            [embedding] = await self._embedding_provider.embed([query])
            return embedding

        key = cache_key("embedding", "v1", self._embedding_provider_identity(), hash_text(query))
        cached = await self._cache.get(key)
        if cached is not None:
            result: list[float] = json.loads(cached)
            return result

        [embedding] = await self._embedding_provider.embed([query])
        await self._cache.set(key, json.dumps(embedding))
        return embedding

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

        cache_key_str = None
        if self._cache is not None:
            cache_key_str = cache_key(
                "hybrid_search",
                "v1",
                str(project_id),
                self._embedding_provider_identity(),
                hash_text(query),
                str(candidate_limit),
                str(limit),
            )
            cached = await self._cache.get(cache_key_str)
            if cached is not None:
                hit = await self._rehydrate(json.loads(cached))
                if hit is not None:
                    return hit

        query_embedding = await self._embed_query(query)
        vector_results = await self._chunk_repository.search_by_embedding(
            project_id=project_id, query_embedding=query_embedding, limit=candidate_limit
        )

        all_chunks = await self._chunk_repository.list_for_project(project_id)
        keyword_results = bm25_search(all_chunks, query, limit=candidate_limit)

        fused = reciprocal_rank_fusion(vector_results, keyword_results, limit=limit)

        if self._cache is not None and cache_key_str is not None:
            await self._cache.set(cache_key_str, json.dumps([_serialize(r) for r in fused]))

        return fused

    async def _rehydrate(self, serialized: list[dict]) -> list[FusedResult] | None:
        """Re-fetches every cached chunk id from the DB in one query (a
        cache should never hand a caller a detached/stale ORM object) and
        rebuilds FusedResult in the cached order. Returns None — a cache
        miss in all but name — if any cached chunk no longer exists,
        since a partial result set would silently under-represent the
        project.

        One batched query rather than one per cached chunk (fixed in
        Phase 57 after scripts/benchmark.py measured the N+1 version as
        *slower* than recomputing the search from scratch — a cache
        whose hit path costs more than its miss path defeats the point)."""
        chunk_ids = [uuid.UUID(entry["chunk_id"]) for entry in serialized]
        chunks_by_id = await self._chunk_repository.get_many_by_ids_with_document(chunk_ids)

        results: list[FusedResult] = []
        for entry in serialized:
            chunk = chunks_by_id.get(uuid.UUID(entry["chunk_id"]))
            if chunk is None:
                return None
            results.append(
                FusedResult(
                    chunk=chunk,
                    fused_score=entry["fused_score"],
                    vector_rank=entry["vector_rank"],
                    vector_score=entry["vector_score"],
                    keyword_rank=entry["keyword_rank"],
                    keyword_score=entry["keyword_score"],
                )
            )
        return results


def _serialize(result: FusedResult) -> dict:
    return {
        "chunk_id": str(result.chunk.id),
        "fused_score": result.fused_score,
        "vector_rank": result.vector_rank,
        "vector_score": result.vector_score,
        "keyword_rank": result.keyword_rank,
        "keyword_score": result.keyword_score,
    }
