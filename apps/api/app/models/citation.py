import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.chunk import DocumentChunk
    from app.models.conversation import Message
    from app.models.document import Document


class Citation(Base):
    """A link from an assistant Message to the DocumentChunk that grounds
    part of its answer (see app/rag/service.py, which produces these
    before they're persisted here by ConversationService).

    `source_number` isn't in the original docs/domain-model.md sketch of
    this entity — added because it's exactly the [n] marker the answer
    text cites (see app/rag/citations.py), and losing it would make a
    persisted answer's citation markers unable to be matched back to a
    specific source when the conversation is redisplayed later.
    """

    __tablename__ = "citations"

    id: Mapped[uuid.UUID] = uuid_pk()
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    document_chunk_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"), nullable=False
    )
    source_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    message: Mapped["Message"] = relationship(back_populates="citations")
    document: Mapped["Document"] = relationship()
    document_chunk: Mapped["DocumentChunk"] = relationship()

    def __repr__(self) -> str:
        return f"<Citation id={self.id} message={self.message_id} source={self.source_number}>"
