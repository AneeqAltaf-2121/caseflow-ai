"""Phase 50: ALB IaC. `terraform init/fmt/validate` all pass for real
against environments/dev with this module wired in — these tests check
the specific properties the phase spec calls for (ALB, target groups,
listener, health checks via /health and /ready), since `validate` alone
only proves the HCL parses.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
ALB_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "alb"


def _main_tf() -> str:
    return (ALB_MODULE / "main.tf").read_text()


def test_alb_is_internet_facing_in_the_public_subnets() -> None:
    content = _main_tf()
    assert 'resource "aws_lb" "this"' in content
    assert "internal           = false" in content
    assert "subnets            = var.public_subnet_ids" in content


def test_api_and_web_each_get_their_own_target_group_using_ip_targets() -> None:
    content = _main_tf()
    for tg in ("api", "web"):
        block = content.split(f'resource "aws_lb_target_group" "{tg}"')[1].split("resource")[0]
        assert 'target_type = "ip"' in block  # required for awsvpc Fargate tasks


def test_api_target_group_health_check_uses_the_ready_endpoint() -> None:
    content = _main_tf()
    block = content.split('resource "aws_lb_target_group" "api"')[1].split(
        'resource "aws_lb_target_group" "web"'
    )[0]
    assert 'path                = "/ready"' in block


def test_web_target_group_health_check_uses_root_path() -> None:
    content = _main_tf()
    block = content.split('resource "aws_lb_target_group" "web"')[1]
    assert 'path                = "/"' in block


def test_listener_forwards_to_web_by_default_and_api_under_slash_api() -> None:
    content = _main_tf()
    assert 'resource "aws_lb_listener" "http"' in content
    assert "target_group_arn = aws_lb_target_group.web.arn" in content
    assert 'resource "aws_lb_listener_rule" "api"' in content
    assert "target_group_arn = aws_lb_target_group.api.arn" in content
    assert 'values = ["/api/*"]' in content


def test_alb_module_is_wired_into_the_dev_environment() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "alb"' in main_tf
    assert 'source = "../../modules/alb"' in main_tf


def test_ecs_services_are_wired_to_the_alb_target_groups_in_dev() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert "api_target_group_arn    = module.alb.api_target_group_arn" in main_tf
    assert "web_target_group_arn    = module.alb.web_target_group_arn" in main_tf
