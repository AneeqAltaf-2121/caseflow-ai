"""Citation-grounded question answering (Phase 19), nested under a
project. Stateless — see app/rag/service.py; persistent conversations
wrapping this land in Phase 21."""

import uuid

from fastapi import APIRouter

from app.dependencies import (
    CurrentUserIdDep,
    DbSessionDep,
    EmbeddingProviderDep,
    GenerationProviderDep,
    RerankerDep,
)
from app.rag.service import RagService
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.rag import AskAnswerRead, AskQuestion, CitationRead
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService
from app.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/projects/{project_id}/ask", tags=["rag"])


@router.post("", response_model=AskAnswerRead)
async def ask_question(
    project_id: uuid.UUID,
    payload: AskQuestion,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> AskAnswerRead:
    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db), ProjectService(ProjectRepository(db)), embedding_provider
    )
    retrieval_service = RetrievalService(hybrid_service, reranker)
    rag_service = RagService(retrieval_service, generation_provider)

    answer = await rag_service.answer_question(
        project_id=project_id, user_id=current_user_id, query=payload.question, top_k=payload.top_k
    )
    return AskAnswerRead(
        answer=answer.answer,
        citations=[
            CitationRead(
                source_number=c.source_number,
                document_id=c.document_id,
                document_chunk_id=c.document_chunk_id,
                document_filename=c.document_filename,
                page_number=c.page_number,
                quote=c.quote,
            )
            for c in answer.citations
        ],
        sources_considered=answer.sources_considered,
        model=answer.model,
        insufficient_evidence=answer.insufficient_evidence,
    )
