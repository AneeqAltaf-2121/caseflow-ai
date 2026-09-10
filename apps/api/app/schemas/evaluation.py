import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.evaluation import EvaluationRunStatus


class EvaluationRunCreate(BaseModel):
    dataset_name: str = Field(min_length=1, max_length=200)
    # Phase 31 model comparison: omit to use the globally configured
    # default model, or name a specific known model (see
    # app.integrations.generation.get_generation_provider_by_model) to
    # run this same dataset through a different one — create several
    # runs with different `model` values to compare them.
    model: str | None = Field(default=None, max_length=100)


class EvaluationRunRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    dataset_name: str
    dataset_version: int
    prompt_version_id: uuid.UUID | None
    model: str
    retriever_version: str
    status: EvaluationRunStatus
    error: str | None
    created_by: uuid.UUID
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class EvaluationResultRead(BaseModel):
    id: uuid.UUID
    example_id: str
    question: str
    generated_answer: str
    expected_answer: str | None
    faithfulness_score: float | None
    relevance_score: float | None
    completeness_score: float | None
    citation_support_score: float | None
    citation_correct: bool
    judge_reason: str | None
    recall_at_k: float | None
    precision_at_k: float | None
    mrr: float | None
    ndcg_at_k: float | None
    latency_ms: int
    cost_usd: float
    model_run_id: uuid.UUID | None
    grader_details: dict


class EvaluationRunDetailRead(EvaluationRunRead):
    results: list[EvaluationResultRead] = Field(default_factory=list)
