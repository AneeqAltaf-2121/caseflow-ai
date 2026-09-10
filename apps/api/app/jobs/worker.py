"""Dramatiq worker entrypoint.

Run with: dramatiq app.jobs.worker

Importing this module registers every actor (just ingestion for now;
reports/evaluations land in later phases) on the broker configured in
app/jobs/__init__.py. It has no code of its own — it exists purely as the
CLI's import target, one place that pulls in every actor module.
"""

from app.jobs import ingestion  # noqa: F401
