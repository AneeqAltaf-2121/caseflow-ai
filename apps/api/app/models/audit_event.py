import uuid
from datetime import datetime

from sqlalchemy import JSON, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.types import created_at_column, uuid_pk


class AuditEvent(Base):
    """An immutable record of a security- or review-relevant action.

    Rows are append-only: services write them, nothing ever updates or
    deletes one. `target_type`/`target_id` point at an arbitrary entity
    (document, evaluation, conversation, ...).
    """

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    event_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = created_at_column()

    def __repr__(self) -> str:
        target = f"{self.target_type}:{self.target_id}"
        return f"<AuditEvent id={self.id} action={self.action!r} target={target}>"
