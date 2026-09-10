"""Persistent conversations (Phase 21): wraps RagService (Phase 19/20)
with storage — every question/answer becomes USER/ASSISTANT Message rows,
citations become Citation rows, and each new question is asked with a
bounded slice of the conversation's own history (app/rag/history.py) as
context.
"""

import uuid
from dataclasses import dataclass

from app.errors import NotFoundError
from app.models.citation import Citation
from app.models.conversation import Conversation, Message, MessageRole
from app.models.project import ProjectRole
from app.rag.history import build_history_text
from app.rag.service import DEFAULT_TOP_K, RagService
from app.rag.service import Citation as RagCitation
from app.repositories.conversation_repository import ConversationRepository
from app.services.project_service import ProjectService

DEFAULT_TITLE = "Untitled"


@dataclass(frozen=True)
class CitationView:
    """Display-ready citation: a persisted Citation row's fields plus the
    document filename, which the row itself doesn't store (see
    app/models/citation.py) — sourced from app.rag.service.Citation for a
    just-posted message (no query needed) or from the eager-loaded
    `Citation.document` relationship when reading an existing
    conversation back (see ConversationRepository.get_by_id)."""

    id: uuid.UUID
    source_number: int
    document_id: uuid.UUID
    document_chunk_id: uuid.UUID
    document_filename: str
    page_number: int
    quote: str


@dataclass(frozen=True)
class PostMessageResult:
    user_message: Message
    assistant_message: Message
    citations: list[CitationView]
    insufficient_evidence: bool
    sources_considered: int
    model: str


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository,
        project_service: ProjectService,
        rag_service: RagService,
    ) -> None:
        self._repository = repository
        self._project_service = project_service
        self._rag_service = rag_service

    async def create_conversation(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID, title: str = DEFAULT_TITLE
    ) -> Conversation:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.create(project_id=project_id, title=title, created_by=user_id)

    async def list_conversations(
        self, *, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Conversation]:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        return await self._repository.list_for_project(project_id)

    async def get_conversation(
        self, *, conversation_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> Conversation:
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        conversation = await self._repository.get_by_id(conversation_id)
        if conversation is None or conversation.project_id != project_id:
            raise NotFoundError(f"Conversation {conversation_id} not found.")
        return conversation

    async def _require_manage_permission(
        self, conversation: Conversation, *, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        """Renaming/deleting is allowed for the conversation's own creator
        (even a viewer can manage their own conversation) or any
        owner/editor of the project."""
        if conversation.created_by == user_id:
            return
        await self._project_service.require_role(
            project_id=project_id,
            user_id=user_id,
            allowed={ProjectRole.OWNER, ProjectRole.EDITOR},
        )

    async def rename_conversation(
        self, *, conversation_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID, title: str
    ) -> Conversation:
        conversation = await self.get_conversation(
            conversation_id=conversation_id, project_id=project_id, user_id=user_id
        )
        await self._require_manage_permission(conversation, project_id=project_id, user_id=user_id)
        return await self._repository.update_title(conversation, title)

    async def delete_conversation(
        self, *, conversation_id: uuid.UUID, project_id: uuid.UUID, user_id: uuid.UUID
    ) -> None:
        conversation = await self.get_conversation(
            conversation_id=conversation_id, project_id=project_id, user_id=user_id
        )
        await self._require_manage_permission(conversation, project_id=project_id, user_id=user_id)
        await self._repository.delete(conversation)

    async def post_message(
        self,
        *,
        conversation_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
        top_k: int = DEFAULT_TOP_K,
    ) -> PostMessageResult:
        conversation = await self.get_conversation(
            conversation_id=conversation_id, project_id=project_id, user_id=user_id
        )
        history_text = build_history_text(conversation.messages)

        answer = await self._rag_service.answer_question(
            project_id=project_id,
            user_id=user_id,
            query=content,
            top_k=top_k,
            history=history_text,
        )

        user_message = await self._repository.add_message(
            conversation_id=conversation_id, role=MessageRole.USER, content=content
        )

        citation_rows = [_to_citation_row(c) for c in answer.citations]
        assistant_message = await self._repository.add_message(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer.answer,
            citations=citation_rows,
        )
        await self._repository.touch(conversation)

        # citation_rows and answer.citations are the same length, built in
        # the same order from the same source list — zip is safe, and
        # avoids touching the (unloaded) `Citation.document` relationship.
        citation_views = [
            CitationView(
                id=row.id,
                source_number=row.source_number,
                document_id=row.document_id,
                document_chunk_id=row.document_chunk_id,
                document_filename=rag_citation.document_filename,
                page_number=row.page_number,
                quote=row.quote,
            )
            for row, rag_citation in zip(citation_rows, answer.citations, strict=True)
        ]

        return PostMessageResult(
            user_message=user_message,
            assistant_message=assistant_message,
            citations=citation_views,
            insufficient_evidence=answer.insufficient_evidence,
            sources_considered=answer.sources_considered,
            model=answer.model,
        )


def _to_citation_row(citation: RagCitation) -> Citation:
    return Citation(
        document_id=citation.document_id,
        document_chunk_id=citation.document_chunk_id,
        source_number=citation.source_number,
        page_number=citation.page_number,
        quote=citation.quote,
    )


def citation_row_to_view(citation: Citation) -> CitationView:
    """For reading an existing conversation back — requires
    `Citation.document` to be eager-loaded (see
    ConversationRepository.get_by_id's selectinload chain)."""
    return CitationView(
        id=citation.id,
        source_number=citation.source_number,
        document_id=citation.document_id,
        document_chunk_id=citation.document_chunk_id,
        document_filename=citation.document.filename,
        page_number=citation.page_number,
        quote=citation.quote,
    )
