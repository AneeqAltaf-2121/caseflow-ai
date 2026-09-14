"""Phase 56: demo dataset seeder. scripts/seed_demo.py talks to a real
running API over HTTP, so these tests drive it against an
httpx.MockTransport fake instead of a live server/Docker stack —
exercising the actual request shapes (paths, JSON payloads, polling
loop) without needing infrastructure this test suite doesn't otherwise
depend on.
"""

import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "scripts" / "seed_demo.py"


def _load_seed_demo():
    spec = importlib.util.spec_from_file_location("seed_demo", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_demo"] = module
    spec.loader.exec_module(module)
    return module


seed_demo = _load_seed_demo()


class FakeApi:
    """A minimal in-memory stand-in for the real API's relevant routes.
    Ingestion/evaluation/report all "complete" after a couple of polls,
    the same asynchronous shape the real background jobs have."""

    def __init__(self, *, mock_oauth_enabled: bool = True) -> None:
        self.mock_oauth_enabled = mock_oauth_enabled
        self.projects: list[dict[str, Any]] = []
        self.documents: dict[str, dict[str, Any]] = {}
        self.evaluations: dict[str, dict[str, Any]] = {}
        self.reports: dict[str, dict[str, Any]] = {}
        self._poll_counts: dict[str, int] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method

        if path == "/auth/mock/callback" and method == "GET":
            if not self.mock_oauth_enabled:
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(200, json={"access_token": "fake-token", "refresh_token": "x"})

        if path == "/projects" and method == "GET":
            return httpx.Response(200, json=self.projects)

        if path == "/projects" and method == "POST":
            body = _json(request)
            project = {"id": str(uuid.uuid4()), "name": body["name"]}
            self.projects.append(project)
            return httpx.Response(201, json=project)

        if path.endswith("/documents") and method == "GET":
            return httpx.Response(200, json=list(self.documents.values()))

        if path.endswith("/documents") and method == "POST":
            doc_id = str(uuid.uuid4())
            self.documents[doc_id] = {
                "id": doc_id,
                "filename": "sample-contract.pdf",
                "status": "uploaded",
            }
            return httpx.Response(201, json=self.documents[doc_id])

        if "/documents/" in path and method == "GET":
            doc_id = path.rsplit("/", 1)[-1]
            doc = self.documents[doc_id]
            doc["status"] = self._advance(f"doc:{doc_id}", "processing", "ready")
            return httpx.Response(200, json=doc)

        if path.endswith("/conversations") and method == "POST":
            return httpx.Response(201, json={"id": str(uuid.uuid4())})

        if "/conversations/" in path and path.endswith("/messages") and method == "POST":
            return httpx.Response(
                201,
                json={
                    "user_message": {"id": str(uuid.uuid4())},
                    "assistant_message": {"id": str(uuid.uuid4())},
                    "insufficient_evidence": False,
                    "sources_considered": 1,
                    "model": "mock",
                },
            )

        if path.endswith("/reviews") and method == "POST":
            return httpx.Response(201, json={"id": str(uuid.uuid4())})

        if path.endswith("/evaluations") and method == "POST":
            run_id = str(uuid.uuid4())
            self.evaluations[run_id] = {"id": run_id, "status": "queued"}
            return httpx.Response(201, json=self.evaluations[run_id])

        if "/evaluations/" in path and method == "GET":
            run_id = path.rsplit("/", 1)[-1]
            run = self.evaluations[run_id]
            run["status"] = self._advance(f"eval:{run_id}", "running", "succeeded")
            return httpx.Response(200, json=run)

        if path.endswith("/reports") and method == "POST":
            report_id = str(uuid.uuid4())
            self.reports[report_id] = {"id": report_id, "status": "queued"}
            return httpx.Response(201, json=self.reports[report_id])

        if "/reports/" in path and method == "GET":
            report_id = path.rsplit("/", 1)[-1]
            report = self.reports[report_id]
            report["status"] = self._advance(f"report:{report_id}", "processing", "ready")
            return httpx.Response(200, json=report)

        raise AssertionError(f"Unhandled request: {method} {path}")

    def _advance(self, key: str, pending: str, done: str) -> str:
        """First poll returns `pending`, every poll after that `done` —
        exercises the seeder's polling loop actually looping at least once."""
        count = self._poll_counts.get(key, 0)
        self._poll_counts[key] = count + 1
        return pending if count == 0 else done


def _json(request: httpx.Request) -> dict[str, Any]:
    import json

    return json.loads(request.content)


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_demo, "POLL_INTERVAL_SECONDS", 0.0)


def test_login_raises_a_clear_error_when_mock_oauth_is_disabled() -> None:
    fake = FakeApi(mock_oauth_enabled=False)
    client = seed_demo.DemoClient("http://test", transport=httpx.MockTransport(fake.handler))
    with pytest.raises(seed_demo.SeedError, match="Mock OAuth provider is not available"):
        client.login("demo@example.com")


def test_find_or_create_project_reuses_an_existing_project_by_name() -> None:
    fake = FakeApi()
    client = seed_demo.DemoClient("http://test", transport=httpx.MockTransport(fake.handler))
    client.login("demo@example.com")

    first_id = client.find_or_create_project("Demo Project", "desc")
    second_id = client.find_or_create_project("Demo Project", "desc")

    assert first_id == second_id
    assert len(fake.projects) == 1


def test_poll_until_stops_as_soon_as_is_done_returns_true() -> None:
    calls = iter(["pending", "pending", "done"])
    result = seed_demo._poll_until("thing", lambda: next(calls), lambda s: s == "done")
    assert result == "done"


def test_poll_until_raises_seed_error_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_demo, "POLL_INTERVAL_SECONDS", 0.0)
    with pytest.raises(seed_demo.SeedError, match="Timed out"):
        seed_demo._poll_until(
            "thing that never finishes",
            lambda: "pending",
            lambda s: s == "done",
            timeout=0.01,
        )


def test_seed_runs_end_to_end_against_a_fake_api() -> None:
    fake = FakeApi()
    seed_demo.seed("http://test", "demo@example.com", transport=httpx.MockTransport(fake.handler))

    assert len(fake.projects) == 1
    assert len(fake.documents) == 1
    assert all(doc["status"] == "ready" for doc in fake.documents.values())
    assert len(fake.evaluations) == 1
    assert all(run["status"] == "succeeded" for run in fake.evaluations.values())
    assert len(fake.reports) == 1
    assert all(report["status"] == "ready" for report in fake.reports.values())


def test_readme_documents_the_seed_script() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/seed_demo.py" in readme
    assert seed_demo.DEFAULT_EMAIL in readme


def test_seed_is_safe_to_run_twice_without_duplicating_the_project() -> None:
    fake = FakeApi()
    transport = httpx.MockTransport(fake.handler)
    seed_demo.seed("http://test", "demo@example.com", transport=transport)
    seed_demo.seed("http://test", "demo@example.com", transport=transport)

    assert len(fake.projects) == 1
    # The already-ready document is reused, not re-uploaded...
    assert len(fake.documents) == 1
    # ...but a conversation/evaluation/report is still created each run.
    assert len(fake.evaluations) == 2
    assert len(fake.reports) == 2
