terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

variable "task_role_arn" { type = string }
variable "allowed_models" {
  type = list(string)
  default = [
    "anthropic.claude-opus-4-7-v1:0",
    "anthropic.claude-sonnet-4-6-v1:0",
    "anthropic.claude-haiku-4-5-v1:0",
  ]
}

# Bedrock AgentCore session isolation is configured at the model-invoke layer.
# Here we attach the minimum IAM that lets ECS tasks call InvokeModel for the
# allowed models only — no wildcard model access.
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "InvokeAllowedModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      for m in var.allowed_models : "arn:aws:bedrock:*::foundation-model/${m}"
    ]
  }
}

resource "aws_iam_policy" "bedrock" {
  name   = "avengers-bedrock-invoke"
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

resource "aws_iam_role_policy_attachment" "task_bedrock" {
  role       = split("/", var.task_role_arn)[1]
  policy_arn = aws_iam_policy.bedrock.arn
}
