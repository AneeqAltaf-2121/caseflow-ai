import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import Settings, get_settings
from app.integrations.embeddings import get_embedding_provider
from app.integrations.generation import get_generation_provider
from app.integrations.storage import LocalStorageBackend
from app.jobs.ingestion import process_document
from app.jobs.reports import generate_report
from app.models.job import Job
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import CrossEncoderReranker


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def test_report_lifecycle(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.embedding_provider = "local"
    try:
        async with db_session_factory() as session:
            owner = await UserRepository(session).create(email="rep@x.com", display_name="Rep")
            org = await OrganizationRepository(session).create(name="R", slug="r-corp")
            await session.commit()
        headers = _auth_headers(owner.id)

        project_id = (
            await api_client.post(
                "/projects",
                json={"organization_id": str(org.id), "name": "Report project"},
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
            ingest_job = (
                await session.execute(select(Job).order_by(Job.created_at.desc()).limit(1))
            ).scalar_one()
        storage = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))
        await process_document(
            job_id=ingest_job.id,
            document_id=document_id,
            session_factory=db_session_factory,
            storage=storage,
            embedding_provider=get_embedding_provider(settings),
        )

        create_response = await api_client.post(
            f"/projects/{project_id}/reports",
            json={"report_type": "executive_summary", "title": "Q1 Report"},
            headers=headers,
        )
        assert create_response.status_code == 201
        report_id = uuid.UUID(create_response.json()["id"])
        assert create_response.json()["status"] == "queued"

        async with db_session_factory() as session:
            report_job_query = select(Job).where(Job.type == "report_generation")
            report_job_query = report_job_query.order_by(Job.created_at.desc())
            report_job = (await session.execute(report_job_query)).scalars().first()
        assert report_job is not None

        # StubBroker queues the message but nothing consumes it in a test
        # process — run the job body directly, same as ingestion tests.
        await generate_report(
            job_id=report_job.id,
            report_id=report_id,
            session_factory=db_session_factory,
            embedding_provider=get_embedding_provider(settings),
            reranker=CrossEncoderReranker(),
            generation_provider=get_generation_provider(settings),
        )

        detail_response = await api_client.get(
            f"/projects/{project_id}/reports/{report_id}", headers=headers
        )
        assert detail_response.status_code == 200
        body = detail_response.json()
        assert body["status"] == "ready"
        assert len(body["sections"]) == 1
        assert body["sections"][0]["citations"][0]["document_filename"] == "notes.txt"

        list_response = await api_client.get(f"/projects/{project_id}/reports", headers=headers)
        assert len(list_response.json()) == 1
    finally:
        settings.embedding_provider = "mock"


async def test_viewer_cannot_create_report(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="o@x.com", display_name="Owner")
        viewer = await UserRepository(session).create(email="v@x.com", display_name="Viewer")
        org = await OrganizationRepository(session).create(name="V", slug="v-corp")
        await session.commit()
    owner_headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Viewer project"},
            headers=owner_headers,
        )
    ).json()["id"]
    await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "v@x.com", "role": "viewer"},
        headers=owner_headers,
    )

    response = await api_client.post(
        f"/projects/{project_id}/reports",
        json={"report_type": "executive_summary", "title": "Nope"},
        headers=_auth_headers(viewer.id),
    )
    assert response.status_code == 403


async def test_reports_route_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(f"/projects/{uuid.uuid4()}/reports")
    assert response.status_code == 401
