import uuid
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import Settings, get_settings
from app.integrations.embeddings import get_embedding_provider
from app.integrations.generation import MockGenerationProvider
from app.integrations.storage import LocalStorageBackend
from app.jobs.evaluations import run_evaluation
from app.jobs.ingestion import process_document
from app.models.job import Job
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.retrieval.reranker import MockReranker

CANNED_JUDGE_RESPONSE = '{"score": 0.9, "reason": "solid", "failures": []}'


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


async def test_evaluation_run_lifecycle(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    tmp_path: Path,
) -> None:
    settings = get_settings()
    settings.embedding_provider = "local"
    try:
        async with db_session_factory() as session:
            owner = await UserRepository(session).create(email="ev@x.com", display_name="Ev")
            org = await OrganizationRepository(session).create(name="E", slug="e-corp")
            await session.commit()
        headers = _auth_headers(owner.id)

        project_id = (
            await api_client.post(
                "/projects",
                json={"organization_id": str(org.id), "name": "Eval project"},
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
            f"/projects/{project_id}/evaluations",
            json={"dataset_name": "sample_contract_qa"},
            headers=headers,
        )
        assert create_response.status_code == 201
        body = create_response.json()
        assert body["status"] == "queued"
        assert body["dataset_name"] == "sample_contract_qa"
        assert body["dataset_version"] == 1
        assert body["model"] == "mock-echo-v1"
        assert body["retriever_version"] == "hybrid_rrf_v1"
        run_id = uuid.UUID(body["id"])

        async with db_session_factory() as session:
            eval_job_query = select(Job).where(Job.type == "evaluation_run")
            eval_job_query = eval_job_query.order_by(Job.created_at.desc())
            eval_job = (await session.execute(eval_job_query)).scalars().first()
        assert eval_job is not None

        # StubBroker queues the message but nothing consumes it in a test
        # process — run the job body directly, same as ingestion/reports.
        await run_evaluation(
            job_id=eval_job.id,
            evaluation_run_id=run_id,
            session_factory=db_session_factory,
            embedding_provider=get_embedding_provider(settings),
            reranker=MockReranker(),
            generation_provider=MockGenerationProvider(
                canned_response="The clause takes effect after 90 days [1]."
            ),
            judge_provider=MockGenerationProvider(canned_response=CANNED_JUDGE_RESPONSE),
        )

        detail_response = await api_client.get(
            f"/projects/{project_id}/evaluations/{run_id}", headers=headers
        )
        assert detail_response.status_code == 200
        detail = detail_response.json()
        assert detail["status"] == "succeeded"
        assert len(detail["results"]) == 3
        assert all(r["faithfulness_score"] == 0.9 for r in detail["results"])

        list_response = await api_client.get(f"/projects/{project_id}/evaluations", headers=headers)
        assert len(list_response.json()) == 1
    finally:
        settings.embedding_provider = "mock"


async def test_viewer_cannot_create_evaluation_run(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="eo@x.com", display_name="Owner")
        viewer = await UserRepository(session).create(email="ev2@x.com", display_name="Viewer")
        org = await OrganizationRepository(session).create(name="EV", slug="ev-corp")
        await session.commit()
    owner_headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Viewer eval project"},
            headers=owner_headers,
        )
    ).json()["id"]
    await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "ev2@x.com", "role": "viewer"},
        headers=owner_headers,
    )

    response = await api_client.post(
        f"/projects/{project_id}/evaluations",
        json={"dataset_name": "sample_contract_qa"},
        headers=_auth_headers(viewer.id),
    )
    assert response.status_code == 403


async def test_create_evaluation_run_with_unknown_dataset_returns_404(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="eo3@x.com", display_name="Owner")
        org = await OrganizationRepository(session).create(name="EV3", slug="ev3-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Unknown dataset project"},
            headers=headers,
        )
    ).json()["id"]

    response = await api_client.post(
        f"/projects/{project_id}/evaluations",
        json={"dataset_name": "does_not_exist"},
        headers=headers,
    )
    assert response.status_code == 404


async def test_create_evaluation_run_with_explicit_model_override(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    """Phase 31 model comparison: two runs of the same dataset can be
    created with different `model` values, each recorded on its own
    EvaluationRun row — the basis for comparing them."""
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="eo4@x.com", display_name="Owner")
        org = await OrganizationRepository(session).create(name="EV4", slug="ev4-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Model comparison project"},
            headers=headers,
        )
    ).json()["id"]

    default_run = await api_client.post(
        f"/projects/{project_id}/evaluations",
        json={"dataset_name": "sample_contract_qa"},
        headers=headers,
    )
    assert default_run.status_code == 201
    assert default_run.json()["model"] == "mock-echo-v1"

    openai_run = await api_client.post(
        f"/projects/{project_id}/evaluations",
        json={"dataset_name": "sample_contract_qa", "model": "gpt-4o-mini"},
        headers=headers,
    )
    assert openai_run.status_code == 201
    assert openai_run.json()["model"] == "gpt-4o-mini"
    assert openai_run.json()["dataset_name"] == "sample_contract_qa"

    list_response = await api_client.get(f"/projects/{project_id}/evaluations", headers=headers)
    models = {run["model"] for run in list_response.json()}
    assert models == {"mock-echo-v1", "gpt-4o-mini"}


async def test_create_evaluation_run_with_unknown_model_returns_422(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="eo5@x.com", display_name="Owner")
        org = await OrganizationRepository(session).create(name="EV5", slug="ev5-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects",
            json={"organization_id": str(org.id), "name": "Unknown model project"},
            headers=headers,
        )
    ).json()["id"]

    response = await api_client.post(
        f"/projects/{project_id}/evaluations",
        json={"dataset_name": "sample_contract_qa", "model": "not-a-real-model"},
        headers=headers,
    )
    assert response.status_code == 422
