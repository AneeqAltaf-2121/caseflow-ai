import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import get_settings
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository

pytestmark = pytest.mark.asyncio


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


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
    headers = _auth_headers(user_id)

    create_response = await api_client.post(
        "/projects",
        json={
            "organization_id": str(org_id),
            "name": "API-created project",
            "description": "created via the route test",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    get_response = await api_client.get(f"/projects/{project_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "API-created project"

    list_response = await api_client.get("/projects", headers=headers)
    assert list_response.status_code == 200
    assert any(p["id"] == project_id for p in list_response.json())


async def test_create_project_without_organization_id_auto_provisions_one(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        user = await UserRepository(session).create(
            email="no-org@example.com", display_name="No Org"
        )
        await session.commit()
    headers = _auth_headers(user.id)

    first = await api_client.post("/projects", json={"name": "First"}, headers=headers)
    assert first.status_code == 201
    second = await api_client.post("/projects", json={"name": "Second"}, headers=headers)
    assert second.status_code == 201

    # Same user reuses the same auto-provisioned personal organization.
    assert first.json()["organization_id"] == second.json()["organization_id"]


async def test_project_routes_require_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/projects")
    assert response.status_code == 401


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
        json={"organization_id": str(org.id), "name": "Private project"},
        headers=_auth_headers(owner.id),
    )
    project_id = create_response.json()["id"]

    response = await api_client.get(f"/projects/{project_id}", headers=_auth_headers(outsider.id))
    assert response.status_code == 404


async def test_owner_can_invite_member_but_viewer_cannot(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="owner2@x.com", display_name="Owner")
        invitee = await UserRepository(session).create(
            email="invitee@x.com", display_name="Invitee"
        )
        org = await OrganizationRepository(session).create(name="Y", slug="y-corp")
        await session.commit()

    create_response = await api_client.post(
        "/projects",
        json={"organization_id": str(org.id), "name": "Shared project"},
        headers=_auth_headers(owner.id),
    )
    project_id = create_response.json()["id"]

    invite_response = await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "invitee@x.com", "role": "viewer"},
        headers=_auth_headers(owner.id),
    )
    assert invite_response.status_code == 201
    assert invite_response.json()["role"] == "viewer"

    members_response = await api_client.get(
        f"/projects/{project_id}/members", headers=_auth_headers(owner.id)
    )
    assert len(members_response.json()) == 2

    forbidden_response = await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "owner2@x.com", "role": "editor"},
        headers=_auth_headers(invitee.id),
    )
    assert forbidden_response.status_code == 403


async def test_update_and_delete_project(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user_id, org_id = await _seed_user_and_org(db_session_factory, "crud")
    headers = _auth_headers(user_id)

    create_response = await api_client.post(
        "/projects",
        json={"organization_id": str(org_id), "name": "Before"},
        headers=headers,
    )
    project_id = create_response.json()["id"]

    patch_response = await api_client.patch(
        f"/projects/{project_id}", json={"name": "After"}, headers=headers
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "After"

    delete_response = await api_client.delete(f"/projects/{project_id}", headers=headers)
    assert delete_response.status_code == 204

    get_response = await api_client.get(f"/projects/{project_id}", headers=headers)
    assert get_response.status_code == 404


async def test_remove_member_route(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="rm-owner@x.com", display_name="Owner")
        member = await UserRepository(session).create(
            email="rm-member@x.com", display_name="Member"
        )
        org = await OrganizationRepository(session).create(name="Z", slug="z-corp")
        await session.commit()

    owner_headers = _auth_headers(owner.id)
    create_response = await api_client.post(
        "/projects",
        json={"organization_id": str(org.id), "name": "Removable"},
        headers=owner_headers,
    )
    project_id = create_response.json()["id"]

    await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "rm-member@x.com", "role": "viewer"},
        headers=owner_headers,
    )

    remove_response = await api_client.delete(
        f"/projects/{project_id}/members/{member.id}", headers=owner_headers
    )
    assert remove_response.status_code == 204

    members_response = await api_client.get(
        f"/projects/{project_id}/members", headers=owner_headers
    )
    assert len(members_response.json()) == 1
