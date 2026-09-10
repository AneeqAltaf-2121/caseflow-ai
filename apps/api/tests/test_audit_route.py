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


async def test_audit_log_records_project_and_document_actions(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="aud-owner@x.com", display_name="O")
        org = await OrganizationRepository(session).create(name="Aud", slug="aud-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Audited"},
            headers=headers,
        )
    ).json()["id"]

    upload = await api_client.post(
        f"/projects/{project_id}/documents",
        files={"file": ("notes.txt", b"evidence", "text/plain")},
        headers=headers,
    )
    document_id = upload.json()["id"]

    delete_response = await api_client.delete(
        f"/projects/{project_id}/documents/{document_id}", headers=headers
    )
    assert delete_response.status_code == 204

    # Deleted document is gone.
    get_response = await api_client.get(
        f"/projects/{project_id}/documents/{document_id}", headers=headers
    )
    assert get_response.status_code == 404

    audit_response = await api_client.get(f"/projects/{project_id}/audit-events", headers=headers)
    assert audit_response.status_code == 200
    actions = [e["action"] for e in audit_response.json()]
    assert "project.created" in actions
    assert "document.uploaded" in actions
    assert "document.deleted" in actions


async def test_change_member_role_via_route(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="role-owner@x.com", display_name="O")
        member = await UserRepository(session).create(email="role-member@x.com", display_name="M")
        org = await OrganizationRepository(session).create(name="Role", slug="role-corp")
        await session.commit()
    owner_headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Role project"},
            headers=owner_headers,
        )
    ).json()["id"]

    await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "role-member@x.com", "role": "viewer"},
        headers=owner_headers,
    )

    change_response = await api_client.patch(
        f"/projects/{project_id}/members/{member.id}",
        json={"role": "editor"},
        headers=owner_headers,
    )
    assert change_response.status_code == 200
    assert change_response.json()["role"] == "editor"

    audit_response = await api_client.get(
        f"/projects/{project_id}/audit-events", headers=owner_headers
    )
    actions = [e["action"] for e in audit_response.json()]
    assert "member.role_changed" in actions


async def test_non_member_cannot_view_audit_log(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="aud-owner2@x.com", display_name="O")
        outsider = await UserRepository(session).create(email="aud-out2@x.com", display_name="X")
        org = await OrganizationRepository(session).create(name="Aud2", slug="aud2-corp")
        await session.commit()

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Private"},
            headers=_auth_headers(owner.id),
        )
    ).json()["id"]

    response = await api_client.get(
        f"/projects/{project_id}/audit-events", headers=_auth_headers(outsider.id)
    )
    assert response.status_code == 404
