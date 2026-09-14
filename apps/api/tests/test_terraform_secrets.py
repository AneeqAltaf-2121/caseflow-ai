"""Phase 51: Secrets Manager IaC. `terraform init/fmt/validate` all pass
for real against environments/dev with this module wired in — these
tests check the specific properties the phase spec calls for (OAuth
secret, LLM API credentials, an app secret, no literal secret values
anywhere in Terraform), since `validate` alone only proves the HCL
parses.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SECRETS_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "secrets"


def _main_tf() -> str:
    return (SECRETS_MODULE / "main.tf").read_text()


def test_oauth_client_secret_container_is_declared() -> None:
    content = _main_tf()
    assert 'resource "aws_secretsmanager_secret" "oauth_client_secret"' in content


def test_llm_api_key_containers_are_declared_for_both_providers() -> None:
    content = _main_tf()
    assert 'resource "aws_secretsmanager_secret" "anthropic_api_key"' in content
    assert 'resource "aws_secretsmanager_secret" "openai_api_key"' in content


def test_externally_issued_secrets_have_no_version_populated_by_terraform() -> None:
    # OAuth and LLM credentials come from a third party — Terraform must
    # never invent or store a literal value for them.
    content = _main_tf()
    for secret in ("oauth_client_secret", "anthropic_api_key", "openai_api_key"):
        assert f'resource "aws_secretsmanager_secret_version" "{secret}"' not in content


def test_app_secret_is_generated_by_terraform_not_hardcoded() -> None:
    content = _main_tf()
    assert 'resource "random_password" "jwt_secret_key"' in content
    assert 'resource "aws_secretsmanager_secret_version" "jwt_secret_key"' in content
    assert "random_password.jwt_secret_key.result" in content


def test_no_literal_secret_string_is_ever_assigned_in_the_module() -> None:
    content = _main_tf()
    # The only secret_string assignment must come from the generated
    # random_password resource, never a quoted literal.
    assert 'secret_string = "' not in content


def test_random_provider_is_declared_for_this_module() -> None:
    content = _main_tf()
    assert 'source  = "hashicorp/random"' in content


def test_secrets_module_is_wired_into_the_dev_environment() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "secrets"' in main_tf
    assert 'source = "../../modules/secrets"' in main_tf


def test_ecs_containers_inject_secrets_via_arn_not_literal_values() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    for name in (
        "OAUTH_CLIENT_SECRET",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "JWT_SECRET_KEY",
    ):
        assert name in main_tf
    assert "module.secrets.oauth_client_secret_arn" in main_tf
    assert "module.secrets.jwt_secret_key_arn" in main_tf
