import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import get_settings
from app.models.model_run import ModelRunStatus
from app.repositories.model_run_repository import ModelRunRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def test_get_cost_summary_returns_aggregates(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="cost-route@x.com", display_name="O")
        org = await OrganizationRepository(session).create(name="CR", slug="cr-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Cost project"},
            headers=headers,
        )
    ).json()["id"]

    async with db_session_factory() as session:
        await ModelRunRepository(session).create(
            project_id=uuid.UUID(project_id),
            user_id=owner.id,
            provider="MockGenerationProvider",
            model="mock-echo-v1",
            prompt_version_id=None,
            temperature=0.0,
            latency_ms=42,
            input_tokens=10,
            output_tokens=5,
            estimated_cost_usd=0.0,
            status=ModelRunStatus.SUCCEEDED,
            retrieval_config={},
        )
        await session.commit()

    response = await api_client.get(f"/projects/{project_id}/costs", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["total_runs"] == 1
    assert body["total_input_tokens"] == 10
    assert body["total_output_tokens"] == 5
    assert body["by_model"]["mock-echo-v1"] == 0.0
    assert len(body["by_day"]) == 1


async def test_get_cost_summary_requires_membership(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="cost-owner2@x.com", display_name="O")
        outsider = await UserRepository(session).create(email="cost-out2@x.com", display_name="X")
        org = await OrganizationRepository(session).create(name="CR2", slug="cr2-corp")
        await session.commit()

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Private cost project"},
            headers=_auth_headers(owner.id),
        )
    ).json()["id"]

    response = await api_client.get(
        f"/projects/{project_id}/costs", headers=_auth_headers(outsider.id)
    )
    assert response.status_code == 404
