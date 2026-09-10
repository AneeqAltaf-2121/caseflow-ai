import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.evaluation import EvaluationResult, EvaluationRun, EvaluationRunStatus


class EvaluationRunRepository:
    """Data access for EvaluationRun/EvaluationResult. No authorization
    here — see app/services/evaluation_service.py."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        project_id: uuid.UUID,
        dataset_name: str,
        dataset_version: int,
        prompt_version_id: uuid.UUID | None,
        model: str,
        retriever_version: str,
        created_by: uuid.UUID,
    ) -> EvaluationRun:
        run = EvaluationRun(
            project_id=project_id,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            prompt_version_id=prompt_version_id,
            model=model,
            retriever_version=retriever_version,
            created_by=created_by,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_by_id(self, evaluation_run_id: uuid.UUID) -> EvaluationRun | None:
        result = await self._session.execute(
            select(EvaluationRun)
            .where(EvaluationRun.id == evaluation_run_id)
            .options(
                selectinload(EvaluationRun.results), selectinload(EvaluationRun.prompt_version)
            )
        )
        return result.scalar_one_or_none()

    async def list_for_project(self, project_id: uuid.UUID) -> list[EvaluationRun]:
        result = await self._session.execute(
            select(EvaluationRun)
            .where(EvaluationRun.project_id == project_id)
            .order_by(EvaluationRun.created_at.desc())
        )
        return list(result.scalars().all())

    async def mark_running(self, run: EvaluationRun) -> EvaluationRun:
        run.status = EvaluationRunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await self._session.flush()
        return run

    async def mark_succeeded(self, run: EvaluationRun) -> EvaluationRun:
        run.status = EvaluationRunStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.error = None
        await self._session.flush()
        return run

    async def mark_failed(self, run: EvaluationRun, error: str) -> EvaluationRun:
        run.status = EvaluationRunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error = error
        await self._session.flush()
        return run

    async def add_result(
        self,
        *,
        evaluation_run_id: uuid.UUID,
        example_id: str,
        question: str,
        generated_answer: str,
        expected_answer: str | None,
        faithfulness_score: float | None,
        relevance_score: float | None,
        completeness_score: float | None,
        citation_support_score: float | None,
        citation_correct: bool,
        judge_reason: str | None,
        recall_at_k: float | None,
        precision_at_k: float | None,
        mrr: float | None,
        ndcg_at_k: float | None,
        latency_ms: int,
        cost_usd: float,
        model_run_id: uuid.UUID | None,
        grader_details: dict,
    ) -> EvaluationResult:
        result = EvaluationResult(
            evaluation_run_id=evaluation_run_id,
            example_id=example_id,
            question=question,
            generated_answer=generated_answer,
            expected_answer=expected_answer,
            faithfulness_score=faithfulness_score,
            relevance_score=relevance_score,
            completeness_score=completeness_score,
            citation_support_score=citation_support_score,
            citation_correct=citation_correct,
            judge_reason=judge_reason,
            recall_at_k=recall_at_k,
            precision_at_k=precision_at_k,
            mrr=mrr,
            ndcg_at_k=ndcg_at_k,
            latency_ms=latency_ms,
            cost_usd=cost_usd,
            model_run_id=model_run_id,
            grader_details=grader_details,
        )
        self._session.add(result)
        await self._session.flush()
        return result

    async def clear_results(self, run: EvaluationRun) -> None:
        """Idempotency under job retry — same pattern as
        ReportRepository/report.sections.clear() in app/jobs/reports.py: a
        partially-failed previous attempt's rows are dropped before the
        fresh set is written."""
        for result in list(run.results):
            await self._session.delete(result)
        await self._session.flush()
