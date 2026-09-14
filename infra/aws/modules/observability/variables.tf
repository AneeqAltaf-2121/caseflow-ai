variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "alb_arn_suffix" {
  description = "Short-form ALB ARN CloudWatch dimensions need."
  type        = string
}

variable "api_target_group_arn_suffix" {
  type = string
}

variable "ecs_cluster_name" {
  type = string
}

variable "api_service_name" {
  type = string
}

variable "worker_service_name" {
  type = string
}

variable "worker_log_group_name" {
  description = "Log group the worker ships to — a metric filter here counts failed background jobs."
  type        = string
}

variable "db_instance_id" {
  type = string
}

variable "alarm_5xx_threshold" {
  description = "Target-origin 5xx responses in one evaluation period before alarming."
  type        = number
  default     = 10
}

variable "cpu_high_threshold_percent" {
  type    = number
  default = 80
}

variable "db_cpu_high_threshold_percent" {
  type    = number
  default = 80
}

variable "db_free_storage_low_bytes" {
  description = "Alarm once free RDS storage drops below this many bytes."
  type        = number
  default     = 2147483648 # 2 GiB
}

variable "failed_jobs_threshold" {
  description = "Failed background jobs (per the worker log metric filter) in one evaluation period before alarming."
  type        = number
  default     = 5
}

variable "evaluation_periods" {
  type    = number
  default = 2
}

variable "period_seconds" {
  type    = number
  default = 300
}

variable "tags" {
  type    = map(string)
  default = {}
}
