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


async def test_create_list_and_activate_prompt_version(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="p@x.com", display_name="Prompter")
        org = await OrganizationRepository(session).create(name="P", slug="p-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Prompt project"},
            headers=headers,
        )
    ).json()["id"]

    v1_response = await api_client.post(
        f"/projects/{project_id}/prompts",
        json={"name": "rag_answer", "template": "v1 template"},
        headers=headers,
    )
    assert v1_response.status_code == 201
    assert v1_response.json()["version"] == 1
    assert v1_response.json()["is_active"] is True

    v2_response = await api_client.post(
        f"/projects/{project_id}/prompts",
        json={"name": "rag_answer", "template": "v2 template"},
        headers=headers,
    )
    v1_id = v1_response.json()["id"]
    v2_id = v2_response.json()["id"]

    list_response = await api_client.get(
        f"/projects/{project_id}/prompts/rag_answer", headers=headers
    )
    versions = {v["id"]: v for v in list_response.json()}
    assert versions[v1_id]["is_active"] is False
    assert versions[v2_id]["is_active"] is True

    activate_response = await api_client.post(
        f"/projects/{project_id}/prompts/{v1_id}/activate", headers=headers
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["is_active"] is True

    list_response_2 = await api_client.get(
        f"/projects/{project_id}/prompts/rag_answer", headers=headers
    )
    versions_2 = {v["id"]: v for v in list_response_2.json()}
    assert versions_2[v1_id]["is_active"] is True
    assert versions_2[v2_id]["is_active"] is False


async def test_prompt_versions_route_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(f"/projects/{uuid.uuid4()}/prompts/rag_answer")
    assert response.status_code == 401
