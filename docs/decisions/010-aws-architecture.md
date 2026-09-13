# 010 — AWS architecture design

## Status
Accepted

## Context
Phases 44-53 implement this as validated Terraform (see those phases'
own ADRs/modules once built) with no live AWS environment — this
project's explicit scope, chosen at the outset, is infrastructure as
*validated code*, not a running deployment (no AWS account, credentials,
or billing are part of this exercise). This ADR fixes the target
architecture those later phases build toward, so the Terraform that
follows has one coherent design to implement rather than being invented
module-by-module.

The application already assumes a specific shape from earlier phases:
three Dockerized services sharing one backend image (api, worker,
migrate — Phase 39), a Postgres database with the pgvector extension
(ADR 002), Redis for jobs and caching (ADR 003, Phase 33), S3-compatible
object storage behind a `StorageBackend` abstraction (ADR 005), and a
Next.js frontend with dynamic, server-rendered routes (most of its pages
are "ƒ Dynamic" in the build output — see `apps/web`'s route list),
which rules out a pure static hosting target for it.

## Decision

```
Internet
   |
   v
Application Load Balancer (public subnets)
   |-- /api/*, /auth/*, /projects/*, ... --> target group --> ECS Fargate: api service
   |-- /               (default)        --> target group --> ECS Fargate: web service
   |
ECS Fargate: worker service (no ALB target — consumes jobs, doesn't serve HTTP)
   |
   +--> RDS PostgreSQL (pgvector extension) — private subnets
   +--> ElastiCache Redis — private subnets
   +--> S3 (document storage bucket)
   +--> Secrets Manager (DB/OAuth/LLM credentials, app secret)
   +--> CloudWatch (logs + alarms for all of the above)
```

- **Compute — ECS Fargate, three services, one cluster.** `api` and
  `worker` reuse the exact image `apps/api/Dockerfile` already builds
  (Phase 39) — same rationale as the docker-compose services: one image,
  different task command, no separate dependency set to maintain.
  `web` runs `apps/web/Dockerfile`'s standalone Next.js server. All
  three are Fargate tasks (no EC2 fleet to patch/scale by hand),
  in private subnets, with no public IP — only the ALB is
  internet-facing. `worker` isn't registered with any ALB target group;
  it has no HTTP endpoint to route to, matching how it has no
  HEALTHCHECK in the Dockerfile either (Phase 39's same reasoning).
- **Frontend — ECS Fargate (`web`), not Amplify or S3/CloudFront.**
  Considered: AWS Amplify Hosting (has native Next.js SSR support) and
  S3+CloudFront (static only). Amplify would work but moves part of the
  stack outside this project's own Terraform-managed ECS/ALB/VPC
  pattern into a separately-managed service with its own deploy
  mechanism; S3+CloudFront can't serve the app's dynamic, per-request
  routes at all (`/projects/[id]`, `/projects/[id]/chat`, etc. depend on
  a live Node server, not static files) without rebuilding the frontend
  as static-export-only, which it isn't. Running `web` as a third
  Fargate service keeps every piece of compute on one consistent,
  fully-Terraform-defined foundation (Phase 44's `networking`/`ecs`
  modules cover all three services identically) at the cost of Fargate
  being a heavier, less specialized runtime for a frontend than a CDN
  edge network would be.
- **Database — RDS PostgreSQL with the pgvector extension**, private
  subnets, encrypted storage, automated backups (Phase 46) — the same
  engine ADR 002 chose, now with a managed, HA-capable home instead of
  the docker-compose `pgvector/pgvector:pg16` image.
- **Cache/jobs — ElastiCache Redis** (Phase 47), private subnets,
  encrypted in-transit — backs both the Dramatiq job queue (ADR 003)
  and the Phase 33 cache, replacing the docker-compose `redis:7-alpine`
  container with a managed, replicated one.
- **Object storage — S3** (Phase 48): one bucket for uploaded documents,
  already the code path `S3StorageBackend` (ADR 005) targets by setting
  `STORAGE_BACKEND=s3` — no application code changes, only
  configuration.
- **Secrets — Secrets Manager** (Phase 51): OAuth client secret, LLM API
  keys, DB credentials, and the JWT signing secret are stored there and
  injected into ECS task definitions as secrets (not plaintext task
  environment variables) — never a literal value in Terraform state or
  source, consistent with ADR 009's secret-management stance.
- **Observability — CloudWatch** (Phase 52): container logs from all
  three services, with retention policies and alarms for 5xx rate,
  unhealthy target count, high CPU, failed job rate, and DB connection
  pressure.

## Rationale
- One ECS cluster for all three services (rather than, say, Lambda for
  the API or a managed platform for the frontend) keeps the Terraform
  surface area consistent and the docker-compose parity intentional:
  the same images that boot locally are what a real deployment would
  run, just orchestrated by ECS instead of Compose.
- Fargate over EC2-backed ECS: no host patching/capacity planning
  Terraform would otherwise need to own, appropriate for a project
  whose infrastructure is validated but never actually run.
- Keeping `migrate` conceptually a one-shot task (an ECS Task, not a
  Service — see Phase 49) mirrors docker-compose's `migrate` service
  exiting successfully before `api`/`worker` start, so the "don't race
  two processes applying the same migration" property Phase 39 already
  established carries over unchanged.

## Consequences
- Three ECS services means three task definitions, three sets of
  CloudWatch log groups, and the ALB needs host/path routing rules to
  send frontend requests to `web` and API requests to `api` (or,
  simpler and what Phase 50 implements, two separate listener rules by
  path prefix) — more Terraform surface than a single-service setup,
  traded for architectural consistency across the whole stack.
- No CDN edge caching for the frontend (a real tradeoff versus
  CloudFront) — acceptable for a project not serving live traffic;
  revisiting this would mean adding CloudFront in front of the ALB
  later without changing the ECS services themselves.
- This ADR fixes the shape; it does not stand up any of it — every
  subsequent AWS phase (44-53) produces Terraform that `terraform plan`
  can validate, never `terraform apply` against a real account. See
  Phase 53's ADR for how that's verified in CI, and docs/deployment.md
  (Phase 54) for what actually deploying this would involve.
