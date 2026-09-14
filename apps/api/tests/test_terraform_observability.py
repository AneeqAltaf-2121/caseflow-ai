"""Phase 52: CloudWatch alarms IaC. `terraform init/fmt/validate` all
pass for real against environments/dev with this module wired in —
these tests check the specific properties the phase spec calls for
(alarms for 5xx, unhealthy tasks, high CPU, failed jobs, DB pressure),
since `validate` alone only proves the HCL parses. Log groups and their
retention were already covered by test_terraform_ecs.py (Phase 49);
this file is only the alarms layered on top.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OBSERVABILITY_MODULE = REPO_ROOT / "infra" / "aws" / "modules" / "observability"


def _main_tf() -> str:
    return (OBSERVABILITY_MODULE / "main.tf").read_text()


def test_an_sns_topic_fans_out_every_alarm() -> None:
    content = _main_tf()
    assert 'resource "aws_sns_topic" "alerts"' in content
    assert content.count("aws_sns_topic.alerts.arn") >= 7  # every alarm below references it


def test_5xx_alarm_watches_the_api_target_group() -> None:
    content = _main_tf()
    block = content.split('resource "aws_cloudwatch_metric_alarm" "api_5xx"')[1].split("resource")[
        0
    ]
    assert 'metric_name         = "HTTPCode_Target_5XX_Count"' in block
    assert "var.api_target_group_arn_suffix" in block


def test_unhealthy_hosts_alarm_exists() -> None:
    content = _main_tf()
    block = content.split('resource "aws_cloudwatch_metric_alarm" "api_unhealthy_hosts"')[1].split(
        "resource"
    )[0]
    assert 'metric_name         = "UnHealthyHostCount"' in block


def test_high_cpu_alarms_cover_both_api_and_worker_services() -> None:
    content = _main_tf()
    for service in ("api", "worker"):
        block = content.split(f'resource "aws_cloudwatch_metric_alarm" "{service}_high_cpu"')[
            1
        ].split("resource")[0]
        assert 'namespace           = "AWS/ECS"' in block
        assert 'metric_name         = "CPUUtilization"' in block
        assert f"var.{service}_service_name" in block


def test_failed_jobs_are_derived_from_a_log_metric_filter_on_the_worker_log_group() -> None:
    content = _main_tf()
    assert 'resource "aws_cloudwatch_log_metric_filter" "worker_failed_jobs"' in content
    assert "log_group_name = var.worker_log_group_name" in content
    assert 'resource "aws_cloudwatch_metric_alarm" "worker_failed_jobs"' in content


def test_db_pressure_alarms_cover_cpu_and_free_storage() -> None:
    content = _main_tf()
    cpu_block = content.split('resource "aws_cloudwatch_metric_alarm" "db_high_cpu"')[1].split(
        "resource"
    )[0]
    storage_block = content.split('resource "aws_cloudwatch_metric_alarm" "db_low_storage"')[1]
    assert 'namespace           = "AWS/RDS"' in cpu_block
    assert "var.db_instance_id" in cpu_block
    assert 'metric_name         = "FreeStorageSpace"' in storage_block
    assert 'comparison_operator = "LessThanThreshold"' in storage_block


def test_observability_module_is_wired_into_the_dev_environment() -> None:
    main_tf = (REPO_ROOT / "infra" / "aws" / "environments" / "dev" / "main.tf").read_text()
    assert 'module "observability"' in main_tf
    assert 'source = "../../modules/observability"' in main_tf
    assert "db_instance_id              = module.rds.db_instance_id" in main_tf
