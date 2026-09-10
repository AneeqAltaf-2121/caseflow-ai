# Domain Model

This document defines CaseFlow AI's core entities and their relationships,
before any RAG-specific implementation. Everything in `apps/api/app/models`
should trace back to an entity defined here.

## Entities

### User
An authenticated individual. Identity comes from an OAuth provider
(Phase 4); CaseFlow does not store passwords.

- `id`, `email`, `display_name`, `avatar_url`, `created_at`

### Organization
Optional top-level tenant boundary above projects. A user can belong to
multiple organizations.

- `id`, `name`, `slug`, `created_at`

### Project
The primary unit of work — a document collection plus its conversations,
evaluations, and prompt versions. Belongs to an Organization.

- `id`, `organization_id`, `name`, `description`, `created_by`, `created_at`

### ProjectMember
Join entity between User and Project, carrying the authorization role.

- `id`, `project_id`, `user_id`, `role` (`owner` | `editor` | `viewer`), `invited_by`, `created_at`

### Document
A logical document uploaded to a project. May have multiple versions.

- `id`, `project_id`, `filename`, `content_type`, `size_bytes`, `checksum_sha256`,
  `status` (`uploaded` | `processing` | `ready` | `failed`), `uploaded_by`,
  `storage_key`, `created_at`

### DocumentVersion
An immutable version of a document's underlying file, so re-uploads don't
destroy history.

- `id`, `document_id`, `version_number`, `storage_key`, `checksum_sha256`, `created_at`

### DocumentChunk
A retrievable unit of text extracted from a document, with enough
positional metadata to support citations.

- `id`, `document_id`, `document_version_id`, `page_number`, `section`,
  `text`, `token_count`, `start_offset`, `end_offset`, `embedding`, `metadata`

### Conversation
A persisted research thread within a project.

- `id`, `project_id`, `title`, `created_by`, `created_at`, `updated_at`

### Message
A single turn in a Conversation.

- `id`, `conversation_id`, `role` (`user` | `assistant`), `content`,
  `prompt_version_id`, `model_run_id`, `created_at`

### Citation
A link from an assistant Message to the DocumentChunk(s) that ground it.

- `id`, `message_id`, `document_id`, `document_chunk_id`, `source_number`,
  `page_number`, `quote`

  `source_number` is the `[n]` marker the answer text actually cites (see
  `app/rag/citations.py`) — without it, a redisplayed conversation
  couldn't match citation markers in old answer text back to a specific
  source.

### PromptVersion
An immutable, named/versioned prompt template, owned by a Project. Prompts
are never edited in place — a change is a new version (`rag_answer_v2`,
etc.), enabling regression comparisons. At most one version per
`(project_id, name)` is `is_active` at a time — that's the version routes
actually use.

- `id`, `project_id`, `name`, `version`, `template`, `is_active`,
  `created_by`, `created_at`

### ModelRun
A record of a single LLM invocation, for cost/latency/observability and
evaluation.

- `id`, `provider`, `model`, `prompt_version_id`, `temperature`, `latency_ms`,
  `input_tokens`, `output_tokens`, `estimated_cost_usd`, `status`, `created_at`

### EvaluationRun
A batch evaluation against a dataset, for a given prompt/model/retriever
combination.

- `id`, `project_id`, `dataset_name`, `prompt_version_id`, `model`,
  `retriever_version`, `started_at`, `finished_at`, `status`

### EvaluationResult
A single graded example within an EvaluationRun.

- `id`, `evaluation_run_id`, `question`, `generated_answer`, `expected_answer`,
  `faithfulness_score`, `relevance_score`, `completeness_score`,
  `citation_correct`, `judge_reason`, `created_at`

### Job
A unit of asynchronous work (ingestion, evaluation run, report generation).

- `id`, `type`, `status` (`queued` | `running` | `succeeded` | `failed`),
  `attempt`, `max_attempts`, `payload`, `error`, `created_at`, `started_at`, `finished_at`

### AuditEvent
An immutable record of a security- or review-relevant action.

- `id`, `project_id`, `actor_user_id`, `action`, `target_type`, `target_id`,
  `metadata`, `created_at`

## Relationships

```
User
 └── belongs to Projects through ProjectMember (role: owner/editor/viewer)

Organization
 └── Projects

Project
 ├── Documents
 │    └── DocumentVersions
 │         └── DocumentChunks
 ├── Conversations
 │    └── Messages
 │         └── Citations -> DocumentChunk
 ├── EvaluationRuns
 │    └── EvaluationResults
 ├── PromptVersions
 └── Jobs

ModelRun is referenced by Message and EvaluationResult, not owned by Project
directly — it's a cross-cutting observability record.

AuditEvent references a Project and an actor User, and points at an
arbitrary target (document, evaluation, conversation, ...).
```

## Layering rule

Every entity above maps to exactly one SQLAlchemy model in
`apps/api/app/models/`. Access always flows:

```
API route -> Service -> Repository -> ORM model -> PostgreSQL
```

No route or service issues raw SQL; no repository contains business logic
or authorization decisions — those live in the service layer, which is the
only layer allowed to combine multiple repositories.
