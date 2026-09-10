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


async def _seed_project(
    api_client: httpx.AsyncClient,
    db_session_factory: async_sessionmaker[AsyncSession],
    *,
    suffix: str,
):
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(
            email=f"doc-owner-{suffix}@x.com", display_name="Owner"
        )
        org = await OrganizationRepository(session).create(name="DocCo", slug=f"docco-{suffix}")
        await session.commit()

    headers = _auth_headers(owner.id)
    create_response = await api_client.post(
        "/projects",
        json={"organization_id": str(org.id), "name": "Doc project"},
        headers=headers,
    )
    project_id = create_response.json()["id"]
    return owner, project_id, headers


async def test_upload_list_get_and_download_document(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _owner, project_id, headers = await _seed_project(
        api_client, db_session_factory, suffix="upload"
    )

    upload_response = await api_client.post(
        f"/projects/{project_id}/documents",
        files={"file": ("notes.txt", b"hello evidence", "text/plain")},
        headers=headers,
    )
    assert upload_response.status_code == 201
    body = upload_response.json()
    assert body["filename"] == "notes.txt"
    assert body["status"] == "uploaded"
    document_id = body["id"]

    list_response = await api_client.get(f"/projects/{project_id}/documents", headers=headers)
    assert len(list_response.json()) == 1

    get_response = await api_client.get(
        f"/projects/{project_id}/documents/{document_id}", headers=headers
    )
    assert get_response.status_code == 200

    download_response = await api_client.get(
        f"/projects/{project_id}/documents/{document_id}/download", headers=headers
    )
    assert download_response.status_code == 200
    assert download_response.content == b"hello evidence"


async def test_upload_rejects_disallowed_content_type(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _owner, project_id, headers = await _seed_project(
        api_client, db_session_factory, suffix="reject"
    )

    response = await api_client.post(
        f"/projects/{project_id}/documents",
        files={"file": ("script.exe", b"MZ...", "application/x-msdownload")},
        headers=headers,
    )
    assert response.status_code == 422


async def test_viewer_cannot_upload_document(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _owner, project_id, owner_headers = await _seed_project(
        api_client, db_session_factory, suffix="viewer"
    )

    async with db_session_factory() as session:
        viewer = await UserRepository(session).create(
            email="doc-viewer@x.com", display_name="Viewer"
        )
        await session.commit()

    await api_client.post(
        f"/projects/{project_id}/members",
        json={"email": "doc-viewer@x.com", "role": "viewer"},
        headers=owner_headers,
    )

    response = await api_client.post(
        f"/projects/{project_id}/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        headers=_auth_headers(viewer.id),
    )
    assert response.status_code == 403


async def test_reupload_creates_new_version(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _owner, project_id, headers = await _seed_project(
        api_client, db_session_factory, suffix="version"
    )

    upload_response = await api_client.post(
        f"/projects/{project_id}/documents",
        files={"file": ("notes.txt", b"v1", "text/plain")},
        headers=headers,
    )
    document_id = upload_response.json()["id"]

    version_response = await api_client.post(
        f"/projects/{project_id}/documents/{document_id}/versions",
        files={"file": ("notes.txt", b"v2", "text/plain")},
        headers=headers,
    )
    assert version_response.status_code == 201

    download_response = await api_client.get(
        f"/projects/{project_id}/documents/{document_id}/download", headers=headers
    )
    assert download_response.content == b"v2"


async def test_document_from_another_project_is_not_found(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    _owner_a, project_a, headers_a = await _seed_project(api_client, db_session_factory, suffix="a")
    _owner_b, project_b, headers_b = await _seed_project(api_client, db_session_factory, suffix="b")

    upload_response = await api_client.post(
        f"/projects/{project_a}/documents",
        files={"file": ("secret.txt", b"confidential", "text/plain")},
        headers=headers_a,
    )
    document_id = upload_response.json()["id"]

    response = await api_client.get(
        f"/projects/{project_b}/documents/{document_id}", headers=headers_b
    )
    assert response.status_code == 404
