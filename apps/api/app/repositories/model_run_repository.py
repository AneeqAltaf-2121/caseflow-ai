import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_run import ModelRun, ModelRunStatus


class ModelRunRepository:
    """Data access for ModelRun. No authorization here — a ModelRun isn't
    directly project-scoped (see docs/domain-model.md: it's a
    cross-cutting observability record referenced by Message and, later,
    EvaluationResult), so callers scope access through whatever owns the
    reference to it."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
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
