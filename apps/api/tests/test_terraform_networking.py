"""Phase 45: AWS networking IaC. Verified for real in this session —
`terraform init`, `fmt -check`, and `validate` all pass against
infra/aws/environments/dev with the networking module wired in. These
tests check the specific security posture the phase spec calls for
(ALB public, everything else private) is actually encoded, since a
passing `terraform validate` only proves the syntax is well-formed, not
that the security groups are wired the way this phase intends.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
NETWORKING_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "networking"


def _main_tf() -> str:
    return (NETWORKING_MODULE / "main.tf").read_text()


def test_module_declares_public_and_private_subnets() -> None:
    content = _main_tf()
    assert 'resource "aws_subnet" "public"' in content
    assert 'resource "aws_subnet" "private"' in content
    assert "map_public_ip_on_launch = true" in content


def test_private_subnets_route_outbound_through_nat_not_the_internet_gateway() -> None:
    content = _main_tf()
    assert 'resource "aws_nat_gateway"' in content
    # The private route table's default route points at a NAT gateway,
    # not aws_internet_gateway.this — only the public route table does.
    private_route_table = content.split('resource "aws_route_table" "private"')[1].split(
        "resource"
    )[0]
    assert "nat_gateway_id" in private_route_table
    # The internet-gateway route's exact line ("gateway_id = aws_internet_
    # gateway...") only ever appears in the public route table — a plain
    # "gateway_id" substring check would false-positive against
    # "nat_gateway_id" (which contains it as a suffix).
    assert "gateway_id = aws_internet_gateway.this.id" not in private_route_table


def test_alb_security_group_allows_inbound_from_the_internet() -> None:
    content = _main_tf()
    alb_sg = content.split('resource "aws_security_group" "alb"')[1].split(
        'resource "aws_security_group"'
    )[0]
    assert '"0.0.0.0/0"' in alb_sg


def test_ecs_security_group_only_allows_inbound_from_the_alb() -> None:
    content = _main_tf()
    ecs_sg = content.split('resource "aws_security_group" "ecs"')[1].split(
        'resource "aws_security_group"'
    )[0]
    assert "security_groups = [aws_security_group.alb.id]" in ecs_sg
    assert "0.0.0.0/0" not in ecs_sg.split("egress")[0]  # no public ingress


def test_rds_and_redis_security_groups_only_allow_inbound_from_ecs() -> None:
    content = _main_tf()
    rds_sg = content.split('resource "aws_security_group" "rds"')[1].split(
        'resource "aws_security_group"'
    )[0]
    redis_sg = content.split('resource "aws_security_group" "redis"')[1]

    assert "security_groups = [aws_security_group.ecs.id]" in rds_sg
    assert "security_groups = [aws_security_group.ecs.id]" in redis_sg
    assert "0.0.0.0/0" not in rds_sg.split("egress")[0]
    assert "0.0.0.0/0" not in redis_sg.split("egress")[0]


def test_networking_module_is_wired_into_the_dev_environment() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "networking"' in main_tf
    assert 'source = "../../modules/networking"' in main_tf
