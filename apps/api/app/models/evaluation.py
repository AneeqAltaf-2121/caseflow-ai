import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.types import created_at_column, uuid_pk

if TYPE_CHECKING:
    from app.models.model_run import ModelRun
    from app.models.project import Project
    from app.models.prompt_version import PromptVersion


class EvaluationRunStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class EvaluationRun(Base):
    """A batch evaluation of a dataset against a given prompt/model/
    retriever combination (see docs/domain-model.md) — dataset + model +
    prompt version + retrieval config together identify one "experiment",
    letting two runs be compared later (Phase 31). Runs as a background
    job (app/jobs/evaluations.py), the same async pattern as ingestion and
    report generation: grading a whole dataset spends one retrieval, one
    generation, and up to four judge calls per example — too slow for a
    request/response cycle.
    """

    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # Not in domain-model.md's original sketch — added because Phase 25's
    # dataset format is versioned (immutable per version, like
    # PromptVersion), and dataset_name alone doesn't pin which version of
    # it actually produced these results.
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prompt_versions.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    retriever_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[EvaluationRunStatus] = mapped_column(
        SqlEnum(EvaluationRunStatus, native_enum=False, length=20),
        nullable=False,
        default=EvaluationRunStatus.QUEUED,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = created_at_column()
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship()
    prompt_version: Mapped["PromptVersion | None"] = relationship()
    results: Mapped[list["EvaluationResult"]] = relationship(
        back_populates="evaluation_run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<EvaluationRun id={self.id} dataset={self.dataset_name} status={self.status}>"


class EvaluationResult(Base):
    """A single graded example within an EvaluationRun (see
    docs/domain-model.md). Extends that sketch with the retrieval metrics
    (Phase 26) and citation-support score (Phase 28) the dashboard
    (Phase 30) needs to drill into, plus model_run_id — the domain
    model's own relationships note says "ModelRun is referenced by
    Message and EvaluationResult" even though the entity sketch omits the
    column.
    """

    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = uuid_pk()
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    example_id: Mapped[str] = mapped_column(String(100), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    generated_answer: Mapped[str] = mapped_column(Text, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    faithfulness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_support_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    judge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Populated only for examples whose dataset entry has relevant_chunk_ids
    # (Phase 25/26) — null, not 0.0, when there was no ground truth to
    # score retrieval against.
    recall_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    mrr: Mapped[float | None] = mapped_column(Float, nullable=True)
    ndcg_at_k: Mapped[float | None] = mapped_column(Float, nullable=True)

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    model_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("model_runs.id", ondelete="SET NULL"), nullable=True
    )
    # Full grader/deterministic-check detail (every grader's reason and
    # failures list, judge model/prompt version per grader) for the
    # dashboard's per-example drill-down (Phase 30) — more than the
    # scalar columns above can hold on their own.
    grader_details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = created_at_column()

    evaluation_run: Mapped["EvaluationRun"] = relationship(back_populates="results")
    model_run: Mapped["ModelRun | None"] = relationship()

    def __repr__(self) -> str:
        return f"<EvaluationResult id={self.id} run={self.evaluation_run_id}>"
