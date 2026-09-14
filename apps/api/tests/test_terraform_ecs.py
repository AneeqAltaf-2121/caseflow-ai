"""Phase 49: ECS/Fargate IaC. `terraform init/fmt/validate` all pass for
real against environments/dev with this module wired in — these tests
check the specific properties the phase spec calls for (cluster, three
task definitions sharing api/worker's image with different commands,
three services, task roles, container logs), since `validate` alone
only proves the HCL parses.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ECS_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "ecs"


def _main_tf() -> str:
    return (ECS_MODULE / "main.tf").read_text()


def test_cluster_is_declared_with_container_insights() -> None:
    content = _main_tf()
    assert 'resource "aws_ecs_cluster" "this"' in content
    assert 'name  = "containerInsights"' in content
    assert 'value = "enabled"' in content


def test_all_three_services_have_task_definitions() -> None:
    content = _main_tf()
    for service in ("api", "worker", "web"):
        assert f'resource "aws_ecs_task_definition" "{service}"' in content
        assert f'resource "aws_ecs_service" "{service}"' in content


def test_api_and_worker_share_the_same_image_with_different_commands() -> None:
    content = _main_tf()
    api_block = content.split('resource "aws_ecs_task_definition" "api"')[1].split(
        'resource "aws_ecs_service" "api"'
    )[0]
    worker_block = content.split('resource "aws_ecs_task_definition" "worker"')[1].split(
        'resource "aws_ecs_service" "worker"'
    )[0]

    # Both reference the same shared image variable...
    assert "var.api_image" in api_block
    assert "var.api_image" in worker_block
    # ...but only the worker overrides the container command.
    assert "command" not in api_block
    assert "command   = var.worker_command" in worker_block


def test_web_uses_its_own_image_not_the_shared_api_image() -> None:
    content = _main_tf()
    web_block = content.split('resource "aws_ecs_task_definition" "web"')[1].split(
        'resource "aws_ecs_service" "web"'
    )[0]
    assert "var.web_image" in web_block
    assert "var.api_image" not in web_block


def test_task_definitions_reference_the_iam_module_roles() -> None:
    content = _main_tf()
    assert "execution_role_arn       = var.task_execution_role_arn" in content
    assert "task_role_arn            = var.task_role_arn" in content


def test_every_task_definition_ships_logs_to_its_own_log_group() -> None:
    content = _main_tf()
    for service in ("api", "worker", "web"):
        assert f'resource "aws_cloudwatch_log_group" "{service}"' in content
        assert f"aws_cloudwatch_log_group.{service}.name" in content


def test_tasks_run_on_fargate_in_private_subnets_with_no_public_ip() -> None:
    content = _main_tf()
    assert content.count('requires_compatibilities = ["FARGATE"]') == 3
    assert content.count('launch_type     = "FARGATE"') == 3
    assert content.count("assign_public_ip = false") == 3
    assert content.count("subnets          = var.private_subnet_ids") == 3


def test_ecs_module_is_wired_into_the_dev_environment_with_iam_roles() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "ecs"' in main_tf
    assert 'source = "../../modules/ecs"' in main_tf
    assert "task_execution_role_arn = module.iam.task_execution_role_arn" in main_tf
    assert "task_role_arn           = module.iam.task_role_arn" in main_tf
