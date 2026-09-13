"""Optional in-process job worker (Phase 41), gated by
`settings.run_inline_worker` (default off).

A real deployment (docker-compose, Phase 39) runs a dedicated `worker`
process against real Redis. Requiring that same separate process just to
run the app at all would undercut this project's "runs with zero
external setup" design (every AI provider already defaults to mock —
see docs/decisions/007/008) — a plain `uvicorn app.main:app`, no Docker,
no Redis, should still be able to actually process background jobs, not
just accept uploads that sit at status=uploaded forever.

dramatiq.Worker spawns its own OS threads and works against *any*
broker instance, including the StubBroker `app.jobs.broker` already is
when `ENVIRONMENT=test` — each worker thread's `asyncio.run()` call
(inside the actor wrapper) gets its own event loop with no conflict
against the main thread's ASGI event loop. This is exactly what Phase
41's Playwright E2E tests run the backend with, so an uploaded document
actually gets processed without a separate worker process or a real
Redis connection.
"""

import dramatiq
import structlog

logger = structlog.get_logger("caseflow.jobs.inline_worker")

_worker: dramatiq.Worker | None = None


def start_inline_worker() -> None:
    global _worker
    if _worker is not None:
        return

    # Importing this registers every actor on the broker, same as the
    # real `dramatiq app.jobs.worker` CLI entrypoint does.
    from app.jobs import broker
    from app.jobs import worker as _  # noqa: F401

    _worker = dramatiq.Worker(broker, worker_threads=2)
    _worker.start()
    logger.info("inline_worker_started")


def stop_inline_worker() -> None:
    global _worker
    if _worker is None:
        return
    _worker.stop()
    _worker = None
    logger.info("inline_worker_stopped")
