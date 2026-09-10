import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.conversation import Message
    from app.models.project import Project
    from app.models.user import User


class HumanReviewStatus(enum.StrEnum):
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class HumanReview(Base):
    """A human review of a generated answer (see README's "review
    low-confidence AI outputs"). Not in docs/domain-model.md's original
    sketch — designed for Phase 37, scoped to reviewing Message rows
    (the RAG chat answers a project's members actually see and act on)
    rather than every generated-content type at once.

    `original_answer` is a snapshot of the message's content at flag
    time, not a live join — Message content never changes in this app
    today, but a review record should stay self-contained and
    meaningful even if that ever changed, or if the message were later
    deleted alongside its conversation.
    """

    __tablename__ = "human_reviews"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[HumanReviewStatus] = mapped_column(
        SqlEnum(HumanReviewStatus, native_enum=False, length=20),
        nullable=False,
        default=HumanReviewStatus.NEEDS_REVIEW,
    )
    flagged_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_answer: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = created_at_column()

    project: Mapped["Project"] = relationship()
    message: Mapped["Message"] = relationship()
    reviewer: Mapped["User | None"] = relationship(foreign_keys=[reviewer_id])

    def __repr__(self) -> str:
        return f"<HumanReview id={self.id} status={self.status} message={self.message_id}>"
