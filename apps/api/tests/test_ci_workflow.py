"""Phase 42: CI. This sandbox can't actually run a GitHub Actions
workflow, so — same approach as Phase 39's test_docker_setup.py —
these validate the workflow file's structure: every required job is
present, gated on the right checks, and covers backend lint/typecheck/
tests, frontend lint/typecheck/build, and a Docker build, so main can't
go green without all of them passing.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def _workflow() -> dict:
    with open(REPO_ROOT / ".github" / "workflows" / "ci.yml") as f:
        return yaml.safe_load(f)


def test_workflow_runs_on_push_to_main_and_every_pull_request() -> None:
    workflow = _workflow()
    # PyYAML parses the bare `on:` key as the boolean True under YAML
    # 1.1 (a well-known quirk — GitHub's own parser is unaffected and
    # still reads it as the `on:` trigger key).
    triggers = workflow.get("on") or workflow.get(True)
    assert triggers is not None
    assert triggers["push"]["branches"] == ["main"]
    assert "pull_request" in triggers


def test_workflow_has_every_required_job() -> None:
    workflow = _workflow()
    assert set(workflow["jobs"]) == {"backend", "frontend", "docker", "e2e", "all-checks"}


def test_backend_job_covers_lint_typecheck_and_both_python_packages_tests() -> None:
    workflow = _workflow()
    step_names = [step.get("name", "") for step in workflow["jobs"]["backend"]["steps"]]
    assert any(s == "Ruff check (apps/api)" for s in step_names)
    assert any(s == "Ruff format check (apps/api)" for s in step_names)
    assert any(s == "mypy (apps/api)" for s in step_names)
    assert any(s == "Ruff check (packages/evals)" for s in step_names)
    assert any(s == "mypy (packages/evals)" for s in step_names)
    assert any(s == "pytest (apps/api)" for s in step_names)
    assert any(s == "pytest (packages/evals)" for s in step_names)


def test_frontend_job_covers_lint_typecheck_and_build() -> None:
    workflow = _workflow()
    step_names = [step.get("name", "") for step in workflow["jobs"]["frontend"]["steps"]]
    assert "ESLint" in step_names
    assert "TypeScript" in step_names
    assert "Build" in step_names


def test_docker_job_builds_both_images_and_validates_compose() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["docker"]["steps"]
    dockerfiles = {
        step["with"]["file"] for step in steps if "with" in step and "file" in step["with"]
    }
    assert dockerfiles == {"apps/api/Dockerfile", "apps/web/Dockerfile"}
    step_names = [step.get("name", "") for step in steps]
    assert "Validate docker-compose.yml" in step_names


def test_e2e_job_depends_on_the_other_three_jobs() -> None:
    workflow = _workflow()
    needs = workflow["jobs"]["e2e"]["needs"]
    assert set(needs) == {"backend", "frontend", "docker"}


def test_all_checks_job_fails_if_any_dependency_failed() -> None:
    workflow = _workflow()
    all_checks = workflow["jobs"]["all-checks"]
    assert set(all_checks["needs"]) == {"backend", "frontend", "docker", "e2e"}
    assert all_checks["if"] == "always()"
    run_step = all_checks["steps"][0]["run"]
    assert "failure" in run_step
    assert "exit 1" in run_step
