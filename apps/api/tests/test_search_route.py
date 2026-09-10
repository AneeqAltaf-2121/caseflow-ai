import uuid
from pathlib import Path

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


async def test_search_route_returns_uploaded_document_content(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    # The StubBroker used in tests (see app/jobs/__init__.py) queues the
    # ingestion message but nothing consumes it — no worker runs in a test
    # process. Run the same `process_document` the worker would, directly,
    # against the identical tmp_path storage api_client's fixture uses.
    settings = get_settings()
    settings.embedding_provider = "local"  # mock's hashes aren't lexically comparable
    try:
        async with db_session_factory() as session:
            owner = await UserRepository(session).create(email="s@x.com", display_name="Searcher")
            org = await OrganizationRepository(session).create(name="S", slug="s-corp")
            await session.commit()
        headers = _auth_headers(owner.id)

        create_response = await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Search project"},
            headers=headers,
        )
        project_id = create_response.json()["id"]

        upload_response = await api_client.post(
            f"/projects/{project_id}/documents",
            files={
                "file": (
                    "notes.txt",
                    b"The quarterly revenue report is attached.",
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

        search_response = await api_client.post(
            f"/projects/{project_id}/search",
            json={"query": "quarterly revenue report"},
            headers=headers,
        )
        assert search_response.status_code == 200
        results = search_response.json()
        assert len(results) == 1
        assert results[0]["document_filename"] == "notes.txt"
        assert "revenue" in results[0]["text"]
    finally:
        settings.embedding_provider = "mock"


async def test_keyword_search_route_finds_exact_terms(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="k@x.com", display_name="Keyword")
        org = await OrganizationRepository(session).create(name="K", slug="k-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    create_response = await api_client.post(
        "/projects",
        json={"organization_id": str(org.id), "name": "Keyword project"},
        headers=headers,
    )
    project_id = create_response.json()["id"]

    upload_response = await api_client.post(
        f"/projects/{project_id}/documents",
        files={
            "file": (
                "terms.txt",
                b"The indemnification clause survives termination.",
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
        embedding_provider=get_embedding_provider(get_settings()),
    )

    response = await api_client.post(
        f"/projects/{project_id}/search/keyword",
        json={"query": "indemnification"},
        headers=headers,
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert "indemnification" in results[0]["text"].lower()


async def test_hybrid_search_route_returns_fusion_diagnostics(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.embedding_provider = "local"
    try:
        async with db_session_factory() as session:
            owner = await UserRepository(session).create(email="h@x.com", display_name="Hybrid")
            org = await OrganizationRepository(session).create(name="H", slug="h-corp")
            await session.commit()
        headers = _auth_headers(owner.id)

        create_response = await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Hybrid project"},
            headers=headers,
        )
        project_id = create_response.json()["id"]

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

        response = await api_client.post(
            f"/projects/{project_id}/search/hybrid",
            json={"query": "termination clause"},
            headers=headers,
        )
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert results[0]["vector_rank"] == 1
        assert results[0]["keyword_rank"] == 1
        assert results[0]["fused_score"] > 0
    finally:
        settings.embedding_provider = "mock"


async def test_rerank_route_narrows_to_top_k(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.embedding_provider = "local"
    try:
        async with db_session_factory() as session:
            owner = await UserRepository(session).create(email="r@x.com", display_name="Reranker")
            org = await OrganizationRepository(session).create(name="R", slug="r-corp")
            await session.commit()
        headers = _auth_headers(owner.id)

        create_response = await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Rerank project"},
            headers=headers,
        )
        project_id = create_response.json()["id"]

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

        response = await api_client.post(
            f"/projects/{project_id}/search/rerank",
            json={"query": "termination clause", "limit": 1},
            headers=headers,
        )
        assert response.status_code == 200
        results = response.json()
        assert len(results) == 1
        assert "termination clause" in results[0]["text"].lower()
    finally:
        settings.embedding_provider = "mock"


async def test_search_route_requires_authentication(api_client: httpx.AsyncClient) -> None:
    response = await api_client.post(f"/projects/{uuid.uuid4()}/search", json={"query": "anything"})
    assert response.status_code == 401
