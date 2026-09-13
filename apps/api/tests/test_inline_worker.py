"""Phase 41: the optional in-process worker (app/jobs/inline_worker.py).

Doesn't exercise a job actually completing end-to-end here — that needs
a real DATABASE_URL the module-level `get_settings()` singleton reads at
job-run time (the same production code path a real deployment uses),
which pytest's in-memory SQLite fixtures deliberately don't touch. That
full proof — an uploaded document actually reaching READY with a plain
`uvicorn app.main:app` and no separate worker process or real Redis —
is what Phase 41's Playwright E2E suite runs against instead. This file
covers the lifecycle contract: starting registers every actor and is
idempotent, stopping tears it down cleanly.
"""

from app.jobs import broker
from app.jobs.inline_worker import start_inline_worker, stop_inline_worker


def test_start_inline_worker_registers_every_actor() -> None:
    try:
        start_inline_worker()
        declared = broker.get_declared_actors()
        assert "process_document_job" in declared
        assert "generate_report_job" in declared
        assert "run_evaluation_job" in declared
    finally:
        stop_inline_worker()


def test_start_inline_worker_is_idempotent() -> None:
    try:
        start_inline_worker()
        start_inline_worker()  # must not raise or start a second worker
    finally:
        stop_inline_worker()


def test_stop_inline_worker_without_starting_is_a_no_op() -> None:
    stop_inline_worker()  # must not raise
