import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models.model_run import ModelRunStatus
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.cost_service import CostService
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _seed_project(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="cost-owner@x.com", display_name="Owner")
    outsider = await UserRepository(db_session).create(email="outsider@x.com", display_name="Out")
    org = await OrganizationRepository(db_session).create(name="Co", slug="co-cost")
    project = await ProjectService(ProjectRepository(db_session)).create_project(
        organization_id=org.id, name="Legal", description=None, created_by=owner.id
    )
    await db_session.commit()
    return owner, outsider, project


async def _create_model_run(
    db_session: AsyncSession, *, project_id, user_id, model: str, cost_usd: float
):
    await ModelRunRepository(db_session).create(
        project_id=project_id,
        user_id=user_id,
        provider="MockGenerationProvider",
        model=model,
        prompt_version_id=None,
        temperature=0.0,
        latency_ms=100,
        input_tokens=50,
        output_tokens=20,
        estimated_cost_usd=cost_usd,
        status=ModelRunStatus.SUCCEEDED,
        retrieval_config={},
    )
    await db_session.commit()


async def test_cost_summary_aggregates_totals_across_runs(db_session: AsyncSession) -> None:
    owner, _outsider, project = await _seed_project(db_session)
    await _create_model_run(
        db_session, project_id=project.id, user_id=owner.id, model="gpt-4o-mini", cost_usd=0.01
    )
    await _create_model_run(
        db_session, project_id=project.id, user_id=owner.id, model="gpt-4o-mini", cost_usd=0.02
    )
    await _create_model_run(
        db_session,
        project_id=project.id,
        user_id=owner.id,
        model="claude-3-5-haiku-20241022",
        cost_usd=0.03,
    )

    service = CostService(
        ModelRunRepository(db_session), ProjectService(ProjectRepository(db_session))
    )
    summary = await service.get_cost_summary(project_id=project.id, user_id=owner.id)

    assert summary.total_runs == 3
    assert summary.total_cost_usd == pytest.approx(0.06)
    assert summary.total_input_tokens == 150
    assert summary.total_output_tokens == 60
    assert summary.by_model["gpt-4o-mini"] == pytest.approx(0.03)
    assert summary.by_model["claude-3-5-haiku-20241022"] == pytest.approx(0.03)
    assert summary.by_user[str(owner.id)] == pytest.approx(0.06)
    # Same day + model -> the two gpt-4o-mini runs collapse into one
    # (day, model, user) bucket rather than staying as separate rows.
    gpt_rows = [row for row in summary.by_day if row.model == "gpt-4o-mini"]
    assert len(gpt_rows) == 1
    assert gpt_rows[0].run_count == 2
    assert gpt_rows[0].total_cost_usd == pytest.approx(0.03)


async def test_cost_summary_empty_project_has_zero_totals(db_session: AsyncSession) -> None:
    owner, _outsider, project = await _seed_project(db_session)
    service = CostService(
        ModelRunRepository(db_session), ProjectService(ProjectRepository(db_session))
    )

    summary = await service.get_cost_summary(project_id=project.id, user_id=owner.id)

    assert summary.total_runs == 0
    assert summary.total_cost_usd == 0.0
    assert summary.by_day == []
    assert summary.by_model == {}


async def test_cost_summary_requires_project_membership(db_session: AsyncSession) -> None:
    owner, outsider, project = await _seed_project(db_session)
    service = CostService(
        ModelRunRepository(db_session), ProjectService(ProjectRepository(db_session))
    )

    with pytest.raises(NotFoundError):
        await service.get_cost_summary(project_id=project.id, user_id=outsider.id)
