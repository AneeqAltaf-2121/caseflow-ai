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
