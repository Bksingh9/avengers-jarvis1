terraform {
  required_version = ">= 1.6"
}

# Temporal Cloud namespace — provisioned out-of-band via the Temporal Cloud
# UI/CLI. This module exists to record the dependency and produce the env vars
# the worker tasks need.

variable "namespace" { type = string }
variable "grpc_endpoint" { type = string }
variable "client_cert_secret_arn" { type = string }

output "env" {
  value = {
    TEMPORAL_NAMESPACE     = var.namespace
    TEMPORAL_GRPC_ENDPOINT = var.grpc_endpoint
    TEMPORAL_CERT_SECRET   = var.client_cert_secret_arn
  }
}
