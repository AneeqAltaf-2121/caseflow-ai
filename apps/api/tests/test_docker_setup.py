"""Phase 39: Dockerizing every service. This sandbox has no Docker
daemon (see docs/decisions on IaC/environment constraints elsewhere in
this project), so these tests validate structure — every expected
service, health check, and dependency ordering is actually present in
docker-compose.yml and both Dockerfiles — rather than actually building
or running containers.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def _compose() -> dict:
    with open(REPO_ROOT / "docker-compose.yml") as f:
        return yaml.safe_load(f)


def test_compose_file_is_valid_yaml_with_every_expected_service() -> None:
    compose = _compose()
    assert set(compose["services"]) == {"postgres", "redis", "migrate", "api", "worker", "web"}


def test_postgres_and_redis_have_health_checks() -> None:
    compose = _compose()
    assert "healthcheck" in compose["services"]["postgres"]
    assert "healthcheck" in compose["services"]["redis"]


def test_api_and_web_have_health_checks_but_worker_does_not() -> None:
    """Worker doesn't serve HTTP — no meaningful HTTP health check for
    it (documented in docker-compose.yml's comment on that service). api
    and web get theirs from their Dockerfile's HEALTHCHECK instruction
    (not repeated in compose), so check the Dockerfiles for it."""
    compose = _compose()
    api_dockerfile = (REPO_ROOT / "apps" / "api" / "Dockerfile").read_text()
    web_dockerfile = (REPO_ROOT / "apps" / "web" / "Dockerfile").read_text()
    assert "HEALTHCHECK" in api_dockerfile
    assert "HEALTHCHECK" in web_dockerfile
    assert compose["services"]["worker"]["command"][0] == "dramatiq"


def test_migrate_runs_before_api_and_worker_start() -> None:
    compose = _compose()
    for service_name in ("api", "worker"):
        depends_on = compose["services"][service_name]["depends_on"]
        assert depends_on["migrate"]["condition"] == "service_completed_successfully"
        assert depends_on["postgres"]["condition"] == "service_healthy"
        assert depends_on["redis"]["condition"] == "service_healthy"


def test_migrate_runs_alembic_upgrade_head() -> None:
    compose = _compose()
    assert compose["services"]["migrate"]["command"] == ["alembic", "upgrade", "head"]


def test_web_waits_for_api_to_be_healthy() -> None:
    compose = _compose()
    depends_on = compose["services"]["web"]["depends_on"]
    assert depends_on["api"]["condition"] == "service_healthy"


def test_api_worker_and_web_all_have_build_contexts() -> None:
    compose = _compose()
    for service_name in ("migrate", "api", "worker", "web"):
        build = compose["services"][service_name]["build"]
        # Build context is the repo root — both images need files from
        # outside their own app directory (packages/evals for the
        # backend image; nothing outside apps/web today, but kept
        # consistent so both Dockerfiles are invoked the same way).
        assert build["context"] == "."


def test_api_and_worker_share_the_same_dockerfile() -> None:
    compose = _compose()
    assert (
        compose["services"]["api"]["build"]["dockerfile"]
        == compose["services"]["worker"]["build"]["dockerfile"]
        == compose["services"]["migrate"]["build"]["dockerfile"]
        == "apps/api/Dockerfile"
    )


def test_storage_volume_is_shared_between_api_and_worker() -> None:
    """Documents are uploaded via the API and read back by the worker
    during ingestion — both need the same on-disk storage."""
    compose = _compose()
    api_volumes = compose["services"]["api"]["volumes"]
    worker_volumes = compose["services"]["worker"]["volumes"]
    assert any("caseflow_storage" in v for v in api_volumes)
    assert any("caseflow_storage" in v for v in worker_volumes)


def test_backend_dockerfile_installs_both_packages() -> None:
    dockerfile = (REPO_ROOT / "apps" / "api" / "Dockerfile").read_text()
    assert "packages/evals" in dockerfile
    assert "apps/api" in dockerfile
    assert "EXPOSE 8000" in dockerfile


def test_frontend_dockerfile_uses_standalone_output() -> None:
    dockerfile = (REPO_ROOT / "apps" / "web" / "Dockerfile").read_text()
    assert ".next/standalone" in dockerfile
    assert "EXPOSE 3000" in dockerfile
    next_config = (REPO_ROOT / "apps" / "web" / "next.config.ts").read_text()
    assert 'output: "standalone"' in next_config


def test_dockerignore_excludes_heavy_local_directories() -> None:
    dockerignore = (REPO_ROOT / ".dockerignore").read_text()
    for pattern in ("node_modules", ".venv", ".git", "__pycache__", ".next"):
        assert pattern in dockerignore
