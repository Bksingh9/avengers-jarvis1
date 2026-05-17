terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
  backend "s3" {
    bucket         = "avengers-tfstate-dev"
    key            = "envs/dev/terraform.tfstate"
    region         = "ap-south-1"
    dynamodb_table = "avengers-tflock-dev"
    encrypt        = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "avengers"
      Environment = "dev"
      ManagedBy   = "terraform"
    }
  }
}

variable "region" {
  type    = string
  default = "ap-south-1"
}

variable "tenant_ids" {
  type    = list(string)
  default = ["acme"]
}

variable "tenant_secret_names" {
  type = map(list(string))
  default = {
    acme = ["okta/client_id", "okta/client_secret", "slack/bot_token", "exa/api_key"]
  }
}

variable "api_image" { type = string }
variable "worker_image" { type = string }

# --- Modules -------------------------------------------------------------

module "vpc" {
  source = "../../modules/vpc"
  name   = "avengers-dev"
}

module "kms" {
  source     = "../../modules/kms"
  tenant_ids = var.tenant_ids
}

module "secrets" {
  source              = "../../modules/secrets"
  tenant_secret_names = var.tenant_secret_names
  kms_key_arns        = module.kms.key_arns
}

module "s3_audit" {
  source       = "../../modules/s3-audit"
  tenant_ids   = var.tenant_ids
  kms_key_arns = module.kms.key_arns
}

module "aurora" {
  source      = "../../modules/aurora"
  name        = "avengers-dev"
  vpc_id      = module.vpc.vpc_id
  subnet_ids  = module.vpc.private_subnet_ids
  kms_key_arn = module.kms.key_arns[var.tenant_ids[0]]
}

module "ecs" {
  source             = "../../modules/ecs"
  name               = "avengers-dev"
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  public_subnet_ids  = module.vpc.public_subnet_ids
  api_image          = var.api_image
  worker_image       = var.worker_image
  container_env = {
    AVENGERS_ENVIRONMENT = "dev"
    AVENGERS_REGION      = var.region
  }
}

module "bedrock" {
  source        = "../../modules/bedrock"
  task_role_arn = module.ecs.task_role_arn
}

output "alb_dns_name" { value = module.ecs.alb_dns_name }
output "audit_buckets" { value = module.s3_audit.bucket_names }
output "aurora_endpoint" { value = module.aurora.endpoint }
