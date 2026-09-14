# Phase 52: CloudWatch alarms on top of the log groups Phase 49 already
# created alongside each ECS task definition. One SNS topic fans out
# every alarm; a real deployment would subscribe an email/Slack/
# PagerDuty endpoint to it (out of scope here — no such endpoint exists
# to subscribe, and Terraform shouldn't invent one), but the topic and
# every alarm's wiring to it are real and validate on their own.

resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-alerts"
  tags = var.tags
}

# --- 5xx errors -----------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name_prefix}-api-5xx"
  alarm_description   = "The api target group is returning too many 5xx responses."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.alarm_5xx_threshold
  period              = var.period_seconds
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.api_target_group_arn_suffix
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# --- unhealthy tasks --------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "api_unhealthy_hosts" {
  alarm_name          = "${var.name_prefix}-api-unhealthy-hosts"
  alarm_description   = "One or more api tasks are failing the ALB's /ready health check."
  namespace           = "AWS/ApplicationELB"
  metric_name         = "UnHealthyHostCount"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  period              = var.period_seconds
  evaluation_periods  = var.evaluation_periods
  treat_missing_data  = "notBreaching"

  dimensions = {
    LoadBalancer = var.alb_arn_suffix
    TargetGroup  = var.api_target_group_arn_suffix
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# --- high CPU (api + worker services) --------------------------------

resource "aws_cloudwatch_metric_alarm" "api_high_cpu" {
  alarm_name          = "${var.name_prefix}-api-high-cpu"
  alarm_description   = "The api ECS service is running hot and may need more capacity."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.cpu_high_threshold_percent
  period              = var.period_seconds
  evaluation_periods  = var.evaluation_periods
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.api_service_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "worker_high_cpu" {
  alarm_name          = "${var.name_prefix}-worker-high-cpu"
  alarm_description   = "The worker ECS service is running hot and may need more capacity."
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.cpu_high_threshold_percent
  period              = var.period_seconds
  evaluation_periods  = var.evaluation_periods
  treat_missing_data  = "notBreaching"

  dimensions = {
    ClusterName = var.ecs_cluster_name
    ServiceName = var.worker_service_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# --- failed background jobs --------------------------------------------
# Dramatiq doesn't publish a CloudWatch metric of its own, so a metric
# filter counts lines matching a failure pattern in the worker's log
# group (already created in the ecs module) and an alarm watches that
# derived metric.

resource "aws_cloudwatch_log_metric_filter" "worker_failed_jobs" {
  name           = "${var.name_prefix}-worker-failed-jobs"
  log_group_name = var.worker_log_group_name
  pattern        = "?ERROR ?Error ?FAILED ?Failed"

  metric_transformation {
    name          = "FailedJobs"
    namespace     = "${var.name_prefix}/worker"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_failed_jobs" {
  alarm_name          = "${var.name_prefix}-worker-failed-jobs"
  alarm_description   = "Background jobs are failing faster than expected."
  namespace           = aws_cloudwatch_log_metric_filter.worker_failed_jobs.metric_transformation[0].namespace
  metric_name         = aws_cloudwatch_log_metric_filter.worker_failed_jobs.metric_transformation[0].name
  statistic           = "Sum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.failed_jobs_threshold
  period              = var.period_seconds
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

# --- DB pressure -------------------------------------------------------

resource "aws_cloudwatch_metric_alarm" "db_high_cpu" {
  alarm_name          = "${var.name_prefix}-db-high-cpu"
  alarm_description   = "RDS CPU utilization is sustained and high."
  namespace           = "AWS/RDS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = var.db_cpu_high_threshold_percent
  period              = var.period_seconds
  evaluation_periods  = var.evaluation_periods
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.db_instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "db_low_storage" {
  alarm_name          = "${var.name_prefix}-db-low-storage"
  alarm_description   = "RDS is running low on free storage."
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Average"
  comparison_operator = "LessThanThreshold"
  threshold           = var.db_free_storage_low_bytes
  period              = var.period_seconds
  evaluation_periods  = var.evaluation_periods
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = var.db_instance_id
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  tags          = var.tags
}
