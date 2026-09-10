import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.project import Project


class PromptVersion(Base):
    """An immutable, named/versioned prompt template (see
    docs/domain-model.md). A change is a new row, never an edit to an
    existing one — that's what makes prompt/model comparisons across
    versions meaningful (Phase 26+).
    """

    __tablename__ = "prompt_versions"
    __table_args__ = (UniqueConstraint("project_id", "name", "version", name="uq_prompt_version"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    # At most one (project_id, name) row is active at a time — enforced in
    # PromptVersionRepository.activate(), not at the DB level (a partial
    # unique index would need Postgres-specific DDL; SQLite still needs to
    # run this same migration for fast tests, per the established pattern
    # — see migration 0003's comment).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()

    project: Mapped["Project"] = relationship()

    def __repr__(self) -> str:
        return f"<PromptVersion {self.name}_v{self.version} active={self.is_active}>"
