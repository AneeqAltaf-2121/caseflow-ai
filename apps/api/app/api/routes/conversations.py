"""Persistent conversations (Phase 21), nested under a project."""

import uuid

from fastapi import APIRouter

from app.dependencies import (
    CurrentUserIdDep,
    DbSessionDep,
    EmbeddingProviderDep,
    GenerationProviderDep,
    RerankerDep,
)
from app.models.conversation import Conversation, Message
from app.rag.service import RagService
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.conversation import (
    CitationRead,
    ConversationCreate,
    ConversationDetailRead,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
    PostMessageRequest,
    PostMessageResponse,
)
from app.services.conversation_service import (
    CitationView,
    ConversationService,
    citation_row_to_view,
)
from app.services.hybrid_search_service import HybridSearchService
from app.services.project_service import ProjectService
from app.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/projects/{project_id}/conversations", tags=["conversations"])


def _service(
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> ConversationService:
    hybrid_service = HybridSearchService(
        DocumentChunkRepository(db), ProjectService(ProjectRepository(db)), embedding_provider
    )
    retrieval_service = RetrievalService(hybrid_service, reranker)
    rag_service = RagService(retrieval_service, generation_provider)
    return ConversationService(
        ConversationRepository(db), ProjectService(ProjectRepository(db)), rag_service
    )


def _conversation_read(conversation: Conversation) -> ConversationRead:
    return ConversationRead(
        id=conversation.id,
        project_id=conversation.project_id,
        title=conversation.title,
        created_by=conversation.created_by,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _citation_read(view: CitationView) -> CitationRead:
    return CitationRead(
        id=view.id,
        source_number=view.source_number,
        document_id=view.document_id,
        document_chunk_id=view.document_chunk_id,
        document_filename=view.document_filename,
        page_number=view.page_number,
        quote=view.quote,
    )


def _message_read(message: Message) -> MessageRead:
    return MessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        citations=[_citation_read(citation_row_to_view(c)) for c in message.citations],
    )


@router.post("", response_model=ConversationRead, status_code=201)
async def create_conversation(
    project_id: uuid.UUID,
    payload: ConversationCreate,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> ConversationRead:
    service = _service(db, embedding_provider, reranker, generation_provider)
    conversation = await service.create_conversation(
        project_id=project_id, user_id=current_user_id, title=payload.title
    )
    return _conversation_read(conversation)


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    project_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> list[ConversationRead]:
    service = _service(db, embedding_provider, reranker, generation_provider)
    conversations = await service.list_conversations(project_id=project_id, user_id=current_user_id)
    return [_conversation_read(c) for c in conversations]


@router.get("/{conversation_id}", response_model=ConversationDetailRead)
async def get_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> ConversationDetailRead:
    service = _service(db, embedding_provider, reranker, generation_provider)
    conversation = await service.get_conversation(
        conversation_id=conversation_id, project_id=project_id, user_id=current_user_id
    )
    return ConversationDetailRead(
        **_conversation_read(conversation).model_dump(),
        messages=[_message_read(m) for m in conversation.messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationRead)
async def rename_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> ConversationRead:
    service = _service(db, embedding_provider, reranker, generation_provider)
    conversation = await service.rename_conversation(
        conversation_id=conversation_id,
        project_id=project_id,
        user_id=current_user_id,
        title=payload.title,
    )
    return _conversation_read(conversation)


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> None:
    service = _service(db, embedding_provider, reranker, generation_provider)
    await service.delete_conversation(
        conversation_id=conversation_id, project_id=project_id, user_id=current_user_id
    )


@router.post("/{conversation_id}/messages", response_model=PostMessageResponse, status_code=201)
async def post_message(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: PostMessageRequest,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    embedding_provider: EmbeddingProviderDep,
    reranker: RerankerDep,
    generation_provider: GenerationProviderDep,
) -> PostMessageResponse:
    service = _service(db, embedding_provider, reranker, generation_provider)
    result = await service.post_message(
        conversation_id=conversation_id,
        project_id=project_id,
        user_id=current_user_id,
        content=payload.content,
        top_k=payload.top_k,
    )
    return PostMessageResponse(
        user_message=MessageRead(
            id=result.user_message.id,
            role=result.user_message.role,
            content=result.user_message.content,
            created_at=result.user_message.created_at,
            citations=[],
        ),
        assistant_message=MessageRead(
            id=result.assistant_message.id,
            role=result.assistant_message.role,
            content=result.assistant_message.content,
            created_at=result.assistant_message.created_at,
            citations=[_citation_read(c) for c in result.citations],
        ),
        insufficient_evidence=result.insufficient_evidence,
        sources_considered=result.sources_considered,
        model=result.model,
    )
