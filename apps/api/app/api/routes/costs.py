"""Cost tracking (Phase 32), nested under a project — a read-only
aggregate view over ModelRun spend, open to any project member."""

import uuid

from fastapi import APIRouter

from app.cache import get_cache
from app.dependencies import CurrentUserIdDep, DbSessionDep
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.project_repository import ProjectRepository
from app.schemas.cost import CostDayRead, CostSummaryRead
from app.services.cost_service import CostService
from app.services.project_service import ProjectService

router = APIRouter(prefix="/projects/{project_id}/costs", tags=["costs"])


def _service(db: DbSessionDep) -> CostService:
    return CostService(ModelRunRepository(db), ProjectService(ProjectRepository(db)), get_cache())


@router.get("", response_model=CostSummaryRead)
async def get_cost_summary(
    project_id: uuid.UUID, current_user_id: CurrentUserIdDep, db: DbSessionDep
) -> CostSummaryRead:
    summary = await _service(db).get_cost_summary(project_id=project_id, user_id=current_user_id)
    return CostSummaryRead(
        project_id=summary.project_id,
        total_cost_usd=summary.total_cost_usd,
        total_input_tokens=summary.total_input_tokens,
        total_output_tokens=summary.total_output_tokens,
        total_runs=summary.total_runs,
        by_day=[
            CostDayRead(
                day=row.day,
                model=row.model,
                user_id=row.user_id,
                total_cost_usd=row.total_cost_usd,
                total_input_tokens=row.total_input_tokens,
                total_output_tokens=row.total_output_tokens,
                run_count=row.run_count,
            )
            for row in summary.by_day
        ],
        by_model=summary.by_model,
        by_user=summary.by_user,
    )
