variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet ids (from the networking module) to place the DB subnet group in."
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group id (the networking module's rds security group — inbound 5432 from ECS only)."
  type        = string
}

variable "engine_version" {
  description = "PostgreSQL engine version. 16.x has pgvector support built in (CREATE EXTENSION vector needs no custom parameter group) — see ADR 002."
  type        = string
  default     = "16.4"
}

variable "instance_class" {
  description = "RDS instance class. db.t4g.micro is enough for a dev/demo workload at low cost."
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Initial storage, in GiB."
  type        = number
  default     = 20
}

variable "max_allocated_storage" {
  description = "Ceiling for RDS storage autoscaling, in GiB."
  type        = number
  default     = 100
}

variable "database_name" {
  type    = string
  default = "caseflow"
}

variable "master_username" {
  type    = string
  default = "caseflow"
}

variable "multi_az" {
  description = "Standby replica in a second AZ for automatic failover. false is the appropriate default for dev; a production environment would set this true."
  type        = bool
  default     = false
}

variable "backup_retention_period" {
  description = "Days of automated backups to retain."
  type        = number
  default     = 7
}

variable "deletion_protection" {
  description = "Blocks `terraform destroy`/console deletion until explicitly disabled. false in dev so the environment can actually be torn down; a production environment would set this true."
  type        = bool
  default     = false
}

variable "skip_final_snapshot" {
  description = "Skip taking a final snapshot on deletion. true in dev for easy teardown; a production environment would set this false."
  type        = bool
  default     = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
