"""Phase 48: S3 IaC. `terraform init/fmt/validate` all pass for real
against environments/dev with this module wired in — these tests check
the specific properties the phase spec calls for (encryption, public
access block, lifecycle policy, versioning), since `validate` alone
only proves the HCL parses.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
S3_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "s3"


def _main_tf() -> str:
    return (S3_MODULE / "main.tf").read_text()


def test_versioning_is_enabled() -> None:
    content = _main_tf()
    assert 'resource "aws_s3_bucket_versioning" "documents"' in content
    assert 'status = "Enabled"' in content


def test_server_side_encryption_is_configured() -> None:
    content = _main_tf()
    assert 'resource "aws_s3_bucket_server_side_encryption_configuration" "documents"' in content
    assert 'sse_algorithm = "AES256"' in content


def test_all_four_public_access_block_settings_are_true() -> None:
    content = _main_tf()
    block = content.split('resource "aws_s3_bucket_public_access_block" "documents"')[1]
    for setting in (
        "block_public_acls",
        "block_public_policy",
        "ignore_public_acls",
        "restrict_public_buckets",
    ):
        assert re.search(rf"{setting}\s*=\s*true", block)


def test_lifecycle_policy_transitions_and_expires_old_versions() -> None:
    content = _main_tf()
    assert 'resource "aws_s3_bucket_lifecycle_configuration" "documents"' in content
    assert "noncurrent_version_expiration" in content
    assert "transition" in content
    assert "STANDARD_IA" in content


def test_bucket_name_is_globally_unique_via_account_id_suffix() -> None:
    content = _main_tf()
    assert "data.aws_caller_identity.current.account_id" in content


def test_s3_module_is_wired_into_the_dev_environment() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "s3"' in main_tf
    assert 'source = "../../modules/s3"' in main_tf
