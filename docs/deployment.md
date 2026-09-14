# Deployment

## Status

**No live environment exists for this project beyond a developer's own
machine.** Local development runs the full stack via Docker Compose
(Phase 39) — that part of this document is accurate today and
reproducible by anyone who clones the repo. The AWS section below
describes how deploying to a real account *would* proceed, using the
Terraform this project actually ships (`infra/aws/`, Phases 44-53,
validated by `terraform fmt -check`/`terraform validate` in CI) — it
has never been run against a real AWS account, since this project
intentionally has neither one nor the credentials for one. Treat the
AWS section as a runbook to follow once an account exists, not a
record of something already done.

## Local development (Docker Compose)

This is the one deployment target that's real today.

```bash
cp .env.example .env   # override anything you need to (see the file's comments)
docker compose up --build
```

This boots seven services: `postgres` (pgvector), `redis`, `migrate`
(runs `alembic upgrade head` and exits), `api`, `worker`, `web`, in the
dependency order docker-compose's `depends_on: condition:
service_completed_successfully`/`service_healthy` enforces — `migrate`
must exit 0 before `api`/`worker` start, and both must report healthy
before `web`'s build even matters to a user hitting it. The api and
worker containers are `apps/api/Dockerfile`'s image with different
commands, exactly like the AWS Terraform below models it. See the root
`README.md` for the full local setup (non-Docker) alternative and
`.env.example` for every setting.

To run it exactly like CI does, see `.github/workflows/ci.yml`'s `e2e`
job — it's the same `docker compose up --build -d`, polls both
containers' Docker `HEALTHCHECK` status, then runs the Playwright
suite against it.

## AWS (target architecture, not yet deployed)

The full design rationale lives in
`docs/decisions/010-aws-architecture.md`; this section is the
step-by-step a real deployment would follow, not a new design.

```
Internet
   |
