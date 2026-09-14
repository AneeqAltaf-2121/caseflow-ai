variable "name_prefix" {
  description = "Prefix applied to every resource this module creates."
  type        = string
}

variable "documents_bucket_arn" {
  description = "S3 documents bucket ARN (from the s3 module) — the task role gets read/write/delete on objects under it."
  type        = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
