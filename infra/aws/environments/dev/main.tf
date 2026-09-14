# Phase 44: environment root — wires every module together. Modules
# themselves stay environment-agnostic (no hardcoded "dev"); this file
# is the one place that composes them for the dev environment specifically.
# A second environment (e.g. staging) would be a sibling directory
# under infra/aws/environments/ instantiating the same modules with
# different variable values, never a copy-pasted module.

locals {
  name_prefix = "${var.project_name}-${var.environment}"

  common_tags = {
    Project     = var.project_name
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Module calls are added incrementally, one per phase, rather than all
# at once here — see the phase-by-phase commit history:
#   Phase 45 -> module "networking" (below)
#   Phase 46 -> module "rds"
#   Phase 47 -> module "redis"
#   Phase 48 -> module "s3"
#   Phase 49 -> module "ecs" (+ module "iam" for task roles)
#   Phase 50 -> load balancer resources (folded into "ecs" or its own "alb" module)
#   Phase 51 -> module "secrets"
#   Phase 52 -> module "observability"

module "networking" {
  source = "../../modules/networking"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}
