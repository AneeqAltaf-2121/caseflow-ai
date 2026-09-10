import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import Settings, get_settings
from app.integrations.embeddings import get_embedding_provider
from app.integrations.storage import LocalStorageBackend
from app.jobs.ingestion import process_document
from app.models.job import Job
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def test_conversation_lifecycle_and_grounded_messages(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession], tmp_path
) -> None:
    settings = get_settings()
    settings.embedding_provider = "local"
    try:
        async with db_session_factory() as session:
            owner = await UserRepository(session).create(email="c@x.com", display_name="Chatter")
            org = await OrganizationRepository(session).create(name="C", slug="c-corp")
            await session.commit()
        headers = _auth_headers(owner.id)

        project_id = (
            await api_client.post(
                "/projects",
                json={"organization_id": str(org.id), "name": "Convo project"},
                headers=headers,
            )
        ).json()["id"]

        upload_response = await api_client.post(
            f"/projects/{project_id}/documents",
            files={
                "file": (
                    "notes.txt",
                    b"The termination clause takes effect after 90 days.",
                    "text/plain",
                )
            },
            headers=headers,
        )
        document_id = uuid.UUID(upload_response.json()["id"])

        async with db_session_factory() as session:
            job = (
                await session.execute(select(Job).order_by(Job.created_at.desc()).limit(1))
            ).scalar_one()
        storage = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))
        await process_document(
            job_id=job.id,
            document_id=document_id,
            session_factory=db_session_factory,
            storage=storage,
            embedding_provider=get_embedding_provider(settings),
        )

        create_response = await api_client.post(
            f"/projects/{project_id}/conversations", json={"title": "First chat"}, headers=headers
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]
        assert create_response.json()["title"] == "First chat"

        list_response = await api_client.get(
            f"/projects/{project_id}/conversations", headers=headers
        )
        assert len(list_response.json()) == 1

        message_response = await api_client.post(
            f"/projects/{project_id}/conversations/{conversation_id}/messages",
            json={"content": "when does the termination clause take effect?"},
            headers=headers,
        )
        assert message_response.status_code == 201
        body = message_response.json()
        assert body["assistant_message"]["citations"][0]["document_filename"] == "notes.txt"
        assert body["sources_considered"] == 1

        detail_response = await api_client.get(
            f"/projects/{project_id}/conversations/{conversation_id}", headers=headers
        )
        assert len(detail_response.json()["messages"]) == 2

        rename_response = await api_client.patch(
            f"/projects/{project_id}/conversations/{conversation_id}",
            json={"title": "Renamed chat"},
            headers=headers,
        )
        assert rename_response.json()["title"] == "Renamed chat"

        delete_response = await api_client.delete(
            f"/projects/{project_id}/conversations/{conversation_id}", headers=headers
        )
        assert delete_response.status_code == 204

        get_after_delete = await api_client.get(
            f"/projects/{project_id}/conversations/{conversation_id}", headers=headers
        )
        assert get_after_delete.status_code == 404
    finally:
        settings.embedding_provider = "mock"


async def test_conversations_route_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(f"/projects/{uuid.uuid4()}/conversations")
    assert response.status_code == 401
