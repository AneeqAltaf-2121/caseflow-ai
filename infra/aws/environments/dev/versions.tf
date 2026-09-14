# Phase 44: Terraform foundation.
#
# Local backend (the default — no `backend` block) rather than the S3 +
# DynamoDB-lock backend a real deployment would use: this project has no
# AWS account to host that backend in, and `terraform init` needs a
# reachable backend to succeed at all. A real deployment would add:
#
#   terraform {
#     backend "s3" {
#       bucket         = "caseflow-ai-terraform-state"
#       key            = "dev/terraform.tfstate"
#       region         = "us-east-1"
#       dynamodb_table = "caseflow-ai-terraform-locks"
#       encrypt        = true
#     }
#   }
#
# — deliberately left as a comment, not configured, so `terraform init`
# and `terraform validate` (Phase 53, this project's CI) run with zero
# AWS access.

terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
