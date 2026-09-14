variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnet ids (from the networking module) to place the cache subnet group in."
  type        = list(string)
}

variable "security_group_id" {
  description = "Security group id (the networking module's redis security group — inbound 6379 from ECS only)."
  type        = string
}

variable "node_type" {
  description = "ElastiCache node type. cache.t4g.micro is enough for a dev/demo workload at low cost."
  type        = string
  default     = "cache.t4g.micro"
}

variable "engine_version" {
  type    = string
  default = "7.1"
}

variable "num_cache_clusters" {
  description = "1 for a single node (dev — no automatic failover); 2+ adds read replicas and enables automatic failover."
  type        = number
  default     = 1

  validation {
    condition     = var.num_cache_clusters >= 1
    error_message = "At least one cache cluster (the primary) is required."
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
