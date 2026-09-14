# Phase 47: ElastiCache Redis — backs both the Dramatiq job queue
# (ADR 003) and the Phase 33 application cache, replacing
# docker-compose's redis:7-alpine container with a managed, encrypted,
# optionally-replicated one (see docs/decisions/010-aws-architecture.md).

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name_prefix}-redis-subnets"
  subnet_ids = var.private_subnet_ids

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis-subnets" })
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id = "${var.name_prefix}-redis"
  description           = "CaseFlow AI job queue + cache (${var.name_prefix})"

  engine         = "redis"
  engine_version = var.engine_version
  node_type      = var.node_type
  port           = 6379

  num_cache_clusters         = var.num_cache_clusters
  automatic_failover_enabled = var.num_cache_clusters > 1
  multi_az_enabled           = var.num_cache_clusters > 1

  subnet_group_name = aws_elasticache_subnet_group.this.name
  security_group_ids = [var.security_group_id]

  # Encrypted connections (Phase 47's own requirement) — both directions:
  # data at rest on the underlying nodes, and in transit between the
  # app and the cluster (the app connects over rediss:// once Phase 51
  # wires this endpoint in).
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true

  apply_immediately = true

  tags = merge(var.tags, { Name = "${var.name_prefix}-redis" })
}
