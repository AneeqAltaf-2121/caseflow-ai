# Phase 46: RDS PostgreSQL with pgvector (ADR 002's engine choice, now
# managed/HA-capable — see docs/decisions/010-aws-architecture.md).
# Encrypted storage, automated backups, private-subnets-only placement,
# and a master password Terraform never sees or stores in state
# (manage_master_user_password delegates that to RDS itself, which
# creates and rotates it in Secrets Manager — consistent with ADR 009's
# "no literal secrets in Terraform" stance, ahead of Phase 51 wiring
# the app to actually read it).

resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-db-subnets" })
}

resource "aws_db_instance" "this" {
  identifier = "${var.name_prefix}-postgres"

  engine         = "postgres"
  engine_version = var.engine_version
  instance_class = var.instance_class

  allocated_storage     = var.allocated_storage
  max_allocated_storage = var.max_allocated_storage
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.database_name
  username = var.master_username
  # RDS generates, stores, and rotates the master password in Secrets
  # Manager — no password variable exists in this module at all, so
  # there's nothing to accidentally hardcode or leak into state.
  manage_master_user_password = true

  db_subnet_group_name   = aws_db_subnet_group.this.name
  vpc_security_group_ids = [var.security_group_id]
  publicly_accessible    = false

  multi_az                = var.multi_az
  backup_retention_period = var.backup_retention_period
  backup_window           = "03:00-04:00"
  maintenance_window      = "mon:04:30-mon:05:30"

  deletion_protection = var.deletion_protection
  skip_final_snapshot = var.skip_final_snapshot
  final_snapshot_identifier = var.skip_final_snapshot ? null : (
    "${var.name_prefix}-postgres-final-snapshot"
  )

  apply_immediately = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-postgres" })
}
