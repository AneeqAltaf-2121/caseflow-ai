"""Phase 54: deployment documentation. docs/deployment.md is prose, not
code, so these tests only pin down the facts in it that could silently
drift out of sync with the actual Terraform/Docker setup — the status
disclaimer, and that every AWS resource name/default it walks through
(secret names, image variable defaults, the migrate task) is one that
actually exists in infra/aws/.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _deployment_md() -> str:
    return (REPO_ROOT / "docs" / "deployment.md").read_text()


def test_deployment_doc_exists_and_states_no_live_environment() -> None:
    content = _deployment_md()
    assert "No live environment exists" in content
    assert "never been run against a real AWS account" in content


def test_local_development_section_matches_the_real_docker_compose_command() -> None:
    content = _deployment_md()
    assert "docker compose up --build" in content


def test_aws_section_references_the_architecture_adr() -> None:
    content = _deployment_md()
    assert "010-aws-architecture.md" in content


def test_aws_section_walks_through_the_migrate_one_shot_task() -> None:
    content = _deployment_md()
    assert "aws ecs run-task" in content
    assert "migrate" in content


def test_secret_names_referenced_in_the_doc_match_the_secrets_module() -> None:
    content = _deployment_md()
    secrets_main_tf = (REPO_ROOT / "infra" / "aws" / "modules" / "secrets" / "main.tf").read_text()
    for suffix in ("oauth-client-secret", "anthropic-api-key", "openai-api-key"):
        doc_name = f"caseflow-ai-dev-{suffix}"
        assert doc_name in content
        assert f'"${{var.name_prefix}}-{suffix}"' in secrets_main_tf


def test_doc_mentions_subscribing_the_alerts_topic_from_observability_module() -> None:
    content = _deployment_md()
    assert "sns subscribe" in content
    assert "alerts_topic_arn" in content


def test_alb_routing_diagram_matches_the_apis_real_route_prefixes_not_slash_api() -> None:
    # Phase 59: the original diagram said "/api/*", which matches nothing
    # — apps/api's routes carry no "/api" prefix (app/api/router.py's
    # APIRouter() takes none). Locks the doc to the corrected prefixes so
    # it can't silently drift from infra/aws/modules/alb/main.tf again.
    content = _deployment_md()
    assert "/api/*" not in content
    assert "/health, /ready, /auth/*, /projects/*" in content

    alb_main_tf = (REPO_ROOT / "infra" / "aws" / "modules" / "alb" / "main.tf").read_text()
    assert 'values = ["/health", "/ready", "/auth/*", "/projects/*"]' in alb_main_tf
