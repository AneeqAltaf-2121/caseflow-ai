import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_run import ModelRun, ModelRunStatus


@dataclass(frozen=True)
class CostAggregateRow:
    """One (day, model, user) bucket's totals — Phase 32 cost tracking.
    The caller (CostService) further rolls these up by whichever
    dimension it needs (model, user, day) since this is already the
    finest grain worth returning."""

    day: str
    model: str
    user_id: uuid.UUID
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    run_count: int


class ModelRunRepository:
    """Data access for ModelRun. No authorization here — a ModelRun isn't
    directly project-scoped (see docs/domain-model.md: it's a
    cross-cutting observability record referenced by Message and
    EvaluationResult), so callers scope access through whatever owns the
    reference to it."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        provider: str,
        model: str,
        prompt_version_id: uuid.UUID | None,
        temperature: float,
        latency_ms: int,
        input_tokens: int,
        output_tokens: int,
        estimated_cost_usd: float,
        status: ModelRunStatus,
        retrieval_config: dict,
    ) -> ModelRun:
        model_run = ModelRun(
            project_id=project_id,
            user_id=user_id,
            provider=provider,
            model=model,
            prompt_version_id=prompt_version_id,
            temperature=temperature,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            status=status,
            retrieval_config=retrieval_config,
        )
        self._session.add(model_run)
        await self._session.flush()
        return model_run

    async def get_by_id(self, model_run_id: uuid.UUID) -> ModelRun | None:
        return await self._session.get(ModelRun, model_run_id)

    async def aggregate_costs_for_project(self, project_id: uuid.UUID) -> list[CostAggregateRow]:
        """Every (day, model, user) bucket of spend for a project, most
        recent day first. `func.date()` truncates a timestamp to a plain
        date on both SQLite and PostgreSQL, so this needs no dialect
        branch (unlike DocumentChunkRepository.search_by_embedding)."""
        day = func.date(ModelRun.created_at)
        result = await self._session.execute(
            select(
                day.label("day"),
                ModelRun.model,
                ModelRun.user_id,
                func.sum(ModelRun.estimated_cost_usd).label("total_cost_usd"),
                func.sum(ModelRun.input_tokens).label("total_input_tokens"),
                func.sum(ModelRun.output_tokens).label("total_output_tokens"),
                func.count(ModelRun.id).label("run_count"),
            )
            .where(ModelRun.project_id == project_id)
            .group_by(day, ModelRun.model, ModelRun.user_id)
            .order_by(day.desc())
        )
        return [
            CostAggregateRow(
                day=str(row.day),
                model=row.model,
                user_id=row.user_id,
                total_cost_usd=row.total_cost_usd or 0.0,
                total_input_tokens=row.total_input_tokens or 0,
                total_output_tokens=row.total_output_tokens or 0,
                run_count=row.run_count,
            )
            for row in result.all()
        ]
