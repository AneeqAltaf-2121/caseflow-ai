import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.citation import Citation
from app.models.conversation import Conversation, Message, MessageRole


class ConversationRepository:
    """Data access for Conversation, Message, and Citation. No
    authorization here — see app/services/conversation_service.py."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, project_id: uuid.UUID, title: str, created_by: uuid.UUID
    ) -> Conversation:
        conversation = Conversation(project_id=project_id, title=title, created_by=created_by)
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get_by_id(self, conversation_id: uuid.UUID) -> Conversation | None:
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(
                selectinload(Conversation.messages)
                .selectinload(Message.citations)
                .selectinload(Citation.document)
            )
        )
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: uuid.UUID) -> list[Conversation]:
        result = await self._session.execute(
            select(Conversation)
            .where(Conversation.project_id == project_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(result.scalars().all())

    async def update_title(self, conversation: Conversation, title: str) -> Conversation:
        conversation.title = title
        await self._session.flush()
        # `updated_at` is set by an onupdate=func.now() DB-side default, so
        # after an UPDATE (unlike an INSERT) SQLAlchemy doesn't know its new
        # value and marks it expired — refresh it now rather than leaving a
        # lazy-load for whoever reads it next (e.g. schema serialization),
        # which isn't safe outside an awaited call (see
        # ProjectRepository.update for the same fix).
        await self._session.refresh(conversation, attribute_names=["updated_at"])
        return conversation

    async def delete(self, conversation: Conversation) -> None:
        await self._session.delete(conversation)
        await self._session.flush()

    async def touch(self, conversation: Conversation) -> None:
        """Bump `updated_at` when a message is added — adding a child row
        doesn't fire the parent's onupdate trigger on its own."""
        conversation.updated_at = datetime.now(UTC)
        await self._session.flush()

    async def add_message(
        self,
        *,
        conversation_id: uuid.UUID,
        role: MessageRole,
        content: str,
        citations: list[Citation] | None = None,
    ) -> Message:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        self._session.add(message)
        # Appending via the relationship (rather than setting citation.
        # message_id directly) sets the FK *and* populates message.
        # citations in memory — needed so an object already in this
        # session's identity map (e.g. the conversation this message
        # belongs to, loaded earlier in the same request) reflects the
        # new citations without a lazy load, which isn't safe on an
        # AsyncSession outside of an explicit await.
        for citation in citations or []:
            message.citations.append(citation)
        await self._session.flush()
        return message
