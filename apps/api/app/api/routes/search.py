"""Semantic (Phase 14) and keyword (Phase 15) search routes, nested under
a project. Hybrid fusion (Phase 16) combines both, and reranking
(Phase 17) narrows hybrid's output further — none of the four modes
replace each other."""

import uuid

from fastapi import APIRouter

from app.cache import get_cache
from app.dependencies import (
    CurrentUserIdDep,
    DbSessionDep,
    EmbeddingProviderDep,
    RerankerDep,
)
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.search import HybridSearchResultRead, SearchQuery, SearchResultRead
from app.services.hybrid_search_service import HybridSearchService
from app.services.keyword_search_service import KeywordSearchService
from app.services.project_service import ProjectService
from app.services.retrieval_service import RetrievalService
from app.services.search_service import SearchService

router = APIRouter(prefix="/projects/{project_id}/search", tags=["search"])


@router.post("", response_model=list[SearchResultRead])
async def semantic_search(
    project_id: uuid.UUID,
    payload: SearchQuery,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
) -> list[SearchResultRead]:
    service = SearchService(
        DocumentChunkRepository(db), ProjectService(ProjectRepository(db)), embedding_provider
    )
    results = await service.semantic_search(
        project_id=project_id, user_id=current_user_id, query=payload.query, limit=payload.limit
    )
    return [
        SearchResultRead(
            chunk_id=result.chunk.id,
            document_id=result.chunk.document_id,
            document_filename=result.chunk.document.filename,
            page_number=result.chunk.page_number,
            text=result.chunk.text,
            score=result.score,
        )
        for result in results
    ]


@router.post("/hybrid", response_model=list[HybridSearchResultRead])
async def hybrid_search(
    project_id: uuid.UUID,
    payload: SearchQuery,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
) -> list[HybridSearchResultRead]:
    service = HybridSearchService(
        DocumentChunkRepository(db),
        ProjectService(ProjectRepository(db)),
        embedding_provider,
        get_cache(),
    )
    results = await service.hybrid_search(
        project_id=project_id, user_id=current_user_id, query=payload.query, limit=payload.limit
    )
    return [
        HybridSearchResultRead(
            chunk_id=result.chunk.id,
            document_id=result.chunk.document_id,
            document_filename=result.chunk.document.filename,
            page_number=result.chunk.page_number,
            text=result.chunk.text,
            fused_score=result.fused_score,
            vector_rank=result.vector_rank,
            vector_score=result.vector_score,
            keyword_rank=result.keyword_rank,
            keyword_score=result.keyword_score,
        )
        for result in results
    ]


@router.post("/rerank", response_model=list[SearchResultRead])
async def reranked_search(
    project_id: uuid.UUID,
    payload: SearchQuery,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
) -> list[SearchResultRead]:
    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db),
        ProjectService(ProjectRepository(db)),
        embedding_provider,
        get_cache(),
    )
    service = RetrievalService(hybrid_service, reranker)
    results = await service.retrieve(
        project_id=project_id, user_id=current_user_id, query=payload.query, top_k=payload.limit
    )
    return [
        SearchResultRead(
            chunk_id=result.chunk.id,
            document_id=result.chunk.document_id,
            document_filename=result.chunk.document.filename,
            page_number=result.chunk.page_number,
            text=result.chunk.text,
            score=result.score,
        )
        for result in results
    ]


@router.post("/keyword", response_model=list[SearchResultRead])
async def keyword_search(
    project_id: uuid.UUID,
    payload: SearchQuery,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
) -> list[SearchResultRead]:
    service = KeywordSearchService(
        DocumentChunkRepository(db), ProjectService(ProjectRepository(db))
    )
    results = await service.keyword_search(
        project_id=project_id, user_id=current_user_id, query=payload.query, limit=payload.limit
    )
    return [
        SearchResultRead(
            chunk_id=result.chunk.id,
            document_id=result.chunk.document_id,
            document_filename=result.chunk.document.filename,
            page_number=result.chunk.page_number,
            text=result.chunk.text,
            score=result.score,
        )
        for result in results
    ]
