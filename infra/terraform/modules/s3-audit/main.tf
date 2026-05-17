terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

variable "tenant_ids" { type = list(string) }
variable "kms_key_arns" {
  type        = map(string)
  description = "tenant_id -> KMS key arn from the kms module"
}
variable "retention_years" {
  type    = number
  default = 7
}
variable "tags" {
  type    = map(string)
  default = {}
}

# One bucket per tenant — separate audit S3 prefix is not enough; Object Lock
# must be set at bucket creation, so a separate bucket is the safe boundary.
resource "aws_s3_bucket" "audit" {
  for_each            = toset(var.tenant_ids)
  bucket              = "avengers-audit-${each.key}"
  object_lock_enabled = true
  force_destroy       = false
  tags                = merge(var.tags, { TenantId = each.key, Purpose = "audit" })
}

resource "aws_s3_bucket_versioning" "audit" {
  for_each = toset(var.tenant_ids)
  bucket   = aws_s3_bucket.audit[each.key].id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_object_lock_configuration" "audit" {
  for_each = toset(var.tenant_ids)
  bucket   = aws_s3_bucket.audit[each.key].id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = var.retention_years
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "audit" {
  for_each = toset(var.tenant_ids)
  bucket   = aws_s3_bucket.audit[each.key].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arns[each.key]
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "audit" {
  for_each                = toset(var.tenant_ids)
  bucket                  = aws_s3_bucket.audit[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "audit" {
  for_each = toset(var.tenant_ids)
  bucket   = aws_s3_bucket.audit[each.key].id

  rule {
    id     = "transition-to-glacier"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "GLACIER"
    }
  }
}

output "bucket_names" {
  value = { for k, v in aws_s3_bucket.audit : k => v.bucket }
}
