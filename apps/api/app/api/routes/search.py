"""Semantic search route, nested under a project (Phase 14)."""

import uuid

from fastapi import APIRouter

from app.dependencies import CurrentUserIdDep, DbSessionDep, EmbeddingProviderDep
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.search import SearchQuery, SearchResultRead
from app.services.project_service import ProjectService
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
