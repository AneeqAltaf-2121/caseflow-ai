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
#   Phase 50 -> module "alb" (ecs services attach to its target groups)
#   Phase 51 -> module "secrets" (ecs's api/worker containers inject its ARNs)
#   Phase 52 -> module "observability" (alarms on top of ecs/alb/rds)

module "networking" {
  source = "../../modules/networking"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "rds" {
  source = "../../modules/rds"

  name_prefix        = local.name_prefix
  private_subnet_ids = module.networking.private_subnet_ids
  security_group_id  = module.networking.rds_security_group_id
  tags               = local.common_tags
}

module "redis" {
  source = "../../modules/redis"

  name_prefix        = local.name_prefix
  private_subnet_ids = module.networking.private_subnet_ids
  security_group_id  = module.networking.redis_security_group_id
  tags               = local.common_tags
}

module "s3" {
  source = "../../modules/s3"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "iam" {
  source = "../../modules/iam"

  name_prefix          = local.name_prefix
  documents_bucket_arn = module.s3.bucket_arn
  tags                 = local.common_tags
}

module "secrets" {
  source = "../../modules/secrets"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

module "alb" {
  source = "../../modules/alb"

  name_prefix       = local.name_prefix
  vpc_id            = module.networking.vpc_id
  public_subnet_ids = module.networking.public_subnet_ids
  security_group_id = module.networking.alb_security_group_id
  tags              = local.common_tags
}

module "ecs" {
  source = "../../modules/ecs"

  name_prefix             = local.name_prefix
  private_subnet_ids      = module.networking.private_subnet_ids
  security_group_id       = module.networking.ecs_security_group_id
  task_execution_role_arn = module.iam.task_execution_role_arn
  task_role_arn           = module.iam.task_role_arn
  api_target_group_arn    = module.alb.api_target_group_arn
  web_target_group_arn    = module.alb.web_target_group_arn
  tags                    = local.common_tags

  api_secrets = [
    { name = "OAUTH_CLIENT_SECRET", valueFrom = module.secrets.oauth_client_secret_arn },
    { name = "ANTHROPIC_API_KEY", valueFrom = module.secrets.anthropic_api_key_arn },
    { name = "OPENAI_API_KEY", valueFrom = module.secrets.openai_api_key_arn },
    { name = "JWT_SECRET_KEY", valueFrom = module.secrets.jwt_secret_key_arn },
  ]
}

module "observability" {
  source = "../../modules/observability"

  name_prefix                 = local.name_prefix
  alb_arn_suffix              = module.alb.alb_arn_suffix
  api_target_group_arn_suffix = module.alb.api_target_group_arn_suffix
  ecs_cluster_name            = module.ecs.cluster_name
  api_service_name            = module.ecs.api_service_name
  worker_service_name         = module.ecs.worker_service_name
  worker_log_group_name       = module.ecs.worker_log_group_name
  db_instance_id              = module.rds.db_instance_id
  tags                        = local.common_tags
}
