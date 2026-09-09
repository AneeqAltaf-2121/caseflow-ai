import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.asyncio


async def _seed_user_and_org(session_factory: async_sessionmaker[AsyncSession], suffix: str):
    async with session_factory() as session:
        user = await UserRepository(session).create(
            email=f"route-{suffix}@example.com", display_name="Route Test"
        )
        org = await OrganizationRepository(session).create(name="RouteCo", slug=f"routeco-{suffix}")
        await session.commit()
        return user.id, org.id


async def test_create_and_fetch_project(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user_id, org_id = await _seed_user_and_org(db_session_factory, "create")

    create_response = await api_client.post(
        "/projects",
        json={
            "organization_id": str(org_id),
            "name": "API-created project",
            "description": "created via the route test",
            "created_by": str(user_id),
        },
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    get_response = await api_client.get(f"/projects/{project_id}", params={"user_id": str(user_id)})
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "API-created project"

    list_response = await api_client.get("/projects", params={"user_id": str(user_id)})
    assert list_response.status_code == 200
    assert any(p["id"] == project_id for p in list_response.json())


async def test_get_project_as_non_member_returns_404(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="owner@x.com", display_name="Owner")
        outsider = await UserRepository(session).create(
            email="outsider@x.com", display_name="Outsider"
        )
        org = await OrganizationRepository(session).create(name="X", slug="x-corp")
        await session.commit()

    create_response = await api_client.post(
        "/projects",
        json={
            "organization_id": str(org.id),
            "name": "Private project",
            "created_by": str(owner.id),
        },
    )
    project_id = create_response.json()["id"]

    response = await api_client.get(f"/projects/{project_id}", params={"user_id": str(outsider.id)})
    assert response.status_code == 404
