# Phase 49: IAM roles for the ECS Fargate services (api, worker, web).
# All three services share these two roles — they run the same image
# family and need the same baseline permissions; per-service scoping
# is not warranted at this project's size.

data "aws_partition" "current" {}

# --- Task execution role -----------------------------------------------
# Used by the ECS agent itself (not application code) to pull the
# container image, write to CloudWatch Logs, and — once Phase 51 wires
# real secrets in — resolve `secrets` blocks in the task definition by
# reading Secrets Manager. This is the standard split AWS documents:
# execution role for the infrastructure, task role for the application.

resource "aws_iam_role" "task_execution" {
  name = "${var.name_prefix}-ecs-task-execution"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "task_execution_managed" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Execution role also needs to read secrets so the ECS agent can
# resolve `secrets = [...]` entries in a task definition (DB URL, LLM
# API keys, etc. — declared for real in Phase 51). Scoped to secrets
# tagged for this project rather than left wildcard-open.
resource "aws_iam_role_policy" "task_execution_secrets" {
  name = "${var.name_prefix}-ecs-task-execution-secrets"
  role = aws_iam_role.task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = "arn:${data.aws_partition.current.partition}:secretsmanager:*:*:secret:${var.name_prefix}-*"
      }
    ]
  })
}

# --- Task role -----------------------------------------------------------
# Assumed by the application code running inside the container (via the
# ECS credential provider). Grants only what the app itself needs at
# runtime: read/write/delete on the documents bucket it stores uploads in.

resource "aws_iam_role" "task" {
  name = "${var.name_prefix}-ecs-task"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
        Action    = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "task_s3_documents" {
  name = "${var.name_prefix}-ecs-task-s3-documents"
  role = aws_iam_role.task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${var.documents_bucket_arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = var.documents_bucket_arn
      }
    ]
  })
}
