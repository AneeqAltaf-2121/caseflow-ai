"""Background job infrastructure (see docs/decisions/003-job-queue.md).

Importing this package sets the process-wide Dramatiq broker as a side
effect, *before* any actor module (ingestion.py, ...) is imported and
declares its `@dramatiq.actor`s — Dramatiq resolves an actor's broker from
whatever is globally current at decoration time, so ordering matters.
Every actor module must therefore be imported as `app.jobs.<name>`, never
by reaching into the module directly, so this file always runs first.

`ENVIRONMENT=test` gets an in-memory StubBroker instead of a real Redis
connection, so the full enqueue path is exercised in tests without a
broker running — see tests/conftest.py.
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker

from app.config import get_settings


def _create_broker() -> dramatiq.Broker:
    settings = get_settings()
    if settings.environment == "test":
        return StubBroker()
    return RedisBroker(url=settings.redis_url)


broker = _create_broker()
dramatiq.set_broker(broker)
