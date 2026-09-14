#!/usr/bin/env python
"""Phase 56: demo dataset seeder.

Populates a *running* CaseFlow AI instance with realistic demo data
through its public HTTP API — the same API the frontend calls — so a
fresh `docker compose up` (or any dev/demo deployment) has something to
explore immediately instead of an empty dashboard: a demo user, one
project, an uploaded and ingested document, a chat conversation with a
grounded, cited answer, a flagged human review, an evaluation run, and
a generated report.

Usage:

    python scripts/seed_demo.py
    python scripts/seed_demo.py --api-url http://localhost:8000 --email demo@example.com

Requires the target API to have mock OAuth enabled (`ALLOW_MOCK_OAUTH`,
on by default outside production — see app/config.py) since this script
logs in through the mock provider. It will refuse to run against an
instance where the mock provider is disabled, which in practice means
it only ever works against a dev/demo deployment, never production.

Safe to re-run: it looks for a project already named `PROJECT_NAME`
under the demo user (and, within it, an already-ready copy of the
sample document) before creating either one again, so running this
twice against the same instance doesn't pile up duplicate demo
projects or documents. It does still add a new conversation/evaluation
run/report each time, since those are meant to demonstrate activity
over time.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_EMAIL = "demo@caseflow.example"
PROJECT_NAME = "Demo: Acme Supply Agreement"
PROJECT_DESCRIPTION = (
    "A sample vendor supply agreement, seeded for demo purposes — "
    "explore document ingestion, grounded chat, evaluation, and reporting "
    "without uploading anything yourself."
)
SAMPLE_PDF = (
    Path(__file__).resolve().parent.parent
    / "apps"
    / "web"
    / "e2e"
    / "fixtures"
    / "sample-contract.pdf"
)

# Same three questions packages/evals/datasets/sample_contract_qa.json
# expects answers to, so the seeded chat history and the evaluation run
# this script also creates are asking about the same document.
DEMO_QUESTIONS = [
    "When does the agreement terminate?",
    "What is the payment term?",
    "Is there an indemnification clause?",
]

POLL_INTERVAL_SECONDS = 2.0
POLL_TIMEOUT_SECONDS = 60.0


class SeedError(RuntimeError):
    """Raised for any failure that should stop the script with a clear message."""


def _poll_until(
    description: str, fetch: "Any", is_done: "Any", *, timeout: float = POLL_TIMEOUT_SECONDS
) -> Any:
    """Call `fetch()` every POLL_INTERVAL_SECONDS until `is_done(result)`,
    or raise SeedError once `timeout` seconds have passed. Mirrors the
    same bounded-retry shape apps/web's reports/evaluations pages and
    e2e/full-journey.spec.ts use for the same reason: background jobs
    finish on their own time, not synchronously with the request that
    queued them.
    """
    deadline = time.monotonic() + timeout
    result = fetch()
    while not is_done(result):
        if time.monotonic() > deadline:
            raise SeedError(f"Timed out waiting for {description}.")
        time.sleep(POLL_INTERVAL_SECONDS)
        result = fetch()
    return result


class DemoClient:
    """Thin wrapper over the public HTTP API — every method mirrors one
    endpoint apps/web/lib/api.ts also calls, so this script exercises
    the same surface a real user's browser does."""

    def __init__(self, api_url: str, *, transport: httpx.BaseTransport | None = None) -> None:
        # `transport` is only ever overridden by tests (httpx.MockTransport)
        # — production always uses the real network transport.
        self._http = httpx.Client(base_url=api_url, timeout=30.0, transport=transport)
        self._token: str | None = None

    def _headers(self) -> dict[str, str]:
        if not self._token:
            raise SeedError("Not logged in yet.")
        return {"Authorization": f"Bearer {self._token}"}

    def login(self, email: str) -> None:
        response = self._http.get(f"/auth/mock/callback?code={email}")
        if response.status_code == 404:
            raise SeedError(
                "Mock OAuth provider is not available on this instance "
                "(ALLOW_MOCK_OAUTH is off, or this is a production deployment) — "
                "seed_demo.py only works against a dev/demo instance."
            )
        response.raise_for_status()
        self._token = response.json()["access_token"]

    def find_or_create_project(self, name: str, description: str) -> str:
        existing = self._http.get("/projects", headers=self._headers())
        existing.raise_for_status()
        for project in existing.json():
            if project["name"] == name:
                return project["id"]

        response = self._http.post(
            "/projects",
            json={"name": name, "description": description},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    def find_document_by_filename(self, project_id: str, filename: str) -> dict[str, Any] | None:
        response = self._http.get(f"/projects/{project_id}/documents", headers=self._headers())
        response.raise_for_status()
        for document in response.json():
            if document["filename"] == filename:
                return document
        return None

    def upload_document(self, project_id: str, path: Path) -> str:
        with path.open("rb") as f:
            response = self._http.post(
                f"/projects/{project_id}/documents",
                files={"file": (path.name, f, "application/pdf")},
                headers=self._headers(),
            )
        response.raise_for_status()
        return response.json()["id"]

    def get_document_status(self, project_id: str, document_id: str) -> str:
        response = self._http.get(
            f"/projects/{project_id}/documents/{document_id}", headers=self._headers()
        )
        response.raise_for_status()
        return response.json()["status"]

    def create_conversation(self, project_id: str, title: str) -> str:
        response = self._http.post(
            f"/projects/{project_id}/conversations",
            json={"title": title},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    def ask(self, project_id: str, conversation_id: str, question: str) -> dict[str, Any]:
        response = self._http.post(
            f"/projects/{project_id}/conversations/{conversation_id}/messages",
            json={"content": question},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()

    def flag_for_review(self, project_id: str, message_id: str) -> None:
        response = self._http.post(
            f"/projects/{project_id}/reviews",
            json={"message_id": message_id},
            headers=self._headers(),
        )
        response.raise_for_status()

    def create_evaluation_run(self, project_id: str, dataset_name: str) -> str:
        response = self._http.post(
            f"/projects/{project_id}/evaluations",
            json={"dataset_name": dataset_name},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    def get_evaluation_status(self, project_id: str, run_id: str) -> str:
        response = self._http.get(
            f"/projects/{project_id}/evaluations/{run_id}", headers=self._headers()
        )
        response.raise_for_status()
        return response.json()["status"]

    def create_report(self, project_id: str, report_type: str, title: str) -> str:
        response = self._http.post(
            f"/projects/{project_id}/reports",
            json={"report_type": report_type, "title": title},
            headers=self._headers(),
        )
        response.raise_for_status()
        return response.json()["id"]

    def get_report_status(self, project_id: str, report_id: str) -> str:
        response = self._http.get(
            f"/projects/{project_id}/reports/{report_id}", headers=self._headers()
        )
        response.raise_for_status()
        return response.json()["status"]


def seed(
    api_url: str, email: str, *, transport: httpx.BaseTransport | None = None
) -> None:
    if not SAMPLE_PDF.is_file():
        raise SeedError(f"Sample document not found at {SAMPLE_PDF}.")

    client = DemoClient(api_url, transport=transport)

    print(f"Logging in as {email} (mock OAuth)...")
    client.login(email)

    print(f'Finding or creating project "{PROJECT_NAME}"...')
    project_id = client.find_or_create_project(PROJECT_NAME, PROJECT_DESCRIPTION)
    print(f"  project_id={project_id}")

    existing_document = client.find_document_by_filename(project_id, SAMPLE_PDF.name)
    if existing_document is not None and existing_document["status"] == "ready":
        print(f"{SAMPLE_PDF.name} already uploaded and ready — reusing it.")
        document_id = existing_document["id"]
    else:
        print(f"Uploading {SAMPLE_PDF.name}...")
        document_id = client.upload_document(project_id, SAMPLE_PDF)
        print("  Waiting for ingestion to finish (needs a running worker)...")
        status = _poll_until(
            "document ingestion",
            lambda: client.get_document_status(project_id, document_id),
            lambda s: s in ("ready", "failed"),
        )
        if status != "ready":
            raise SeedError(f"Document ingestion ended in status {status!r}, expected 'ready'.")
        print("  document status=ready")

    print("Creating a chat conversation...")
    conversation_id = client.create_conversation(project_id, "Contract Q&A")
    first_flagged_message_id: str | None = None
    for question in DEMO_QUESTIONS:
        print(f'  Asking: "{question}"')
        result = client.ask(project_id, conversation_id, question)
        if first_flagged_message_id is None:
            first_flagged_message_id = result["assistant_message"]["id"]

    if first_flagged_message_id is not None:
        print("Flagging the first answer for human review...")
        client.flag_for_review(project_id, first_flagged_message_id)

    print("Starting an evaluation run against sample_contract_qa...")
    run_id = client.create_evaluation_run(project_id, "sample_contract_qa")
    eval_status = _poll_until(
        "evaluation run",
        lambda: client.get_evaluation_status(project_id, run_id),
        lambda s: s in ("succeeded", "failed"),
    )
    print(f"  evaluation status={eval_status}")

    print("Generating an executive summary report...")
    report_id = client.create_report(project_id, "executive_summary", "Executive Summary")
    report_status = _poll_until(
        "report generation",
        lambda: client.get_report_status(project_id, report_id),
        lambda s: s in ("ready", "failed"),
    )
    print(f"  report status={report_status}")

    print()
    print("Demo data seeded successfully:")
    print(f"  - Log in at the frontend as {email} (mock OAuth) to explore it")
    print(f"  - Project: {PROJECT_NAME}")
    print("  - 1 document, 1 conversation (3 questions), 1 flagged review,")
    print("    1 evaluation run, 1 report")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help=f"default: {DEFAULT_API_URL}")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help=f"default: {DEFAULT_EMAIL}")
    args = parser.parse_args()

    try:
        seed(args.api_url, args.email)
    except SeedError as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as err:
        print(
            f"error: {err.request.method} {err.request.url} -> {err.response.status_code}",
            file=sys.stderr,
        )
        print(err.response.text, file=sys.stderr)
        return 1
    except httpx.ConnectError as err:
        print(
            f"error: could not reach {args.api_url} ({err}) — is the stack running?",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
