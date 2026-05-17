terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

# Per-tenant secret namespace (spec §7.1 secrets_namespace = avengers/<tenant>).
# Actual secret values are populated out-of-band; we only own the names + ACLs.
variable "tenant_secret_names" {
  type        = map(list(string))
  description = "tenant_id -> list of bare secret names (e.g. okta/client_id)"
}
variable "kms_key_arns" { type = map(string) }
variable "tags" {
  type    = map(string)
  default = {}
}

locals {
  flat = flatten([
    for tenant, names in var.tenant_secret_names : [
      for n in names : {
        tenant = tenant
        name   = n
        full   = "avengers/${tenant}/${n}"
      }
    ]
  ])
  by_key = { for s in local.flat : s.full => s }
}

resource "aws_secretsmanager_secret" "this" {
  for_each   = local.by_key
  name       = each.value.full
  kms_key_id = var.kms_key_arns[each.value.tenant]
  tags       = merge(var.tags, { TenantId = each.value.tenant })
}

output "secret_arns" {
  value = { for k, v in aws_secretsmanager_secret.this : k => v.arn }
}
