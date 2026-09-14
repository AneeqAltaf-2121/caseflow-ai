# Infrastructure as code (AWS)

**No live AWS environment exists for this project.** This is validated
Terraform describing the target architecture (see
`docs/decisions/010-aws-architecture.md`) — `terraform fmt -check` and
`terraform validate` run in CI (Phase 53); `terraform plan`/`apply`
never run against a real account here, since this project has none.

## Layout

```text
infra/aws/
├── environments/
│   └── dev/              # Composes every module for one environment.
│                          # A second environment would be a sibling
│                          # directory, never a copy-pasted module.
└── modules/
    ├── networking/        # VPC, subnets, route tables, security groups
    ├── iam/                # ECS task/execution roles
    ├── s3/                 # Document storage bucket
    ├── rds/                # PostgreSQL + pgvector
    ├── redis/              # ElastiCache Redis
    ├── ecs/                # Cluster, task definitions, services
    ├── alb/                # Load balancer, target groups, listeners
    ├── secrets/            # Secrets Manager
    └── observability/      # CloudWatch log groups + alarms
```

Each module is environment-agnostic (no hardcoded "dev") — see
`environments/dev/main.tf` for how they're composed.

## Working with this locally

```bash
cd infra/aws/environments/dev
terraform init      # no backend configured — see versions.tf's comment
terraform fmt -check -recursive ..
terraform validate
```

Both commands succeed with zero AWS credentials — `validate` only
checks configuration syntax and internal consistency, no API calls.
`terraform plan`/`apply` need real AWS credentials this project
intentionally doesn't have.
