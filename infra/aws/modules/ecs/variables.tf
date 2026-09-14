variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets the Fargate tasks run in (no public IP)."
  type        = list(string)
}

variable "security_group_id" {
  description = "The networking module's ECS security group (ingress from the ALB only)."
  type        = string
}

variable "task_execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "api_target_group_arn" {
  description = "ALB target group the api service registers its tasks with (Phase 50). Null skips ALB attachment."
  type        = string
  default     = null
}

variable "web_target_group_arn" {
  description = "ALB target group the web service registers its tasks with (Phase 50). Null skips ALB attachment."
  type        = string
  default     = null
}

variable "health_check_grace_period_seconds" {
  description = "Grace period before the ECS deployment considers a slow-to-start ALB-attached task unhealthy."
  type        = number
  default     = 60
}

variable "api_image" {
  description = "Container image URI for the api and worker services (they share one image, differing only by command — the api Dockerfile from Phase 39)."
  type        = string
  default     = "caseflow-ai-api:latest"
}

variable "web_image" {
  description = "Container image URI for the web service (the frontend Dockerfile from Phase 39)."
  type        = string
  default     = "caseflow-ai-web:latest"
}

variable "api_port" {
  type    = number
  default = 8000
}

variable "web_port" {
  type    = number
  default = 3000
}

variable "worker_command" {
  description = "Command override that turns the shared api image into the background worker process."
  type        = list(string)
  default     = ["python", "-m", "app.worker"]
}

variable "api_desired_count" {
  type    = number
  default = 1
}

variable "worker_desired_count" {
  type    = number
  default = 1
}

variable "web_desired_count" {
  type    = number
  default = 1
}

variable "api_cpu" {
  type    = number
  default = 512
}

variable "api_memory" {
  type    = number
  default = 1024
}

variable "worker_cpu" {
  type    = number
  default = 512
}

variable "worker_memory" {
  type    = number
  default = 1024
}

variable "web_cpu" {
  type    = number
  default = 256
}

variable "web_memory" {
  type    = number
  default = 512
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for all three services' log groups."
  type        = number
  default     = 30
}

variable "tags" {
  type    = map(string)
  default = {}
}
