"""Dramatiq worker entrypoint.

Run with: dramatiq app.jobs.worker

Importing this module registers every actor (evaluation runs land in a
later phase) on the broker configured in app/jobs/__init__.py. It has no
code of its own — it exists purely as the CLI's import target, one place
that pulls in every actor module.
"""

from app.jobs import (
    ingestion,  # noqa: F401
    reports,  # noqa: F401
)
