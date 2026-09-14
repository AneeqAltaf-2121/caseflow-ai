"""Phase 44: Terraform foundation. Validated for real in this session
with an actual Terraform CLI (`terraform init`, `fmt -check`,
`validate` all pass — see infra/aws/README.md for the exact commands),
which isn't available to pytest itself, so these tests check the
structure `terraform` needs to be pointed at: every module directory
Phases 45-52 fill in, and the environment root that composes them.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INFRA_ROOT = REPO_ROOT / "infra" / "aws"

EXPECTED_MODULES = {
    "networking",
    "iam",
    "s3",
    "rds",
    "redis",
    "ecs",
    "alb",
    "secrets",
    "observability",
}


def test_every_expected_module_directory_exists() -> None:
    modules_dir = INFRA_ROOT / "modules"
    actual = {p.name for p in modules_dir.iterdir() if p.is_dir()}
    assert actual >= EXPECTED_MODULES


def test_dev_environment_has_the_core_terraform_files() -> None:
    dev_dir = INFRA_ROOT / "environments" / "dev"
    for filename in ("versions.tf", "providers.tf", "variables.tf", "main.tf", "outputs.tf"):
        assert (dev_dir / filename).is_file()


def test_versions_file_pins_terraform_and_the_aws_provider() -> None:
    content = (INFRA_ROOT / "environments" / "dev" / "versions.tf").read_text()
    assert "required_version" in content
    assert 'source  = "hashicorp/aws"' in content


def test_no_backend_is_configured_so_init_needs_no_aws_access() -> None:
    """A real deployment would use an S3 + DynamoDB backend (documented
    in versions.tf's comment) — left commented out, not configured, so
    `terraform init` succeeds with zero AWS credentials."""
    content = (INFRA_ROOT / "environments" / "dev" / "versions.tf").read_text()
    assert 'backend "s3"' not in content.replace("#", "").split("\n")[0]
    # The only active (uncommented) `terraform {}` block has no `backend`
    # sub-block of its own.
    lines = [line for line in content.splitlines() if not line.strip().startswith("#")]
    assert not any(line.strip().startswith("backend ") for line in lines)


def test_tfvars_example_matches_declared_variables() -> None:
    variables = (INFRA_ROOT / "environments" / "dev" / "variables.tf").read_text()
    tfvars_example = (INFRA_ROOT / "environments" / "dev" / "terraform.tfvars.example").read_text()
    for var_name in ("aws_region", "project_name", "environment"):
        assert f'variable "{var_name}"' in variables
        assert f"{var_name} " in tfvars_example or f"{var_name}=" in tfvars_example
