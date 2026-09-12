"""Phase 38: security hardening — malicious filename handling and a
resource-level authorization sweep across resource types not already
covered by a dedicated cross-project test elsewhere. Rate limiting has
its own file (test_rate_limit.py); CORS is exercised structurally by
every api_client test hitting the real CORSMiddleware-wrapped app.
"""

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt import create_access_token
from app.config import get_settings
from app.repositories.organization_repository import OrganizationRepository
from app.repositories.user_repository import UserRepository
from app.services.document_service import sanitize_filename


def _auth_headers(user_id: uuid.UUID) -> dict[str, str]:
    token = create_access_token(user_id=user_id, settings=get_settings())
    return {"Authorization": f"Bearer {token}"}


def test_sanitize_filename_strips_path_separators() -> None:
    traversal = sanitize_filename("../../etc/passwd")
    assert "/" not in traversal
    assert not traversal.startswith("..")
    assert "/" not in sanitize_filename("a/b/c.txt")
    assert "\\" not in sanitize_filename("a\\b\\c.txt")


def test_sanitize_filename_strips_control_characters_and_quotes() -> None:
    malicious = 'evidence".pdf\r\nX-Injected-Header: 1'
    cleaned = sanitize_filename(malicious)
    assert "\r" not in cleaned
    assert "\n" not in cleaned
    assert '"' not in cleaned


def test_sanitize_filename_never_returns_empty() -> None:
    assert sanitize_filename("") == "untitled"
    assert sanitize_filename("...") == "untitled"
    # Quotes are replaced (not stripped to nothing), so this is legitimately
    # non-empty — a safe, if ugly, filename rather than a bare "untitled".
    assert sanitize_filename('"""') == "___"


async def test_upload_with_malicious_filename_is_sanitized_end_to_end(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="sec@x.com", display_name="Sec")
        org = await OrganizationRepository(session).create(name="Sec", slug="sec-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_id = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "Security"}, headers=headers
        )
    ).json()["id"]

    malicious_filename = 'evidence".txt\r\nX-Injected: 1'
    upload_response = await api_client.post(
        f"/projects/{project_id}/documents",
        files={"file": (malicious_filename, b"hello", "text/plain")},
        headers=headers,
    )
    assert upload_response.status_code == 201
    stored_filename = upload_response.json()["filename"]
    assert "\r" not in stored_filename
    assert "\n" not in stored_filename
    assert '"' not in stored_filename

    document_id = upload_response.json()["id"]
    download_response = await api_client.get(
        f"/projects/{project_id}/documents/{document_id}/download", headers=headers
    )
    assert download_response.status_code == 200
    disposition = download_response.headers["content-disposition"]
    # A well-formed single header value with no injected second header —
    # httpx would have folded an injected header into this same string
    # only if raw CRLF had survived into the response, which it can't
    # (sanitize_filename already stripped it, and _content_disposition
    # escapes quotes/backslashes and percent-encodes filename* besides).
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "X-Injected" not in download_response.headers


async def test_conversation_from_another_project_is_not_reachable(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="sec2@x.com", display_name="Sec2")
        org = await OrganizationRepository(session).create(name="Sec2", slug="sec2-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_a = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "A"}, headers=headers
        )
    ).json()["id"]
    project_b = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "B"}, headers=headers
        )
    ).json()["id"]

    conversation_id = (
        await api_client.post(f"/projects/{project_a}/conversations", json={}, headers=headers)
    ).json()["id"]

    # The conversation belongs to project_a — reached through project_b's
    # URL, it must not resolve.
    cross_response = await api_client.get(
        f"/projects/{project_b}/conversations/{conversation_id}", headers=headers
    )
    assert cross_response.status_code == 404


async def test_report_from_another_project_is_not_reachable(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="sec3@x.com", display_name="Sec3")
        org = await OrganizationRepository(session).create(name="Sec3", slug="sec3-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_a = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "A"}, headers=headers
        )
    ).json()["id"]
    project_b = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "B"}, headers=headers
        )
    ).json()["id"]

    report_id = (
        await api_client.post(
            f"/projects/{project_a}/reports",
            json={"report_type": "executive_summary", "title": "A's report"},
            headers=headers,
        )
    ).json()["id"]

    cross_response = await api_client.get(
        f"/projects/{project_b}/reports/{report_id}", headers=headers
    )
    assert cross_response.status_code == 404


async def test_evaluation_run_from_another_project_is_not_reachable(
    api_client: httpx.AsyncClient, db_session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with db_session_factory() as session:
        owner = await UserRepository(session).create(email="sec4@x.com", display_name="Sec4")
        org = await OrganizationRepository(session).create(name="Sec4", slug="sec4-corp")
        await session.commit()
    headers = _auth_headers(owner.id)

    project_a = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "A"}, headers=headers
        )
    ).json()["id"]
    project_b = (
        await api_client.post(
            "/projects", json={"organization_id": str(org.id), "name": "B"}, headers=headers
        )
    ).json()["id"]

    run_id = (
        await api_client.post(
            f"/projects/{project_a}/evaluations",
            json={"dataset_name": "sample_contract_qa"},
            headers=headers,
        )
    ).json()["id"]

    cross_response = await api_client.get(
        f"/projects/{project_b}/evaluations/{run_id}", headers=headers
    )
    assert cross_response.status_code == 404


async def test_unauthenticated_request_is_rejected(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/projects")
    assert response.status_code == 401


async def test_forged_token_is_rejected(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get(
        "/projects", headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert response.status_code == 401
