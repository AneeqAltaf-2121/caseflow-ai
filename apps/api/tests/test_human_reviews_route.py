import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import get_settings
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def test_human_review_lifecycle_via_route(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="hrr-owner@x.com", display_name="O")
        org = await OrganizationRepository(session).create(name="HRR", slug="hrr-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Review project"},
            headers=headers,
        )
    ).json()["id"]

    conversation_id = (
        await api_client.post(f"/projects/{project_id}/conversations", json={}, headers=headers)
    ).json()["id"]

    post_response = await api_client.post(
        f"/projects/{project_id}/conversations/{conversation_id}/messages",
        json={"content": "What is the termination clause?"},
        headers=headers,
    )
    assert post_response.status_code == 201
    assistant_message_id = post_response.json()["assistant_message"]["id"]

    flag_response = await api_client.post(
        f"/projects/{project_id}/reviews",
        json={"message_id": assistant_message_id},
        headers=headers,
    )
    assert flag_response.status_code == 201
    review = flag_response.json()
    assert review["status"] == "needs_review"
    review_id = review["id"]

    list_response = await api_client.get(f"/projects/{project_id}/reviews", headers=headers)
    assert len(list_response.json()) == 1

    decide_response = await api_client.patch(
        f"/projects/{project_id}/reviews/{review_id}",
        json={"status": "corrected", "corrected_answer": "The real answer.", "reason": "Fixed."},
        headers=headers,
    )
    assert decide_response.status_code == 200
    body = decide_response.json()
    assert body["status"] == "corrected"
    assert body["corrected_answer"] == "The real answer."
    assert body["reviewer_id"] == str(owner.id)

    audit_response = await api_client.get(f"/projects/{project_id}/audit-events", headers=headers)
    actions = [e["action"] for e in audit_response.json()]
    assert "human_review.completed" in actions


async def test_viewer_can_flag_but_not_resolve(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="hrr-owner2@x.com", display_name="O")
        viewer = await UserRepository(session).create(email="hrr-viewer2@x.com", display_name="V")
        org = await OrganizationRepository(session).create(name="HRR2", slug="hrr2-corp")
        await session.commit()
    owner_headers = _auth_headers(owner.id)
    viewer_headers = _auth_headers(viewer.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Review project 2"},
            headers=owner_headers,
        )
    ).json()["id"]
    await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "hrr-viewer2@x.com", "role": "viewer"},
        headers=owner_headers,
    )

    conversation_id = (
        await api_client.post(
            f"/projects/{project_id}/conversations", json={}, headers=owner_headers
        )
    ).json()["id"]
    post_response = await api_client.post(
        f"/projects/{project_id}/conversations/{conversation_id}/messages",
        json={"content": "Anything?"},
        headers=owner_headers,
    )
    assistant_message_id = post_response.json()["assistant_message"]["id"]

    flag_response = await api_client.post(
        f"/projects/{project_id}/reviews",
        json={"message_id": assistant_message_id},
        headers=viewer_headers,
    )
    assert flag_response.status_code == 201
    review_id = flag_response.json()["id"]

    resolve_response = await api_client.patch(
        f"/projects/{project_id}/reviews/{review_id}",
        json={"status": "approved"},
        headers=viewer_headers,
    )
    assert resolve_response.status_code == 403
