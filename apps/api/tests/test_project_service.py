import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ForbiddenError, NotFoundError
from app.models.project import ProjectRole
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.user_repository import UserRepository
from app.services.project_service import ProjectService

pytestmark = pytest.mark.asyncio


async def _make_user(session: AsyncSession, email: str):
    return await UserRepository(session).create(email=email, display_name=email)


async def _make_org(session: AsyncSession, slug: str):
    return await OrganizationRepository(session).create(name=slug, slug=slug)


async def test_create_project_adds_creator_as_owner(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner@example.com")
    org = await _make_org(db_session, "acme")
    service = ProjectService(ProjectRepository(db_session))

    project = await service.create_project(
        organization_id=org.id, name="Contract Review", description=None, created_by=owner.id
    )
    await db_session.commit()

    member = await ProjectRepository(db_session).get_member(project_id=project.id, user_id=owner.id)
    assert member is not None
    assert member.role == ProjectRole.OWNER


async def test_get_project_for_user_raises_not_found_for_non_member(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session, "owner2@example.com")
    outsider = await _make_user(db_session, "outsider@example.com")
    org = await _make_org(db_session, "acme2")
    service = ProjectService(ProjectRepository(db_session))

    project = await service.create_project(
        organization_id=org.id, name="Discovery", description=None, created_by=owner.id
    )
    await db_session.commit()

    with pytest.raises(NotFoundError):
        await service.get_project_for_user(project_id=project.id, user_id=outsider.id)


async def test_get_project_for_user_succeeds_for_member(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner3@example.com")
    org = await _make_org(db_session, "acme3")
    service = ProjectService(ProjectRepository(db_session))

    project = await service.create_project(
        organization_id=org.id, name="Merger Review", description=None, created_by=owner.id
    )
    await db_session.commit()

    fetched = await service.get_project_for_user(project_id=project.id, user_id=owner.id)
    assert fetched.id == project.id


async def test_require_role_rejects_viewer_for_owner_only_action(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner4@example.com")
    viewer = await _make_user(db_session, "viewer@example.com")
    org = await _make_org(db_session, "acme4")
    repository = ProjectRepository(db_session)
    service = ProjectService(repository)

    project = await service.create_project(
        organization_id=org.id, name="Compliance Audit", description=None, created_by=owner.id
    )
    await repository.add_member(
        project_id=project.id, user_id=viewer.id, role=ProjectRole.VIEWER, invited_by=owner.id
    )
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await service.require_role(
            project_id=project.id, user_id=viewer.id, allowed={ProjectRole.OWNER}
        )
