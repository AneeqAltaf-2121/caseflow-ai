# Populated as each module lands (Phases 45-52) with the values a
# deployment or another environment would actually need to read —
# e.g. the ALB DNS name, RDS endpoint, ECR repository URLs.

output "vpc_id" {
  value = module.networking.vpc_id
}

output "public_subnet_ids" {
  value = module.networking.public_subnet_ids
}

output "private_subnet_ids" {
  value = module.networking.private_subnet_ids
}

output "db_endpoint" {
  value = module.rds.db_endpoint
}

output "db_master_user_secret_arn" {
  value = module.rds.master_user_secret_arn
}

output "redis_endpoint" {
  value = module.redis.primary_endpoint_address
}

output "documents_bucket_name" {
  value = module.s3.bucket_name
}

output "ecs_cluster_name" {
  value = module.ecs.cluster_name
}

output "alb_dns_name" {
  value = module.alb.alb_dns_name
}

output "alerts_topic_arn" {
  value = module.observability.alerts_topic_arn
}
