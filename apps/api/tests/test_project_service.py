import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, ForbiddenError, NotFoundError
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


async def test_update_project_renames_and_redescribes(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner5@example.com")
    org = await _make_org(db_session, "acme5")
    service = ProjectService(ProjectRepository(db_session))

    project = await service.create_project(
        organization_id=org.id, name="Old Name", description="old", created_by=owner.id
    )
    await db_session.commit()

    updated = await service.update_project(
        project_id=project.id,
        user_id=owner.id,
        name="New Name",
        description="new",
        description_set=True,
    )
    assert updated.name == "New Name"
    assert updated.description == "new"


async def test_update_project_partial_patch_leaves_other_field_untouched(
    db_session: AsyncSession,
) -> None:
    owner = await _make_user(db_session, "owner6@example.com")
    org = await _make_org(db_session, "acme6")
    service = ProjectService(ProjectRepository(db_session))

    project = await service.create_project(
        organization_id=org.id, name="Keep Description", description="keep me", created_by=owner.id
    )
    await db_session.commit()

    updated = await service.update_project(
        project_id=project.id,
        user_id=owner.id,
        name="Renamed",
        description=None,
        description_set=False,
    )
    assert updated.name == "Renamed"
    assert updated.description == "keep me"


async def test_viewer_cannot_update_project(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner7@example.com")
    viewer = await _make_user(db_session, "viewer2@example.com")
    org = await _make_org(db_session, "acme7")
    repository = ProjectRepository(db_session)
    service = ProjectService(repository)

    project = await service.create_project(
        organization_id=org.id, name="Locked", description=None, created_by=owner.id
    )
    await repository.add_member(
        project_id=project.id, user_id=viewer.id, role=ProjectRole.VIEWER, invited_by=owner.id
    )
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await service.update_project(
            project_id=project.id,
            user_id=viewer.id,
            name="Hacked",
            description=None,
            description_set=False,
        )


async def test_delete_project_removes_it(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner8@example.com")
    org = await _make_org(db_session, "acme8")
    repository = ProjectRepository(db_session)
    service = ProjectService(repository)

    project = await service.create_project(
        organization_id=org.id, name="Disposable", description=None, created_by=owner.id
    )
    await db_session.commit()

    await service.delete_project(project_id=project.id, user_id=owner.id)
    await db_session.commit()

    assert await repository.get_by_id(project.id) is None


async def test_editor_cannot_delete_project(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner9@example.com")
    editor = await _make_user(db_session, "editor@example.com")
    org = await _make_org(db_session, "acme9")
    repository = ProjectRepository(db_session)
    service = ProjectService(repository)

    project = await service.create_project(
        organization_id=org.id, name="Guarded", description=None, created_by=owner.id
    )
    await repository.add_member(
        project_id=project.id, user_id=editor.id, role=ProjectRole.EDITOR, invited_by=owner.id
    )
    await db_session.commit()

    with pytest.raises(ForbiddenError):
        await service.delete_project(project_id=project.id, user_id=editor.id)


async def test_cannot_remove_last_owner(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner10@example.com")
    org = await _make_org(db_session, "acme10")
    repository = ProjectRepository(db_session)
    service = ProjectService(repository)

    project = await service.create_project(
        organization_id=org.id, name="SoleOwner", description=None, created_by=owner.id
    )
    await db_session.commit()

    with pytest.raises(ConflictError):
        await service.remove_member(
            project_id=project.id, actor_user_id=owner.id, target_user_id=owner.id
        )


async def test_owner_can_remove_editor(db_session: AsyncSession) -> None:
    owner = await _make_user(db_session, "owner11@example.com")
    editor = await _make_user(db_session, "editor2@example.com")
    org = await _make_org(db_session, "acme11")
    repository = ProjectRepository(db_session)
    service = ProjectService(repository)

    project = await service.create_project(
        organization_id=org.id, name="Team", description=None, created_by=owner.id
    )
    await repository.add_member(
        project_id=project.id, user_id=editor.id, role=ProjectRole.EDITOR, invited_by=owner.id
    )
    await db_session.commit()

    await service.remove_member(
        project_id=project.id, actor_user_id=owner.id, target_user_id=editor.id
    )
    await db_session.commit()

    assert await repository.get_member(project_id=project.id, user_id=editor.id) is None
