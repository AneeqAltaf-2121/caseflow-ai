"""Evaluation runs (Phase 29), nested under a project. Grading runs as a
background job (see app/jobs/evaluations.py) — creating a run returns
immediately with status=QUEUED; poll GET .../{evaluation_run_id} for
progress and per-example results."""

import uuid

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import CurrentUserIdDep, DbSessionDep, GenerationProviderDep, SettingsDep
from app.jobs.evaluations import run_evaluation_job
from app.models.evaluation import EvaluationResult, EvaluationRun
from app.repositories.evaluation_repository import EvaluationRunRepository
from app.repositories.job_repository import JobRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.prompt_version_repository import PromptVersionRepository
from app.schemas.evaluation import (
    EvaluationResultRead,
    EvaluationRunCreate,
    EvaluationRunDetailRead,
    EvaluationRunRead,
)
from app.services.evaluation_service import EvaluationRunService
from app.services.project_service import ProjectService
from app.services.prompt_version_service import PromptVersionService

router = APIRouter(prefix="/projects/{project_id}/evaluations", tags=["evaluations"])


def _service(
    db: DbSessionDep, generation_provider: GenerationProviderDep, settings: SettingsDep
) -> EvaluationRunService:
    return EvaluationRunService(
        EvaluationRunRepository(db),
        ProjectService(ProjectRepository(db)),
        PromptVersionService(PromptVersionRepository(db), ProjectService(ProjectRepository(db))),
        generation_provider,
        settings,
    )


async def _enqueue_evaluation_run(db: AsyncSession, evaluation_run_id: uuid.UUID) -> None:
    """Same commit-before-send reasoning as documents.py's
    _enqueue_ingestion — a worker must never be able to pick up a message
    before the row it references is actually visible to it."""
    job = await JobRepository(db).create(
        type="evaluation_run", payload={"evaluation_run_id": str(evaluation_run_id)}
    )
    await db.commit()
    run_evaluation_job.send(str(job.id), str(evaluation_run_id))


def _run_read(run: EvaluationRun) -> EvaluationRunRead:
    return EvaluationRunRead(
        id=run.id,
        project_id=run.project_id,
        dataset_name=run.dataset_name,
        dataset_version=run.dataset_version,
        prompt_version_id=run.prompt_version_id,
        model=run.model,
        retriever_version=run.retriever_version,
        status=run.status,
        error=run.error,
        created_by=run.created_by,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _result_read(result: EvaluationResult) -> EvaluationResultRead:
    return EvaluationResultRead(
        id=result.id,
        example_id=result.example_id,
        question=result.question,
        generated_answer=result.generated_answer,
        expected_answer=result.expected_answer,
        faithfulness_score=result.faithfulness_score,
        relevance_score=result.relevance_score,
        completeness_score=result.completeness_score,
        citation_support_score=result.citation_support_score,
        citation_correct=result.citation_correct,
        judge_reason=result.judge_reason,
        recall_at_k=result.recall_at_k,
        precision_at_k=result.precision_at_k,
        mrr=result.mrr,
        ndcg_at_k=result.ndcg_at_k,
        latency_ms=result.latency_ms,
        cost_usd=result.cost_usd,
        model_run_id=result.model_run_id,
        grader_details=result.grader_details,
    )


@router.post("", response_model=EvaluationRunRead, status_code=201)
async def create_evaluation_run(
    project_id: uuid.UUID,
    payload: EvaluationRunCreate,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    generation_provider: GenerationProviderDep,
    settings: SettingsDep,
) -> EvaluationRunRead:
    run = await _service(db, generation_provider, settings).create_run(
        project_id=project_id,
        user_id=current_user_id,
        dataset_name=payload.dataset_name,
        model=payload.model,
    )
    await _enqueue_evaluation_run(db, run.id)
    return _run_read(run)


@router.get("", response_model=list[EvaluationRunRead])
async def list_evaluation_runs(
    project_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    generation_provider: GenerationProviderDep,
    settings: SettingsDep,
) -> list[EvaluationRunRead]:
    runs = await _service(db, generation_provider, settings).list_runs(
        project_id=project_id, user_id=current_user_id
    )
    return [_run_read(r) for r in runs]


@router.get("/{evaluation_run_id}", response_model=EvaluationRunDetailRead)
async def get_evaluation_run(
    project_id: uuid.UUID,
    evaluation_run_id: uuid.UUID,
    current_user_id: CurrentUserIdDep,
    db: DbSessionDep,
    generation_provider: GenerationProviderDep,
    settings: SettingsDep,
) -> EvaluationRunDetailRead:
    run = await _service(db, generation_provider, settings).get_run(
        evaluation_run_id=evaluation_run_id, project_id=project_id, user_id=current_user_id
    )
    return EvaluationRunDetailRead(
        **_run_read(run).model_dump(),
        results=[_result_read(r) for r in run.results],
    )
