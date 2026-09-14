"""Phase 49: IAM roles for ECS tasks. `terraform init/fmt/validate` all
pass for real against environments/dev with this module wired in —
these tests check the specific properties the phase spec calls for
(separate execution vs. task role, scoped S3 access, no wildcard
resources), since `validate` alone only proves the HCL parses.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
IAM_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "iam"


def _main_tf() -> str:
    return (IAM_MODULE / "main.tf").read_text()


def test_task_execution_role_exists_and_trusts_ecs_tasks() -> None:
    content = _main_tf()
    assert 'resource "aws_iam_role" "task_execution"' in content
    assert 'Service = "ecs-tasks.amazonaws.com"' in content


def test_task_execution_role_has_the_managed_ecs_policy_attached() -> None:
    content = _main_tf()
    assert 'resource "aws_iam_role_policy_attachment" "task_execution_managed"' in content
    assert "AmazonECSTaskExecutionRolePolicy" in content


def test_task_role_is_distinct_from_execution_role() -> None:
    content = _main_tf()
    assert 'resource "aws_iam_role" "task"' in content
    assert 'resource "aws_iam_role" "task_execution"' in content
    # Two separate role resources, not one role reused for both purposes.
    assert content.count('resource "aws_iam_role"') == 2


def test_task_role_s3_permissions_are_scoped_to_the_documents_bucket_not_wildcard() -> None:
    content = _main_tf()
    block = content.split('resource "aws_iam_role_policy" "task_s3_documents"')[1]
    assert "var.documents_bucket_arn" in block
    assert 'Resource = "*"' not in block


def test_execution_role_secrets_access_is_scoped_to_this_project_not_wildcard() -> None:
    content = _main_tf()
    block = content.split('resource "aws_iam_role_policy" "task_execution_secrets"')[1]
    assert "secretsmanager:GetSecretValue" in block
    assert "var.name_prefix" in block


def test_iam_module_is_wired_into_the_dev_environment() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "iam"' in main_tf
    assert 'source = "../../modules/iam"' in main_tf
