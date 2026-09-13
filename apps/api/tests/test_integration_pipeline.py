"""Phase 40: integration testing across DB, Redis, the API, and workers
together — one coherent narrative through the real upload -> job queued
-> worker processes -> chunks stored -> embeddings stored -> document
READY pipeline, then on into retrieval and a grounded chat answer,
rather than each layer's own isolated unit tests (which already exist
throughout the suite — this file is about proving the seams between
them actually work).

Every earlier phase's job tests call a job function directly against a
db_session_factory rather than running a real broker/worker process —
necessary here too (see tests/conftest.py and every jobs/*.py module's
own "not exercised in CI" note): this sandbox has no live Postgres/Redis
for a real out-of-process dramatiq worker to connect to, and the actor
wrapper's `asyncio.run()` would build a fresh engine against the real
`DATABASE_URL` anyway, not the test's in-memory SQLite session factory.
What *is* real and exercised end-to-end here: the HTTP API layer, the
StubBroker standing in for Redis (a message is actually enqueued, not
just assumed), the durable Job row it's paired with, the full ingestion
pipeline, and the Phase 33 cache (InMemoryCache standing in for Redis)
that retrieval reads from.
"""

import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import Settings, get_settings
from app.integrations.embeddings import get_embedding_provider
from app.integrations.storage import LocalStorageBackend
from app.jobs import broker
from app.jobs.ingestion import process_document
from app.models.document import DocumentStatus
from app.models.job import Job, JobStatus
from app.repositories.chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def test_full_ingestion_pipeline_across_api_db_redis_and_worker(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    settings = get_settings()
    settings.embedding_provider = "local"
    try:
        # --- API layer: real user, real org, real project ---
        async with db_session_factory() as session:
            owner = await UserRepository(session).create(
                email="pipeline@x.com", display_name="Pipeline"
            )
            org = await OrganizationRepository(session).create(name="Pipe", slug="pipe-corp")
            await session.commit()
        headers = _auth_headers(owner.id)

        project_id = (
            await api_client.post(
                "/projects",
                json={"organization_id": str(org.id), "name": "Pipeline project"},
                headers=headers,
            )
        ).json()["id"]

        # --- API layer: upload creates the Document + the durable Job row ---
        upload_response = await api_client.post(
            f"/projects/{project_id}/documents",
            files={
                "file": (
                    "contract.txt",
                    b"The termination clause takes effect after 90 days notice.",
                    "text/plain",
                )
            },
            headers=headers,
        )
        assert upload_response.status_code == 201
        document_id = uuid.UUID(upload_response.json()["id"])
        assert upload_response.json()["status"] == "uploaded"

        async with db_session_factory() as session:
            job = (
                await session.execute(select(Job).order_by(Job.created_at.desc()).limit(1))
            ).scalar_one()
        assert job.type == "document_ingestion"
        assert job.status == JobStatus.QUEUED
        assert job.payload == {"document_id": str(document_id)}

        # --- "Redis" layer: the job route didn't just write a DB row, it
        # actually enqueued a message on the broker (StubBroker standing
        # in for a real Redis connection in tests — see this module's
        # docstring) that a real worker process would consume. ---
        ingestion_queue = broker.queues["ingestion"]
        assert ingestion_queue.qsize() >= 1

        # --- Worker layer: run the actual job body (same function a real
        # worker consuming that queued message would run) against the
        # same DB the API just wrote to, and the same storage location —
        # `tmp_path` is function-scoped, so the api_client fixture (which
        # also depends on it) already wrote the upload under this exact
        # path, matching how api and worker share one storage volume in
        # docker-compose (Phase 39). ---
        storage = LocalStorageBackend(Settings(local_storage_path=str(tmp_path)))

        await process_document(
            job_id=job.id,
            document_id=document_id,
            session_factory=db_session_factory,
            storage=storage,
            embedding_provider=get_embedding_provider(settings),
        )

        # --- DB layer: chunks exist, each with a real embedding, and the
        # document is READY. ---
        async with db_session_factory() as session:
            final_document = await DocumentRepository(session).get_by_id(document_id)
            chunks = await DocumentChunkRepository(session).list_for_document(document_id)
            final_job = await session.get(Job, job.id)

        assert final_document is not None
        assert final_document.status == DocumentStatus.READY
        assert len(chunks) >= 1
        assert all(chunk.embedding is not None for chunk in chunks)
        assert final_job is not None
        assert final_job.status == JobStatus.SUCCEEDED

        # --- API layer again: the document is visible as READY through
        # the same route a client polls. ---
        get_response = await api_client.get(
            f"/projects/{project_id}/documents/{document_id}", headers=headers
        )
        assert get_response.json()["status"] == "ready"

        # --- Retrieval + generation, exercising the Phase 33 cache
        # (InMemoryCache standing in for Redis) and a real grounded
        # answer with a citation back to the chunk the worker just
        # created — the pipeline this phase is meant to prove doesn't
        # stop at "chunks exist", it ends at "the app can actually
        # answer questions from them". ---
        conversation_id = (
            await api_client.post(f"/projects/{project_id}/conversations", json={}, headers=headers)
        ).json()["id"]
        answer_response = await api_client.post(
            f"/projects/{project_id}/conversations/{conversation_id}/messages",
            json={"content": "termination clause"},
            headers=headers,
        )
        assert answer_response.status_code == 201
        assistant_message = answer_response.json()["assistant_message"]
        assert len(assistant_message["citations"]) >= 1
        assert assistant_message["citations"][0]["document_filename"] == "contract.txt"
    finally:
        settings.embedding_provider = "mock"


async def test_duplicate_upload_does_not_enqueue_a_second_ingestion_job(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Phase 35's duplicate-upload rejection means the "Redis" layer
    should see exactly one enqueued message for one piece of content,
    not two — a real assertion about the queue, not just the HTTP
    response code."""
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="dup-pipe@x.com", display_name="D")
        org = await OrganizationRepository(session).create(name="DupPipe", slug="dup-pipe-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "P"}, headers=headers
        )
    ).json()["id"]

    ingestion_queue = broker.queues["ingestion"]
    before = ingestion_queue.qsize()

    payload = {"file": ("evidence.txt", b"identical bytes", "text/plain")}
    first = await api_client.post(
        f"/projects/{project_id}/documents", files=payload, headers=headers
    )
    assert first.status_code == 201
    second = await api_client.post(
        f"/projects/{project_id}/documents", files=payload, headers=headers
    )
    assert second.status_code == 409

    after = ingestion_queue.qsize()
    assert after - before == 1