Application Load Balancer (public subnets)
   |-- /health, /ready, /auth/*, /projects/* --> target group --> ECS Fargate: api service
   |-- /                        (default)    --> target group --> ECS Fargate: web service
ECS Fargate: worker service (no ALB target)
ECS Task (one-shot): migrate — run explicitly, not a long-running service
   |
   +--> RDS PostgreSQL (pgvector) · ElastiCache Redis · S3 · Secrets Manager · CloudWatch
```

### Prerequisites

- An AWS account and credentials with permission to create the
  resources in `infra/aws/modules/` (VPC, RDS, ElastiCache, ECS, ALB,
  IAM, S3, Secrets Manager, CloudWatch, SNS).
- Terraform >= 1.9 (the version `infra/aws/environments/dev/versions.tf`
  pins).
- A container registry the ECS task definitions can pull from — the
  Terraform's `api_image`/`web_image` variables default to bare image
  names (`caseflow-ai-api:latest`) and expect a real registry URI
  (e.g. an ECR repository) once one exists; ECR repositories
  themselves aren't provisioned by this Terraform, since creating them
  is a one-time bootstrapping step independent of environment-specific
  infrastructure.
- A Terraform state backend. `versions.tf` deliberately has none
  configured (state is local, gitignored) because no team or CI
  pipeline shares this state today — see that file's comment for what
  an S3+DynamoDB backend block would look like when one is needed.

### Steps

1. **Bootstrap a container registry and push images.** Build
   `apps/api/Dockerfile` and `apps/web/Dockerfile` (the same
   Dockerfiles Compose and CI's `docker` job already build) and push
   both to ECR, then set `api_image`/`web_image` in
   `environments/dev/terraform.tfvars` to the pushed URIs.

2. **`terraform init` / `plan` / `apply`** from
   `infra/aws/environments/dev`. This stands up networking, RDS,
   Redis, S3, IAM, ECS (cluster + task definitions, api/web/worker
   services at `desired_count = 0` the first time — see step 4), ALB,
   Secrets Manager containers, and CloudWatch alarms, in one apply
   (Terraform resolves the dependency graph the modules already
   express — `main.tf`'s `module` blocks reference each other's
   outputs, so ordering is automatic).

3. **Populate the externally-issued secrets.** Terraform creates the
   Secrets Manager *containers* for the OAuth client secret and both
   LLM API keys but never their values (Phase 51 — nothing here can
   generate credentials a third party issues). Populate them once,
   out-of-band:

   ```bash
   aws secretsmanager put-secret-value \
     --secret-id caseflow-ai-dev-oauth-client-secret \
     --secret-string '<value from Google Cloud Console>'
   # repeat for caseflow-ai-dev-anthropic-api-key, caseflow-ai-dev-openai-api-key
   ```

   The JWT signing key and the RDS master password need no such step —
   Terraform (via `random_password`) and RDS itself
   (`manage_master_user_password`) already generated and stored them.

4. **Run the migration task once, before the first deploy.**

   ```bash
   aws ecs run-task \
     --cluster <ecs_cluster_name output> \
     --task-definition <migrate_task_definition_arn output> \
     --launch-type FARGATE \
     --network-configuration "awsvpcConfiguration={subnets=[<private_subnet_ids>],securityGroups=[<ecs_security_group_id>]}"
   ```

   Wait for it to exit 0 (check its CloudWatch log group,
   `/ecs/caseflow-ai-dev/migrate`), the same completed-before-anything-
   else-starts ordering `depends_on: service_completed_successfully`
   gives `migrate` in docker-compose.

5. **Scale the services up.** Set `api_desired_count`,
   `worker_desired_count`, and `web_desired_count` to 1 (or more) in
   `terraform.tfvars` and `terraform apply` again — or `aws ecs
   update-service --desired-count N` directly for a faster first
   rollout without a full apply.

6. **Point a domain at the ALB and add HTTPS.** The ALB Terraform
   (Phase 50) is deliberately HTTP-only on port 80 — no domain or ACM
   certificate exists in this project's scope to request one against.
   Once a domain exists: request/validate an ACM certificate for it,
   add an HTTPS listener on port 443 using that certificate, and
   change the existing HTTP listener's default action to a redirect to
   HTTPS instead of forwarding.

7. **Subscribe something to the alerts topic.** The `observability`
   module (Phase 52) creates every alarm and one SNS topic they publish
   to, but subscribes nothing to it — no email/Slack/PagerDuty endpoint
   exists to subscribe in this project's scope.
   `aws sns subscribe --topic-arn <alerts_topic_arn output> --protocol
   email --notification-endpoint <you>` is the one-line step that
   makes the alarms actually reach someone.

### Redeploying an application change

New application code doesn't need a `terraform apply` at all: build
and push a new image tag, then `aws ecs update-service --force-new-
deployment` for the affected service(s) (`api`/`worker` share the same
image, so both need it; `web` only needs it for frontend changes). Run
the migrate task first (step 4) whenever the change includes a new
Alembic revision — exactly the same ordering constraint docker-compose
already encodes for local development.

### Rollback

ECS keeps the previous task definition revision registered even after
a new one is deployed. Rolling back is `aws ecs update-service
--task-definition <previous-revision-arn>` for the affected service —
no Terraform involved, since the infrastructure (cluster, roles,
networking) isn't what changed. A rollback that must also reverse a
database migration needs its own down-migration run through the same
`migrate` one-shot task, the same way it would locally.

### Cost

Every module defaults to the smallest configuration that still
demonstrates the intended architecture (single NAT gateway, single-AZ
RDS and Redis, `db.t4g.micro`/`cache.t4g.micro`-class defaults, Fargate
tasks with modest CPU/memory) — appropriate for a dev environment, not
for production traffic. None of this has been priced against a real
account since none exists; a real deployment should run `terraform
plan` and review the resources it would create before ever running
`apply`.
