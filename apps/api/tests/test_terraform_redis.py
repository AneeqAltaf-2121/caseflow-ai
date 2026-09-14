"""Phase 47: ElastiCache Redis IaC. `terraform init/fmt/validate` all
pass for real against environments/dev with this module wired in —
these tests check the specific properties the phase spec calls for
(subnet group, security group, replication group, encrypted
connections), since `validate` alone only proves the HCL parses.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REDIS_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "redis"


def _main_tf() -> str:
    return (REDIS_MODULE / "main.tf").read_text()


def test_declares_a_subnet_group_in_private_subnets() -> None:
    content = _main_tf()
    assert 'resource "aws_elasticache_subnet_group" "this"' in content
    assert "subnet_ids = var.private_subnet_ids" in content


def test_declares_a_replication_group_not_a_bare_cluster() -> None:
    content = _main_tf()
    assert 'resource "aws_elasticache_replication_group" "this"' in content
    assert "aws_elasticache_cluster" not in content


def test_uses_the_shared_redis_security_group() -> None:
    content = _main_tf()
    assert "security_group_ids" in content
    assert "var.security_group_id" in content.split("security_group_ids")[1][:40]


def test_connections_are_encrypted_both_at_rest_and_in_transit() -> None:
    content = _main_tf()
    assert "at_rest_encryption_enabled" in content
    assert "transit_encryption_enabled" in content
    for line in content.splitlines():
        if "at_rest_encryption_enabled" in line or "transit_encryption_enabled" in line:
            assert line.strip().endswith("true")


def test_replica_count_is_a_configurable_variable_not_hardcoded() -> None:
    content = _main_tf()
    variables = (REDIS_MODULE / "variables.tf").read_text()
    assert "num_cache_clusters         = var.num_cache_clusters" in content
    assert 'variable "num_cache_clusters"' in variables


def test_redis_module_is_wired_into_the_dev_environment_using_networking_outputs() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "redis"' in main_tf
    assert "module.networking.redis_security_group_id" in main_tf
