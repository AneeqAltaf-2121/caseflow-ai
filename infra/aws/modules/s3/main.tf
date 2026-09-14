# Phase 48: S3 document storage — the bucket `S3StorageBackend` (ADR
# 005, app/integrations/storage.py) already targets when
# `STORAGE_BACKEND=s3`; no application code changes, only configuration
# (see docs/decisions/010-aws-architecture.md).

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "documents" {
  # S3 bucket names are globally unique across all AWS accounts — the
  # account id suffix guarantees that without needing a random_id
  # resource (whose state, once created, would need preserving across
  # applies anyway).
  bucket = "${var.name_prefix}-documents-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, { Name = "${var.name_prefix}-documents" })
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket = aws_s3_bucket.documents.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "transition-and-expire-old-versions"
    status = "Enabled"

    filter {}

    transition {
      days          = var.standard_ia_transition_days
      storage_class = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_version_expiration_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
