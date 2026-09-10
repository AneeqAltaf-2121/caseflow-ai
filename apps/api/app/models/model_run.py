import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.prompt_version import PromptVersion


class ModelRunStatus(enum.StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ModelRun(Base):
    """A record of a single LLM invocation (see docs/domain-model.md), for
    cost/latency/observability and evaluation. Only created for an
    invocation that actually happened — Phase 20's zero-evidence
    short-circuit (no chunks retrieved, so no generation call is made)
    doesn't produce a row.

    `retrieval_config` isn't in the original domain-model.md sketch —
    added because the Phase 23 spec explicitly asks to record retrieval
    configuration (top_k, retriever/reranker version, embedding model)
    alongside each run, and JSON keeps that flexible as retrieval evolves
    without a schema migration per new knob.
    """

    __tablename__ = "model_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL"), nullable=True
    )
    temperature: Mapped[float] = mapped_column(Float, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[ModelRunStatus] = mapped_column(
        SqlEnum(ModelRunStatus, native_enum=False, length=20), nullable=False
    )
    retrieval_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = created_at_column()

    prompt_version: Mapped["PromptVersion | None"] = relationship()

    def __repr__(self) -> str:
        return f"<ModelRun id={self.id} model={self.model!r} status={self.status}>"
