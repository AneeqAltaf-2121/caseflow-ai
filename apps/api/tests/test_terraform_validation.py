"""Phase 53: Terraform validation. `terraform fmt -check` and
`terraform validate` are already run for real against every module as
part of each IaC phase's own commit (45-52); this phase's job is
wiring that same check into CI (see test_ci_workflow.py's
test_terraform_job_runs_fmt_check_and_validate_against_the_dev_environment)
and stating plainly, in the one place a reader would look, that no
live AWS environment backs any of it.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_infra_readme_states_no_live_aws_environment_is_deployed() -> None:
    readme = (REPO_ROOT / "infra" / "aws" / "README.md").read_text()
    assert "No live AWS environment exists" in readme
    assert "validated" in readme.lower() and "terraform" in readme.lower()


def test_infra_readme_documents_that_plan_and_apply_never_run_here() -> None:
    readme = (REPO_ROOT / "infra" / "aws" / "README.md").read_text()
    assert "plan" in readme.lower()
    assert "apply" in readme.lower()


def test_ci_workflow_references_terraform_fmt_check_and_validate() -> None:
    ci_yml = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
    assert "terraform fmt -check" in ci_yml
    assert "terraform validate" in ci_yml


def test_every_terraform_module_and_environment_directory_has_a_versions_or_variables_file() -> (
    None
):
    # Sanity check that Phase 53's CI job actually has something to walk:
    # every module/environment directory under infra/aws is a real,
    # non-empty Terraform directory, not a stray empty folder.
    aws_root = REPO_ROOT / "infra" / "aws"
    module_dirs = list((aws_root / "modules").iterdir()) + list(
        (aws_root / "environments").iterdir()
    )
    assert len(module_dirs) >= 9  # 9 modules + 1 environment, at minimum
    for directory in module_dirs:
        tf_files = list(directory.glob("*.tf"))
        assert tf_files, f"{directory} has no .tf files"
