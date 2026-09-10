import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ForbiddenError
from app.models.project import ProjectRole
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.prompt_version_repository import PromptVersionRepository
from app.repositories.user_repository import UserRepository
from app.services.project_service import ProjectService
from app.services.prompt_version_service import PromptVersionService

pytestmark = pytest.mark.asyncio


async def _seed(db_session: AsyncSession):
    owner = await UserRepository(db_session).create(email="owner@x.com", display_name="Owner")
    viewer = await UserRepository(db_session).create(email="viewer@x.com", display_name="Viewer")
    org = await OrganizationRepository(db_session).create(name="Co", slug="co")
    project_repository = ProjectRepository(db_session)
    project = await ProjectService(project_repository).create_project(
        organization_id=org.id, name="Proj", description=None, created_by=owner.id
    )
    await project_repository.add_member(
        project_id=project.id, user_id=viewer.id, role=ProjectRole.VIEWER, invited_by=owner.id
    )
    await db_session.commit()

    service = PromptVersionService(
        PromptVersionRepository(db_session), ProjectService(ProjectRepository(db_session))
    )
    return service, owner, viewer, project


async def test_create_version_starts_at_one_and_is_active(db_session: AsyncSession) -> None:
    service, owner, _viewer, project = await _seed(db_session)

    version = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="v1 template"
    )

    assert version.version == 1
    assert version.is_active is True


async def test_creating_a_new_version_deactivates_the_previous_one(
    db_session: AsyncSession,
) -> None:
    service, owner, _viewer, project = await _seed(db_session)

    v1 = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="v1"
    )
    v2 = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="v2"
    )

    versions = await service.list_versions(
        project_id=project.id, user_id=owner.id, name="rag_answer"
    )
    by_id = {v.id: v for v in versions}
    assert by_id[v1.id].is_active is False
    assert by_id[v2.id].is_active is True
    assert v2.version == 2


async def test_creating_without_activating_leaves_previous_active(
    db_session: AsyncSession,
) -> None:
    service, owner, _viewer, project = await _seed(db_session)

    v1 = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="v1"
    )
    v2 = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="v2", activate=False
    )

    versions = await service.list_versions(
        project_id=project.id, user_id=owner.id, name="rag_answer"
    )
    by_id = {v.id: v for v in versions}
    assert by_id[v1.id].is_active is True
    assert by_id[v2.id].is_active is False


async def test_activate_version_switches_the_active_flag(db_session: AsyncSession) -> None:
    service, owner, _viewer, project = await _seed(db_session)
    v1 = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="v1"
    )
    v2 = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="v2", activate=False
    )

    await service.activate_version(project_id=project.id, user_id=owner.id, prompt_version_id=v2.id)

    versions = await service.list_versions(
        project_id=project.id, user_id=owner.id, name="rag_answer"
    )
    by_id = {v.id: v for v in versions}
    assert by_id[v1.id].is_active is False
    assert by_id[v2.id].is_active is True


async def test_viewer_cannot_create_prompt_version(db_session: AsyncSession) -> None:
    service, _owner, viewer, project = await _seed(db_session)

    with pytest.raises(ForbiddenError):
        await service.create_version(
            project_id=project.id, user_id=viewer.id, name="rag_answer", template="hack"
        )


async def test_get_or_seed_active_creates_default_once(db_session: AsyncSession) -> None:
    service, owner, _viewer, project = await _seed(db_session)

    first = await service.get_or_seed_active(
        project_id=project.id, user_id=owner.id, name="rag_answer", default_template="default"
    )
    second = await service.get_or_seed_active(
        project_id=project.id, user_id=owner.id, name="rag_answer", default_template="default"
    )

    assert first.id == second.id
    assert first.version == 1


async def test_get_or_seed_active_returns_customized_version_if_present(
    db_session: AsyncSession,
) -> None:
    service, owner, _viewer, project = await _seed(db_session)
    custom = await service.create_version(
        project_id=project.id, user_id=owner.id, name="rag_answer", template="custom"
    )

    seeded = await service.get_or_seed_active(
        project_id=project.id, user_id=owner.id, name="rag_answer", default_template="default"
    )

    assert seeded.id == custom.id
    assert seeded.template == "custom"
