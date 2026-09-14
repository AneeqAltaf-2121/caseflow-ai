"""Phase 59: documentation accuracy pass. README.md had drifted badly —
written around Phase 3-4, never updated as the other 54 phases landed,
still describing auth as "in progress" and RAG/evaluation/frontend/AWS
as "planned" long after they shipped. These tests pin down that the
stale claims are gone and the repository layout it documents matches
what's actually on disk, so this can't silently rot again the same way.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _readme() -> str:
    return (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_readme_no_longer_claims_only_phases_0_to_3_are_done() -> None:
    content = _readme()
    assert "currently under development" not in content.lower()
    assert "current focus is authentication and authorization" not in content.lower()
    assert "12 tests passing" not in content
    assert "v1.0.0" in content


def test_readme_does_not_describe_rag_or_evaluation_as_merely_planned() -> None:
    content = _readme()
    assert "will be added incrementally as their corresponding phases" not in content
    assert "planned evaluation dimensions" not in content.lower()
    assert "later phases will introduce" not in content.lower()


def test_readme_repository_tree_matches_what_actually_exists_on_disk() -> None:
    content = _readme()
    # infra/docker was an empty placeholder never actually used (the
    # Dockerfiles live in apps/api and apps/web) — removed in Phase 59;
    # the README must not claim it still holds container configuration.
    assert not (REPO_ROOT / "infra" / "docker").exists()
    assert "infra/docker" not in content
    assert (REPO_ROOT / "docs" / "deployment.md").exists()
    assert "docs/deployment.md" in content or "deployment.md" in content
    assert (REPO_ROOT / "docs" / "benchmarks.md").exists()
    assert (REPO_ROOT / "scripts" / "seed_demo.py").exists()
    assert (REPO_ROOT / "scripts" / "benchmark.py").exists()


def test_readme_frontend_development_section_exists() -> None:
    content = _readme()
    assert "## Frontend Development" in content
    assert "npm run dev" in content


def test_readme_ci_badge_points_at_the_real_repo() -> None:
    content = _readme()
    assert "AneeqAltaf-2121/caseflow-ai/actions/workflows/ci.yml" in content
