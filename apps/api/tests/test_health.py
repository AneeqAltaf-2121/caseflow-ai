from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from app.observability import get_latency_tracker


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_sets_request_id_header(client: TestClient) -> None:
    response = client.get("/health")

    assert "X-Request-ID" in response.headers


def test_ready_returns_503_when_dependencies_unreachable(client: TestClient) -> None:
    # No live Postgres/Redis in the unit test environment, so /ready should
    # report a structured 503 rather than raising an unhandled exception.
    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "dependency_unavailable"
    assert body["error"]["request_id"]


def test_ready_returns_200_when_dependencies_are_healthy(client: TestClient) -> None:
    class FakeResult:
        pass

    class FakeSession:
        async def execute(self, _query: object) -> FakeResult:
            return FakeResult()

    class FakeRedis:
        async def ping(self) -> bool:
            return True

        async def aclose(self) -> None:
            return None

    @asynccontextmanager
    async def fake_session_factory():
        yield FakeSession()

    client.app.state.session_factory = fake_session_factory
    client.app.state.redis_client = FakeRedis()

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok", "redis": "ok"}}


def test_latency_metrics_reports_requests_made_through_the_middleware(
    client: TestClient,
) -> None:
    get_latency_tracker().reset()

    client.get("/health")
    client.get("/health")

    response = client.get("/metrics/latency")

    assert response.status_code == 200
    body = response.json()
    assert "GET /health" in body
    assert body["GET /health"]["count"] == 2
    assert body["GET /health"]["p50_ms"] >= 0
    assert body["GET /health"]["p95_ms"] >= body["GET /health"]["p50_ms"]


def test_latency_metrics_empty_when_no_requests_recorded() -> None:
    get_latency_tracker().reset()
    assert get_latency_tracker().snapshot() == {}
