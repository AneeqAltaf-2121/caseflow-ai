variable "aws_region" {
  description = "AWS region for every resource in this environment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short name prefixed onto every resource this environment creates."
  type        = string
  default     = "caseflow-ai"
}

variable "environment" {
  description = "Deployment environment name (dev, staging, production, ...)."
  type        = string
  default     = "dev"
}
