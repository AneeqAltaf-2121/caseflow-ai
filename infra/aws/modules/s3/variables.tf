variable "name_prefix" {
  description = "Prefix applied to the bucket name (account id is appended for global uniqueness)."
  type        = string
}

variable "noncurrent_version_expiration_days" {
  description = "Days to keep a superseded object version (from S3 versioning) before it's permanently deleted."
  type        = number
  default     = 365
}

variable "standard_ia_transition_days" {
  description = "Days before a current object version transitions to Standard-IA (cheaper, for evidence that's rarely re-read after initial ingestion)."
  type        = number
  default     = 90
}

variable "tags" {
  type    = map(string)
  default = {}
}
