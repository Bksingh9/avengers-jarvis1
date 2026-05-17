terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

variable "tenant_ids" { type = list(string) }
variable "tags" { type = map(string), default = {} }

# Spec §5.3: one KMS key per tenant — hard isolation boundary.
resource "aws_kms_key" "tenant" {
  for_each                = toset(var.tenant_ids)
  description             = "AVENGERS per-tenant CMK (${each.key})"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false
  tags                    = merge(var.tags, { TenantId = each.key })
}

resource "aws_kms_alias" "tenant" {
  for_each      = toset(var.tenant_ids)
  name          = "alias/avengers-${each.key}"
  target_key_id = aws_kms_key.tenant[each.key].id
}

output "key_arns" {
  value = { for k, v in aws_kms_key.tenant : k => v.arn }
}
