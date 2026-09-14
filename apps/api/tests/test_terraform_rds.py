"""Phase 46: RDS PostgreSQL + pgvector IaC. `terraform init/fmt/validate`
all pass for real against environments/dev with this module wired in —
these tests check the specific properties the phase spec calls for
(encrypted storage, backups, private networking, security groups),
since `validate` alone only proves the HCL is well-formed.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RDS_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "rds"


def _main_tf() -> str:
    return (RDS_MODULE / "main.tf").read_text()


def test_storage_is_encrypted() -> None:
    assert "storage_encrypted     = true" in _main_tf()


def test_backups_are_enabled_via_a_retention_period_variable() -> None:
    content = _main_tf()
    assert "backup_retention_period = var.backup_retention_period" in content
    variables = (RDS_MODULE / "variables.tf").read_text()
    assert 'variable "backup_retention_period"' in variables
    assert "default     = 7" in variables


def test_instance_is_placed_in_the_private_db_subnet_group_and_not_public() -> None:
    content = _main_tf()
    assert "publicly_accessible    = false" in content
    assert "db_subnet_group_name   = aws_db_subnet_group.this.name" in content
    assert "subnet_ids = var.private_subnet_ids" in content


def test_instance_uses_the_shared_rds_security_group() -> None:
    content = _main_tf()
    assert "vpc_security_group_ids = [var.security_group_id]" in content


def test_no_master_password_variable_or_literal_is_declared() -> None:
    """RDS itself manages and rotates the master password in Secrets
    Manager (manage_master_user_password = true) — there should be no
    `password` *variable* or a `password = "..."` assignment for a
    literal value to ever end up in (explanatory prose mentioning the
    word "password" in a comment is fine and expected)."""
    content = _main_tf()
    variables = (RDS_MODULE / "variables.tf").read_text()
    assert "manage_master_user_password = true" in content
    assert 'variable "master_password"' not in variables
    assert "password" not in variables.lower()
    # A literal string assignment (`password = "..."`) would be the
    # actual red flag — manage_master_user_password's own boolean
    # assignment legitimately contains the substring "password" and
    # isn't one.
    assert 'password = "' not in content.lower()


def test_rds_module_is_wired_into_the_dev_environment_using_networking_outputs() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "rds"' in main_tf
    assert "module.networking.private_subnet_ids" in main_tf
    assert "module.networking.rds_security_group_id" in main_tf
