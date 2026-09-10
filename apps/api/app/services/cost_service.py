"""Cost tracking (Phase 32): aggregates real LLM spend recorded on
ModelRun (Phase 23's per-invocation records, now Phase 32's
project_id/user_id columns) by day, model, and user for a project.
Covers both chat (ConversationService) and evaluation-run (Phase 29)
generation calls — every ModelRun-creating call site feeds the same
aggregate, regardless of which feature spent the money.
"""

import uuid
from dataclasses import dataclass, field

from app.repositories.model_run_repository import CostAggregateRow, ModelRunRepository
from app.services.project_service import ProjectService


@dataclass(frozen=True)
class CostSummary:
    project_id: uuid.UUID
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    total_runs: int
    by_day: list[CostAggregateRow] = field(default_factory=list)
    by_model: dict[str, float] = field(default_factory=dict)
    by_user: dict[str, float] = field(default_factory=dict)


def _summarize(project_id: uuid.UUID, rows: list[CostAggregateRow]) -> CostSummary:
    by_model: dict[str, float] = {}
    by_user: dict[str, float] = {}
    for row in rows:
        by_model[row.model] = by_model.get(row.model, 0.0) + row.total_cost_usd
        user_key = str(row.user_id)
        by_user[user_key] = by_user.get(user_key, 0.0) + row.total_cost_usd

    return CostSummary(
        project_id=project_id,
        total_cost_usd=sum(row.total_cost_usd for row in rows),
        total_input_tokens=sum(row.total_input_tokens for row in rows),
        total_output_tokens=sum(row.total_output_tokens for row in rows),
        total_runs=sum(row.run_count for row in rows),
        by_day=rows,
        by_model=by_model,
        by_user=by_user,
    )


class CostService:
    def __init__(self, repository: ModelRunRepository, project_service: ProjectService) -> None:
        self._repository = repository
        self._project_service = project_service

    async def get_cost_summary(self, *, project_id: uuid.UUID, user_id: uuid.UUID) -> CostSummary:
        # Viewing spend is a read — any project member, not just
        # owner/editor, per the same membership check other read
        # endpoints (list_reports, list_runs) use.
        await self._project_service.get_project_for_user(project_id=project_id, user_id=user_id)
        rows = await self._repository.aggregate_costs_for_project(project_id)
        return _summarize(project_id, rows)
